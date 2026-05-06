# BUS 410 · Round 7 · Two-Layer Credit-Desert Risk

Interactive dashboard and modeling pipeline for forecasting U.S. small-business credit-desert risk at the census-tract level. Two parallel models (Diagnostic + Influenceable), two horizons (2027 forecast + 2030 scenario), 79,000+ tracts.

**Headline numbers** (walk-forward validated, averaged across 8 time-split tests):

| Lens | 2027 (h+3) | 2030 (h+6) |
|---|---|---|
| Diagnostic (Model 1, 39 features incl. demographics) | AUC 0.875 / AP 0.322 | AUC 0.871 / AP 0.489 |
| Influenceable (Model 2, 20 lending-environment features) | AUC 0.820 / AP 0.282 | AUC 0.862 / AP 0.464 |

The Diagnostic model uses every signal available (ACS demographics, HMDA, FDIC, CRA churn). The Influenceable model uses only lending-environment features that local actors can plausibly move (branch access, MDI/microlender presence, SSBCI activation, residualized concentration metrics). Both predict the same target: probability of becoming a small-business credit desert (bottom-decile CRA-reporting lender count) by year T+3 or T+6.

---

## Quick start (run the dashboard)

The dashboard is vanilla HTML/CSS/JS + MapLibre GL via CDN. No build step. Any static-file server works.

```bash
# 1. Clone
git clone <REPO_URL> round7
cd round7

# 2. Decompress the SHAP attribution cache
#    (shap_top.json.gz is checked in; the uncompressed file is gitignored
#     because raw size exceeds GitHub's 100 MB limit)
./scripts/prepare-data.sh

# 3. Serve
cd web
python3 -m http.server 8009

# 4. Open
open http://localhost:8009
```

First paint takes ~2 seconds because of the 30 MB tract geojson. Subsequent loads use browser cache.

### What you can do in the dashboard

- **Toggle the lens** (top-right): Diagnostic vs Influenceable. Same map, two models.
- **Toggle the horizon** (top-right): 2027 forecast vs 2030 scenario.
- **Click any tract**: a detail panel slides in from the left with the tract's predictions across both lenses and both horizons, percentile ranks, and the top 5 features pushing the prediction up or down (real per-tract SHAP attribution). When the two lenses disagree dramatically, a divergence explainer appears in the panel telling you why.
- **Search a county or city** (top): autocomplete + fly-to. Counties also filter the map.
- **Click a state in the alphabetical grid** (right rail): fly-to + filter. State tint vanishes for the focused state, peripheral states keep their tint.
- **Move the scenario sliders** (right rail, when no tract is pinned): national choropleth recolors live. Each slider shows its honest impact (if removing this signal barely moves accuracy, the slider says so).
- **Move the scenario sliders WHILE a tract is pinned**: the tract's predicted risk and SHAP drivers in the drawer update live for that scenario.
- **Hover any feature** in the SHAP list or any scenario slider: a tooltip explains what it is and how to interpret it.

### Browser support

Modern browsers only (Chrome, Firefox, Safari latest). Uses ES2020 syntax, OKLCH colors (CSS Color 4), and MapLibre GL JS 4.x.

---

## Project structure

```
round7/
├── README.md                           ← you are here
├── .impeccable.md                      ← design context (locked: dark, mustard/chartreuse/coral, Bricolage + Manrope + Recursive)
├── .gitignore
│
├── web/                                ← the dashboard
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   ├── build_dashboard_data.py         ← rebuilds web/data/ from upstream parquet/csv
│   └── data/                           ← what the dashboard fetches at runtime
│       ├── tracts.geojson              ← 79K tracts, predictions baked into properties (~30 MB)
│       ├── shap_top.json.gz            ← per-tract SHAP top-8 features (~19 MB compressed)
│       ├── shap_top.json               ← decompressed by scripts/prepare-data.sh
│       ├── state_stats.json            ← per-state means + AUC/AP for all (model, horizon)
│       ├── state_bbox.json             ← per-state bounding box (for fly-to)
│       ├── county_index.json           ← county search index (~3K counties + bbox)
│       ├── city_index.json             ← city search index (~5K places > 10K population)
│       ├── feature_stats.json          ← per-feature mean/std/importance for slider physics
│       ├── ablation_h{3,6}.json        ← per-lever ablation deltas
│       ├── pruning_h{3,6}.json         ← top-features ranking at each horizon
│       └── regime_h{3,6}.json          ← pre/post-COVID model split
│
├── notes/                              ← methodology + rationale
│   ├── 00_design_brief.md
│   ├── 01_rssd_cra_crosswalk.md        ← 94.6% match between CRA respondent IDs and FDIC RSSDs
│   ├── 02_geocoding_log.md
│   ├── 03_decision_rule.md
│   ├── 04_final_results.md
│   ├── 05_methodology_brief.md         ← academic brief, ~7,600 words
│   └── 06_full_documentation.md        ← canonical record, ~22,000 words
│
├── etl/                                ← data ingestion (network-bound)
│   ├── cra/parse_cra_round7.py         ← FFIEC CRA → tract×lender×year (apportioned)
│   ├── lender_class/                   ← FDIC Call Report + RSSD↔CRA crosswalk
│   ├── cdfi/, mdi/, microlender/       ← mission-lender list pulls
│   ├── geocode/run_geocode.py          ← Census Geocoder + Nominatim fallback
│   ├── ssbci/build_ssbci_overlay.py    ← state-year SSBCI program presence
│   └── nmtc/                           ← NMTC investment data (loaded but dropped from final model)
│
├── features/                           ← feature engineering
│   ├── build_branch_geo.py             ← FDIC SoD + tract centroids → distance, branches_within_5mi, closures
│   ├── build_concentration.py          ← top1/top3/HHI/loans_under_100k + trailing means
│   ├── build_concentration_residualized.py
│   ├── build_cra_lender_mix.py         ← community/top4/credit-union shares
│   ├── build_mdi_features.py           ← year-precise MDI proximity
│   ├── build_mission_proximity.py
│   ├── build_nmtc_features.py
│   └── build_round7_panel.py           ← merge all feature CSVs into the training panel
│
├── train/                              ← modeling
│   ├── _horizon_config.py              ← shared HORIZON config + walk-forward folds
│   ├── walk_forward_round7.py          ← Phase A: influenceable-only Model 2
│   ├── walk_forward_boltOn.py          ← Phase C: Model 1 + Model 2 features (auxiliary)
│   ├── walk_forward_overlay.py         ← Phase C: directional overlay variant
│   ├── prune_features.py               ← block-of-clay → min features × max AUC
│   ├── ablation_per_lever.py           ← per-lever-group ablation
│   ├── regime_split.py                 ← pre/post-COVID split
│   ├── diagnostics_round7.py           ← per-fold stability, per-state AP, PDP directional sanity
│   ├── compute_shap.py                 ← per-tract SHAP top-N for the drawer
│   └── final_models_for_shap.py        ← (alias of compute_shap.py for clarity)
│
├── diagnostics/                        ← model results (CSVs + parquet predictions)
│   ├── round7_phaseA_h{3,6}/           ← canonical Phase A runs
│   ├── round7_phaseA_clean/            ← residualized variant (legacy h+1)
│   ├── round7_pruned_h{3,6}/           ← pruning sweep results + feature ranking
│   ├── round7_ablation_h{3,6}/         ← per-lever ablation summary
│   ├── round7_regime_split_h{3,6}/     ← pre/post-COVID metrics
│   └── round7_bolton/                  ← bolt-on auxiliary variant
│
├── scripts/
│   └── prepare-data.sh                 ← run this once after clone
│
└── data/                               ← gitignored. ~2.4 GB of intermediate ETL outputs.
    ├── raw/                            ← downloaded source data (FDIC SoD, CRA, ACS, etc.)
    └── processed/                      ← parsed CSVs + the merged training panel
```

---

## What is and isn't in the repo

**Included** (everything required to RUN the dashboard):
- All code (etl/, features/, train/, web/)
- All built dashboard data files (web/data/), with shap_top.json compressed
- Methodology documentation (notes/)
- Diagnostic outputs (diagnostics/) — model predictions, ablation summaries, pruning sweeps

**Excluded** (regenerable; would push the repo past GitHub limits):
- `data/raw/` — raw federal data sources (~1+ GB). Pull fresh via the ETL scripts; URLs documented below.
- `data/processed/` — intermediate ETL outputs (~1.5 GB). Regenerated by running ETL → features.
- `__pycache__/`, `.DS_Store`, etc.

If you only want to use the dashboard, you don't need any of the excluded data. If you want to retrain or extend the models, you'll need to re-run the ETL pipeline.

---

## Reproducing the pipeline (advanced)

If you want to retrain from scratch:

### Stage 1: pull raw data (network-bound, ~30 min total + manual steps)

Each ETL script is documented in `notes/06_full_documentation.md` §11. Pull order:

```bash
# CRA disclosure files (5.5 GB across 16 years; manual download from FFIEC)
# Save to ../round5/data/raw/cra/{year}/
# https://www.ffiec.gov/data/cra/flat-files

# FDIC institutions + Call Report assets (rate-limited at 2 req/sec)
python3 etl/lender_class/pull_fdic_call.py        # ~10 min

# MDI roster (manual download from FDIC)
# Save to data/raw/mdi/historical-data-year-2001-2025.xlsx
# https://www.fdic.gov/minority-depository-institutions-program

# CDFI Fund NMTC data (manual download)
# https://www.cdfifund.gov/programs-training/certification/cdfi

# SBA microlender list (HTML scrape, ~12 pages)
python3 etl/microlender/pull_sba_micro.py

# SSBCI state-year overlay (synthesizes from Treasury era windows)
python3 etl/ssbci/build_ssbci_overlay.py

# Geocode CDFI + microlender addresses (Census Geocoder, free)
python3 etl/geocode/run_geocode.py                # ~15 min
```

### Stage 2: build the training panel

```bash
python3 etl/cra/parse_cra_round7.py               # ~5 min, 16 years of CRA D-files → tract×lender×year
python3 etl/lender_class/build_rssd_cra_crosswalk.py
python3 etl/lender_class/classify_lenders.py
python3 features/build_branch_geo.py              # ~10 min, BallTree spatial join
python3 features/build_concentration.py
python3 features/build_concentration_residualized.py
python3 features/build_cra_lender_mix.py
python3 features/build_mdi_features.py
python3 features/build_mission_proximity.py
python3 features/build_nmtc_features.py           # (kept but dropped from final model)
python3 features/build_round7_panel.py            # merges everything into tract_year_with_target_round7.parquet
```

### Stage 3: train

```bash
ROUND7_HORIZON=3 python3 train/walk_forward_round7.py
ROUND7_HORIZON=6 python3 train/walk_forward_round7.py
ROUND7_HORIZON=3 python3 train/prune_features.py
ROUND7_HORIZON=3 python3 train/ablation_per_lever.py
ROUND7_HORIZON=6 python3 train/ablation_per_lever.py
ROUND7_HORIZON=3 python3 train/regime_split.py
ROUND7_HORIZON=6 python3 train/regime_split.py
python3 train/compute_shap.py                     # ~10 min, per-tract SHAP for drawer
```

### Stage 4: rebuild dashboard data

```bash
cd web
python3 build_dashboard_data.py                   # rebuilds tracts.geojson + JSONs
gzip -k -9 -f data/shap_top.json                  # refresh the compressed cache
```

### Round 5 dependency

`build_dashboard_data.py` reads from `../round5/diagnostics/walk_forward_h{3,6}/test_predictions.parquet` to populate the Diagnostic-model layer. Round 5 is a separate codebase (the original credit-desert diagnostic model). If you want to rebuild from raw data, you'll also need to re-run Round 5's walk-forward training. Round 5 source lives at the project's prior directory; for this BUS 410 submission, the necessary outputs are baked into the `web/data/` files in this repo so the dashboard runs without round 5 source.

---

## Methodology in 200 words

The target is "tract becomes a small-business credit desert by year T+H," operationalized as: tract's CRA-reporting lender count drops into the bottom decile of its rural-vs-urban peer group at year T+H, **conditional on not being a desert at year T**. Walk-forward 8-fold validation (or 6 folds at h+6 due to data-end constraints). XGBoost classifier with isotonic calibration on the validation fold.

Two models share the target but diverge on features. Model 1 (Diagnostic) uses 39 features including ACS demographics, HMDA mortgage activity, FDIC concentration, and CRA churn. Model 2 (Influenceable) uses 20 features restricted to the lending environment: branch geography, MDI/microlender proximity, SSBCI state programs, and concentration metrics that have been residualized against the lender-count signal to break mechanical leakage from the target.

Per-tract SHAP attribution comes from a final-deployable model trained on all available data through the latest year where the target is observable (2024 − H). Top-8 features per tract per (model, horizon) are cached and served to the dashboard.

Honest negative findings: NMTC investment data showed no signal and was dropped. SSBCI 2.0 doesn't behave like SSBCI 1.0 in the model. Branch-access dominance is a pre-2020 phenomenon at h+1 but holds at longer horizons.

Full treatment in `notes/06_full_documentation.md` (~22,000 words).

---

## Authors

BUS 410 Round 7 — Spring 2026.

## License

This is academic coursework. Code under MIT, data per the original federal source licenses (CRA, FDIC, ACS, etc. are public-domain).
