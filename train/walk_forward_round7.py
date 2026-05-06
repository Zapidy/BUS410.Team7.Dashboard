#!/usr/bin/env python3
"""Phase A — Influenceable-only walk-forward training.

Forked structurally from round5/train/walk_forward_audit_fixed.py:
    - Same target: target_becomes_service_desert_h1.
    - Same 8 folds, same XGBoost hyperparameters, same isotonic calibration.
    - Same PR/VI exclusion.
    - DIFFERENT feature list: only the 14 influenceable lending-environment
      variables (Tier 1 + Tier 2 from notes/00_design_brief.md), with all
      structural ACS / HMDA / RUCA features dropped.

CRITICAL: drops `n_cra_lenders` and `n_active_lenders_tract` from features
since both are the underlying signal of the target. Keeps `is_rural` only
for evaluation slicing (also dropped from features).
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

import os
from _horizon_config import HORIZON, TARGET, FOLDS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data" / "processed" / "panel" / "tract_year_with_target_round7.parquet"

# Output dir defaults reflect horizon for cleanliness.
_run_name = os.environ.get("ROUND7_RUN_NAME", f"round7_phaseA_h{HORIZON}")
OUT = ROOT / "diagnostics" / _run_name
OUT.mkdir(parents=True, exist_ok=True)

# Whitelist: only these columns are passed to the model.
# Everything else (ACS, HMDA, RUCA, target leak) is excluded by design.
INFLUENCEABLE_FEATURES = [
    # Tier 1 — CRA, RESIDUALIZED against n_cra_lenders to break leakage
    "pct_loans_from_community_banks_resid",
    "pct_loans_from_top4_banks_resid",
    "pct_loans_from_credit_unions_resid",
    "pct_loans_under_100k_resid",
    "pct_loans_under_250k_resid",
    "top1_lender_share_tract_resid",
    "top3_lender_share_tract_resid",
    "lender_hhi_tract_resid",
    # Tier 1 — FDIC branch (clean)
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
    # NMTC features dropped — all 5 had ~0 importance in the prior pruning sweep.
]

# Trailing-mean variants (added when running the leakage-mitigated model)
TRAILING_FEATURES = [
    "pct_loans_from_community_banks_lag2to5_mean",
    "pct_loans_from_top4_banks_lag2to5_mean",
    "pct_loans_from_credit_unions_lag2to5_mean",
    "pct_loans_under_100k_lag2to5_mean",
    "pct_loans_under_250k_lag2to5_mean",
    "top1_lender_share_tract_lag2to5_mean",
    "top3_lender_share_tract_lag2to5_mean",
    "lender_hhi_tract_lag2to5_mean",
]


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


def main():
    print(f"Loading {PANEL.name}…")
    df = pd.read_parquet(PANEL)
    df = df[df[TARGET].notna()].copy()
    df[TARGET] = df[TARGET].astype(int)

    # Drop territories — same as round5
    df["state_fips"] = df["tract_fips"].str[:2]
    territory_mask = df["state_fips"].isin({"72", "78", "60", "66", "69"})
    df = df[~territory_mask].copy()
    print(f"  rows: {len(df):,}  positive rate: {df[TARGET].mean()*100:.2f}%")

    # Decide feature list — start with year-T, can add trailing means via env flag.
    use_trailing = bool(int(__import__("os").environ.get("ROUND7_USE_TRAILING", "0")))
    feat_cols = list(INFLUENCEABLE_FEATURES)
    if use_trailing:
        feat_cols += [c for c in TRAILING_FEATURES if c in df.columns]
    feat_cols = [c for c in feat_cols if c in df.columns]
    if not feat_cols:
        raise SystemExit("ERROR: no influenceable features found in the panel — "
                         "did build_round7_panel.py run?")
    print(f"  features ({len(feat_cols)}): {feat_cols}")

    fold_results = []
    test_predictions = []

    for fold_name, tr_s, tr_e, val_y, te_s, te_e in FOLDS:
        train = df[(df["year"] >= tr_s) & (df["year"] <= tr_e)]
        val = df[df["year"] == val_y]
        test = df[(df["year"] >= te_s) & (df["year"] <= te_e)]
        if len(train) == 0 or len(val) == 0 or len(test) == 0:
            print(f"\n{fold_name}: SKIP (empty split)")
            continue

        X_tr, y_tr = train[feat_cols], train[TARGET].values
        X_val, y_val = val[feat_cols], val[TARGET].values
        X_te, y_te = test[feat_cols], test[TARGET].values

        print(f"\n{fold_name}: train {tr_s}-{tr_e} ({len(train):,}) | "
              f"val {val_y} ({len(val):,}) | test {te_s}-{te_e} ({len(test):,})")
        print(f"  pos rate: train={y_tr.mean()*100:.2f}%  val={y_val.mean()*100:.2f}%  test={y_te.mean()*100:.2f}%")

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

        print(f"  VAL  AUC={val_metrics['auc']:.4f}  AP={val_metrics['ap']:.4f}")
        print(f"  TEST raw       AUC={test_metrics_raw['auc']:.4f}  AP={test_metrics_raw['ap']:.4f}  "
              f"lift={test_metrics_raw['ap_lift']:.2f}x  Brier={test_metrics_raw['brier']:.4f}")
        print(f"  TEST calibrated AUC={test_metrics_cal['auc']:.4f}  AP={test_metrics_cal['ap']:.4f}")

        fold_results.append({
            "fold": fold_name, "train_years": f"{tr_s}-{tr_e}",
            "val_year": val_y, "test_years": f"{te_s}-{te_e}",
            "n_train": len(train), "n_val": len(val), "n_test": len(test),
            "best_iter": model.best_iteration,
            "val_auc": val_metrics["auc"], "val_ap": val_metrics["ap"],
            "test_auc": test_metrics_raw["auc"],
            "test_ap": test_metrics_raw["ap"],
            "test_ap_lift": test_metrics_raw["ap_lift"],
            "test_brier_raw": test_metrics_raw["brier"],
            "test_brier_calibrated": test_metrics_cal["brier"],
            "test_pos_rate": test_metrics_raw["pos_rate"],
        })

        # Feature importance per fold
        imp = pd.DataFrame({
            "feature": feat_cols,
            "importance": model.feature_importances_,
            "fold": fold_name,
        })
        imp.to_csv(OUT / f"feature_importance_{fold_name}.csv", index=False)

        pred_df = test[["tract_fips", "county_fips", "year"]].copy()
        pred_df["fold"] = fold_name
        pred_df["y_true"] = y_te
        pred_df["y_prob"] = test_prob
        pred_df["y_prob_calibrated"] = test_prob_calibrated
        test_predictions.append(pred_df)

    res_df = pd.DataFrame(fold_results)
    print(f"\n{'='*80}\nROUND 7 PHASE A — Influenceable-only model | h+{HORIZON} (target={TARGET})\n{'='*80}")
    print(res_df[["fold", "train_years", "test_years", "n_test", "test_auc",
                  "test_ap", "test_ap_lift", "test_brier_calibrated"]].to_string(
                      index=False, float_format="%.4f"))
    print(f"\nMean test AUC: {res_df['test_auc'].mean():.4f}  ± {res_df['test_auc'].std():.4f}")
    print(f"Mean test AP:  {res_df['test_ap'].mean():.4f}")
    print(f"Mean lift:     {res_df['test_ap_lift'].mean():.2f}x")
    print(f"\nDecision rule (notes/03_decision_rule.md):")
    mean_ap = res_df['test_ap'].mean()
    if mean_ap >= 0.10:
        print(f"  AP {mean_ap:.4f} ≥ 0.10 → STRONG signal. Phase 2 (slider) viable.")
    elif mean_ap >= 0.05:
        print(f"  AP {mean_ap:.4f} ∈ [0.05, 0.10) → MODERATE. Run both Phase C variants.")
    else:
        print(f"  AP {mean_ap:.4f} < 0.05 → WEAK. Run only Variant B (bolt-on).")

    res_df.to_csv(OUT / "fold_results.csv", index=False)
    pd.concat(test_predictions, ignore_index=True).to_parquet(OUT / "test_predictions.parquet", index=False)
    print(f"\n→ {OUT}")


if __name__ == "__main__":
    main()
