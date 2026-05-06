# Round 7 — Final Results

## Two-Layer Architecture (matches the original handoff)

| Layer | Role | Model | Features | Mean AUC | Mean AP | Lift | Std AUC |
|---|---|---|---|---|---|---|---|
| Model 1 — Diagnostic | "Where is risk high?" | round5 XGBoost | 39 (ACS + CRA + FDIC + HMDA) | **0.857** | 0.172 | 9.25× | 0.044 |
| Model 2 — Influenceable | "Which lending-environment changes plausibly improve access?" | round7 XGBoost (cleaned) | 20 (residualized concentration + branch + MDI + SSBCI) | **0.794** | 0.129 | 6.7× | 0.047 |

Both clear the AP ≥ 0.10 STRONG-signal threshold. Model 2 trades 0.06 AUC for full leakage defensibility.

## Iteration Path (block-of-clay → cleaned)

| Iteration | Variant | Features | AUC | AP | Notes |
|---|---|---|---|---|---|
| v1 | 14 influenceable, year-T concentration | 14 | 0.817 | 0.153 | Initial; leakage-vulnerable |
| v2 | + trailing 5-to-2y means | 17 | 0.841 | 0.205 | Trailing means improved AP — first leakage-mitigation evidence |
| v3 | + NMTC + year-precise MDI + SSBCI | 25 | 0.826 | 0.155 | New features added stability (std 0.060) but not AP |
| v3 prune | top-10 from v3 by importance | 10 | 0.834 | 0.145 | Found elbow at k=10 |
| **v4 cleaned** | **NMTC dropped + concentration residualized** | **20** | **0.794** | **0.129** | **Headline — defensible** |
| v4 prune | top-7 from v4 by importance | 7 | 0.780 | 0.129 | Cleaned elbow |

## Per-fold story (v4 cleaned)

| Fold | Test years | AUC | AP | Lift |
|---|---|---|---|---|
| F1 | 2016–17 | 0.810 | 0.135 | 7.9× |
| F2 | 2017–18 | 0.841 | 0.130 | 8.6× |
| F3 | 2018–19 | 0.850 | 0.153 | 10.3× |
| F4 | 2019–20 | 0.829 | 0.164 | 11.2× |
| F5 | 2020–21 | 0.713 | 0.110 | 3.9× ← COVID regime shift |
| F6 | 2021–22 | 0.751 | 0.160 | 4.3× |
| F7 | 2022–23 | 0.780 | 0.094 | 3.7× |
| F8 | 2023–24 | 0.780 | 0.084 | 3.7× |

**6 of 8 folds clear AP ≥ 0.10**. Std AUC 0.047 — better stability than v3 (0.060).

## Top Features (cleaned Model 2, mean XGBoost gain across folds)

| Rank | Feature | Importance | Type | Policy lever? |
|---|---|---|---|---|
| 1 | **distance_to_nearest_bank_branch** | **0.369** | branch | ✅ Strong |
| 2 | lender_hhi_tract_resid | 0.097 | residualized concentration | ⚠️ Indirect |
| 3 | pct_loans_from_top4_banks_resid | 0.066 | residualized concentration | ⚠️ Indirect |
| 4 | pct_loans_from_credit_unions_resid | 0.049 | residualized concentration | ⚠️ Indirect |
| 5 | **ssbci_active** | **0.048** | state policy | ✅ Strong |
| 6 | top3_lender_share_tract_resid | 0.046 | residualized concentration | ⚠️ Indirect |
| 7 | branches_within_5mi | 0.041 | branch | ✅ Strong |
| 8 | pct_loans_under_250k_resid | 0.040 | residualized loan-size | ⚠️ Indirect |
| 9 | mdi_branches_within_10mi | 0.037 | mission lender | ✅ Strong |
| 10 | pct_loans_from_community_banks_resid | 0.029 | residualized concentration | ⚠️ Indirect |
| 11 | nearest_mdi_branch_miles | 0.029 | mission lender | ✅ Strong |
| 12 | top1_lender_share_tract_resid | 0.025 | residualized concentration | ⚠️ Indirect |
| 13 | branch_closures_3y_within_10mi | 0.024 | branch | ✅ Strong |
| 14 | ssbci_program_count | 0.024 | state policy | ✅ Strong |
| 15-20 | mdi_branches_within_25mi, pct_loans_under_100k_resid, microloan_intermediary_within_25mi, mdi_active_in_county, ssbci_n_capital_programs, ssbci_2_0_active | each <0.022 | mixed | mixed |

**Branch access alone (rank 1, 7, 13) accounts for ~43% of model importance.** That's the cleanest, most policy-leverable result of the entire study.

## Negative Findings (real, not bugs)

### NMTC investment dollars don't predict desert formation

All 5 NMTC features had mean importance ≤ 0.005 in v3. Reasons:
1. **Selection bias** — NMTC went where deserts were already forming.
2. **Scale mismatch** — NMTC is project-scale capital ($M/yr/tract); CRA lending volume is order-of-magnitude larger.
3. **Wrong mechanism** — NMTC operates through CDEs, not commercial bank lending; it doesn't move our target's underlying lender count.

**Action**: dropped from training panel and slider UI. Worth writing up as a finding.

### Concentration features lose ~40% of their variance to residualization

After regressing top1/top3/HHI/community-bank-share against `n_cra_lenders` within (year × peer_group):
- top3 share: residual std = 0.55× of original
- HHI: 0.57×
- top1: 0.71×
- community-bank share: 0.92× (mostly clean already)
- credit-union share: 0.36× (heavily lender-count-driven)

The residualized features still carry signal in v4 (4 of top 7 features are residualized), but the leakage-vulnerable component has been removed.

## Auxiliary: Bolt-on (round5 + cleaned round7, NOT the headline)

| Metric | Round 5 alone | Bolt-on | Δ |
|---|---|---|---|
| Mean test AUC | 0.857 | **0.889** | **+0.032** |
| Mean test AP | 0.172 | 0.175 | +0.003 |

Translation: the cleaned round7 features add ~0.03 AUC discriminative power to the diagnostic baseline, but only marginal AP. They're useful for ranking but not for top-K precision.

This is **auxiliary**, not the centerpiece — it contradicts the two-layer story by mixing the layers.

## Policy Slider Mapping

| Slider lever | Maps to model feature(s) | Combined importance | Realistic policy mechanism |
|---|---|---|---|
| **Branch access (preserve / restore)** | distance_to_nearest_bank_branch + branches_within_5mi + branch_closures_3y_within_10mi | **0.434** | Banks, local coalitions, branch-retention agreements |
| **State activates SSBCI** | ssbci_active + ssbci_program_count + ssbci_2_0_active + ssbci_n_capital_programs | 0.083 | Treasury allocates; states accept and run programs |
| **MDI expansion / preservation** | mdi_branches_within_10mi + mdi_branches_within_25mi + nearest_mdi_branch_miles + mdi_active_in_county | 0.099 | FDIC certifies; partnerships, local MDI charters |
| **Microlender ecosystem** | microloan_intermediary_within_25mi | 0.016 | SBA designates intermediaries; states can match |
| ~~NMTC funding~~ | ~~nmtc_*~~ | ~~0~~ | **Dropped — model shows no signal** |

**Headline slider story**: branch-access preservation is the dominant lever in this model. SSBCI activation and MDI expansion are real-but-modest secondary levers. The microlender ecosystem matters at the margins.

## Honest Caveats for the Writeup

1. **COVID regime shift** — F5–F8 (test years 2020+) show notably weaker performance than F1–F4 (test 2016–2019). Mean AUC drops from 0.83 (pre-COVID) to 0.76 (post-COVID). Std AUC across all 8 folds = 0.047, exceeding the 0.044 round5 std.

2. **Selection bias in policy features** — SSBCI activation correlates with broader macro-era effects, not just the policy itself. The era windows (2011-2017, 2022-2024) coincide with post-recession recovery and post-COVID recovery; some of `ssbci_active`'s signal is era, not program.

3. **NMTC null result is informative** — for a small-business credit-desert model, federal mission-investment dollars don't predict where commercial-bank lending dries up. This is consistent with the framing that NMTC operates in a different lending stratum (CDE-mediated equity-like investment, not commercial bank credit).

4. **Branch access is the clearest signal** — and also the most actionable: state-level branch-retention policies, mobile lending units, and branch-closure mitigation are real, well-understood policy mechanisms with documented effects (Federal Reserve research cited in `Policy Layer Research.md`).

5. **Residualization has tradeoffs** — removing the n_cra_lenders-explained component of concentration features makes them harder to interpret in the slider UI. We'd say "residualized HHI went up" rather than "lender concentration increased". Worth a sentence in the methods section.

## What the model says about the original hypothesis

> "Show what counties, states, and local lending ecosystems can plausibly influence."

**Answer (cleaned Model 2)**:
1. **Physical branch access matters most.** Policies that preserve or restore branch access in declining tracts have the biggest plausible model effect.
2. **State credit-support policies matter modestly.** SSBCI activation correlates with reduced future-desert risk in this model.
3. **Mission-lender presence (MDI) helps modestly.** Year-precise MDI proximity is rank-9 — meaningful but secondary.
4. **Lender-mix composition matters but is harder to defend.** Residualized concentration features survived the leakage cut and contribute, but interpreting "shift the share away from top-4 banks" as a policy is harder than interpreting "preserve a branch."
5. **NMTC capital deployment doesn't show up in this model.** Different lending stratum — federal CDE-mediated investment doesn't move commercial-bank-lender counts.
