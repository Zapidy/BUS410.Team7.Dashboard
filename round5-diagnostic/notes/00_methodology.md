# Round 5 — Methodology Brief

This document is the operating plan for the Round-5 rebuild. It sets temporal scope, names the leakage failure modes Round 4 left on the table, lists the data sources to ETL, the features to engineer, and the validation framework. Read this before writing any code.

---

## 1. Recommendation: 15-year scope, 2009–2024

**Pick 15 years (2009–2024). Reject 21 years.** Reasons, in order of weight:

### 1.1 Regulatory regime changes punish a 21-year window

A 21-year span (2003–2024) crosses four regulatory regimes that *redefine the variables*, not just shift their distribution:

- **Pre-crisis (2003–2007):** subprime expansion, no Dodd-Frank, no CFPB, no QM rule. Lender behavior in this period reflects an environment that no longer exists.
- **Crisis (2008–2010):** bank failures (140 in 2009 alone), TARP, FDIC absorptions. The *identity* of lenders in any given tract changes discontinuously.
- **Dodd-Frank era (2011–2017):** Volcker, CFPB, mortgage QM rule, CRA exam revisions, expanded HMDA.
- **EGRRCPA + post-2018 (2018–2024):** HMDA reporting threshold raised to ≥25 closed-end loans (many small lenders fall out of the data); CRA asset thresholds adjusted upward.

A model that trains on 2003 expects a 2024 lender mix that doesn't exist. 15 years (2009–2024) is *one* regulatory regime in two phases, not four.

### 1.2 ACS 5-year first exists in 2009

The American Community Survey 5-year tract estimates first cover 2005–2009 (released 2010). Pre-2009 demographics rely on the 2000 decennial only — a single static snapshot per tract for the entire pre-2009 period. Including 2003–2008 in the panel means six years of demographics that cannot move. The model would learn that "demographics never change" is a feature of those years, then fail to generalize.

### 1.3 HMDA reporting threshold step in 2018

The 2018 EGRRCPA raised HMDA reporting thresholds; an estimated ~5,000 small institutions stopped reporting. Within a 15-year window this is a *single* modeled transition (a `post_2018_hmda` flag). Within a 21-year window you also have the 2010 Dodd-Frank threshold expansion as a second transition — twice the threshold-shock work for diminishing data quality.

### 1.4 Walk-forward folds are still abundant at 15 years

15 years gives 8 walk-forward folds with meaningful train + test sizes:

| Fold | Train | Validate | Test (3-yr horizon) |
|---|---|---|---|
| 1 | 2009–2014 | 2015 | 2016–2018 |
| 2 | 2009–2015 | 2016 | 2017–2019 |
| 3 | 2009–2016 | 2017 | 2018–2020 |
| 4 | 2009–2017 | 2018 | 2019–2021 |
| 5 | 2009–2018 | 2019 | 2020–2022 |
| 6 | 2009–2019 | 2020 | 2021–2023 |
| 7 | 2009–2020 | 2021 | 2022–2024 |
| 8 | 2009–2021 | 2022 | 2023–2024 (partial) |

Eight folds is enough to report a *distribution* of out-of-sample AUC, not just a point estimate.

### 1.5 The COVID problem still exists, but is contained

PPP (April 2020 – May 2021) inflated SBA loan counts by ~10x. With a 15-year window, COVID is two adjacent years that need explicit handling (either exclusion from training, a `covid_era` regime flag, or treating PPP as a separate target leak). Within a 21-year window you also have the 2008-crisis distortion — two simultaneous regime shocks to handle. Pick one.

---

## 2. Leakage taxonomy — failure modes Round 4 left open

This is where the bulk of the methodological gain comes from. Round 4 has known leakage in at least 5 of these 6 categories.

### 2.1 Definitional / regulatory leakage
The model learns relationships defined by a regulatory regime that no longer applies at test time. Mitigation: 15-year scope (§1.1), regime-flag features, robustness-checks across folds.

### 2.2 Feature lookahead — ACS 5-year is the worst offender
ACS 5-year estimates labeled "2015–2019" are released in 2020. Using "2017 ACS 5-year" features to predict 2017 desert formation is using 2017–2021 data — a 2-to-4-year forward leak. Round 4 documentation does not address this. Mitigation: lag every ACS 5-year vintage by **at least its end-year minus its label-year**, i.e. always use the most recent 5-year ACS that ended *strictly before* the prediction year.

### 2.3 Feature-publication lag — CRA, HMDA, SBA
- **CRA**: year-T disclosures release in autumn of year T+1
- **HMDA**: year-T LAR releases in spring of year T+1 (TRID modernization sometimes pushes to autumn)
- **SBA**: year-T loans available within ~30 days

Mitigation: enforce `feature_year ≤ prediction_year - 1` for CRA/HMDA, `≤ prediction_year` for SBA. Encode the lag as a `feature_age_years` column for transparency.

### 2.4 Target leakage in lender-behavior features
"Branch-count change in year T" includes the branches that closed *because* the tract was already failing. "Lender exits in year T" similarly captures exits that are caused by, not predictive of, desert formation. Round 4's `cra_lender_exits_1yr` is exposed to this.

Mitigation: compute behavioral features as 3-to-5-year *trailing* change (lender-count Δ between year T-5 and T-2), so the most recent year is excluded from the feature window. Loss of immediacy, gain of clean separation.

### 2.5 Cross-tract spatial leakage in cross-validation
Two adjacent tracts in the same county share demographics, lenders, and economic shocks. Random K-fold across tracts puts neighbors in train and test simultaneously — the model effectively memorizes the county and reports inflated AUC.

Mitigation: walk-forward by **year** is the primary defense. As a robustness check, run **leave-one-state-out** and **leave-one-county-out** CV; report the AUC distribution across all three schemes.

### 2.6 Survivor bias in CRA reporters
CRA only requires banks above an asset threshold to report. The threshold has risen with inflation; banks crossing it appear/disappear from the panel without changing behavior. A tract appearing to "lose CRA lenders" between 2010 and 2020 may simply reflect threshold drift.

Mitigation: identify the **stable reporter cohort** (banks present every year of the panel), compute lender-count features only against that cohort, and add a separate `non_stable_reporter_count` covariate so the threshold-drift signal is observable but not confounding.

---

## 3. Datasets to ETL

| Source | Years | Volume | Geo | Status |
|---|---|---|---|---|
| **FFIEC HMDA LAR** (loan-level) | 2009–2024 | ~17M rows/yr × 15 yr ≈ 250M rows | Tract-coded | New ingestion |
| **FFIEC CRA disclosure D1/D2** | 2009–2024 | ~600k rows/yr | Lender × tract × year | Parser exists ([round4/cra_raw/](../../round4/cra_raw/)); extend backfill |
| **SBA 7(a) and 504 loans** | 2009–2024 | ~150k loans/yr | Borrower address → geocode to tract | New |
| **FDIC SoD** (full panel) | 2009–2024 | ~80k branches/yr | Branch lat/lng → tract | API exists ([round4/fetch_fdic_sod_cache.sh](../../round4/fetch_fdic_sod_cache.sh)); extend |
| **FDIC failed bank list** | 2009–2024 | ~500 events | Bank-level | New |
| **FFIEC NIC institution structure** | 2009–2024 | quarterly snapshots | Bank-level | New |
| **CDFI Fund awards / certifications** | 2009–2024 | ~10k records | Investee → geocode | New |
| **Census ACS 5-year** | 2009 (covering 2005–2009) – 2023 (covering 2019–2023) | tract panel | Tract-coded | New, lag-aware ingestion |
| **Census Bureau tract relationship files** | 2000↔2010, 2010↔2020 | lookup | – | Pulled (no account required) |
| **USDA RUCA codes** (rural-urban continuum) | 2010, 2020 | tract-coded | – | New |
| **EIG Distressed Communities Index** | 2010–2024 | tract-coded | – | New |
| **Opportunity Zones designation** (2017) | static | tract-coded | – | New |
| **Persistent poverty counties** (USDA) | static | county-coded | – | New |

---

## 4. Feature additions Round 4 doesn't have

### 4.1 HMDA-derived (the biggest single gain)
- Mortgage application count per tract per year
- Approval rate
- Denial reasons distribution (debt-to-income, credit history, collateral, etc.)
- Median origination amount
- Lender-type mix: large bank / community bank / credit union / non-bank / fintech
- Approval-rate disparity index across borrower-race categories
- 3-year change in approval rate

### 4.2 SBA-derived
- 7(a) and 504 loan count per tract per year
- Loan amount per capita
- Loan size distribution
- 5-year cumulative SBA lending intensity

### 4.3 Lender-shock features
- Branch closures per tract per year (FDIC SoD year-over-year diff at the branch level)
- FDIC bank failures affecting tract (bank-id × branch-id mapping)
- Acquisition events (NIC structure data)
- Net new branches (openings − closures)

### 4.4 Place-based controls Round 4 lacks
- Rural-urban continuum code (RUCA, 1–10)
- Persistent poverty county flag
- Opportunity Zone designation flag
- EIG distressed-community quintile
- Tribal area / Native land flag
- Coastal / non-coastal

### 4.5 Macro / cyclical controls
- National unemployment rate (year)
- 10-year Treasury yield (year-end)
- Bank consolidation rate (% of charters merged or failed in year)
- COVID-era flag (2020, 2021)

### 4.6 Spatial features
- Spatial lag of all key features (county-level mean, weighted by inverse distance)
- Risk in adjacent tracts (lagged target, must use prior-year only to avoid leakage)
- Drive-time isochrone to nearest active branch (computed from FDIC SoD lat/lng)

---

## 5. Target redefinition

Round 4 uses a binary "becomes a desert in next H years." Three improvements:

### 5.1 Continuous target
Predict the lender-presence index directly. A regression model preserves ordinal information and produces a richer ranking. Convert to binary at policy time, not training time.

### 5.2 Multi-flavor target
Three correlated but distinct desert types:
- **Branch desert**: nearest active branch >X miles
- **Origination desert**: loan origination volume per capita below Yth percentile
- **Service desert**: < N active CRA lenders

Train a single model with a multi-output head, or three separate models and ensemble. Predicting all three jointly should improve generalization (Round 4 collapses signal across all three into one flag).

### 5.3 Time-to-event
Survival analysis (Cox or DeepSurv) treats desert formation as a hazard, naturally handles right-censoring (tracts that haven't yet become deserts), and produces calibrated horizon-specific probabilities from a single model.

---

## 6. Validation framework

### 6.1 Primary: walk-forward by year
Eight folds (§1.4). Report mean ± std AUC, mean Brier, mean AP-lift, calibration slope.

### 6.2 Robustness: spatial blocking
Re-run the *most recent* fold (train 2009–2021, test 2022–2024) under:
- Leave-one-state-out CV (51 folds)
- Leave-one-large-MSA-out CV (~50 folds across the largest MSAs)
- Tract-random K-fold (the *naive* baseline — should produce a *higher* AUC; the gap is the spatial-leakage tax)

### 6.3 Calibration
Reliability diagrams in deciles. Brier score decomposition (reliability + resolution + uncertainty). Spiegelhalter's z-test.

### 6.4 Decision-curve analysis
For a policy artifact, AUC isn't the deliverable. Net benefit at threshold = `(TP_rate × prevalence) − (FP_rate × (1 − prevalence) × (threshold / (1 − threshold)))`. Report net benefit across thresholds 0.05–0.50 against a "treat all" and "treat none" baseline. This tells you *at what risk threshold the model is actually useful*.

### 6.5 Top-N precision
At each fold, report precision at top 100, top 500, top 1000 tracts ranked by predicted risk. This is the metric that maps directly to "if we used this to flag tracts for outreach, how many flags would be right?"

---

## 7. Things easy to overlook

These are the "wait, what?" failure modes that crash this kind of project late.

### 7.1 Census tract vintage harmonization
Tract polygons re-draw every decennial (2010 → 2020 most recent). FIPS code `36061003500` in 2008 is **not the same polygon** as in 2018. Without crosswalking, a 15-year tract panel is silently corrupted. Use the **Census Bureau relationship files** (`data/raw/census-geo/tract_xwalk_2000_2010.txt` and `tract_xwalk_2010_2020.txt`, both already pulled) — these are the canonical source and do not require an NHGIS / IPUMS account. Choose a target vintage (recommend **2020**) and project all years onto it via population-weighted apportionment using the `pop_overlap` column.

### 7.2 PPP distortion in SBA
PPP loan volume in 2020–2021 dwarfs all prior SBA lending combined. Either:
- (a) Use only 7(a) and 504 (exclude PPP entirely)
- (b) Treat PPP as a separate dataset / separate feature
- (c) Add a `covid_era` interaction term

Recommend (a). PPP is a one-time regime shock, not a persistent supply-side signal.

### 7.3 The "credit desert" definition itself is contested
Round 4's exact threshold is in code, not in docs. We should pin a *transparent, citable* definition (e.g., FRBSF 2018, Friedline & Despard 2017, or Faber & Rifkin 2017) before training anything. The choice of threshold is a stronger driver of final results than most of the modeling decisions.

### 7.4 Selection bias against fintechs
CRA captures only deposit-taking institutions. HMDA captures non-bank mortgage lenders. Neither captures: BNPL, online consumer lending, fintech small-business lending. A "credit desert" by current data may have heavy fintech presence we cannot see. Document this as a caveat; consider augmenting with CFPB consumer complaint volumes per tract as a proxy for fintech activity (complaints are a poor proxy but better than zero).

### 7.5 Survivor bias in tracts themselves
Tracts that *split* between the 2010 and 2020 boundaries vs. those that don't are not a random sample — split tracts are usually high-growth suburban tracts. Attributing a "credit desert prediction" to a 2010-vintage tract and crosswalking to 2020 averages over those splits in ways that bias toward stable tracts.

### 7.6 Geocoding strategy for SBA addresses
~2M SBA addresses to geocode. Census Geocoder is free but rate-limited (~10k/day batch). Recommend:
1. Census Geocoder for the bulk batch (free, slow)
2. Cache aggressively (most addresses repeat)
3. Fall back to ZIP-tract crosswalk for failures (HUD CROSSWALK API)
4. Manual review for addresses that fail both

Budget 3–5 days end-to-end.

---

## 8. Recommended round-5 file layout

```
round5/
├── notes/
│   ├── 00_methodology.md       (this file)
│   ├── 01_target_definition.md
│   ├── 02_etl_log.md            (running log of what was pulled and when)
│   └── 03_findings.md           (rolling results from each walk-forward fold)
├── etl/
│   ├── hmda/                    (one script per source, produces parquet under data/processed/)
│   ├── cra/
│   ├── sba/
│   ├── fdic/
│   ├── acs/
│   └── crosswalk/               (tract vintage harmonization)
├── data/
│   ├── raw/                     (source files, gitignored)
│   ├── processed/               (per-source tract-year parquets)
│   └── crosswalks/              (NHGIS, GeoCorr, ZIP-tract)
├── features/
│   └── build_panel.py           (joins all processed sources into a tract-year panel)
├── train/
│   ├── walk_forward.py
│   └── calibration.py
├── models/                      (trained model artifacts per fold)
└── diagnostics/
```

---

## 9. Phased plan

**Phase 0 — alignment (this doc).** Done.

**Phase 1 — ETL (5–8 days):** HMDA, CRA full backfill, FDIC extend, SBA + geocoding, ACS lag-aware. Acceptance: a single tract-year parquet covering 2009–2024 with all six sources joined, leakage-clean.

**Phase 2 — features + target (3–4 days):** Tract-vintage harmonization, target redefinition, place-based controls, spatial features.

**Phase 3 — walk-forward training (3–5 days):** 8 folds, three model variants (XGBoost / LightGBM / survival), calibration, decision-curve, top-N precision.

**Phase 4 — diagnostics + writeup (2–3 days):** robustness checks, leakage audit, ablation tables, rendered figures.

**Phase 5 — refresh showcase (2 days):** new map, this time with confidence intervals from the walk-forward distribution overlaid.

**Total: 15–22 working days of focused effort.** Ship Phase 1 first; everything depends on it.
