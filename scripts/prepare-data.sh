#!/usr/bin/env bash
# Decompress checked-in data files. Run this once after cloning.
#
# We compress shap_top.json (~101 MB raw, ~19 MB gzipped) because GitHub's
# hard limit is 100 MB per file. The dashboard expects the uncompressed
# JSON at runtime.

set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f web/data/shap_top.json ]; then
  echo "shap_top.json already present; skipping decompression."
else
  if [ -f web/data/shap_top.json.gz ]; then
    echo "Decompressing web/data/shap_top.json.gz ..."
    gunzip -k web/data/shap_top.json.gz
    echo "Done. shap_top.json: $(du -h web/data/shap_top.json | cut -f1)"
  else
    echo "ERROR: neither web/data/shap_top.json nor shap_top.json.gz exists."
    echo "Re-clone the repo or run train/compute_shap.py to regenerate."
    exit 1
  fi
fi

echo
echo "Dashboard data is ready. Serve with:"
echo "    cd web && python3 -m http.server 8009"
echo "Then open http://localhost:8009"
