#!/usr/bin/env python3
"""Merge round7 influenceable features + carry the round5 target into a single
training panel.

Inputs:
    ../round5/data/processed/panel/tract_year_with_target.parquet
        Provides target_becomes_service_desert_h1 + tract_fips + year keys.

    data/processed/branch_geo/tract_year_branch_geo.csv
    data/processed/features/tract_year_concentration.csv
    data/processed/features/tract_year_lender_mix.csv
    data/processed/features/tract_year_mission_proximity.csv

Output:
    data/processed/panel/tract_year_with_target_round7.parquet

Columns:
    tract_fips, county_fips, year, is_rural,           # keys + slicing
    target_becomes_service_desert_h1,                  # carried from round5
    pct_loans_from_community_banks,
    pct_loans_from_top4_banks,
    pct_loans_from_credit_unions,
    pct_loans_under_100k,
    pct_loans_under_250k,
    top1_lender_share_tract,
    top3_lender_share_tract,
    lender_hhi_tract,
    distance_to_nearest_bank_branch,
    branches_within_5mi,
    branch_closures_3y_within_10mi,
    cdfi_within_10mi,
    mdi_branches_within_10mi,
    microloan_intermediary_within_25mi,
    + all `*_lag2to5_mean` trailing variants

NOTE: `n_active_lenders_tract` is preserved as a column to support the
NaN-gate verification in diagnostics, but it MUST be dropped from features
before training (it is the target's underlying signal).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ROUND5_PANEL = ROOT.parent / "round5" / "data" / "processed" / "panel" / "tract_year_with_target.parquet"

BRANCH_GEO = ROOT / "data" / "processed" / "branch_geo" / "tract_year_branch_geo.csv"
CONCENTRATION = ROOT / "data" / "processed" / "features" / "tract_year_concentration.csv"
LENDER_MIX = ROOT / "data" / "processed" / "features" / "tract_year_lender_mix.csv"
MISSION = ROOT / "data" / "processed" / "features" / "tract_year_mission_proximity.csv"
MDI = ROOT / "data" / "processed" / "features" / "tract_year_mdi.csv"
SSBCI = ROOT / "data" / "processed" / "features" / "state_year_ssbci.csv"
RESIDUALIZED = ROOT / "data" / "processed" / "features" / "tract_year_concentration_residualized.csv"

# NMTC features dropped per pruning result — all 5 were ~0 importance.
SSBCI_FEATURES = ["ssbci_active", "ssbci_2_0_active",
                  "ssbci_program_count", "ssbci_n_capital_programs"]

OUT_DIR = ROOT / "data" / "processed" / "panel"
OUT_PATH = OUT_DIR / "tract_year_with_target_round7.parquet"

KEEP_FROM_ROUND5 = [
    "tract_fips", "county_fips", "year", "is_rural",
    # All horizons carried for downstream training. h+3 is primary, h+6 is the
    # 2030-scenario long-horizon target. h+1 retained for backwards-comparable
    # baseline sanity checks.
    "target_becomes_service_desert_h1",
    "target_becomes_service_desert_h3",
    "target_becomes_service_desert_h6",
    # Keep n_cra_lenders for verification / NaN-gate sanity, then drop in training.
    "n_cra_lenders",
]


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        print(f"  WARN: {path} missing — features will be absent", flush=True)
        return pd.DataFrame(columns=["tract_fips", "year"])
    return pd.read_csv(path, dtype={"tract_fips": str, "year": int})


def main():
    if not ROUND5_PANEL.exists():
        raise SystemExit(f"Missing: {ROUND5_PANEL}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loading round5 panel…", flush=True)
    base = pd.read_parquet(ROUND5_PANEL)
    keep = [c for c in KEEP_FROM_ROUND5 if c in base.columns]
    base = base[keep].copy()
    base["tract_fips"] = base["tract_fips"].astype(str).str.zfill(11)
    base["year"] = base["year"].astype(int)
    print(f"  rows: {len(base):,}", flush=True)
    for h in (1, 3, 6):
        c = f"target_becomes_service_desert_h{h}"
        if c in base.columns:
            print(f"  h+{h}: {(base[c]==1).sum():,} pos / {base[c].notna().sum():,} labeled", flush=True)

    print("Joining branch geo…", flush=True)
    bg = load_csv(BRANCH_GEO)
    if not bg.empty:
        bg["tract_fips"] = bg["tract_fips"].astype(str).str.zfill(11)
        base = base.merge(bg, on=["tract_fips", "year"], how="left")

    print("Joining concentration…", flush=True)
    cc = load_csv(CONCENTRATION)
    if not cc.empty:
        cc["tract_fips"] = cc["tract_fips"].astype(str).str.zfill(11)
        base = base.merge(cc, on=["tract_fips", "year"], how="left")

    print("Joining lender mix…", flush=True)
    lm = load_csv(LENDER_MIX)
    if not lm.empty:
        lm["tract_fips"] = lm["tract_fips"].astype(str).str.zfill(11)
        # n_active_lenders may already exist from concentration; keep first
        dup = [c for c in lm.columns if c in base.columns and c not in {"tract_fips", "year"}]
        lm = lm.drop(columns=dup)
        base = base.merge(lm, on=["tract_fips", "year"], how="left")

    print("Joining mission proximity (microlender)…", flush=True)
    mp = load_csv(MISSION)
    if not mp.empty:
        mp["tract_fips"] = mp["tract_fips"].astype(str).str.zfill(11)
        # Drop the older NaN cdfi/mdi columns; the year-precise MDI feature
        # below replaces mdi_branches_within_10mi, and NMTC replaces cdfi_within_10mi.
        drop_overlap = [c for c in ("cdfi_within_10mi", "mdi_branches_within_10mi") if c in mp.columns]
        mp = mp.drop(columns=drop_overlap)
        base = base.merge(mp, on=["tract_fips", "year"], how="left")

    print("Joining year-precise MDI…", flush=True)
    mdi = load_csv(MDI)
    if not mdi.empty:
        mdi["tract_fips"] = mdi["tract_fips"].astype(str).str.zfill(11)
        # Avoid column collisions with prior mission_proximity merge
        dup = [c for c in mdi.columns if c in base.columns and c not in {"tract_fips", "year"}]
        mdi = mdi.drop(columns=dup)
        base = base.merge(mdi, on=["tract_fips", "year"], how="left")

    print("Joining residualized concentration features…", flush=True)
    rz = load_csv(RESIDUALIZED)
    if not rz.empty:
        rz["tract_fips"] = rz["tract_fips"].astype(str).str.zfill(11)
        # Drop column collisions if any (residualized cols are suffixed _resid so should be safe)
        dup = [c for c in rz.columns if c in base.columns and c not in {"tract_fips", "year"}]
        rz = rz.drop(columns=dup)
        base = base.merge(rz, on=["tract_fips", "year"], how="left")

    print("Joining SSBCI state-year overlay…", flush=True)
    ssbci = load_csv(SSBCI)
    if not ssbci.empty:
        # SSBCI is keyed on (state_fips, year) — broadcast to all tracts in state
        ssbci["state_fips"] = ssbci["state_fips"].astype(str).str.zfill(2)
        if "state_fips" not in base.columns:
            base["state_fips"] = base["tract_fips"].astype(str).str[:2]
        base = base.merge(
            ssbci[["state_fips", "year"] + SSBCI_FEATURES + ([] if "era_label" not in ssbci.columns else ["era_label"])],
            on=["state_fips", "year"], how="left",
        )
        for c in SSBCI_FEATURES:
            if c in base.columns:
                base[c] = base[c].fillna(0)

    print(f"\nFinal panel: {base.shape}", flush=True)
    print(f"Columns: {list(base.columns)}", flush=True)

    base.to_parquet(OUT_PATH, index=False)
    print(f"\n→ {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
