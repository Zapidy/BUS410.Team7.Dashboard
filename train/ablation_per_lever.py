#!/usr/bin/env python3
"""Per-lever ablation study on round7 Model 2 (influenceable-only).

For each policy-lever group, retrains the walk-forward model with that group's
features REMOVED, runs all 8 folds, and records mean AUC, mean AP, and per-fold
metrics. Also runs a baseline with all features kept.

Same pipeline as walk_forward_round7.py:
    - Same panel, same target
    - Same 8 walk-forward folds
    - Same XGBoost hyperparameters
    - Same isotonic calibration on the val year
    - Same PR/VI territory exclusion

Outputs:
    diagnostics/round7_ablation/ablation_summary.csv
    diagnostics/round7_ablation/ablation_per_fold.csv
"""
from __future__ import annotations
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)

warnings.filterwarnings("ignore", category=UserWarning)

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data" / "processed" / "panel" / "tract_year_with_target_round7.parquet"

from _horizon_config import HORIZON, TARGET, FOLDS  # noqa: E402

OUT = ROOT / "diagnostics" / f"round7_ablation_h{HORIZON}"
OUT.mkdir(parents=True, exist_ok=True)

INFLUENCEABLE_FEATURES = [
    # Tier 1 — CRA, RESIDUALIZED against n_cra_lenders
    "pct_loans_from_community_banks_resid",
    "pct_loans_from_top4_banks_resid",
    "pct_loans_from_credit_unions_resid",
    "pct_loans_under_100k_resid",
    "pct_loans_under_250k_resid",
    "top1_lender_share_tract_resid",
    "top3_lender_share_tract_resid",
    "lender_hhi_tract_resid",
    # Tier 1 — FDIC branch
    "distance_to_nearest_bank_branch",
    "branches_within_5mi",
    "branch_closures_3y_within_10mi",
    # Tier 2 — Microlender ecosystem
    "microloan_intermediary_within_25mi",
    # Tier 2 — Year-precise MDI
    "mdi_branches_within_10mi",
    "mdi_branches_within_25mi",
    "nearest_mdi_branch_miles",
    "mdi_active_in_county",
    # Tier 3 — SSBCI state-year overlay
    "ssbci_active",
    "ssbci_2_0_active",
    "ssbci_program_count",
    "ssbci_n_capital_programs",
]

# Policy-lever groups for ablation. The label is the lever_dropped value;
# its features are removed from the feature list for that run.
LEVER_GROUPS = {
    "branch_access": [
        "distance_to_nearest_bank_branch",
        "branches_within_5mi",
        "branch_closures_3y_within_10mi",
    ],
    "mdi_mission_lender": [
        "mdi_branches_within_10mi",
        "mdi_branches_within_25mi",
        "nearest_mdi_branch_miles",
        "mdi_active_in_county",
    ],
    "ssbci_state_policy": [
        "ssbci_active",
        "ssbci_2_0_active",
        "ssbci_program_count",
        "ssbci_n_capital_programs",
    ],
    "microlender_ecosystem": [
        "microloan_intermediary_within_25mi",
    ],
    "residualized_concentration": [
        "top1_lender_share_tract_resid",
        "top3_lender_share_tract_resid",
        "lender_hhi_tract_resid",
    ],
    "residualized_lender_mix": [
        "pct_loans_from_community_banks_resid",
        "pct_loans_from_top4_banks_resid",
        "pct_loans_from_credit_unions_resid",
    ],
    "residualized_loan_size": [
        "pct_loans_under_100k_resid",
        "pct_loans_under_250k_resid",
    ],
}


def evaluate(y_true, y_prob):
    if len(np.unique(y_true)) < 2:
        return {"auc": float("nan"), "ap": float("nan"),
                "ap_lift": float("nan"), "brier": float("nan"),
                "n": len(y_true), "pos_rate": float(y_true.mean())}
    auc = roc_auc_score(y_true, y_prob)
    ap = average_precision_score(y_true, y_prob)
    pos_rate = y_true.mean()
    return {
        "auc": float(auc), "ap": float(ap),
        "ap_lift": float(ap / pos_rate) if pos_rate > 0 else float("nan"),
        "brier": float(brier_score_loss(y_true, y_prob)),
        "n": len(y_true), "pos_rate": float(pos_rate),
    }


def run_walk_forward(df: pd.DataFrame, feat_cols: list[str], label: str) -> list[dict]:
    """Run all 8 folds with the given feature set; return per-fold metric dicts."""
    fold_results = []
    for fold_name, tr_s, tr_e, val_y, te_s, te_e in FOLDS:
        train = df[(df["year"] >= tr_s) & (df["year"] <= tr_e)]
        val = df[df["year"] == val_y]
        test = df[(df["year"] >= te_s) & (df["year"] <= te_e)]
        if len(train) == 0 or len(val) == 0 or len(test) == 0:
            print(f"  {fold_name}: SKIP (empty split)")
            continue

        X_tr, y_tr = train[feat_cols], train[TARGET].values
        X_val, y_val = val[feat_cols], val[TARGET].values
        X_te, y_te = test[feat_cols], test[TARGET].values

        model = xgb.XGBClassifier(
            n_estimators=400, max_depth=6, learning_rate=0.05,
            subsample=0.85, colsample_bytree=0.85,
            min_child_weight=5, reg_lambda=1.0,
            tree_method="hist", objective="binary:logistic",
            eval_metric="aucpr", early_stopping_rounds=25,
            random_state=42, verbosity=0,
        )
        model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)

        val_prob = model.predict_proba(X_val)[:, 1]
        test_prob = model.predict_proba(X_te)[:, 1]

        cal = IsotonicRegression(out_of_bounds="clip")
        cal.fit(val_prob, y_val)
        test_prob_calibrated = cal.transform(test_prob)

        val_metrics = evaluate(y_val, val_prob)
        test_metrics_raw = evaluate(y_te, test_prob)
        test_metrics_cal = evaluate(y_te, test_prob_calibrated)

        print(f"  {fold_name}: TEST AUC={test_metrics_raw['auc']:.4f}  "
              f"AP={test_metrics_raw['ap']:.4f}  lift={test_metrics_raw['ap_lift']:.2f}x")

        fold_results.append({
            "lever_dropped": label,
            "n_features": len(feat_cols),
            "fold": fold_name,
            "train_years": f"{tr_s}-{tr_e}",
            "val_year": val_y,
            "test_years": f"{te_s}-{te_e}",
            "n_train": len(train), "n_val": len(val), "n_test": len(test),
            "best_iter": int(model.best_iteration),
            "val_auc": val_metrics["auc"], "val_ap": val_metrics["ap"],
            "test_auc": test_metrics_raw["auc"],
            "test_ap": test_metrics_raw["ap"],
            "test_ap_lift": test_metrics_raw["ap_lift"],
            "test_brier_raw": test_metrics_raw["brier"],
            "test_brier_calibrated": test_metrics_cal["brier"],
            "test_pos_rate": test_metrics_raw["pos_rate"],
        })
    return fold_results


def main():
    print(f"Loading {PANEL.name}…")
    df = pd.read_parquet(PANEL)
    df = df[df[TARGET].notna()].copy()
    df[TARGET] = df[TARGET].astype(int)

    df["state_fips"] = df["tract_fips"].str[:2]
    territory_mask = df["state_fips"].isin({"72", "78", "60", "66", "69"})
    df = df[~territory_mask].copy()
    print(f"  rows: {len(df):,}  positive rate: {df[TARGET].mean()*100:.2f}%")

    available = [c for c in INFLUENCEABLE_FEATURES if c in df.columns]
    if len(available) != len(INFLUENCEABLE_FEATURES):
        missing = set(INFLUENCEABLE_FEATURES) - set(available)
        print(f"  WARNING: missing features in panel: {missing}")
    print(f"  full feature set ({len(available)}): {available}")

    # Sanity-check that every lever-group feature is in the panel
    all_lever_feats = {f for feats in LEVER_GROUPS.values() for f in feats}
    missing_lever = all_lever_feats - set(available)
    if missing_lever:
        print(f"  WARNING: lever features missing in panel: {missing_lever}")

    runs = [("none_baseline", [])]  # baseline: drop nothing
    runs.extend((label, feats) for label, feats in LEVER_GROUPS.items())

    all_per_fold = []
    summary_rows = []

    for label, drop_feats in runs:
        feat_cols = [c for c in available if c not in set(drop_feats)]
        print(f"\n{'='*80}\nABLATION: {label}  (n_features={len(feat_cols)})\n"
              f"  dropped: {drop_feats}\n{'='*80}")
        fold_results = run_walk_forward(df, feat_cols, label)
        all_per_fold.extend(fold_results)
        fr_df = pd.DataFrame(fold_results)
        summary_rows.append({
            "lever_dropped": label,
            "n_features": len(feat_cols),
            "mean_test_auc": fr_df["test_auc"].mean(),
            "std_test_auc": fr_df["test_auc"].std(),
            "mean_test_ap": fr_df["test_ap"].mean(),
            "std_test_ap": fr_df["test_ap"].std(),
            "mean_test_ap_lift": fr_df["test_ap_lift"].mean(),
            "mean_test_brier_calibrated": fr_df["test_brier_calibrated"].mean(),
        })
        print(f"\n  -> mean AUC={summary_rows[-1]['mean_test_auc']:.4f}  "
              f"mean AP={summary_rows[-1]['mean_test_ap']:.4f}  "
              f"mean lift={summary_rows[-1]['mean_test_ap_lift']:.2f}x")

    summary_df = pd.DataFrame(summary_rows)
    base = summary_df.loc[summary_df["lever_dropped"] == "none_baseline"].iloc[0]
    summary_df["delta_auc_vs_full"] = summary_df["mean_test_auc"] - base["mean_test_auc"]
    summary_df["delta_ap_vs_full"] = summary_df["mean_test_ap"] - base["mean_test_ap"]
    summary_df = summary_df.sort_values("delta_ap_vs_full").reset_index(drop=True)

    pf_df = pd.DataFrame(all_per_fold)

    summary_df.to_csv(OUT / "ablation_summary.csv", index=False)
    pf_df.to_csv(OUT / "ablation_per_fold.csv", index=False)

    print(f"\n{'='*80}\nABLATION SUMMARY (sorted by delta_ap, most-impactful drop first)\n{'='*80}")
    print(summary_df[["lever_dropped", "n_features",
                      "mean_test_auc", "mean_test_ap",
                      "delta_auc_vs_full", "delta_ap_vs_full"]].to_string(
                          index=False, float_format="%.4f"))
    print(f"\n→ {OUT}")


if __name__ == "__main__":
    main()
