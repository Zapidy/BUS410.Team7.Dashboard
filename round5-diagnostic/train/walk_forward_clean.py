#!/usr/bin/env python3
"""Walk-forward training with circular features REMOVED.

The original walk_forward.py uses every column in the panel (64 features),
including features mechanically tied to the target:

  TARGET: tract becomes a desert at T+1, where 'desert' = n_cra_lenders at T+1
          is in the bottom decile of (year × rural/urban peer-group).

CIRCULAR FEATURES to remove:

  TIER 1 — directly target-defining at year T:
    - n_cra_lenders                          (literally the variable that defines the target)
    - cra_lender_entries_1yr                 (1yr change feeds directly into "did desert form?")
    - cra_lender_exits_1yr
    - cra_lender_churn_1yr
    - cra_lender_presence_ratio_1yr
    - cra_lender_entries_3yr                 (3yr aggregate STILL includes year T's value)
    - cra_lender_exits_3yr
    - cra_lender_churn_3yr

  TIER 2 — county-level proxies for the target ('county desert rate' analog):
    - cra_county_lender_count                (mechanically: tract-desert ⇒ tract few lenders;
                                              if county-lender-count low, multiple tracts in county
                                              are flagged → county_lender_count is a proxy for
                                              county desert prevalence)
    - cra_county_total_loan_count            (same logic: small businesses + small lenders correlate)
    - cra_county_total_loan_amount_k

CLEAN FEATURES (kept) — different supply-side, different domain, structural:
    - All FDIC SoD branch features           (physical branches, distinct from CRA reporters)
    - All HMDA tract aggregates              (mortgage origination, distinct from CRA SB lending)
    - All ACS demographic features
    - Place-based controls (rural / persistent poverty / OZ)
    - CRA county HHI features (concentration is a structural/distribution shape, not a level proxy)
    - CRA county top-lender-share features

This run gives the HONEST forecasting AUC. Expect a meaningful drop from
~0.93 → something between 0.65 and 0.80, which is the genuine signal.
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
OUT = ROOT / "diagnostics" / "walk_forward_clean"
OUT.mkdir(parents=True, exist_ok=True)

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

TARGET = "target_becomes_service_desert_h1"

# Identifiers + alternate targets — drop always
DROP_NEVER_FEATURES = {
    "tract_fips", "county_fips", "peer_group", "service_desert_threshold",
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

# Tier-1 + Tier-2 circular features — drop in the CLEAN run
CIRCULAR_FEATURES = {
    # Tier 1: directly target-defining at year T
    "n_cra_lenders",
    "cra_lender_entries_1yr", "cra_lender_exits_1yr",
    "cra_lender_churn_1yr", "cra_lender_presence_ratio_1yr",
    "cra_lender_entries_3yr", "cra_lender_exits_3yr",
    "cra_lender_churn_3yr",
    # Tier 2: county-level lender-count proxies (the 'county desert rate' analog)
    "cra_county_lender_count",
    "cra_county_total_loan_count",
    "cra_county_total_loan_amount_k",
}

DROP_COLS = DROP_NEVER_FEATURES | CIRCULAR_FEATURES


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    feats = df.drop(columns=[c for c in DROP_COLS if c in df.columns], errors="ignore")
    keep = [c for c in feats.columns if c != "year"]
    feats = feats[["year"] + keep]
    for col in feats.columns:
        if feats[col].dtype == object:
            feats[col] = pd.to_numeric(feats[col], errors="coerce")
    hmda_cols = [c for c in feats.columns
                 if c in {"n_applications", "n_originated", "n_denied", "n_withdrawn",
                          "n_purchased", "approval_rate", "denial_rate",
                          "sum_loan_amount", "mean_loan_amount", "n_distinct_lenders",
                          "n_white", "n_black", "n_asian", "n_hispanic", "n_other_race"}]
    feats[hmda_cols] = feats[hmda_cols].fillna(0)
    return feats


def evaluate(y_true, y_prob):
    if len(np.unique(y_true)) < 2:
        return {"n": len(y_true), "pos_rate": float(y_true.mean()),
                "auc": float("nan"), "ap": float("nan"),
                "ap_lift": float("nan"), "brier": float("nan")}
    auc = roc_auc_score(y_true, y_prob)
    ap = average_precision_score(y_true, y_prob)
    pos_rate = y_true.mean()
    ap_lift = ap / pos_rate if pos_rate > 0 else float("nan")
    brier = brier_score_loss(y_true, y_prob)
    return {"n": len(y_true), "pos_rate": float(pos_rate),
            "auc": float(auc), "ap": float(ap),
            "ap_lift": float(ap_lift), "brier": float(brier)}


def main():
    print(f"Loading {PANEL.name}…")
    df = pd.read_parquet(PANEL)
    print(f"  Loaded: {df.shape}")

    print(f"\nDROPPING {len(CIRCULAR_FEATURES)} circular features:")
    for c in sorted(CIRCULAR_FEATURES):
        in_panel = "✓" if c in df.columns else "·"
        print(f"  {in_panel} {c}")

    df = df[df[TARGET].notna()].copy()
    df[TARGET] = df[TARGET].astype(int)
    print(f"\nAfter dropping rows without {TARGET}: {df.shape}")
    print(f"Overall positive rate: {df[TARGET].mean()*100:.2f}%")

    fold_results = []
    test_predictions = []

    for fold_name, tr_s, tr_e, val_y, te_s, te_e in FOLDS:
        train = df[(df["year"] >= tr_s) & (df["year"] <= tr_e)]
        val = df[df["year"] == val_y]
        test = df[(df["year"] >= te_s) & (df["year"] <= te_e)]
        if len(train) == 0 or len(val) == 0 or len(test) == 0:
            continue

        X_tr = prepare_features(train).drop(columns=["year"])
        y_tr = train[TARGET].values
        X_val = prepare_features(val).drop(columns=["year"])
        y_val = val[TARGET].values
        X_te = prepare_features(test).drop(columns=["year"])
        y_te = test[TARGET].values

        common = sorted(set(X_tr.columns) & set(X_val.columns) & set(X_te.columns))
        X_tr, X_val, X_te = X_tr[common], X_val[common], X_te[common]

        print(f"\n{fold_name}: train {tr_s}-{tr_e} ({len(train):,}) | "
              f"val {val_y} ({len(val):,}) | test {te_s}-{te_e} ({len(test):,})")
        print(f"  features: {len(common)} (was 64; circular dropped)")

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
        val_metrics = evaluate(y_val, val_prob)
        test_metrics = evaluate(y_te, test_prob)
        print(f"  VAL  AUC={val_metrics['auc']:.4f}  AP={val_metrics['ap']:.4f}  AP-lift={val_metrics['ap_lift']:.2f}x")
        print(f"  TEST AUC={test_metrics['auc']:.4f}  AP={test_metrics['ap']:.4f}  AP-lift={test_metrics['ap_lift']:.2f}x")

        fold_results.append({
            "fold": fold_name, "train_years": f"{tr_s}-{tr_e}",
            "val_year": val_y, "test_years": f"{te_s}-{te_e}",
            "n_train": len(train), "n_val": len(val), "n_test": len(test),
            "best_iter": model.best_iteration,
            "val_auc": val_metrics["auc"], "val_ap": val_metrics["ap"],
            "test_auc": test_metrics["auc"], "test_ap": test_metrics["ap"],
            "test_ap_lift": test_metrics["ap_lift"], "test_brier": test_metrics["brier"],
            "test_pos_rate": test_metrics["pos_rate"],
        })

        pred_df = test[["tract_fips", "county_fips", "year"]].copy()
        pred_df["fold"] = fold_name
        pred_df["y_true"] = y_te
        pred_df["y_prob"] = test_prob
        test_predictions.append(pred_df)

        # Capture top-15 feature importances per fold
        try:
            imp = pd.Series(model.feature_importances_, index=common).sort_values(ascending=False)
            (OUT / f"feature_importance_{fold_name}.csv").write_text(
                "feature,importance\n" + "\n".join(f"{k},{v:.6f}" for k, v in imp.items())
            )
        except Exception:
            pass

    res_df = pd.DataFrame(fold_results)
    print(f"\n{'='*80}\nCLEAN fold summary (no circular features)\n{'='*80}")
    print(res_df[["fold", "train_years", "test_years", "n_test", "test_auc",
                  "test_ap", "test_ap_lift", "test_brier"]].to_string(
                      index=False, float_format="%.4f"))
    print(f"\nMean test AUC: {res_df['test_auc'].mean():.4f}  ± {res_df['test_auc'].std():.4f}")
    print(f"Mean test AP:  {res_df['test_ap'].mean():.4f}")
    print(f"Mean AP-lift:  {res_df['test_ap_lift'].mean():.2f}x")

    res_df.to_csv(OUT / "fold_results.csv", index=False)
    pd.concat(test_predictions, ignore_index=True).to_parquet(OUT / "test_predictions.parquet", index=False)
    print(f"\n→ {OUT}")


if __name__ == "__main__":
    main()
