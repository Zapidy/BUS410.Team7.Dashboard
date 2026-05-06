#!/usr/bin/env python3
"""Define the credit-desert target variable(s) for Round 5.

Per notes/00_methodology.md §5, we model THREE flavors of "credit desert"
and predict them jointly (or separately at policy-application time):

  1. SERVICE DESERT  — tract has fewer than P-th percentile CRA lender count
                        relative to its peer group (rural vs urban).
  2. ORIGINATION DESERT — tract has fewer than P-th percentile loan-origination
                        per-capita (HMDA originations, post-2018 only).
  3. BRANCH DESERT   — nearest active FDIC branch > X miles. Requires spatial
                        join to FDIC branch lat/lng. STUB FOR NOW.

For each flavor we also emit a CONTINUOUS target (the underlying score) so
regression / survival models can use the same data without re-bucketing.

Threshold defaults:
  - Service desert percentile: 10th (bottom-decile lender count within peer)
  - Origination desert percentile: 10th
  - Branch desert miles: 5 (urban) / 15 (rural)

Peer groupings keep the threshold honest across rural/urban: a 2-lender
rural tract is normal, a 2-lender urban tract is a desert.

Inputs:  data/processed/panel/tract_year.parquet
Outputs: data/processed/panel/tract_year_with_target.parquet
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PANEL_PATH = ROOT / "data" / "processed" / "panel" / "tract_year.parquet"
OUT_PATH = ROOT / "data" / "processed" / "panel" / "tract_year_with_target.parquet"


def add_service_desert(df: pd.DataFrame, percentile: float = 0.10) -> pd.DataFrame:
    """Bottom-decile lender count, computed within (year × peer-group)."""
    df = df.copy()
    # Peer group: urban (RUCA 1-6) vs rural (RUCA 7-10), per year
    df["peer_group"] = np.where(df["is_rural"] == 1, "rural", "urban")

    # Compute year-peer percentile threshold for n_cra_lenders
    thresholds = (
        df.groupby(["year", "peer_group"])["n_cra_lenders"]
          .quantile(percentile)
          .rename("service_desert_threshold")
          .reset_index()
    )
    df = df.merge(thresholds, on=["year", "peer_group"], how="left")
    df["is_service_desert"] = (df["n_cra_lenders"] <= df["service_desert_threshold"]).astype(int)

    # Continuous score: standardized residual from peer median
    medians = (
        df.groupby(["year", "peer_group"])["n_cra_lenders"]
          .median().rename("service_peer_median").reset_index()
    )
    df = df.merge(medians, on=["year", "peer_group"], how="left")
    df["service_desert_score"] = -(df["n_cra_lenders"] - df["service_peer_median"])
    return df


def add_origination_desert(df: pd.DataFrame, percentile: float = 0.10) -> pd.DataFrame:
    """Bottom-decile origination per capita (HMDA, post-2018 only)."""
    df = df.copy()
    df["originations_per_1k"] = np.where(
        (df["population"].notna()) & (df["population"] > 0) & (df["year"] >= 2018),
        df["n_originated"] / (df["population"] / 1000.0),
        np.nan,
    )

    # Year-peer thresholds
    thresholds = (
        df[df["originations_per_1k"].notna()]
          .groupby(["year", "peer_group"])["originations_per_1k"]
          .quantile(percentile)
          .rename("origination_desert_threshold")
          .reset_index()
    )
    df = df.merge(thresholds, on=["year", "peer_group"], how="left")
    df["is_origination_desert"] = np.where(
        df["originations_per_1k"].notna(),
        (df["originations_per_1k"] <= df["origination_desert_threshold"]).astype(int),
        np.nan,
    )
    df["origination_desert_score"] = -df["originations_per_1k"]
    return df


def add_any_desert(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["is_any_desert"] = (
        (df["is_service_desert"] == 1)
        | (df["is_origination_desert"] == 1)
    ).astype(int)
    return df


def add_forward_targets(df: pd.DataFrame) -> pd.DataFrame:
    """For each (tract, year), compute target families at H1, H3, H6.

    H1: 1-year horizon (legacy / sanity-check)
    H3: 3-year horizon (PRIMARY — used to forecast 2027 from 2024 features
        once federal CRA reporting catches up)
    H6: 6-year horizon (long-horizon "2030 scenario" — for showing time-
        horizon effects of policy intervention)

    1. STATE target — `target_service_desert_hN` = is the tract a desert at year+N?
       Naively suspectible to autocorrelation leakage when desert state is sticky.

    2. TRANSITION target — `target_becomes_desert_hN` = tract is NOT a desert at
       year T, but IS a desert at year T+N. This is the actually-hard forecasting
       problem and the right primary target for Round 5.

    Per methodology brief §2.4 (target leakage): the state target is essentially
    explained by current-year lender count being the lagged version of itself.
    The transition target removes that leakage by conditioning on non-desert at T.
    """
    df = df.copy().sort_values(["tract_fips", "year"]).reset_index(drop=True)
    for h in (1, 2, 3, 4, 5, 6):
        future = df[["tract_fips", "year", "is_service_desert", "is_any_desert"]].copy()
        future["year"] = future["year"] - h  # shift backwards so it joins as "future from year"
        future = future.rename(columns={
            "is_service_desert": f"_future_service_h{h}",
            "is_any_desert":     f"_future_any_h{h}",
        })
        df = df.merge(future, on=["tract_fips", "year"], how="left")

        # State target (kept for sanity-check / lineage with Round 4)
        df[f"target_service_desert_h{h}"] = df[f"_future_service_h{h}"]
        df[f"target_any_desert_h{h}"]     = df[f"_future_any_h{h}"]

        # Transition target — the actually-hard forecasting problem
        df[f"target_becomes_service_desert_h{h}"] = np.where(
            df["is_service_desert"] == 1,
            np.nan,  # already a desert — drop from supervised set
            df[f"_future_service_h{h}"],
        )
        df[f"target_becomes_any_desert_h{h}"] = np.where(
            df["is_any_desert"] == 1,
            np.nan,
            df[f"_future_any_h{h}"],
        )
        df = df.drop(columns=[f"_future_service_h{h}", f"_future_any_h{h}"])
    return df


def main():
    if not PANEL_PATH.exists():
        raise SystemExit(f"Panel not built. Run features/build_panel.py first.")

    print(f"Loading {PANEL_PATH}…")
    df = pd.read_parquet(PANEL_PATH)
    print(f"  Loaded: {df.shape}")

    print("\nDefining service desert (bottom-decile lender count by year × rural/urban)…")
    df = add_service_desert(df, percentile=0.10)
    n_sd = df["is_service_desert"].sum()
    print(f"  Service desert flags: {n_sd:,} of {len(df):,} ({n_sd/len(df)*100:.1f}%)")

    print("\nDefining origination desert (HMDA originations per capita, 2018+ only)…")
    df = add_origination_desert(df, percentile=0.10)
    n_od = (df["is_origination_desert"] == 1).sum()
    n_avail = df["is_origination_desert"].notna().sum()
    print(f"  Origination desert flags: {n_od:,} of {n_avail:,} eligible ({n_od/max(n_avail,1)*100:.1f}%)")

    df = add_any_desert(df)
    n_any = df["is_any_desert"].sum()
    print(f"  ANY desert flags: {n_any:,} of {len(df):,} ({n_any/len(df)*100:.1f}%)")

    print("\nAdding forward targets (H1, H2, H3 — both state + transition variants)…")
    df = add_forward_targets(df)
    print("\n  STATE targets (sticky — autocorrelation will inflate AUC):")
    for h in (1, 2, 3):
        col = f"target_service_desert_h{h}"
        n_pos = (df[col] == 1).sum()
        n_lab = df[col].notna().sum()
        print(f"    {col}: {n_pos:,} pos / {n_lab:,} lab  ({n_pos/max(n_lab,1)*100:.1f}%)")
    print("\n  TRANSITION targets (genuine forecasting problem — primary):")
    for h in (1, 2, 3):
        col = f"target_becomes_service_desert_h{h}"
        n_pos = (df[col] == 1).sum()
        n_lab = df[col].notna().sum()
        print(f"    {col}: {n_pos:,} pos / {n_lab:,} lab  ({n_pos/max(n_lab,1)*100:.2f}%)")

    print(f"\nFinal shape: {df.shape}")
    df.to_parquet(OUT_PATH, index=False)
    print(f"→ {OUT_PATH}  ({OUT_PATH.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
