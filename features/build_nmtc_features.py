#!/usr/bin/env python3
"""Build NMTC (New Markets Tax Credit) tract-year investment features.

The CDFI Fund publishes NMTC project-level data: per-investment QLICI dollars
deployed in 2020 census tracts. We use this as a stronger signal than
"CDFI office within 10mi" because it captures actual mission-lender capital
deployed at the tract you care about — and it maps cleanly to a policy lever
("expand NMTC allocation").

Caveat: NMTC has selection bias — projects went to tracts already struggling.
We mitigate by computing rolling LAGGED windows (excluding year T-0 and T-1)
to break the immediate feedback loop. Trailing windows match the 5-to-2-year
convention used elsewhere in round 7.

Inputs:
    data/raw/cdfi/files.xlsx
        sheet 'Financial Notes 1 - Data Set PU'
        cols: 2020 Census Tract, QLICI Amount, Origination Year, ...

Output:
    data/processed/features/tract_year_nmtc.csv
        per (tract_fips, year), for years 2009-2024:
            - nmtc_dollars_5yr_lag2to6        (rolling sum, $K, 5y window
                                                ending at T-2)
            - nmtc_dollars_3yr_lag2to4        (rolling sum, $K, shorter window)
            - nmtc_projects_5yr_lag2to6       (project count, same window)
            - nmtc_received_5yr_lag2to6       (binary, ever received NMTC)
            - nmtc_dollars_county_5yr_lag2to6 (county-level rollup, smooths
                                                sparse-tract gaps)

Notes:
    - Multi-tract projects are flagged in the source file but the financial-notes
      sheet allocates the dollar amount to a single tract. We trust that
      allocation.
    - Tracts not appearing in NMTC data get all-zero values (not NaN).
    - 2023+ years have no NMTC data yet (file ends at 2022); we assume 0 for
      those and document the censoring.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "raw" / "cdfi" / "files.xlsx"
OUT_DIR = ROOT / "data" / "processed" / "features"

PANEL_YEARS = list(range(2009, 2025))
LAG_LONG = (2, 3, 4, 5, 6)  # 5-year window ending at T-2
LAG_SHORT = (2, 3, 4)        # 3-year window ending at T-2


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not SRC.exists():
        raise SystemExit(f"Missing: {SRC}")

    print(f"Loading {SRC.name}…", flush=True)
    df = pd.read_excel(
        SRC,
        sheet_name="Financial Notes 1 - Data Set PU",
        dtype=str,
    )
    print(f"  rows: {len(df):,}", flush=True)

    df["tract_fips"] = df["2020 Census Tract"].astype(str).str.zfill(11)
    df["year_origination"] = pd.to_numeric(df["Origination Year"], errors="coerce").astype("Int64")
    df["dollars_k"] = pd.to_numeric(df["QLICI Amount"], errors="coerce") / 1000.0  # convert to $K

    # Drop rows without a usable tract or year
    df = df.dropna(subset=["tract_fips", "year_origination", "dollars_k"]).copy()
    df = df[df["tract_fips"].str.match(r"^\d{11}$")]
    print(f"  usable rows: {len(df):,}", flush=True)
    print(f"  unique tracts: {df['tract_fips'].nunique():,}", flush=True)
    print(f"  origination years: {df['year_origination'].min()}–{df['year_origination'].max()}", flush=True)

    df["county_fips"] = df["tract_fips"].str[:5]
    df["year"] = df["year_origination"].astype(int)

    # Tract-year totals (raw, not yet windowed)
    tract_year_raw = (
        df.groupby(["tract_fips", "year"], as_index=False)
        .agg(dollars_k=("dollars_k", "sum"), projects=("year_origination", "count"))
    )
    tract_year_raw["county_fips"] = tract_year_raw["tract_fips"].str[:5]

    county_year_raw = (
        df.groupby(["county_fips", "year"], as_index=False)
        .agg(dollars_k=("dollars_k", "sum"), projects=("year_origination", "count"))
    )

    # Build a complete (tract, year) grid of 2009-2024 for every tract that
    # ever received NMTC. (Tracts that never received NMTC get all-zero values
    # at the panel-merge step, no need to enumerate them here — saves memory.)
    all_tracts = sorted(df["tract_fips"].unique())
    grid = pd.DataFrame(
        [(t, y) for t in all_tracts for y in PANEL_YEARS],
        columns=["tract_fips", "year"],
    )
    grid["county_fips"] = grid["tract_fips"].str[:5]

    grid = grid.merge(tract_year_raw[["tract_fips", "year", "dollars_k", "projects"]],
                      on=["tract_fips", "year"], how="left")
    grid["dollars_k"] = grid["dollars_k"].fillna(0.0)
    grid["projects"] = grid["projects"].fillna(0).astype(int)
    grid = grid.sort_values(["tract_fips", "year"]).reset_index(drop=True)

    # Rolling lagged windows
    print("Computing rolling lagged windows…", flush=True)

    def lagged_sum(s: pd.Series, lags: tuple[int, ...]) -> pd.Series:
        return pd.concat([s.shift(lag) for lag in lags], axis=1).sum(axis=1, min_count=1)

    # Long window — 5-year sum ending T-2
    grid["nmtc_dollars_5yr_lag2to6"] = (
        grid.groupby("tract_fips")["dollars_k"]
        .apply(lambda s: lagged_sum(s, LAG_LONG))
        .reset_index(level=0, drop=True)
    )
    grid["nmtc_projects_5yr_lag2to6"] = (
        grid.groupby("tract_fips")["projects"]
        .apply(lambda s: lagged_sum(s, LAG_LONG))
        .reset_index(level=0, drop=True)
    )
    # Short window — 3-year sum ending T-2
    grid["nmtc_dollars_3yr_lag2to4"] = (
        grid.groupby("tract_fips")["dollars_k"]
        .apply(lambda s: lagged_sum(s, LAG_SHORT))
        .reset_index(level=0, drop=True)
    )
    grid["nmtc_received_5yr_lag2to6"] = (grid["nmtc_dollars_5yr_lag2to6"] > 0).astype(int)

    # County-level rollup of dollars_k (smooths sparse tract coverage)
    print("Computing county-level rollups…", flush=True)
    cy = (
        df.groupby(["county_fips", "year"], as_index=False)
        .agg(dollars_k=("dollars_k", "sum"))
    )
    # Build full (county, year) grid for years 2009-2024
    all_counties = sorted(df["county_fips"].unique())
    cy_grid = pd.DataFrame(
        [(c, y) for c in all_counties for y in PANEL_YEARS],
        columns=["county_fips", "year"],
    )
    cy_grid = cy_grid.merge(cy, on=["county_fips", "year"], how="left")
    cy_grid["dollars_k"] = cy_grid["dollars_k"].fillna(0.0)
    cy_grid = cy_grid.sort_values(["county_fips", "year"]).reset_index(drop=True)
    cy_grid["nmtc_dollars_county_5yr_lag2to6"] = (
        cy_grid.groupby("county_fips")["dollars_k"]
        .apply(lambda s: lagged_sum(s, LAG_LONG))
        .reset_index(level=0, drop=True)
    )

    # Join county rollup back to grid
    grid = grid.merge(
        cy_grid[["county_fips", "year", "nmtc_dollars_county_5yr_lag2to6"]],
        on=["county_fips", "year"], how="left",
    )

    feat_cols = [
        "nmtc_dollars_5yr_lag2to6",
        "nmtc_dollars_3yr_lag2to4",
        "nmtc_projects_5yr_lag2to6",
        "nmtc_received_5yr_lag2to6",
        "nmtc_dollars_county_5yr_lag2to6",
    ]
    out = grid[["tract_fips", "year"] + feat_cols].copy()

    # Limit to panel years (2009-2024 only)
    out = out[out["year"].between(2009, 2024)]
    out_path = OUT_DIR / "tract_year_nmtc.csv"
    out.to_csv(out_path, index=False)
    print(f"\n→ {out_path} ({len(out):,} rows)", flush=True)

    print("Coverage on tracts that ever received NMTC:")
    for c in feat_cols:
        non_zero = (out[c] > 0).sum()
        mean_val = out[out[c] > 0][c].mean() if non_zero > 0 else 0
        print(f"  {c:<40s} non-zero: {non_zero:>9,}  mean (when >0): {mean_val:.1f}")


if __name__ == "__main__":
    main()
