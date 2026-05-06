#!/usr/bin/env python3
"""Feature importance for the audit-fixed walk-forward model.

Trains XGBoost on each of the 8 walk-forward folds, pulls gain-based
feature importance per fold, and reports the average ranking. Gain is
the right importance metric here (how much each feature contributes
to reducing the loss when used in a split — accounts for both how often
the feature is used and how informative each split is).

Outputs:
  diagnostics/feature_importance/per_fold.csv     — feature × fold matrix of normalized gain
  diagnostics/feature_importance/ranked.csv       — features ranked by mean gain across folds
"""
from __future__ import annotations
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

warnings.filterwarnings("ignore", category=UserWarning)

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data" / "processed" / "panel" / "tract_year_with_target.parquet"
OUT = ROOT / "diagnostics" / "feature_importance"
OUT.mkdir(parents=True, exist_ok=True)

TARGET = "target_becomes_service_desert_h1"

FOLDS = [
    ("F1", 2009, 2014, 2015, 2016, 2017),
    ("F2", 2009, 2015, 2016, 2017, 2018),
    ("F3", 2009, 2016, 2017, 2018, 2019),
    ("F4", 2009, 2017, 2018, 2019, 2020),
    ("F5", 2009, 2018, 2019, 2020, 2021),
    ("F6", 2009, 2019, 2020, 2021, 2022),
    ("F7", 2009, 2020, 2021, 2022, 2023),
    ("F8", 2009, 2021, 2022, 2023, 2024),
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
DROP_COLS = DROP_NEVER_FEATURES | CIRCULAR_FEATURES_PRIOR | CIRCULAR_FEATURES_FDIC


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


def main():
    print(f"Loading {PANEL.name}…")
    df = pd.read_parquet(PANEL)
    df = df[df[TARGET].notna()].copy()
    df[TARGET] = df[TARGET].astype(int)
    df["state_fips"] = df["tract_fips"].str[:2]
    df = df[~df["state_fips"].isin({"72", "78", "60", "66", "69"})].copy()
    print(f"  Loaded: {df.shape}")

    per_fold = {}  # feature -> {fold: gain}

    for fold_name, tr_s, tr_e, val_y, te_s, te_e in FOLDS:
        train = df[(df["year"] >= tr_s) & (df["year"] <= tr_e)]
        val = df[df["year"] == val_y]
        if len(train) == 0 or len(val) == 0:
            continue

        X_tr = prepare(train).drop(columns=["year"])
        y_tr = train[TARGET].values
        X_val = prepare(val).drop(columns=["year"])
        y_val = val[TARGET].values

        common = sorted(set(X_tr.columns) & set(X_val.columns))
        X_tr, X_val = X_tr[common], X_val[common]

        model = xgb.XGBClassifier(
            n_estimators=400, max_depth=6, learning_rate=0.05,
            subsample=0.85, colsample_bytree=0.85,
            min_child_weight=5, reg_lambda=1.0,
            tree_method="hist", objective="binary:logistic",
            eval_metric="aucpr", early_stopping_rounds=25,
            random_state=42, verbosity=0,
        )
        model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
        booster = model.get_booster()
        gain = booster.get_score(importance_type="gain")  # raw gain, dict
        # Normalize so each fold's gains sum to 1
        total = sum(gain.values()) or 1
        for f, v in gain.items():
            per_fold.setdefault(f, {})[fold_name] = v / total
        print(f"  {fold_name}: {len(gain)} features used (best_iter={model.best_iteration})")

    # Build feature × fold matrix
    fold_names = [f for f, *_ in FOLDS]
    rows = []
    for feat in sorted(per_fold):
        row = {"feature": feat}
        for fn in fold_names:
            row[fn] = per_fold[feat].get(fn, 0.0)
        row["mean"] = sum(row[fn] for fn in fold_names) / len(fold_names)
        row["folds_used"] = sum(1 for fn in fold_names if row[fn] > 0)
        rows.append(row)

    out_df = pd.DataFrame(rows).sort_values("mean", ascending=False).reset_index(drop=True)
    out_df["rank"] = out_df.index + 1

    # Group features into source families for the summary
    def family(feat):
        if feat in {"is_rural", "ruca_code"}: return "place_rural"
        if feat == "is_persistent_poverty": return "place_persistent_pov"
        if feat == "has_hmda": return "regime_flag"
        if feat.startswith("cra_county_"): return "cra_county_concentration"
        if feat.startswith("fdic_deposit") or feat.startswith("fdic_top_bank"): return "fdic_concentration"
        if feat.startswith("fdic_"): return "fdic_other"
        if feat in {"n_applications", "n_originated", "n_denied", "n_withdrawn", "n_purchased",
                    "approval_rate", "denial_rate", "sum_loan_amount", "mean_loan_amount",
                    "n_distinct_lenders", "n_white", "n_black", "n_asian", "n_hispanic", "n_other_race"}:
            return "hmda"
        if feat in {"population", "median_hh_income", "pct_poverty", "pct_minority",
                    "pct_black", "pct_hispanic", "housing_units", "pct_vacant",
                    "unemployment_rate", "pct_bachelor_plus"}:
            return "acs_demographics"
        return "other"
    out_df["family"] = out_df["feature"].map(family)

    # Ranked table — full
    out_path = OUT / "ranked.csv"
    out_df.to_csv(out_path, index=False)
    print(f"\n→ {out_path}  ({len(out_df)} features ranked)")

    # Top-30 console output
    print("\n" + "=" * 100)
    print(f"{'rank':>4}  {'feature':40}  {'family':24}  {'mean_gain':>10}  {'folds':>5}")
    print("=" * 100)
    for _, r in out_df.head(30).iterrows():
        print(f"{int(r['rank']):>4}  {r['feature']:40}  {r['family']:24}  {r['mean']:>10.4f}  {int(r['folds_used']):>5}")
    print("=" * 100)

    # Family rollup
    print("\nBy feature family (mean of mean gains, summed across features in family):")
    fam = out_df.groupby("family").agg(
        n_features=("feature", "count"),
        sum_gain=("mean", "sum"),
        mean_gain_per_feature=("mean", "mean"),
    ).sort_values("sum_gain", ascending=False)
    print(fam.round(4).to_string())
    fam.to_csv(OUT / "by_family.csv")

    # Long format for the dashboard or reports
    per_fold_long = []
    for _, r in out_df.iterrows():
        per_fold_long.append(r.to_dict())
    pd.DataFrame(per_fold_long).to_csv(OUT / "per_fold.csv", index=False)


if __name__ == "__main__":
    main()
