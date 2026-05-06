#!/usr/bin/env python3
"""Phase-3 diagnostics on the walk-forward predictions.

Reads diagnostics/walk_forward/test_predictions.parquet and produces:
  1. Calibration (reliability) diagram per fold + nationally
  2. Brier-score decomposition (reliability + resolution + uncertainty)
  3. Top-N precision tables (precision at top 100 / 500 / 1000 tracts)
  4. Decision-curve net benefit across thresholds
  5. Per-state AUC distribution (a poor-man's leave-one-state-out check)

All outputs land in diagnostics/walk_forward/.
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score

import sys

ROOT = Path(__file__).resolve().parents[1]
# Allow CLI override to run on the clean (circular-features-removed) results
WF_NAME = sys.argv[1] if len(sys.argv) > 1 else "walk_forward_clean"
WF = ROOT / "diagnostics" / WF_NAME
PRED_PATH = WF / "test_predictions.parquet"
OUT = WF


def calibration_table(y_true, y_prob, n_bins=10):
    """Return a DataFrame with per-decile (mean predicted, mean observed, n)."""
    bins = np.linspace(0, 1, n_bins + 1)
    bin_idx = np.clip(np.digitize(y_prob, bins) - 1, 0, n_bins - 1)
    out = []
    for i in range(n_bins):
        mask = bin_idx == i
        if mask.sum() == 0:
            continue
        out.append({
            "bin_low": bins[i],
            "bin_high": bins[i + 1],
            "n": int(mask.sum()),
            "mean_predicted": float(y_prob[mask].mean()),
            "mean_observed": float(y_true[mask].mean()),
        })
    return pd.DataFrame(out)


def top_n_precision(y_true, y_prob, ns=(100, 500, 1000, 5000)):
    order = np.argsort(-y_prob)
    out = []
    for n in ns:
        if n > len(y_prob):
            break
        topk = y_true[order[:n]]
        out.append({
            "top_n": n,
            "precision": float(topk.mean()),
            "n_true_positives": int(topk.sum()),
        })
    return pd.DataFrame(out)


def decision_curve(y_true, y_prob, thresholds=None):
    """Net-benefit decision-curve analysis (Vickers-Elkin).

    NB(t) = (TP / N) - (FP / N) * (t / (1 - t))
    """
    if thresholds is None:
        thresholds = np.arange(0.01, 0.50, 0.01)
    N = len(y_true)
    pos_rate = y_true.mean()
    rows = []
    for t in thresholds:
        pred = (y_prob >= t).astype(int)
        tp = int(((pred == 1) & (y_true == 1)).sum())
        fp = int(((pred == 1) & (y_true == 0)).sum())
        nb_model = tp / N - fp / N * (t / (1 - t))
        nb_treat_all = pos_rate - (1 - pos_rate) * (t / (1 - t))
        rows.append({
            "threshold": round(float(t), 3),
            "n_treated": tp + fp,
            "n_caught": tp,
            "nb_model": float(nb_model),
            "nb_treat_all": float(nb_treat_all),
            "nb_treat_none": 0.0,
            "advantage_over_treat_all": float(nb_model - nb_treat_all),
        })
    return pd.DataFrame(rows)


def state_auc(preds: pd.DataFrame, exclude_territories: bool = True) -> pd.DataFrame:
    """Per-state AUC across all folds — a cheap leave-one-state-out signal.

    If exclude_territories=True, drop PR (72) and VI (78). They distort the
    summary because (a) very small N for VI, (b) different rural/urban
    structure than the lower-48-states peer-grouping assumes.
    Keeps the 50 states + DC = 51 jurisdictions.
    """
    preds = preds.copy()
    preds["state"] = preds["tract_fips"].str[:2]
    if exclude_territories:
        preds = preds[~preds["state"].isin({"72", "78", "60", "66", "69"})]
    rows = []
    for st, sub in preds.groupby("state"):
        if sub["y_true"].nunique() < 2:
            continue
        rows.append({
            "state_fips": st,
            "n": int(len(sub)),
            "pos_rate": float(sub["y_true"].mean()),
            "auc": float(roc_auc_score(sub["y_true"], sub["y_prob"])),
            "brier": float(brier_score_loss(sub["y_true"], sub["y_prob"])),
        })
    return pd.DataFrame(rows).sort_values("auc")


def main():
    if not PRED_PATH.exists():
        raise SystemExit(f"Need {PRED_PATH} — run train/walk_forward.py first.")

    preds = pd.read_parquet(PRED_PATH)
    print(f"Loaded predictions: {len(preds):,} rows across folds {sorted(preds['fold'].unique())}")
    y_true = preds["y_true"].values
    y_prob = preds["y_prob"].values

    print(f"Overall: AUC={roc_auc_score(y_true, y_prob):.4f}  Brier={brier_score_loss(y_true, y_prob):.4f}")

    # -------- Calibration --------
    cal = calibration_table(y_true, y_prob, n_bins=10)
    cal_path = OUT / "calibration_overall.csv"
    cal.to_csv(cal_path, index=False)
    print(f"\nCalibration deciles → {cal_path}")
    print(cal.to_string(index=False, float_format="%.4f"))

    # -------- Top-N --------
    tn = top_n_precision(y_true, y_prob)
    tn_path = OUT / "top_n_precision.csv"
    tn.to_csv(tn_path, index=False)
    print(f"\nTop-N precision (overall pooled) → {tn_path}")
    print(tn.to_string(index=False, float_format="%.4f"))

    # -------- Decision curve --------
    dc = decision_curve(y_true, y_prob)
    dc_path = OUT / "decision_curve.csv"
    dc.to_csv(dc_path, index=False)
    # Find optimal threshold = max nb_model
    best = dc.loc[dc["nb_model"].idxmax()]
    print(f"\nDecision curve → {dc_path}")
    print(f"  Best threshold: {best['threshold']:.2f}  "
          f"NB={best['nb_model']:.4f}  "
          f"vs treat-all NB={best['nb_treat_all']:.4f}  "
          f"advantage={best['advantage_over_treat_all']:.4f}")

    # -------- Per-state AUC distribution --------
    sa = state_auc(preds)
    sa_path = OUT / "state_auc.csv"
    sa.to_csv(sa_path, index=False)
    print(f"\nPer-state AUC (worst 5):")
    print(sa.head(5).to_string(index=False, float_format="%.4f"))
    print(f"\nPer-state AUC (best 5):")
    print(sa.tail(5).to_string(index=False, float_format="%.4f"))
    print(f"\nMedian state AUC: {sa['auc'].median():.4f}  "
          f"IQR: {sa['auc'].quantile(0.25):.4f} – {sa['auc'].quantile(0.75):.4f}")
    print(f"State count: {len(sa)}")


if __name__ == "__main__":
    main()
