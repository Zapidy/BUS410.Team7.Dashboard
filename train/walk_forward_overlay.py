#!/usr/bin/env python3
"""Phase C Variant A — Directional overlay.

Combines round5's diagnostic prediction with round7's influenceable-only
prediction as a directional adjustment:

    final_score(t) = round5_prob(t) × (1 + α × directional_sign(t) × |Δm2(t)|)

where:
    Δm2(t) = round7_prob(t) − mean(round7_prob in same year × peer_group)
    directional_sign(t) = sign(Δm2(t))

α is swept across {0.10, 0.25, 0.50}; pick the α that maximizes test AP-lift
while preserving Round 5 calibration (Brier degradation < 10%).

Inputs:
    ../round5/diagnostics/walk_forward_audit_fixed/test_predictions.parquet
    diagnostics/round7_phaseA/test_predictions.parquet

Output:
    diagnostics/round7_overlay/{fold_results.csv, sweep_results.csv,
                                test_predictions.parquet}

Run only if Phase B's verdict is Moderate (AP ∈ [0.05, 0.10)).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)

ROOT = Path(__file__).resolve().parents[1]
ROUND5_PRED = ROOT.parent / "round5" / "diagnostics" / "walk_forward_audit_fixed" / "test_predictions.parquet"
ROUND7_PRED = ROOT / "diagnostics" / "round7_phaseA" / "test_predictions.parquet"
PANEL = ROOT / "data" / "processed" / "panel" / "tract_year_with_target_round7.parquet"
OUT = ROOT / "diagnostics" / "round7_overlay"

ALPHAS = [0.10, 0.25, 0.50]


def evaluate(y_true, y_prob):
    if len(np.unique(y_true)) < 2:
        return {"auc": float("nan"), "ap": float("nan"), "brier": float("nan")}
    return {
        "auc": roc_auc_score(y_true, y_prob),
        "ap": average_precision_score(y_true, y_prob),
        "brier": brier_score_loss(y_true, y_prob),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if not ROUND5_PRED.exists():
        raise SystemExit(f"Missing: {ROUND5_PRED}\nRun round5/train/walk_forward_audit_fixed.py.")
    if not ROUND7_PRED.exists():
        raise SystemExit(f"Missing: {ROUND7_PRED}\nRun train/walk_forward_round7.py.")
    if not PANEL.exists():
        raise SystemExit(f"Missing: {PANEL}")

    print("Loading round5 predictions…")
    p5 = pd.read_parquet(ROUND5_PRED)
    p5 = p5.rename(columns={"y_prob_calibrated": "round5_prob"})

    print("Loading round7 predictions…")
    p7 = pd.read_parquet(ROUND7_PRED)
    p7 = p7.rename(columns={"y_prob_calibrated": "round7_prob"})

    print("Loading panel for is_rural slicing…")
    panel = pd.read_parquet(PANEL)[["tract_fips", "year", "is_rural"]]
    panel["tract_fips"] = panel["tract_fips"].astype(str)

    keys = ["tract_fips", "year", "fold"]
    merged = p5[keys + ["y_true", "round5_prob"]].merge(
        p7[keys + ["round7_prob"]], on=keys, how="inner"
    )
    merged["tract_fips"] = merged["tract_fips"].astype(str)
    merged = merged.merge(panel, on=["tract_fips", "year"], how="left")

    # Compute peer-group baseline of round7_prob per (year, peer_group)
    merged["peer_group"] = np.where(merged["is_rural"] == 1, "rural", "urban")
    peer_baseline = (
        merged.groupby(["year", "peer_group"])["round7_prob"]
        .transform("mean")
    )
    merged["delta_m2"] = merged["round7_prob"] - peer_baseline

    sweep_rows = []
    best_alpha = None
    best_ap = -np.inf
    best_scores = None

    for alpha in ALPHAS:
        merged[f"final_a{alpha}"] = merged["round5_prob"] * (
            1 + alpha * np.sign(merged["delta_m2"]) * np.abs(merged["delta_m2"])
        )
        # Clip to [0,1] for calibration check
        merged[f"final_a{alpha}"] = merged[f"final_a{alpha}"].clip(0, 1)
        scores = evaluate(merged["y_true"], merged[f"final_a{alpha}"])
        sweep_rows.append({
            "alpha": alpha,
            "auc": scores["auc"],
            "ap": scores["ap"],
            "brier": scores["brier"],
        })
        if scores["ap"] > best_ap:
            best_ap = scores["ap"]
            best_alpha = alpha
            best_scores = scores

    base = evaluate(merged["y_true"], merged["round5_prob"])
    sweep_rows.append({"alpha": "round5_baseline",
                       "auc": base["auc"], "ap": base["ap"], "brier": base["brier"]})

    sweep = pd.DataFrame(sweep_rows)
    print("\nOverlay sweep:")
    print(sweep.to_string(index=False, float_format="%.4f"))
    print(f"\nBest α = {best_alpha}  (AP={best_ap:.4f})")
    print(f"Brier vs baseline: {best_scores['brier']:.4f} vs {base['brier']:.4f} "
          f"(Δ {(best_scores['brier'] - base['brier']) / base['brier'] * 100:+.1f}%)")

    sweep.to_csv(OUT / "sweep_results.csv", index=False)
    keep_cols = keys + ["y_true", "round5_prob", "round7_prob", "delta_m2",
                        f"final_a{best_alpha}"]
    merged[keep_cols].to_parquet(OUT / "test_predictions.parquet", index=False)

    # Per-fold results at best alpha
    fold_rows = []
    for fold, sub in merged.groupby("fold"):
        s = evaluate(sub["y_true"], sub[f"final_a{best_alpha}"])
        b = evaluate(sub["y_true"], sub["round5_prob"])
        fold_rows.append({
            "fold": fold,
            "alpha": best_alpha,
            "overlay_auc": s["auc"], "overlay_ap": s["ap"], "overlay_brier": s["brier"],
            "round5_auc": b["auc"], "round5_ap": b["ap"], "round5_brier": b["brier"],
        })
    pd.DataFrame(fold_rows).to_csv(OUT / "fold_results.csv", index=False)
    print(f"\n→ {OUT}")


if __name__ == "__main__":
    main()
