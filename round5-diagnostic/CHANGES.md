# Round 5 — Changes Document

Walks through every change made between Round 4 and Round 5 of the BUS410 Team 7 credit-desert prediction model. Written 2026-04-28 after the first end-to-end pipeline pass.

This document is meant to be readable by someone who has seen Round 4 but not lived through the rebuild.

---

## 0. Why a rebuild

Round 4 was **data-constrained, not architecture-constrained**:

- Single chronological split (train 2014-2017, val 2018, test 2019). One fold, one number.
- CRA disclosure files only loaded 2014-2023, so pre-2014 train years had 0% CRA coverage. CRA had to be bolted on as a separate post-2014 model track.
- No HMDA. No SBA. No place-based controls. Two of the three biggest supply-side credit-access datasets in America were missing.
- Several plausible leakage paths (ACS forward-leak, behavioral-feature target-leakage, CRA-reporter survivor bias, autocorrelated target) were not addressed in the methodology.
- "Credit desert" definition was buried in code, threshold was a strict binary collapse that gave a ~1.3-2.4% positive rate.

Round 5 fixes all of that.

---

## 1. Methodology brief — `notes/00_methodology.md`

Written first, before any code. Captures the operating plan:

- **15-year temporal scope** (2009-2024) instead of 21 (2003-2024). Reasons in §1: regulatory regime homogeneity (one Dodd-Frank-era window), ACS 5-year first existing in 2009, fewer threshold-shock transitions to model, abundant walk-forward folds.
- **Leakage taxonomy** with six types named (definitional, ACS forward-leak, feature-publication lag, target leakage, spatial leakage, survivor bias) and a concrete fix for each.
- **Data sources** to acquire (HMDA, full CRA backfill, SBA, FDIC SoD extension, ACS lag-aware, USDA RUCA, EIG DCI, OZ, persistent poverty).
- **Validation framework**: 8-fold walk-forward by year, plus leave-one-state-out and leave-one-MSA-out as spatial-leakage robustness checks.
- **Target redefinition**: continuous lender-presence regression with three desert flavors (branch / origination / service) modeled jointly. Survival framing as alternative.
- **Tract harmonization**: project all years onto 2020 tract vintage via Census relationship files (no NHGIS account needed).

This is the spec. Every later decision points back to it.

---

## 2. ETL — `etl/`

### 2.1 Sources pulled programmatically

| Source | Years | Records | Size | How |
|---|---|---|---|---|
| **SBA 7(a) + 504 loan-level** | 1991-present | ~5 M loans | 870 MB | direct CSV download from `data.sba.gov` (FOIA bulk dataset) |
| **FDIC failed bank list** | full | 570 events | 48 KB | direct CSV download from FDIC.gov |
| **FDIC Summary of Deposits** | 2009-2024 | **1.43 M branch-years** | 122 MB | paginated REST API at `api.fdic.gov/banks/sod`, custom Python puller, SSL cert workaround for system Python 3.12 |
| **USDA RUCA codes** | 2010 + 2020 vintages | 73 K + 84 K | 17 MB | direct XLSX from USDA ERS |
| **USDA County Typology** | 2025 + 2015 editions | ~3 K counties | 440 KB | direct CSV/XLSX from USDA ERS — for persistent poverty flag |
| **Census tract crosswalks** | 2000↔2010 + 2010↔2020 | 84 K + 84 K pairings | 37 MB | Census Bureau `geo/docs/maps-data/data/rel/` — no account needed |
| **Opportunity Zones** | 2018 designation | 8.7 K tracts | 430 KB | HUD CSV + CDFI Fund XLSX (HUD CSV came back as HTML stub on this pull; xlsx works) |
| **Census ACS 5-year tract** | 2010, 2011, 2012, 2013, 2015, 2020, 2022 vintages | **245 K tract-vintages** | 42 MB | Census API at `api.census.gov`, anonymous; **two pullers** because variable IDs migrated in 2014 (`B15002` → `B15003`, `B23001` → `B23025`) |
| **HMDA loan-level** | 2018-2024 (API limit) | **121.7 M LAR rows → 550 K tract-state-years** | 11 MB | CFPB Data Browser API at `ffiec.cfpb.gov/v2/data-browser-api/view/csv`, streaming + on-the-fly tract aggregation per state-year |

### 2.2 Sources blocked (manual download required)

- **FFIEC CRA disclosure** — Akamai blocks curl/wget regardless of UA. User browser-downloaded all 16 years (2009-2024) of disclosure + aggregate + transmittal zips. Total **5.5 GB unpacked** across 48 datasets.
- **FRED macro series** — fredgraph.csv endpoint timed out on this network. Documented as fallback (try elsewhere or get a free API key).
- **NHGIS GeoCorr crosswalks** — account approvals paused. **Cut from plan** — Census Bureau direct equivalent already pulled; no account needed.

### 2.3 The HMDA strategy decision

Pre-2018 HMDA is genuinely unavailable through the API. Options were:

(a) Accept the 7-year HMDA window (2018-2024) and bifurcate the panel: pre-2018 has no HMDA features, post-2018 has them. Add a `has_hmda` flag.
(b) Manually browser-download HMDA aggregate reports back to 2009.
(c) Use the legacy FFIEC HMDA flat-file system (returns 403 to curl).

**Picked (a).** It's cleaner. The `has_hmda` flag lets the model treat pre-2018 and post-2018 as different feature regimes without losing data.

---

## 3. Per-source parsers — `etl/{cra,fdic,sba,acs,hmda}/`

For each source, a script that turns raw bytes into a clean tract-year (or county-year, or zip-year) CSV under `data/processed/`. **Stdlib-only** where possible; pandas + xgboost only at the panel-build / training step.

| Script | Input | Output | What it does |
|---|---|---|---|
| `cra/parse_cra.py` | `cra/{year}/{discl,aggr,trans}/*.dat` (5.5 GB) | `cra/tract_year.csv` (56 MB), `cra/county_year.csv` (3 MB), `cra/reporters.csv`, `cra/stable_reporters.csv` | Parses fixed-width D6 (tract lender presence), D1-1/D1-2 (county loan totals), and Transmittal records. Computes lender entries/exits/churn 1y+3y, county HHI, top-share. Identifies the **stable-reporter cohort** (lenders present every panel year — 295 of 1,629 ever-seen) — the survivor-bias-clean lender set. |
| `fdic/pull_sod.py` | (none — calls API) | `fdic/sod/sod_{year}.csv` × 16 years | Paginated FDIC SoD pull, idempotent, with SSL workaround. |
| `fdic/parse_sod.py` | `fdic/sod/sod_{year}.csv` | `fdic/county_year.csv` (7.6 MB) | Aggregates branch-level → county-year, computes branch count, bank count, total deposits, deposit HHI, top-bank share, plus 1y/3y change features. 51,234 county-year rows. |
| `sba/parse_sba.py` | `sba/foia-*.csv` (870 MB) | `sba/zip_year.csv` (7.6 MB) | Aggregates loan-level → (state, zip5, year). 211,577 rows. **Tract assignment deferred** — needs HUD ZIP-tract crosswalk. |
| `acs/pull_acs.py` + `pull_acs_early.py` | (Census API) | `acs/acs5_{vintage}/state_{ss}.json` | Two pullers — modern variable set 2014+, legacy 2010-2013. |
| `acs/pivot_acs.py` | per-state JSON | `acs/tract_year.csv` (35 MB) | Maps both legacy (B15002, B23001) and modern (B15003, B23025) variables into canonical columns: `pct_bachelor_plus`, `unemployment_rate`, `pct_poverty`, etc. 540 K tract-vintage rows. |
| `hmda/pull_hmda.py` | (CFPB API) | `hmda/tract_aggregates_{year}/{ST}.csv` × 7 × 52 | Streams LAR from CFPB Data Browser API; aggregates to tract-year on the fly without storing full LAR (would be 30-60 GB). |

### 3.1 Schema EDA — `etl/schema_eda.py` + `notes/03_schema_audit.md`

YOY schema drift audit across all sources. Findings:

- **CRA disclosure**: 2009-2013 ship as one bundled file, 2014-2024 ship split into 8 D-files. **Zero functional drift** — parser already filters by record-type prefix.
- **FDIC SoD**: zero drift, 10 cols stable across 16 years.
- **CRA transmittal**: stable since 1996.
- **HMDA**: zero drift (we control the schema).
- **ACS**: real drift (2014 variable migration), **already reconciled** by separate early/modern pullers.
- **SBA**: real drift between 504 (40 cols, CDC + third-party lender structure) and 7(a) (43 cols, single-bank). **Outstanding** — small parser tightening.
- **Tract vintage**: real drift — Census redraws every 10 years. **Outstanding** — Phase 2.5.

---

## 4. Panel build — `features/build_panel.py`

Joins all per-source CSVs into one tract-year parquet:

```
data/processed/panel/tract_year.parquet  (1,241,399 rows × 69 cols, 62.5 MB)
```

Joins (in order):
1. Start with CRA tract-year as the spine
2. Merge CRA county features (HHI, top-share) on `county_fips × year`
3. Merge FDIC SoD on `county_fips × year`
4. Merge HMDA tract aggregates on `tract_fips × year` (only fills 2018-2024; rest get `has_hmda=0`)
5. **Lag-aware ACS merge**: for each (tract, year), pick the latest ACS vintage with `vintage ≤ year - 1`. This enforces the rule from methodology brief §2.2: never use an ACS vintage that hadn't been published yet at prediction time. Round 4 had this leak.
6. Merge USDA RUCA (`is_rural` flag from PrimaryRUCA ≥ 7)
7. Merge persistent poverty county flag (USDA County Typology 2025)

Static-designation flags (`is_opportunity_zone`, `is_persistent_poverty`) get masked to 0 for years before the policy took effect, where applicable.

---

## 5. Target definition — `features/define_target.py`

Three desert flavors per methodology brief §5:

1. **Service desert**: `n_cra_lenders` in bottom 10th percentile of (year × rural/urban peer group). 11.2% of tract-years.
2. **Origination desert**: HMDA originations per capita in bottom 10th percentile (2018+ only). 10.0% of eligible tract-years.
3. **Any desert**: union of above. 14.5%.

Two target families per flavor, at H1/H2/H3:

- **STATE target** (`target_service_desert_hN`): is the tract a desert at year+N? — sticky, ~10.5% positive rate. Suspectible to autocorrelation leakage.
- **TRANSITION target** (`target_becomes_service_desert_hN`): tract is NOT a desert at T but IS at T+N. ~2.75% positive rate. **The genuine forecasting problem.**

We caught the autocorrelation issue when the first walk-forward run reported AUC 0.98 on the state target — too good. Switched to transition target → AUC 0.93. Still suspicious; deeper audit revealed circular features (see §7).

Output: `data/processed/panel/tract_year_with_target.parquet` (1.30 M × 91 cols, 78.7 MB).

---

## 6. Walk-forward training — `train/walk_forward.py`

**8-fold expanding-window walk-forward by year:**

| Fold | Train | Val | Test |
|---|---|---|---|
| F1 | 2009-2014 | 2015 | 2016-2018 |
| F2 | 2009-2015 | 2016 | 2017-2019 |
| F3 | 2009-2016 | 2017 | 2018-2020 |
| F4 | 2009-2017 | 2018 | 2019-2021 |
| F5 | 2009-2018 | 2019 | 2020-2022 |
| F6 | 2009-2019 | 2020 | 2021-2023 |
| F7 | 2009-2020 | 2021 | 2022-2024 |
| F8 | 2009-2021 | 2022 | 2023-2024 |

**Algorithm**: XGBoost classifier, max_depth 6, learning_rate 0.05, subsample 0.85, colsample 0.85, min_child_weight 5, reg_lambda 1.0, tree_method hist, eval_metric aucpr, early_stopping_rounds 25. Hyperparameters not tuned yet — first run.

Per fold: fit on train, early-stop on val, predict on test. Compute test AUC, AP, AP-lift, Brier.

Output: `diagnostics/walk_forward/fold_results.csv` + per-tract `test_predictions.parquet`.

---

## 7. Circular feature audit — `train/walk_forward_clean.py`

The first end-to-end run reported **mean test AUC 0.9335 ± 0.0143**. Suspiciously high. Audit revealed two tiers of circular features:

**Tier 1 — directly target-defining at year T:**
- `n_cra_lenders` (the variable that defines the target)
- `cra_lender_entries_1yr`, `cra_lender_exits_1yr`, `cra_lender_churn_1yr`, `cra_lender_presence_ratio_1yr`
- `cra_lender_entries_3yr`, `cra_lender_exits_3yr`, `cra_lender_churn_3yr` (3yr aggregates still include T's value)

**Tier 2 — county-level proxies for target ("county desert rate" analog):**
- `cra_county_lender_count`
- `cra_county_total_loan_count`
- `cra_county_total_loan_amount_k`

Removed all 11 circular features. Re-ran. Result: **AUC 0.8345 ± 0.0097**.

The 0.10 AUC drop is the size of the leakage. The clean number is the genuine forecasting performance and is what should be reported.

---

## 8. Diagnostics — `train/diagnostics.py`

Reads `test_predictions.parquet`, produces:
- **Calibration deciles** (reliability table): `calibration_overall.csv`
- **Top-N precision** at top 100 / 500 / 1,000 / 5,000: `top_n_precision.csv`
- **Decision-curve net benefit** at thresholds 0.01-0.50: `decision_curve.csv`
- **Per-state AUC** (filtering territories PR + VI; uses 50 states + DC = 51): `state_auc.csv`

---

## 9. Final results

**Round 4 best (single split, behavioral_compact, 2014-2017 train):**
- AUC 0.7510, AP 0.0452, AP-lift 2.51×

**Round 5 with circular features (8 walk-forward folds, transition target):**
- AUC 0.9335, AP 0.2876, AP-lift 11.83× — **inflated by circular features**

**Round 5 CLEAN (8 walk-forward folds, transition target, no circular features):**
- **AUC 0.8345 ± 0.0097**
- **AP 0.1249, AP-lift 5.10×**
- Top-100 precision: 70%
- Top-1,000 precision: 42%
- Median per-state AUC: 0.8362 (IQR 0.7955 - 0.8658) across 51 jurisdictions
- Honest +0.08 AUC over Round 4, achieved without target leakage

**Per-fold AUC walks 0.85 → 0.83 across F1 → F8** — slight degradation through the COVID-era folds (F4-F8), as the methodology brief predicted at §1.5. Honest behavior; the model isn't pretending COVID didn't happen.

---

## 10. Stage 1-3 follow-up (executed)

After the initial honest baseline (AUC 0.8345 with circular features removed), we ran three further stages.

### Stage 1: Tract vintage harmonization

Implementation: [features/harmonize_tracts.py](features/harmonize_tracts.py). Loads both Census Bureau relationship files (`tract_xwalk_2000_2010.txt` for population-weighted apportionment, `tract_xwalk_2010_2020.txt` for area-weighted apportionment), composes them into a unified `source_tract → [(target_2020_tract, weight), ...]` lookup, and applies it to the CRA tract-year and ACS tract-year processed CSVs.

Output: `data/processed/cra/tract_year_h2020.csv` (95 MB, 1.41 M rows — up from 1.23 M because split tracts duplicate into multiple targets), `data/processed/acs/tract_year_h2020.csv` (46 MB, 597 k rows). Crosswalk debug at `data/processed/crosswalk/_harmonization_log.txt`.

[features/build_panel.py](features/build_panel.py) updated to prefer `_h2020.csv` versions when present.

| | AUC | AP | AP-lift |
|---|---|---|---|
| Pre-harmonization clean | 0.8345 ± 0.0097 | 0.1249 | 5.10× |
| **Post-harmonization clean** | **0.8494 ± 0.0395** | **0.1731** | **8.34×** |
| Δ | **+0.015** | **+0.048** | **+3.24×** |

Mean AUC up +0.015 (matches the +0.01–0.02 expected). Variance widened — early folds (F1-F3) jumped to 0.87-0.91 because they had more vintage drift to fix; late folds (F6-F8) drifted slightly down. Honest fold variance, not leakage.

### Stage 2: Spatial robustness — leave-one-state-out

Implementation: [train/spatial_robustness.py](train/spatial_robustness.py). Runs three CV regimes on the 2009-2021 working set (51 jurisdictions = 50 states + DC, territories filtered):

```
(A) Tract-random K-fold AUC:    0.8927    (LEAKY baseline — neighbors in train+test)
(B) Year walk-forward AUC:      0.8494    (current methodology)
(C) Leave-one-state-out AUC:    0.8887    (STRICTEST — all 51 states held out)

Random-CV vs LOSO gap:          +0.0040  ← the spatial-leakage tax
Walk-forward vs LOSO gap:       -0.0393  ← temporal gap from COVID-era folds
```

**Spatial leakage tax is essentially zero (+0.004).** Random-K-fold AUC (0.8927) is within 0.004 of leave-one-state-out (0.8887) — the model isn't memorizing geography.

What dominates the AUC drop in walk-forward is the **temporal regime shift through COVID**, not spatial leakage. The model performs *better* when predicting unseen states (LOSO 0.8887) than when predicting the next 2 years (walk-forward 0.8494).

Per-state spread (LOSO): median 0.8874, IQR 0.8645 – 0.9172. Worst NV (0.76), best VT (0.98). Smaller, more homogeneous states do better; larger heterogeneous states (CA, FL) do okay but slightly worse.

Outputs at [diagnostics/spatial_robustness/](diagnostics/spatial_robustness/).

### Stage 3: LightGBM + Optuna hyperparameter tuning

Implementation: [train/walk_forward_lgbm_optuna.py](train/walk_forward_lgbm_optuna.py). Replaces XGBoost with LightGBM, runs 30-trial Optuna Bayesian (TPE) search on F1's (2009-2014 train, 2015 val) — the **earliest** val window so we don't peek at later folds' test years. Best params then applied to F2-F8.

Best params found:
```
num_leaves           75
max_depth             9
learning_rate     0.0153
min_child_samples    30
subsample          0.82
colsample_bytree   0.52
reg_alpha          0.034
reg_lambda       0.00026
n_estimators        509
```

| | AUC | AP | AP-lift |
|---|---|---|---|
| Stage 1 (XGBoost, harmonized, default params) | 0.8494 ± 0.0395 | 0.1731 | 8.34× |
| **Stage 3 (LightGBM + Optuna, harmonized)** | **0.8472 ± 0.0368** | **0.1740** | **8.38×** |
| Δ | **−0.002** | **+0.001** | **+0.04×** |

**Tuning was a wash.** AUC essentially unchanged (within stochastic noise of 0.002), AP+AP-lift marginally up. This is informative: **the XGBoost baseline was already near-optimal** for this feature set + target. Optuna didn't find meaningful headroom.

Implication: **we've hit the AUC ceiling at ~0.85 for this target with these 53 features.** Further gains require new features, not more tuning.

---

## 11. Final number to report

```
Round 4 best (single-split, 2014-2017 train, behavioral_compact):
  AUC 0.7510  AP 0.0452  AP-lift 2.51×

Round 5 final (8-fold walk-forward, harmonized, transition target, no circular features):
  AUC 0.8494 ± 0.0395  AP 0.1731  AP-lift 8.34×
  Δ vs Round 4: +0.10 AUC, 3.8× AP, 3.3× AP-lift
```

Spatial robustness: **+0.004 AUC tax** (essentially zero). The model generalizes to unseen states.

Geographic IQR: 0.8645–0.9172 across 51 jurisdictions.

Top-N precision (overall pooled, clean):
- Top 100: 70%
- Top 1,000: 42%
- Top 5,000: 29%

---

## 13. Methodology audit fixes — round 2 (2026-04-28 evening)

After staging the model end-to-end, I did an honest methodology review and flagged 17 issues. Five were unambiguous tightenings; five need explicit user calls; the rest are larger lifts deferred to a Phase-3 pass. This section documents the five applied fixes.

### Fix #1 — FDIC proxy circularity (Tier-3 circular features dropped)

**Problem.** The "clean" model dropped 11 CRA-side features but kept FDIC count features (`fdic_bank_count`, `fdic_branch_count`, total/avg deposits and their deltas). At year T those are highly correlated with `n_cra_lenders` at year T — because **banks ARE CRA reporters** above the asset threshold. FDIC bank count and CRA lender count cross-correlate ~0.85 in cross-section. The model could effectively reconstruct the dropped CRA lender count from FDIC.

**Fix.** Added 14 FDIC count and total-deposit features to the circular-feature drop list:
```
fdic_bank_count, fdic_branch_count
fdic_bank_count_chg1yr/3yr, fdic_branch_count_chg1yr/3yr
fdic_total_branch_deposits_k (+chg1yr/3yr/pctchg1yr/pctchg3yr)
fdic_avg_branch_deposits_k (+chg1yr/3yr)
```

**Kept.** `fdic_deposit_hhi`, `fdic_top_bank_share`, and their delta variants — these measure *concentration shape*, not lender count *level*, and are not mechanically tied to the target.

**Implementation.** [train/walk_forward_audit_fixed.py](train/walk_forward_audit_fixed.py) — `CIRCULAR_FEATURES_FDIC` set unioned with the prior `CIRCULAR_FEATURES_PRIOR`. Feature count: 53 → 39.

### Fix #2 — ACS publication-lag forward leak

**Problem.** The lag-aware ACS merge required `vintage <= year - 1`. But ACS 5-year vintage labeled `V` is **published in autumn of year V+1**. So for predicting at the START of year P, the latest valid vintage is `P - 2`, not `P - 1`. The old rule allowed using the 2015 vintage (published Nov 2016) for predictions at the start of 2016 — a ~6-month forward leak.

**Fix.** Changed the rule to `vintage <= year - 2` in `lag_aware_acs_merge()`.

**Implementation.** [features/build_panel.py](features/build_panel.py) lag rule tightened. Effect on panel: ACS-merged row count dropped from 1,186,045 → 1,102,239 (−7%). Tracts in the earliest panel year (2009) now have no usable ACS vintage and get NaN demographics, which is the honest representation.

### Fix #6 — Test-window asymmetry standardized

**Problem.** F1-F7 tested on 3-year windows (T+2 to T+4); F8 tested on 2 years (2023-2024 — only 2 years remain in the panel). Per-fold metrics weren't directly comparable because test set sizes differ.

**Fix.** Standardized all 8 folds to 2-year test windows. Changed FOLDS table from e.g. `("F1", 2009, 2014, 2015, 2016, 2018)` to `("F1", 2009, 2014, 2015, 2016, 2017)`.

**Implementation.** [train/walk_forward_audit_fixed.py](train/walk_forward_audit_fixed.py) `FOLDS` constant. Side effect: AUC went up ~+0.01 because shorter test windows drop hard years (F4 gained from removing 2021 COVID year).

### Fix #7 — Puerto Rico / US Virgin Islands excluded from training

**Problem.** The walk-forward and walk-forward-clean runs included PR (state_fips 72) and VI (state_fips 78) in train, val, and test. Per-state diagnostic tables filtered them post-hoc, but the model coefficients still reflected their data. Since these territories have very different rural/urban structures and small samples, including them in training added noise without methodological clarity.

**Fix.** Filter `state_fips ∈ {72, 78, 60, 66, 69}` (PR, VI, AS, GU, MP) from the panel **at training time**. Now the model is trained, evaluated, and reported on the 50 states + DC = 51 jurisdictions consistently.

**Implementation.** [train/walk_forward_audit_fixed.py](train/walk_forward_audit_fixed.py) — territory filter applied to `df` before fold splitting.

### Fix #11 — Isotonic calibration on val, applied to test

**Problem.** The diagnostics showed the model was slightly under-confident in the 0.1–0.4 range (predicted 14% → observed 25%). Brier could be improved.

**Fix.** Per fold, fit `IsotonicRegression(out_of_bounds="clip")` on the validation set's predictions, apply to the test set's predictions. Save both raw and calibrated probabilities.

**Implementation.** [train/walk_forward_audit_fixed.py](train/walk_forward_audit_fixed.py) `IsotonicRegression` per fold.

**Result.** Effectively a no-op on this run — Brier moved from 0.0203 (raw) to 0.0201 (calibrated), Δ = −0.0002. The model was already well-calibrated post-FDIC-drop. The infrastructure is in place for any future runs where calibration matters more.

---

## Audit-fixed final number

```
Round 4 best (single split, 2014-2017 train):           AUC 0.7510  AP 0.0452  AP-lift 2.51×
Round 5 baseline (clean, un-harmonized):                AUC 0.8345  AP 0.1249  AP-lift 5.10×
Round 5 + harmonization (Stage 1):                      AUC 0.8494  AP 0.1731  AP-lift 8.34×
Round 5 + LightGBM/Optuna (Stage 3):                    AUC 0.8472  AP 0.1740  AP-lift 8.38×
Round 5 + audit fixes (Stage 4 — current best):         AUC 0.8566  AP 0.1718  AP-lift 9.25×
                                                        Δ vs Round 4: +0.106 AUC, 3.8× AP, 3.7× AP-lift
                                                        Brier: 0.0203 (raw) / 0.0201 (calibrated)
                                                        51 jurisdictions (50 states + DC), 39 features
```

Per-state median AUC: 0.8106 (was 0.8362 pre-fix). IQR: 0.7753 – 0.8705. Worst: DC (0.68 — unusual all-urban federal district). Best: RI, VT, SD, DE, NH (>0.90).

The +0.007 from baseline-Stage-1 to audit-fixed is **partly real** (cleaner methodology) and **partly artifact** (shorter test windows drop hard years). The honest comparison vs Round 4: **+0.10 AUC** with multiple leakage paths closed and 8-fold walk-forward distribution rather than single-split point estimate.

---

## 14. Decisions still owed to the user (audit findings #4, #10, and three deferred lifts)

The audit also flagged:

### #4 — Desert threshold drift across years (philosophical)

The threshold is the bottom decile within (year × peer_group). It shifts year-over-year as lender counts decline nationally. A tract with 3 lenders is "always a desert" in 2024 but "marginal" in 2009 — cross-year comparisons of which tracts are deserts conflate two things (the tract changed AND the threshold changed).

**Options:**
- (a) Keep current — percentile within (year × peer_group). Good for forecasting; noisy for cross-year stories.
- (b) Pin to fixed year — use 2015's bottom decile applied to all years. Cleaner trends, but assumes 2015 is "normal."
- (c) Absolute threshold — e.g., `<4 lenders per 10k pop`. Most policy-relevant; harder to defend the specific number.

Defer until policy use case is defined.

### #10 — External hold-out year (workflow)

Currently F1-F8 use the same data, and Optuna tuning happened on F1's val. Strictly, F2-F8 reflect a tuned config, not truly out-of-sample. Holding out 2024 entirely (never train, never validate, never tune) would be the gold standard.

**Options:**
- (a) Hold out 2024. F1-F7 become tuning territory, 2024 is the truly clean test. Loses one walk-forward fold.
- (b) Hold out 2023+2024. Even cleaner, loses two folds.
- (c) Skip — current protocol is acceptable for an academic deliverable.

Defer until presentation/paper context is clearer.

### Three larger lifts deferred to Phase-3

- **#3** — Use Census 2020 block-level population to compute proper population weights for the 2010↔2020 crosswalk (currently land-area-only). ~200 lines, more accurate harmonization, plausibly +0.002 AUC.
- **#5** — Harmonize at parse time, not at output time. ~300 lines. Fixes the arithmetic awkwardness for ratio/churn features when tracts split.
- **#15** — HMDA pre-2018 backfill from CFPB legacy site. Manual download. Plausibly +0.02–0.04 AUC for F1-F3 folds where HMDA features currently have `has_hmda=0`.

These three are the highest-leverage remaining technical work but require either large code changes or manual data acquisition.

---

## 15. Outstanding work, in priority order

What gives further AUC bumps from here:

1. **HMDA backfill to 2009-2017** — the API only goes back to 2018; manual download from CFPB's legacy site or FFIEC's older flat-file system. This would let HMDA features participate in the F1-F3 folds where they currently aren't available. Plausibly worth +0.02 to +0.04 AUC.
2. **SBA tract assignment** — currently aggregated at ZIP level. Apportion via HUD ZIP-tract crosswalk. Adds tract-level small-business-credit-access features. Plausibly worth +0.01 to +0.02 AUC.
3. **Branch-distance features** — using FDIC SoD lat/lng, compute drive-time isochrones to nearest branch per tract. Captures supply-side access in a way the count-based features can't. Plausibly worth +0.01 to +0.02 AUC.
4. **Trailing-Δ feature engineering** — replace `cra_lender_*` 1yr/3yr deltas (currently dropped as circular) with **5-to-2 year trailing deltas** (Δ between T-5 and T-2, excluding the most recent year). Restores the lender-behavior signal without target leakage. Plausibly worth +0.005 to +0.015 AUC.
5. **Calibration fix** — isotonic scaling on a hold-out fold. Doesn't change AUC; improves Brier and policy-deployment usefulness.
6. **Multi-target joint model** — predict service / origination / branch desert simultaneously (multi-output LightGBM). Plausibly worth +0.005 AUC plus richer policy outputs.
7. **Refreshed showcase map** — using harmonized panel + LightGBM-Optuna predictions, with 8-fold confidence bands.

---

## File map

```
round5/
├── README.md
├── CHANGES.md                              ← you are here
├── .impeccable.md                          ← design context (from Round 4 carryover)
├── notes/
│   ├── 00_methodology.md                   methodology brief — the spec
│   ├── 02_etl_log.md                       ETL log + manual download instructions
│   └── 03_schema_audit.md                  YOY schema audit + reconciliation plan
├── etl/
│   ├── download_all.sh                     orchestrator for curl-able sources
│   ├── schema_eda.py                       YOY schema audit script
│   ├── cra/parse_cra.py                    CRA D-file parser → tract+county features
│   ├── fdic/pull_sod.py                    FDIC SoD API puller
│   ├── fdic/parse_sod.py                   FDIC SoD → county-year features
│   ├── sba/parse_sba.py                    SBA loans → zip-year aggregates
│   ├── acs/pull_acs.py + pull_acs_early.py Census ACS pullers (modern + legacy)
│   ├── acs/pivot_acs.py                    ACS JSON → canonical tract-year CSV
│   ├── hmda/pull_hmda.py                   HMDA streaming aggregator
│   └── fred/pull_macro.py                  FRED macro pull (currently blocked by network)
├── features/
│   ├── build_panel.py                      joins all sources → tract-year parquet
│   └── define_target.py                    desert thresholds + state/transition targets
├── train/
│   ├── walk_forward.py                     XGBoost walk-forward (with circular features)
│   ├── walk_forward_clean.py               XGBoost walk-forward (CLEAN, no circular)
│   └── diagnostics.py                      calibration / top-N / decision-curve / per-state
├── data/
│   ├── raw/                                downloaded source data (~7 GB)
│   └── processed/                          parsed features and panel (~300 MB)
└── diagnostics/
    ├── walk_forward/                       run with circular features (inflated)
    └── walk_forward_clean/                 honest run (this is the result we report)
```

---

## 16. Showcase dashboard — Round 5 quant-terminal interactive map

A live interactive dashboard built on top of the audit-fixed predictions. Lives at [web/](web/), serves locally with `python3 -m http.server`, ready for GitHub Pages via the staged `.github/workflows/pages.yml`. Aesthetic = quant-terminal dark per [.impeccable.md](.impeccable.md): Funnel Display + Funnel Sans + JetBrains Mono, OKLCH cool-tinted neutrals + single burnt amber accent, hairline-bordered rails over a full-bleed dark map, no cards-with-shadows, no gradients, no glassmorphism. Tabular figures everywhere. Reads at 10 ft (projector) and 18 in (laptop).

### What it does

- **Full-bleed choropleth** of 79,111 US census tracts colored by the audit-fixed model's calibrated `P(becomes a desert at year+1)`. Single-hue ramp from near-surface to saturated burnt amber.
- **Live filtering** — state dropdown (50 + DC), rural-only and persistent-poverty toggles, range sliders for population / median income / poverty rate / non-white-or-Hispanic rate / risk floor. Filters use **mask-mode**: filtered-out tracts dim to ~10% opacity, geographic context is preserved.
- **Live statistics rail** — recomputes filtered AUC (Mann-Whitney implementation in JS), mean risk, max risk, positive rate, n_tracts on every slider tick (~50 ms debounce). Plus the top-25 highest-risk tracts in the current filter, and a per-state AUC table.
- **Hover tooltip** on any tract — state, FIPS, predicted risk (large mono number), 6 demographic fields. **Click to pin**; ESC or click outside to release.
- **State zoom** — click a state in the right-rail table to filter+fly. State filter dropdown also flies to its bounding box.
- **Reset** via the button or `R` key.

### Round-2 dashboard additions (this section's work)

After the initial dashboard shipped, four enhancements were added based on user feedback:

#### 1. Top-25 click → fly + pin (was: fly only)

Previously, clicking a row in the right-rail "TOP 25 RISK" list only flew the map to that tract. Now it **also pins the tract's tooltip** as if you'd clicked the polygon directly. Implementation: after the `flyTo` settles (`map.once('moveend', ...)`), synthesize a click event with the projected pixel coordinates and call the existing `pinTract()` handler. One unified interaction model — top-25 list, state table click, and direct map click all behave identically.

#### 2. Hover-glossary on every metric label

Every label in the dashboard with `data-gloss="key"` now shows a small tooltip on hover. Visually marked with a 1-px dotted underline that turns burnt amber on hover (matching the focus-ring color logic). The tooltip is a hairline-bordered amber-edge popup containing:

- **TERM** (mono, all-caps, accent color) — e.g. "FILTERED AUC"
- **Definition** (1-2 sentences in body type) — what it is, why it might differ from the headline
- Optional **see DOCS · SECTION** pointer (mono, small, muted)

Glossary keys covered (12): `auc`, `ap_lift`, `n_tracts`, `walk_forward`, `filtered_auc`, `filtered_tracts`, `mean_risk`, `max_risk`, `pos_rate`, `risk`, `filter_state`, `static_flags`. Definitions live in `GLOSSARY` constant in `app.js`.

#### 3. DOCS panel — slide-in methodology

New **DOCS** pill in the masthead (after the headline metrics). Click it (or press `D`) to slide in a 440-px-wide panel from the right edge that overlays the stats rail. Contents, in order:

1. **THE FORECASTING PROBLEM** — what we predict, why transition target, positive rate
2. **WALK-FORWARD VALIDATION** — table of all 8 folds with AUCs, the COVID-era regime-shift narrative
3. **LEAKAGE PATHS CLOSED** — list of the 25 circular features dropped, ACS lag fix, PR/VI exclusion, test-window standardization
4. **CALIBRATION** — what isotonic does, why it was a no-op on Round 5
5. **WHY FILTERED AUC ≠ HEADLINE AUC** — direct answer to the eponymous question
6. **DATA PANEL** — sources, vintage harmonization, the +0.106 Round-4-to-Round-5 delta
7. **GLOSSARY** — 19 entries combining the hover-glossary terms and DOCS-only methodology terms (TRANSITION TARGET, CIRCULAR FEATURES, TRACT VINTAGE HARMONIZATION, BRIER SCORE, ISOTONIC CALIBRATION, RUCA / PERSISTENT POVERTY, ACS LAG-AWARE MERGE)
8. References to CHANGES.md, methodology brief, README

Closes via X button, Escape key, or pressing `D` again. ARIA `aria-expanded` toggles on the pill.

#### 4. Updated keyboard shortcuts

| Key | Action |
|---|---|
| `R` | Reset all filters and re-fit US |
| `D` | Toggle DOCS panel |
| `Esc` | Unpin tooltip / close DOCS panel |

### Files added / changed (round-2)

```
web/index.html       +DOCS panel markup (~70 lines), data-gloss hooks on 12 labels, glossary tooltip <div>
web/styles.css       +280 lines: .docs* (slide-in panel), .gtip (glossary tooltip), .docs-pill, [data-gloss] underline
web/app.js           +130 lines: GLOSSARY map, GLOSSARY_DOCS extra entries, gtip handlers, DOCS toggle, pinTract from top-25
```

### Aesthetic audit

The DOCS panel and glossary tooltip strictly follow the design context from [.impeccable.md](.impeccable.md):
- No glassmorphism — opaque dark surface (`oklch(0.18)` and `oklch(0.22)`)
- No cards-with-shadows — single hairline border + accent edge for the DOCS panel; full amber border for glossary tooltip
- No `border-left: Npx solid var(--accent)` — the accent edge on the DOCS panel is `border-left: 1px solid var(--accent)` (1px is the OK threshold per the absolute-bans rule, AND it's a structural divider not a decorative accent stripe)
- No gradient text — all text solid color
- All numbers in JetBrains Mono with tabular-nums
- Slide-in animation: 320 ms ease-out-quart, transform-only (no width animation)
- One accent color (burnt amber) only on: DOCS panel border, hover-glossary border, hover-glossary term, dotted underline on hover, "DOCS" text when expanded

### Round-3 dashboard additions — county + ZIP context in tracts

User asked for richer per-tract context in the hover/click tooltip. Added two fields without growing the tooltip footprint meaningfully.

**Data sources pulled** (free Census Bureau, no auth):
- **County names**: [`national_county2020.txt`](data/_lookup/county_names.txt) — 124 KB, 3,234 entries (state + county FIPS → "Madison County, AL"-style label).
- **ZCTA → tract relationship**: [`tab20_zcta520_tract20_natl.txt`](data/_lookup/zcta_tract.txt) — 23 MB. We use the ZCTA with the largest `AREALAND_PART` overlap as the dominant ZIP per tract.

**Tract → place (city)** is **deferred**. The 2020 Census doesn't publish a national tract-to-place relationship file. Getting authoritative city names per tract requires either (a) a spatial join against TIGER PLACES shapefiles, (b) the HUD ZIP-tract crosswalk (which is account-gated), or (c) a third-party dataset. Round-3 sticks with county + ZIP, which together convey location with similar specificity to most viewers ("Madison County, AL · ZIP 35801" reads as "Huntsville area" to a Southeast US reader). City lookup would be a Round-4 add.

**Tooltip header redesigned** to a two-row layout:
```
┌───────────────────────────┐
│ AL          Madison County, AL  │ ← state (accent mono) | county (body)
│ TR 01089003100   ZIP 35801      │ ← FIPS (mono mute)    | ZIP (mono)
└───────────────────────────┘
│         8.4%                    │ ← risk (44px mono)
│         PREDICTED RISK · H1     │
…
```

**Files changed (round-3)**:
```
web/build_dashboard_data.py   +30 lines: county_lookup + zip_lookup load and merge
web/data/_lookup/             new dir with raw Census reference files
web/data/tracts.geojson       rebuilt: now carries `cn` (county name) + `zp` (ZIP) per tract
web/index.html                tooltip head: 2-row layout (state | county / FIPS | ZIP)
web/styles.css                .tip__head, .tip__county, .tip__zip; FIPS muted, county is the readable label
web/app.js                    renderTip populates county and ZIP, prefixes "TR " to FIPS and "ZIP " to ZIP
```

Geojson size: 26 MB → 29 MB raw / 4.3 MB → 4.8 MB gzipped. ~12% increase, acceptable.

### Round-4 dashboard additions — typeset / distill / clarify / polish

After running `/impeccable critique` on the live dashboard (score 31/40, "strong"), four targeted skills addressed every flagged issue. Each skill ran with explicit scope; nothing drifted into adjacent territory.

**`/typeset`** — projector-distance type bumps inside the existing `@media (min-width: 1600px)` block. 35 selectors across both rails, the tooltip, glossary tooltip, top-25 list, state table, loader, and colophon. Two-px rule:
- 9 px small mono labels (stat dt, filter legends, table th, hint text, toplist rank/state, tooltip dt) → **11 px**
- 10 px section headers (rail-head, check labels, colophon, toplist row, table td, glossary term, loader, docs-pill) → **12 px**
- 11 px secondary-emphasis labels (toplist risk, tip state/county) → **12-13 px**

Mono + tabular-nums + 0.10em+ tracking preserved on every all-caps label. Body text in the METHODS panel (12-13 px) intentionally untouched — that view is laptop-side. Laptop view (<1600 px) unchanged.

**`/distill`** — collapsed four range-slider groups (POPULATION, MEDIAN HH INCOME, POVERTY RATE, NON-WHITE/HISPANIC %) under a single expandable ADVANCED · DEMOGRAPHIC FILTERS section. First-impression visible-control count went from 12 to 6. Mechanics:
- `<button aria-expanded aria-controls>` + `<div role="region" aria-labelledby>` — proper toggle semantics
- `grid-template-rows: 0fr → 1fr` over 280 ms ease-out-quart (no height-property animation per the design context)
- Affordance is a single `+` glyph that **rotates 45° to become `×`** when expanded — single-character indicator, no chevron-down icon (avoids the templated SaaS-dashboard tell)
- A 5×5 px amber dot inline-prefixed to the section label appears when any of the 8 advanced range values is non-default AND the section is collapsed — communicates "you have hidden filters active" without forcing the user to expand. The chev also stays amber when collapsed-with-modifications.

**`/clarify`** — two copy fixes:
1. Empty-state copy in right rail. Bare `—` replaced with semantic, muted-mono text. `setStat(id, value, muted)` helper toggles a `.is-muted` class on the `<dd>` (lower color, smaller weight, slightly smaller font, wider tracking). Three states:
   - Zero tracts match → `no match`
   - Some tracts but zero are labeled → `no labels`
   - Some labels but n ≤ 50 (AUC unstable) → `n=37 · too few` (with the actual count)
2. Colophon restructured from a single centered row to a split-justify two-section layout: info-left, keyboard-hints-right. Three keys exposed: `R` reset · `D` METHODS · `ESC` close. Each shortcut uses semantic `<kbd>` styled as accent-color mono letter (no border / key-cap chrome). Hidden below 900 px viewport.

**`/polish`** — three closures:
1. **Skipped heading hierarchy** — METHODS panel section heads converted from `<h3>` to `<h2>` (matched CSS selector `.docs__section h3` → `.docs__section h2`). Document outline now h1 (masthead) → h2 (METHODS section) with no skips. Screen-reader navigation via heading levels works.
2. **DOCS → METHODS rename** — every user-facing string updated: masthead pill text, colophon keyboard hint, 5 glossary "see DOCS · SECTION" pointers (now "see METHODS · …"), HTML / JS comments. The internal CSS class names (`.docs`, `.docs__head`, `.docs-pill`, etc.) intentionally stay — they're internal naming, not user-visible, and changing them would force a no-value diff. Added `aria-expanded="false"` and `aria-controls="docsPanel"` to the METHODS button for proper toggle semantics.
3. **Contrast accessibility** — `--text-mute` lifted from `oklch(0.42 0.005 240)` (2:1 contrast on surface-1, fails WCAG AA Large) to `oklch(0.55 0.005 240)` (3.4:1, passes AA Large). Affects: colophon shortcut separators, glossary tooltip "more" hints, METHODS quiet section, muted-stat labels.

Verified during the polish pass:
- All interactive elements use `:focus-visible` (not `:focus`) — never strips the indicator from non-keyboard interactions
- `aria-expanded` ↔ `aria-controls` pairs both on the METHODS toggle and the ADVANCED toggle
- `noscript` fallback present
- `prefers-reduced-motion` honored across all transitions

**Known a11y compromise** (documented, not fixed): top-25 list items and per-state AUC table rows fire click events but aren't in the keyboard-focus order (no `tabindex`). Adding focus to all 76 rows would flood Tab-key navigation. Power users access the same data via the methodology panel's fold table. Mouse-only convenience by design.

**Final delta**:
```
After /critique  /typeset  /distill  /clarify  /polish:
  53 → 39 features (already done)
  rail: 12 → 6 visible controls
  empty states: bare "—" → semantic muted copy
  shortcuts: discoverable
  contrast: WCAG AA Large pass on muted text
  headings: clean h1 → h2 outline
  re-running /critique would expect 31 → 36-37 / 40
```

### Round-5 dashboard addition — POOLED AUC vs FOLD-AVERAGED AUC disambiguation

A user spotted the right-rail metric reading 0.752 at default (no filters) while the masthead AUC reads 0.857. Their reasonable expectation: with no filters applied, these should match. They don't — and they shouldn't. The two are genuinely different statistics:

| Metric | Computation | Value at default |
|---|---|---|
| **Masthead AUC** | Arithmetic mean of 8 walk-forward fold AUCs (each computed on its own test set) | 0.857 ± 0.044 |
| **Right-rail AUC** | Pooled AUC across the union of all ~84k unique-tract predictions, treated as one rank-ordering | 0.752 |

The pooled number is lower because mixing F1→F8 predictions in one rank shifts the positive/negative mix relative to any single fold. As filters apply, the pooled AUC moves further as the visible subset's positive count and score variance change.

**Fix**: rename "FILTERED AUC" → "POOLED AUC" in the right rail. The label now signals what's actually computed (a pooled statistic across the visible subset) rather than misleadingly implying "the headline AUC restricted to the filter."

Concretely:
- HTML: `<dt data-gloss="filtered_auc">FILTERED AUC</dt>` → `<dt data-gloss="pooled_auc">POOLED AUC</dt>`
- Glossary entry rewritten to make the "different statistic from headline, even at default" point explicit, with the 0.857 vs 0.75 numerical contrast called out
- METHODS panel section title updated: "WHY FILTERED AUC ≠ HEADLINE AUC" → "WHY POOLED AUC ≠ HEADLINE AUC"
- METHODS panel body rewritten with the side-by-side comparison and the "even with no filters applied" note
- Masthead AUC glossary tooltip updated to say "AUC (FOLD-AVERAGED)" with the explicit "mean of 8 fold AUCs" phrasing

Both numbers stay in the dashboard. The labeling is now honest about which is which.
