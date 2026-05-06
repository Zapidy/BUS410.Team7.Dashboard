# Round 5 — Handoff

**Project**: BUS410 Team 7 Credit-Desert Prediction Model · Round 5 rebuild
**Status as of 2026-04-28**: model + dashboard shipped; documented; ready to present
**Previous round**: [../round4/](../round4/) — preserved as historical reference

This document is the context-clearing summary. If you're picking this up cold, read this first.

---

## What this is

A tract-level forecasting model that predicts which US census tracts will become **credit deserts** at year+1, with an interactive dashboard surfacing the results. Round 4's single-split AUC 0.751 → Round 5's walk-forward AUC **0.857 ± 0.044** with 25 circular features removed and multiple leakage paths closed.

Two artifacts:
1. **The model**: 8-fold walk-forward XGBoost on a 2009–2024 tract-year panel
2. **The dashboard**: interactive map at `web/` — quant-terminal aesthetic, full filtering

---

## Where things live

```
round5/
├── HANDOFF.md                       this document
├── README.md                        project overview
├── CHANGES.md                       full chronological narrative across all 16+ sections
├── .impeccable.md                   design context for the dashboard
├── CLAUDE.md                        project intro + duplicated design context

├── notes/
│   ├── 00_methodology.md            the operating brief — read this first if rebuilding the model
│   ├── 02_etl_log.md                ETL log + manual download instructions
│   └── 03_schema_audit.md           year-over-year schema audit + reconciliation plan

├── etl/                             data-acquisition + parsing scripts
│   ├── download_all.sh              bash orchestrator for curl-able sources
│   ├── schema_eda.py                YOY schema-drift audit
│   ├── cra/parse_cra.py             CRA D-files → tract-year + county-year + reporters
│   ├── fdic/pull_sod.py             FDIC SoD via api.fdic.gov (paginated)
│   ├── fdic/parse_sod.py            SoD per-year CSVs → county-year features
│   ├── sba/parse_sba.py             SBA loans → zip-year aggregates
│   ├── acs/pull_acs.py              ACS 5-year, modern variables (2014+)
│   ├── acs/pull_acs_early.py        ACS 5-year, legacy variables (2010-2013)
│   ├── acs/pivot_acs.py             ACS state-JSON → canonical tract-year CSV
│   ├── hmda/pull_hmda.py            HMDA streaming aggregator (CFPB Data Browser API)
│   └── fred/pull_macro.py           FRED macro series (currently network-blocked here)

├── features/
│   ├── harmonize_tracts.py          Phase 2.5 — project all years onto 2020 vintage
│   ├── build_panel.py               joins all sources → tract-year parquet
│   └── define_target.py             desert thresholds + state/transition targets

├── train/
│   ├── walk_forward.py              first-pass with all features (inflated by leakage)
│   ├── walk_forward_clean.py        Tier-1+2 circular features dropped
│   ├── walk_forward_audit_fixed.py  CURRENT — Tier-3 also dropped + 5 audit fixes
│   ├── walk_forward_lgbm_optuna.py  LightGBM + Optuna tuning experiment
│   ├── spatial_robustness.py        leave-one-state-out CV
│   └── diagnostics.py               calibration / top-N / decision-curve / per-state

├── data/
│   ├── raw/                         downloaded source data (~7 GB, .gitignored)
│   ├── processed/                   parsed features and the panel parquet (~300 MB)
│   └── crosswalks/                  Census Bureau relationship files

├── diagnostics/
│   ├── walk_forward/                early run (with circular features — inflated)
│   ├── walk_forward_clean/          intermediate (Tier-1+2 drops only)
│   ├── walk_forward_audit_fixed/    CURRENT — final reportable predictions
│   ├── walk_forward_lgbm_optuna/    LightGBM tuning run (~same AUC as XGBoost)
│   └── spatial_robustness/          LOSO CV outputs

├── web/                             showcase dashboard (this is the deliverable)
│   ├── index.html                   markup, font + library CDN links
│   ├── styles.css                   full quant-terminal design system
│   ├── app.js                       MapLibre + filters + tooltip + AUC compute
│   ├── build_dashboard_data.py      rebuild data files from upstream model artifacts
│   ├── data/                        tracts.geojson (29 MB) + states + state_stats + state_bbox
│   ├── .github/workflows/pages.yml  staged GitHub Pages deploy (not pushed)
│   └── README.md                    dashboard-specific docs

└── models/                          (empty; per-fold model artifacts saved in diagnostics/)
```

---

## Headline numbers (commit these to memory)

| Metric | Value | Source |
|---|---|---|
| **Mean test AUC** | **0.857 ± 0.044** | Fold-averaged across 8 walk-forward folds |
| Per-fold AUCs | F1 0.882 · F2 0.884 · F3 0.904 · F4 0.913 · F5 0.826 · F6 0.823 · F7 0.794 · F8 0.826 | F4 peaks pre-COVID; F5+ degrades through COVID era |
| Mean test AP | 0.172 | |
| Mean AP-lift | **9.25×** | Top-ranked tracts ~9.25× more likely to become deserts |
| Brier (calibrated) | 0.020 | Isotonic calibration was a no-op; model was already well-calibrated |
| Top-100 precision | 70% | Of the 100 highest-risk tracts, 70 actually transition |
| Top-1,000 precision | 42% | |
| Median per-state AUC | 0.81 | IQR 0.78–0.87 across 51 jurisdictions |
| Spatial-leakage tax | +0.004 | Random K-fold (0.893) − Leave-one-state-out (0.889); essentially zero |
| Round 4 baseline | 0.751 AUC | Round 5 is **+0.106 AUC** with leakage paths closed |

The dashboard's right-rail "POOLED AUC" reads ~0.752. **This is a different statistic** from the masthead 0.857 — see `notes/00_methodology.md` and the METHODS panel in the dashboard for the explanation. The two are not expected to match even at default.

---

## Pipeline — how to reproduce the model end-to-end

```bash
cd /Users/navya/Documents/Gravity/School/Shivani/round5

# 1. ETL — pulls everything that's curl-able. Manual downloads (CRA, NHGIS) documented in notes/02_etl_log.md.
bash etl/download_all.sh
python3 etl/fdic/pull_sod.py --start 2009 --end 2024
python3 etl/acs/pull_acs.py
python3 etl/acs/pull_acs_early.py
python3 etl/hmda/pull_hmda.py

# 2. Per-source parsing
python3 etl/cra/parse_cra.py
python3 etl/fdic/parse_sod.py
python3 etl/sba/parse_sba.py
python3 etl/acs/pivot_acs.py

# 3. Tract vintage harmonization (Phase 2.5)
python3 features/harmonize_tracts.py

# 4. Panel build + target definition
python3 features/build_panel.py
python3 features/define_target.py

# 5. Walk-forward training (this is the canonical run)
python3 train/walk_forward_audit_fixed.py
python3 train/diagnostics.py walk_forward_audit_fixed
python3 train/spatial_robustness.py
```

End-to-end runtime ~1 hour, dominated by the HMDA pull (~30 min) and the panel build.

---

## Dashboard — how to run

```bash
cd /Users/navya/Documents/Gravity/School/Shivani/round5/web
python3 -m http.server 8765
# open http://localhost:8765/
```

To rebuild the data files from upstream artifacts (after a model re-run):

```bash
python3 build_dashboard_data.py    # produces tracts_raw.geojson + state_stats + state_bbox
npx --yes mapshaper@latest data/tracts_raw.geojson \
  -simplify dp 1.5% keep-shapes -clean \
  -o data/tracts.geojson precision=0.001 format=geojson
npx --yes mapshaper@latest data/tracts_raw.geojson \
  -each "st = f.substring(0,2)" -dissolve st -simplify dp 25% keep-shapes -clean \
  -o data/states.geojson precision=0.001 format=geojson
rm data/tracts_raw.geojson
```

Deploy to GitHub Pages: workflow staged at `.github/workflows/pages.yml`. Push the `web/` folder to a new GitHub repo with Pages → GitHub Actions enabled.

---

## What was actively done in the most recent session

(In rough chronological order — for a complete narrative see CHANGES.md.)

1. **Round 4 inheritance + first dashboard built** (a civic-infographic-register map, then deleted at user request).
2. **Wrote `notes/00_methodology.md`** — the operating brief (15-year scope, walk-forward validation, leakage taxonomy).
3. **Massive ETL pull** — CRA (5.5 GB unpacked, manual browser download), FDIC SoD (122 MB via API), HMDA (550k tract-state-years streamed from CFPB API, 2018-2024 only), SBA (870 MB), ACS (245k tract-vintages), Census crosswalks (replaced NHGIS), USDA codes.
4. **Per-source parsers** — stdlib-only Python, all sources → canonical tract-year or county-year CSVs.
5. **Schema EDA** — flagged 8 YOY drift issues, 6 turned out to be aesthetic-by-design, 2 needed real fixes (SBA program-family + tract vintage).
6. **Panel build + target definition** — 1.4M rows × 91 cols. Two target families: state (sticky, leaky) and transition (the one we use).
7. **First walk-forward run** — AUC 0.93. **Caught circular features** (n_cra_lenders directly defines target). Removed Tier 1+2 → AUC 0.83.
8. **Tract vintage harmonization (Phase 2.5)** — projected onto 2020 vintage. AUC 0.83 → 0.85.
9. **Spatial robustness** — leave-one-state-out CV. **Confirmed essentially zero spatial-leakage tax** (+0.004 between random K-fold and LOSO).
10. **LightGBM + Optuna tuning** — wash. ~Same AUC as default XGBoost. Hit ceiling for this feature set.
11. **Methodology audit (round 2)** — caught FDIC features as Tier-3 circular (banks ARE CRA reporters), tightened ACS lag rule, standardized test windows, excluded PR/VI from training, added isotonic calibration. **Final AUC 0.857.**
12. **Dashboard built** — quant-terminal aesthetic per `.impeccable.md`. MapLibre GL JS + vanilla JS, no bundler.
13. **Dashboard polish loop**:
    - `/impeccable critique` → 31/40 score, 5 priority issues identified
    - `/typeset` → projector-distance type bumps in >1600px media query
    - `/distill` → collapsed 4 sliders under expandable ADVANCED section (12 controls → 6)
    - `/clarify` → semantic empty states + keyboard hints in colophon
    - `/polish` → h3 → h2, DOCS → METHODS rename, WCAG AA Large contrast fix
14. **POOLED vs FOLD-AVERAGED AUC disambiguation** — renamed the right-rail metric to be honest about the statistic it computes.

---

## Outstanding work (in priority order)

What would meaningfully move the model forward, ranked by AUC-leverage:

1. **HMDA pre-2018 manual backfill** — the API only goes back to 2018; pre-2018 HMDA must be manually downloaded from CFPB's legacy historic-data page or FFIEC's older flat-file system. Plausibly **+0.02 to +0.04 AUC** for the F1-F3 folds where HMDA features are currently `has_hmda=0`.
2. **SBA tract assignment** — currently aggregated at zip-year level. Apportion via HUD ZIP-tract crosswalk (account-gated) or spatial join via geocoded borrower addresses. Plausibly **+0.01 to +0.02 AUC** plus richer policy-relevant features.
3. **Branch-distance features** — using FDIC SoD lat/lng, compute drive-time isochrones from each tract centroid to nearest active branch. Captures supply-side access in a way count-based features can't. Plausibly **+0.01 to +0.02 AUC**.
4. **Trailing-Δ feature engineering** — replace the 11 dropped CRA-side circular features with **5-to-2 year trailing deltas** (Δ between T-5 and T-2, excluding the most recent year). Restores the lender-behavior signal without target leakage. Plausibly **+0.005 to +0.015 AUC**.
5. **External hold-out year** — currently Optuna tuning happened on F1's val, so F2-F8 aren't strictly out-of-sample. Holding out 2024 entirely (never train, never validate, never tune) would be the gold standard for a paper-grade defense. Loses one walk-forward fold.
6. **Population-weighted 2010↔2020 crosswalk** — currently area-only weights are used (the 2010↔2020 file doesn't include population overlap). For tracts with concentrated population in a small overlap area, area-weights mis-estimate. Use Census 2020 block-level population to compute proper population weights. Plausibly **+0.002 AUC**, more accuracy.

What's worth doing for the dashboard, ranked by user value:

7. **Multi-target joint model** — predict service / origination / branch desert simultaneously with a multi-output head. Richer policy outputs.
8. **Year scrubber** — switch from single-year (2023) to a year slider 2016–2024, switching `y_prob_{year}` source data. Lets viewers see the COVID-era AUC drop in real time.
9. **Refreshed showcase narrative** — the dashboard shows the model's predictions but doesn't tell a story. A 3-step "guided tour" overlay (intro → headline finding → call to interaction) would land better with a recruiter audience.
10. **City lookup for tooltip** — currently shows County + ZIP + State. City would require either HUD ZIP-tract-city crosswalk (account-gated) or spatial join against TIGER PLACES shapefiles.

---

## Known issues / caveats (deliberate compromises)

These are documented in CHANGES.md but worth re-stating:

- **POOLED AUC 0.752 ≠ FOLD-AVERAGED AUC 0.857**. Different statistics. Glossary tooltips and METHODS panel explain. Not a bug.
- **Top-25 list and per-state AUC table rows are click-only** (no `tabindex`). Mouse-only convenience by design — adding focus to all 76 rows would flood Tab navigation. Power users can access the same data via the METHODS panel's fold table.
- **HMDA bifurcation** — features are `has_hmda=0` for 2009-2017 panel rows because the API doesn't expose pre-2018 data. The `has_hmda` flag tells the model which regime each row is in.
- **Tract harmonization arithmetic** — split tracts get population-weighted apportionment. For *count* features this is defensible. For *ratio/churn* features computed at parse time it's slightly questionable (the weighted average doesn't perfectly preserve the ratio semantics). A Phase-3 fix would harmonize at parse time, not at output time.
- **The 2010↔2020 crosswalk uses area weights** (the modern Census file lacks population overlap data). Affects ~5% of tracts that split or merge between vintages.
- **Tract-by-tract data only goes back to 2009** because that's when ACS 5-year first published. Pre-2009 demographics rely on the 2000 decennial only — too sparse for the panel.
- **Per-state results are filtered to 50 states + DC**. Puerto Rico and US Virgin Islands are excluded from training (small samples, different rural-urban geography) and from per-state diagnostic reports.
- **No external held-out year**. Optuna tuned on F1's val; F2-F8 use that tuned config. Strictly speaking they're not truly out-of-sample. For class-deliverable purposes this is fine; for a paper, hold out 2024.

---

## Aesthetic constraints — the dashboard

The dashboard follows `.impeccable.md` strictly. **Quant terminal / institutional dark.** Anti-references explicitly include the civic-infographic register (Urban Institute / Pew), generic SaaS dashboard, and glassmorphism / glow / gradient-heavy modern web. If you're modifying the dashboard, anything that adds:

- Cards with rounded corners and drop shadows
- Glass blur effects or glow accents
- Gradient text or gradient buttons
- `border-left: Npx solid var(--accent)` accent stripes (>1px is banned per `.impeccable.md`)
- The fonts Inter, DM Sans, Plus Jakarta, Fraunces, Newsreader, Instrument *, Outfit, IBM Plex *, Space *, Cormorant, Crimson, Playfair, Lora, Syne

…is a regression. Run `/impeccable critique` after any non-trivial dashboard change to flag drift.

Current type stack: **Funnel Display** (Pangram Pangram, OFL) + **Funnel Sans** (Pangram, OFL) + **JetBrains Mono** (Google Fonts, OFL). All numbers are mono with `font-variant-numeric: tabular-nums`.

Palette: OKLCH cool-tinted neutrals (hue 240) + single warm accent `oklch(0.78 0.18 65)` (burnt amber). The accent appears only on: highest-risk choropleth tracts, active toggle states, the headline AUC number, focus rings, the METHODS pill when expanded, the ADVANCED dot when modified, the keyboard `<kbd>` letters in the colophon. Nowhere else.

---

## Useful keyboard shortcuts (dashboard)

| Key | Action |
|---|---|
| `R` | Reset all filters |
| `D` | Toggle METHODS panel |
| `Esc` | Unpin tooltip / close METHODS |

---

## How to write a 5-minute presentation

1. **Open with the headline**: AUC 0.857 ± 0.044 across 8 walk-forward folds (vs Round 4's single-split 0.751). +0.106.
2. **Show the choropleth**: full-bleed dark map, single-hue amber ramp. The audience sees risk geography in 5 seconds.
3. **Click into a top-25 risk tract**: show the tooltip. Demographic context + predicted risk in one pin.
4. **Click METHODS**: walk through the WHY POOLED AUC ≠ HEADLINE AUC explanation if the audience is technical, or skip to LEAKAGE PATHS CLOSED if they're not.
5. **Demonstrate filtering**: Vermont rural tracts. Show the pooled AUC change. Show top-25 update. The dashboard does real computation, not just visual filtering.

---

## Memory hooks

If you're returning to this project after a context clear, the things that will save you the most time:

- **Read [notes/00_methodology.md](notes/00_methodology.md) first.** It captures the operating logic for the entire rebuild.
- **The `walk_forward_audit_fixed` directory is the canonical run.** Other diagnostics dirs are intermediate or experimental.
- **The model has hit its AUC ceiling at ~0.85 for the current feature set.** Further gains require new features (HMDA backfill, SBA tract, branch-distance), not more tuning.
- **The dashboard is self-contained at [web/](web/).** All upstream dependencies are referenced via relative paths (`../round4/tract_boundaries.geojson` for geometry, `../diagnostics/walk_forward_audit_fixed/test_predictions.parquet` for predictions).
- **DOCS → METHODS rename happened.** If you see "DOCS" in the dashboard UI, you're looking at a stale build.
