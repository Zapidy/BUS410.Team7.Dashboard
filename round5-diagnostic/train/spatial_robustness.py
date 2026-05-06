#!/usr/bin/env python3
"""Spatial robustness — leave-one-state-out CV.

Walk-forward by year handles temporal leakage. But within a fold, training
and test tracts may be neighbors in the same county or state, which lets
the model "memorize" county-level dynamics. The walk-forward AUC may be
inflated by this.

This script measures the spatial-leakage tax three ways, on the most recent
walk-forward fold's training window (2009-2021):

  1. Tract-random K-fold CV       (the optimistic baseline — spatially leaky)
  2. Year walk-forward (re-run)   (current methodology)
  3. Leave-one-state-out CV       (51 folds, the strictest spatial blocking)

The gap between (1) and (3) is the spatial-leakage tax. If (3) ≈ walk-forward,
the model generalizes spatially. If (3) << (1), our reported number has a
geography-memorization component we should know about.

Computes ~25 minutes total.
"""
from __future__ import annotations
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import (
    average_precision_score,
    roc_auc_score,
    brier_score_loss,
)
from sklearn.model_selection import KFold

warnings.filterwarnings("ignore", category=UserWarning)

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data" / "processed" / "panel" / "tract_year_with_target.parquet"
OUT = ROOT / "diagnostics" / "spatial_robustness"
OUT.mkdir(parents=True, exist_ok=True)

TARGET = "target_becomes_service_desert_h1"

DROP_NEVER_FEATURES = {
    "tract_fips", "county_fips", "state_fips", "peer_group", "service_desert_threshold",
    "service_peer_median", "origination_desert_threshold",
    "originations_per_1k", "service_desert_score", "origination_desert_score",
    "is_service_desert", "is_origination_desert", "is_any_desert",
    "vintage", "acs_vintage_used",
    "target_service_desert_h1", "target_service_desert_h2", "target_service_desert_h3",
    "target_any_desert_h1", "target_any_desert_h2", "target_any_desert_h3",
    "target_becomes_service_desert_h1", "target_becomes_service_desert_h2",
    "target_becomes_service_desert_h3",
    "target_becomes_any_desert_h1", "target_becomes_any_desert_h2",
    "target_becomes_any_desert_h3",
}
CIRCULAR_FEATURES = {
    "n_cra_lenders",
    "cra_lender_entries_1yr", "cra_lender_exits_1yr",
    "cra_lender_churn_1yr", "cra_lender_presence_ratio_1yr",
    "cra_lender_entries_3yr", "cra_lender_exits_3yr",
    "cra_lender_churn_3yr",
    "cra_county_lender_count",
    "cra_county_total_loan_count",
    "cra_county_total_loan_amount_k",
}
DROP_COLS = DROP_NEVER_FEATURES | CIRCULAR_FEATURES


def prepare(df):
    feats = df.drop(columns=[c for c in DROP_COLS if c in df.columns], errors="ignore")
    keep = [c for c in feats.columns if c != "year"]
    feats = feats[["year"] + keep]
    for col in feats.columns:
        if feats[col].dtype == object:
            feats[col] = pd.to_numeric(feats[col], errors="coerce")
    hmda_cols = [c for c in feats.columns if c in {
        "n_applications", "n_originated", "n_denied", "n_withdrawn", "n_purchased",
        "approval_rate", "denial_rate", "sum_loan_amount", "mean_loan_amount",
        "n_distinct_lenders", "n_white", "n_black", "n_asian", "n_hispanic", "n_other_race",
    }]
    feats[hmda_cols] = feats[hmda_cols].fillna(0)
    return feats


def fit_predict(X_tr, y_tr, X_te):
    """Quick model — half the trees of full run for speed across 50+ folds."""
    model = xgb.XGBClassifier(
        n_estimators=200, max_depth=6, learning_rate=0.05,
        subsample=0.85, colsample_bytree=0.85,
        min_child_weight=5, reg_lambda=1.0,
        tree_method="hist", objective="binary:logistic",
        eval_metric="aucpr",
        random_state=42, verbosity=0,
    )
    model.fit(X_tr, y_tr, verbose=False)
    return model.predict_proba(X_te)[:, 1]


def metrics(y, p, label="?"):
    if len(np.unique(y)) < 2:
        return {"label": label, "n": len(y), "pos": int(y.sum()),
                "pos_rate": float(y.mean()), "auc": None, "ap": None}
    return {
        "label": label, "n": len(y), "pos": int(y.sum()),
        "pos_rate": float(y.mean()),
        "auc": float(roc_auc_score(y, p)),
        "ap": float(average_precision_score(y, p)),
        "ap_lift": float(average_precision_score(y, p) / max(y.mean(), 1e-9)),
        "brier": float(brier_score_loss(y, p)),
    }


def main():
    print(f"Loading {PANEL.name}…")
    df = pd.read_parquet(PANEL)
    df = df[df[TARGET].notna()].copy()
    df[TARGET] = df[TARGET].astype(int)

    # Use all data 2009-2021 — same window as F8's training set in walk_forward
    df = df[df["year"].between(2009, 2021)].copy()
    df["state_fips"] = df["tract_fips"].str[:2]
    # Filter territories so per-state results align with main report
    df = df[~df["state_fips"].isin({"72", "78", "60", "66", "69"})]
    print(f"  Working set: {df.shape}, pos rate {df[TARGET].mean()*100:.2f}%, "
          f"states: {df['state_fips'].nunique()}, years 2009-2021")

    X = prepare(df).drop(columns=["year"])
    y = df[TARGET].values

    # Drop rows with no usable feature — keep deterministic
    X = X.copy()
    for col in X.columns:
        if X[col].isna().all():
            X = X.drop(columns=[col])

    print(f"  Feature matrix: {X.shape}")
    print()

    # ---- (A) Tract-random K-fold (5-fold) — the LEAKY baseline ----
    print("=" * 80)
    print("(A) Tract-random 5-fold CV (LEAKY baseline — neighbors in train + test)")
    print("=" * 80)
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    aucs_random = []
    for i, (tr_idx, te_idx) in enumerate(kf.split(X), 1):
        p = fit_predict(X.iloc[tr_idx], y[tr_idx], X.iloc[te_idx])
        m = metrics(y[te_idx], p, f"random-fold-{i}")
        aucs_random.append(m["auc"])
        print(f"  Random fold {i}: AUC={m['auc']:.4f}  AP={m['ap']:.4f}  AP-lift={m['ap_lift']:.2f}x  n={m['n']:,}")
    mean_random = float(np.nanmean(aucs_random))
    print(f"  Mean random-CV AUC: {mean_random:.4f}\n")

    # ---- (B) Year walk-forward (re-run last fold of clean run for reference) ----
    # We already have this from walk_forward_clean — read it
    print("=" * 80)
    print("(B) Year walk-forward F8 (current methodology — reference)")
    print("=" * 80)
    wf_csv = ROOT / "diagnostics" / "walk_forward_clean" / "fold_results.csv"
    wf_auc = None
    if wf_csv.exists():
        wf = pd.read_csv(wf_csv)
        wf_auc = float(wf["test_auc"].mean())
        print(f"  Mean walk-forward test AUC (across 8 folds): {wf_auc:.4f}\n")

    # ---- (C) Leave-one-state-out CV ----
    print("=" * 80)
    print("(C) Leave-one-state-out CV (STRICTEST spatial blocking — 50 folds + DC)")
    print("=" * 80)
    state_results = []
    states = sorted(df["state_fips"].unique())
    for st in states:
        held = df["state_fips"] == st
        tr_mask = ~held.values
        te_mask = held.values
        if y[tr_mask].sum() == 0 or y[te_mask].sum() == 0:
            print(f"  state={st}: SKIP (no positives in train or test)")
            continue
        p = fit_predict(X.iloc[tr_mask], y[tr_mask], X.iloc[te_mask])
        m = metrics(y[te_mask], p, f"loo-{st}")
        state_results.append({"state_fips": st, **{k: v for k, v in m.items() if k != "label"}})
        print(f"  loo-{st}: AUC={m['auc']:.4f}  AP={m['ap']:.4f}  n={m['n']:>6,}  pos={m['pos']:>5,}")
    sr_df = pd.DataFrame(state_results)
    mean_loo = float(sr_df["auc"].mean())
    median_loo = float(sr_df["auc"].median())
    iqr_loo = (float(sr_df["auc"].quantile(0.25)), float(sr_df["auc"].quantile(0.75)))
    sr_df.to_csv(OUT / "leave_one_state_out.csv", index=False)
    print()
    print(f"  Mean leave-one-state-out AUC: {mean_loo:.4f}")
    print(f"  Median:                       {median_loo:.4f}")
    print(f"  IQR:                          {iqr_loo[0]:.4f} – {iqr_loo[1]:.4f}")

    # ---- Summary ----
    print()
    print("=" * 80)
    print("SPATIAL LEAKAGE TAX — summary")
    print("=" * 80)
    print(f"  (A) Tract-random K-fold AUC:     {mean_random:.4f}    (LEAKY baseline)")
    if wf_auc:
        print(f"  (B) Year walk-forward AUC:       {wf_auc:.4f}    (current methodology)")
    print(f"  (C) Leave-one-state-out AUC:     {mean_loo:.4f}    (STRICTEST)")
    if wf_auc:
        print(f"\n  Walk-forward vs LOSO gap:        {wf_auc - mean_loo:+.4f}")
        print(f"  Random-CV vs LOSO gap:           {mean_random - mean_loo:+.4f}    (the spatial-leakage tax)")
    print()

    summary = {
        "random_5fold_mean_auc": mean_random,
        "walk_forward_mean_auc": wf_auc,
        "leave_one_state_out_mean_auc": mean_loo,
        "leave_one_state_out_median_auc": median_loo,
        "leave_one_state_out_iqr_low": iqr_loo[0],
        "leave_one_state_out_iqr_high": iqr_loo[1],
    }
    pd.Series(summary).to_csv(OUT / "summary.csv")
    print(f"→ {OUT}/summary.csv")
    print(f"→ {OUT}/leave_one_state_out.csv")


if __name__ == "__main__":
    main()
