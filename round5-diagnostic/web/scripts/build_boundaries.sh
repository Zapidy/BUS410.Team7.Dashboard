#!/usr/bin/env bash
# Fetch + simplify TIGER 2024 county and place boundaries.
#
#   counties → web/data/counties.geojson    (single national file, ~3.2k features)
#   places   → web/data/places.geojson      (all states, incorporated only, ~19k features)
#
# Requires: curl, unzip, npx (mapshaper). Re-runs are idempotent.
set -euo pipefail

WEB="$(cd "$(dirname "$0")/.." && pwd)"
DATA="$WEB/data"
TMP="$DATA/_tmp/tiger"
mkdir -p "$TMP"
cd "$TMP"

VINTAGE="${TIGER_VINTAGE:-2024}"
BASE="https://www2.census.gov/geo/tiger/TIGER${VINTAGE}"

echo "==> Counties (national)"
if [[ ! -f "tl_${VINTAGE}_us_county.shp" ]]; then
  curl -sSL -o "tl_${VINTAGE}_us_county.zip" "$BASE/COUNTY/tl_${VINTAGE}_us_county.zip"
  unzip -oq "tl_${VINTAGE}_us_county.zip"
fi

echo "==> Counties → simplified GeoJSON"
npx -y mapshaper@latest "tl_${VINTAGE}_us_county.shp" \
  -simplify dp 4% keep-shapes \
  -each 'this.properties = {f: GEOID, n: NAME, st: STATEFP}' \
  -o "$DATA/counties.geojson" precision=0.0001 format=geojson

# State FIPS for the 50 states + DC + PR (places only published per state)
STATES=(01 02 04 05 06 08 09 10 11 12 13 15 16 17 18 19 20 21 22 23 24 25 \
        26 27 28 29 30 31 32 33 34 35 36 37 38 39 40 41 42 44 45 46 47 48 \
        49 50 51 53 54 55 56 72)

echo "==> Places (incorporated, per state)"
for fp in "${STATES[@]}"; do
  if [[ ! -f "tl_${VINTAGE}_${fp}_place.shp" ]]; then
    echo "    fetch $fp"
    if curl -sSLf -o "tl_${VINTAGE}_${fp}_place.zip" "$BASE/PLACE/tl_${VINTAGE}_${fp}_place.zip"; then
      unzip -oq "tl_${VINTAGE}_${fp}_place.zip" || true
    else
      echo "    (skipped $fp — not published)"
    fi
  fi
done

echo "==> Places → simplified GeoJSON (incorporated only)"
# CLASSFP C1/C2/C5/C6/C7 = active incorporated places.
# Drop CDPs (U1/U2) — they are not legal entities and balloon the file.
npx -y mapshaper@latest tl_${VINTAGE}_*_place.shp combine-files \
  -merge-layers \
  -filter '["C1","C2","C5","C6","C7"].indexOf(CLASSFP) > -1' \
  -simplify dp 6% keep-shapes \
  -each 'this.properties = {f: GEOID, n: NAME, st: STATEFP}' \
  -o "$DATA/places.geojson" precision=0.0001 format=geojson

echo
echo "Done."
ls -lh "$DATA/counties.geojson" "$DATA/places.geojson"
