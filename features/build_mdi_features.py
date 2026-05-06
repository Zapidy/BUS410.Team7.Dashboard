#!/usr/bin/env python3
"""Build year-precise tract-year MDI (Minority Depository Institution) features.

For each (tract_fips, year) for years 2009-2024 produces:
    - mdi_branches_within_10mi    (count of MDI bank branches within 10 miles)
    - mdi_branches_within_25mi    (count within 25 miles, rural fallback)
    - nearest_mdi_branch_miles    (haversine distance to nearest MDI branch)
    - mdi_active_in_county        (1 if any MDI HQ'd in tract's county that year)

Inputs:
    data/raw/mdi/historical-data-year-2001-2025.xlsx  (FDIC historical MDI list,
        one sheet per year; header row index 4, data starts at row 5; columns
        include "Certificate Number" -> CERT)
    ../round5/data/raw/fdic/sod/sod_{year}.csv        (FDIC SoD branch-level)
    data/raw/tiger/tract_centroids_2020.csv           (tract_fips, lat, lon)

Output:
    data/processed/features/tract_year_mdi.csv

Notes on the MDI xlsx:
    The FDIC historical-MDI workbook has one sheet per year (2001-2025) plus
    Contents/Notes/Annual Totals. Each year sheet has a banner row, a date
    row, two blank rows, then a header row at index 4. The CERT column is
    labelled "Certificate Number". There is no RSSDID in the MDI file, so we
    join MDI -> SoD on CERT alone (CERT is FDIC's stable institution key).

Usage:
    python3 build_mdi_features.py                  # all years 2009-2024
    python3 build_mdi_features.py --years 2020 2021
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

ROOT = Path(__file__).resolve().parents[1]
MDI_XLSX = ROOT / "data" / "raw" / "mdi" / "historical-data-year-2001-2025.xlsx"
ROUND5_SOD = ROOT.parent / "round5" / "data" / "raw" / "fdic" / "sod"
TIGER_FILE = ROOT / "data" / "raw" / "tiger" / "tract_centroids_2020.csv"
OUT_DIR = ROOT / "data" / "processed" / "features"
OUT_FILE = OUT_DIR / "tract_year_mdi.csv"

PANEL_YEARS = list(range(2009, 2025))  # 2009-2024 inclusive

EARTH_R_MI = 3958.7613
RADIUS_10MI = 10.0 / EARTH_R_MI
RADIUS_25MI = 25.0 / EARTH_R_MI


def load_mdi_year(year: int) -> pd.DataFrame:
    """Read the MDI sheet for a given year and return DataFrame with CERT."""
    sheet = str(year)
    with warnings.catch_warnings():
        # FDIC's xlsx sometimes flags integer date cells (YYYYMMDD) as
        # invalid serial dates. Suppress the openpyxl warning — we don't
        # use those date columns.
        warnings.simplefilter("ignore")
        raw = pd.read_excel(MDI_XLSX, sheet_name=sheet, header=None, dtype=object)

    # Find the header row by searching for "Certificate" in column 0
    header_row = None
    for i in range(min(15, len(raw))):
        v = raw.iat[i, 0]
        if isinstance(v, str) and "certificate" in v.lower():
            header_row = i
            break
    if header_row is None:
        # Fallback: known FDIC pattern
        header_row = 4

    headers = [str(x).strip() if x is not None else f"col{i}"
               for i, x in enumerate(raw.iloc[header_row].tolist())]
    body = raw.iloc[header_row + 1:].copy()
    body.columns = headers
    # drop fully-empty rows (FDIC sometimes appends a totals/footer line)
    body = body.dropna(how="all")
    # CERT column
    cert_col = next((c for c in body.columns if c.lower().startswith("certificate")), None)
    if cert_col is None:
        cert_col = headers[0]
    body = body.rename(columns={cert_col: "CERT"})
    # Keep only rows where CERT is numeric
    body["CERT"] = pd.to_numeric(body["CERT"], errors="coerce")
    body = body.dropna(subset=["CERT"])
    body["CERT"] = body["CERT"].astype(int).astype(str)
    return body[["CERT"]].drop_duplicates().reset_index(drop=True)


def load_sod_year(year: int) -> pd.DataFrame:
    path = ROUND5_SOD / f"sod_{year}.csv"
    if not path.exists():
        return pd.DataFrame(columns=["CERT", "RSSDID", "lat", "lon", "STCNTYBR"])
    df = pd.read_csv(
        path,
        usecols=["CERT", "RSSDID", "SIMS_LATITUDE", "SIMS_LONGITUDE", "STCNTYBR"],
        dtype={"CERT": str, "RSSDID": str, "STCNTYBR": str},
    )
    df = df.rename(columns={"SIMS_LATITUDE": "lat", "SIMS_LONGITUDE": "lon"})
    df["CERT"] = df["CERT"].str.replace(r"\.0$", "", regex=True).str.strip()
    df = df.dropna(subset=["lat", "lon"])
    df = df[(df["lat"].between(17, 72)) & (df["lon"].between(-180, -65))]
    # 5-digit county FIPS
    df["county_fips"] = df["STCNTYBR"].str.zfill(5)
    return df.reset_index(drop=True)


def to_radians(df: pd.DataFrame, lat="lat", lon="lon") -> np.ndarray:
    return np.radians(df[[lat, lon]].to_numpy(dtype=float))


def build_year(year: int, tracts: pd.DataFrame, mdi_certs: set[str],
               sod: pd.DataFrame) -> pd.DataFrame:
    """Compute MDI features for one year."""
    n = len(tracts)
    if sod.empty or not mdi_certs:
        return pd.DataFrame({
            "tract_fips": tracts["tract_fips"].values,
            "year": year,
            "mdi_branches_within_10mi": 0,
            "mdi_branches_within_25mi": 0,
            "nearest_mdi_branch_miles": np.nan,
            "mdi_active_in_county": 0,
        })

    mdi_branches = sod[sod["CERT"].isin(mdi_certs)].copy()

    if mdi_branches.empty:
        return pd.DataFrame({
            "tract_fips": tracts["tract_fips"].values,
            "year": year,
            "mdi_branches_within_10mi": 0,
            "mdi_branches_within_25mi": 0,
            "nearest_mdi_branch_miles": np.nan,
            "mdi_active_in_county": 0,
        })

    tract_rad = to_radians(tracts)
    branch_rad = to_radians(mdi_branches)
    tree = BallTree(branch_rad, metric="haversine")

    # Nearest distance
    dist_rad, _ = tree.query(tract_rad, k=1)
    nearest_mi = dist_rad[:, 0] * EARTH_R_MI

    # Counts within 10 / 25 miles
    n10 = tree.query_radius(tract_rad, r=RADIUS_10MI, count_only=True)
    n25 = tree.query_radius(tract_rad, r=RADIUS_25MI, count_only=True)

    # mdi_active_in_county: a county with any MDI branch that year
    # (proxy for "MDI HQ'd in this tract's county" — SoD STCNTYBR is the
    # branch's county, so any branch presence = MDI active in that county).
    mdi_counties = set(mdi_branches["county_fips"].dropna().unique())
    tract_counties = tracts["tract_fips"].str[:5]
    mdi_active = tract_counties.isin(mdi_counties).astype(int).values

    return pd.DataFrame({
        "tract_fips": tracts["tract_fips"].values,
        "year": year,
        "mdi_branches_within_10mi": n10.astype(int),
        "mdi_branches_within_25mi": n25.astype(int),
        "nearest_mdi_branch_miles": nearest_mi,
        "mdi_active_in_county": mdi_active,
    })


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs="*", type=int, default=None)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not TIGER_FILE.exists():
        raise SystemExit(f"Missing tract centroid file: {TIGER_FILE}")
    tracts = pd.read_csv(TIGER_FILE, dtype={"tract_fips": str})
    tracts["tract_fips"] = tracts["tract_fips"].str.zfill(11)
    tracts = tracts.dropna(subset=["lat", "lon"]).reset_index(drop=True)
    print(f"Loaded {len(tracts):,} tract centroids", flush=True)

    if not MDI_XLSX.exists():
        raise SystemExit(f"Missing MDI xlsx: {MDI_XLSX}")

    years = args.years or PANEL_YEARS
    parts: list[pd.DataFrame] = []
    for y in years:
        sod_path = ROUND5_SOD / f"sod_{y}.csv"
        if not sod_path.exists():
            print(f"  Skipping {y}: no SoD file at {sod_path}", flush=True)
            continue
        mdi = load_mdi_year(y)
        sod = load_sod_year(y)
        certs = set(mdi["CERT"].tolist())
        matched = sod[sod["CERT"].isin(certs)]
        print(
            f"  {y}: MDI institutions={len(certs)}, SoD branches={len(sod):,}, "
            f"MDI branches matched={len(matched):,}",
            flush=True,
        )
        parts.append(build_year(y, tracts, certs, sod))

    if not parts:
        raise SystemExit("No years produced — check inputs.")

    out = pd.concat(parts, ignore_index=True)
    out.to_csv(OUT_FILE, index=False)
    print(f"\n→ {OUT_FILE} ({len(out):,} rows)", flush=True)

    # Quick coverage summary
    print("\nCoverage summary:", flush=True)
    summary = (
        out.groupby("year")
        .agg(
            n=("tract_fips", "size"),
            pct_with_mdi_10mi=("mdi_branches_within_10mi", lambda s: (s > 0).mean() * 100),
            pct_with_mdi_25mi=("mdi_branches_within_25mi", lambda s: (s > 0).mean() * 100),
            median_nearest_mi=("nearest_mdi_branch_miles", "median"),
            pct_county_active=("mdi_active_in_county", lambda s: (s > 0).mean() * 100),
        )
        .round(2)
    )
    print(summary.to_string(), flush=True)


if __name__ == "__main__":
    main()
