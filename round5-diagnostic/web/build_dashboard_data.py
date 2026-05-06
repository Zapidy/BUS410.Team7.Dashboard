#!/usr/bin/env python3
"""Build dashboard data files for the Round-5 quant-terminal dashboard.

Inputs:
    diagnostics/walk_forward_audit_fixed/test_predictions.parquet
    data/processed/panel/tract_year_with_target.parquet  (for demographics)
    ../round4/tract_boundaries.geojson  (for tract polygons)

Outputs (under web/data/):
    tracts_raw.geojson    Full unsimplified GeoJSON (intermediate; mapshaper will eat this)
    state_stats.json      Per-state AUC and counts for the right-rail table
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
import pandas as pd
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
WEB_DATA = WEB / "data"
WEB_DATA.mkdir(parents=True, exist_ok=True)

PREDS = ROOT / "diagnostics" / "walk_forward_audit_fixed" / "test_predictions.parquet"
H3_PREDS = ROOT / "diagnostics" / "walk_forward_h3" / "future_predictions.parquet"
PANEL = ROOT / "data" / "processed" / "panel" / "tract_year_with_target.parquet"
GEOJSON = ROOT.parent / "round4" / "tract_boundaries.geojson"

# State FIPS → 2-letter abbreviation
STATE_ABBR = {
    "01":"AL","02":"AK","04":"AZ","05":"AR","06":"CA","08":"CO","09":"CT","10":"DE",
    "11":"DC","12":"FL","13":"GA","15":"HI","16":"ID","17":"IL","18":"IN","19":"IA",
    "20":"KS","21":"KY","22":"LA","23":"ME","24":"MD","25":"MA","26":"MI","27":"MN",
    "28":"MS","29":"MO","30":"MT","31":"NE","32":"NV","33":"NH","34":"NJ","35":"NM",
    "36":"NY","37":"NC","38":"ND","39":"OH","40":"OK","41":"OR","42":"PA","44":"RI",
    "45":"SC","46":"SD","47":"TN","48":"TX","49":"UT","50":"VT","51":"VA","53":"WA",
    "54":"WV","55":"WI","56":"WY",
}

LOOKUP_DIR = WEB_DATA / "_lookup"

# ---------- Build county-name lookup ----------
print("Loading Census county-name lookup…")
county_lookup = {}  # 5-char FIPS -> "Cook County, IL"
cl_path = LOOKUP_DIR / "county_names.txt"
if cl_path.exists():
    with cl_path.open("r", encoding="utf-8", errors="replace") as f:
        next(f)  # header
        for line in f:
            parts = line.rstrip("\r\n").split("|")
            if len(parts) < 5: continue
            fips = (parts[1] + parts[2]).strip().zfill(5)
            county_lookup[fips] = f"{parts[4].strip()}, {parts[0].strip()}"
    print(f"  {len(county_lookup):,} counties")
else:
    print("  (county_names.txt not found — county names will be empty)")

# ---------- Build tract → ZIP lookup (dominant ZCTA per tract) ----------
print("Loading Census ZCTA-Tract relationship → dominant ZIP per tract…")
zip_lookup = {}  # 11-char tract FIPS -> 5-digit ZIP
best_overlap = {}  # tract -> area_part of currently-best zcta
zt_path = LOOKUP_DIR / "zcta_tract.txt"
if zt_path.exists():
    with zt_path.open("r", encoding="utf-8-sig", errors="replace") as f:
        next(f)  # header
        for line in f:
            parts = line.rstrip("\r\n").split("|")
            if len(parts) < 16: continue
            zcta = parts[1].strip()
            tract = parts[9].strip().zfill(11)
            try:
                area_part = int(parts[15] or 0)
            except (ValueError, IndexError):
                continue
            if not zcta or not tract.isdigit() or len(tract) != 11:
                continue
            # Keep the ZCTA with the largest area_part overlap for this tract
            if area_part > best_overlap.get(tract, -1):
                best_overlap[tract] = area_part
                zip_lookup[tract] = zcta
    print(f"  {len(zip_lookup):,} tracts mapped to a dominant ZCTA")

print("\nLoading predictions…")
preds = pd.read_parquet(PREDS)
print(f"  rows: {len(preds):,}, years: {sorted(preds['year'].unique())}")

# For each tract, pick the LATEST (year, fold) prediction. Prefer 2023 + F8.
preds_sorted = preds.sort_values(["year", "fold"], ascending=[False, False])
latest = preds_sorted.drop_duplicates(subset="tract_fips", keep="first").copy()
print(f"  unique tracts after dedup: {len(latest):,}")
print(f"  latest year coverage: {latest.groupby('year').size().to_dict()}")

print("\nLoading panel demographics…")
panel = pd.read_parquet(PANEL, columns=[
    "tract_fips", "year", "population", "median_hh_income",
    "pct_poverty", "pct_minority", "is_rural", "is_persistent_poverty",
])
# Take the most recent panel year per tract that has ANY demographics
panel = panel.dropna(subset=["population"], how="all").copy()
panel_sorted = panel.sort_values(["tract_fips", "year"], ascending=[True, False])
panel_latest = panel_sorted.drop_duplicates(subset="tract_fips", keep="first")
print(f"  unique tracts with demographics: {len(panel_latest):,}")

# Merge predictions + demographics
merged = latest.merge(
    panel_latest[["tract_fips", "population", "median_hh_income",
                  "pct_poverty", "pct_minority", "is_rural", "is_persistent_poverty"]],
    on="tract_fips", how="left"
)
print(f"\nMerged: {len(merged):,} tract rows with both prediction + demographics")
print(f"  with demographics: {merged['population'].notna().sum():,}")

# Build per-state stats (AUC, n_tracts, mean_risk, top_decile)
print("\nComputing per-state statistics…")
merged["state_fips"] = merged["tract_fips"].str[:2]
merged["state"] = merged["state_fips"].map(STATE_ABBR).fillna(merged["state_fips"])

# Filter territories from per-state report
state_data = merged[~merged["state_fips"].isin({"72", "78", "60", "66", "69"})].copy()

state_stats = []
for st, sub in state_data.groupby("state"):
    if len(sub) < 5 or sub["y_true"].nunique() < 2:
        continue
    state_stats.append({
        "state": st,
        "state_fips": sub["state_fips"].iloc[0],
        "n": int(len(sub)),
        "pos_rate": round(float(sub["y_true"].mean()), 4),
        "mean_risk": round(float(sub["y_prob_calibrated"].mean()), 4),
        "auc": round(float(roc_auc_score(sub["y_true"], sub["y_prob_calibrated"])), 4),
    })

state_stats.sort(key=lambda r: -r["auc"])
with (WEB_DATA / "state_stats.json").open("w") as f:
    json.dump({
        "states": state_stats,
        "national": {
            "n_tracts": int(len(merged)),
            "pos_rate": round(float(merged["y_true"].mean()), 4),
            "mean_risk": round(float(merged["y_prob_calibrated"].mean()), 4),
            "auc": round(float(roc_auc_score(merged["y_true"], merged["y_prob_calibrated"])), 4),
        }
    }, f, indent=2)
print(f"  → {WEB_DATA/'state_stats.json'}  ({len(state_stats)} states)")

# Build the GeoJSON join data — small Python dict keyed by tract_fips
print("\nLoading tract boundaries (large file, may take ~10s)…")
with GEOJSON.open() as f:
    geo = json.load(f)
print(f"  features: {len(geo['features']):,}")

# Optional: H3 forecast layer (3-year horizon, scored on 2024 features)
# Loaded BEFORE the SBA/peers section so the merge can include `yp3` per tract.
h3_lookup = {}
if H3_PREDS.exists():
    h3_df = pd.read_parquet(H3_PREDS)
    for _, r in h3_df.iterrows():
        h3_lookup[r["tract_fips"]] = round(float(r["y_prob_calibrated"]), 4)
    print(f"Loaded H3 future predictions: {len(h3_lookup):,}")
else:
    print("(H3 future_predictions.parquet not found — yp3 will be empty)")

# Pull current desert status (latest year) so the dashboard can mark tracts
# that are ALREADY a credit desert today (Diagnostic layer overlay).
print("Loading current desert status (latest year)…")
status = pd.read_parquet(PANEL, columns=["tract_fips", "year", "is_service_desert"])
status = status.dropna(subset=["is_service_desert"])
status = status.sort_values(["tract_fips", "year"], ascending=[True, False])
status_latest = status.drop_duplicates(subset="tract_fips", keep="first")
desert_now = dict(zip(status_latest["tract_fips"], status_latest["is_service_desert"].astype(int)))
print(f"  current-desert flags: {sum(desert_now.values()):,} of {len(desert_now):,}")

# Optional: SBA-per-tract score (built by scripts/build_sba_tract.py)
sba_tract = {}
sba_path = LOOKUP_DIR / "sba_tract.parquet"
if sba_path.exists():
    sdf = pd.read_parquet(sba_path)
    for _, r in sdf.iterrows():
        sba_tract[r["tract_fips"]] = (
            round(float(r["sba_loans_per_1k"]), 2),
            round(float(r["sba_score"]), 1),
        )
    print(f"Loaded SBA tract scores: {len(sba_tract):,}")
else:
    print("(sba_tract.parquet not found — SBA fields will be empty)")

# Optional: precomputed peer FIPS (built by scripts/build_peers.py)
peers_lookup = {}
peers_path = LOOKUP_DIR / "peers.json"
if peers_path.exists():
    with peers_path.open("r") as f:
        peers_lookup = json.load(f)
    print(f"Loaded peer mapping: {len(peers_lookup):,}")
else:
    print("(peers.json not found — peer field will be empty)")

# Build tract-fips → properties dict (compact key names for smaller output)
tract_props = {}
for _, r in merged.iterrows():
    fips = r["tract_fips"]
    cf5 = (r.get("county_fips") if pd.notna(r.get("county_fips")) else "") or fips[:5]
    cf5 = str(cf5).zfill(5)
    sl, ss = sba_tract.get(fips, (None, None))
    pr = peers_lookup.get(fips)
    yp1 = round(float(r["y_prob_calibrated"]), 4)
    tract_props[fips] = {
        # Layer 1 — Diagnostic 2026 (existing H1 model, near-term)
        "yp": yp1,            # back-compat alias used by hover/tooltip
        "yp1": yp1,
        # Layer 2 — Forecast 2030 (new H3 model scored on 2024 features)
        "yp3": h3_lookup.get(fips),
        # Currently-a-desert flag (binary, latest year). The model excludes
        # already-deserts from its training set so for those tracts the model
        # has no opinion; the dashboard renders them with a saturated "is
        # already a desert" color in the Diagnostic layer.
        "dn": desert_now.get(fips, 0),
        "yt": int(r["y_true"]) if pd.notna(r["y_true"]) else None,
        "fd": r["fold"],
        "yr": int(r["year"]),
        "st": r["state"],
        "cn": county_lookup.get(cf5, ""),
        "zp": zip_lookup.get(fips, ""),
        "pop": int(r["population"]) if pd.notna(r["population"]) else None,
        "inc": int(r["median_hh_income"]) if pd.notna(r["median_hh_income"]) else None,
        "pov": round(float(r["pct_poverty"]), 1) if pd.notna(r["pct_poverty"]) else None,
        "min": round(float(r["pct_minority"]), 1) if pd.notna(r["pct_minority"]) else None,
        "ru": int(r["is_rural"]) if pd.notna(r["is_rural"]) else 0,
        "pp": int(r["is_persistent_poverty"]) if pd.notna(r["is_persistent_poverty"]) else 0,
        "sl": sl,   # SBA loans per 1k residents (latest year)
        "ss": ss,   # within-state SBA percentile (0-100)
        "pr": pr,   # 3 peer tract FIPS (same state, thriving SBA, similar demographics)
    }

# Inject into the GeoJSON, drop tracts without predictions
print("Joining into GeoJSON…")
# Pre-pass: collect the set of FIPS actually being written so we can filter
# peer references down to renderable tracts (geometries the map will show).
renderable_fips = {
    (feat.get("properties", {}).get("tract_fips") or "").zfill(11)
    for feat in geo["features"]
} & set(tract_props.keys())

out_features = []
matched = 0
peers_dropped = 0
for feat in geo["features"]:
    fips = (feat.get("properties", {}).get("tract_fips") or "").zfill(11)
    if fips not in tract_props:
        continue
    p = dict(tract_props[fips])
    if p.get("pr"):
        kept = [q for q in p["pr"] if q in renderable_fips]
        if len(kept) != len(p["pr"]):
            peers_dropped += len(p["pr"]) - len(kept)
        p["pr"] = kept or None
    out_features.append({
        "type": "Feature",
        "geometry": feat["geometry"],
        "properties": {"f": fips, **p},
    })
    matched += 1
print(f"  peer FIPS dropped (not renderable): {peers_dropped:,}")

print(f"  matched: {matched:,} / {len(geo['features']):,} GeoJSON features")
print(f"  ratio: {matched/len(geo['features'])*100:.1f}%")

# Write intermediate (mapshaper will simplify)
out_path = WEB_DATA / "tracts_raw.geojson"
with out_path.open("w") as f:
    json.dump({"type": "FeatureCollection", "features": out_features}, f)
print(f"  → {out_path}  ({out_path.stat().st_size / 1e6:.1f} MB)")

# Bounding box per state for state-zoom
print("\nComputing per-state bounding boxes…")
import math
def bbox_from_feature(feat):
    coords = feat["geometry"]["coordinates"]
    minx, miny, maxx, maxy = math.inf, math.inf, -math.inf, -math.inf
    def walk(coord):
        nonlocal minx, miny, maxx, maxy
        if isinstance(coord[0], (int, float)):
            x, y = coord[0], coord[1]
            minx = min(minx, x); miny = min(miny, y)
            maxx = max(maxx, x); maxy = max(maxy, y)
        else:
            for c in coord: walk(c)
    walk(coords)
    return [minx, miny, maxx, maxy]

state_bbox = {}
for feat in out_features:
    st = feat["properties"]["st"]
    bb = bbox_from_feature(feat)
    if st not in state_bbox:
        state_bbox[st] = bb
    else:
        state_bbox[st] = [
            min(state_bbox[st][0], bb[0]),
            min(state_bbox[st][1], bb[1]),
            max(state_bbox[st][2], bb[2]),
            max(state_bbox[st][3], bb[3]),
        ]

# round + write
state_bbox = {st: [round(v, 4) for v in bb] for st, bb in state_bbox.items()}
with (WEB_DATA / "state_bbox.json").open("w") as f:
    json.dump(state_bbox, f)
print(f"  → {WEB_DATA/'state_bbox.json'}  ({len(state_bbox)} states)")

print("\nDone.")
