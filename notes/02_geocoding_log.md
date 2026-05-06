# Geocoding Log — CDFI / MDI / Microlender Lists

## Sources

| List | Approx size | Has lat/lng natively? | Source |
|---|---|---|---|
| CDFI Fund certified institutions | ~1,400 | No (address only) | [CDFI Fund](https://www.cdfifund.gov/programs-training/certification/cdfi) |
| FDIC MDI list | ~150 | No directly, but RSSD lets us join SoD | [FDIC MDI Program](https://www.fdic.gov/minority-depository-institutions-program/minority-depository-institutions-list) |
| SBA microlender intermediaries | ~140 | No (address only) | [SBA microlender list](https://www.sba.gov/funding-programs/loans/microloans/list-microlenders) |

**MDI shortcut**: MDI list is keyed on FDIC RSSD/CERT. Since SoD (already in `round5/data/raw/fdic/sod/`) has lat/lng for every branch, we get MDI branch coordinates for free by inner-joining the MDI list to SoD on RSSDID. No geocoding needed for MDIs.

So the geocoding budget is ~1,540 unique entity addresses (CDFI + microlender), with annual-snapshot churn pushing total unique entity-addresses to ~3,500 across 2009–2024.

## Geocoder Choice

**Primary: Census Geocoder** ([benchmarks](https://geocoding.geo.census.gov/geocoder/)).
- Free, no API key, batch endpoint accepts up to 10K addresses per request.
- Optimized for US addresses; ~85% hit rate on commercial addresses.
- Returns lat/lng + matched census tract — we can use the matched tract directly without our own spatial join in some cases.

**Fallback: Nominatim (OpenStreetMap)**.
- Free, no key, 1 req/sec rate limit (fine for residual ~200 addresses).
- Better at mixed-quality addresses, PO boxes flagged but partial coords sometimes.

**Skipped: Google / Mapbox.** Cost > $0; unnecessary at this scale.

## Caching

`data/raw/geocode_cache/{address_hash}.json` — keyed by SHA1 of normalized address string. Re-run is idempotent. Caches survive across the three pulls.

## Quality Bar

- **CDFI**: ≥ 85% hit rate. Failures get logged with reason; manual cleanup if list shrinks below 1,200.
- **MDI**: 100% (via SoD join — no geocoding involved).
- **Microlender**: ≥ 90% hit rate. Small list, manually verify failures.

## Annual Churn Handling

CDFI Fund publishes a quarterly certified list. Microlender list updates quarterly. For each year of the panel (2009–2024):

1. Find the snapshot closest to mid-year (June 30).
2. If a historical snapshot is unavailable for early years, use the earliest available + a presence-back-extension flag (annotate which years are extrapolated).
3. Document the snapshot date in `cdfi_snapshots.csv` and `microlender_snapshots.csv`.

**Realistic constraint**: CDFI Fund's earliest publicly archived list may only go back to ~2012. For 2009–2011, we likely have to back-extend the 2012 list with the assumption that established CDFIs don't suddenly de-certify. Document this caveat in the final write-up.

## Status

- [ ] CDFI list pulled
- [ ] MDI list pulled
- [ ] Microlender list pulled
- [ ] Census Geocoder run + cache populated
- [ ] Nominatim fallback run
- [ ] Hit rates reported per source
- [ ] Annual snapshot dates documented

To be filled in as work progresses.
