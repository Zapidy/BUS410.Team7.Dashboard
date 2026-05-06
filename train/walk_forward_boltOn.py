#!/usr/bin/env python3
"""Phase C Variant B — Bolt-on.

Train round5's full feature stack PLUS the 14 round7 influenceable variables,
report ΔAUC and ΔAP vs the round5 baseline. Use sklearn permutation_importance
on the val set restricted to the 14 new features (XGBoost gain importance is
biased toward high-cardinality features and unreliable for additive comparison).

Inputs:
    ../round5/data/processed/panel/tract_year_with_target.parquet  (round5 features + target)
    data/processed/panel/tract_year_with_target_round7.parquet     (round7 features)

Output:
    diagnostics/round7_bolton/{fold_results.csv, test_predictions.parquet,
                               permutation_importance.csv}
"""
from __future__ import annotations
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.inspection import permutation_importance
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)

warnings.filterwarnings("ignore", category=UserWarning)

ROOT = Path(__file__).resolve().parents[1]
ROUND5_PANEL = ROOT.parent / "round5" / "data" / "processed" / "panel" / "tract_year_with_target.parquet"
ROUND7_PANEL = ROOT / "data" / "processed" / "panel" / "tract_year_with_target_round7.parquet"
from _horizon_config import HORIZON, TARGET, FOLDS  # noqa: E402

OUT = ROOT / "diagnostics" / f"round7_bolton_h{HORIZON}"

# Reuse round5's drop set
DROP_NEVER_FEATURES = {
    "tract_fips", "county_fips", "state_fips", "peer_group", "service_desert_threshold",
    "service_peer_median", "origination_desert_threshold",
    "originations_per_1k", "service_desert_score", "origination_desert_score",
    "is_service_desert", "is_origination_desert", "is_any_desert",
    "vintage", "acs_vintage_used",
    "target_service_desert_h1", "target_service_desert_h2", "target_service_desert_h3",
    "target_service_desert_h4", "target_service_desert_h5", "target_service_desert_h6",
    "target_any_desert_h1", "target_any_desert_h2", "target_any_desert_h3",
    "target_any_desert_h4", "target_any_desert_h5", "target_any_desert_h6",
    "target_becomes_service_desert_h1", "target_becomes_service_desert_h2",
    "target_becomes_service_desert_h3", "target_becomes_service_desert_h4",
    "target_becomes_service_desert_h5", "target_becomes_service_desert_h6",
    "target_becomes_any_desert_h1", "target_becomes_any_desert_h2",
    "target_becomes_any_desert_h3", "target_becomes_any_desert_h4",
    "target_becomes_any_desert_h5", "target_becomes_any_desert_h6",
}

CIRCULAR_FEATURES = {
    # Same as round5 walk_forward_audit_fixed
    "n_cra_lenders",
    "cra_lender_entries_1yr", "cra_lender_exits_1yr",
    "cra_lender_churn_1yr", "cra_lender_presence_ratio_1yr",
    "cra_lender_entries_3yr", "cra_lender_exits_3yr",
    "cra_lender_churn_3yr",
    "cra_county_lender_count",
    "cra_county_total_loan_count",
    "cra_county_total_loan_amount_k",
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
    # round7-specific: also drop n_active_lenders_tract since it's the same target signal
    "n_active_lenders_tract",
}

# Round 7 cleaned feature set: residualized concentration + branch + MDI + SSBCI.
# NMTC dropped per pruning result.
ROUND7_FEATURES = [
    # Tier 1 — CRA, residualized
    "pct_loans_from_community_banks_resid",
    "pct_loans_from_top4_banks_resid",
    "pct_loans_from_credit_unions_resid",
    "pct_loans_under_100k_resid",
    "pct_loans_under_250k_resid",
    "top1_lender_share_tract_resid",
    "top3_lender_share_tract_resid",
    "lender_hhi_tract_resid",
    # Tier 1 — FDIC branch
    "distance_to_nearest_bank_branch",
    "branches_within_5mi",
    "branch_closures_3y_within_10mi",
    # Tier 2 — Microlender + Year-precise MDI
    "microloan_intermediary_within_25mi",
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


def evaluate(y_true, y_prob):
    if len(np.unique(y_true)) < 2:
        return {"auc": float("nan"), "ap": float("nan"), "brier": float("nan")}
    return {
        "auc": float(roc_auc_score(y_true, y_prob)),
        "ap": float(average_precision_score(y_true, y_prob)),
        "brier": float(brier_score_loss(y_true, y_prob)),
    }


def prepare(df, drop_cols):
    feats = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore")
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
    OUT.mkdir(parents=True, exist_ok=True)
    print("Loading round5 panel…")
    p5 = pd.read_parquet(ROUND5_PANEL)
    p5["tract_fips"] = p5["tract_fips"].astype(str).str.zfill(11)

    print("Loading round7 panel…")
    p7 = pd.read_parquet(ROUND7_PANEL)
    p7["tract_fips"] = p7["tract_fips"].astype(str).str.zfill(11)
    r7_cols = [c for c in ROUND7_FEATURES if c in p7.columns]
    p7 = p7[["tract_fips", "year"] + r7_cols]

    df = p5.merge(p7, on=["tract_fips", "year"], how="left")
    df = df[df[TARGET].notna()].copy()
    df[TARGET] = df[TARGET].astype(int)

    df["state_fips"] = df["tract_fips"].str[:2]
    df = df[~df["state_fips"].isin({"72", "78", "60", "66", "69"})].copy()
    print(f"  Merged panel: {df.shape}, target pos rate {df[TARGET].mean()*100:.2f}%")
    print(f"  Round7 features bolted on: {r7_cols}")

    drop_cols = DROP_NEVER_FEATURES | CIRCULAR_FEATURES

    fold_results = []
    test_predictions = []
    perm_imp_rows = []

    for fold_name, tr_s, tr_e, val_y, te_s, te_e in FOLDS:
        train = df[(df["year"] >= tr_s) & (df["year"] <= tr_e)]
        val = df[df["year"] == val_y]
        test = df[(df["year"] >= te_s) & (df["year"] <= te_e)]
        if len(train) == 0 or len(val) == 0 or len(test) == 0:
            print(f"\n{fold_name}: SKIP")
            continue

        X_tr = prepare(train, drop_cols).drop(columns=["year"])
        X_val = prepare(val, drop_cols).drop(columns=["year"])
        X_te = prepare(test, drop_cols).drop(columns=["year"])
        common = sorted(set(X_tr.columns) & set(X_val.columns) & set(X_te.columns))
        X_tr, X_val, X_te = X_tr[common], X_val[common], X_te[common]
        y_tr, y_val, y_te = train[TARGET].values, val[TARGET].values, test[TARGET].values

        print(f"\n{fold_name}: features={len(common)} (incl. {sum(1 for f in r7_cols if f in common)} round7)")

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

        m = evaluate(y_te, test_prob_cal)
        print(f"  TEST  AUC={m['auc']:.4f}  AP={m['ap']:.4f}  Brier={m['brier']:.4f}")

        # Permutation importance — only on the round7 features that are present
        r7_in_model = [f for f in r7_cols if f in common]
        if r7_in_model:
            print(f"  Permutation importance on {len(r7_in_model)} round7 features…")
            try:
                # Use a sample of val for speed (perm imp is slow on full val)
                sample = X_val.sample(n=min(20_000, len(X_val)), random_state=42)
                y_sample = y_val[sample.index] if hasattr(y_val, "__getitem__") and not isinstance(y_val, np.ndarray) else y_val[sample.index.values]
                pi = permutation_importance(
                    model, sample, y_sample,
                    n_repeats=3, random_state=42, n_jobs=1, scoring="average_precision",
                )
                for i, feat in enumerate(common):
                    if feat in r7_in_model:
                        perm_imp_rows.append({
                            "fold": fold_name, "feature": feat,
                            "importance_mean": pi.importances_mean[i],
                            "importance_std": pi.importances_std[i],
                        })
            except Exception as e:
                print(f"    perm_imp failed: {e}")

        fold_results.append({
            "fold": fold_name, "train_years": f"{tr_s}-{tr_e}",
            "test_years": f"{te_s}-{te_e}",
            "n_test": len(test),
            "test_auc": m["auc"], "test_ap": m["ap"], "test_brier": m["brier"],
        })

        pred_df = test[["tract_fips", "county_fips", "year"]].copy()
        pred_df["fold"] = fold_name
        pred_df["y_true"] = y_te
        pred_df["y_prob_bolton"] = test_prob_cal
        test_predictions.append(pred_df)

    res = pd.DataFrame(fold_results)
    print("\nBolt-on summary:")
    print(res.to_string(index=False, float_format="%.4f"))
    print(f"\nMean test AUC: {res['test_auc'].mean():.4f}  AP: {res['test_ap'].mean():.4f}")

    res.to_csv(OUT / "fold_results.csv", index=False)
    pd.concat(test_predictions, ignore_index=True).to_parquet(
        OUT / "test_predictions.parquet", index=False
    )
    if perm_imp_rows:
        pd.DataFrame(perm_imp_rows).to_csv(OUT / "permutation_importance.csv", index=False)
        print(f"  Permutation importance for round7 features: {len(perm_imp_rows)} rows")
    print(f"\n→ {OUT}")


if __name__ == "__main__":
    main()
