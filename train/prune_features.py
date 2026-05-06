#!/usr/bin/env python3
"""Block-of-clay feature pruning: minimum features × maximum AUC.

Strategy (pragmatic — keeps runtime ~30 min):
    1. Read fold-level feature importances from the just-completed Phase A run
       (`diagnostics/round7_phaseA/feature_importance_F*.csv`).
    2. Average XGBoost gain importance across all 8 folds → master ranking.
    3. For k in {3, 5, 7, 10, 14, 18, 22, ALL}: re-run walk-forward training
       using only the top-k features by aggregated importance.
    4. Record mean test AUC, AP, and AP-lift per k.
    5. Identify the elbow — smallest k with AP within 5% of the all-features AP.

Output:
    diagnostics/round7_pruned/sweep_results.csv
    diagnostics/round7_pruned/feature_ranking.csv

Notes:
    - Drops `n_cra_lenders` and `n_active_lenders_tract` from candidate features.
    - At each k step, we re-train ALL 8 folds — gives true walk-forward AP not
      just a single-fold AP.
    - This is the prune-and-retrain approach (not retrain-once-and-permute) —
      slower but gives an honest answer: at each k we let XGBoost re-fit with
      the smaller feature set. This catches cases where dropping a leakage-
      vulnerable concentration feature actually IMPROVES AP.
"""
from __future__ import annotations
import warnings
from pathlib import Path
from time import time

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
import os
from _horizon_config import HORIZON, TARGET, FOLDS  # noqa: E402

PHASEA = ROOT / "diagnostics" / os.environ.get("ROUND7_PRUNE_SOURCE", f"round7_phaseA_h{HORIZON}")
OUT = ROOT / "diagnostics" / os.environ.get("ROUND7_PRUNE_OUT", f"round7_pruned_h{HORIZON}")
OUT.mkdir(parents=True, exist_ok=True)

EXCLUDE = {
    "tract_fips", "county_fips", "state_fips", "year",
    TARGET, "n_cra_lenders", "n_active_lenders_tract", "n_active_lenders",
    "is_rural", "era_label",
    "is_service_desert", "is_origination_desert", "is_any_desert",
}

K_VALUES = [3, 5, 7, 10, 14, 18, 22, None]  # None = all features


def aggregate_feature_ranking(phaseA_dir: Path) -> pd.DataFrame:
    """Average XGBoost gain importance across all 8 fold importance files."""
    parts = []
    for p in sorted(phaseA_dir.glob("feature_importance_F*.csv")):
        df = pd.read_csv(p)
        parts.append(df)
    if not parts:
        raise SystemExit(f"No feature_importance_F*.csv in {phaseA_dir}")
    full = pd.concat(parts, ignore_index=True)
    agg = (
        full.groupby("feature", as_index=False)["importance"]
        .agg(mean_importance="mean", std_importance="std")
        .sort_values("mean_importance", ascending=False)
        .reset_index(drop=True)
    )
    return agg


def train_walk_forward(df: pd.DataFrame, feat_cols: list[str]) -> pd.DataFrame:
    """Run all 8 folds with the given feature subset; return per-fold metrics."""
    rows = []
    for fold_name, tr_s, tr_e, val_y, te_s, te_e in FOLDS:
        train = df[(df["year"] >= tr_s) & (df["year"] <= tr_e)]
        val = df[df["year"] == val_y]
        test = df[(df["year"] >= te_s) & (df["year"] <= te_e)]
        if len(train) == 0 or len(val) == 0 or len(test) == 0:
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
        test_prob_cal = cal.transform(test_prob)

        if len(np.unique(y_te)) >= 2:
            rows.append({
                "fold": fold_name,
                "test_auc": roc_auc_score(y_te, test_prob_cal),
                "test_ap": average_precision_score(y_te, test_prob_cal),
                "test_pos_rate": float(y_te.mean()),
                "test_brier": brier_score_loss(y_te, test_prob_cal),
            })
    return pd.DataFrame(rows)


def main():
    print(f"Loading panel from {PANEL}…")
    df = pd.read_parquet(PANEL)
    df = df[df[TARGET].notna()].copy()
    df[TARGET] = df[TARGET].astype(int)
    df["state_fips"] = df["tract_fips"].str[:2]
    df = df[~df["state_fips"].isin({"72", "78", "60", "66", "69"})].copy()
    print(f"  rows: {len(df):,}  positive rate: {df[TARGET].mean()*100:.2f}%")

    print(f"\nAggregating feature ranking from {PHASEA}…")
    ranking = aggregate_feature_ranking(PHASEA)
    ranking.to_csv(OUT / "feature_ranking.csv", index=False)
    print(ranking.to_string(index=False, float_format="%.4f"))

    sweep_rows = []
    full_features = ranking["feature"].tolist()
    full_features = [f for f in full_features if f in df.columns and f not in EXCLUDE]
    print(f"\nFull candidate set: {len(full_features)} features")

    for k in K_VALUES:
        feat_cols = full_features if k is None else full_features[:k]
        feat_cols = [f for f in feat_cols if f in df.columns]
        n = len(feat_cols)

        t0 = time()
        results = train_walk_forward(df, feat_cols)
        elapsed = time() - t0

        if results.empty:
            continue

        mean_auc = results["test_auc"].mean()
        std_auc = results["test_auc"].std()
        mean_ap = results["test_ap"].mean()
        n_folds_above_010 = (results["test_ap"] >= 0.10).sum()

        print(f"\nk={n:>3}  mean AUC={mean_auc:.4f}  AP={mean_ap:.4f}  "
              f"std={std_auc:.4f}  folds≥0.10AP={n_folds_above_010}/8  ({elapsed:.0f}s)")
        for _, r in results.iterrows():
            print(f"    {r['fold']}  AUC={r['test_auc']:.4f}  AP={r['test_ap']:.4f}")

        sweep_rows.append({
            "k": n,
            "mean_test_auc": mean_auc,
            "std_test_auc": std_auc,
            "mean_test_ap": mean_ap,
            "n_folds_at_or_above_ap_010": n_folds_above_010,
            "features": ",".join(feat_cols),
        })

    sweep = pd.DataFrame(sweep_rows)
    sweep.to_csv(OUT / "sweep_results.csv", index=False)

    # Find elbow: smallest k where mean_ap is within 5% of the all-features mean_ap
    full_ap = sweep[sweep["k"] == sweep["k"].max()]["mean_test_ap"].iloc[0]
    target_ap = full_ap * 0.95
    candidates = sweep[sweep["mean_test_ap"] >= target_ap].sort_values("k")
    if not candidates.empty:
        elbow = candidates.iloc[0]
        print(f"\n{'='*70}")
        print(f"ELBOW: k={int(elbow['k'])} achieves AP={elbow['mean_test_ap']:.4f} "
              f"(target ≥ {target_ap:.4f}, full-set AP={full_ap:.4f})")
        print(f"Features at elbow:")
        for f in elbow['features'].split(","):
            print(f"  - {f}")

    print(f"\n→ {OUT}")


if __name__ == "__main__":
    main()
