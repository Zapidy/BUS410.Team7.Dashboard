#!/usr/bin/env python3
"""Build tract-year concentration + small-loan supply features (vectorized).

Reads tract×lender×year apportioned loans (from etl/cra/parse_cra_round7.py)
and produces, per (tract_fips, year):

    - top1_lender_share_tract       (max lender's share of tract loan count)
    - top3_lender_share_tract       (top-3 cumulative share)
    - lender_hhi_tract              (Herfindahl on tract loan-count shares)
    - pct_loans_under_100k          (count_lt_100 / n_loans)
    - pct_loans_under_250k          ((count_lt_100 + count_100_250) / n_loans)
    - n_active_lenders_tract        (count of distinct lenders, used for NaN-gate
                                     and excluded from the model itself)

LEAKAGE MITIGATION (see notes/00_design_brief.md):
    The Round 5 target is built from `n_cra_lenders`. When lender count is
    small, top1/top3/HHI mechanically saturate. To break this:
    - All concentration features are NaN when n_active_lenders_tract < 3.
    - Trailing 5-to-2-year mean variants (suffix `_lag2to5_mean`) are
      computed for each feature to break the T → T+1 mechanical link.

Implementation notes:
    Vectorized pandas (no per-group Python apply). At 20M tract-lender-year
    rows the groupby-apply approach takes >5 min; this version finishes in <30s.

Inputs:
    data/processed/cra/tract_lender_year.csv

Output:
    data/processed/features/tract_year_concentration.csv
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
IN_PATH = ROOT / "data" / "processed" / "cra" / "tract_lender_year.csv"
OUT_DIR = ROOT / "data" / "processed" / "features"

NAN_GATE_MIN_LENDERS = 3
TRAILING_LAGS = (2, 3, 4, 5)  # 5-to-2-year mean


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not IN_PATH.exists():
        raise SystemExit(f"Input missing: {IN_PATH}\n"
                         f"Run etl/cra/parse_cra_round7.py first.")

    print(f"Loading {IN_PATH}…", flush=True)
    df = pd.read_csv(
        IN_PATH,
        dtype={"tract_fips": str, "county_fips": str, "lender_id": str, "year": int},
        usecols=["tract_fips", "year", "lender_id", "n_loans",
                 "count_lt_100", "count_100_250"],
    )
    print(f"  rows: {len(df):,}", flush=True)

    # ---- Tract-level totals ----
    print("Aggregating tract totals…", flush=True)
    tract_total = (
        df.groupby(["tract_fips", "year"], sort=False)
        .agg(
            total_loans=("n_loans", "sum"),
            n_under_100=("count_lt_100", "sum"),
            n_100_250=("count_100_250", "sum"),
            n_active_lenders_tract=("lender_id", "nunique"),
        )
        .reset_index()
    )
    print(f"  tract-years: {len(tract_total):,}", flush=True)

    # ---- Compute per-row share for HHI + ranking ----
    print("Computing per-lender shares…", flush=True)
    df = df.merge(
        tract_total[["tract_fips", "year", "total_loans"]],
        on=["tract_fips", "year"], how="left",
    )
    df["share"] = np.where(df["total_loans"] > 0, df["n_loans"] / df["total_loans"], 0.0)
    df["share_sq"] = df["share"] ** 2

    # HHI = sum of share^2 per tract-year
    print("Computing HHI…", flush=True)
    hhi = df.groupby(["tract_fips", "year"], sort=False)["share_sq"].sum().rename("lender_hhi_tract").reset_index()

    # Top-1 share = max share per tract-year
    # Top-3 share = sum of top-3 shares per tract-year
    print("Computing top-1, top-3 shares…", flush=True)
    df_sorted = df.sort_values(["tract_fips", "year", "share"], ascending=[True, True, False])
    df_sorted["rank"] = df_sorted.groupby(["tract_fips", "year"], sort=False).cumcount() + 1

    top1 = (
        df_sorted[df_sorted["rank"] == 1]
        [["tract_fips", "year", "share"]]
        .rename(columns={"share": "top1_lender_share_tract"})
    )
    top3 = (
        df_sorted[df_sorted["rank"] <= 3]
        .groupby(["tract_fips", "year"], sort=False)["share"]
        .sum()
        .rename("top3_lender_share_tract")
        .reset_index()
    )

    # Merge all
    feat = tract_total.merge(hhi, on=["tract_fips", "year"], how="left")
    feat = feat.merge(top1, on=["tract_fips", "year"], how="left")
    feat = feat.merge(top3, on=["tract_fips", "year"], how="left")

    # NaN-gate: when fewer than 3 lenders, concentration features are unmeasurable
    print(f"Applying NaN-gate (n < {NAN_GATE_MIN_LENDERS})…", flush=True)
    gate = feat["n_active_lenders_tract"] < NAN_GATE_MIN_LENDERS
    feat.loc[gate, "top1_lender_share_tract"] = np.nan
    feat.loc[gate, "top3_lender_share_tract"] = np.nan
    feat.loc[gate, "lender_hhi_tract"] = np.nan

    # Loan-size shares (no NaN-gate — these are mostly safe)
    feat["pct_loans_under_100k"] = np.where(
        feat["total_loans"] > 0,
        feat["n_under_100"] / feat["total_loans"],
        np.nan,
    )
    feat["pct_loans_under_250k"] = np.where(
        feat["total_loans"] > 0,
        (feat["n_under_100"] + feat["n_100_250"]) / feat["total_loans"],
        np.nan,
    )

    # Drop intermediates
    feat = feat.drop(columns=["total_loans", "n_under_100", "n_100_250"])

    # Trailing 5-to-2-year means
    print("Computing trailing 5-to-2-year means…", flush=True)
    feat = feat.sort_values(["tract_fips", "year"]).reset_index(drop=True)
    feature_cols = [
        "top1_lender_share_tract",
        "top3_lender_share_tract",
        "lender_hhi_tract",
        "pct_loans_under_100k",
        "pct_loans_under_250k",
    ]
    for col in feature_cols:
        lagged = []
        for lag in TRAILING_LAGS:
            lagged.append(feat.groupby("tract_fips", sort=False)[col].shift(lag))
        feat[f"{col}_lag2to5_mean"] = pd.concat(lagged, axis=1).mean(axis=1, skipna=True)

    out = OUT_DIR / "tract_year_concentration.csv"
    feat.to_csv(out, index=False)
    print(f"\n→ {out} ({len(feat):,} rows)", flush=True)
    print("Non-null coverage:", flush=True)
    for c in feat.columns:
        if c not in {"tract_fips", "year"}:
            non_null = feat[c].notna().sum()
            print(f"  {c:<40s} {non_null:>9,}", flush=True)


if __name__ == "__main__":
    main()
