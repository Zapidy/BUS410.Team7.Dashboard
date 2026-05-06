#!/usr/bin/env python3
"""Geocode CDFI and SBA microlender addresses to lat/lng.

(MDIs are FDIC-insured; their branch lat/lng comes free from SoD — no geocoding.)

Strategy:
    1. Census Geocoder (batch endpoint, free, no API key, ~85% hit rate).
    2. Nominatim (OpenStreetMap, 1 req/sec, free) for residual addresses.
    3. Cache by SHA1 of the normalized address string in
       data/raw/geocode_cache/{hash}.json.

Inputs:
    data/raw/cdfi/cdfi_list.csv
    data/raw/microlender/microlender_list.csv

Output:
    data/processed/mission_proximity/cdfi_geocoded.csv
    data/processed/mission_proximity/microlender_geocoded.csv
        columns: <source columns> + lat, lon, geocoder, geocode_status

Reference: https://geocoding.geo.census.gov/geocoder/Geocoding_Services_API.pdf
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "raw" / "geocode_cache"
OUT_DIR = ROOT / "data" / "processed" / "mission_proximity"

CENSUS_BATCH_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "round7-credit-desert-research/1.0 (school project)"
NOMINATIM_DELAY = 1.05  # seconds between requests


def normalize(addr: str, city: str, state: str, zip_: str) -> str:
    return ", ".join(filter(None, (
        str(addr or "").strip(),
        str(city or "").strip(),
        str(state or "").strip(),
        str(zip_ or "").strip(),
    ))).upper()


def cache_path(key: str) -> Path:
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return CACHE / f"{h}.json"


def cache_get(key: str):
    p = cache_path(key)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return None
    return None


def cache_put(key: str, value: dict):
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_path(key).write_text(json.dumps(value))


def census_batch(rows: list[dict]) -> list[dict]:
    """Census batch geocoder. rows = [{id, address, city, state, zip}, ...]."""
    if not rows:
        return []
    csv_buf = io.StringIO()
    csv_buf.write("id,address,city,state,zip\n")
    for r in rows:
        csv_buf.write(",".join(f'"{(r.get(k, "") or "")}"' for k in ("id", "address", "city", "state", "zip")))
        csv_buf.write("\n")
    csv_buf.seek(0)

    files = {"addressFile": ("batch.csv", csv_buf.getvalue(), "text/csv")}
    data = {"benchmark": "Public_AR_Current"}
    try:
        r = requests.post(CENSUS_BATCH_URL, files=files, data=data, timeout=300)
        r.raise_for_status()
    except Exception as e:
        print(f"  Census batch failed: {e}", file=sys.stderr)
        return []

    out = []
    for line in r.text.splitlines():
        cols = [c.strip('"') for c in line.split(",")]
        if len(cols) < 6:
            continue
        rec = {"id": cols[0], "match": cols[2], "matchtype": cols[3] if len(cols) > 3 else ""}
        if rec["match"].lower() == "match" and len(cols) > 5:
            try:
                lon, lat = cols[5].split(",")
                rec["lat"] = float(lat)
                rec["lon"] = float(lon)
            except Exception:
                pass
        out.append(rec)
    return out


def nominatim_one(addr: str) -> dict | None:
    try:
        r = requests.get(
            NOMINATIM_URL,
            params={"q": addr, "format": "json", "limit": 1, "countrycodes": "us"},
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        r.raise_for_status()
        body = r.json()
    except Exception:
        return None
    if not body:
        return None
    return {"lat": float(body[0]["lat"]), "lon": float(body[0]["lon"])}


def geocode_df(df: pd.DataFrame, source: str) -> pd.DataFrame:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = df.copy()
    df["geocode_key"] = df.apply(
        lambda r: normalize(r.get("address"), r.get("city"), r.get("state"), r.get("zip")),
        axis=1,
    )

    # Pull cached results
    cached = []
    pending = []
    for idx, row in df.iterrows():
        c = cache_get(row["geocode_key"])
        if c is not None:
            cached.append((idx, c))
        else:
            pending.append(idx)
    print(f"  {source}: cached={len(cached):,}  pending={len(pending):,}", flush=True)

    # Census batch (in chunks of 1000)
    pending_rows = []
    for idx in pending:
        r = df.loc[idx]
        pending_rows.append({
            "id": str(idx),
            "address": r.get("address", ""),
            "city": r.get("city", ""),
            "state": r.get("state", ""),
            "zip": r.get("zip", ""),
        })

    print(f"  Querying Census Geocoder…", flush=True)
    for chunk_start in range(0, len(pending_rows), 1000):
        chunk = pending_rows[chunk_start:chunk_start + 1000]
        results = census_batch(chunk)
        for rec in results:
            try:
                idx = int(rec["id"])
            except Exception:
                continue
            key = df.loc[idx, "geocode_key"]
            if "lat" in rec and "lon" in rec:
                cache_put(key, {"lat": rec["lat"], "lon": rec["lon"], "geocoder": "census"})
            else:
                cache_put(key, {"lat": None, "lon": None, "geocoder": "census", "fail": True})

    # Nominatim fallback for failures
    print(f"  Nominatim fallback for residuals…", flush=True)
    fallback_count = 0
    for idx in pending:
        key = df.loc[idx, "geocode_key"]
        c = cache_get(key)
        if c and c.get("lat") is not None:
            continue
        # Try Nominatim
        time.sleep(NOMINATIM_DELAY)
        result = nominatim_one(key)
        if result:
            cache_put(key, {"lat": result["lat"], "lon": result["lon"], "geocoder": "nominatim"})
            fallback_count += 1
        else:
            cache_put(key, {"lat": None, "lon": None, "geocoder": "none", "fail": True})
    print(f"    Nominatim recovered: {fallback_count:,}", flush=True)

    # Read final cache state
    df["lat"] = pd.NA
    df["lon"] = pd.NA
    df["geocoder"] = ""
    for idx, row in df.iterrows():
        c = cache_get(row["geocode_key"])
        if c:
            df.at[idx, "lat"] = c.get("lat")
            df.at[idx, "lon"] = c.get("lon")
            df.at[idx, "geocoder"] = c.get("geocoder", "")
    df["geocode_status"] = df["lat"].notna().map({True: "ok", False: "fail"})
    return df


def main():
    cdfi = ROOT / "data" / "raw" / "cdfi" / "cdfi_list.csv"
    micro = ROOT / "data" / "raw" / "microlender" / "microlender_list.csv"

    if cdfi.exists():
        print(f"Geocoding CDFIs…", flush=True)
        df = pd.read_csv(cdfi).fillna("")
        out = geocode_df(df, "cdfi")
        out.to_csv(OUT_DIR / "cdfi_geocoded.csv", index=False)
        hits = out["geocode_status"].eq("ok").sum()
        print(f"\n→ {OUT_DIR / 'cdfi_geocoded.csv'}  hits {hits}/{len(out)} ({hits/len(out)*100:.1f}%)\n",
              flush=True)
    else:
        print(f"  CDFI list missing — run etl/cdfi/pull_cdfi_list.py first", flush=True)

    if micro.exists():
        print(f"Geocoding microlenders…", flush=True)
        df = pd.read_csv(micro).fillna("")
        out = geocode_df(df, "microlender")
        out.to_csv(OUT_DIR / "microlender_geocoded.csv", index=False)
        hits = out["geocode_status"].eq("ok").sum()
        print(f"\n→ {OUT_DIR / 'microlender_geocoded.csv'}  hits {hits}/{len(out)} ({hits/len(out)*100:.1f}%)",
              flush=True)
    else:
        print(f"  Microlender list missing — run etl/microlender/pull_sba_micro.py first", flush=True)


if __name__ == "__main__":
    main()
