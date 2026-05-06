#!/usr/bin/env python3
"""Build a slim GeoJSON of FDIC bank branches for the map overlay.

Source: data/raw/fdic/sod/sod_2024.csv (Summary of Deposits)
Output: web/data/branches.geojson

Properties kept per Point feature:
    c   CERT (institution certificate number)
    d   DEPSUMBR (branch deposits, $K)
    fc  STCNTYBR (5-digit county FIPS, for filtering)

Drops rows with missing or zeroed coordinates. ~78k branches expected.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
WEB_DATA = ROOT / "web" / "data"
WEB_DATA.mkdir(parents=True, exist_ok=True)

SOD_PATH = ROOT / "data" / "raw" / "fdic" / "sod" / "sod_2024.csv"
OUT = WEB_DATA / "branches.geojson"


def parse_money(v: object) -> int:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return 0
    s = str(v).replace(",", "").strip()
    if not s:
        return 0
    try:
        return int(float(s))
    except ValueError:
        return 0


def main() -> int:
    if not SOD_PATH.exists():
        print(f"ERROR: missing {SOD_PATH}", file=sys.stderr)
        return 2

    print(f"Loading {SOD_PATH.name}…")
    df = pd.read_csv(
        SOD_PATH,
        usecols=["CERT", "DEPSUMBR", "SIMS_LATITUDE", "SIMS_LONGITUDE", "STCNTYBR"],
        dtype={"CERT": "Int64", "STCNTYBR": str},
        low_memory=False,
    )
    print(f"  raw rows: {len(df):,}")

    df = df.dropna(subset=["SIMS_LATITUDE", "SIMS_LONGITUDE"])
    df = df[(df["SIMS_LATITUDE"] != 0) & (df["SIMS_LONGITUDE"] != 0)]
    df["STCNTYBR"] = df["STCNTYBR"].fillna("").str.zfill(5)
    print(f"  with valid coords: {len(df):,}")

    features = []
    for row in df.itertuples(index=False):
        lon = float(row.SIMS_LONGITUDE)
        lat = float(row.SIMS_LATITUDE)
        # Skip far-out-of-bounds rows (data-entry artifacts)
        if not (-180 < lon < -50 and 14 < lat < 72):
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
            "properties": {
                "c": int(row.CERT) if pd.notna(row.CERT) else 0,
                "d": parse_money(row.DEPSUMBR),
                "fc": row.STCNTYBR,
            },
        })

    print(f"  in-bounds features: {len(features):,}")
    out = {"type": "FeatureCollection", "features": features}
    with OUT.open("w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"  → {OUT} ({OUT.stat().st_size/1e6:.2f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
