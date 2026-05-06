#!/usr/bin/env bash
# Round 5 — Master download orchestrator
# Pulls everything publicly accessible without an account into data/raw/.
# Logs successes / failures to data/raw/_download.log.
# Re-run safely: every step uses curl -fL with output paths, and skips files
# that already exist at >0 bytes.

set -uo pipefail
UA='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15'

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAW="$ROOT/data/raw"
LOG="$RAW/_download.log"

mkdir -p "$RAW/sba" "$RAW/hmda" "$RAW/cra" "$RAW/fdic" "$RAW/acs" \
         "$RAW/usda" "$RAW/oz" "$RAW/cdfi" "$RAW/census-geo" \
         "$RAW/cfpb" "$RAW/eig" "$RAW/macro"

: > "$LOG"
log() { printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*" | tee -a "$LOG"; }
get() {
  local url="$1" out="$2" referer="${3:-}"
  if [[ -s "$out" ]]; then log "SKIP  (already present) $out"; return 0; fi
  log "GET   $url"
  if [[ -n "$referer" ]]; then
    curl -fL -A "$UA" -e "$referer" --retry 2 --max-time 600 -o "$out" "$url" 2>>"$LOG" \
      && log "OK    $(du -h "$out" | cut -f1)  $out" \
      || { log "FAIL  $url"; rm -f "$out"; return 1; }
  else
    curl -fL -A "$UA" --retry 2 --max-time 600 -o "$out" "$url" 2>>"$LOG" \
      && log "OK    $(du -h "$out" | cut -f1)  $out" \
      || { log "FAIL  $url"; rm -f "$out"; return 1; }
  fi
}

# ============================================================================
log "=== SBA loan-level (7(a) + 504, 1991–present, ~900 MB total) ==="
# Found via https://data.sba.gov/dataset/7-a-504-foia
SBA_BASE="https://data.sba.gov/en/dataset/0ff8e8e9-b967-4f4e-987c-6ac78c575087/resource"
get "$SBA_BASE/182e9421-ccee-4562-acb3-93b34fb695f2/download/foia-7a-fy1991-fy1999-asof-260331.csv" \
    "$RAW/sba/foia-7a-1991-1999.csv"
get "$SBA_BASE/186eb176-b53e-4cbe-ab93-e5c4fb50197d/download/foia-7a-fy2000-fy2009-asof-260331.csv" \
    "$RAW/sba/foia-7a-2000-2009.csv"
get "$SBA_BASE/3f838176-6060-44db-9c91-b4acafbcb28c/download/foia-7a-fy2010-fy2019-asof-260331.csv" \
    "$RAW/sba/foia-7a-2010-2019.csv"
get "$SBA_BASE/d67d3ccb-2002-4134-a288-481b51cd3479/download/foia-7a-fy2020-present-asof-260331.csv" \
    "$RAW/sba/foia-7a-2020-present.csv"
get "$SBA_BASE/8854d636-599d-463f-a961-7dbdb3bab152/download/foia-504-fy1991-fy2009-asof-260331.csv" \
    "$RAW/sba/foia-504-1991-2009.csv"
get "$SBA_BASE/4ad7f0f1-9da6-4d90-8bdb-89a6f821a1a9/download/foia-504-fy2010-present-asof-260331.csv" \
    "$RAW/sba/foia-504-2010-present.csv"

# ============================================================================
log "=== FDIC failed-bank list ==="
get "https://www.fdic.gov/resources/resolutions/bank-failures/failed-bank-list/banklist.csv" \
    "$RAW/fdic/failed_banks.csv"

# ============================================================================
log "=== USDA Rural-Urban Commuting Area (RUCA) codes ==="
get "https://www.ers.usda.gov/media/5441/2020-rural-urban-commuting-area-codes-census-tracts.xlsx" \
    "$RAW/usda/ruca_2020_tracts.xlsx"
get "https://www.ers.usda.gov/media/5438/2010-rural-urban-commuting-area-codes-revised-732019.xlsx" \
    "$RAW/usda/ruca_2010_tracts.xlsx"

# ============================================================================
log "=== Census tract vintage crosswalk (2010 ↔ 2020) ==="
get "https://www2.census.gov/geo/docs/maps-data/data/rel2020/tract/tab20_tract20_tract10_natl.txt" \
    "$RAW/census-geo/tract_xwalk_2010_2020.txt"

# ============================================================================
log "=== Opportunity Zones designation ==="
get "https://opportunityzones.hud.gov/sites/opportunityzones.hud.gov/files/documents/Opportunity_Zones.csv" \
    "$RAW/oz/opportunity_zones.csv"
get "https://www.cdfifund.gov/sites/cdfi/files/documents/designated-qozs.12.14.18.xlsx" \
    "$RAW/oz/designated_qozs.xlsx"

# ============================================================================
log "=== HMDA snapshot LAR (try direct CFPB endpoint, 1 year at a time) ==="
# These are large (≈4–8 GB per year unzipped). Pulling 2018 + 2023 only as a
# Phase-1 sample. Add more years once disk space is confirmed.
for yr in 2018 2023; do
  url="https://ffiec.cfpb.gov/v2/data-publication/snapshot-data/${yr}/lar"
  get "$url" "$RAW/hmda/hmda_lar_${yr}.zip" "https://ffiec.cfpb.gov/data-publication/snapshot-national-loan-level-dataset"
done

# ============================================================================
log "=== HMDA Aggregate / Disclosure tract-level reports (FAR smaller, ~tract-year aggregates) ==="
# Per-MSA aggregate CSV downloads. The endpoint streams a CSV when given the
# right query params. Sample first; expand once confirmed.
for yr in 2018 2020 2023; do
  url="https://ffiec.cfpb.gov/v2/data-browser-api/view/csv?years=${yr}&actions_taken=1,2,3,4,5,6,7,8"
  get "$url" "$RAW/hmda/hmda_browser_${yr}.csv" "https://ffiec.cfpb.gov/data-browser/"
done

# ============================================================================
log "=== FDIC Summary of Deposits (extend Round-4 cache to 2009-2024) ==="
# The Round-4 fetch script is API-based and idempotent; reusing it.
if [[ -f "$ROOT/../round4/fetch_fdic_sod_cache.sh" ]]; then
  log "Re-using round4/fetch_fdic_sod_cache.sh (note: edit YEARS env to 2009..2024 if needed)"
fi
# Direct FDIC SoD bulk download (per-year zips):
for yr in 2009 2010 2011 2012 2013 2014 2015 2016 2017 2018 2019 2020 2021 2022 2023 2024; do
  url="https://www7.fdic.gov/sod/download/ALL_${yr}.zip"
  get "$url" "$RAW/fdic/sod_${yr}.zip"
done

# ============================================================================
log "=== Done. Summary: ==="
du -sh "$RAW"/*/ 2>/dev/null | tee -a "$LOG"
echo ""
log "See $LOG for full per-file results."
log "For sources that need an account or returned FAIL above, see notes/02_etl_log.md"
