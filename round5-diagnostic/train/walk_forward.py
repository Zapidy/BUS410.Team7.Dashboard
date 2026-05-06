#!/usr/bin/env python3
"""Walk-forward credit-desert prediction trainer for Round 5.

Trains XGBoost across 8 expanding-window folds covering 2009–2024.
Per fold: train on years up to T, validate on T+1, test on T+2..T+3 (clamped
to data availability). Reports AUC + AP + Brier per fold, and the mean ± std
distribution at the end. Also dumps per-tract predictions for downstream
calibration / decision-curve / map work.

This is an INITIAL pipeline — meant to be run end-to-end so we can see how
the model behaves on the new panel before tuning. For a target horizon of
H1 (1-year ahead), runs in ~2-3 minutes total on a laptop.
"""
from __future__ import annotations
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)

warnings.filterwarnings("ignore", category=UserWarning)

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data" / "processed" / "panel" / "tract_year_with_target.parquet"
OUT = ROOT / "diagnostics" / "walk_forward"
OUT.mkdir(parents=True, exist_ok=True)

# ---------- Fold definitions (expanding-window, walk-forward by year) ----------
FOLDS = [
    # name, train_start, train_end, val_year, test_start, test_end
    ("F1", 2009, 2014, 2015, 2016, 2018),
    ("F2", 2009, 2015, 2016, 2017, 2019),
    ("F3", 2009, 2016, 2017, 2018, 2020),
    ("F4", 2009, 2017, 2018, 2019, 2021),
    ("F5", 2009, 2018, 2019, 2020, 2022),
    ("F6", 2009, 2019, 2020, 2021, 2023),
    ("F7", 2009, 2020, 2021, 2022, 2024),
    ("F8", 2009, 2021, 2022, 2023, 2024),
]

# ---------- Columns to drop (identifiers + sentinels + targets) ----------
DROP_COLS = {
    "tract_fips", "county_fips", "peer_group", "service_desert_threshold",
    "service_peer_median", "origination_desert_threshold",
    "originations_per_1k", "service_desert_score", "origination_desert_score",
    "is_service_desert", "is_origination_desert", "is_any_desert",
    "vintage", "acs_vintage_used",
    # All forward-target labels (we pick one as y)
    "target_service_desert_h1", "target_service_desert_h2", "target_service_desert_h3",
    "target_any_desert_h1", "target_any_desert_h2", "target_any_desert_h3",
    "target_becomes_service_desert_h1", "target_becomes_service_desert_h2",
    "target_becomes_service_desert_h3",
    "target_becomes_any_desert_h1", "target_becomes_any_desert_h2",
    "target_becomes_any_desert_h3",
}

# Configurable target. Default is the TRANSITION target (becomes a desert),
# which removes the autocorrelation leakage from the STATE target.
TARGET = "target_becomes_service_desert_h1"


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce numeric, fill HMDA NaN for pre-2018 with 0 (since has_hmda tracks it)."""
    feats = df.drop(columns=[c for c in DROP_COLS if c in df.columns], errors="ignore")
    keep = [c for c in feats.columns if c != "year"]
    feats = feats[["year"] + keep]
    # Numeric coercion
    for col in feats.columns:
        if feats[col].dtype == object:
            feats[col] = pd.to_numeric(feats[col], errors="coerce")
    # Pre-2018 HMDA columns expected NaN; fill 0 (the has_hmda flag tells the model)
    hmda_cols = [c for c in feats.columns
                 if c in {"n_applications", "n_originated", "n_denied", "n_withdrawn",
                          "n_purchased", "approval_rate", "denial_rate",
                          "sum_loan_amount", "mean_loan_amount", "n_distinct_lenders",
                          "n_white", "n_black", "n_asian", "n_hispanic", "n_other_race"}]
    feats[hmda_cols] = feats[hmda_cols].fillna(0)
    return feats


def evaluate(y_true: np.ndarray, y_prob: np.ndarray) -> dict:
    if len(np.unique(y_true)) < 2:
        return {"n": len(y_true), "pos_rate": float(y_true.mean()),
                "auc": float("nan"), "ap": float("nan"),
                "ap_lift": float("nan"), "brier": float("nan")}
    auc = roc_auc_score(y_true, y_prob)
    ap = average_precision_score(y_true, y_prob)
    pos_rate = y_true.mean()
    ap_lift = ap / pos_rate if pos_rate > 0 else float("nan")
    brier = brier_score_loss(y_true, y_prob)
    return {
        "n": len(y_true), "pos_rate": float(pos_rate),
        "auc": float(auc), "ap": float(ap),
        "ap_lift": float(ap_lift), "brier": float(brier),
    }


def main():
    print(f"Loading {PANEL.name}…")
    df = pd.read_parquet(PANEL)
    print(f"  Loaded: {df.shape}")

    df = df[df[TARGET].notna()].copy()
    df[TARGET] = df[TARGET].astype(int)
    print(f"  After dropping rows without {TARGET}: {df.shape}")
    print(f"  Overall positive rate: {df[TARGET].mean()*100:.2f}%")

    fold_results = []
    test_predictions = []

    for fold_name, tr_s, tr_e, val_y, te_s, te_e in FOLDS:
        train = df[(df["year"] >= tr_s) & (df["year"] <= tr_e)]
        val = df[df["year"] == val_y]
        test = df[(df["year"] >= te_s) & (df["year"] <= te_e)]

        if len(train) == 0 or len(val) == 0 or len(test) == 0:
            print(f"\n{fold_name}: SKIP (empty split)")
            continue

        X_tr = prepare_features(train).drop(columns=["year"])
        y_tr = train[TARGET].values
        X_val = prepare_features(val).drop(columns=["year"])
        y_val = val[TARGET].values
        X_te = prepare_features(test).drop(columns=["year"])
        y_te = test[TARGET].values

        # Align columns (in case some sources are missing in early years)
        common = sorted(set(X_tr.columns) & set(X_val.columns) & set(X_te.columns))
        X_tr = X_tr[common]
        X_val = X_val[common]
        X_te = X_te[common]

        print(f"\n{fold_name}: train {tr_s}-{tr_e} ({len(train):,}) | "
              f"val {val_y} ({len(val):,}) | test {te_s}-{te_e} ({len(test):,})")
        print(f"  features: {len(common)}")
        print(f"  pos rate: train={y_tr.mean()*100:.1f}%  val={y_val.mean()*100:.1f}%  test={y_te.mean()*100:.1f}%")

        model = xgb.XGBClassifier(
            n_estimators=400,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.85,
            colsample_bytree=0.85,
            min_child_weight=5,
            reg_lambda=1.0,
            tree_method="hist",
            objective="binary:logistic",
            eval_metric="aucpr",
            early_stopping_rounds=25,
            random_state=42,
            verbosity=0,
        )
        model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)

        val_prob = model.predict_proba(X_val)[:, 1]
        test_prob = model.predict_proba(X_te)[:, 1]

        val_metrics = evaluate(y_val, val_prob)
        test_metrics = evaluate(y_te, test_prob)
        print(f"  VAL  AUC={val_metrics['auc']:.4f}  AP={val_metrics['ap']:.4f}  AP-lift={val_metrics['ap_lift']:.2f}x")
        print(f"  TEST AUC={test_metrics['auc']:.4f}  AP={test_metrics['ap']:.4f}  AP-lift={test_metrics['ap_lift']:.2f}x")

        fold_results.append({
            "fold": fold_name,
            "train_years": f"{tr_s}-{tr_e}",
            "val_year": val_y,
            "test_years": f"{te_s}-{te_e}",
            "n_train": len(train),
            "n_val": len(val),
            "n_test": len(test),
            "best_iter": model.best_iteration,
            "val_auc": val_metrics["auc"],
            "val_ap": val_metrics["ap"],
            "test_auc": test_metrics["auc"],
            "test_ap": test_metrics["ap"],
            "test_ap_lift": test_metrics["ap_lift"],
            "test_brier": test_metrics["brier"],
            "test_pos_rate": test_metrics["pos_rate"],
        })

        # Save predictions for downstream analysis
        pred_df = test[["tract_fips", "county_fips", "year"]].copy()
        pred_df["fold"] = fold_name
        pred_df["y_true"] = y_te
        pred_df["y_prob"] = test_prob
        test_predictions.append(pred_df)

    # ---- Summary ----
    if not fold_results:
        print("\nNo successful folds.")
        return

    res_df = pd.DataFrame(fold_results)
    print(f"\n{'='*80}\nFold summary\n{'='*80}")
    print(res_df[["fold", "train_years", "test_years", "n_test", "test_auc",
                  "test_ap", "test_ap_lift", "test_brier"]].to_string(index=False,
                                                                       float_format="%.4f"))
    print(f"\nMean test AUC: {res_df['test_auc'].mean():.4f}  ± {res_df['test_auc'].std():.4f}")
    print(f"Mean test AP:  {res_df['test_ap'].mean():.4f}")
    print(f"Mean AP-lift:  {res_df['test_ap_lift'].mean():.2f}x")

    res_df.to_csv(OUT / "fold_results.csv", index=False)
    pd.concat(test_predictions, ignore_index=True).to_parquet(OUT / "test_predictions.parquet", index=False)
    print(f"\n→ {OUT / 'fold_results.csv'}")
    print(f"→ {OUT / 'test_predictions.parquet'}")


if __name__ == "__main__":
    main()
