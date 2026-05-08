#!/usr/bin/env python3
"""Build dashboard data files for the Round-7 two-layer credit-desert dashboard.

Two models × two horizons (h+3 = 2027, h+6 = 2030):
    Model 1, diagnostic (Round 5): full 39-feature stack including supply-side.
    Model 2, influenceable (Round 7): 20 lever features, residualized.

Inputs (all on disk; ROUND5 is bundled into the repo as round5-diagnostic/):
    ../round5-diagnostic/diagnostics/walk_forward_h3/test_predictions.parquet
    ../round5-diagnostic/diagnostics/walk_forward_h6/test_predictions.parquet
    ../round5-diagnostic/diagnostics/feature_importance/ranked.csv
    ../round5-diagnostic/diagnostics/family_ablation_h{3,6}/ablation_summary.csv
    ../diagnostics/round7_phaseA_h3/test_predictions.parquet
    ../diagnostics/round7_phaseA_h6/test_predictions.parquet
    ../diagnostics/round7_ablation_h{3,6}/ablation_summary.csv
    ../diagnostics/round7_pruned_h{3,6}/sweep_results.csv + feature_ranking.csv
    ../diagnostics/round7_regime_split_h{3,6}/...
    ../round5-diagnostic/web/data/tracts.geojson  (simplified geometry; download via scripts/download-data.sh)

Outputs (web/data/):
    tracts.geojson                  per tract: m1_h3, m2_h3, m1_h6, m2_h6 + ranks
    counties.geojson                per county: weighted m1_h3, m2_h3, m1_h6, m2_h6 + ranks
    county_stats.json               per-county drawer payload (top tracts + metadata)
    state_stats.json                per-state tract/county summaries + national histograms
    state_bbox.json                 per-state bbox for fly-to
    ablation_h3.json, ablation_h6.json    model-keyed: diagnostic + influenceable
    pruning_h3.json, pruning_h6.json      model-keyed: diagnostic + influenceable
    regime_h3.json, regime_h6.json
    feature_stats.json              for the Scenario explorer slider
"""
from __future__ import annotations
import json
import math
import gzip
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, average_precision_score

ROOT = Path(__file__).resolve().parent
ROUND7 = ROOT.parent
SHIVANI = ROUND7.parent
# Round 5 (diagnostic-model) source ships in this repo at round7/round5-diagnostic/.
# Some processed/raw data is gitignored and lives in tarballs uploaded as
# GitHub Release assets. See scripts/download-data.sh for retrieval.
ROUND5 = ROUND7 / "round5-diagnostic"

DATA = ROOT / "data"
DATA.mkdir(parents=True, exist_ok=True)

HORIZONS = (3, 6)

PREDS = {
    ("m1", 3): ROUND5 / "diagnostics" / "walk_forward_h3" / "test_predictions.parquet",
    ("m1", 6): ROUND5 / "diagnostics" / "walk_forward_h6" / "test_predictions.parquet",
    ("m2", 3): ROUND7 / "diagnostics" / "round7_phaseA_h3" / "test_predictions.parquet",
    ("m2", 6): ROUND7 / "diagnostics" / "round7_phaseA_h6" / "test_predictions.parquet",
}

SRC_GEO = ROUND5 / "web" / "data" / "tracts.geojson"
COUNTY_GEO = ROUND5 / "web" / "data" / "counties.geojson"
COUNTY_LOOKUP = ROUND5 / "web" / "data" / "_lookup" / "county_names.txt"
SHAP_JSON = DATA / "shap_top.json"
SHAP_JSON_GZ = DATA / "shap_top.json.gz"

# Search index inputs (downloaded ahead of build by the harness; if missing,
# the city index falls back to a hardcoded list of major US cities).
GAZ_PLACE_FILE = Path("/tmp/gaz_place/2020_Gaz_place_national.txt")
PLACE_POP_FILE = Path("/tmp/place_pop.json")

PANEL_PARQUET = ROUND7 / "data" / "processed" / "panel" / "tract_year_with_target_round7.parquet"
ROUND5_PANEL_PARQUET = ROUND5 / "data" / "processed" / "panel" / "tract_year_with_target.parquet"
ACS_POP_CSV = ROUND5 / "data" / "processed" / "acs" / "tract_year_h2020.csv"
ACS_POP_CSV_FALLBACK = ROUND5 / "data" / "processed" / "acs" / "tract_year.csv"

LEVER_FEATURES = [
    "distance_to_nearest_bank_branch",
    "branches_within_5mi",
    "mdi_branches_within_10mi",
    "mdi_branches_within_25mi",
    "ssbci_active",
    "ssbci_program_count",
    "microloan_intermediary_within_25mi",
    "lender_hhi_tract_resid",
]

LEVER_LABEL = {
    "residualized_concentration": "Lender concentration (residualized)",
    "mdi_mission_lender": "MDI / mission lender",
    "branch_access": "Branch access",
    "residualized_loan_size": "Loan-size mix (residualized)",
    "microlender_ecosystem": "Microlender ecosystem",
    "residualized_lender_mix": "Lender mix (residualized)",
    "ssbci_state_policy": "SSBCI state policy",
}

DIAGNOSTIC_FAMILY_LABEL = {
    "place_rural": "Rurality / place type",
    "place_persistent_pov": "Persistent poverty",
    "regime_flag": "HMDA availability regime",
    "cra_county_concentration": "CRA county concentration",
    "fdic_concentration": "FDIC concentration",
    "fdic_other": "FDIC branch / deposit structure",
    "hmda": "HMDA lending flow",
    "acs_demographics": "ACS demographics",
    "other": "Other",
}

STATE_ABBR = {
    "01":"AL","02":"AK","04":"AZ","05":"AR","06":"CA","08":"CO","09":"CT","10":"DE",
    "11":"DC","12":"FL","13":"GA","15":"HI","16":"ID","17":"IL","18":"IN","19":"IA",
    "20":"KS","21":"KY","22":"LA","23":"ME","24":"MD","25":"MA","26":"MI","27":"MN",
    "28":"MS","29":"MO","30":"MT","31":"NE","32":"NV","33":"NH","34":"NJ","35":"NM",
    "36":"NY","37":"NC","38":"ND","39":"OH","40":"OK","41":"OR","42":"PA","44":"RI",
    "45":"SC","46":"SD","47":"TN","48":"TX","49":"UT","50":"VT","51":"VA","53":"WA",
    "54":"WV","55":"WI","56":"WY",
}

TERRITORIES = {"72", "78", "60", "66", "69"}


def build_ablation_payload(df: pd.DataFrame, label_map: dict[str, str]) -> dict | None:
    if df.empty:
        return None
    base_rows = df[df["lever_dropped"] == "none_baseline"]
    if base_rows.empty:
        return None
    base = base_rows.iloc[0]
    levers = df[df["lever_dropped"] != "none_baseline"].sort_values("delta_ap_vs_full")

    def lever_label(row: pd.Series) -> str:
        raw = row.get("lever_label")
        if isinstance(raw, str) and raw.strip():
            return raw
        return label_map.get(row["lever_dropped"], row["lever_dropped"])

    return {
        "baseline": {
            "n_features": int(base["n_features"]),
            "mean_auc": round(float(base["mean_test_auc"]), 4),
            "mean_ap": round(float(base["mean_test_ap"]), 4),
        },
        "levers": [
            {
                "lever": lever_label(r),
                "key": r["lever_dropped"],
                "n_features": int(r["n_features"]),
                "mean_auc": round(float(r["mean_test_auc"]), 4),
                "mean_ap": round(float(r["mean_test_ap"]), 4),
                "delta_auc": round(float(r["delta_auc_vs_full"]), 4),
                "delta_ap": round(float(r["delta_ap_vs_full"]), 4),
            }
            for _, r in levers.iterrows()
        ],
    }


def build_ranking_payload(
    rk: pd.DataFrame,
    importance_col: str,
    *,
    sweep: pd.DataFrame | None = None,
) -> dict:
    payload = {
        "ranking": [
            {
                "rank": int(r["rank"]) if "rank" in rk.columns else i + 1,
                "feature": r["feature"],
                "importance": round(float(r[importance_col]), 4),
            }
            for i, (_, r) in enumerate(rk.iterrows())
        ],
    }
    if sweep is not None:
        payload["sweep"] = [
            {
                "k": int(r["k"]),
                "auc": round(float(r["mean_test_auc"]), 4),
                "ap": round(float(r["mean_test_ap"]), 4),
            }
            for _, r in sweep.iterrows()
        ]
    return payload


def aggregate_latest(preds: pd.DataFrame) -> pd.DataFrame:
    """Per tract, take the most-recent (year, fold) calibrated probability."""
    sorted_p = preds.sort_values(["year", "fold"], ascending=[False, False])
    latest = sorted_p.drop_duplicates(subset="tract_fips", keep="first").copy()
    return latest[["tract_fips", "county_fips", "year", "fold", "y_true", "y_prob_calibrated"]]


def load_county_names() -> dict[str, str]:
    out: dict[str, str] = {}
    if not COUNTY_LOOKUP.exists():
        return out
    with COUNTY_LOOKUP.open("r", encoding="utf-8", errors="replace") as f:
        next(f)
        for line in f:
            parts = line.rstrip("\r\n").split("|")
            if len(parts) < 5:
                continue
            fips = (parts[1] + parts[2]).strip().zfill(5)
            out[fips] = f"{parts[4].strip()}, {parts[0].strip()}"
    return out


def headline_metrics(preds: pd.DataFrame) -> dict:
    """Mean across folds — the canonical AUC/AP for this project."""
    per_fold_auc, per_fold_ap = [], []
    for fold, sub in preds.groupby("fold"):
        if sub["y_true"].nunique() < 2:
            continue
        per_fold_auc.append(float(roc_auc_score(sub["y_true"], sub["y_prob_calibrated"])))
        per_fold_ap.append(float(average_precision_score(sub["y_true"], sub["y_prob_calibrated"])))
    return {
        "mean_auc": round(float(np.mean(per_fold_auc)), 4) if per_fold_auc else None,
        "std_auc":  round(float(np.std(per_fold_auc)),  4) if per_fold_auc else None,
        "mean_ap":  round(float(np.mean(per_fold_ap)),  4) if per_fold_ap else None,
        "std_ap":   round(float(np.std(per_fold_ap)),   4) if per_fold_ap else None,
        "n_folds":  len(per_fold_auc),
    }


def load_latest_population() -> pd.DataFrame:
    """Latest non-null tract population for county weighting."""
    if not PANEL_PARQUET.exists():
        print(f"  WARN: panel parquet missing: {PANEL_PARQUET}")
    else:
        try:
            panel = pd.read_parquet(PANEL_PARQUET, columns=["tract_fips", "year", "population"])
            panel = panel.dropna(subset=["population"]).copy()
            if not panel.empty:
                panel = panel.sort_values(["tract_fips", "year"], ascending=[True, False])
                latest = panel.drop_duplicates(subset="tract_fips", keep="first").copy()
                latest["population"] = pd.to_numeric(latest["population"], errors="coerce")
                latest = latest.dropna(subset=["population"])
                print(f"  population source: {PANEL_PARQUET}")
                return latest[["tract_fips", "population"]]
        except Exception as exc:
            if "population" not in str(exc):
                raise
            print("  WARN: Round 7 panel has no population column; using Round 5 ACS population")

    pop_csv = ACS_POP_CSV if ACS_POP_CSV.exists() else ACS_POP_CSV_FALLBACK
    if not pop_csv.exists():
        print(f"  WARN: no tract population source found: {ACS_POP_CSV}")
        return pd.DataFrame(columns=["tract_fips", "population"])

    acs = pd.read_csv(pop_csv, dtype={"tract_fips": str})
    if "vintage" not in acs.columns or "population" not in acs.columns:
        print(f"  WARN: population CSV missing required columns: {pop_csv}")
        return pd.DataFrame(columns=["tract_fips", "population"])
    acs = acs[["tract_fips", "vintage", "population"]].copy()
    acs["tract_fips"] = acs["tract_fips"].astype(str).str.zfill(11)
    acs["population"] = pd.to_numeric(acs["population"], errors="coerce")
    acs = acs.dropna(subset=["population"])
    if acs.empty:
        return pd.DataFrame(columns=["tract_fips", "population"])
    acs = acs.sort_values(["tract_fips", "vintage"], ascending=[True, False])
    latest = acs.drop_duplicates(subset="tract_fips", keep="first").copy()
    print(f"  population source: {pop_csv}")
    return latest[["tract_fips", "population"]]


def top_tracts_payload(sub: pd.DataFrame,
                       county_names_lookup: dict[str, str],
                       model_keys: list[tuple[str, int]],
                       limit: int = 5) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for (model, h) in model_keys:
        col = f"risk_{model}_h{h}"
        if col not in sub.columns:
            continue
        ranked = sub.dropna(subset=[col]).sort_values(col, ascending=False).head(limit)
        out[f"{model}_h{h}"] = [
            {
                "f": str(r.tract_fips),
                "cn": county_names_lookup.get(
                    str(getattr(r, "county_fips", None) or r.tract_fips[:5]).zfill(5),
                    "",
                ),
                "m1_h3": None if pd.isna(getattr(r, "risk_m1_h3", float("nan"))) else round(float(r.risk_m1_h3), 4),
                "m1_h6": None if pd.isna(getattr(r, "risk_m1_h6", float("nan"))) else round(float(r.risk_m1_h6), 4),
                "m2_h3": None if pd.isna(getattr(r, "risk_m2_h3", float("nan"))) else round(float(r.risk_m2_h3), 4),
                "m2_h6": None if pd.isna(getattr(r, "risk_m2_h6", float("nan"))) else round(float(r.risk_m2_h6), 4),
            }
            for r in ranked.itertuples(index=False)
        ]
    return out


def load_shap_top() -> dict:
    """Load per-tract top SHAP drivers if present."""
    if SHAP_JSON_GZ.exists():
        with gzip.open(SHAP_JSON_GZ, "rt") as f:
            data = json.load(f)
        print(f"  SHAP driver source: {SHAP_JSON_GZ}")
        return data
    if SHAP_JSON.exists():
        with SHAP_JSON.open() as f:
            data = json.load(f)
        print(f"  SHAP driver source: {SHAP_JSON}")
        return data
    print("  WARN: SHAP driver source missing; county drawer drivers will be empty")
    return {}


def _clip_prob(p: float) -> float:
    return max(1e-4, min(1 - 1e-4, p))


def shap_to_pp(risk: float, shap_value: float) -> float:
    """Convert log-odds SHAP contribution to signed probability points."""
    p = _clip_prob(float(risk))
    z = math.log(p / (1 - p))
    without_feature = 1 / (1 + math.exp(-(z - float(shap_value))))
    return (p - without_feature) * 100


def county_drivers_payload(sub: pd.DataFrame,
                           shap_top: dict,
                           model_keys: list[tuple[str, int]],
                           limit: int = 8) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {f"{model}_h{h}": [] for (model, h) in model_keys}
    for (model, h) in model_keys:
        key = f"{model}_h{h}"
        risk_col = f"risk_{model}_h{h}"
        if risk_col not in sub.columns:
            continue
        valid = sub.dropna(subset=[risk_col]).copy()
        if valid.empty:
            continue
        weighted = valid.dropna(subset=["population"]).copy()
        if not weighted.empty and float(weighted["population"].sum()) > 0:
            rows = weighted
            weights = weighted["population"].to_numpy(dtype=float)
        else:
            rows = valid
            weights = np.ones(len(valid), dtype=float)

        total_weight = 0.0
        feature_sums: dict[str, dict[str, float]] = {}
        for row, weight in zip(rows.itertuples(index=False), weights):
            entry = shap_top.get(str(row.tract_fips))
            drivers = entry.get(key) if isinstance(entry, dict) else None
            if not drivers:
                continue
            weight = float(weight)
            total_weight += weight
            risk = float(getattr(row, risk_col))
            for feat, raw_value in drivers:
                try:
                    shap_value = float(raw_value)
                except (TypeError, ValueError):
                    continue
                rec = feature_sums.setdefault(feat, {"value": 0.0, "pp": 0.0})
                rec["value"] += shap_value * weight
                rec["pp"] += shap_to_pp(risk, shap_value) * weight

        if total_weight <= 0:
            out[key] = []
            continue
        ranked = []
        for feat, sums in feature_sums.items():
            ranked.append({
                "feature": feat,
                "value": round(sums["value"] / total_weight, 4),
                "pp": round(sums["pp"] / total_weight, 3),
            })
        ranked.sort(key=lambda r: abs(r["pp"]), reverse=True)
        out[key] = ranked[:limit]
    return out


# Hardcoded fallback list of major US cities (used if Census Gazetteer is missing).
# Roughly the top ~120 cities by population — enough to be useful but not exhaustive.
HARDCODED_CITIES = [
    ("New York", "NY", 40.7128, -74.0060, 8336000),
    ("Los Angeles", "CA", 34.0522, -118.2437, 3979000),
    ("Chicago", "IL", 41.8781, -87.6298, 2693000),
    ("Houston", "TX", 29.7604, -95.3698, 2320000),
    ("Phoenix", "AZ", 33.4484, -112.0740, 1680000),
    ("Philadelphia", "PA", 39.9526, -75.1652, 1584000),
    ("San Antonio", "TX", 29.4241, -98.4936, 1547000),
    ("San Diego", "CA", 32.7157, -117.1611, 1424000),
    ("Dallas", "TX", 32.7767, -96.7970, 1343000),
    ("San Jose", "CA", 37.3382, -121.8863, 1027000),
    ("Austin", "TX", 30.2672, -97.7431, 978000),
    ("Jacksonville", "FL", 30.3322, -81.6557, 911000),
    ("Fort Worth", "TX", 32.7555, -97.3308, 909000),
    ("Columbus", "OH", 39.9612, -82.9988, 898000),
    ("Charlotte", "NC", 35.2271, -80.8431, 885000),
    ("Indianapolis", "IN", 39.7684, -86.1581, 876000),
    ("San Francisco", "CA", 37.7749, -122.4194, 875000),
    ("Seattle", "WA", 47.6062, -122.3321, 753000),
    ("Denver", "CO", 39.7392, -104.9903, 727000),
    ("Washington", "DC", 38.9072, -77.0369, 705000),
    ("Boston", "MA", 42.3601, -71.0589, 692000),
    ("Nashville", "TN", 36.1627, -86.7816, 670000),
    ("Detroit", "MI", 42.3314, -83.0458, 670000),
    ("Memphis", "TN", 35.1495, -90.0490, 651000),
    ("Portland", "OR", 45.5152, -122.6784, 654000),
    ("Las Vegas", "NV", 36.1699, -115.1398, 651000),
    ("Atlanta", "GA", 33.7490, -84.3880, 506000),
    ("Miami", "FL", 25.7617, -80.1918, 467000),
    ("New Orleans", "LA", 29.9511, -90.0715, 391000),
    ("Minneapolis", "MN", 44.9778, -93.2650, 429000),
]


def build_city_index() -> list[dict]:
    """Build city search index from Census Gazetteer + decennial place-pop API.
    Falls back to the hardcoded list if either input file is missing.
    Filters to incorporated places with population > 10,000.
    """
    if not GAZ_PLACE_FILE.exists() or not PLACE_POP_FILE.exists():
        print(f"  WARN: Gazetteer ({GAZ_PLACE_FILE.exists()}) or pop file "
              f"({PLACE_POP_FILE.exists()}) missing; using hardcoded fallback.")
        return [{"name": n, "state": s, "lat": lat, "lon": lon, "pop": pop}
                for (n, s, lat, lon, pop) in HARDCODED_CITIES]

    # Load population by GEOID. Decennial returns rows: [name, pop, state, place].
    # GEOID is state(2)+place(5).
    with PLACE_POP_FILE.open("r", encoding="utf-8") as f:
        pop_rows = json.load(f)
    pop_by_geoid: dict[str, int] = {}
    for row in pop_rows[1:]:
        try:
            pop = int(row[1])
        except (ValueError, TypeError):
            continue
        geoid = str(row[2]).zfill(2) + str(row[3]).zfill(5)
        pop_by_geoid[geoid] = pop

    # Parse gazetteer (tab-separated). Trim place-name suffixes (e.g. "city",
    # "town", "CDP") so the search index reads cleanly. Skip CDPs entirely
    # (LSAD 57) — these aren't cities people would search for.
    KEEP_LSAD = {"21", "25", "37", "43", "47"}  # borough, city, town, town, village
    out = []
    with GAZ_PLACE_FILE.open("r", encoding="utf-8", errors="replace") as f:
        next(f)  # header
        for line in f:
            parts = line.rstrip("\r\n").split("\t")
            if len(parts) < 12:
                continue
            usps = parts[0].strip()
            geoid = parts[1].strip().zfill(7)
            name = parts[3].strip()
            lsad = parts[4].strip()
            if lsad not in KEEP_LSAD:
                continue
            try:
                lat = float(parts[10])
                lon = float(parts[11])
            except (ValueError, TypeError):
                continue
            pop = pop_by_geoid.get(geoid)
            if pop is None or pop < 10_000:
                continue
            # Strip the trailing LSAD descriptor from the name if present —
            # "Atlanta city" → "Atlanta", "Boston town" → "Boston".
            for suffix in (" city", " town", " borough", " village",
                           " municipality"):
                if name.endswith(suffix):
                    name = name[: -len(suffix)].strip()
                    break
            out.append({
                "name": name,
                "state": usps,
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "pop": pop,
            })

    out.sort(key=lambda r: (-r["pop"], r["name"].lower()))
    return out


def build_driver_distributions(snap_year: int = 2024) -> None:
    """Emit feature_distributions.json + tract_features.json.gz + county_features.json.gz.

    Drives the new percentile-aware drivers panel. Reads the SHAP cache to
    determine which features ever appear as a top driver, then snapshots the
    latest year of both panels (round 5 for ACS/HMDA features, round 7 for
    lever features), computes p1..p99 nationally and per-state, and emits
    per-tract / per-county raw values for those features.
    """
    print(f"\nDriver distributions (year={snap_year})…")

    shap_path = SHAP_JSON_GZ if SHAP_JSON_GZ.exists() else SHAP_JSON
    if not shap_path.exists():
        print(f"  SKIP: SHAP cache missing at {shap_path}")
        return
    opener = gzip.open if shap_path.suffix == ".gz" else open
    with opener(shap_path, "rt") as f:
        shap = json.load(f)

    feat_universe: set[str] = set()
    for tract, models in shap.items():
        if not isinstance(models, dict):
            continue
        for _key, drivers in models.items():
            for entry in (drivers or []):
                if isinstance(entry, (list, tuple)) and len(entry) >= 1:
                    feat_universe.add(str(entry[0]))
    feat_universe.discard("has_hmda")  # render-excluded; skip distribution work
    print(f"  driver universe: {len(feat_universe)} features")

    panels = []
    if PANEL_PARQUET.exists():
        r7 = pd.read_parquet(PANEL_PARQUET)
        r7 = r7[r7["year"] == snap_year].copy()
        panels.append(("round7", r7))
        print(f"  round7 panel: {len(r7):,} tracts")
    if ROUND5_PANEL_PARQUET.exists():
        r5 = pd.read_parquet(ROUND5_PANEL_PARQUET)
        r5 = r5[r5["year"] == snap_year].copy()
        panels.append(("round5", r5))
        print(f"  round5 panel: {len(r5):,} tracts")
    if not panels:
        print("  SKIP: no panel parquet found")
        return

    # Outer-merge on tract_fips. For features in multiple panels, the first
    # panel listed wins (round 7 takes precedence — it's what the model trained on).
    merged = panels[0][1].drop(columns=["year"], errors="ignore").copy()
    for _name, p in panels[1:]:
        new_cols = [c for c in p.columns if c not in merged.columns and c != "year"]
        if not new_cols:
            continue
        merged = merged.merge(
            p[["tract_fips"] + new_cols], on="tract_fips", how="outer"
        )
    merged["tract_fips"] = merged["tract_fips"].astype(str).str.zfill(11)
    merged["_state"] = merged["tract_fips"].str[:2]

    keep_feats = sorted([f for f in feat_universe if f in merged.columns])
    skipped = sorted(feat_universe - set(keep_feats))
    if skipped:
        print(f"  features in SHAP cache but absent from panels (skipped): {skipped}")
    print(f"  features kept: {len(keep_feats)}")

    # ---- 1. feature_distributions.json ----
    QUANTILES = [i / 100.0 for i in range(1, 100)]  # p1..p99 (99 cutpoints)
    distributions: dict[str, dict] = {}
    for feat in keep_feats:
        s = pd.to_numeric(merged[feat], errors="coerce").dropna()
        if len(s) < 100:
            continue
        nunique = int(s.nunique())
        # Categorical heuristic: small distinct count AND values are integer-valued.
        is_cat = (nunique <= 12) and bool(np.allclose(s.values, np.round(s.values)))
        rec: dict = {"is_categorical": is_cat}
        if is_cat:
            counts = s.astype(int).value_counts(normalize=True).sort_index()
            rec["categories"] = [
                {"value": int(v), "share": round(float(counts[v]), 4)}
                for v in counts.index
            ]
        else:
            rec["national"] = [round(float(q), 6) for q in s.quantile(QUANTILES).tolist()]
        # By-state slice (skip if too few non-null tracts in the state).
        by_state: dict = {}
        for st_fips, st_abbr in STATE_ABBR.items():
            mask = merged["_state"] == st_fips
            ss = pd.to_numeric(merged.loc[mask, feat], errors="coerce").dropna()
            if len(ss) < 25:
                continue
            if is_cat:
                vc = ss.astype(int).value_counts(normalize=True).sort_index()
                by_state[st_abbr] = [
                    {"value": int(v), "share": round(float(vc[v]), 4)}
                    for v in vc.index
                ]
            else:
                by_state[st_abbr] = [round(float(q), 6) for q in ss.quantile(QUANTILES).tolist()]
        if by_state:
            rec["by_state"] = by_state
        distributions[feat] = rec
    with (DATA / "feature_distributions.json").open("w") as f:
        json.dump(distributions, f, separators=(",", ":"))
    print(f"  → feature_distributions.json ({len(distributions)} features)")

    # ---- 2. tract_features.json.gz ----
    tract_features: dict[str, dict] = {}
    feat_arrays = {feat: pd.to_numeric(merged[feat], errors="coerce").to_numpy() for feat in keep_feats}
    fips_arr = merged["tract_fips"].to_numpy()
    for i, fips in enumerate(fips_arr):
        rec: dict = {}
        for feat in keep_feats:
            v = feat_arrays[feat][i]
            if np.isnan(v) or np.isinf(v):
                continue
            rec[feat] = round(float(v), 4)
        if rec:
            tract_features[fips] = rec
    with gzip.open(DATA / "tract_features.json.gz", "wt") as f:
        json.dump(tract_features, f, separators=(",", ":"))
    print(f"  → tract_features.json.gz ({len(tract_features)} tracts)")

    # ---- 3. county_features.json.gz (population-weighted across tracts) ----
    pop = pd.to_numeric(merged.get("population"), errors="coerce").fillna(0.0).to_numpy()
    county_fips = merged["tract_fips"].str[:5].to_numpy()
    county_features: dict[str, dict] = {}
    df = merged[["tract_fips"] + keep_feats].copy()
    df["_county"] = county_fips
    df["_w"] = pop
    for cf, grp in df.groupby("_county", sort=False):
        w = grp["_w"].to_numpy()
        wsum = float(w.sum())
        if wsum <= 0:
            w = np.ones(len(grp), dtype=float)
            wsum = float(len(grp))
        rec: dict = {}
        for feat in keep_feats:
            vals = pd.to_numeric(grp[feat], errors="coerce").to_numpy()
            mask = ~np.isnan(vals)
            if not mask.any():
                continue
            v = float(np.average(vals[mask], weights=w[mask]))
            if math.isfinite(v):
                rec[feat] = round(v, 4)
        if rec:
            county_features[str(cf)] = rec
    with gzip.open(DATA / "county_features.json.gz", "wt") as f:
        json.dump(county_features, f, separators=(",", ":"))
    print(f"  → county_features.json.gz ({len(county_features)} counties)")


def main() -> None:
    print("=" * 60)
    print("ROUND 7 · Two-Layer Dashboard Data Build (multi-horizon)")
    print("=" * 60)

    # ---- Load all 4 prediction sources, build per-tract latest risks ----
    print("\n[1/7] Loading 4 prediction sources…")
    preds_loaded: dict[tuple[str, int], pd.DataFrame] = {}
    latest_per: dict[tuple[str, int], pd.DataFrame] = {}
    for key, path in PREDS.items():
        if not path.exists():
            print(f"  WARN: {path} missing")
            continue
        df = pd.read_parquet(path)
        preds_loaded[key] = df
        latest_per[key] = aggregate_latest(df)
        print(f"  {key}: {len(df):,} rows, {len(latest_per[key]):,} unique tracts")

    # ---- Build merged per-tract table ----
    print("\n[2/7] Merging per-tract risks across 4 (model, horizon)…")
    merged = None
    for (model, h), latest in latest_per.items():
        col = f"risk_{model}_h{h}"
        ycol = f"ytrue_{model}_h{h}"
        ren = latest.rename(columns={"y_prob_calibrated": col, "y_true": ycol})
        keep = ["tract_fips", "county_fips", col, ycol]
        ren = ren[keep]
        merged = ren if merged is None else merged.merge(ren, on=["tract_fips", "county_fips"], how="outer")
    merged["state_fips"] = merged["tract_fips"].str[:2]
    merged["state"] = merged["state_fips"].map(STATE_ABBR).fillna(merged["state_fips"])
    merged = merged[~merged["state_fips"].isin(TERRITORIES)].copy()
    print(f"  merged tracts (excl. territories): {len(merged):,}")

    # ---- Attach latest tract population ----
    print("\n[2b/7] Latest tract population…")
    tract_pop = load_latest_population()
    merged = merged.merge(tract_pop, on="tract_fips", how="left")
    pop_cov = int(merged["population"].notna().sum())
    print(f"  population coverage: {pop_cov:,} / {len(merged):,} tracts")
    shap_top = load_shap_top()

    # ---- Within-state percentile ranks ----
    print("\n[3/7] Within-state percentile ranks…")
    for (model, h) in PREDS.keys():
        col = f"risk_{model}_h{h}"
        if col in merged.columns:
            merged[f"rk_{model}_h{h}"] = merged.groupby("state")[col].rank(pct=True) * 100

    # ---- County aggregates ----
    print("\n[3b/7] County aggregates…")
    county_names_lookup = load_county_names()
    county_rows = []
    county_details: dict[str, dict] = {}
    fallback_counties: list[str] = []
    model_keys = list(PREDS.keys())
    for _, sub in merged.groupby("county_fips", dropna=False):
        if sub.empty:
            continue
        tract0 = str(sub["tract_fips"].iloc[0])
        cf5 = str(sub["county_fips"].iloc[0] if pd.notna(sub["county_fips"].iloc[0]) else tract0[:5]).zfill(5)
        st = str(sub["state"].iloc[0])
        rec = {
            "cf": cf5,
            "state": st,
            "state_fips": str(sub["state_fips"].iloc[0]).zfill(2),
            "cn": county_names_lookup.get(cf5, county_names_lookup.get(cf5[:5], "")),
            "n_tracts": int(len(sub)),
        }
        weighted_population = sub.dropna(subset=["population"])["population"].sum()
        rec["population"] = None if pd.isna(weighted_population) or weighted_population <= 0 else int(round(float(weighted_population)))
        used_unweighted_fallback = False

        for (model, h) in model_keys:
            col = f"risk_{model}_h{h}"
            if col not in sub.columns:
                continue
            valid = sub.dropna(subset=[col]).copy()
            if valid.empty:
                continue
            weighted = valid.dropna(subset=["population"]).copy()
            if not weighted.empty and float(weighted["population"].sum()) > 0:
                value = np.average(weighted[col].to_numpy(dtype=float),
                                   weights=weighted["population"].to_numpy(dtype=float))
            else:
                value = valid[col].mean()
                used_unweighted_fallback = True
            rec[f"risk_{model}_h{h}"] = float(value)

        for (model, h) in model_keys:
            rk_col = f"rk_{model}_h{h}"
            src = sub.dropna(subset=[rk_col]) if rk_col in sub.columns else pd.DataFrame()
            if src.empty:
                continue
            rec[rk_col] = float(src[rk_col].mean())

        if used_unweighted_fallback:
            fallback_counties.append(cf5)

        top_tracts = top_tracts_payload(sub, county_names_lookup, model_keys)
        drivers = county_drivers_payload(sub, shap_top, model_keys)
        county_details[cf5] = {
            "cf": cf5,
            "st": st,
            "cn": rec["cn"],
            "n_tracts": rec["n_tracts"],
            "population": rec["population"],
            "weighting": "unweighted_fallback" if used_unweighted_fallback else "population_weighted",
            "top_tracts": top_tracts,
            "drivers": drivers,
        }
        county_rows.append(rec)

    county_df = pd.DataFrame(county_rows)
    if county_df.empty:
        raise SystemExit("County aggregation failed: no county rows built")
    for (model, h) in model_keys:
        risk_col = f"risk_{model}_h{h}"
        if risk_col in county_df.columns:
            county_df[f"rk_{model}_h{h}"] = county_df.groupby("state")[risk_col].rank(pct=True) * 100
    print(f"  counties built: {len(county_df):,}")
    if fallback_counties:
        preview = ", ".join(fallback_counties[:12])
        extra = "" if len(fallback_counties) <= 12 else f" (+{len(fallback_counties) - 12} more)"
        print(f"  WARN: unweighted fallback for {len(fallback_counties):,} counties: {preview}{extra}")

    # ---- Per-state stats ----
    print("\n[4/7] Per-state stats…")
    state_rows = []
    for st, sub in merged.groupby("state"):
        if len(sub) < 5:
            continue
        county_sub = county_df[county_df["state"] == st].copy()
        rec = {
            "state": st,
            "state_fips": sub["state_fips"].iloc[0],
            "n": int(len(sub)),
            "n_tracts": int(len(sub)),
            "n_counties": int(len(county_sub)),
        }
        for (model, h) in PREDS.keys():
            col = f"risk_{model}_h{h}"
            ycol = f"ytrue_{model}_h{h}"
            ssub = sub.dropna(subset=[col, ycol])
            if len(ssub) == 0:
                continue
            rec[f"mean_{model}_h{h}"] = round(float(ssub[col].mean()), 4)
            if not county_sub.empty and col in county_sub.columns:
                cvals = county_sub[col].dropna()
                if not cvals.empty:
                    rec[f"county_mean_{model}_h{h}"] = round(float(cvals.mean()), 4)
            if ssub[ycol].nunique() > 1:
                rec[f"auc_{model}_h{h}"] = round(float(roc_auc_score(ssub[ycol], ssub[col])), 4)
                rec[f"ap_{model}_h{h}"]  = round(float(average_precision_score(ssub[ycol], ssub[col])), 4)

        rec["top"] = top_tracts_payload(sub, county_names_lookup, model_keys)

        top_counties = {}
        for (model, h) in model_keys:
            col = f"risk_{model}_h{h}"
            if col not in county_sub.columns:
                continue
            ranked = county_sub.dropna(subset=[col]).sort_values(col, ascending=False).head(5)
            top_counties[f"{model}_h{h}"] = [
                {
                    "cf": str(r.cf),
                    "cn": r.cn,
                    "n_tracts": int(r.n_tracts),
                    "population": None if pd.isna(getattr(r, "population", np.nan)) else int(r.population),
                    "m1_h3": None if pd.isna(getattr(r, "risk_m1_h3", float("nan"))) else round(float(r.risk_m1_h3), 4),
                    "m1_h6": None if pd.isna(getattr(r, "risk_m1_h6", float("nan"))) else round(float(r.risk_m1_h6), 4),
                    "m2_h3": None if pd.isna(getattr(r, "risk_m2_h3", float("nan"))) else round(float(r.risk_m2_h3), 4),
                    "m2_h6": None if pd.isna(getattr(r, "risk_m2_h6", float("nan"))) else round(float(r.risk_m2_h6), 4),
                }
                for r in ranked.itertuples(index=False)
            ]
        rec["top_counties"] = top_counties
        state_rows.append(rec)
    state_rows.sort(key=lambda r: r["state"])

    # ---- National risk distribution per (model, horizon): 10-bin histogram ----
    nat_hist_tract = {}
    nat_hist_county = {}
    national_means = {"tract": {}, "county": {}}
    for (model, h) in PREDS.keys():
        col = f"risk_{model}_h{h}"
        edges = np.linspace(0, 1, 11)
        if col in merged.columns:
            vals = merged[col].dropna().values
            if len(vals):
                counts, _ = np.histogram(vals, bins=edges)
                nat_hist_tract[f"{model}_h{h}"] = {
                    "edges": [round(float(e), 2) for e in edges.tolist()],
                    "counts": [int(c) for c in counts.tolist()],
                }
                national_means["tract"][f"{model}_h{h}"] = round(float(np.mean(vals)), 4)
        if col in county_df.columns:
            cvals = county_df[col].dropna().values
            if len(cvals):
                counts, _ = np.histogram(cvals, bins=edges)
                nat_hist_county[f"{model}_h{h}"] = {
                    "edges": [round(float(e), 2) for e in edges.tolist()],
                    "counts": [int(c) for c in counts.tolist()],
                }
                national_means["county"][f"{model}_h{h}"] = round(float(np.mean(cvals)), 4)

    # ---- National / fold averages per (model, horizon) ----
    headline = {}
    for (model, h), df in preds_loaded.items():
        headline[f"{model}_h{h}"] = headline_metrics(df)
    state_stats = {
        "states": state_rows,
        "headline": headline,
        "model_names": {"m1": "Diagnostic", "m2": "Influenceable"},
        "horizons": list(HORIZONS),
        "horizon_labels": {3: "2027 forecast (h+3)", 6: "2030 scenario (h+6)"},
        "feature_counts": {"tract": int(len(merged)), "county": int(len(county_df))},
        "national_means_by_geo": national_means,
        "national_histogram": nat_hist_tract,
        "national_histogram_by_geo": {
            "tract": nat_hist_tract,
            "county": nat_hist_county,
        },
    }
    with (DATA / "state_stats.json").open("w") as f:
        json.dump(state_stats, f, indent=2)
    print(f"  → {DATA/'state_stats.json'}")

    # ---- Per-tract properties → geojson ----
    print("\n[5/7] Building tract properties + geojson…")
    county_names = load_county_names()
    tract_props: dict[str, dict] = {}
    for r in merged.itertuples(index=False):
        fips = r.tract_fips
        cf5 = str(getattr(r, "county_fips", None) or fips[:5]).zfill(5)
        props = {
            "f": fips,
            "st": r.state,
            "cf": cf5,
            "cn": county_names.get(cf5, ""),
            "population": None if pd.isna(getattr(r, "population", np.nan)) else int(round(float(r.population))),
        }
        for (model, h) in PREDS.keys():
            risk = getattr(r, f"risk_{model}_h{h}", None)
            rk   = getattr(r, f"rk_{model}_h{h}", None)
            props[f"{model}_h{h}"]  = None if pd.isna(risk) else round(float(risk), 4)
            props[f"{model}r_h{h}"] = None if pd.isna(rk)   else round(float(rk),   1)
        tract_props[fips] = props

    tract_geo_source = SRC_GEO if SRC_GEO.exists() else DATA / "tracts.geojson"
    if not tract_geo_source.exists():
        raise SystemExit(f"Tract geojson not found: {SRC_GEO}")
    if tract_geo_source != SRC_GEO:
        print(f"  WARN: archived tract geojson missing; reusing {tract_geo_source}")
    with tract_geo_source.open() as f:
        geo = json.load(f)
    out_features = []
    for feat in geo["features"]:
        fips = feat.get("properties", {}).get("f") or feat.get("properties", {}).get("tract_fips")
        if not fips or fips not in tract_props:
            continue
        out_features.append({
            "type": "Feature",
            "geometry": feat["geometry"],
            "properties": tract_props[fips],
        })
    out_geo = {"type": "FeatureCollection", "features": out_features}
    geo_out = DATA / "tracts.geojson"
    with geo_out.open("w") as f:
        json.dump(out_geo, f, separators=(",", ":"))
    print(f"  → {geo_out} ({geo_out.stat().st_size/1e6:.1f} MB, {len(out_features):,} tracts)")

    # ---- County properties + geojson ----
    print("\n[5b/7] Building county properties + geojson…")
    county_props: dict[str, dict] = {}
    for r in county_df.itertuples(index=False):
        props = {
            "f": str(r.cf),
            "st": r.state,
            "cf": str(r.cf),
            "cn": r.cn,
            "n_tracts": int(r.n_tracts),
            "population": None if pd.isna(getattr(r, "population", np.nan)) else int(r.population),
        }
        for (model, h) in model_keys:
            risk = getattr(r, f"risk_{model}_h{h}", None)
            rk = getattr(r, f"rk_{model}_h{h}", None)
            props[f"{model}_h{h}"] = None if pd.isna(risk) else round(float(risk), 4)
            props[f"{model}r_h{h}"] = None if pd.isna(rk) else round(float(rk), 1)
        county_props[str(r.cf)] = props

    if not COUNTY_GEO.exists():
        raise SystemExit(f"County geojson not found: {COUNTY_GEO}")
    with COUNTY_GEO.open() as f:
        county_geo = json.load(f)
    county_out_features = []
    for feat in county_geo["features"]:
        cf5 = str(feat.get("properties", {}).get("f") or "").zfill(5)
        if not cf5 or cf5 not in county_props:
            continue
        county_out_features.append({
            "type": "Feature",
            "geometry": feat["geometry"],
            "properties": county_props[cf5],
        })
    county_out = {"type": "FeatureCollection", "features": county_out_features}
    county_geo_out = DATA / "counties.geojson"
    with county_geo_out.open("w") as f:
        json.dump(county_out, f, separators=(",", ":"))
    print(f"  → {county_geo_out} ({county_geo_out.stat().st_size/1e6:.1f} MB, {len(county_out_features):,} counties)")

    with (DATA / "county_stats.json").open("w") as f:
        json.dump(county_details, f, separators=(",", ":"))
    print(f"  → {DATA/'county_stats.json'} ({len(county_details):,} counties)")

    # ---- bbox per state ----
    print("\n[6/7] State bbox…")

    def bbox_of(geom):
        minx, miny, maxx, maxy = math.inf, math.inf, -math.inf, -math.inf
        def walk(c):
            nonlocal minx, miny, maxx, maxy
            if not c:
                return
            if isinstance(c[0], (int, float)):
                x, y = c[0], c[1]
                if x < minx: minx = x
                if y < miny: miny = y
                if x > maxx: maxx = x
                if y > maxy: maxy = y
            else:
                for cc in c:
                    walk(cc)
        if not geom:
            return None
        walk(geom.get("coordinates") or [])
        return None if minx is math.inf else [minx, miny, maxx, maxy]

    state_bbox: dict[str, list[float]] = {}
    county_bbox: dict[str, list[float]] = {}
    for feat in out_features:
        st = feat["properties"]["st"]
        bb = bbox_of(feat["geometry"])
        if bb is None:
            continue
        if st not in state_bbox:
            state_bbox[st] = bb
        else:
            cur = state_bbox[st]
            state_bbox[st] = [min(cur[0], bb[0]), min(cur[1], bb[1]),
                              max(cur[2], bb[2]), max(cur[3], bb[3])]
    for feat in county_out_features:
        cf = feat["properties"].get("cf")
        bb = bbox_of(feat["geometry"])
        if cf and bb is not None:
            county_bbox[cf] = bb[:]
    state_bbox = {st: [round(v, 4) for v in bb] for st, bb in state_bbox.items()}
    county_bbox = {cf: [round(v, 4) for v in bb] for cf, bb in county_bbox.items()}
    with (DATA / "state_bbox.json").open("w") as f:
        json.dump(state_bbox, f)
    print(f"  → {DATA/'state_bbox.json'} ({len(state_bbox)} states)")

    # ---- County search index ----
    print("\n[6b/7] County search index…")
    county_index = []
    if COUNTY_LOOKUP.exists():
        with COUNTY_LOOKUP.open("r", encoding="utf-8", errors="replace") as f:
            next(f)
            for line in f:
                parts = line.rstrip("\r\n").split("|")
                if len(parts) < 5:
                    continue
                state_abbr = parts[0].strip()
                state_fp = parts[1].strip().zfill(2)
                county_fp = parts[2].strip().zfill(3)
                county_nm = parts[4].strip()
                cf5 = state_fp + county_fp
                if state_fp in TERRITORIES:
                    continue
                bb = county_bbox.get(cf5)
                if not bb:
                    continue  # tracts not present in our merged set
                county_index.append({
                    "name": county_nm,
                    "state": state_abbr,
                    "cf": cf5,
                    "bbox": bb,
                })
    county_index.sort(key=lambda r: (r["name"].lower(), r["state"]))
    with (DATA / "county_index.json").open("w") as f:
        json.dump(county_index, f, separators=(",", ":"))
    print(f"  → {DATA/'county_index.json'} ({len(county_index)} counties)")

    # ---- City search index ----
    print("\n[6c/7] City search index…")
    city_index = build_city_index()
    with (DATA / "city_index.json").open("w") as f:
        json.dump(city_index, f, separators=(",", ":"))
    print(f"  → {DATA/'city_index.json'} ({len(city_index)} cities)")

    # ---- Methodology JSONs per horizon ----
    print("\n[7/7] Methodology panel JSONs (per horizon)…")
    for h in HORIZONS:
        DIAG_ABL_CSV = ROUND5 / "diagnostics" / f"family_ablation_h{h}" / "ablation_summary.csv"
        DIAG_RANK = ROUND5 / "diagnostics" / "feature_importance" / "ranked.csv"
        ABL_CSV = ROUND7 / "diagnostics" / f"round7_ablation_h{h}" / "ablation_summary.csv"
        SWEEP = ROUND7 / "diagnostics" / f"round7_pruned_h{h}" / "sweep_results.csv"
        RANK  = ROUND7 / "diagnostics" / f"round7_pruned_h{h}" / "feature_ranking.csv"
        REG   = ROUND7 / "diagnostics" / f"round7_regime_split_h{h}" / "regime_comparison.csv"
        PRE_FI  = ROUND7 / "diagnostics" / f"round7_regime_split_h{h}" / "precovid_feature_importance.csv"
        POST_FI = ROUND7 / "diagnostics" / f"round7_regime_split_h{h}" / "postcovid_feature_importance.csv"

        # Ablation
        abl_models = {}
        if DIAG_ABL_CSV.exists():
            diag_abl = pd.read_csv(DIAG_ABL_CSV)
            diag_payload = build_ablation_payload(diag_abl, DIAGNOSTIC_FAMILY_LABEL)
            if diag_payload:
                abl_models["diagnostic"] = diag_payload
        if ABL_CSV.exists():
            abl = pd.read_csv(ABL_CSV)
            infl_payload = build_ablation_payload(abl, LEVER_LABEL)
            if infl_payload:
                abl_models["influenceable"] = infl_payload
        if abl_models:
            abl_out = {"horizon": h, **abl_models}
            with (DATA / f"ablation_h{h}.json").open("w") as f:
                json.dump(abl_out, f, indent=2)
            print(f"  → ablation_h{h}.json")

        # Pruning
        pr_models = {}
        if DIAG_RANK.exists():
            diag_rank = pd.read_csv(DIAG_RANK).head(10)
            pr_models["diagnostic"] = build_ranking_payload(diag_rank, "mean")
        if SWEEP.exists() and RANK.exists():
            rk = pd.read_csv(RANK).head(10)
            sw = pd.read_csv(SWEEP).drop_duplicates(subset="k").sort_values("k")
            pr_models["influenceable"] = build_ranking_payload(rk, "mean_importance", sweep=sw)
        if pr_models:
            pr_out = {"horizon": h, **pr_models}
            with (DATA / f"pruning_h{h}.json").open("w") as f:
                json.dump(pr_out, f, indent=2)
            print(f"  → pruning_h{h}.json")

        # Regime
        if REG.exists() and PRE_FI.exists() and POST_FI.exists():
            regime = pd.read_csv(REG)
            pre  = pd.read_csv(PRE_FI).head(8)
            post = pd.read_csv(POST_FI).head(8)
            def fi_rows(df):
                return [{"rank": int(r["rank"]),
                         "feature": r["feature"],
                         "importance": round(float(r["importance"]), 4)}
                        for _, r in df.iterrows()]
            reg_out = {
                "horizon": h,
                "rows": [
                    {"regime": r["regime"],
                     "train_years": r["train_years"],
                     "test_years":  r["test_years"],
                     "n_test":      int(r["n_test"]),
                     "auc":         round(float(r["test_auc"]), 4),
                     "ap":          round(float(r["test_ap"]),  4),
                     "ap_lift":     round(float(r["test_ap_lift"]), 2),
                     "pos_rate":    round(float(r["test_pos_rate"]), 4)}
                    for _, r in regime.iterrows()
                ],
                "precovid_top":  fi_rows(pre),
                "postcovid_top": fi_rows(post),
            }
            with (DATA / f"regime_h{h}.json").open("w") as f:
                json.dump(reg_out, f, indent=2)
            print(f"  → regime_h{h}.json")

    # ---- feature_stats for the slider ----
    print("\nFeature stats for slider…")
    PHASEA_FI = ROUND7 / "diagnostics" / "round7_phaseA_h3"
    fi_files = sorted(PHASEA_FI.glob("feature_importance_F*.csv"))
    fi_frames = [pd.read_csv(p) for p in fi_files]
    fi_all = pd.concat(fi_frames, ignore_index=True) if fi_frames else pd.DataFrame()
    fi_mean = (fi_all.groupby("feature")["importance"].mean().to_dict()
               if not fi_all.empty else {})

    panel = pd.read_parquet(PANEL_PARQUET, columns=LEVER_FEATURES)
    feat_stats: dict[str, dict] = {}
    for col in LEVER_FEATURES:
        s = panel[col].dropna().astype(float)
        if len(s) == 0:
            continue
        feat_stats[col] = {
            "mean": round(float(s.mean()), 6),
            "std":  round(float(s.std(ddof=0)), 6),
            "min":  round(float(s.min()), 6),
            "max":  round(float(s.max()), 6),
            "p10":  round(float(s.quantile(0.10)), 6),
            "p90":  round(float(s.quantile(0.90)), 6),
            "importance": round(float(fi_mean.get(col, 0.0)), 6),
        }
    with (DATA / "feature_stats.json").open("w") as f:
        json.dump(feat_stats, f, indent=2)
    print(f"  → feature_stats.json")

    build_driver_distributions()

    print("\nDone.")


if __name__ == "__main__":
    main()
