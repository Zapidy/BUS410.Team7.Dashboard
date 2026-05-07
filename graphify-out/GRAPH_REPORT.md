# Graph Report - 410DB  (2026-05-07)

## Corpus Check
- 54 files · ~1,898,013 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 484 nodes · 710 edges · 79 communities detected
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 10 edges (avg confidence: 0.77)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 79|Community 79]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 81|Community 81]]
- [[_COMMUNITY_Community 82|Community 82]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 84|Community 84]]
- [[_COMMUNITY_Community 85|Community 85]]
- [[_COMMUNITY_Community 86|Community 86]]

## God Nodes (most connected - your core abstractions)
1. `boot()` - 19 edges
2. `isCountyMode()` - 16 edges
3. `applyActive()` - 13 edges
4. `$()` - 11 edges
5. `main()` - 10 edges
6. `log()` - 9 edges
7. `main()` - 8 edges
8. `main()` - 7 edges
9. `pinFeature()` - 7 edges
10. `renderDrawer()` - 7 edges

## Surprising Connections (you probably didn't know these)
- `Residualized Concentration Features (HHI, top1, top3 residuals)` --semantically_similar_to--> `Lender Concentration / Market Depth Variables (HHI, top1, top3, unique lenders)`  [INFERRED] [semantically similar]
  410DB/train/ablation_per_lever.py → Rebuild Brainstorming/Exploratory Policy Layer Variable Brainstorm.md
- `Policy Layer Research.md — Policy Lever Mapping and Evidence` --references--> `Branch Access Policy Lever (distance, branches within 5mi, closures)`  [EXTRACTED]
  Rebuild Brainstorming/Policy Layer Research.md → 410DB/train/ablation_per_lever.py
- `Policy Layer Research.md — Policy Lever Mapping and Evidence` --references--> `SSBCI State Policy Lever (4 SSBCI features)`  [EXTRACTED]
  Rebuild Brainstorming/Policy Layer Research.md → 410DB/train/ablation_per_lever.py
- `Policy Layer Research.md — Policy Lever Mapping and Evidence` --references--> `Microlender Ecosystem Lever (microloan_intermediary_within_25mi)`  [EXTRACTED]
  Rebuild Brainstorming/Policy Layer Research.md → 410DB/train/ablation_per_lever.py
- `COVID Regime Shift — Pre-COVID AUC 0.817 vs Post-COVID AUC 0.734` --semantically_similar_to--> `has_hmda Temporal Proxy — 1 for 2018+, misleads policy-audience readers`  [INFERRED] [semantically similar]
  410DB/notes/06_full_documentation.md → 410DB/train/prune_features.py

## Hyperedges (group relationships)
- **Mission-Lender ETL Pipeline (CDFI + MDI + Microlender)** — pull_cdfi_list_script, pull_mdi_list_script, pull_sba_micro_script, run_geocode_script [INFERRED 0.90]
- **Lender Classification Pipeline (FDIC + RSSD + CRA)** — pull_fdic_call_script, build_rssd_cra_crosswalk_script, classify_lenders_script, lender_class_csv [EXTRACTED 1.00]
- **Round 7 Feature Assembly (all feature builders → panel)** — build_concentration_script, build_cra_lender_mix_script, build_branch_geo_script, build_mdi_features_script, build_mission_proximity_script, build_concentration_residualized_script, build_round7_panel_script [EXTRACTED 1.00]
- **Seven Policy Lever Groups Jointly Define Ablation Study Design** — ablation_per_lever_script, residualized_concentration, branch_access_lever, mdi_mission_lever, ssbci_state_policy_lever, microlender_ecosystem_lever [EXTRACTED 0.95]
- **Walk-Forward Scripts Collectively Implement Two-Layer Architecture** — walk_forward_round7_script, walk_forward_bolton_script, walk_forward_overlay_script, regime_split_script, two_layer_architecture [INFERRED 0.88]
- **Rebuild Brainstorming Docs Collectively Specify Policy Layer Design** — handoff_doc, exploratory_brainstorm_doc, policy_layer_research_doc [EXTRACTED 0.92]

## Communities

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (77): activeFeatureCount(), activeFillLayerId(), activeGeoMeta(), activeHistogramStore(), activeHoverLayerId(), activeLeversForNote(), activePinnedLayerId(), activeStateTopList() (+69 more)

### Community 1 - "Community 1"
Cohesion: 0.08
Nodes (36): $(), addLayers(), auc(), bindBranchPopup(), bindLayerToggles(), bindMap(), buildOpacityExpression(), buildRampExpression() (+28 more)

### Community 2 - "Community 2"
Cohesion: 0.1
Nodes (26): Ablation Surprise: residualized_concentration drives most signal (−0.096 AUC when dropped), Bolt-On Result: Mean AUC 0.889 (+0.032 over Round 5), AP gain is noise, Branch Access Policy Lever (distance, branches within 5mi, closures), Census Geocoder — Primary Geocoding (~85% hit rate, batch, free, no API key), COVID Regime Shift — Pre-COVID AUC 0.817 vs Post-COVID AUC 0.734, 8-Fold Walk-Forward Cross-Validation Structure, Exploratory Policy Layer Variable Brainstorm.md — Predictor Shortlist, 04_final_results.md — Round 7 Final Performance Results (+18 more)

### Community 3 - "Community 3"
Cohesion: 0.18
Nodes (20): abImpactByGroup(), leverGroupImportance(), logit(), scenarioLeverEffect(), scenarioLeverSummary(), showLeverTip(), totalLeverImportance(), build_unified_xwalk() (+12 more)

### Community 4 - "Community 4"
Cohesion: 0.24
Nodes (13): lag_aware_acs_merge(), load_acs(), load_cra_county(), load_cra_tract(), load_fdic(), load_hmda(), load_oz(), load_persistent_poverty() (+5 more)

### Community 5 - "Community 5"
Cohesion: 0.27
Nodes (12): discover(), iter_lines(), main(), normalize_tract(), parse_disclosure(), parse_transmittal(), Return {year: {'discl': [...], 'trans': [...], 'aggr': [...]}}., Return (tract_lenders, county_lender_loans) for this year.      tract_lenders[(t (+4 more)

### Community 6 - "Community 6"
Cohesion: 0.26
Nodes (11): aggregate_latest(), build_city_index(), headline_metrics(), load_county_names(), load_latest_population(), main(), Per tract, take the most-recent (year, fold) calibrated probability., Mean across folds — the canonical AUC/AP for this project. (+3 more)

### Community 7 - "Community 7"
Cohesion: 0.31
Nodes (10): apportion(), discover(), iter_lines(), main(), normalize_tract(), parse_year(), Return (tract_lender_presence, county_lender_buckets).      tract_lender_presenc, Equal-share apportion county-lender bucket totals across tracts where the     le (+2 more)

### Community 8 - "Community 8"
Cohesion: 0.38
Nodes (9): cache_get(), cache_path(), cache_put(), census_batch(), geocode_df(), main(), nominatim_one(), normalize() (+1 more)

### Community 9 - "Community 9"
Cohesion: 0.47
Nodes (9): audit_acs(), audit_cra(), audit_fdic_sod(), audit_hmda(), audit_sba(), cra_dat_columns(), emit(), main() (+1 more)

### Community 10 - "Community 10"
Cohesion: 0.33
Nodes (8): build_panel(), main(), build_ssbci_overlay.py ======================  Build a state-year feature panel, Attempt to fetch Treasury SSBCI summary pages.      Returns a parsed per-state p, Build a single (state, year) row using the documented fallback rules., _row_for_year(), try_scrape_treasury(), write_csv()

### Community 11 - "Community 11"
Cohesion: 0.33
Nodes (8): fit_one(), hmda_fillna(), latest_train_year(), main(), Latest year T where target_h{horizon} is observable (T + h ≤ 2024)., Fit ONE final-deployable model on rows where year ≤ train_end and target observa, Return top-k (feature, signed_shap) per row. Uses XGBoost native pred_contribs., shap_top()

### Community 12 - "Community 12"
Cohesion: 0.33
Nodes (8): add_any_desert(), add_forward_targets(), add_origination_desert(), add_service_desert(), main(), For each (tract, year), compute target families at H1, H3, H6.      H1: 1-year h, Bottom-decile lender count, computed within (year × peer-group)., Bottom-decile origination per capita (HMDA, post-2018 only).

### Community 13 - "Community 13"
Cohesion: 0.33
Nodes (8): calibration_table(), decision_curve(), main(), Return a DataFrame with per-decile (mean predicted, mean observed, n)., Net-benefit decision-curve analysis (Vickers-Elkin).      NB(t) = (TP / N) - (FP, Per-state AUC across all folds — a cheap leave-one-state-out signal.      If exc, state_auc(), top_n_precision()

### Community 14 - "Community 14"
Cohesion: 0.39
Nodes (7): build_year(), ensure_tract_centroids(), load_sod_year(), main(), For one year, compute distance, branches_within_5mi, closures-in-prior-3y., Load tract centroids; pull from Census Gazetteer if missing., to_radians()

### Community 15 - "Community 15"
Cohesion: 0.39
Nodes (7): build_year(), load_mdi_year(), load_sod_year(), main(), Compute MDI features for one year., Read the MDI sheet for a given year and return DataFrame with CERT., to_radians()

### Community 16 - "Community 16"
Cohesion: 0.48
Nodes (6): main(), paged_get(), pull_assets_year(), pull_institutions(), FDIC API pagination via offset/limit. Returns merged data list.      The FDIC AP, Pull Call Report ASSET per institution at year-end.

### Community 17 - "Community 17"
Cohesion: 0.43
Nodes (6): evaluate(), main(), make_model(), Identical hyperparameters to walk_forward_round7.py., Standard metric bundle, NaN-safe when only one class present., run_study()

### Community 18 - "Community 18"
Cohesion: 0.47
Nodes (5): aggregate_feature_ranking(), main(), Average XGBoost gain importance across all 8 fold importance files., Run all 8 folds with the given feature subset; return per-fold metrics., train_walk_forward()

### Community 19 - "Community 19"
Cohesion: 0.47
Nodes (5): aggregate_state_year(), main(), Yield dict-rows from the CFPB CSV endpoint, streaming., Stream LAR, aggregate to tract-year, write CSV. Return summary., stream_state_year()

### Community 20 - "Community 20"
Cohesion: 0.53
Nodes (5): fit_predict(), main(), metrics(), prepare(), Quick model — half the trees of full run for speed across 50+ folds.

### Community 21 - "Community 21"
Cohesion: 0.4
Nodes (3): precovid_postcovid_splits(), Shared horizon + fold config for all round7 training scripts.  ROUND7_HORIZON en, For regime_split.py. Returns ((train_yrs, val_yr, test_yrs), ...)     pre-COVID

### Community 22 - "Community 22"
Cohesion: 0.7
Nodes (4): directional_sanity(), main(), per_fold_stability(), per_state_ap()

### Community 23 - "Community 23"
Cohesion: 0.6
Nodes (4): evaluate(), main(), Run all 8 folds with the given feature set; return per-fold metric dicts., run_walk_forward()

### Community 24 - "Community 24"
Cohesion: 0.7
Nodes (4): evaluate(), main(), make_objective(), prepare()

### Community 25 - "Community 25"
Cohesion: 0.6
Nodes (3): evaluate(), main(), prepare()

### Community 26 - "Community 26"
Cohesion: 0.6
Nodes (4): evaluate(), main(), prepare_features(), Coerce numeric, fill HMDA NaN for pre-2018 with 0 (since has_hmda tracks it).

### Community 27 - "Community 27"
Cohesion: 0.83
Nodes (3): load_raw(), main(), normalize()

### Community 28 - "Community 28"
Cohesion: 0.83
Nodes (3): load_raw(), main(), normalize()

### Community 29 - "Community 29"
Cohesion: 0.83
Nodes (3): count_within(), main(), to_radians()

### Community 30 - "Community 30"
Cohesion: 0.67
Nodes (3): main(), Within a (year, peer_group) cohort, regress each target column on     [log(n_cra, residualize_cohort()

### Community 31 - "Community 31"
Cohesion: 0.83
Nodes (3): evaluate(), main(), prepare()

### Community 32 - "Community 32"
Cohesion: 0.67
Nodes (3): load_zcta_tract_weights(), main(), Return a DataFrame [zcta, tract_fips, weight] where weight is the     share of t

### Community 33 - "Community 33"
Cohesion: 0.67
Nodes (3): main(), ACS uses -666666666 etc. as null sentinels; convert to ''., to_num()

### Community 34 - "Community 34"
Cohesion: 0.67
Nodes (3): main(), parse_year(), SBA dates are usually YYYY-MM-DD or MM/DD/YYYY.

### Community 35 - "Community 35"
Cohesion: 0.67
Nodes (3): fetch_year(), main(), Pull all SoD records for a single year and write a single CSV. Returns row count

### Community 36 - "Community 36"
Cohesion: 0.83
Nodes (3): evaluate(), main(), prepare_features()

### Community 37 - "Community 37"
Cohesion: 0.83
Nodes (3): evaluate(), main(), prepare()

### Community 38 - "Community 38"
Cohesion: 1.0
Nodes (2): main(), parse_page()

### Community 40 - "Community 40"
Cohesion: 1.0
Nodes (2): load_optional_csv(), main()

### Community 41 - "Community 41"
Cohesion: 1.0
Nodes (2): load_csv(), main()

### Community 42 - "Community 42"
Cohesion: 1.0
Nodes (2): evaluate(), main()

### Community 43 - "Community 43"
Cohesion: 1.0
Nodes (2): evaluate(), main()

### Community 44 - "Community 44"
Cohesion: 1.0
Nodes (2): main(), parse_money()

### Community 45 - "Community 45"
Cohesion: 1.0
Nodes (2): load_demographics(), main()

### Community 46 - "Community 46"
Cohesion: 1.0
Nodes (2): fetch_state_year(), main()

### Community 47 - "Community 47"
Cohesion: 1.0
Nodes (2): main(), prepare()

### Community 48 - "Community 48"
Cohesion: 1.0
Nodes (3): 03_decision_rule.md — Phase B AP Threshold Decision Rule, Phase B Decision Rule: AP threshold STRONG ≥ 0.10 (not PR-AUC ≥ 0.6), Random Baseline AP ≈ 1.7% (equals positive rate for rare-event target)

### Community 49 - "Community 49"
Cohesion: 0.67
Nodes (3): Credit Union NCUA Join (bypass FDIC, agency_code=4, ~10K institutions), 01_rssd_cra_crosswalk.md — RSSD to CRA Respondent ID Crosswalk (94.6% match), RSSD-CRA Match Rate: 94.6% volume-weighted; success criterion ≥ 95%

### Community 56 - "Community 56"
Cohesion: 1.0
Nodes (2): 410DB README — Round 7 Two-Layer Credit-Desert Risk Project, tracts.geojson (Dashboard Map Data)

### Community 57 - "Community 57"
Cohesion: 1.0
Nodes (1): Per tract, take the most-recent (year, fold) calibrated probability.

### Community 58 - "Community 58"
Cohesion: 1.0
Nodes (1): Mean across folds — the canonical AUC/AP for this project.

### Community 59 - "Community 59"
Cohesion: 1.0
Nodes (1): Build city search index from Census Gazetteer + decennial place-pop API.     Fal

### Community 60 - "Community 60"
Cohesion: 1.0
Nodes (1): Per tract, take the most-recent (year, fold) calibrated probability.

### Community 61 - "Community 61"
Cohesion: 1.0
Nodes (1): Mean across folds — the canonical AUC/AP for this project.

### Community 62 - "Community 62"
Cohesion: 1.0
Nodes (1): Build city search index from Census Gazetteer + decennial place-pop API.     Fal

### Community 63 - "Community 63"
Cohesion: 1.0
Nodes (1): tract_lender_year.csv (CRA Apportioned)

### Community 64 - "Community 64"
Cohesion: 1.0
Nodes (1): lender_class.csv (Lender Flags)

### Community 65 - "Community 65"
Cohesion: 1.0
Nodes (1): cra_to_rssd.csv (RSSD-CRA Crosswalk)

### Community 66 - "Community 66"
Cohesion: 1.0
Nodes (1): mdi_list.csv (MDI Roster)

### Community 67 - "Community 67"
Cohesion: 1.0
Nodes (1): cdfi_list.csv (CDFI Certified List)

### Community 68 - "Community 68"
Cohesion: 1.0
Nodes (1): microlender_list.csv (SBA Microlender List)

### Community 69 - "Community 69"
Cohesion: 1.0
Nodes (1): FDIC Institutions CSV (RSSD/CERT)

### Community 70 - "Community 70"
Cohesion: 1.0
Nodes (1): assets_by_year.csv (FDIC Call Report)

### Community 71 - "Community 71"
Cohesion: 1.0
Nodes (1): cdfi_geocoded.csv (CDFI with lat/lon)

### Community 72 - "Community 72"
Cohesion: 1.0
Nodes (1): microlender_geocoded.csv (Microlenders with lat/lon)

### Community 73 - "Community 73"
Cohesion: 1.0
Nodes (1): tract_centroids_2020.csv (Census TIGER)

### Community 74 - "Community 74"
Cohesion: 1.0
Nodes (1): state_year_ssbci.csv (SSBCI Overlay)

### Community 76 - "Community 76"
Cohesion: 1.0
Nodes (1): tract_year_with_target_round7.parquet (Training Panel)

### Community 77 - "Community 77"
Cohesion: 1.0
Nodes (1): test_predictions.parquet (Walk-Forward Predictions)

### Community 78 - "Community 78"
Cohesion: 1.0
Nodes (1): FDIC BankFind API (External)

### Community 79 - "Community 79"
Cohesion: 1.0
Nodes (1): Census Geocoder API (External)

### Community 80 - "Community 80"
Cohesion: 1.0
Nodes (1): Nominatim (OpenStreetMap) Geocoder

### Community 81 - "Community 81"
Cohesion: 1.0
Nodes (1): FFIEC CRA Disclosure Flat Files (D1/D6)

### Community 82 - "Community 82"
Cohesion: 1.0
Nodes (1): FDIC Summary of Deposits (SoD)

### Community 83 - "Community 83"
Cohesion: 1.0
Nodes (1): Target: Becomes Service Desert (h+3/h+6)

### Community 84 - "Community 84"
Cohesion: 1.0
Nodes (1): web/README.md — Dashboard Build and Data Documentation

### Community 85 - "Community 85"
Cohesion: 1.0
Nodes (1): 00_design_brief.md — Round 7 Design Brief and Feature Tiers

### Community 86 - "Community 86"
Cohesion: 1.0
Nodes (1): 05_methodology_brief.md — Methodology Brief

## Knowledge Gaps
- **85 isolated node(s):** `Per tract, take the most-recent (year, fold) calibrated probability.`, `Mean across folds — the canonical AUC/AP for this project.`, `Latest non-null tract population for county weighting.`, `Build city search index from Census Gazetteer + decennial place-pop API.     Fal`, `FDIC API pagination via offset/limit. Returns merged data list.      The FDIC AP` (+80 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 38`** (3 nodes): `main()`, `parse_page()`, `pull_sba_micro.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (3 nodes): `load_optional_csv()`, `main()`, `classify_lenders.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 41`** (3 nodes): `load_csv()`, `main()`, `build_round7_panel.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 42`** (3 nodes): `walk_forward_overlay.py`, `evaluate()`, `main()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 43`** (3 nodes): `walk_forward_round7.py`, `evaluate()`, `main()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 44`** (3 nodes): `main()`, `parse_money()`, `build_branches.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 45`** (3 nodes): `load_demographics()`, `main()`, `build_peers.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 46`** (3 nodes): `fetch_state_year()`, `main()`, `pull_acs.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (3 nodes): `main()`, `prepare()`, `feature_importance.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 56`** (2 nodes): `410DB README — Round 7 Two-Layer Credit-Desert Risk Project`, `tracts.geojson (Dashboard Map Data)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 57`** (1 nodes): `Per tract, take the most-recent (year, fold) calibrated probability.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 58`** (1 nodes): `Mean across folds — the canonical AUC/AP for this project.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 59`** (1 nodes): `Build city search index from Census Gazetteer + decennial place-pop API.     Fal`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 60`** (1 nodes): `Per tract, take the most-recent (year, fold) calibrated probability.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 61`** (1 nodes): `Mean across folds — the canonical AUC/AP for this project.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 62`** (1 nodes): `Build city search index from Census Gazetteer + decennial place-pop API.     Fal`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 63`** (1 nodes): `tract_lender_year.csv (CRA Apportioned)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 64`** (1 nodes): `lender_class.csv (Lender Flags)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 65`** (1 nodes): `cra_to_rssd.csv (RSSD-CRA Crosswalk)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 66`** (1 nodes): `mdi_list.csv (MDI Roster)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 67`** (1 nodes): `cdfi_list.csv (CDFI Certified List)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 68`** (1 nodes): `microlender_list.csv (SBA Microlender List)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 69`** (1 nodes): `FDIC Institutions CSV (RSSD/CERT)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 70`** (1 nodes): `assets_by_year.csv (FDIC Call Report)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 71`** (1 nodes): `cdfi_geocoded.csv (CDFI with lat/lon)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 72`** (1 nodes): `microlender_geocoded.csv (Microlenders with lat/lon)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 73`** (1 nodes): `tract_centroids_2020.csv (Census TIGER)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 74`** (1 nodes): `state_year_ssbci.csv (SSBCI Overlay)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 76`** (1 nodes): `tract_year_with_target_round7.parquet (Training Panel)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 77`** (1 nodes): `test_predictions.parquet (Walk-Forward Predictions)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 78`** (1 nodes): `FDIC BankFind API (External)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 79`** (1 nodes): `Census Geocoder API (External)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 80`** (1 nodes): `Nominatim (OpenStreetMap) Geocoder`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 81`** (1 nodes): `FFIEC CRA Disclosure Flat Files (D1/D6)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 82`** (1 nodes): `FDIC Summary of Deposits (SoD)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 83`** (1 nodes): `Target: Becomes Service Desert (h+3/h+6)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 84`** (1 nodes): `web/README.md — Dashboard Build and Data Documentation`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 85`** (1 nodes): `00_design_brief.md — Round 7 Design Brief and Feature Tiers`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 86`** (1 nodes): `05_methodology_brief.md — Methodology Brief`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `flyToState()` connect `Community 0` to `Community 1`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Why does `logit()` connect `Community 3` to `Community 0`?**
  _High betweenness centrality (0.016) - this node is a cross-community bridge._
- **What connects `Per tract, take the most-recent (year, fold) calibrated probability.`, `Mean across folds — the canonical AUC/AP for this project.`, `Latest non-null tract population for county weighting.` to the rest of the system?**
  _85 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.06 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.08 - nodes in this community are weakly interconnected._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.1 - nodes in this community are weakly interconnected._