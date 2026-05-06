# RSSD ↔ CRA respondent_id Crosswalk

## Problem

CRA disclosure files key on `(agency_code, respondent_id)`:
- `agency_code = 1` (OCC), `2` (FRB), `3` (FDIC), `4` (NCUA)
- `respondent_id` is a 10-digit regulator-assigned ID, **not** the FDIC RSSD or CERT.

FDIC Summary of Deposits (SoD) and Call Reports key on `RSSDID` and `CERT`. There is **no public, official crosswalk** from CRA `(agency_code, respondent_id)` to FDIC RSSD.

Without this crosswalk, we cannot:
- Classify CRA reporters as community banks (needs FDIC Call Report `total_assets`).
- Identify the top-4 banks by year (need consistent IDs across data sources).
- Identify CRA reporters that are MDIs (needs MDI list keyed on RSSD).

Credit unions (`agency_code = 4`) are out of scope for FDIC and route through NCUA instead.

## Approach

`etl/lender_class/build_rssd_cra_crosswalk.py` performs a 3-pass match:

### Inputs

- **CRA reporters** ([../../round5/data/processed/cra/reporters.csv](../../round5/data/processed/cra/reporters.csv)): `(respondent_id, agency_code, year, name, street, city, state, zip)`. ~12K rows union across years.
- **FDIC institutions** (pulled fresh via [pull_fdic_call.py](../../etl/lender_class/pull_fdic_call.py)): `(RSSDID, CERT, NAME, ADDRESS, CITY, STALP, ZIP, ACTIVE)`.

### Match passes

1. **Exact normalized name + state.** Strip punctuation, lowercase, strip "national association"/"n.a."/"the"/"&"/"and". Match on `(name_norm, state)`. Expected hit: ~80% by row count.
2. **Fuzzy name + state.** rapidfuzz `token_set_ratio` ≥ 90 within state. Expected lift: +10%.
3. **Name + city** for the residual. rapidfuzz `token_set_ratio` ≥ 85 + city exact. Expected lift: +5%.

Manual review queue: rapidfuzz ratio in `[75, 90)` — bank chains rebrand and merger histories make these ambiguous. Half-day budget.

### Output

`data/processed/lender_class/cra_to_rssd.csv`:
```
agency_code, respondent_id, year, RSSDID, match_method, confidence, manual_reviewed
```

`confidence` ∈ {1.0 (exact), 0.9 (fuzzy ≥ 90), 0.85 (city+name), 0.75 (manual)}.

## Success criteria

**≥ 95% match rate weighted by CRA loan dollar volume.** Match rate by row count is less important — long-tail lenders contribute little volume. Volume-weighted match rate is the right metric for downstream feature reliability.

If volume-weighted match falls below 90%, the community-bank-share and top-4-share features become unreliable. Fallback: name-based community-bank flag using CRA reporter agency code + a curated top-N list of large banks. Coarser; document the precision penalty.

## Credit unions

Bypass FDIC entirely. CRA `agency_code = 4` rows join via NCUA institution list (separate pull, ~10K credit unions). Flag `is_credit_union = 1` directly.

## Status

- [ ] FDIC institutions pull (`pull_fdic_call.py`)
- [ ] Match passes implemented
- [ ] Manual review queue resolved
- [ ] Volume-weighted match rate report
- [ ] NCUA credit-union join

To be filled in as work progresses.
