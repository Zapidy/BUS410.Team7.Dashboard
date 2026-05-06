#!/usr/bin/env python3
"""H3 (3-year) horizon walk-forward training — sibling of audit-fixed H1.

Same architecture as walk_forward_audit_fixed.py:
  - XGBoost, hist tree method, 400 trees, depth 6, lr 0.05
  - 25 circular features dropped
  - PR/VI/territories excluded
  - Isotonic calibration on val, applied to test

Differences:
  - TARGET = target_becomes_service_desert_h3 (3-year horizon)
  - Folds compress to where h3 labels exist: train Y → val Y+1 → test Y+2..Y+3
    Need test_year + 3 ≤ 2024 so test ranges Y ≤ 2021. Six folds.
  - After fold 8, score 2024 features (no labels) → future_predictions.parquet
    These are the "Forecast 2030" surface used by the dashboard.
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
PANEL = ROOT / "data" / "processed" / "panel" / "tract_year_with_target.parquet"
OUT = ROOT / "diagnostics" / "walk_forward_h3"
OUT.mkdir(parents=True, exist_ok=True)

TARGET = "target_becomes_service_desert_h3"

# H3 needs Y+3 labels → test_year ≤ 2021 (since panel ends 2024).
# Six walk-forward folds, 2-year test windows where possible.
FOLDS = [
    ("F1", 2009, 2014, 2015, 2016, 2017),
    ("F2", 2009, 2015, 2016, 2017, 2018),
    ("F3", 2009, 2016, 2017, 2018, 2019),
    ("F4", 2009, 2017, 2018, 2019, 2020),
    ("F5", 2009, 2018, 2019, 2020, 2021),
    ("F6", 2009, 2019, 2020, 2021, 2021),
]

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

CIRCULAR_FEATURES_PRIOR = {
    "n_cra_lenders",
    "cra_lender_entries_1yr", "cra_lender_exits_1yr",
    "cra_lender_churn_1yr", "cra_lender_presence_ratio_1yr",
    "cra_lender_entries_3yr", "cra_lender_exits_3yr",
    "cra_lender_churn_3yr",
    "cra_county_lender_count",
    "cra_county_total_loan_count",
    "cra_county_total_loan_amount_k",
}

CIRCULAR_FEATURES_FDIC = {
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

CIRCULAR_FEATURES = CIRCULAR_FEATURES_PRIOR | CIRCULAR_FEATURES_FDIC
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
    df_full = pd.read_parquet(PANEL)
    df_full["state_fips"] = df_full["tract_fips"].str[:2]
    territory_mask = df_full["state_fips"].isin({"72", "78", "60", "66", "69"})
    df_full = df_full[~territory_mask].copy()

    # Labeled set for fit/eval — H3 label observable
    df = df_full[df_full[TARGET].notna()].copy()
    df[TARGET] = df[TARGET].astype(int)
    print(f"  Labeled rows (h3 observable): {df.shape}")
    print(f"  Overall positive rate: {df[TARGET].mean()*100:.2f}%")

    # Future-prediction set: latest year (2024), unlabeled, excludes already-deserts
    future_year = int(df_full["year"].max())
    future = df_full[
        (df_full["year"] == future_year) & (df_full["is_service_desert"] == 0)
    ].copy()
    print(f"  Future scoring set: {len(future):,} non-desert tracts at year {future_year}")

    fold_results = []
    test_predictions = []
    last_model = None
    last_calibrator = None
    last_feature_cols = None

    for fold_name, tr_s, tr_e, val_y, te_s, te_e in FOLDS:
        train = df[(df["year"] >= tr_s) & (df["year"] <= tr_e)]
        val = df[df["year"] == val_y]
        test = df[(df["year"] >= te_s) & (df["year"] <= te_e)]
        if len(train) == 0 or len(val) == 0 or len(test) == 0:
            print(f"\n{fold_name}: SKIP (empty split)")
            continue

        X_tr = prepare(train).drop(columns=["year"])
        y_tr = train[TARGET].values
        X_val = prepare(val).drop(columns=["year"])
        y_val = val[TARGET].values
        X_te = prepare(test).drop(columns=["year"])
        y_te = test[TARGET].values

        common = sorted(set(X_tr.columns) & set(X_val.columns) & set(X_te.columns))
        X_tr, X_val, X_te = X_tr[common], X_val[common], X_te[common]

        print(f"\n{fold_name}: train {tr_s}-{tr_e} ({len(train):,}) | "
              f"val {val_y} ({len(val):,}) | test {te_s}-{te_e} ({len(test):,})")
        print(f"  features: {len(common)}")
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
        print(f"  TEST raw          AUC={test_metrics_raw['auc']:.4f}  AP={test_metrics_raw['ap']:.4f}  "
              f"AP-lift={test_metrics_raw['ap_lift']:.2f}x  Brier={test_metrics_raw['brier']:.4f}")
        print(f"  TEST calibrated   AUC={test_metrics_cal['auc']:.4f}  AP={test_metrics_cal['ap']:.4f}  "
              f"AP-lift={test_metrics_cal['ap_lift']:.2f}x  Brier={test_metrics_cal['brier']:.4f}")

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

        pred_df = test[["tract_fips", "county_fips", "year"]].copy()
        pred_df["fold"] = fold_name
        pred_df["y_true"] = y_te
        pred_df["y_prob"] = test_prob
        pred_df["y_prob_calibrated"] = test_prob_calibrated
        test_predictions.append(pred_df)

        last_model = model
        last_calibrator = cal
        last_feature_cols = common

    res_df = pd.DataFrame(fold_results)
    print(f"\n{'='*80}\nH3 (3-YEAR HORIZON) fold summary\n{'='*80}")
    print(res_df[["fold", "train_years", "test_years", "n_test", "test_auc",
                  "test_ap", "test_ap_lift", "test_brier_raw", "test_brier_calibrated"]].to_string(
                      index=False, float_format="%.4f"))
    print(f"\nMean test AUC:  {res_df['test_auc'].mean():.4f}  ± {res_df['test_auc'].std():.4f}")
    print(f"Mean test AP:   {res_df['test_ap'].mean():.4f}")
    print(f"Mean AP-lift:   {res_df['test_ap_lift'].mean():.2f}x")
    print(f"Brier (raw):    {res_df['test_brier_raw'].mean():.4f}")
    print(f"Brier (calib):  {res_df['test_brier_calibrated'].mean():.4f}")

    res_df.to_csv(OUT / "fold_results.csv", index=False)
    pd.concat(test_predictions, ignore_index=True).to_parquet(OUT / "test_predictions.parquet", index=False)

    # Score the unlabeled future set (year 2024) → "Forecast 2030" surface.
    print(f"\nScoring future set ({len(future):,} non-desert tracts at {future_year})…")
    X_fu = prepare(future).drop(columns=["year"])
    X_fu = X_fu.reindex(columns=last_feature_cols, fill_value=0)
    fu_prob = last_model.predict_proba(X_fu)[:, 1]
    fu_prob_cal = last_calibrator.transform(fu_prob)
    future_out = future[["tract_fips", "county_fips", "year"]].copy()
    future_out["y_prob"] = fu_prob
    future_out["y_prob_calibrated"] = fu_prob_cal
    future_out.to_parquet(OUT / "future_predictions.parquet", index=False)
    print(f"  → {OUT/'future_predictions.parquet'} ({len(future_out):,} rows)")
    print(f"  mean future risk: {fu_prob_cal.mean()*100:.2f}%  max: {fu_prob_cal.max()*100:.1f}%")
    print(f"\n→ {OUT}")


if __name__ == "__main__":
    main()
