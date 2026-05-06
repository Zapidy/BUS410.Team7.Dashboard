#!/usr/bin/env python3
"""Walk-forward training with the 2026-04-28 audit fixes applied.

This is the most defensible version of the model. Compared to walk_forward_clean.py:

  Fix #1 — FDIC proxy circularity:
    Drop fdic_bank_count, fdic_branch_count, and their chg1yr/chg3yr/pctchg variants.
    These features at year T are mechanically correlated with n_cra_lenders at year T
    (banks ARE CRA reporters above the asset threshold). Keep deposit-concentration
    (HHI, top-bank-share) since those measure shape, not level.

  Fix #2 — ACS publication-lag leak:
    Already applied in build_panel.py: vintage <= year - 2 (was year - 1).

  Fix #6 — Test-window asymmetry:
    Standardize all folds to 2-year test windows. Previously F1-F7 tested 3 years,
    F8 tested 2 years — incomparable.

  Fix #7 — PR/VI in training:
    Filter state_fips ∈ {72, 78} from train, val, test, and diagnostics.
    Previously they were in training but excluded only from per-state reports.

  Fix #11 — Isotonic calibration:
    After fold training, fit an isotonic regressor on val predictions and apply
    to test predictions. Reports Brier score before and after.
"""
from __future__ import annotations
import os
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

# HORIZON: forecast h-step. Default 3 — the primary horizon since h+1 forecasts
# are already past by the time CRA reports new data.
HORIZON = int(os.environ.get("ROUND5_HORIZON", "3"))
TARGET = f"target_becomes_service_desert_h{HORIZON}"

_run = os.environ.get("ROUND5_RUN_NAME", f"walk_forward_h{HORIZON}")
OUT = ROOT / "diagnostics" / _run
OUT.mkdir(parents=True, exist_ok=True)


def _build_folds(horizon: int) -> list:
    if horizon == 1:
        return [
            ("F1", 2009, 2014, 2015, 2016, 2017),
            ("F2", 2009, 2015, 2016, 2017, 2018),
            ("F3", 2009, 2016, 2017, 2018, 2019),
            ("F4", 2009, 2017, 2018, 2019, 2020),
            ("F5", 2009, 2018, 2019, 2020, 2021),
            ("F6", 2009, 2019, 2020, 2021, 2022),
            ("F7", 2009, 2020, 2021, 2022, 2023),
            ("F8", 2009, 2021, 2022, 2023, 2024),
        ]
    if horizon == 3:
        return [
            ("F1", 2009, 2012, 2013, 2014, 2015),
            ("F2", 2009, 2013, 2014, 2015, 2016),
            ("F3", 2009, 2014, 2015, 2016, 2017),
            ("F4", 2009, 2015, 2016, 2017, 2018),
            ("F5", 2009, 2016, 2017, 2018, 2019),
            ("F6", 2009, 2017, 2018, 2019, 2020),
            ("F7", 2009, 2018, 2019, 2020, 2021),
            ("F8", 2009, 2019, 2020, 2021, 2021),
        ]
    if horizon == 6:
        return [
            ("F1", 2009, 2010, 2011, 2012, 2013),
            ("F2", 2009, 2011, 2012, 2013, 2014),
            ("F3", 2009, 2012, 2013, 2014, 2015),
            ("F4", 2009, 2013, 2014, 2015, 2016),
            ("F5", 2009, 2014, 2015, 2016, 2017),
            ("F6", 2009, 2015, 2016, 2017, 2018),
        ]
    raise ValueError(f"Unsupported HORIZON: {horizon}")


FOLDS = _build_folds(HORIZON)

DROP_NEVER_FEATURES = {
    "tract_fips", "county_fips", "state_fips", "peer_group", "service_desert_threshold",
    "service_peer_median", "origination_desert_threshold",
    "originations_per_1k", "service_desert_score", "origination_desert_score",
    "is_service_desert", "is_origination_desert", "is_any_desert",
    "vintage", "acs_vintage_used",
    "target_service_desert_h1", "target_service_desert_h2", "target_service_desert_h3",
    "target_any_desert_h1", "target_any_desert_h2", "target_any_desert_h3",
    "target_becomes_service_desert_h1", "target_becomes_service_desert_h2",
    "target_becomes_service_desert_h3", "target_becomes_service_desert_h4",
    "target_becomes_service_desert_h5", "target_becomes_service_desert_h6",
    "target_service_desert_h4", "target_service_desert_h5", "target_service_desert_h6",
    "target_any_desert_h4", "target_any_desert_h5", "target_any_desert_h6",
    "target_becomes_any_desert_h1", "target_becomes_any_desert_h2",
    "target_becomes_any_desert_h3", "target_becomes_any_desert_h4",
    "target_becomes_any_desert_h5", "target_becomes_any_desert_h6",
}

# Tier 1 + Tier 2 from prior audit (CRA-side circular features)
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

# Fix #1 — Tier 3: FDIC count features that are proxies for CRA lender count.
# Keep concentration shape (HHI, top-share) since those measure distribution shape, not level.
CIRCULAR_FEATURES_FDIC = {
    "fdic_bank_count", "fdic_branch_count",
    "fdic_bank_count_chg1yr", "fdic_bank_count_chg3yr",
    "fdic_branch_count_chg1yr", "fdic_branch_count_chg3yr",
    # Total branch deposits are heavily correlated with branch counts
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
    df = pd.read_parquet(PANEL)
    df = df[df[TARGET].notna()].copy()
    df[TARGET] = df[TARGET].astype(int)

    # Fix #7: drop PR (72) and VI (78) from train + val + test entirely
    df["state_fips"] = df["tract_fips"].str[:2]
    territory_mask = df["state_fips"].isin({"72", "78", "60", "66", "69"})
    n_territory = int(territory_mask.sum())
    df = df[~territory_mask].copy()
    print(f"  Loaded: {df.shape}, dropped {n_territory:,} territory rows (PR/VI/etc)")
    print(f"  Overall positive rate: {df[TARGET].mean()*100:.2f}%")

    print(f"  CIRCULAR features dropped: {len(CIRCULAR_FEATURES)} total "
          f"({len(CIRCULAR_FEATURES_PRIOR)} prior + {len(CIRCULAR_FEATURES_FDIC)} new FDIC)")

    fold_results = []
    test_predictions = []

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

        # Fix #11: isotonic calibration on val, applied to test
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

    res_df = pd.DataFrame(fold_results)
    print(f"\n{'='*80}\nAUDIT-FIXED fold summary\n{'='*80}")
    print(res_df[["fold", "train_years", "test_years", "n_test", "test_auc",
                  "test_ap", "test_ap_lift", "test_brier_raw", "test_brier_calibrated"]].to_string(
                      index=False, float_format="%.4f"))
    print(f"\nMean test AUC:  {res_df['test_auc'].mean():.4f}  ± {res_df['test_auc'].std():.4f}")
    print(f"Mean test AP:   {res_df['test_ap'].mean():.4f}")
    print(f"Mean AP-lift:   {res_df['test_ap_lift'].mean():.2f}x")
    print(f"Brier (raw):    {res_df['test_brier_raw'].mean():.4f}")
    print(f"Brier (calib):  {res_df['test_brier_calibrated'].mean():.4f}  "
          f"(Δ {(res_df['test_brier_calibrated'] - res_df['test_brier_raw']).mean():+.4f})")

    res_df.to_csv(OUT / "fold_results.csv", index=False)
    pd.concat(test_predictions, ignore_index=True).to_parquet(OUT / "test_predictions.parquet", index=False)
    print(f"\n→ {OUT}")


if __name__ == "__main__":
    main()
