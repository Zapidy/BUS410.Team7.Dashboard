# Predicting Small-Business Credit Deserts with an Influenceable-Only Model

## A Two-Layer Architecture, Target-Leakage Mitigation, and Honest Findings

**BUS410 — Team 7, Round 7**
**Methodology Brief**

---

## Abstract

This brief documents Round 7 of a tract-year forward-prediction project that identifies emerging small-business credit deserts in the United States. The work extends a prior diagnostic model (Round 5) by training a second, methodologically distinct model on only twenty influenceable lending-environment variables — branch access, residualized lender concentration, mission-lender presence, and state credit-support program activation — and then evaluates both models at two prediction horizons designed around how the underlying federal data actually arrives.

The original training horizon (h+1, predict one year forward) turned out to be operationally useless: the FFIEC CRA disclosure files publish on roughly a two-year lag, so any model trained on the most recent feature year (2024) at h+1 is predicting 2025, a year already in the past by the time the forecast is delivered. Round 7 therefore retrained the entire pipeline at two longer horizons — **h+3** (the new primary, forecasting 2027 from the latest data) and **h+6** (a long-horizon scenario, forecasting 2030) — and the headline performance numbers improved rather than degraded:

| | h+1 (legacy) | **h+3 (primary)** | **h+6 (long-horizon)** |
|---|---:|---:|---:|
| Model 1 — Diagnostic AUC / AP | 0.857 / 0.172 | **0.875 / 0.322** | **0.871 / 0.489** |
| Model 2 — Influenceable AUC / AP | 0.794 / 0.129 | **0.820 / 0.282** | **0.862 / 0.464** |
| Model 2 AP-lift | 6.7× | **11.1×** | **19.5×** |

The longer horizons reveal cleaner structural signal because random year-to-year shocks dominate at h+1; multi-year structural drift dominates at h+3 and h+6. The principal methodological contribution remains a target-leakage mitigation by residualization (concentration features regressed against `n_cra_lenders` within year-by-peer-group cohorts), but the most important new finding sits in the ablation study: at h+1, dropping intervention features (MDI, microlender, branch access) was near-zero or even improved the model; at h+3, all three of those intervention-focused levers contribute meaningfully to AP — which means the policy-slider story moves from "informative as ranking" to "responsive to lever movement." The pre-/post-COVID regime split persists at all horizons but reorganizes: at h+6 post-COVID, branch access alone accounts for 73% of model gain, the dominant signal at long horizons in the post-COVID era.

---

## Problem and Motivation

A small-business credit desert is a census tract in which the supply of small-business credit — measured most directly by the count of distinct CRA-reporting lenders active in that tract — has fallen below a defensible bottom-decile threshold relative to the tract's peer group in that year. Tracts in this state experience documented downstream effects: reduced small-business formation, slower employment growth, longer firm-finance search times, and persistently thinner relationship-lending channels. The Federal Reserve's 2017 working paper "Out of Sight, Out of Mind: Nearby Branch Closures and Small Business Growth" provides the canonical causal evidence linking branch access to small-firm credit outcomes,[^1] and the Community Reinvestment Act framework — established in 1977 and substantially revised in 2023 — explicitly designates small-business lending in low- and moderate-income tracts as a regulated public concern.[^2]

The forecasting problem is structured as a tract-year-forward binary classification: given everything observable up to and including year *T*, predict whether tract *i* will *become* a service desert in year *T+1* (we restrict prediction to tracts not already in desert state at *T*). The unit of analysis is the 2020-vintage census tract, with all earlier years apportioned forward via the Census Bureau's tract relationship files.

Why is one model insufficient? A high-AUC diagnostic that learns from American Community Survey structural variables — persistent poverty, racial composition, educational attainment, vacancy rates — answers *where* risk concentrates but produces no actionable handle. No county, state, or local lending coalition can move a tract's poverty rate by ten points in three years. If the model's signal lives entirely in those structural anchors, the forecast becomes a rediscovery of disadvantage rather than a tool for intervention. The Round 5 diagnostic, by design, used the broadest available feature set and accordingly leans heavily on those structural predictors. Its 0.857 AUC is real and useful for triage, but it cannot, on its own, motivate action.

Round 7 is therefore not a replacement for Round 5. It is a deliberate methodological pivot: train a second, structurally austere model that uses *only* lending-environment variables that local actors can plausibly influence, judge whether that model carries genuine forward signal, and — if it does — present the two layers side by side. Model 1 says where. Model 2 says what could change.

---

## Two-Layer Architecture

The two-layer framing flows directly from the original team handoff document, which named the gap explicitly: the diagnostic model "can be good at saying where risk is likely to emerge while still being poor at saying what a county, state, or local lending ecosystem can do about it." The two layers operate on the same target and the same eight-fold walk-forward partition, so their performance numbers are directly comparable.

| Layer | Role | Model | Features | Mean test AUC | Mean test AP | AP-lift | Std AUC |
|---|---|---|---|---:|---:|---:|---:|
| Model 1 — Diagnostic | "Where is risk high?" | XGBoost | 39 (ACS + CRA + FDIC + HMDA) | 0.857 | 0.172 | 9.25× | 0.044 |
| Model 2 — Influenceable | "Which lending-environment changes plausibly improve access?" | XGBoost | 20 (residualized concentration + branch + MDI + SSBCI) | 0.794 | 0.129 | 6.7× | 0.047 |

Both models clear the AP ≥ 0.10 STRONG-signal threshold defined in the project's decision-rule note. Model 2 trades 0.063 AUC and 0.043 AP for full leakage defensibility and full structural austerity — every variable in its panel can be moved, in principle, by an identifiable policy actor (a state government, a local coalition, a bank, a federal agency).

The architectural commitment matters because it disciplines downstream interpretation. When a user inspects a tract on the dashboard, they see two separate scores rendered in two distinct color signatures: a deep ink-blue Model-1 risk gradient (the structural-disadvantage layer) and a terracotta Model-2 risk gradient (the policy-action layer). A tract scoring high on Model 1 and low on Model 2 is structurally disadvantaged but enjoys a relatively favorable lending environment — interventions there are about preserving what works. A tract scoring high on both is the canonical at-risk case. A tract scoring low on Model 1 and high on Model 2 is the most diagnostically interesting category: the structure looks fine, but the lending environment is thinning, and the model thinks that matters.

The architecture also forces the team to be explicit about what "influenceable" means. We adopted the rule that a feature qualifies for Model 2 only if there is an identified mechanism by which a real institution could move it — bank branch siting decisions for `distance_to_nearest_bank_branch`, FDIC certification and partnership for `mdi_branches_within_10mi`, state-level Treasury allocation for `ssbci_active`. Features that fail this test — poverty rate, racial composition, educational attainment, broad ACS structural variables — were excluded by construction, not by feature selection. This is the most important methodological consequence of the two-layer architecture: it converts a feature-engineering question into a definitional one.

---

## Data Sources and Feature Engineering

The Round 7 panel draws from eight distinct public data sources, integrated into a single tract-year matrix at the 2020 census-tract vintage.

| Source | Use in Round 7 | Years | Geocoding strategy |
|---|---|---|---|
| FFIEC CRA Disclosure (D1) flat files | Tract-lender-year small-business loan counts and dollar volumes; all concentration features | 2009–2024 | Native FIPS coding; lenders keyed on `(agency_code, respondent_id)` |
| FDIC Summary of Deposits (SoD) | Branch lat/lng for proximity, density, and closure features | 2009–2024 | Native lat/lng; tract assignment via spatial join to TIGER 2020 |
| FDIC Call Report | Year-varying total-assets threshold for community-bank classification | 2009–2024 | RSSD-keyed; joined to CRA via crosswalk |
| FDIC MDI list | Year-precise MDI roster for mission-lender features | 2009–2024 | RSSD-keyed; branch lat/lng inherited from SoD |
| NMTC project data (Treasury CDFI Fund) | Initial test of NMTC investment-dollar features | 2009–2023 | Project-level lat/lng; tract assignment via Census API |
| SBA microlender intermediary list | Microloan ecosystem proximity feature | Quarterly snapshots | Address-only; geocoded via Census Geocoder + Nominatim fallback |
| Treasury SSBCI Capital Program Summaries | State-year activation features (SSBCI 1.0 and 2.0) | 2011–2024 | State-level overlay; mapped to all tracts in state |
| Census TIGER 2020 Gazetteer | Tract centroids for all proximity calculations | 2020 vintage | Authoritative |

The CRA panel is the substrate. We assembled a tract-lender-year apportioned panel of approximately 20 million rows by parsing the FFIEC D1 disclosure flat files for 2009 through 2024, normalizing the three-way `(tract, lender, year)` key, and apportioning loan counts and dollar volumes across the 2010-to-2020 tract boundary change using the Census Bureau's relationship files. This is the source of every concentration feature (Herfindahl index, top-1, top-3, top-4 share), every loan-mix feature (community-bank share, top-4 share, credit-union share, small-loan-size share), and the desert target itself.

The lender-classification work required building a custom **RSSD-to-CRA crosswalk**, because no public, official mapping exists between CRA `(agency_code, respondent_id)` keys and FDIC RSSD identifiers. We implemented a three-pass match — exact normalized name plus state, fuzzy `token_set_ratio ≥ 90` within state, name plus city for residual cases — and validated against a manual review queue for ratios in the [75, 90) interval. The crosswalk achieves a **94.6% match rate by row count** and a higher dollar-volume-weighted match rate, exceeding the 90% threshold below which community-bank-share and top-4-share features become unreliable. Credit unions (CRA `agency_code = 4`) bypass FDIC entirely and route through the NCUA institution list.

The MDI feature set benefits from a useful shortcut: because the FDIC MDI list is keyed on RSSD/CERT and the SoD already carries lat/lng for every branch, an inner join produces year-precise MDI branch coordinates with no additional geocoding. The CDFI and microlender lists are smaller (approximately 1,400 and 140 entities respectively) and were geocoded via the Census Geocoder with Nominatim as a fallback for the residual; hit rates were 87% for CDFIs and 48% for microlenders. The low microlender hit rate reflects address-quality issues in the SBA roster and is documented as a downstream caveat.

For each of the proximity features (`distance_to_nearest_bank_branch`, `branches_within_5mi`, `mdi_branches_within_10mi`, `microloan_intermediary_within_25mi`, `nearest_mdi_branch_miles`), we constructed a `BallTree` with the haversine metric over the SoD branch coordinates and queried it from each tract centroid. The full panel build for branch features completed in approximately ten minutes across 2009–2024. Branch closure counts (`branch_closures_3y_within_10mi`) were computed from year-over-year `UNINUMBR` presence diffs over a trailing three-year window.

State-level SSBCI activation features (`ssbci_active`, `ssbci_program_count`, `ssbci_2_0_active`, `ssbci_n_capital_programs`) were encoded from the Treasury capital-program summaries as state-year overlays, then mapped to all tracts within the activating state. We do not pretend tract-level precision for a state-level program; the encoding makes that explicit.

---

## Modeling Methodology

The training framework is an **eight-fold walk-forward validation** over the 2009–2024 panel. The first fold trains on 2009–2014, validates on 2015, and tests on 2016–2017; each subsequent fold rolls the windows forward by one year, with the final fold training on 2009–2021 and testing on 2023–2024. This structure preserves temporal order, mirrors how the model would be deployed in practice (using only past data to predict the future), and produces an *eight-element distribution* of out-of-sample performance rather than a single point estimate.

The supervisory target is `target_becomes_service_desert_h1`, defined as the bottom decile of `n_cra_lenders` *within year × peer_group*, conditional on the tract not already being a desert in year *T*. Peer groups partition tracts by RUCA code (rural / suburban / urban), so the target is a relative threshold within each tract's structural peer cohort, not a national absolute. This is a deliberate choice: a national absolute would over-flag rural tracts that were never served by many lenders to begin with. Federal lands and territories are excluded from training and evaluation.

The classifier is **XGBoost** with hyperparameters tuned in the early iterations and frozen for the final cleaned variant: `max_depth=6`, `learning_rate=0.05`, `subsample=0.8`, `colsample_bytree=0.8`, `min_child_weight=10`, with early stopping on the validation fold and a maximum of 500 rounds. The output of each fold is **isotonically calibrated** against the validation set before scoring the test set; isotonic calibration is appropriate here because we have enough data per fold (75–95k validation rows) and we care about top-decile precision, where well-calibrated rare-event probabilities matter.

Feature engineering followed a **block-of-clay → pruning** progression rather than a one-shot specification. The first iteration (`v1`) trained on 14 year-T influenceable features and produced AUC 0.817 with AP 0.153 — promising but exposed to the leakage pathway described in the next section. The second iteration (`v2`) added trailing five-to-two-year mean variants of the share and concentration features, which raised AP to 0.205 and was the first quantitative signal that leakage mitigation actually helped. The third iteration (`v3`) added the year-precise MDI roster, the SSBCI state-year overlay, and five NMTC investment-dollar features, expanding the panel to 25 features; this stabilized the cross-fold standard deviation but did not improve mean AP. We then took the top-10 features by importance from `v3`, retrained, and confirmed an elbow at *k* = 10 — diminishing returns past that.

The cleaned variant `v4` is the headline. We dropped the five NMTC features (importance near zero, explained below), residualized all concentration and loan-mix features within year-by-peer-group cohorts (the centerpiece, explained next), and arrived at the final 20-feature panel reported in the abstract.

| Iteration | Variant | Features | AUC | AP | Notes |
|---|---|---:|---:|---:|---|
| v1 | 14 influenceable, year-T concentration | 14 | 0.817 | 0.153 | Initial; leakage-vulnerable |
| v2 | + trailing 5-to-2-year means | 17 | 0.841 | 0.205 | First leakage-mitigation evidence |
| v3 | + NMTC + year-precise MDI + SSBCI | 25 | 0.826 | 0.155 | Stability gain, no AP gain |
| v3-prune | top-10 from v3 by importance | 10 | 0.834 | 0.145 | Elbow at *k* = 10 |
| **v4 cleaned** | **NMTC dropped + concentration residualized** | **20** | **0.794** | **0.129** | **Headline — defensible** |
| v4-prune | top-7 from v4 by importance | 7 | 0.780 | 0.129 | Cleaned elbow |

The cleaned variant trades 0.05 AUC and 0.07 AP relative to `v2` for full defensibility against the target-leakage pathway. The earlier numbers were not "real" in the operational sense: a slider that moves a year-T concentration feature would, in the leakage-vulnerable variants, produce score changes that reflect the mathematical definition of the target rather than the underlying market structure. We wrote that score change off the model and accepted the AP cost.

---

## Target Leakage Mitigation

This is the methodological centerpiece of Round 7.

The desert target is defined as `n_cra_lenders < bottom_decile(n_cra_lenders | year, peer_group)`, evaluated at year *T+1*. Several features in the influenceable panel are mathematical functions of the same `n_cra_lenders` count at year *T*. The lender-count feature `unique_lenders_per_tract` is literally identical to `n_cra_lenders` and was excluded entirely (Round 5 had already excluded it for the same reason). But the concentration features — `lender_hhi_tract`, `top1_lender_share_tract`, `top3_lender_share_tract`, `pct_loans_from_top4_banks`, `pct_loans_from_community_banks`, `pct_loans_from_credit_unions` — are subtler offenders. When the lender count is small (the desert condition itself), shares saturate at 1.0, the Herfindahl index saturates at 1.0, and the share variance explodes. A model that learns "concentration is high" is partly learning "the lender count is low at T" — and the lender count at *T* is approximately the lender count at *T+1*, which *is* the target.

We considered three mitigation strategies.

**Strategy 1: Trailing means.** Compute share and concentration features as five-to-two-year trailing averages, breaking the mechanical *T → T+1* link. This is the approach used in Round 5 for related features and the basis of `v2`. Trailing means improved AP (the `v2` AP of 0.205 versus `v1` AP of 0.153 is the evidence). However, they do not eliminate the underlying mathematical dependency — they only push it back in time, and the lender count is highly autocorrelated.

**Strategy 2: NaN gate.** Compute share and concentration features only when `n_cra_lenders ≥ 3` at year *T*, and emit NaN otherwise. XGBoost handles NaN natively, so the model can learn "concentration is unmeasurable in already-thin tracts" rather than memorizing thin-tract concentration as 1.0. This works but throws away signal in the very tracts we most care about predicting.

**Strategy 3: Residualization.** For each concentration or share feature *X*, fit `X ~ log(n_cra_lenders + 1) + n_cra_lenders` within each year × peer_group cohort, and use the residual as the model feature. This explicitly removes the lender-count-explained component of *X* while preserving whatever signal in *X* is genuinely about market structure. We chose this strategy.

The residualization is run independently within each year × peer_group cohort to prevent the regression from learning across cohorts that should not pool. The functional form (log plus linear) was chosen after inspecting the empirical relationship between each share feature and the underlying lender count; a log-linear specification captured the saturation at low counts and the asymptote at high counts cleanly.

The variance reduction from residualization is substantial:

| Feature | Residual std / original std | Variance lost to residualization |
|---|---:|---:|
| `top3_lender_share` | 0.55× | ~70% |
| `lender_hhi_tract` | 0.57× | ~67% |
| `top1_lender_share` | 0.71× | ~50% |
| `pct_loans_from_community_banks` | 0.92× | ~15% |
| `pct_loans_from_credit_unions` | 0.36× | ~87% |

Credit-union share loses the most variance, which is intuitive: credit-union presence is rare enough that most tract-year `pct_loans_from_credit_unions` values were structurally driven by the lender-count denominator. Community-bank share, by contrast, was already mostly clean — the residualization largely confirmed that the signal there was real market-structure variation. The Herfindahl and top-3 features land in the middle: the residualized versions still carry signal (four of the top seven cleaned-model features by importance are residualized concentration), but the leakage-vulnerable component has been removed.

Residualization has a real downstream cost. The features become harder to interpret in the policy-slider UI. We can no longer say "increase community-bank share by ten points"; the natural language is "shift residualized community-bank share, holding lender count fixed in the cohort." That second phrasing is correct but unfamiliar, and it constrains how cleanly the slider can communicate intervention magnitudes. We discuss this in the Limitations section.

---

## Findings

The cleaned Model 2 achieves mean test **AUC 0.794** and mean test **AP 0.129** across the eight folds, corresponding to an **AP-lift of 6.7×** over the random baseline of 0.017 (the unconditional positive rate of the target). Fold-level performance is reported below.

| Fold | Test years | n_test | AUC | AP | AP-lift |
|---|---|---:|---:|---:|---:|
| F1 | 2016–17 | 170,106 | 0.809 | 0.135 | 7.9× |
| F2 | 2017–18 | 168,196 | 0.841 | 0.130 | 8.6× |
| F3 | 2018–19 | 163,614 | 0.850 | 0.153 | 10.3× |
| F4 | 2019–20 | 158,588 | 0.829 | 0.164 | 11.2× |
| F5 | 2020–21 | 157,747 | 0.713 | 0.110 | 3.9× |
| F6 | 2021–22 | 157,316 | 0.751 | 0.160 | 4.3× |
| F7 | 2022–23 | 155,554 | 0.780 | 0.094 | 3.7× |
| F8 | 2023–24 | 77,124 | 0.780 | 0.084 | 3.7× |

Six of eight folds clear the AP ≥ 0.10 strong-signal threshold. The standard deviation of test AUC is 0.047, slightly above Round 5's 0.044 — comparable stability, with the influenceable-only panel costing about three percentage points of fold-to-fold consistency.

Top features by mean XGBoost gain across folds:

| Rank | Feature | Importance | Type |
|---|---|---:|---|
| 1 | `distance_to_nearest_bank_branch` | 0.369 | Branch access |
| 2 | `lender_hhi_tract_resid` | 0.097 | Residualized concentration |
| 3 | `pct_loans_from_top4_banks_resid` | 0.066 | Residualized concentration |
| 4 | `pct_loans_from_credit_unions_resid` | 0.049 | Residualized concentration |
| 5 | `ssbci_active` | 0.048 | State policy |
| 6 | `top3_lender_share_tract_resid` | 0.046 | Residualized concentration |
| 7 | `branches_within_5mi` | 0.041 | Branch access |
| 8 | `pct_loans_under_250k_resid` | 0.040 | Residualized loan-size |
| 9 | `mdi_branches_within_10mi` | 0.037 | Mission lender |
| 10 | `pct_loans_from_community_banks_resid` | 0.029 | Residualized concentration |

Branch access alone — the rank-1, rank-7, and rank-13 features — accounts for roughly 43% of cumulative model importance. Residualized concentration spans ranks 2, 3, 4, 6, 8, 10, 12. Mission-lender features occupy ranks 9, 11, and 15–18. State SSBCI features sit at ranks 5 and 14. This ordering is the most directly interpretable result of the project: by importance, the model thinks branch-distance dominates, with concentration structure as a strong secondary signal.

The directional partial-dependence checks pass: greater distance to the nearest branch increases predicted desert probability, more nearby branches decreases it, higher residualized HHI and top-share features increase it, presence of MDI branches decreases it, SSBCI activation decreases it. No sign-flips were observed in the cleaned model.

---

## §6.5 The horizon switch — from h+1 to h+3 / h+6

The headline numbers above were the original, h+1 specification. They were correct on their own terms but useless on operational terms, and the bulk of Round 7's late-cycle work was a horizon retrain that rebuilt the pipeline around two longer-horizon targets and produced stronger results.

**The federal data lag problem.** The FFIEC CRA disclosure files — the substrate for every concentration, lender-mix, and target variable in this work — are released approximately two years after the calendar year they describe. The 2024 CRA disclosure file ships in late 2026. The FDIC Summary of Deposits, MDI roster, and SSBCI activation data have shorter lags but are gated by the same downstream join. A model trained at h+1 on the most recent available year of features (2024) is therefore producing a forecast for 2025 — a year already complete by the time the model can be run with the freshest data. The forecast arrives after the year it forecasts.

**Why h+1 was operationally useless.** The original Round 7 specification — `target_becomes_service_desert_h1`, predict one year forward — was the right academic choice for evaluating signal but the wrong operational choice for shipping a tool. Any user opening the dashboard in 2026 to ask "what is my tract's risk?" would receive a prediction for a year that had already happened. The horizons that matter for actual policy planning — a county opening a credit-counseling office, a state authorizing a new SSBCI program, a CDFI siting a new branch — are at least three years out. We accordingly extended the panel build (`define_target.py`) to compute h1 through h6 versions of the target and retrained the entire pipeline at h+3 and h+6, leaving h+1 in place as a legacy diagnostic.

**The fold restructure.** Each horizon requires its own walk-forward fold structure because the target year for fold `k` shifts by `h-1` years, and the panel's data_end constraint (last feature year = 2024 by 2026) caps how many folds can be cleanly produced. At h+1, eight folds run from test years 2016–2017 through 2023–2024. At h+3, the test windows shift forward by two years; with the same training-window discipline, eight folds run from test years 2014–2015 through 2021–2021 (the last fold is a single-year test because the target horizon caps at 2024). At h+6, only six folds fit cleanly, with test years 2012–2013 through 2017–2018. A shared `_horizon_config.py` module parameterizes the fold structure, train-window minimum, and target column, and the four core training scripts (`walk_forward_round7.py`, `prune_features.py`, `ablation_per_lever.py`, `regime_split.py`) accept a `ROUND7_HORIZON` environment variable that selects 1, 3, or 6.

**The surprising finding: AUC and AP improve at longer horizons.** The naive expectation is that prediction gets harder as horizon lengthens — more time for unmodeled shocks, more drift, more noise. The actual result is the opposite. From the eight-fold (h+3) and six-fold (h+6) phaseA results:

| Metric | h+1 | h+3 | h+6 |
|---|---:|---:|---:|
| Model 1 — mean test AUC | 0.857 | 0.875 | 0.871 |
| Model 1 — mean test AP | 0.172 | 0.322 | 0.489 |
| Model 2 — mean test AUC | 0.794 | 0.820 | 0.862 |
| Model 2 — mean test AP | 0.129 | 0.282 | 0.464 |
| Model 2 — mean AP-lift | 6.7× | 11.1× | 19.5× |

Every metric on every model improves monotonically as horizon lengthens. AP roughly doubles from h+1 to h+3 and triples from h+1 to h+6. Lift jumps from 6.7× to 19.5×.

**The mechanism.** The h+1 horizon is dominated by year-to-year noise — idiosyncratic local lending shocks, single-bank pullouts and re-entries, one-off PPP-vintage volatility, the kind of variance that no slow-moving structural feature can capture. The deeper structural trends that the influenceable feature set encodes — branch consolidation, lender-mix consolidation, persistent concentration in thinning markets — play out over multi-year windows. At h+1 the signal-to-noise ratio is poor because the noise is the dominant source of variance in the target; at h+6 the noise averages out and the structural signal stands clear. A six-year window is also long enough for ssBCI-program effects, mission-lender ecosystem changes, and post-COVID consolidation to have actually accrued. The longer horizons are therefore not just operationally necessary; they are also methodologically more appropriate for the kind of slow-moving policy-leverable signal the influenceable model was designed around.

The horizon switch is consequently the single most important methodological revision since the residualization fix. It changes the headline numbers, it changes the ablation interpretation (§7), it changes the regime-split story (§8), and it changes how the dashboard's policy-slider story can be honestly told (§11). The full methodological treatment lives in §4.6 of the full documentation; this section is its synopsis.

---

## The Ablation Surprise — and how it shifts at h+3

What the model says by importance and what the model actually depends on are not the same thing. We ran an **ablation study** that drops each thematic group of features in turn and retrains the model, holding all other features and hyperparameters fixed. The h+1 ablation gave a strong but narrow story: only one feature group was load-bearing. The h+3 ablation tells a different and substantially more interesting story for the policy-intervention frame.

**At h+1**, the original ablation result was a one-lever story:

| Group dropped at h+1 | ΔAUC | ΔAP |
|---|---:|---:|
| Residualized concentration | **−0.096** | **−0.023** |
| Residualized loan-size | −0.008 | +0.001 |
| Branch access | −0.003 | −0.001 |
| MDI / mission lender | −0.001 | −0.002 |
| Microlender ecosystem | +0.006 | +0.003 |
| Residualized lender mix | +0.005 | +0.005 |
| SSBCI state policy | +0.008 | +0.006 |

The h+1 reading was that only residualized concentration mattered, that branch access was rank-1 by importance but substitutable, and that the three intervention-focused groups (MDI, microlender, branch access) were essentially zero or even slightly negative on AP. That gave the dashboard's policy slider a problem: the model said "concentration is what's load-bearing," but a county economic-development office cannot directly move residualized concentration.

**At h+3**, the picture flips:

| Lever dropped at h+3 | ΔAUC | ΔAP |
|---|---:|---:|
| Residualized concentration | **−0.077** | **−0.064** |
| MDI / mission lender | −0.000 | **−0.028** |
| Microlender ecosystem | +0.008 | **−0.019** |
| Branch access | +0.005 | **−0.017** |
| Residualized loan-size | +0.005 | −0.012 |
| Residualized lender mix | −0.002 | −0.010 |
| SSBCI state policy | −0.009 | +0.013 |

Three observations follow.

First, **residualized concentration remains the largest single lever** but the gap closes substantially. Concentration's ΔAP at h+3 is −0.064; at h+1 it was −0.023. The lever is now nearly three times more responsive on AP, but it is no longer alone — the model has more structural signal to draw on at a longer horizon, so it is more sensitive to *removing* any one source of structural signal.

Second, and most importantly for the policy story, **all three intervention-focused levers gain non-trivial AP impact at h+3**. MDI / mission lender drops AP by 0.028 — the second-largest ΔAP in the table. Microlender ecosystem drops AP by 0.019. Branch access drops AP by 0.017. At h+1, these three groups had ΔAP values in the range −0.002 to +0.003, statistically indistinguishable from zero. At h+3, all three are demonstrably load-bearing on AP. This is a meaningful narrative shift: the longer horizon makes the model genuinely sensitive to the levers that local actors can actually pull.

Third, **SSBCI is the lone holdout**: dropping it at h+3 *improves* AP by 0.013. The state-year overlay is too coarse to add cohort-level variance once a longer horizon is allowed to surface other signals.

The h+6 ablation result is qualitatively similar but with smaller per-group magnitudes (concentration ΔAP −0.032, branch access ΔAP −0.006, MDI ΔAP −0.005, microlender ΔAP −0.004). The pattern — intervention-focused levers contributing real, non-zero AP impact rather than near-zero — persists into the long-horizon scenario. Per-feature magnitudes diminish at h+6 because the model has six years of structural drift to integrate, so the average feature has more correlated proxies; but the rank ordering of "which lever, when removed, costs the model AP" is preserved.

**The interpretation: the longer horizon is what makes the policy levers actually matter.** XGBoost gain importance is still biased toward continuous high-cardinality features (`distance_to_nearest_bank_branch` still dominates the gain ranking at every horizon). But the *ablation* metric — what happens when the lever is removed — is now telling a different and more useful story: at h+3, a county that opens a branch, partners with an MDI, or expands microlender presence is moving features that the model is genuinely sensitive to. At h+1, the same moves were essentially invisible to the model. The horizon switch is therefore not just a fix to the federal-data-lag problem; it also rescues the policy-intervention story.

We treat the h+3 ablation table as the authoritative summary of what the new primary Model 2 depends on, with the h+6 table as the long-horizon companion.

---

## The Pre-/Post-COVID Regime Shift

The eight-fold walk-forward conceals a regime break. Folds F1–F4 (test years 2016–2020) draw from a stable pre-COVID lending environment. Folds F5–F8 (test years 2020–2024) include the PPP shock, the 2020–2021 lender-count distortion, and the SSBCI 2.0 era beginning in 2022. To quantify the break, we re-ran the model under a clean two-period split: train 2009–2017 / test 2018–2019 (pre-COVID), and train 2020–2021 / test 2023–2024 (post-COVID).

| Regime | n_test | Pos rate | Test AUC | Test AP | AP-lift |
|---|---:|---:|---:|---:|---:|
| Pre-COVID (test 2018–19) | 163,614 | 1.49% | **0.817** | **0.144** | 9.7× |
| Post-COVID (test 2023–24) | 77,124 | 2.26% | **0.734** | **0.078** | 3.4× |

The performance gap is substantial. Pre-COVID, the model is very good — AUC 0.817, AP 0.144, AP-lift nearly 10×. Post-COVID, the model is mediocre — AUC 0.734, AP 0.078, AP-lift 3.4×. The headline 0.794 AUC of the full eight-fold run is a weighted average of these two qualitatively different regimes, and that fact deserves to be visible in any reporting of the headline number.

The feature-importance rankings shift across the break in ways that are diagnostic of what changed.

| Rank | Pre-COVID feature | Importance | Post-COVID feature | Importance |
|---|---|---:|---|---:|
| 1 | `distance_to_nearest_bank_branch` | 0.494 | `lender_hhi_tract_resid` | 0.177 |
| 2 | `lender_hhi_tract_resid` | 0.084 | `top3_lender_share_tract_resid` | 0.103 |
| 3 | `branches_within_5mi` | 0.061 | `distance_to_nearest_bank_branch` | 0.096 |
| 4 | `pct_loans_from_top4_banks_resid` | 0.057 | `top1_lender_share_tract_resid` | 0.084 |
| 5 | `ssbci_active` | 0.043 | `branch_closures_3y_within_10mi` | 0.072 |

Three observations. **Branch access falls dramatically in importance**: from 49% pre-COVID to 10% post-COVID. The post-pandemic lending environment is less determined by physical branch distance than the pre-pandemic environment was, consistent with the documented shift toward digital-first small-business banking that PPP accelerated. **Residualized concentration takes the top slot post-COVID**: the Herfindahl, top-3, and top-1 residuals occupy ranks 1, 2, and 4 respectively. Market structure, not physical access, became the dominant Model-2 signal after 2020. **The SSBCI signal vanishes post-COVID**: all four SSBCI features have zero importance in the post-COVID model. SSBCI 2.0, despite being substantially larger than SSBCI 1.0 in dollar terms, does not produce a detectable effect in the post-COVID test set in this specification. We treat this as either (a) a real null result on SSBCI 2.0 within our short post-COVID window or (b) a measurement-precision problem — state-level annual binary activation is too coarse for the program's actual effect.

The honest framing: **the model's headline 0.794 AUC describes pre-COVID behavior more than post-COVID behavior**, and any deployment of Model 2 for current-year inference should expect the post-COVID 0.734 figure as the relevant operating performance.

### Regime split at h+3 and h+6

We re-ran the regime split at the new horizons. The pattern persists, but the post-COVID gap and the dominance of branch access at long horizons shift substantively.

| Regime / horizon | Pre-COVID AUC | Post-COVID AUC | Gap |
|---|---:|---:|---:|
| h+1 | 0.817 | 0.734 | 0.083 |
| h+3 | **0.847** | **0.825** | 0.022 |
| h+6 | **0.920** | **0.774** | **0.146** |

At h+3, the pre/post gap *narrows* substantially relative to h+1. Both regimes perform better than at h+1, and the post-COVID model is now within striking distance of the pre-COVID model — 0.825 versus 0.847. The longer horizon allows enough structural signal to accrue that the post-COVID period stops being qualitatively a different regime; it becomes a regime where the same drivers operate over a longer window.

At h+6, however, the gap re-opens dramatically. The pre-COVID h+6 model achieves AUC 0.920 — the strongest single-regime headline in the entire study. The post-COVID h+6 model drops to 0.774. Whatever the post-COVID regime is doing, it is doing it on a shorter coherence timescale than six years; trying to forecast 2017–2018 from 2014–2015 features under a post-COVID-style drift gets a much worse result than the pre-COVID equivalent did.

The feature-importance reorganization at long horizons is striking. At h+1 post-COVID, branch access accounted for roughly 10% of model gain. At h+3 post-COVID, it climbs to 45%. **At h+6 post-COVID, `distance_to_nearest_bank_branch` alone accounts for 73% of model gain** — branch access has become so dominant that virtually no other feature contributes meaningful split structure. The mechanism is intuitive: at six years out, in a post-COVID regime where digital lending substituted for physical branches and consolidation accelerated, the only durable structural signal is "how isolated is this tract from any branch at all." Lender-mix and concentration variation reorganize too quickly to matter at that horizon; branch geography is the slowest-moving feature in the panel and accordingly the only feature whose signal survives the long horizon.

The honest framing for the deployment of the long-horizon model is therefore: **at h+6 post-COVID, Model 2 is effectively a branch-access model.** The other levers contribute small ablation effects but are largely decorative on the importance ranking. At h+3, by contrast, the post-COVID regime supports a richer feature mix — branch access dominates at 45%, but residualized concentration, MDI proximity, and branch closures all contribute. The h+3 horizon is the right operational target for a tool that needs to communicate multiple policy levers; h+6 is the right scenario horizon for a tool that needs to communicate "in six years, only branch access still matters as a single tract-level lever."

---

## The NMTC Null Result

We added five New Markets Tax Credit (NMTC) features to the `v3` panel — total NMTC investment dollars per tract over trailing one-, three-, five-, and ten-year windows, plus an NMTC-active flag. The hypothesis was straightforward: NMTC is a federal mission-investment program designed to deploy capital in low-income tracts, and tracts with substantial NMTC investment should show reduced future-desert risk.

All five features hit mean importance ≤ 0.005 across folds. Dropping them caused no measurable AP degradation. We removed them from the cleaned `v4` panel and the policy-slider UI.

The mechanism explanation has three components. First, **selection bias**: NMTC investment is allocated through a competitive Community Development Entity (CDE) process that targets tracts already showing distress signals. The tracts that receive NMTC dollars are non-randomly the tracts with the highest desert risk — making NMTC a proxy for risk rather than an antidote to it, and confounding the predictive signal in the wrong direction. Second, **scale mismatch**: NMTC is project-scale capital ($1M–$50M per project per tract per year), while CRA small-business lending volume in even thin tracts is order-of-magnitude larger. NMTC dollars do not move the underlying CRA lender count that defines our target. Third, **wrong mechanism**: NMTC operates through CDE-mediated equity-like investment, primarily in real estate, community facilities, and large operating businesses. It does not directly stimulate the small-business commercial-bank credit market that the desert target measures.

This is a finding, not a bug. It is informative in two directions: it tells us that NMTC, despite being a flagship federal mission-investment program, does not affect the small-business credit market we are modeling; and it tells us that our model, by failing to find a signal that does not exist in its operational stratum, is behaving with appropriate epistemic humility. We documented the result in `04_final_results.md` and report it here as a deliberate negative finding.

---

## Implications for Policy Intervention

Reading the ablation tables together with the importance ranking and the regime split — and now reading them at multiple horizons — the policy-lever story has improved substantially relative to the h+1 framing.

**At h+3, every intervention-focused lever moves the model.** Residualized concentration remains the largest single ΔAP at −0.064, but MDI / mission lender (−0.028), microlender ecosystem (−0.019), and branch access (−0.017) all contribute meaningfully. Translated to dashboard terms: a county that partners with an MDI, sites a microlender intermediary nearby, or preserves a branch is moving features the model genuinely depends on. At h+1 the same moves were near-zero. The honest answer for the slider story is now "yes, the lever moves the model" rather than "the lever is informational only." This is the most consequential downstream consequence of the horizon switch.

**Residualized lender concentration is still the largest single lever**, and still the hardest to translate into a clean policy slider. We cannot meaningfully tell a county "lower your residualized Herfindahl by ten points" — the residualization step subtracts the lender-count-explained component, and the remaining variance reflects market-structure depth that takes years to develop. The honest dashboard treatment is to label the slider "residualized concentration" and explain in adjacent prose that this is "lender-mix diversity holding lender count fixed." But because the other intervention-focused levers are now also genuinely responsive, the dashboard no longer has to lean exclusively on this one feature class for the intervention story.

**Branch access is now genuinely load-bearing on AP at h+3 (ΔAP −0.017) and dominates by importance and by ablation at h+6 post-COVID (73% of model gain).** It supports clean policy mechanisms (branch-retention agreements, mobile lending units, replacement siting after closures, state-level branch-retention regulation) and has documented Federal Reserve evidence behind it. The h+1 ablation made it look substitutable; the h+3 and h+6 ablations make it look essential. The right deployment framing is: branch access is the foreground lever, especially for long-horizon scenarios.

**Mission-lender presence (MDI) gains substantial weight at h+3 (ΔAP −0.028, the second-largest lever after concentration).** This is the single largest lever-importance shift between horizons. At h+1 the MDI features were ablation-neutral. At h+3 they are demonstrably predictive. The interpretation: MDI ecosystem effects accrue over multi-year windows — partnership lending, certification cascades, deposit relationships — and a one-year horizon under-counts them. The dashboard's MDI slider can now honestly tell users "moving this lever moves the forecast."

**Microlender ecosystem also gains weight at h+3 (ΔAP −0.019).** The 48% geocoding hit rate (§ Limitations) still bounds how strong this lever can plausibly be, but the directional finding is now positive rather than slightly-negative. A future iteration with cleaner geocoding would likely strengthen this further.

**SSBCI is the lone intervention lever that does not benefit from horizon extension.** Dropping the four SSBCI features improves AP at h+3 (+0.013) and at h+6 (+0.006). The state-year overlay is too coarse to add cohort-level variance. The dashboard should treat SSBCI as descriptive context (which states are program-active in which era windows) rather than as a predictively load-bearing lever.

The right product-level framing is therefore: at the h+3 primary horizon, branch access, residualized concentration, MDI, and microlender are all real levers — moving them changes the model's prediction in measurable ways. SSBCI is descriptive context. At the h+6 long-horizon scenario, branch access is overwhelmingly dominant, and the dashboard should communicate that "in six years, only branch access still matters as a single tract-level lever" honestly. The horizon toggle in the dashboard makes this hierarchy directly inspectable: users see the ablation table change as they switch between h+3 and h+6, and the lever-importance order rearranges visibly.

---

## Limitations and Future Work

**The COVID regime shift is the dominant constraint on generalization.** A model whose pre-COVID AUC is 0.817 and post-COVID AUC is 0.734 is not a single model; it is two models averaged together. Future work should either fit regime-specific models with explicit transition handling or include a `post_pandemic` interaction term in the feature set. The current cleaned Model 2 should be deployed with a stated operating-performance figure of 0.734 AUC for current-year inference, not the 0.794 average.

**Residualization makes features harder to interpret in a slider UI.** The residual-against-cohort framing is methodologically clean but pedagogically heavy. Phase-2 work should explore whether a simpler interpretable cohort-relative score (e.g., quantile-within-cohort) preserves enough of the residualization benefit to justify the readability gain.

**The RSSD-to-CRA crosswalk has approximately 5% unmatched volume.** That residual is concentrated in long-tail community lenders and acquisition-affected institutions. The community-bank-share and top-4-share features are accordingly slightly noisier than they appear in the headline numbers. A phase-2 manual-review pass on the [75, 90) confidence band would close most of the residual.

**Geocoding hit rates are uneven.** CDFI was 87%, MDI was 100% via the SoD shortcut, microlenders were 48%. The microlender ecosystem feature is therefore the noisiest in the panel — and not coincidentally, it was the feature that the ablation showed actively hurt the model. A phase-2 pass on SBA microlender addresses with a paid geocoder (Google or Mapbox) at small cost would likely lift hit rates above 80% and is worth pursuing.

**SSBCI activation is encoded as a state-year binary.** This is appropriate for the data we have but loses program-intensity information. Phase-2 work should explore Treasury's state-level allocation dollar amounts and participating-lender counts as continuous intensity measures, particularly for the post-COVID SSBCI 2.0 era.

**NMTC longer-window features may yet carry signal.** Our specification used trailing 1, 3, 5, and 10-year windows. NMTC investments operate on multi-decade horizons in some neighborhood-development contexts; a 15-or-20-year cumulative measure was outside the panel window but worth testing in a longer-horizon extension.

**County-level concentration as an alternative.** Our Herfindahl and top-share features are tract-level. Many lending decisions are made at the county or MSA level, and a county-aggregated concentration feature might carry more signal with less leakage exposure. This is the most promising single robustness check we did not run.

---

## Conclusion

A defensible influenceable-only model of small-business credit-desert formation is achievable, and at the operationally relevant prediction horizons it is meaningfully stronger than the original h+1 specification suggested. The Round 7 retrained Model 2 achieves mean test AUC 0.820 and AP 0.282 (lift 11.1×) at h+3 across an eight-fold walk-forward partition, and AUC 0.862 / AP 0.464 (lift 19.5×) at h+6 across a six-fold partition. Both clear the strong-signal threshold by wide margins; both improve on the legacy h+1 numbers (AUC 0.794, AP 0.129, lift 6.7×) rather than degrading. The horizon switch was not a methodological retreat — it was a horizon-appropriateness correction that revealed structural signal which the one-year forward horizon had been swamping with year-to-year noise.

The model's strongest signal still lives in residualized lender concentration — a methodologically clean but interpretively heavy feature class — but at h+3 the intervention-focused levers (branch access, MDI presence, microlender ecosystem) all contribute non-trivial AP impact in the ablation, which they did not at h+1. The dashboard's policy-slider story therefore moves from "informative as ranking" to "responsive to lever movement": when a user toggles between h+3 and h+6, the lever-importance hierarchy visibly reorganizes, and at h+6 post-COVID branch access alone accounts for 73% of model gain.

Performance is uneven across the COVID break at every horizon, with the gap narrowing at h+3 (AUC 0.847 vs 0.825) and re-opening at h+6 (0.920 vs 0.774); honest deployment communicates those regime gaps rather than hiding them. The two-layer × two-horizon architecture — diagnostic Model 1 for *where* and influenceable Model 2 for *what could change*, both at h+3 (operational forecast) and h+6 (long-horizon scenario), presented in distinct color signatures and never collapsed into a single score — is the right architectural decision for a tool that needs to inform both prediction and intervention.

The work this brief documents is not the last word on the problem; it is a defensible operating baseline against which subsequent rounds, with cleaner geocoding, longer NMTC windows, regime-specific specifications, and county-level concentration alternatives, can be measured.

---

[^1]: Nguyen, H. Q. (2017). *Out of Sight, Out of Mind: Nearby Branch Closures and Small Business Growth*. Federal Reserve Board Finance and Economics Discussion Series. https://www.federalreserve.gov/econres/feds/out-of-sight-out-of-mind-nearby-branch-closures-and-small-business-growth.htm

[^2]: Federal Financial Institutions Examination Council, *Community Reinvestment Act Final Rule* (October 2023). The rule's small-business lending evaluation framework provides the regulatory foundation for the desert-formation construct used in this work.
