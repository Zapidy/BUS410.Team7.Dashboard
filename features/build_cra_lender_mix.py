#!/usr/bin/env python3
"""Build tract-year CRA lender-mix features.

For each (tract_fips, year):
    - pct_loans_from_community_banks
    - pct_loans_from_top4_banks
    - pct_loans_from_credit_unions

Inputs:
    data/processed/cra/tract_lender_year.csv         (apportioned loan counts)
    data/processed/lender_class/lender_class.csv     (per-lender classification flags)

Output:
    data/processed/features/tract_year_lender_mix.csv

LEAKAGE MITIGATION:
    Same NaN gate as build_concentration.py — features are NaN when
    n_active_lenders_tract < 3.
    Trailing 5-to-2-year mean variants computed for each share feature.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TLY = ROOT / "data" / "processed" / "cra" / "tract_lender_year.csv"
LC = ROOT / "data" / "processed" / "lender_class" / "lender_class.csv"
OUT_DIR = ROOT / "data" / "processed" / "features"

NAN_GATE_MIN_LENDERS = 3
TRAILING_LAGS = (2, 3, 4, 5)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not TLY.exists():
        raise SystemExit(f"Missing: {TLY}\nRun etl/cra/parse_cra_round7.py first.")
    if not LC.exists():
        raise SystemExit(f"Missing: {LC}\nRun etl/lender_class/classify_lenders.py first.")

    print(f"Loading tract×lender×year…", flush=True)
    tly = pd.read_csv(
        TLY,
        dtype={"tract_fips": str, "county_fips": str, "lender_id": str, "year": int},
    )
    print(f"  rows: {len(tly):,}", flush=True)

    print(f"Loading lender_class…", flush=True)
    lc = pd.read_csv(
        LC, dtype={"lender_id": str, "year": int},
    )

    # Join class flags onto tract-lender-year rows
    flags = ["is_community_bank", "is_top4", "is_credit_union"]
    merged = tly.merge(
        lc[["lender_id", "year"] + flags],
        on=["lender_id", "year"],
        how="left",
    )

    for f in flags:
        if merged[f].dtype == object:
            merged[f] = pd.to_numeric(merged[f], errors="coerce")

    # Compute weighted shares per tract-year
    print("Aggregating to tract-year…", flush=True)
    agg = (
        merged.groupby(["tract_fips", "year"], sort=False)
        .agg(
            total_loans=("n_loans", "sum"),
            community_loans=("n_loans", lambda s: (s * merged.loc[s.index, "is_community_bank"]).sum(skipna=True)),
            top4_loans=("n_loans", lambda s: (s * merged.loc[s.index, "is_top4"]).sum(skipna=True)),
            cu_loans=("n_loans", lambda s: (s * merged.loc[s.index, "is_credit_union"]).sum(skipna=True)),
            n_active_lenders=("lender_id", "nunique"),
        )
        .reset_index()
    )

    def _compute_share(numerator_col: str, sentinel_col: str) -> pd.Series:
        share = agg[numerator_col] / agg["total_loans"].replace(0, np.nan)
        # NaN-gate: if not enough lenders, NaN
        share = share.where(agg["n_active_lenders"] >= NAN_GATE_MIN_LENDERS)
        # If sentinel column has *all NaN* per (tract,year) for community-bank
        # (e.g., RSSD assets unavailable), share itself is NaN.
        return share

    agg["pct_loans_from_community_banks"] = _compute_share("community_loans", "community_loans")
    agg["pct_loans_from_top4_banks"] = _compute_share("top4_loans", "top4_loans")
    agg["pct_loans_from_credit_unions"] = _compute_share("cu_loans", "cu_loans")

    # Trailing 5-to-2 means
    feature_cols = [
        "pct_loans_from_community_banks",
        "pct_loans_from_top4_banks",
        "pct_loans_from_credit_unions",
    ]

    print("Computing trailing 5-to-2-year means…", flush=True)
    agg = agg.sort_values(["tract_fips", "year"]).reset_index(drop=True)
    for col in feature_cols:
        lagged = []
        for lag in TRAILING_LAGS:
            lagged.append(agg.groupby("tract_fips")[col].shift(lag))
        agg[f"{col}_lag2to5_mean"] = pd.concat(lagged, axis=1).mean(axis=1, skipna=True)

    out = agg.drop(columns=["community_loans", "top4_loans", "cu_loans", "total_loans"])
    out.to_csv(OUT_DIR / "tract_year_lender_mix.csv", index=False)
    print(f"\n→ {OUT_DIR / 'tract_year_lender_mix.csv'}  ({len(out):,} rows)", flush=True)

    print("\nNon-null coverage:", flush=True)
    for c in feature_cols:
        n = out[c].notna().sum()
        print(f"  {c:<40s}  {n:>9,}", flush=True)


if __name__ == "__main__":
    main()
