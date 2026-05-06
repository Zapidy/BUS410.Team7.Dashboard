#!/usr/bin/env python3
"""Build tract-year FDIC branch geography features.

For each (tract_fips, year) produces:
    - distance_to_nearest_bank_branch  (miles, haversine)
    - branches_within_5mi              (count)
    - branch_closures_3y_within_10mi   (count of UNINUMBRs disappearing
                                        within 10mi over the prior 3 years)

Inputs:
    ../round5/data/raw/fdic/sod/sod_{year}.csv     (raw SoD branch-level)
    data/raw/tiger/tract_centroids_2020.csv        (tract_fips, lat, lon)
        Pulled from Census 2020 Gazetteer (2020_Gaz_tracts_national.zip)
        if absent. Columns expected: GEOID (11-digit tract_fips), INTPTLAT, INTPTLONG.

Output:
    data/processed/branch_geo/tract_year_branch_geo.csv

Runtime:
    ~10 min for 85K tracts × ~85K branches × 16 years using sklearn
    BallTree (haversine).

Usage:
    python3 build_branch_geo.py                  # all years 2009-2024
    python3 build_branch_geo.py --years 2020 2021
"""
from __future__ import annotations

import argparse
import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sklearn.neighbors import BallTree

ROOT = Path(__file__).resolve().parents[1]
ROUND5_SOD = ROOT.parent / "round5" / "data" / "raw" / "fdic" / "sod"
TIGER_DIR = ROOT / "data" / "raw" / "tiger"
OUT_DIR = ROOT / "data" / "processed" / "branch_geo"

EARTH_R_MI = 3958.7613  # miles
RADIUS_5MI = 5.0 / EARTH_R_MI  # radians
RADIUS_10MI = 10.0 / EARTH_R_MI

GAZETTEER_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
    "2020_Gazetteer/2020_Gaz_tracts_national.zip"
)


def ensure_tract_centroids() -> pd.DataFrame:
    """Load tract centroids; pull from Census Gazetteer if missing."""
    TIGER_DIR.mkdir(parents=True, exist_ok=True)
    out = TIGER_DIR / "tract_centroids_2020.csv"
    if out.exists():
        return pd.read_csv(out, dtype={"tract_fips": str})

    print(f"Pulling tract centroids from Census Gazetteer…", file=sys.stderr)
    r = requests.get(GAZETTEER_URL, timeout=120)
    r.raise_for_status()
    zip_bytes = r.content
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        names = [n for n in z.namelist() if n.endswith(".txt")]
        if not names:
            raise SystemExit("No .txt member found in gazetteer zip")
        with z.open(names[0]) as f:
            df = pd.read_csv(f, sep="\t", dtype={"GEOID": str})

    df.columns = [c.strip() for c in df.columns]
    out_df = (
        df[["GEOID", "INTPTLAT", "INTPTLONG"]]
        .rename(columns={"GEOID": "tract_fips", "INTPTLAT": "lat", "INTPTLONG": "lon"})
        .dropna()
    )
    out_df["tract_fips"] = out_df["tract_fips"].astype(str).str.zfill(11)
    out_df.to_csv(out, index=False)
    print(f"  → {out} ({len(out_df):,} tracts)", file=sys.stderr)
    return out_df


def load_sod_year(year: int) -> pd.DataFrame:
    path = ROUND5_SOD / f"sod_{year}.csv"
    if not path.exists():
        return pd.DataFrame(columns=["UNINUMBR", "CERT", "RSSDID", "lat", "lon"])
    df = pd.read_csv(
        path,
        usecols=["UNINUMBR", "CERT", "RSSDID", "SIMS_LATITUDE", "SIMS_LONGITUDE"],
        dtype={"UNINUMBR": str, "CERT": str, "RSSDID": str},
    )
    df = df.rename(columns={"SIMS_LATITUDE": "lat", "SIMS_LONGITUDE": "lon"})
    df = df.dropna(subset=["lat", "lon"])
    df = df[(df["lat"].between(17, 72)) & (df["lon"].between(-180, -65))]
    return df.reset_index(drop=True)


def to_radians(df: pd.DataFrame, lat="lat", lon="lon") -> np.ndarray:
    return np.radians(df[[lat, lon]].to_numpy(dtype=float))


def build_year(year: int, tracts: pd.DataFrame, sod_history: dict[int, pd.DataFrame]) -> pd.DataFrame:
    """For one year, compute distance, branches_within_5mi, closures-in-prior-3y."""
    cur = sod_history.get(year, pd.DataFrame())
    if cur.empty:
        return pd.DataFrame(
            {
                "tract_fips": tracts["tract_fips"],
                "year": year,
                "distance_to_nearest_bank_branch": np.nan,
                "branches_within_5mi": np.nan,
                "branch_closures_3y_within_10mi": np.nan,
            }
        )

    tract_rad = to_radians(tracts)
    branch_rad = to_radians(cur)

    tree = BallTree(branch_rad, metric="haversine")

    # 1) distance to nearest
    dist_rad, _ = tree.query(tract_rad, k=1)
    distance_mi = (dist_rad[:, 0] * EARTH_R_MI)

    # 2) branches within 5mi
    n5 = tree.query_radius(tract_rad, r=RADIUS_5MI, count_only=True)

    # 3) closures within 10mi over prior 3 years
    # A "closure" = a UNINUMBR present in any of years (Y-3, Y-2, Y-1) but not in year Y.
    closures_count = np.zeros(len(tracts), dtype=int)
    if year > min(sod_history):
        cur_uni = set(cur["UNINUMBR"])
        prior_branches = []
        for prior_year in (year - 1, year - 2, year - 3):
            prior = sod_history.get(prior_year)
            if prior is None or prior.empty:
                continue
            gone = prior[~prior["UNINUMBR"].isin(cur_uni)]
            if not gone.empty:
                prior_branches.append(gone)
        if prior_branches:
            closed = pd.concat(prior_branches, ignore_index=True).drop_duplicates(
                subset=["UNINUMBR"]
            )
            if not closed.empty:
                closed_rad = to_radians(closed)
                tree_closed = BallTree(closed_rad, metric="haversine")
                closures_count = tree_closed.query_radius(
                    tract_rad, r=RADIUS_10MI, count_only=True
                )

    return pd.DataFrame(
        {
            "tract_fips": tracts["tract_fips"].values,
            "year": year,
            "distance_to_nearest_bank_branch": distance_mi,
            "branches_within_5mi": n5.astype(int),
            "branch_closures_3y_within_10mi": closures_count.astype(int),
        }
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs="*", type=int, default=None)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tracts = ensure_tract_centroids()
    print(f"Loaded {len(tracts):,} tract centroids", flush=True)

    available = sorted(int(p.stem.replace("sod_", "")) for p in ROUND5_SOD.glob("sod_*.csv"))
    if not available:
        raise SystemExit(f"No SoD files under {ROUND5_SOD}")
    years = args.years or available

    # Preload all SoD years (needed for closure detection over 3-year lookback)
    sod_history: dict[int, pd.DataFrame] = {}
    for y in available:
        sod_history[y] = load_sod_year(y)
        print(f"  SoD {y}: {len(sod_history[y]):,} branches", flush=True)

    parts: list[pd.DataFrame] = []
    for y in years:
        if y not in available:
            print(f"  Skipping {y}: no SoD file", flush=True)
            continue
        print(f"Processing {y}…", flush=True)
        parts.append(build_year(y, tracts, sod_history))

    out = pd.concat(parts, ignore_index=True)
    out.to_csv(OUT_DIR / "tract_year_branch_geo.csv", index=False)
    print(f"\n→ {OUT_DIR / 'tract_year_branch_geo.csv'} ({len(out):,} rows)", flush=True)


if __name__ == "__main__":
    main()
