#!/usr/bin/env python3
"""Residualize CRA-derived concentration features against n_cra_lenders to break
the mechanical leakage from the target.

The Round 5 target `target_becomes_service_desert_h1` is defined as the
bottom decile of `n_cra_lenders` within (year × peer_group). Several of our
"influenceable" concentration features (top1_lender_share, top3_lender_share,
HHI, community-bank share, etc.) saturate mechanically when lender count is
small — that's a target-leakage path the design brief flags.

Mitigation strategy C (per user decision): for each (year × peer_group)
cohort, regress each leakage-vulnerable feature on:
    log(n_cra_lenders + 1)  +  n_cra_lenders
and use the residual as the new feature.

This isolates the part of the feature *not* mechanically explained by the
underlying lender count signal that defines the target.

Inputs:
    data/processed/panel/tract_year_with_target_round7.parquet
        — needs `n_cra_lenders`, `is_rural`, plus the leakage-vulnerable cols.

Output:
    data/processed/features/tract_year_concentration_residualized.csv
        per (tract_fips, year), residualized variants suffixed `_resid`.

Run AFTER the main panel is built (build_round7_panel.py).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data" / "processed" / "panel" / "tract_year_with_target_round7.parquet"
OUT_DIR = ROOT / "data" / "processed" / "features"

LEAKAGE_VULN_FEATURES = [
    "top1_lender_share_tract",
    "top3_lender_share_tract",
    "lender_hhi_tract",
    "pct_loans_from_community_banks",
    "pct_loans_from_top4_banks",
    "pct_loans_from_credit_unions",
    "pct_loans_under_100k",
    "pct_loans_under_250k",
]


def residualize_cohort(group: pd.DataFrame, target_cols: list[str]) -> pd.DataFrame:
    """Within a (year, peer_group) cohort, regress each target column on
    [log(n_cra_lenders+1), n_cra_lenders] and emit residuals."""
    out = group[["tract_fips", "year"]].copy()

    n = group["n_cra_lenders"].astype(float).fillna(0).clip(lower=0)
    X = np.column_stack([np.log1p(n.values), n.values])

    for col in target_cols:
        if col not in group.columns:
            continue
        y = group[col].astype(float)
        mask = y.notna() & np.isfinite(X).all(axis=1)
        if mask.sum() < 50:
            # too few observations — leave residual NaN
            out[f"{col}_resid"] = np.nan
            continue
        try:
            model = LinearRegression()
            model.fit(X[mask], y[mask])
            pred = model.predict(X[mask])
            resid = pd.Series(np.nan, index=group.index)
            resid.loc[group.index[mask]] = (y[mask].values - pred)
            out[f"{col}_resid"] = resid.values
        except Exception:
            out[f"{col}_resid"] = np.nan
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not PANEL.exists():
        raise SystemExit(f"Missing: {PANEL}\nRun features/build_round7_panel.py first.")

    print(f"Loading {PANEL.name}…", flush=True)
    df = pd.read_parquet(PANEL)
    print(f"  rows: {len(df):,}", flush=True)

    needed = ["tract_fips", "year", "n_cra_lenders", "is_rural"] + LEAKAGE_VULN_FEATURES
    have = [c for c in needed if c in df.columns]
    missing = set(needed) - set(have)
    if missing:
        print(f"  missing cols: {missing}", flush=True)
    df = df[have].copy()
    df["peer_group"] = np.where(df["is_rural"] == 1, "rural", "urban")

    print(f"\nResidualizing {len(LEAKAGE_VULN_FEATURES)} features within (year, peer_group)…",
          flush=True)
    parts = []
    for (year, peer), g in df.groupby(["year", "peer_group"], sort=False):
        parts.append(residualize_cohort(g, LEAKAGE_VULN_FEATURES))
    out = pd.concat(parts, ignore_index=True)

    # Sort and dedupe
    out = out.sort_values(["tract_fips", "year"]).drop_duplicates(subset=["tract_fips", "year"])

    out_path = OUT_DIR / "tract_year_concentration_residualized.csv"
    out.to_csv(out_path, index=False)
    print(f"\n→ {out_path} ({len(out):,} rows)", flush=True)

    print("\nResidual std-dev (sanity check — should be much smaller than original feature std):")
    for col in LEAKAGE_VULN_FEATURES:
        rcol = f"{col}_resid"
        if rcol in out.columns:
            orig_std = df[col].std()
            resid_std = out[rcol].std()
            ratio = resid_std / orig_std if orig_std and not np.isnan(orig_std) else float("nan")
            n_obs = out[rcol].notna().sum()
            print(f"  {col:<40s} orig std={orig_std:.4f}  resid std={resid_std:.4f}  "
                  f"ratio={ratio:.2f}  n={n_obs:,}")


if __name__ == "__main__":
    main()
