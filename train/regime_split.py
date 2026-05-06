#!/usr/bin/env python3
"""Round 7 — Pre-/Post-COVID regime split for the influenceable-only Model 2.

Walk-forward results showed a sharp regime shift around 2020:
    F1-F4 (test 2016-2020): AUC 0.81-0.85, AP 0.13-0.16
    F5-F8 (test 2020-2024): AUC 0.71-0.78, AP 0.08-0.16

This script formally documents that shift by training two SEPARATE Model 2
variants on disjoint pre- and post-COVID windows and comparing top features,
SSBCI signal, and branch-access importance side by side.

Study 1 — Pre-COVID:
    train 2009-2017, val 2018, test 2018-2019
Study 2 — Post-COVID:
    train 2020-2021, val 2022, test 2023-2024

Same XGBoost hyperparameters, isotonic calibration, and territory exclusion as
walk_forward_round7.py. Same INFLUENCEABLE_FEATURES whitelist.
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

from _horizon_config import HORIZON, TARGET, precovid_postcovid_splits  # noqa: E402

OUT = ROOT / "diagnostics" / f"round7_regime_split_h{HORIZON}"
OUT.mkdir(parents=True, exist_ok=True)


# Canonical influenceable feature list — must match walk_forward_round7.py.
INFLUENCEABLE_FEATURES = [
    # Tier 1 — CRA, residualized against n_cra_lenders to break leakage
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
]

# Two regime studies, horizon-aware.
#   (label, train_start, train_end, val_year, test_start, test_end)
_pre, _post = precovid_postcovid_splits(HORIZON)
STUDIES = [
    ("precovid", _pre[0][0], _pre[0][1], _pre[1], _pre[2][0], _pre[2][1]),
    ("postcovid", _post[0][0], _post[0][1], _post[1], _post[2][0], _post[2][1]),
]


def evaluate(y_true: np.ndarray, y_prob: np.ndarray) -> dict:
    """Standard metric bundle, NaN-safe when only one class present."""
    if len(np.unique(y_true)) < 2:
        return {
            "auc": float("nan"), "ap": float("nan"),
            "ap_lift": float("nan"), "brier": float("nan"),
            "n": len(y_true), "pos_rate": float(y_true.mean()),
        }
    auc = roc_auc_score(y_true, y_prob)
    ap = average_precision_score(y_true, y_prob)
    pos_rate = y_true.mean()
    return {
        "auc": float(auc),
        "ap": float(ap),
        "ap_lift": float(ap / pos_rate) if pos_rate > 0 else float("nan"),
        "brier": float(brier_score_loss(y_true, y_prob)),
        "n": len(y_true),
        "pos_rate": float(pos_rate),
    }


def make_model() -> xgb.XGBClassifier:
    """Identical hyperparameters to walk_forward_round7.py."""
    return xgb.XGBClassifier(
        n_estimators=400, max_depth=6, learning_rate=0.05,
        subsample=0.85, colsample_bytree=0.85,
        min_child_weight=5, reg_lambda=1.0,
        tree_method="hist", objective="binary:logistic",
        eval_metric="aucpr", early_stopping_rounds=25,
        random_state=42, verbosity=0,
    )


def run_study(label: str, df: pd.DataFrame, feat_cols: list[str],
              tr_s: int, tr_e: int, val_y: int,
              te_s: int, te_e: int) -> dict:
    train = df[(df["year"] >= tr_s) & (df["year"] <= tr_e)]
    val = df[df["year"] == val_y]
    test = df[(df["year"] >= te_s) & (df["year"] <= te_e)]

    if len(train) == 0 or len(val) == 0 or len(test) == 0:
        raise SystemExit(
            f"{label}: empty split — train={len(train)} val={len(val)} test={len(test)}"
        )

    X_tr, y_tr = train[feat_cols], train[TARGET].values
    X_val, y_val = val[feat_cols], val[TARGET].values
    X_te, y_te = test[feat_cols], test[TARGET].values

    print(f"\n[{label}] train {tr_s}-{tr_e} ({len(train):,}) | "
          f"val {val_y} ({len(val):,}) | test {te_s}-{te_e} ({len(test):,})")
    print(f"  pos rate: train={y_tr.mean()*100:.2f}%  "
          f"val={y_val.mean()*100:.2f}%  test={y_te.mean()*100:.2f}%")

    model = make_model()
    model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)

    val_prob = model.predict_proba(X_val)[:, 1]
    test_prob = model.predict_proba(X_te)[:, 1]

    cal = IsotonicRegression(out_of_bounds="clip")
    cal.fit(val_prob, y_val)
    test_prob_calibrated = cal.transform(test_prob)

    val_metrics = evaluate(y_val, val_prob)
    test_raw = evaluate(y_te, test_prob)
    test_cal = evaluate(y_te, test_prob_calibrated)

    print(f"  VAL  AUC={val_metrics['auc']:.4f}  AP={val_metrics['ap']:.4f}")
    print(f"  TEST raw       AUC={test_raw['auc']:.4f}  AP={test_raw['ap']:.4f}  "
          f"lift={test_raw['ap_lift']:.2f}x  Brier={test_raw['brier']:.4f}")
    print(f"  TEST calibrated AUC={test_cal['auc']:.4f}  AP={test_cal['ap']:.4f}  "
          f"Brier={test_cal['brier']:.4f}")

    # Persist metrics table.
    metrics_row = {
        "regime": label,
        "train_years": f"{tr_s}-{tr_e}",
        "val_year": val_y,
        "test_years": f"{te_s}-{te_e}",
        "n_train": len(train),
        "n_val": len(val),
        "n_test": len(test),
        "best_iter": model.best_iteration,
        "val_auc": val_metrics["auc"],
        "val_ap": val_metrics["ap"],
        "test_auc": test_raw["auc"],
        "test_ap": test_raw["ap"],
        "test_ap_lift": test_raw["ap_lift"],
        "test_brier_raw": test_raw["brier"],
        "test_brier_calibrated": test_cal["brier"],
        "test_pos_rate": test_raw["pos_rate"],
    }
    pd.DataFrame([metrics_row]).to_csv(OUT / f"{label}_metrics.csv", index=False)

    # Feature importance, sorted descending.
    imp = pd.DataFrame({
        "feature": feat_cols,
        "importance": model.feature_importances_,
        "regime": label,
    }).sort_values("importance", ascending=False).reset_index(drop=True)
    imp["rank"] = imp.index + 1
    imp.to_csv(OUT / f"{label}_feature_importance.csv", index=False)

    # Test predictions.
    pred_df = test[["tract_fips", "county_fips", "year"]].copy()
    pred_df["regime"] = label
    pred_df["y_true"] = y_te
    pred_df["y_prob"] = test_prob
    pred_df["y_prob_calibrated"] = test_prob_calibrated
    pred_df.to_parquet(OUT / f"{label}_test_predictions.parquet", index=False)

    return {
        "label": label,
        "metrics_row": metrics_row,
        "importance": imp,
    }


def main() -> None:
    print(f"Loading {PANEL.name}…")
    df = pd.read_parquet(PANEL)
    df = df[df[TARGET].notna()].copy()
    df[TARGET] = df[TARGET].astype(int)

    # Drop territories — match walk_forward_round7.py.
    df["state_fips"] = df["tract_fips"].str[:2]
    territory_mask = df["state_fips"].isin({"72", "78", "60", "66", "69"})
    df = df[~territory_mask].copy()
    print(f"  rows: {len(df):,}  positive rate: {df[TARGET].mean()*100:.2f}%")

    feat_cols = [c for c in INFLUENCEABLE_FEATURES if c in df.columns]
    missing = sorted(set(INFLUENCEABLE_FEATURES) - set(feat_cols))
    if missing:
        print(f"  WARNING: missing features dropped: {missing}")
    if not feat_cols:
        raise SystemExit("ERROR: no influenceable features found in panel.")
    print(f"  features ({len(feat_cols)}): {feat_cols}")

    studies = []
    for label, tr_s, tr_e, val_y, te_s, te_e in STUDIES:
        studies.append(run_study(label, df, feat_cols, tr_s, tr_e, val_y, te_s, te_e))

    # Side-by-side comparison.
    comp_rows = []
    for s in studies:
        m = s["metrics_row"]
        comp_rows.append({
            "regime": m["regime"],
            "train_years": m["train_years"],
            "test_years": m["test_years"],
            "n_test": m["n_test"],
            "test_pos_rate": m["test_pos_rate"],
            "test_auc": m["test_auc"],
            "test_ap": m["test_ap"],
            "test_ap_lift": m["test_ap_lift"],
            "test_brier_calibrated": m["test_brier_calibrated"],
        })
    comp_df = pd.DataFrame(comp_rows)
    comp_df.to_csv(OUT / "regime_comparison.csv", index=False)

    print(f"\n{'='*80}\nROUND 7 — Pre/Post-COVID regime comparison\n{'='*80}")
    print(comp_df.to_string(index=False, float_format="%.4f"))

    # Top-feature side-by-side print.
    print("\nTop 5 features per regime:")
    for s in studies:
        print(f"\n  [{s['label']}]")
        top = s["importance"].head(5)[["rank", "feature", "importance"]]
        print(top.to_string(index=False, float_format="%.4f"))

    print(f"\n→ {OUT}")


if __name__ == "__main__":
    main()
