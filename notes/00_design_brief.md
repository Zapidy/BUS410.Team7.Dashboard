# Round 7 Design Brief

## What and Why

Round 5 produced a strong diagnostic model (mean test AUC 0.857) but its top predictors are structural ACS variables — persistent poverty, racial composition, education attainment — that no local lending ecosystem can move. A high-AUC diagnostic answers *where* but not *what to do*.

Round 7 trains a **separate** model on the same forward target using **only influenceable lending-environment variables**. If that model carries meaningful signal on its own, it earns the right to a policy-scenario layer (Phase 2). If it doesn't, we still ship two informative artifacts: a directional overlay on Round 5's risk score, and a bolt-on report quantifying how much influenceable variables add when stacked on the diagnostic.

## Target Leakage — Read This First

The Round 5 target `target_becomes_service_desert_h1` is **defined directly as the bottom decile of `n_cra_lenders` within (year × peer-group)** ([../../round5/features/define_target.py:39-53](../../round5/features/define_target.py#L39-L53)).

Several "influenceable" features are mechanically driven by the same underlying signal:

| Feature | Leakage mechanism |
|---|---|
| `unique_lenders_per_tract` | Literally `n_cra_lenders` — must be excluded entirely |
| `top1_lender_share`, `top3_lender_share`, `lender_hhi_tract` | When lender count is small (the desert condition), shares saturate at 1.0 / HHI saturates at 1.0 |
| `pct_loans_from_community_banks`, `pct_loans_from_top4_banks` | Numerator volatility explodes in thin-lender tracts |

### Mitigations baked into the build

1. **Drop `unique_lenders_per_tract` entirely.** Round 5 already drops `n_cra_lenders` from features for the same reason.
2. **Compute share/HHI features only when `n_cra_lenders ≥ 3`** at year T; else NaN. XGBoost handles NaN natively, so the model can learn "concentration is unmeasurable in already-thin tracts" rather than memorizing thin-tract concentration = 1.0.
3. **Use trailing 5-to-2-year mean** of share/concentration features (e.g., `pct_loans_from_community_banks_lag2to5_mean`) rather than year-T values — breaks the mechanical T → T+1 link.
4. **Frame honestly** in the final write-up. The "influenceable" framing is genuinely compromised by this dependency. The honest framing is **"lending-environment composition"**, not "policy-pure exogenous."

## Feature Suite (14 variables)

### Tier 1 — CRA-derived

| Feature | Notes |
|---|---|
| `pct_loans_from_community_banks` | Community = FDIC Call Report `total_assets < $10B` (year-varying threshold). Requires RSSD↔CRA crosswalk (see [01_rssd_cra_crosswalk.md](01_rssd_cra_crosswalk.md)). NaN-gated. |
| `pct_loans_from_top4_banks` | Top 4 by annual CRA small-business loan dollar volume. Year-varying list. NaN-gated. |
| `pct_loans_under_100k` | **Renamed from `pct_loans_under_50k`** in HANDOFF.md. CRA D1 schema only exposes `count_lt_100`, not `<50k` ([../../round5/etl/cra/parse_cra.py:61-66](../../round5/etl/cra/parse_cra.py#L61-L66)). Document the relabel. |
| `pct_loans_under_250k` | Tier 1.5 add. From `count_100_250` bucket. |
| `top1_lender_share_tract` | Tract-level (Round 5 only computes at county). NaN-gated. |
| `top3_lender_share_tract` | Same NaN gate. |
| `lender_hhi_tract` | Full Herfindahl. Same NaN gate. |

### Tier 1 — FDIC branch-derived

| Feature | Notes |
|---|---|
| `distance_to_nearest_bank_branch` | TIGER 2020 tract centroids + SoD lat/lng; `BallTree(metric='haversine')`. ~10 min runtime over 2009–2024. |
| `branches_within_5mi` | Same BallTree, `query_radius`. |
| `branch_closures_3y_within_10mi` | UNINUMBR YoY presence diff over prior 3 years. Radius fixed at 10 miles; sensitivity test deferred. |

### Tier 2 — Mission lender / depth

| Feature | Notes |
|---|---|
| `pct_loans_from_credit_unions` | CRA `agency_code = 4` flag from existing reporters table. No FDIC join needed. |
| `cdfi_within_10mi` | CDFI Fund certified-list, geocoded via Census Geocoder. |
| `mdi_branches_within_10mi` | FDIC MDI list joins to SoD via RSSD (free lat/lng from SoD), then spatial. |
| `microloan_intermediary_within_25mi` | SBA microlender list, geocoded. Sparser → larger radius. |

**All 14 features are also generated as trailing 5-to-2-year mean variants** for the leakage-mitigated model variant. Train the model with year-T features first, then re-train with trailing means and report both.

### Excluded by design

- `unique_lenders_per_tract` — direct target leakage.
- All ACS structural variables (poverty, race, income, education, vacancy, unemployment) — the entire reason for this round.
- HMDA volumes — small-business focus, not mortgage.
- RUCA / `is_rural` — kept as evaluation slicing key only, not a feature.
- Opportunity Zone flag — structural designation, not influenceable.

## Decision Rule

See [03_decision_rule.md](03_decision_rule.md) for the AP threshold derivation. Headline: random-baseline AP ≈ 0.017 for this target; user's voice-memo target of PR-AUC ≥ 0.6 is unrealistic. Reset thresholds to AP ≥ 0.10 (strong), 0.05–0.10 (moderate, run both fallbacks), < 0.05 (weak, run only bolt-on).

Per-fold stability matters more than the mean — require ≥ 6 of 8 folds to clear the threshold to avoid pinning the verdict on COVID-distorted years (Round 5's F5–F8 already degrade to 0.79–0.83).

## Directional sanity (Phase D check)

Partial dependence sign expectations:

| Feature | Expected PDP direction with desert risk |
|---|---|
| `pct_loans_from_community_banks` | ↓ (community banks fight deserts via relationship lending) |
| `pct_loans_from_top4_banks` | ↑ (large-bank dominance correlates with thin small-business credit) |
| `pct_loans_under_100k` | ↓ (small-loan supply is the active credit market) |
| `top1_lender_share_tract` | ↑ (concentration is fragility) |
| `lender_hhi_tract` | ↑ (concentration is fragility) |
| `distance_to_nearest_bank_branch` | ↑ (access friction) |
| `branches_within_5mi` | ↓ (access depth) |
| `branch_closures_3y_within_10mi` | ↑ (access deterioration) |
| `pct_loans_from_credit_unions` | ↓ (mission-lender presence) |
| `cdfi_within_10mi` | ↓ (mission-lender presence) |
| `mdi_branches_within_10mi` | ↓ (mission-lender presence) |
| `microloan_intermediary_within_25mi` | ↓ (small-loan ecosystem) |

Any sign-flip is a model-quality red flag and goes in this doc as an open question.
