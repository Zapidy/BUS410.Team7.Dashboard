# Round 5 — ETL Log & Manual Download Instructions

This document tracks what was pulled automatically, what failed, and what needs to be downloaded manually because the source either requires an account, blocks programmatic access, or only exposes data through a JS-driven web app that doesn't have a stable CSV URL.

Status as of 2026-04-28.

---

## Auto-pulled successfully ✅

Run `etl/download_all.sh` then the per-source Python pullers (`etl/fdic/pull_sod.py`, `etl/acs/pull_acs.py`) to (re)pull these. All idempotent.

| Source | Files | Records | Size | Path |
|---|---|---|---|---|
| **SBA 7(a) loans 1991–present** | 4 CSVs | ~5M loans | 770 MB | `data/raw/sba/foia-7a-*.csv` |
| **SBA 504 loans 1991–present** | 2 CSVs | ~140k loans | 100 MB | `data/raw/sba/foia-504-*.csv` |
| **FDIC failed bank list** | 1 CSV | ~570 events | 48 KB | `data/raw/fdic/failed_banks.csv` |
| **FDIC Summary of Deposits 2009–2024** | 16 yearly CSVs | **1.43M branch-years** | 122 MB | `data/raw/fdic/sod/sod_{year}.csv` |
| **USDA RUCA tract codes (2010 + 2020)** | 2 XLSX | 73k + 84k tracts | 17 MB | `data/raw/usda/ruca_*_tracts.xlsx` |
| **USDA County Typology (2015 + 2025 ed.)** | 2 files | ~3k counties | 440 KB | `data/raw/usda/county_typology_*` |
| **Census tract crosswalk 2010 ↔ 2020** | 1 TXT | 84k pairings | 18 MB | `data/raw/census-geo/tract_xwalk_2010_2020.txt` |
| **Opportunity Zones (HUD + CDFI 2018)** | 2 files | ~8.7k tracts | 430 KB | `data/raw/oz/` |
| **Census ACS 5-year (2010, 2015, 2020, 2022 vintages)** | 158 JSON | **245k tract-vintages** | 42 MB | `data/raw/acs/acs5_{year}/state_{ss}.json` |

**Total Round-5 raw data so far: 1.0 GB.** Round 5 has its own self-contained SoD pull spanning **2009–2024** in 16 per-year CSVs — no dependency on the round-4 cache.

### Branch-decline signal already visible

The SoD pull captured a clear secular trend that matters for the model:

| Year | Branches |
|---|---|
| 2009 | 99,530 |
| 2014 | 94,706 |
| 2019 | 86,374 |
| 2024 | 76,711 |

That's a **23% decline in physical bank branches over 15 years**. This trend alone is a strong supply-side signal Round 4 only partially captured (because its SoD coverage stopped at 2019).

---

## Need manual download ⚠️

These either require an account (NHGIS), are blocked by a Cloudflare-style WAF (FFIEC), or are only served through a React SPA with no stable bulk-download URL (HMDA snapshot).

### 1. FFIEC CRA disclosure flat files — **DONE ✓**

User browser-downloaded the missing years 2026-04-28. All zips moved into [data/raw/cra/](data/raw/cra/) and unpacked into per-year `{discl,aggr,trans}/` subfolders. Round-4 D22 zips were also unpacked into the same structure to fill 2014–2023 disclosure.

Final coverage:

| Year | Disclosure | Aggregate | Transmittal |
|------|:----------:|:---------:|:-----------:|
| 2009 | ✓ 215 MB | ✓ | ✓ |
| 2010 | ✓ 204 MB | ✓ | ✓ |
| 2011 | ✓ 218 MB | ✓ | ✓ |
| 2012 | ✓ 240 MB | ✓ | ✓ |
| 2013 | ✓ 233 MB | ✓ | ✓ |
| 2014 | ✓ 305 MB | ✓ | **·** |
| 2015 | ✓ 301 MB | ✓ | ✓ |
| 2016 | ✓ 370 MB | ✓ | ✓ |
| 2017 | ✓ 367 MB | ✓ | ✓ |
| 2018 | ✓ 309 MB | ✓ | ✓ |
| 2019 | ✓ 323 MB | ✓ | ✓ |
| 2020 | ✓ 372 MB | ✓ | ✓ |
| 2021 | ✓ 376 MB | ✓ | ✓ |
| 2022 | ✓ 361 MB | ✓ | ✓ |
| 2023 | ✓ 344 MB | ✓ | ✓ |
| 2024 | ✓ 349 MB | ✓ | ✓ |

**Total CRA: 5.5 GB across 48 datasets. Zero remaining gaps — all 16 years × 3 file types (discl + aggr + trans) present.**

Note: the round-4 zips named `cra{YYYY}_Discl_D22.zip` actually contain the **full disclosure series** (D11/D12/D21/D22/D3/D4/D5/D6, 8 files) — the name is misleading.

---

### 2. FFIEC HMDA — **API pull running for 2018–2024**

Implemented in [etl/hmda/pull_hmda.py](../etl/hmda/pull_hmda.py) using the CFPB Data Browser API (year coverage confirmed 2018–2024 by direct probe; 2017 returns 400, 2025 returns 400):

- **Endpoint:** `GET https://ffiec.cfpb.gov/v2/data-browser-api/view/csv?years={YEAR}&states={SS}&actions_taken=1,2,3,4,5,6,7,8`
- **Strategy:** stream LAR per state-year, aggregate to tract-level on the fly. Never store full LAR (would be 30–60 GB total). Output: ~50 KB CSV per state-year.
- **Output schema:** one row per `(year, state, tract_fips)` with `n_applications`, `n_originated`, `n_denied`, `n_withdrawn`, `n_purchased`, `approval_rate`, `denial_rate`, `sum_loan_amount`, `mean_loan_amount`, `n_distinct_lenders`, `n_white`, `n_black`, `n_asian`, `n_hispanic`, `n_other_race`.
- **Output path:** `data/raw/hmda/tract_aggregates_{year}/{ST}.csv`
- **Smoke test:** DC + DE 2023 returned 60,877 LAR rows → 457 tract aggregates in 3 seconds.
- **Full pull:** running in background as of 2026-04-28 12:59. 7 years × 51 states + PR ≈ ~15–25 minutes total expected. Progress in `data/raw/hmda/_pull.log`.

**Pre-2018 HMDA** is **not available** through the API. If you need 2009–2017 HMDA, manual download is required from https://www.consumerfinance.gov/data-research/hmda/historic-data/ (older site, returns 403 to curl). For Round 5 we accept that:

- 2009–2017: CRA-aware features only (HMDA not available)
- 2018–2024: CRA + HMDA features

This bifurcation is similar to Round 4's CRA bifurcation, but reversed. We'll add a `has_hmda` flag in the panel and run two model variants in walk-forward validation: a "full-panel" model that uses only CRA+FDIC+demographics, and an "HMDA-aware" model that adds HMDA features for 2018+ folds.

---

### 3. Tract vintage crosswalks — **DONE ✓**

Both transitions covered without an account:

- **2000 ↔ 2010**: `data/raw/census-geo/tract_xwalk_2000_2010.txt` (19 MB) — pulled directly from Census Bureau at https://www2.census.gov/geo/docs/maps-data/data/rel/trf_txt/us2010trf.txt
- **2010 ↔ 2020**: `data/raw/census-geo/tract_xwalk_2010_2020.txt` (18 MB) — pulled at the same time as the rest of the auto-set

**NHGIS / IPUMS account is not required.** The Census Bureau publishes the canonical relationship files in the same `rel/` directory tree. (NHGIS account approvals are paused as of 2026-04 anyway.)

The schema of the 2000→2010 file is `state, county, tract00, GEOID00, pop00, hu00, sf, area00, areawater00, state10, county10, tract10, GEOID10, pop10, hu10, sf, area10, areawater10, area_overlap, ...` — 24 columns. Use `area_overlap` and `pop_overlap` columns for population-weighted apportionment when projecting tract data forward.

---

### 4. ACS 5-year tract data — **2009–2023**

Census API at api.census.gov can pull tract-level ACS data **without** an account (rate-limited but unauthenticated). For higher rate limits and bulk requests, register a free key at https://api.census.gov/data/key_signup.html.

We can automate this once we know which ACS variables we want. Round-4 docs imply the key variables are: `pct_poverty`, `pct_minority`, `median_hh_income`, `population`, but the parquet has more (population by age, income brackets, race/ethnicity). The pull script will be in `etl/acs/` once the variable list is finalized.

For now: defer until §3 above is unblocked.

---

### 5. Persistent poverty counties (USDA)

Static list, ~3000 counties.

**Steps:**
1. Visit https://www.ers.usda.gov/data-products/county-typology-codes
2. Download **"County Typology Codes"** Excel
3. The "Persistent Poverty 2020" column is the binary flag we want
4. Drop into `round5/data/raw/usda/county_typology.xlsx`

Or via API: USDA ERS has a JSON endpoint but it's undocumented. Easier to grab the XLSX manually.

---

### 6. EIG Distressed Communities Index

EIG publishes the Distressed Communities Index at the zip-code (and recently census-tract) level, but they require an email signup to access the bulk data.

**Steps:**
1. Visit https://eig.org/distressed-communities/
2. Click "Download Data," provide email
3. Download the most recent year's Excel
4. Drop into `round5/data/raw/eig/dci.xlsx`

**Alternative:** the underlying ACS variables that drive DCI (housing vacancy, median household income, % adults without HS diploma, % unemployed, % out-of-labor-force, change in number of jobs, change in number of business establishments) can be reconstructed from ACS API directly. Skip EIG and rebuild the index in-house if you don't want to give them an email.

---

### 7. CDFI Fund awards & certifications

**Steps:**
1. Visit https://www.cdfifund.gov/awards/state-awards
2. Or directly: https://www.cdfifund.gov/sites/cdfi/files/documents/cdfi-program-awards-2009-2024.xlsx (URL pattern; verify the exact filename is current)
3. For CDFI certifications (active list): https://www.cdfifund.gov/programs-training/certification/cdfi
4. Drop into `round5/data/raw/cdfi/`

CDFI Fund's data publication is inconsistent — bulk Excel downloads are sometimes posted, sometimes only available via FOIA request. If a clean CSV/XLSX isn't there, the alternative is the IRS Form 990 data on Form 990 filers tagged as CDFIs (Treasury maintains a list).

---

### 8. CFPB Consumer Complaints (optional, fintech proxy)

1.8 GB ZIP. Includes complaints against fintechs not covered by CRA. Direct download URL works:

```
https://files.consumerfinance.gov/ccdb/complaints.csv.zip
```

Currently skipped from `download_all.sh` because of disk constraints. To pull when space allows:

```bash
curl -fL -A 'Mozilla/5.0' \
  -o data/raw/cfpb/complaints.csv.zip \
  "https://files.consumerfinance.gov/ccdb/complaints.csv.zip"
```

For a Round-5 rebuild this is **optional** — we'd use it only as a weak fintech-presence proxy per tract.

---

### 9. Macro controls — FRED API

Unemployment rate, 10-year Treasury yield, CPI, etc. are all available via FRED.

`etl/fred/pull_macro.py` exists and uses the public `fredgraph.csv` endpoint (no key required). On this machine all six series **timed out** — likely a network-egress filter or temporary FRED throttling. Two fallback paths:

**Path A — try again on a different network**
```bash
python3 etl/fred/pull_macro.py
```
If your home / coffee-shop / phone-tether network can reach `fred.stlouisfed.org`, this just works.

**Path B — official FRED API with a free key**
1. Sign up at https://fred.stlouisfed.org/docs/api/api_key.html (instant)
2. Add the key to `~/.fredrc` or pass via `--api-key` (we'll plumb this in)
3. Use the `https://api.stlouisfed.org/fred/series/observations` endpoint instead of fredgraph

These are small files (~kB each). Don't block Phase 1 on them — pull when you have a working network or key.

---

## Failures from `download_all.sh` — diagnosed ❌

| Source | Why it failed | Fix |
|---|---|---|
| HMDA snapshot endpoint `ffiec.cfpb.gov/v2/data-publication/snapshot-data/{year}/lar` | Returns the React app's HTML shell, not the data file | Manual download per §2 above |
| HMDA Data Browser CSV `ffiec.cfpb.gov/v2/data-browser-api/view/csv` | API is GET-only; works with proper params + a real query, but is rate-limited and returns LAR-level rows. Use aggregate reports instead | Strategy A in §2 |
| FDIC SoD bulk `www7.fdic.gov/sod/download/ALL_{year}.zip` | URL pattern doesn't exist on www7 | Use the API (`api.fdic.gov/banks/sod`) — round5/etl pulls 2020–2024 incrementally |
| FFIEC CRA flat files | Akamai bot-mitigation returns 403 to all curl/wget requests | Manual browser download per §1 above |

---

## Storage footprint after Phase 1 (estimated)

| Bucket | Size |
|---|---|
| SBA | 870 MB |
| HMDA aggregate (Strategy A) | 300 MB |
| CRA (full backfill, 2009–2024) | 250 MB |
| FDIC SoD (full panel, 2009–2024) | 200 MB |
| ACS API pulls | 50 MB |
| Census-geo crosswalks | 40 MB |
| USDA + OZ + CDFI + EIG + macro | 30 MB |
| Misc | 50 MB |
| **Total raw** | **~1.8 GB** |

If we add full HMDA LAR (Strategy B), add 30–60 GB. Don't do this on the current 17 GB free disk.

---

## Order of operations

1. **Now:** Manually download the 6 missing CRA years (§1) — quickest unblock
2. **Today:** Run `etl/download_all.sh` to confirm the auto-pulls succeeded
3. **This week:** Manually pull HMDA aggregate reports 2009–2024 (§2 Strategy A)
4. **This week:** NHGIS account + 2000↔2010 crosswalk (§3)
5. **Once §1–4 are done:** start writing per-source ETL scripts in `etl/{cra,hmda,sba,fdic,acs}/`
