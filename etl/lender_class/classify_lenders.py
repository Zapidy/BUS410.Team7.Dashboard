#!/usr/bin/env python3
"""Build per-(lender_id, year) classification flags for community-bank, top-4,
credit-union, MDI, CDFI status.

Inputs:
    data/processed/lender_class/cra_to_rssd.csv      (RSSD↔CRA crosswalk)
    data/raw/fdic_call/assets_by_year.csv            (RSSD × year × total_assets_k)
    data/raw/mdi/mdi_list.csv                        (RSSD list — see etl/mdi/)
    data/raw/cdfi/cdfi_list.csv                      (CDFI Fund certified list — see etl/cdfi/)
    ../round5/data/processed/cra/county_year.csv     (used to identify top-4 by year)
    ../round5/data/processed/cra/reporters.csv       (CRA agency_code mapping)

Output:
    data/processed/lender_class/lender_class.csv
        columns: lender_id, year, is_community_bank, is_top4, is_credit_union,
                 is_mdi, is_cdfi, asset_band, asset_threshold_used

Community-bank rule:
    total_assets < $10B (year-varying — keeps 2009 vs 2024 comparable)
    NaN if RSSD assets unavailable for that year.

Top-4 rule:
    Top 4 lenders by national CRA small-business loan dollar volume in that year.
    Year-varying. Computed from CRA D1 county-lender totals.

Credit-union rule:
    CRA agency_code = 4.

MDI / CDFI:
    Boolean flag based on presence in the respective rosters at year of interest.
    For CDFI: snapshot-back-extension to 2009-2011 if no historical roster (see
    notes/02_geocoding_log.md).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
LC_DIR = ROOT / "data" / "processed" / "lender_class"
ASSETS = ROOT / "data" / "raw" / "fdic_call" / "assets_by_year.csv"
MDI = ROOT / "data" / "raw" / "mdi" / "mdi_list.csv"
CDFI = ROOT / "data" / "raw" / "cdfi" / "cdfi_list.csv"
ROUND5 = ROOT.parent / "round5" / "data" / "processed" / "cra"

ASSET_THRESHOLD_K = 10_000_000  # $10B in $K (Call Report ASSET is in $K)


def load_optional_csv(path: Path, **read_csv_kwargs) -> pd.DataFrame:
    if path.exists():
        return pd.read_csv(path, **read_csv_kwargs)
    print(f"  WARN: {path} missing — feature will be NaN", flush=True)
    return pd.DataFrame()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold-k", type=int, default=ASSET_THRESHOLD_K,
                    help="Community-bank threshold in $K (default $10B = 10000000)")
    args = ap.parse_args()

    LC_DIR.mkdir(parents=True, exist_ok=True)

    cw_path = LC_DIR / "cra_to_rssd.csv"
    if not cw_path.exists():
        raise SystemExit(f"Missing: {cw_path}\nRun build_rssd_cra_crosswalk.py first.")

    crosswalk = pd.read_csv(
        cw_path,
        dtype={"lender_id": str, "RSSDID": str, "CERT": str, "year": int},
    )
    assets = load_optional_csv(ASSETS, dtype={"RSSDID": str, "CERT": str})
    mdi = load_optional_csv(MDI, dtype={"RSSDID": str})
    cdfi = load_optional_csv(CDFI, dtype={"RSSDID": str})

    reporters = pd.read_csv(ROUND5 / "reporters.csv", dtype=str).fillna("")
    is_cu = reporters[reporters["agency_code"] == "4"]["lender_id"].unique().tolist()

    # Build (lender_id, year) ground truth grid from reporters
    print("Building (lender_id, year) grid from CRA reporters…", flush=True)
    grid = reporters[["lender_id", "activity_year", "agency_code"]].copy()
    grid = grid.rename(columns={"activity_year": "year"})
    grid["year"] = pd.to_numeric(grid["year"], errors="coerce").astype("Int64")
    grid = grid.dropna(subset=["year"]).copy()
    grid["year"] = grid["year"].astype(int)

    # Join in CERT/RSSDID via crosswalk (year-aware: pick highest-confidence per lender_id)
    cw_best = (crosswalk.sort_values("confidence", ascending=False)
               .drop_duplicates(subset=["lender_id"]))[["lender_id", "RSSDID", "CERT"]]
    cw_best["CERT"] = cw_best["CERT"].astype(str)
    grid = grid.merge(cw_best, on="lender_id", how="left")

    # Community bank flag — assets keyed on CERT (FDIC financials endpoint
    # doesn't expose FED_RSSD, only CERT)
    if not assets.empty:
        assets["CERT"] = assets["CERT"].astype(str)
        assets["year"] = pd.to_numeric(assets["year"], errors="coerce").astype("Int64")
        grid = grid.merge(
            assets[["CERT", "year", "total_assets_k"]],
            on=["CERT", "year"], how="left",
        )
        grid["total_assets_k"] = pd.to_numeric(grid["total_assets_k"], errors="coerce")
        grid["is_community_bank"] = (grid["total_assets_k"] < args.threshold_k).astype("Int64")
        # If no assets row, NaN
        grid.loc[grid["total_assets_k"].isna(), "is_community_bank"] = pd.NA
    else:
        grid["total_assets_k"] = pd.NA
        grid["is_community_bank"] = pd.NA

    # Credit-union flag
    grid["is_credit_union"] = grid["lender_id"].isin(is_cu).astype(int)

    # MDI flag
    if not mdi.empty and "RSSDID" in mdi.columns:
        mdi_set = set(mdi["RSSDID"].astype(str))
        grid["is_mdi"] = grid["RSSDID"].isin(mdi_set).astype(int)
    else:
        grid["is_mdi"] = 0

    # CDFI flag (banks only — separate CDFI institution proximity is in build_mission_proximity.py)
    if not cdfi.empty and "RSSDID" in cdfi.columns:
        cdfi_set = set(cdfi["RSSDID"].astype(str).dropna())
        grid["is_cdfi"] = grid["RSSDID"].isin(cdfi_set).astype(int)
    else:
        grid["is_cdfi"] = 0

    # Top-4 flag — pull from CRA county_year by aggregating to national-lender-year
    print("Computing top-4 by year (national CRA small-business loan dollar volume)…", flush=True)
    # county_year doesn't have lender_id; we need tract_lender_year for accurate top-4
    tly_path = ROOT / "data" / "processed" / "cra" / "tract_lender_year.csv"
    if tly_path.exists():
        print(f"  Using {tly_path}", flush=True)
        tly = pd.read_csv(tly_path, usecols=["lender_id", "year", "amount_k"])
        national = tly.groupby(["year", "lender_id"], as_index=False)["amount_k"].sum()
        national = national.sort_values(["year", "amount_k"], ascending=[True, False])
        top4 = national.groupby("year").head(4)[["year", "lender_id"]]
        top4["is_top4"] = 1
        grid = grid.merge(top4, on=["year", "lender_id"], how="left")
        grid["is_top4"] = grid["is_top4"].fillna(0).astype(int)
    else:
        print(f"  WARN: {tly_path} missing — is_top4 will be 0", flush=True)
        grid["is_top4"] = 0

    out = grid[[
        "lender_id", "year", "RSSDID", "CERT",
        "is_community_bank", "is_top4", "is_credit_union", "is_mdi", "is_cdfi",
        "total_assets_k",
    ]].copy()
    out["asset_threshold_used_k"] = args.threshold_k

    path = LC_DIR / "lender_class.csv"
    out.to_csv(path, index=False)
    print(f"\n→ {path}  ({len(out):,} rows)", flush=True)

    print("\nFlag coverage:", flush=True)
    for col in ("is_community_bank", "is_top4", "is_credit_union", "is_mdi", "is_cdfi"):
        non_null = out[col].notna().sum()
        flagged = (out[col] == 1).sum()
        print(f"  {col:<20s} non-null={non_null:>7,}  flagged={flagged:>5,}", flush=True)


if __name__ == "__main__":
    main()
