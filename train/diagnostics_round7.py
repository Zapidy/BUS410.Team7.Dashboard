#!/usr/bin/env python3
"""Round 7 diagnostics — partial dependence, directional sanity, per-fold
stability, per-state AP.

Usage:
    python3 diagnostics_round7.py round7_phaseA            (default)
    python3 diagnostics_round7.py round7_bolton

Inputs:
    diagnostics/{run_name}/test_predictions.parquet
    diagnostics/{run_name}/fold_results.csv
    diagnostics/{run_name}/feature_importance_*.csv  (Phase A only)
    data/processed/panel/tract_year_with_target_round7.parquet

Outputs:
    diagnostics/{run_name}/diag_per_state_ap.csv
    diagnostics/{run_name}/diag_per_fold_stability.csv
    diagnostics/{run_name}/diag_pdp/*.csv               (one per feature)
    diagnostics/{run_name}/diag_directional_sanity.csv
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.inspection import partial_dependence
from sklearn.metrics import average_precision_score

warnings.filterwarnings("ignore", category=UserWarning)

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data" / "processed" / "panel" / "tract_year_with_target_round7.parquet"
from _horizon_config import HORIZON, TARGET, FOLDS


DIRECTIONAL_EXPECTATIONS = {
    "pct_loans_from_community_banks": "down",
    "pct_loans_from_top4_banks": "up",
    "pct_loans_under_100k": "down",
    "pct_loans_under_250k": "down",
    "top1_lender_share_tract": "up",
    "top3_lender_share_tract": "up",
    "lender_hhi_tract": "up",
    "distance_to_nearest_bank_branch": "up",
    "branches_within_5mi": "down",
    "branch_closures_3y_within_10mi": "up",
    "pct_loans_from_credit_unions": "down",
    "cdfi_within_10mi": "down",
    "mdi_branches_within_10mi": "down",
    "microloan_intermediary_within_25mi": "down",
}


def per_fold_stability(fold_results: pd.DataFrame) -> pd.DataFrame:
    if "test_auc" not in fold_results.columns:
        return pd.DataFrame()
    summary = pd.DataFrame({
        "n_folds": [len(fold_results)],
        "mean_test_auc": [fold_results["test_auc"].mean()],
        "std_test_auc": [fold_results["test_auc"].std()],
        "mean_test_ap": [fold_results["test_ap"].mean()],
        "std_test_ap": [fold_results["test_ap"].std()],
        "min_fold_auc": [fold_results["test_auc"].min()],
        "max_fold_auc": [fold_results["test_auc"].max()],
        "fold_at_min": [fold_results.loc[fold_results["test_auc"].idxmin(), "fold"]],
        "stability_flag": [
            "FLAGGED (std > 0.06)" if fold_results["test_auc"].std() > 0.06 else "OK"
        ],
    })
    return summary


def per_state_ap(predictions: pd.DataFrame) -> pd.DataFrame:
    df = predictions.copy()
    df["state_fips"] = df["tract_fips"].astype(str).str[:2]
    out = []
    for state, sub in df.groupby("state_fips"):
        if len(sub) < 100:
            continue
        if sub["y_true"].nunique() < 2:
            continue
        prob_col = "y_prob_calibrated" if "y_prob_calibrated" in sub.columns else "y_prob_bolton"
        ap = average_precision_score(sub["y_true"], sub[prob_col])
        pos_rate = sub["y_true"].mean()
        out.append({
            "state_fips": state,
            "n_obs": len(sub),
            "ap": ap,
            "pos_rate": pos_rate,
            "lift": ap / pos_rate if pos_rate > 0 else float("nan"),
            "below_random_flag": "FLAGGED" if ap < pos_rate else "OK",
        })
    return pd.DataFrame(out).sort_values("ap")


def directional_sanity(model, X_sample, feat_cols) -> pd.DataFrame:
    rows = []
    for feat in feat_cols:
        if feat not in DIRECTIONAL_EXPECTATIONS:
            continue
        try:
            pd_result = partial_dependence(
                model, X_sample, [feat], grid_resolution=20, kind="average",
            )
            # sklearn ≥1.5 renamed `values` to `grid_values`
            grid_key = "grid_values" if "grid_values" in pd_result else "values"
            grid = pd_result[grid_key][0]
            avg = pd_result["average"][0]
            slope = float(np.polyfit(grid, avg, 1)[0])
            actual = "up" if slope > 0 else "down"
            expected = DIRECTIONAL_EXPECTATIONS[feat]
            rows.append({
                "feature": feat,
                "expected_direction": expected,
                "observed_direction": actual,
                "slope": slope,
                "match": expected == actual,
            })
        except Exception as e:
            rows.append({
                "feature": feat,
                "expected_direction": DIRECTIONAL_EXPECTATIONS[feat],
                "observed_direction": "",
                "slope": float("nan"),
                "match": False,
                "error": str(e),
            })
    return pd.DataFrame(rows)


def main():
    run_name = sys.argv[1] if len(sys.argv) > 1 else "round7_phaseA"
    diag = ROOT / "diagnostics" / run_name
    pred_path = diag / "test_predictions.parquet"
    fold_path = diag / "fold_results.csv"

    if not pred_path.exists():
        raise SystemExit(f"Missing: {pred_path}")
    if not fold_path.exists():
        raise SystemExit(f"Missing: {fold_path}")

    print(f"Loading {pred_path}…")
    preds = pd.read_parquet(pred_path)
    folds = pd.read_csv(fold_path)

    print("\n--- Per-fold stability ---")
    stability = per_fold_stability(folds)
    print(stability.to_string(index=False, float_format="%.4f"))
    stability.to_csv(diag / "diag_per_fold_stability.csv", index=False)

    print("\n--- Per-state AP ---")
    state_ap = per_state_ap(preds)
    state_ap.to_csv(diag / "diag_per_state_ap.csv", index=False)
    print(f"  States below random: {(state_ap['below_random_flag']=='FLAGGED').sum()}")
    print(f"  Lowest AP: {state_ap.head(5).to_string(index=False, float_format='%.4f')}")

    if run_name == "round7_phaseA":
        # Re-train on the full train set (all years through 2022) once to compute PDPs
        print("\n--- Directional sanity (PDP-based) ---")
        df = pd.read_parquet(PANEL)
        df = df[df[TARGET].notna()].copy()
        df["state_fips"] = df["tract_fips"].astype(str).str[:2]
        df = df[~df["state_fips"].isin({"72", "78", "60", "66", "69"})]
        # Take fold 8's training set
        train = df[(df["year"] >= 2009) & (df["year"] <= 2021)]
        feat_cols = [c for c in DIRECTIONAL_EXPECTATIONS if c in train.columns]

        print(f"  Training fold-8 model on {len(train):,} rows × {len(feat_cols)} features…")
        model = xgb.XGBClassifier(
            n_estimators=200, max_depth=6, learning_rate=0.05,
            subsample=0.85, colsample_bytree=0.85,
            tree_method="hist", objective="binary:logistic",
            random_state=42, verbosity=0,
        )
        X_tr = train[feat_cols]
        y_tr = train[TARGET].astype(int).values
        model.fit(X_tr, y_tr)

        sample = X_tr.sample(n=min(5000, len(X_tr)), random_state=42)
        sanity = directional_sanity(model, sample, feat_cols)
        sanity.to_csv(diag / "diag_directional_sanity.csv", index=False)
        print(sanity.to_string(index=False, float_format="%.4f"))
        if "match" in sanity.columns:
            flips = sanity[sanity["match"] == False]
            if not flips.empty:
                print(f"\n  ⚠ {len(flips)} feature(s) with sign-flip — see diag_directional_sanity.csv")

    print(f"\n→ {diag}")


if __name__ == "__main__":
    main()
