# Drivers panel: show distribution position, not just risk share

**Date:** 2026-05-08
**Affects:** `web/build_dashboard_data.py`, `web/app.js`, `web/style.css`

## Problem

The drivers panel ("What's pushing this prediction") currently shows each top driver as `arrow + name + bar + ±X.X pp`. The bar's length encodes the SHAP-derived percentage-point contribution to risk. A reader sees "Population +4.2 pp" and has to know that this means "this tract has *low* population, which raises risk." The state of the underlying metric is hidden behind the contribution.

## Goal

For every driver row (in both county mode and tract mode), expose:

1. The tract/county's **raw value** for that driver.
2. **Where that value sits in the distribution** of the same feature across all tracts/counties (a percentile, with a small bell-curve sparkline).
3. The **risk relationship** (kept): the existing pp number, now formatted as `+4.2%`.
4. **Color/arrow semantics that read as "this place is better/worse than median for this driver"** — consistent across features regardless of whether higher or lower drives risk.

The percentile baseline matches the active scope: within-state when a state is focused, national otherwise.

## Architecture

Three new data files, two new JS helpers, one expanded row renderer. No new top-level JS state shapes — mirrors the existing `STATE.countyStats` / `STATE.shap` pattern.

### Data flow

```
panel parquet ──┐
                ├─► build_dashboard_data.py ──► feature_distributions.json
shap_top.json ──┘                          ──► tract_features.json.gz
                                           ──► county_features.json.gz
                                                       │
                                                       ▼
                                                  app.js (fetchOptional)
                                                       │
                                                       ▼
                                                  drawshap row renderer
```

## Builder additions (`web/build_dashboard_data.py`)

Added near the existing `feature_stats.json` block (~line 954).

### 1. Driver universe

Union of every feature appearing in any tract's top-8 SHAP list across all four `(model, horizon)` combinations. Read from `data/shap_top.json.gz`. Expected size: ~30–40 features. This keeps the per-tract features file compact (we don't need to ship every column from the panel).

### 2. `data/feature_distributions.json`

```jsonc
{
  "population": {
    "is_categorical": false,
    "national": [v01, v02, ..., v99],    // 99 quantile cutpoints (p1..p99)
    "by_state": {
      "AL": [v01, ..., v99],
      "AK": [v01, ..., v99],
      ...
    }
  },
  "ssbci_active": {
    "is_categorical": true,
    "categories": [{"value": 0, "share": 0.42}, {"value": 1, "share": 0.58}],
    "by_state": { "AL": [...], ... }     // shares per state
  }
}
```

Direction (`lower_is_worse` / `higher_is_worse` / `neutral`) is **not** auto-computed. It lives as an explicit hand-curated map in `app.js` (constant `FEATURE_DIRECTION`). This avoids accidentally coloring sensitive features (race composition, etc.) and makes the convention auditable in source.

### Direction enumeration (in `app.js`)

Default for any feature not listed: `lower_is_worse`.

**`higher_is_worse`** (above-median → red, below-median → green):

- All HHI / concentration: `cra_county_amount_hhi`, `cra_county_count_hhi`, `lender_hhi_tract_resid`, `fdic_deposit_hhi`, `fdic_deposit_hhi_chg1yr`, `fdic_deposit_hhi_chg3yr`
- Top-lender shares: `top1_lender_share_tract_resid`, `top3_lender_share_tract_resid`, `pct_loans_from_top4_banks_resid`, `cra_county_top_lender_share_count`, `cra_county_top_lender_share_amount`, `fdic_top_bank_share`, `fdic_top_bank_share_chg1yr`, `fdic_top_bank_share_chg3yr`
- Distance / access penalties: `distance_to_nearest_bank_branch`, `nearest_mdi_branch_miles`, `branch_closures_3y_within_10mi`
- Distress measures: `unemployment_rate`, `pct_vacant`, `pct_poverty`, `is_persistent_poverty`, `denial_rate`, `n_denied`, `n_withdrawn`
- Rurality: `ruca_code` (USDA 1-urban → 10-rural; this model penalises rural)

**`neutral`** (no green/red coloring; arrow grey, pp keeps its sign color):

- Racial / ethnic composition: `pct_minority`, `pct_black`, `pct_hispanic`, `n_black`, `n_hispanic`, `n_asian`, `n_white`, `n_other_race`. *Coloring these green/red would imply a value judgement on demographic composition.*
- `mean_loan_amount` — direction is context-dependent in this model (small loans can read either way).

**`lower_is_worse`** (default — below-median → red, above-median → green): everything else, including `population`, `housing_units`, `median_hh_income`, `pct_bachelor_plus`, `n_originated`, `n_applications`, `n_purchased`, `n_distinct_lenders`, `branches_within_5mi`, `mdi_branches_within_10mi`, `mdi_branches_within_25mi`, `microloan_intermediary_within_25mi`, `mdi_active_in_county`, `ssbci_active`, `ssbci_program_count`, `approval_rate`, `pct_loans_from_credit_unions_resid`, `pct_loans_from_community_banks_resid`, `sum_loan_amount`, `pct_loans_under_100k_resid`, `pct_loans_under_250k_resid`.
- `is_categorical`: True for binary flags (`ssbci_active`, `mdi_branches_within_*`) and ordinal codes (`ruca_code`). Detection: ≤ 12 distinct values *and* integer-valued.
- `national`: array of 99 floats (p1..p99). 99 chosen over a coarser grid so the JS percentile lookup has resolution ±1pp.
- `by_state`: same shape, per state. Skipped if a state has < 25 tracts with non-null values for the feature.

### 3. `data/tract_features.json.gz`

```jsonc
{
  "01001020100": { "population": 3210, "median_hh_income": 54300, ... },
  ...
}
```

- Most-recent-year snapshot (matches the snapshot the dashboard already shows).
- Driver-universe features only.
- Round numerics to 4 sig figs to keep file size down (gzipped target: < 5 MB).

### 4. `data/county_features.json.gz`

Population-weighted aggregation of tract values per county, mirroring how `county_drivers_payload` already aggregates. Same schema as the tract file.

## JS additions (`web/app.js`)

### Loaders

In the existing init block (~line 714) add three `fetchOptional` calls in parallel with the others:

```js
fetchOptional("data/feature_distributions.json"),
fetchOptional("data/tract_features.json.gz"),       // gzip handled by browser
fetchOptional("data/county_features.json.gz"),
```

Stash on `STATE.featureDistributions`, `STATE.tractFeatures`, `STATE.countyFeatures`. All three optional — the renderer falls back to today's behavior if any are null.

### Helpers

```js
function lookupRawValue(feat, geoid, isCounty) { ... }
function featurePercentile(feat, rawValue, scope) {
  // scope: state abbr or null. Binary search into the 99-value array;
  // returns 0..100 (linear interp between cutpoints).
  // For categorical features, returns the cumulative share at/below this bucket.
}
function formatRawValue(feat, value) {
  // Per-feature formatter. Currency, percent, integer, RUCA label, etc.
  // Falls back to value.toLocaleString() if no specific formatter registered.
}
function colorClassForRow(feat, percentile) {
  // Returns 'pos' (green), 'neg' (red), or 'neu' (grey).
  // Looks up FEATURE_DIRECTION[feat]; defaults to 'lower_is_worse'.
  //   lower_is_worse + p < 50 → neg; lower_is_worse + p > 50 → pos
  //   higher_is_worse + p > 50 → neg; higher_is_worse + p < 50 → pos
  //   neutral → neu (grey arrow); pp keeps its sign-based color separately
}
```

`colorClassForRow` replaces the current `isPos = pp >= 0` logic. Color now tracks "better/worse than median for this driver" instead of pp sign.

### Row renderer (~line 2533)

Replace the current row HTML:

```html
<span class="drawshap__nm">
  <span class="drawshap__arrow {pos|neg|neu}">{▲|▼|·}</span>
  {pretty}
</span>
<span class="drawshap__val">{formatted raw value}</span>
<span class="drawshap__bell">
  <svg ...><!-- normal-curve silhouette + marker dot at percentile --></svg>
</span>
<span class="drawshap__pct">{38th[ in AL]}</span>
<span class="drawshap__v {pos|neg|neu}">{+4.2%}</span>
```

- Arrow: ▲ if percentile > 50, ▼ if < 50, · if exactly 50.
- All color-class slots driven by `colorClassForRow(direction, percentile)`.
- pp text: `+4.2 pp` → `+4.2%` (`fmtPp` updated or replaced with `fmtPct`).
- "in AL" suffix only when `STATE.focusedState` is set.
- Bell SVG: ~80px × 22px, faint normal-curve background path, single 4px-radius dot at `(percentile/100) * width`, dot color matches row color class.
- Categorical features: bell SVG replaced by a simple two- or three-segment indicator showing which bucket the tract sits in. Same width slot, no layout shift.

### Re-render on scope change

`STATE.focusedState` already triggers UI updates via the existing focus-state handlers (~line 1804). Add a call to refresh the open drawer there so percentiles re-rank when the user focuses or un-focuses a state.

### Tooltip

Replace the current feature-description tooltip body with:

> **Population: 3,210**
> 38th percentile in Alabama. Lower-than-average population raises the 2027 forecast by **+4.2%**.
>
> *(existing feature description text appended below)*

The "raises/lowers" verb tracks pp sign; the "lower/higher than average" tracks percentile vs 50.

## Styling (`web/style.css`)

- Grid template for `.drawshap` updated to `name | val | bell | pct | pp` (5 columns, was 3).
- Add `.drawshap__val` (right-aligned, monospace numerics, ~70px), `.drawshap__bell` (~80px), `.drawshap__pct` (~50px).
- Add `.neu` color class (grey, midway between `.pos` green and `.neg` red) for percentile-50 rows.
- All five color classes sourced from CSS custom properties so theme switches keep working.

## Empty/missing-data behavior

- If `feature_distributions.json` failed to load: drop the val/bell/pct cells via a `body[data-no-distributions]` attribute selector. Layout collapses cleanly back to today's three-column grid. No console errors.
- If a specific feature isn't in the distribution file (legacy SHAP cache references a feature dropped from the panel): render val + "—" for percentile, no bell.
- If a tract isn't in `tract_features.json.gz` (e.g., AK tract added after the build): same fallback.

## Out of scope

- Recomputing SHAP. The pp values continue to come from the existing cache.
- Re-ranking the top-5 by anything other than `|pp|`. (Could later sort by "distance from median" but that's a separate UX call.)
- Time-series view of the driver. Today's snapshot only.

## Acceptance criteria

1. Open any tract drawer → top-5 drivers each show name, raw value, bell-curve marker, percentile label, and `±X.X%`.
2. Color of arrow + pp number reads consistently as "this place is better (green) or worse (red) than the median tract for this driver."
3. Toggle a state focus → percentiles update to within-state ranking; "in AL" suffix appears.
4. Toggle from tract to county mode → driver rows show population-weighted county values with percentile relative to all counties.
5. Hover row → tooltip shows raw value, percentile, scope, and risk verb in plain English.
6. With `feature_distributions.json` deleted, drawer renders today's exact layout.
