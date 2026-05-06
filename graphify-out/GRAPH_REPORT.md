# Graph Report - .  (2026-05-06)

## Corpus Check
- 41 files · ~72,622 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 292 nodes · 420 edges · 30 communities detected
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 31 edges (avg confidence: 0.82)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Dashboard UI & Scenario Modeling|Dashboard UI & Scenario Modeling]]
- [[_COMMUNITY_Policy Ablation & Model Decisions|Policy Ablation & Model Decisions]]
- [[_COMMUNITY_Feature Engineering Pipeline|Feature Engineering Pipeline]]
- [[_COMMUNITY_CRA Data Parsing|CRA Data Parsing]]
- [[_COMMUNITY_Geocoding Engine|Geocoding Engine]]
- [[_COMMUNITY_Dashboard Data & Metrics|Dashboard Data & Metrics]]
- [[_COMMUNITY_SSBCI Overlay Builder|SSBCI Overlay Builder]]
- [[_COMMUNITY_SHAP & Final Model Scoring|SHAP & Final Model Scoring]]
- [[_COMMUNITY_Branch Geography Features|Branch Geography Features]]
- [[_COMMUNITY_MDI Feature Builder|MDI Feature Builder]]
- [[_COMMUNITY_FDIC Call Report ETL|FDIC Call Report ETL]]
- [[_COMMUNITY_COVID Regime Split Model|COVID Regime Split Model]]
- [[_COMMUNITY_Dashboard Outputs & Assets|Dashboard Outputs & Assets]]
- [[_COMMUNITY_Feature Selection & Pruning|Feature Selection & Pruning]]
- [[_COMMUNITY_Training Configuration|Training Configuration]]
- [[_COMMUNITY_Model Diagnostics|Model Diagnostics]]
- [[_COMMUNITY_Lever Ablation Runner|Lever Ablation Runner]]
- [[_COMMUNITY_MDI Roster ETL|MDI Roster ETL]]
- [[_COMMUNITY_CDFI Roster ETL|CDFI Roster ETL]]
- [[_COMMUNITY_Mission Proximity Features|Mission Proximity Features]]
- [[_COMMUNITY_Residualized Concentration|Residualized Concentration]]
- [[_COMMUNITY_Bolt-On Model (Round 5+)|Bolt-On Model (Round 5+)]]
- [[_COMMUNITY_SBA Microlender ETL|SBA Microlender ETL]]
- [[_COMMUNITY_Lender Classification|Lender Classification]]
- [[_COMMUNITY_Round 7 Panel Assembly|Round 7 Panel Assembly]]
- [[_COMMUNITY_Overlay Walk-Forward|Overlay Walk-Forward]]
- [[_COMMUNITY_Round 7 Walk-Forward|Round 7 Walk-Forward]]
- [[_COMMUNITY_RSSD Crosswalk Results|RSSD Crosswalk Results]]
- [[_COMMUNITY_Web Dashboard Docs|Web Dashboard Docs]]
- [[_COMMUNITY_Methodology Brief|Methodology Brief]]

## God Nodes (most connected - your core abstractions)
1. `boot()` - 13 edges
2. `applyActive()` - 11 edges
3. `renderMethodology()` - 7 edges
4. `parse_year()` - 7 edges
5. `geocode_df()` - 7 edges
6. `walk_forward_round7.py — Phase A Influenceable-Only Walk-Forward` - 6 edges
7. `ablation_per_lever.py — Per-Lever Policy Ablation` - 6 edges
8. `Policy Layer Research.md — Policy Lever Mapping and Evidence` - 6 edges
9. `04_final_results.md — Round 7 Final Performance Results` - 6 edges
10. `Model 2 — Influenceable (Round 7) — 20 Lever Features Residualized` - 6 edges

## Surprising Connections (you probably didn't know these)
- `Lender Concentration / Market Depth Variables (HHI, top1, top3, unique lenders)` --semantically_similar_to--> `Residualized Concentration Features (HHI, top1, top3 residuals)`  [INFERRED] [semantically similar]
  Rebuild Brainstorming/Exploratory Policy Layer Variable Brainstorm.md → 410DB/train/ablation_per_lever.py
- `has_hmda Temporal Proxy — 1 for 2018+, misleads policy-audience readers` --semantically_similar_to--> `COVID Regime Shift — Pre-COVID AUC 0.817 vs Post-COVID AUC 0.734`  [INFERRED] [semantically similar]
  410DB/train/prune_features.py → 410DB/notes/06_full_documentation.md
- `diagnostics_round7.py — Round 7 Model Evaluation` --references--> `Model 2 — Influenceable (Round 7) — 20 Lever Features Residualized`  [INFERRED]
  410DB/train/diagnostics_round7.py → 410DB/notes/04_final_results.md
- `compute_shap.py — SHAP Value Computation` --shares_data_with--> `shap_top.json.gz — Per-Tract SHAP Top-8 Features (~19 MB compressed)`  [INFERRED]
  410DB/train/compute_shap.py → 410DB/README.md
- `Policy Layer Research.md — Policy Lever Mapping and Evidence` --references--> `Branch Access Policy Lever (distance, branches within 5mi, closures)`  [EXTRACTED]
  Rebuild Brainstorming/Policy Layer Research.md → 410DB/train/ablation_per_lever.py

## Hyperedges (group relationships)
- **Mission-Lender ETL Pipeline (CDFI + MDI + Microlender)** — pull_cdfi_list_script, pull_mdi_list_script, pull_sba_micro_script, run_geocode_script [INFERRED 0.90]
- **Lender Classification Pipeline (FDIC + RSSD + CRA)** — pull_fdic_call_script, build_rssd_cra_crosswalk_script, classify_lenders_script, lender_class_csv [EXTRACTED 1.00]
- **Round 7 Feature Assembly (all feature builders → panel)** — build_concentration_script, build_cra_lender_mix_script, build_branch_geo_script, build_mdi_features_script, build_mission_proximity_script, build_concentration_residualized_script, build_round7_panel_script [EXTRACTED 1.00]
- **Seven Policy Lever Groups Jointly Define Ablation Study Design** — ablation_per_lever_script, residualized_concentration, branch_access_lever, mdi_mission_lever, ssbci_state_policy_lever, microlender_ecosystem_lever [EXTRACTED 0.95]
- **Walk-Forward Scripts Collectively Implement Two-Layer Architecture** — walk_forward_round7_script, walk_forward_bolton_script, walk_forward_overlay_script, regime_split_script, two_layer_architecture [INFERRED 0.88]
- **Rebuild Brainstorming Docs Collectively Specify Policy Layer Design** — handoff_doc, exploratory_brainstorm_doc, policy_layer_research_doc [EXTRACTED 0.92]

## Communities

### Community 0 - "Dashboard UI & Scenario Modeling"
Cohesion: 0.07
Nodes (46): activeLeversForNote(), applyActive(), applyScenarioToDrawer(), baselineMeanRisk(), bindDrawerClose(), bindFocusClose(), bindReset(), boot() (+38 more)

### Community 1 - "Policy Ablation & Model Decisions"
Cohesion: 0.07
Nodes (42): ablation_per_lever.py — Per-Lever Policy Ablation, Ablation Surprise: residualized_concentration drives most signal (−0.096 AUC when dropped), Bolt-On Result: Mean AUC 0.889 (+0.032 over Round 5), AP gain is noise, Branch Access Policy Lever (distance, branches within 5mi, closures), Census Geocoder — Primary Geocoding (~85% hit rate, batch, free, no API key), compute_shap.py — SHAP Value Computation, COVID Regime Shift — Pre-COVID AUC 0.817 vs Post-COVID AUC 0.734, 03_decision_rule.md — Phase B AP Threshold Decision Rule (+34 more)

### Community 2 - "Feature Engineering Pipeline"
Cohesion: 0.09
Nodes (20): assets_by_year.csv (FDIC Call Report), cdfi_geocoded.csv (CDFI with lat/lon), cdfi_list.csv (CDFI Certified List), Census Geocoder API (External), cra_to_rssd.csv (RSSD-CRA Crosswalk), FDIC BankFind API (External), FDIC Institutions CSV (RSSD/CERT), FDIC Summary of Deposits (SoD) (+12 more)

### Community 3 - "CRA Data Parsing"
Cohesion: 0.31
Nodes (10): apportion(), discover(), iter_lines(), main(), normalize_tract(), parse_year(), Return (tract_lender_presence, county_lender_buckets).      tract_lender_presenc, Equal-share apportion county-lender bucket totals across tracts where the     le (+2 more)

### Community 4 - "Geocoding Engine"
Cohesion: 0.38
Nodes (9): cache_get(), cache_path(), cache_put(), census_batch(), geocode_df(), main(), nominatim_one(), normalize() (+1 more)

### Community 5 - "Dashboard Data & Metrics"
Cohesion: 0.33
Nodes (8): aggregate_latest(), build_city_index(), headline_metrics(), load_county_names(), main(), Mean across folds — the canonical AUC/AP for this project., Build city search index from Census Gazetteer + decennial place-pop API.     Fal, Per tract, take the most-recent (year, fold) calibrated probability.

### Community 6 - "SSBCI Overlay Builder"
Cohesion: 0.33
Nodes (8): build_panel(), main(), build_ssbci_overlay.py ======================  Build a state-year feature panel, Attempt to fetch Treasury SSBCI summary pages.      Returns a parsed per-state p, Build a single (state, year) row using the documented fallback rules., _row_for_year(), try_scrape_treasury(), write_csv()

### Community 7 - "SHAP & Final Model Scoring"
Cohesion: 0.33
Nodes (8): fit_one(), hmda_fillna(), latest_train_year(), main(), Latest year T where target_h{horizon} is observable (T + h ≤ 2024)., Fit ONE final-deployable model on rows where year ≤ train_end and target observa, Return top-k (feature, signed_shap) per row. Uses XGBoost native pred_contribs., shap_top()

### Community 8 - "Branch Geography Features"
Cohesion: 0.39
Nodes (7): build_year(), ensure_tract_centroids(), load_sod_year(), main(), For one year, compute distance, branches_within_5mi, closures-in-prior-3y., Load tract centroids; pull from Census Gazetteer if missing., to_radians()

### Community 9 - "MDI Feature Builder"
Cohesion: 0.39
Nodes (7): build_year(), load_mdi_year(), load_sod_year(), main(), Compute MDI features for one year., Read the MDI sheet for a given year and return DataFrame with CERT., to_radians()

### Community 10 - "FDIC Call Report ETL"
Cohesion: 0.48
Nodes (6): main(), paged_get(), pull_assets_year(), pull_institutions(), FDIC API pagination via offset/limit. Returns merged data list.      The FDIC AP, Pull Call Report ASSET per institution at year-end.

### Community 11 - "COVID Regime Split Model"
Cohesion: 0.43
Nodes (6): evaluate(), main(), make_model(), Identical hyperparameters to walk_forward_round7.py., Standard metric bundle, NaN-safe when only one class present., run_study()

### Community 12 - "Dashboard Outputs & Assets"
Cohesion: 0.38
Nodes (6): 410DB README — Round 7 Two-Layer Credit-Desert Risk Project, app.js (Dashboard Frontend), shap_top.json.gz — Per-Tract SHAP Top-8 Features (~19 MB compressed), test_predictions.parquet (Walk-Forward Predictions), tracts.geojson (Dashboard Map Data), index.html — MapLibre GL JS Dashboard (Static SPA)

### Community 13 - "Feature Selection & Pruning"
Cohesion: 0.47
Nodes (5): aggregate_feature_ranking(), main(), Average XGBoost gain importance across all 8 fold importance files., Run all 8 folds with the given feature subset; return per-fold metrics., train_walk_forward()

### Community 14 - "Training Configuration"
Cohesion: 0.4
Nodes (3): precovid_postcovid_splits(), Shared horizon + fold config for all round7 training scripts.  ROUND7_HORIZON en, For regime_split.py. Returns ((train_yrs, val_yr, test_yrs), ...)     pre-COVID

### Community 15 - "Model Diagnostics"
Cohesion: 0.7
Nodes (4): directional_sanity(), main(), per_fold_stability(), per_state_ap()

### Community 16 - "Lever Ablation Runner"
Cohesion: 0.6
Nodes (4): evaluate(), main(), Run all 8 folds with the given feature set; return per-fold metric dicts., run_walk_forward()

### Community 17 - "MDI Roster ETL"
Cohesion: 0.83
Nodes (3): load_raw(), main(), normalize()

### Community 18 - "CDFI Roster ETL"
Cohesion: 0.83
Nodes (3): load_raw(), main(), normalize()

### Community 19 - "Mission Proximity Features"
Cohesion: 0.83
Nodes (3): count_within(), main(), to_radians()

### Community 20 - "Residualized Concentration"
Cohesion: 0.67
Nodes (3): main(), Within a (year, peer_group) cohort, regress each target column on     [log(n_cra, residualize_cohort()

### Community 21 - "Bolt-On Model (Round 5+)"
Cohesion: 0.83
Nodes (3): evaluate(), main(), prepare()

### Community 22 - "SBA Microlender ETL"
Cohesion: 1.0
Nodes (2): main(), parse_page()

### Community 24 - "Lender Classification"
Cohesion: 1.0
Nodes (2): load_optional_csv(), main()

### Community 25 - "Round 7 Panel Assembly"
Cohesion: 1.0
Nodes (2): load_csv(), main()

### Community 26 - "Overlay Walk-Forward"
Cohesion: 1.0
Nodes (2): evaluate(), main()

### Community 27 - "Round 7 Walk-Forward"
Cohesion: 1.0
Nodes (2): evaluate(), main()

### Community 28 - "RSSD Crosswalk Results"
Cohesion: 0.67
Nodes (3): Credit Union NCUA Join (bypass FDIC, agency_code=4, ~10K institutions), 01_rssd_cra_crosswalk.md — RSSD to CRA Respondent ID Crosswalk (94.6% match), RSSD-CRA Match Rate: 94.6% volume-weighted; success criterion ≥ 95%

### Community 32 - "Web Dashboard Docs"
Cohesion: 1.0
Nodes (1): web/README.md — Dashboard Build and Data Documentation

### Community 33 - "Methodology Brief"
Cohesion: 1.0
Nodes (1): 05_methodology_brief.md — Methodology Brief

## Knowledge Gaps
- **36 isolated node(s):** `Per tract, take the most-recent (year, fold) calibrated probability.`, `Mean across folds — the canonical AUC/AP for this project.`, `Build city search index from Census Gazetteer + decennial place-pop API.     Fal`, `FDIC API pagination via offset/limit. Returns merged data list.      The FDIC AP`, `Pull Call Report ASSET per institution at year-end.` (+31 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `SBA Microlender ETL`** (3 nodes): `main()`, `parse_page()`, `pull_sba_micro.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Lender Classification`** (3 nodes): `load_optional_csv()`, `main()`, `classify_lenders.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Round 7 Panel Assembly`** (3 nodes): `load_csv()`, `main()`, `build_round7_panel.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Overlay Walk-Forward`** (3 nodes): `walk_forward_overlay.py`, `evaluate()`, `main()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Round 7 Walk-Forward`** (3 nodes): `walk_forward_round7.py`, `evaluate()`, `main()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Web Dashboard Docs`** (1 nodes): `web/README.md — Dashboard Build and Data Documentation`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Methodology Brief`** (1 nodes): `05_methodology_brief.md — Methodology Brief`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What connects `Per tract, take the most-recent (year, fold) calibrated probability.`, `Mean across folds — the canonical AUC/AP for this project.`, `Build city search index from Census Gazetteer + decennial place-pop API.     Fal` to the rest of the system?**
  _36 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Dashboard UI & Scenario Modeling` be split into smaller, more focused modules?**
  _Cohesion score 0.07 - nodes in this community are weakly interconnected._
- **Should `Policy Ablation & Model Decisions` be split into smaller, more focused modules?**
  _Cohesion score 0.07 - nodes in this community are weakly interconnected._
- **Should `Feature Engineering Pipeline` be split into smaller, more focused modules?**
  _Cohesion score 0.09 - nodes in this community are weakly interconnected._