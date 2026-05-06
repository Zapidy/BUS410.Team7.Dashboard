#!/usr/bin/env bash
# Download and extract the bundled data archives from the GitHub Release.
# Use this to populate the gitignored data/processed/, data/raw/, and round 5
# data/processed/ directories without re-running the federal-data ETL pipeline.
#
# Total download: ~780 MB compressed, ~3 GB unpacked.
# Skip this if you only need to run the dashboard (web/data/ is checked in).

set -euo pipefail

REPO="Zapidy/BUS410.Team7.Dashboard"
TAG="data-v1"

cd "$(dirname "$0")/.."

# Make sure gh is installed and authenticated
if ! command -v gh >/dev/null 2>&1; then
  echo "ERROR: gh CLI not installed. Install with 'brew install gh' and run 'gh auth login'."
  echo
  echo "Alternative: download manually from"
  echo "    https://github.com/${REPO}/releases/tag/${TAG}"
  echo "and extract into the repo root (overlaying the existing tree)."
  exit 1
fi

mkdir -p .release-cache

asset_seq=(
  "r5-data-processed.tar.gz"
  "r7-data-processed.tar.gz"
  "r7-data-raw.tar.gz"
)

for asset in "${asset_seq[@]}"; do
  if [ -f ".release-cache/$asset" ]; then
    echo "$asset already cached; skipping download."
  else
    echo "Downloading $asset from release $TAG..."
    gh release download "$TAG" --repo "$REPO" --pattern "$asset" --dir .release-cache
  fi
done

echo
echo "Extracting archives..."

# Round 5 processed data lands inside round5-diagnostic/data/processed/ (the
# tarball was made from round5/, so the top-level path is data/processed/;
# we extract into round5-diagnostic/).
mkdir -p round5-diagnostic
tar -xzf .release-cache/r5-data-processed.tar.gz -C round5-diagnostic
echo "  ✓ round5-diagnostic/data/processed/"

# Round 7 processed and raw extract into the round 7 root.
tar -xzf .release-cache/r7-data-processed.tar.gz
echo "  ✓ data/processed/"
tar -xzf .release-cache/r7-data-raw.tar.gz
echo "  ✓ data/raw/"

echo
echo "Done. You can now re-run any of the ETL/feature/training scripts."
echo
echo "Note: the largest federal sources (Round 5 raw CRA, ACS, HMDA, FDIC,"
echo "etc., ~6.6 GB) are NOT included; re-download from federal sources via"
echo "the URLs documented in round5-diagnostic/notes/ and round7/etl/."
