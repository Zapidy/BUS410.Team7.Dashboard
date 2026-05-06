#!/usr/bin/env python3
"""Build tract-year mission-lender proximity features.

For each (tract_fips, year) produces:
    - cdfi_within_10mi                       (count)
    - mdi_branches_within_10mi               (count, via FDIC SoD)
    - microloan_intermediary_within_25mi     (count)

Inputs:
    data/raw/tiger/tract_centroids_2020.csv         (built by build_branch_geo.py)
    data/processed/mission_proximity/cdfi_geocoded.csv    (from etl/geocode/run_geocode.py)
    data/processed/mission_proximity/microlender_geocoded.csv
    data/raw/mdi/mdi_list.csv                       (RSSD list — etl/mdi/pull_mdi_list.py)
    ../round5/data/raw/fdic/sod/sod_{year}.csv      (SoD branch lat/lng for MDI join)

Output:
    data/processed/features/tract_year_mission_proximity.csv

Notes:
    - CDFI / microlender lists are typically a single snapshot; the same set of
      institutions is broadcast across all panel years (with caveats — see
      notes/02_geocoding_log.md).
    - MDI is year-aware via SoD: a bank that became MDI partway through the
      panel will have its branches counted only in years where it appears in
      both the MDI list AND that year's SoD.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

ROOT = Path(__file__).resolve().parents[1]
TIGER = ROOT / "data" / "raw" / "tiger" / "tract_centroids_2020.csv"
CDFI = ROOT / "data" / "processed" / "mission_proximity" / "cdfi_geocoded.csv"
MICRO = ROOT / "data" / "processed" / "mission_proximity" / "microlender_geocoded.csv"
MDI = ROOT / "data" / "raw" / "mdi" / "mdi_list.csv"
SOD = ROOT.parent / "round5" / "data" / "raw" / "fdic" / "sod"
OUT_DIR = ROOT / "data" / "processed" / "features"

EARTH_R_MI = 3958.7613
RAD_10MI = 10.0 / EARTH_R_MI
RAD_25MI = 25.0 / EARTH_R_MI

PANEL_YEARS = list(range(2009, 2025))


def to_radians(df: pd.DataFrame, lat="lat", lon="lon") -> np.ndarray:
    return np.radians(df[[lat, lon]].to_numpy(dtype=float))


def count_within(tract_rad: np.ndarray, point_rad: np.ndarray, radius: float) -> np.ndarray:
    if len(point_rad) == 0:
        return np.zeros(len(tract_rad), dtype=int)
    tree = BallTree(point_rad, metric="haversine")
    return tree.query_radius(tract_rad, r=radius, count_only=True).astype(int)


def main():
    if not TIGER.exists():
        raise SystemExit(f"Missing: {TIGER}\nRun features/build_branch_geo.py first to pull tract centroids.")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    tracts = pd.read_csv(TIGER, dtype={"tract_fips": str})
    tract_rad = to_radians(tracts)
    print(f"Tracts: {len(tracts):,}", flush=True)

    # --- CDFI proximity (snapshot, broadcast to all years) ---
    cdfi_pts_rad = np.zeros((0, 2))
    if CDFI.exists():
        cdfi = pd.read_csv(CDFI)
        cdfi = cdfi[cdfi["geocode_status"] == "ok"].copy()
        if not cdfi.empty:
            cdfi_pts_rad = to_radians(cdfi)
            print(f"CDFIs geocoded: {len(cdfi):,}", flush=True)
    else:
        print(f"  WARN: {CDFI} missing — cdfi_within_10mi will be NaN", flush=True)

    # --- Microlender proximity (snapshot) ---
    micro_pts_rad = np.zeros((0, 2))
    if MICRO.exists():
        micro = pd.read_csv(MICRO)
        micro = micro[micro["geocode_status"] == "ok"].copy()
        if not micro.empty:
            micro_pts_rad = to_radians(micro)
            print(f"Microlenders geocoded: {len(micro):,}", flush=True)
    else:
        print(f"  WARN: {MICRO} missing — microloan_intermediary_within_25mi will be NaN", flush=True)

    # --- MDI proximity (year-aware via SoD) ---
    mdi_rssd = set()
    if MDI.exists():
        mdi_df = pd.read_csv(MDI, dtype={"RSSDID": str})
        mdi_rssd = set(mdi_df["RSSDID"].astype(str))
        print(f"MDI RSSDs: {len(mdi_rssd):,}", flush=True)
    else:
        print(f"  WARN: {MDI} missing — mdi_branches_within_10mi will be NaN", flush=True)

    # Snapshot counts (CDFI + microlender — broadcast)
    snapshot_cdfi = count_within(tract_rad, cdfi_pts_rad, RAD_10MI) if len(cdfi_pts_rad) else np.full(len(tracts), np.nan)
    snapshot_micro = count_within(tract_rad, micro_pts_rad, RAD_25MI) if len(micro_pts_rad) else np.full(len(tracts), np.nan)

    parts = []
    for year in PANEL_YEARS:
        # MDI branches for this year
        sod_path = SOD / f"sod_{year}.csv"
        if sod_path.exists() and mdi_rssd:
            sod = pd.read_csv(
                sod_path, usecols=["RSSDID", "SIMS_LATITUDE", "SIMS_LONGITUDE"],
                dtype={"RSSDID": str},
            ).rename(columns={"SIMS_LATITUDE": "lat", "SIMS_LONGITUDE": "lon"})
            sod = sod.dropna(subset=["lat", "lon"])
            mdi_branches = sod[sod["RSSDID"].isin(mdi_rssd)]
            mdi_pts_rad = to_radians(mdi_branches) if not mdi_branches.empty else np.zeros((0, 2))
            mdi_count = count_within(tract_rad, mdi_pts_rad, RAD_10MI)
        else:
            mdi_count = np.full(len(tracts), np.nan)

        parts.append(pd.DataFrame({
            "tract_fips": tracts["tract_fips"].values,
            "year": year,
            "cdfi_within_10mi": snapshot_cdfi,
            "mdi_branches_within_10mi": mdi_count,
            "microloan_intermediary_within_25mi": snapshot_micro,
        }))
        print(f"  {year} done", flush=True)

    out = pd.concat(parts, ignore_index=True)
    out.to_csv(OUT_DIR / "tract_year_mission_proximity.csv", index=False)
    print(f"\n→ {OUT_DIR / 'tract_year_mission_proximity.csv'}  ({len(out):,} rows)", flush=True)


if __name__ == "__main__":
    main()
