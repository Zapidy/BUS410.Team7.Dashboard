#!/usr/bin/env python3
"""LightGBM + Optuna walk-forward — Stage 3 of the rebuild pipeline.

Two improvements over walk_forward_clean.py:

  1. Replace XGBoost with LightGBM. Same algorithm class (gradient-boosted
     decision trees), 2-3x faster on this size, slightly different
     histogram-based splitting that often gives marginal AUC gains.

  2. Optuna Bayesian hyperparameter search. Tune on F1's val window
     (year 2015 — earliest val so we don't peek at test years), then apply
     the best config to F2-F8. This avoids the leak of tuning per-fold on
     overlapping val years.

Tuning protocol:
  - Search space: max_depth, num_leaves, learning_rate, subsample, colsample,
    min_child_samples, reg_alpha, reg_lambda, n_estimators (with early stop).
  - 30 Optuna trials (Bayesian, TPE). Each trial fits LightGBM on F1's
    train (2009-2014), evaluates on F1's val (2015) using AUCPR.
  - Best params then refit and applied to F2-F8 walk-forward.

Expected: +0.005 to +0.020 AUC over un-tuned XGBoost (current 0.8494).
"""
from __future__ import annotations
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import lightgbm as lgb
import optuna
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)

warnings.filterwarnings("ignore", category=UserWarning)
optuna.logging.set_verbosity(optuna.logging.WARNING)

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data" / "processed" / "panel" / "tract_year_with_target.parquet"
OUT = ROOT / "diagnostics" / "walk_forward_lgbm_optuna"
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


FOLDS = [
    ("F1", 2009, 2014, 2015, 2016, 2018),
    ("F2", 2009, 2015, 2016, 2017, 2019),
    ("F3", 2009, 2016, 2017, 2018, 2020),
    ("F4", 2009, 2017, 2018, 2019, 2021),
    ("F5", 2009, 2018, 2019, 2020, 2022),
    ("F6", 2009, 2019, 2020, 2021, 2023),
    ("F7", 2009, 2020, 2021, 2022, 2024),
    ("F8", 2009, 2021, 2022, 2023, 2024),
]


def prepare(df):
    feats = df.drop(columns=[c for c in DROP_COLS if c in df.columns], errors="ignore")
    for col in feats.columns:
        if feats[col].dtype == object:
            feats[col] = pd.to_numeric(feats[col], errors="coerce")
    hmda_cols = [c for c in feats.columns if c in {
        "n_applications", "n_originated", "n_denied", "n_withdrawn", "n_purchased",
        "approval_rate", "denial_rate", "sum_loan_amount", "mean_loan_amount",
        "n_distinct_lenders", "n_white", "n_black", "n_asian", "n_hispanic", "n_other_race",
    }]
    feats[hmda_cols] = feats[hmda_cols].fillna(0)
    if "year" in feats.columns:
        feats = feats.drop(columns=["year"])
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


# ---------- Optuna objective on F1's train/val ----------
F1_TRAIN_START, F1_TRAIN_END = 2009, 2014
F1_VAL_YEAR = 2015

def make_objective(X_tr, y_tr, X_val, y_val):
    def objective(trial):
        params = {
            "objective": "binary",
            "metric": "average_precision",
            "boosting_type": "gbdt",
            "num_leaves": trial.suggest_int("num_leaves", 15, 127),
            "max_depth": trial.suggest_int("max_depth", 4, 10),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.10, log=True),
            "min_child_samples": trial.suggest_int("min_child_samples", 5, 100),
            "subsample": trial.suggest_float("subsample", 0.7, 1.0),
            "subsample_freq": 1,
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
            "verbose": -1,
            "random_state": 42,
            "n_jobs": -1,
        }
        n_estimators = trial.suggest_int("n_estimators", 100, 800)

        train_set = lgb.Dataset(X_tr, label=y_tr)
        val_set = lgb.Dataset(X_val, label=y_val, reference=train_set)
        model = lgb.train(
            params, train_set,
            num_boost_round=n_estimators,
            valid_sets=[val_set],
            callbacks=[lgb.early_stopping(stopping_rounds=25, verbose=False)],
        )
        pred = model.predict(X_val, num_iteration=model.best_iteration)
        return average_precision_score(y_val, pred)
    return objective


def main():
    print(f"Loading {PANEL.name}…")
    df = pd.read_parquet(PANEL)
    df = df[df[TARGET].notna()].copy()
    df[TARGET] = df[TARGET].astype(int)
    print(f"  Loaded: {df.shape}, target pos rate {df[TARGET].mean()*100:.2f}%")

    # Build the F1 tune set (no peeking at F2-F8)
    f1_train = df[df["year"].between(F1_TRAIN_START, F1_TRAIN_END)]
    f1_val = df[df["year"] == F1_VAL_YEAR]
    X_f1_tr = prepare(f1_train).values.astype(np.float32)
    y_f1_tr = f1_train[TARGET].values
    X_f1_va = prepare(f1_val).values.astype(np.float32)
    y_f1_va = f1_val[TARGET].values
    feature_names = list(prepare(f1_train).columns)
    print(f"  F1 tune set: train={len(f1_train):,}, val={len(f1_val):,}, features={len(feature_names)}")

    # ---- Optuna ----
    print("\nRunning Optuna (30 trials, TPE Bayesian search)…")
    study = optuna.create_study(direction="maximize",
                                sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(make_objective(X_f1_tr, y_f1_tr, X_f1_va, y_f1_va),
                   n_trials=30, show_progress_bar=False)
    best_params = study.best_params
    print(f"\nBest F1-val AP: {study.best_value:.4f}")
    print(f"Best params:")
    for k, v in best_params.items():
        print(f"  {k:>22s} = {v}")

    # Save tuning history
    trials_df = study.trials_dataframe()
    trials_df.to_csv(OUT / "optuna_trials.csv", index=False)

    # ---- Apply best params to all 8 folds ----
    print("\nWalk-forward with best params:")
    fold_results = []
    test_predictions = []
    for fold_name, tr_s, tr_e, val_y, te_s, te_e in FOLDS:
        train = df[df["year"].between(tr_s, tr_e)]
        val = df[df["year"] == val_y]
        test = df[df["year"].between(te_s, te_e)]
        if len(train) == 0 or len(test) == 0:
            continue

        X_tr = prepare(train).values.astype(np.float32)
        y_tr = train[TARGET].values
        X_val = prepare(val).values.astype(np.float32)
        y_val = val[TARGET].values
        X_te = prepare(test).values.astype(np.float32)
        y_te = test[TARGET].values

        params = {**best_params,
                  "objective": "binary", "metric": "average_precision",
                  "verbose": -1, "random_state": 42, "n_jobs": -1}
        n_est = params.pop("n_estimators", 400)

        train_set = lgb.Dataset(X_tr, label=y_tr)
        val_set = lgb.Dataset(X_val, label=y_val, reference=train_set)
        model = lgb.train(
            params, train_set,
            num_boost_round=n_est,
            valid_sets=[val_set],
            callbacks=[lgb.early_stopping(stopping_rounds=25, verbose=False)],
        )
        test_pred = model.predict(X_te, num_iteration=model.best_iteration)
        m = evaluate(y_te, test_pred)
        print(f"  {fold_name}: train {tr_s}-{tr_e} | test {te_s}-{te_e} | "
              f"AUC={m['auc']:.4f}  AP={m['ap']:.4f}  AP-lift={m['ap_lift']:.2f}x  "
              f"best_iter={model.best_iteration}")

        fold_results.append({
            "fold": fold_name, "train_years": f"{tr_s}-{tr_e}",
            "val_year": val_y, "test_years": f"{te_s}-{te_e}",
            "n_train": len(train), "n_test": len(test),
            "best_iter": model.best_iteration,
            "test_auc": m["auc"], "test_ap": m["ap"],
            "test_ap_lift": m["ap_lift"], "test_brier": m["brier"],
            "test_pos_rate": m["pos_rate"],
        })

        pred_df = test[["tract_fips", "county_fips", "year"]].copy()
        pred_df["fold"] = fold_name
        pred_df["y_true"] = y_te
        pred_df["y_prob"] = test_pred
        test_predictions.append(pred_df)

    # ---- Summary ----
    res_df = pd.DataFrame(fold_results)
    print(f"\n{'='*80}")
    print(f"LightGBM + Optuna fold summary")
    print(f"{'='*80}")
    print(res_df[["fold", "train_years", "test_years", "test_auc",
                  "test_ap", "test_ap_lift", "test_brier"]].to_string(
                      index=False, float_format="%.4f"))
    print(f"\nMean test AUC: {res_df['test_auc'].mean():.4f}  ± {res_df['test_auc'].std():.4f}")
    print(f"Mean test AP:  {res_df['test_ap'].mean():.4f}")
    print(f"Mean AP-lift:  {res_df['test_ap_lift'].mean():.2f}x")

    res_df.to_csv(OUT / "fold_results.csv", index=False)
    pd.concat(test_predictions, ignore_index=True).to_parquet(OUT / "test_predictions.parquet", index=False)
    pd.Series(best_params).to_csv(OUT / "best_params.csv", header=False)
    print(f"\n→ {OUT}")


if __name__ == "__main__":
    main()
