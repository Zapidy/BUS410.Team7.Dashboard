# Round 7 · Two-Layer Credit-Desert Risk

Standalone web dashboard for the BUS 410 Round 7 presentation. One scrollable
page, vanilla HTML / CSS / JS, MapLibre GL JS via CDN. No bundler.

## What it shows

- **Model 1 — Diagnostic.** The Round 5 champion. 39 features. Walk-forward
  AUC ≈ 0.857.
- **Model 2 — Influenceable.** Round 7 phase A. 20 lender / branch / policy
  features, residualized against demographics. Walk-forward AUC ≈ 0.792.

Both models are calibrated; both share the same panel and target. The page
toggles between their tract-level predictions on a single choropleth.

## Build the data

```bash
cd web
python3 build_dashboard_data.py
```

This pulls:

- `../round5-diagnostic/diagnostics/walk_forward_h3/test_predictions.parquet`
- `../round5-diagnostic/diagnostics/walk_forward_h6/test_predictions.parquet`
- `../diagnostics/round7_phaseA_h3/test_predictions.parquet`
- `../diagnostics/round7_phaseA_h6/test_predictions.parquet`
- `../diagnostics/round7_pruned_h{3,6}/sweep_results.csv` and `feature_ranking.csv`
- `../diagnostics/round7_regime_split/*.csv`
- `../round5-diagnostic/web/data/counties.geojson`
- `../round5-diagnostic/data/processed/acs/tract_year_h2020.csv` for county population weights when the Round 7 panel has no `population` column
- `data/tracts.geojson` as the tract geometry fallback if the archived Round 5 tract geometry is unavailable

Requires `pandas`, `numpy`, `scikit-learn`, and a parquet engine such as `pyarrow`.

…and writes:

- `data/tracts.geojson`        ~25 MB raw, ~4 MB gzipped
- `data/counties.geojson`      county polygons with population-weighted tract-risk rollups
- `data/county_stats.json`     county drawer payload, including top tracts
- `data/state_stats.json`      per-state tract/county summaries, histograms, AUC, and AP
- `data/state_bbox.json`       per-state bbox for fly-to
- `data/ablation_h{3,6}.json`  trimmed lever-group ablation
- `data/pruning_h{3,6}.json`   k-feature sweep + top-10 ranking
- `data/regime_h{3,6}.json`    pre/post-COVID metrics + top features

## Serve

```bash
cd round7/web
python3 -m http.server 8009
# open http://localhost:8009
```

If you serve gzipped, the geojson drops to ~4 MB. The tract source is the
heaviest payload by far.

## Design

See [`../.impeccable.md`](../.impeccable.md) for the design brief. Headline
constraints, restated:

- Light parchment background, deep ink-blue text
- Source Serif 4 (display), Public Sans (body), Inconsolata (numerics)
- Two distinct color signatures: blue for diagnostic, terracotta for influenceable
- Hairline rules — no card chrome, no shadows
- Tabular numerics on every metric

This is the sibling product to Round 5's Bloomberg-Terminal dashboard. They
intentionally do not share a visual register.
