#!/usr/bin/env python3
"""Compute SHAP feature-attribution for every tract under each (model, horizon).

We didn't save trained-model artifacts during walk-forward training (the script
only saved fold-level predictions). To compute SHAP cleanly, we train ONE
"final-deployable" model per (model_type, horizon) using ALL training data
through the latest year where the target is observable, then use XGBoost's
built-in pred_contribs (Tree SHAP) to get per-tract per-feature contribution
to log-odds.

Output:
    web/data/shap_top.json
        compact: per tract → top-5 (feature, signed_shap) per (model, horizon)
        ~79K tracts × 4 models × 5 features × ~30 bytes ≈ 5MB raw, ~1MB gzipped
"""
from __future__ import annotations
import json
import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

warnings.filterwarnings("ignore", category=UserWarning)

ROOT = Path(__file__).resolve().parents[1]
ROUND5 = ROOT.parent / "round5"
PANEL_R7 = ROOT / "data" / "processed" / "panel" / "tract_year_with_target_round7.parquet"
PANEL_R5 = ROUND5 / "data" / "processed" / "panel" / "tract_year_with_target.parquet"
OUT = ROOT / "web" / "data" / "shap_top.json"

DATA_END = 2024
TOP_K = 8  # cache top-8 so we can drop structural artifacts at render time and still serve top-5

# Features that show up in SHAP top-N but aren't substantively interpretable.
# `has_hmda` is a temporal proxy (1 for years 2018+, 0 for pre-2018 in our
# panel because CFPB only exposes API HMDA from 2018 onwards). It correlates
# with the post-2018 regime, not with anything about the tract — so it
# misleads policy-audience readers.
STRUCTURAL_ARTIFACTS = {"has_hmda"}

# Same hyperparameters as production walk-forward
XGB_PARAMS = dict(
    n_estimators=400, max_depth=6, learning_rate=0.05,
    subsample=0.85, colsample_bytree=0.85,
    min_child_weight=5, reg_lambda=1.0,
    tree_method="hist", objective="binary:logistic",
    eval_metric="aucpr", early_stopping_rounds=25,
    random_state=42, verbosity=0,
)

# Round 7 (Model 2) features — must match walk_forward_round7.py
M2_FEATURES = [
    "pct_loans_from_community_banks_resid",
    "pct_loans_from_top4_banks_resid",
    "pct_loans_from_credit_unions_resid",
    "pct_loans_under_100k_resid",
    "pct_loans_under_250k_resid",
    "top1_lender_share_tract_resid",
    "top3_lender_share_tract_resid",
    "lender_hhi_tract_resid",
    "distance_to_nearest_bank_branch",
    "branches_within_5mi",
    "branch_closures_3y_within_10mi",
    "microloan_intermediary_within_25mi",
    "mdi_branches_within_10mi",
    "mdi_branches_within_25mi",
    "nearest_mdi_branch_miles",
    "mdi_active_in_county",
    "ssbci_active",
    "ssbci_2_0_active",
    "ssbci_program_count",
    "ssbci_n_capital_programs",
]

# Round 5 (Model 1) feature drop set — keep everything that walk_forward_audit_fixed
# trains on.
M1_DROP_NEVER = {
    "tract_fips", "county_fips", "state_fips", "peer_group", "service_desert_threshold",
    "service_peer_median", "origination_desert_threshold",
    "originations_per_1k", "service_desert_score", "origination_desert_score",
    "is_service_desert", "is_origination_desert", "is_any_desert",
    "vintage", "acs_vintage_used",
    *[f"target_service_desert_h{h}" for h in range(1, 7)],
    *[f"target_any_desert_h{h}" for h in range(1, 7)],
    *[f"target_becomes_service_desert_h{h}" for h in range(1, 7)],
    *[f"target_becomes_any_desert_h{h}" for h in range(1, 7)],
}
M1_CIRCULAR = {
    "n_cra_lenders",
    "cra_lender_entries_1yr", "cra_lender_exits_1yr",
    "cra_lender_churn_1yr", "cra_lender_presence_ratio_1yr",
    "cra_lender_entries_3yr", "cra_lender_exits_3yr",
    "cra_lender_churn_3yr",
    "cra_county_lender_count", "cra_county_total_loan_count", "cra_county_total_loan_amount_k",
    "fdic_bank_count", "fdic_branch_count",
    "fdic_bank_count_chg1yr", "fdic_bank_count_chg3yr",
    "fdic_branch_count_chg1yr", "fdic_branch_count_chg3yr",
    "fdic_total_branch_deposits_k",
    "fdic_total_branch_deposits_k_chg1yr",
    "fdic_total_branch_deposits_k_chg3yr",
    "fdic_total_branch_deposits_k_pctchg1yr",
    "fdic_total_branch_deposits_k_pctchg3yr",
    "fdic_avg_branch_deposits_k",
    "fdic_avg_branch_deposits_k_chg1yr",
    "fdic_avg_branch_deposits_k_chg3yr",
}
M1_DROP = M1_DROP_NEVER | M1_CIRCULAR

TERRITORIES = {"72", "78", "60", "66", "69"}


def latest_train_year(horizon: int) -> int:
    """Latest year T where target_h{horizon} is observable (T + h ≤ 2024)."""
    return DATA_END - horizon


def hmda_fillna(df: pd.DataFrame) -> pd.DataFrame:
    hmda = ["n_applications", "n_originated", "n_denied", "n_withdrawn", "n_purchased",
            "approval_rate", "denial_rate", "sum_loan_amount", "mean_loan_amount",
            "n_distinct_lenders", "n_white", "n_black", "n_asian", "n_hispanic", "n_other_race"]
    cols = [c for c in hmda if c in df.columns]
    df[cols] = df[cols].fillna(0)
    return df


def fit_one(panel_df: pd.DataFrame, feat_cols: list[str], target_col: str,
            train_end: int) -> tuple[xgb.XGBClassifier, pd.DataFrame]:
    """Fit ONE final-deployable model on rows where year ≤ train_end and target observable."""
    df = panel_df[panel_df[target_col].notna()].copy()
    df["state_fips"] = df["tract_fips"].str[:2]
    df = df[~df["state_fips"].isin(TERRITORIES)]
    train = df[df["year"] <= train_end].copy()
    train[target_col] = train[target_col].astype(int)
    val_year = train_end  # use last year of train as val for early stopping
    train_minus = train[train["year"] < val_year]
    val = train[train["year"] == val_year]

    X_tr = train_minus[feat_cols]
    y_tr = train_minus[target_col].values
    X_v = val[feat_cols] if len(val) else X_tr.tail(1000)
    y_v = val[target_col].values if len(val) else y_tr[-1000:]

    model = xgb.XGBClassifier(**XGB_PARAMS)
    model.fit(X_tr, y_tr, eval_set=[(X_v, y_v)], verbose=False)
    print(f"    fit: train={len(train_minus):,}  val={len(val):,}  best_iter={model.best_iteration}")
    return model, df


def shap_top(model: xgb.XGBClassifier, X: pd.DataFrame, feat_cols: list[str], k: int = TOP_K):
    """Return top-k (feature, signed_shap) per row. Uses XGBoost native pred_contribs.

    Structural-artifact features (e.g. `has_hmda`) get their |shap| zeroed so
    they fall out of the top-k ranking — they're temporal proxies, not real
    drivers, and including them in the policy-audience UI is misleading.
    """
    booster = model.get_booster()
    dmat = xgb.DMatrix(X.values, feature_names=feat_cols)
    contribs = booster.predict(dmat, pred_contribs=True)  # (n_rows, n_features+1) — last is bias
    contribs = contribs[:, :-1]  # drop bias

    # For each row: indices of top-k by |shap| (signed) AFTER zeroing artifacts
    abs_c = np.abs(contribs)
    artifact_idx = [i for i, f in enumerate(feat_cols) if f in STRUCTURAL_ARTIFACTS]
    if artifact_idx:
        abs_c[:, artifact_idx] = 0.0
    topk_idx = np.argpartition(-abs_c, kth=min(k, len(feat_cols) - 1), axis=1)[:, :k]
    # sort within those k by |shap| desc
    rows_out = []
    for i, idxs in enumerate(topk_idx):
        order = idxs[np.argsort(-abs_c[i, idxs])]
        row = [(feat_cols[j], float(round(contribs[i, j], 4))) for j in order]
        rows_out.append(row)
    return rows_out


def main():
    print("=" * 72)
    print("ROUND 7 · SHAP attribution for all 4 (model, horizon) variants")
    print("=" * 72)

    print("\n[1/4] Loading round 7 panel…")
    panel7 = pd.read_parquet(PANEL_R7)
    panel7["tract_fips"] = panel7["tract_fips"].astype(str).str.zfill(11)
    print(f"  rows: {len(panel7):,}")

    print("\n[2/4] Loading round 5 panel…")
    panel5 = pd.read_parquet(PANEL_R5)
    panel5["tract_fips"] = panel5["tract_fips"].astype(str).str.zfill(11)
    panel5 = hmda_fillna(panel5)
    print(f"  rows: {len(panel5):,}")
    m1_feat_cols = [c for c in panel5.columns if c not in M1_DROP and c not in {"year", "tract_fips"}]
    # Filter to numeric-only
    m1_feat_cols = [c for c in m1_feat_cols if pd.api.types.is_numeric_dtype(panel5[c])]
    print(f"  M1 features: {len(m1_feat_cols)}")

    # Tracts to score: every tract that appears in either panel (latest year per tract)
    print("\n[3/4] Training 4 final models + computing SHAP per tract…")

    out_top: dict[str, dict[str, list]] = {}

    for model_key, panel, feats in [
        ("m1", panel5, m1_feat_cols),
        ("m2", panel7, M2_FEATURES),
    ]:
        for h in (3, 6):
            target_col = f"target_becomes_service_desert_h{h}"
            train_end = latest_train_year(h)
            run_key = f"{model_key}_h{h}"
            print(f"\n  [{run_key}] target={target_col}  train_end={train_end}…")

            model, full_df = fit_one(panel, feats, target_col, train_end)

            # Score every tract using its LATEST available year of features.
            # We pick the latest year per tract that has all features present.
            score_df = full_df.copy()
            score_df = score_df.sort_values(["tract_fips", "year"], ascending=[True, False])
            # Pick the latest non-null row per tract
            score_df = score_df.dropna(subset=feats).drop_duplicates(subset="tract_fips", keep="first")
            score_df["state_fips"] = score_df["tract_fips"].str[:2]
            score_df = score_df[~score_df["state_fips"].isin(TERRITORIES)]
            print(f"    scoring {len(score_df):,} unique tracts (latest year per tract)…")

            X = score_df[feats]
            top = shap_top(model, X, feats, k=TOP_K)

            for tract_fips, row in zip(score_df["tract_fips"].values, top):
                out_top.setdefault(tract_fips, {})[run_key] = row

            print(f"    done. cumulative tracts with attribution: {len(out_top):,}")

    print("\n[4/4] Writing JSON…")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as f:
        json.dump(out_top, f, separators=(",", ":"))
    sz = OUT.stat().st_size / 1e6
    print(f"  → {OUT}  ({sz:.1f} MB raw)")
    sample_key = next(iter(out_top))
    print(f"\nSample entry ({sample_key}):")
    print(json.dumps(out_top[sample_key], indent=2))


if __name__ == "__main__":
    main()
