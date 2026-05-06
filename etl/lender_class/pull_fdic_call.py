#!/usr/bin/env python3
"""Pull FDIC institutions + Call Report total assets per RSSD-year.

Two endpoints used:
    1. FDIC BankFind Suite — institutions endpoint
       https://banks.data.fdic.gov/api/institutions
       Returns one row per institution with (RSSD, CERT, NAME, CITY, STALP,
       ZIP, ASSET, ACTIVE) — but ASSET is the most-recent snapshot only.

    2. FDIC BankFind Suite — financials endpoint
       https://banks.data.fdic.gov/api/financials
       Returns Call Report financials per CERT × REPDTE. ASSET column is total
       assets at quarter-end. Pull December (REPDTE = YYYY-12-31) for 2009–2024.

Outputs:
    data/raw/fdic_call/institutions.csv          (one row per RSSD, current)
    data/raw/fdic_call/assets_by_year.csv        (RSSD, year, total_assets_k)

Usage:
    python3 pull_fdic_call.py
    python3 pull_fdic_call.py --years 2020 2021    (subset, append-mode)

Requires: requests, pandas. No API key needed.

Reference: https://banks.data.fdic.gov/docs/
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "raw" / "fdic_call"

API_INST = "https://banks.data.fdic.gov/api/institutions"
API_FIN = "https://banks.data.fdic.gov/api/financials"

INST_FIELDS = "CERT,FED_RSSD,NAME,CITY,STALP,ZIP,ASSET,ACTIVE,STNAME"
FIN_FIELDS = "CERT,REPDTE,ASSET"

PAGE_LIMIT = 10000


def paged_get(url: str, params: dict, max_pages: int = 200) -> list[dict]:
    """FDIC API pagination via offset/limit. Returns merged data list.

    The FDIC API rate-limits at ~2 req/sec — sleep 0.6s between pages and
    retry with exponential backoff on 429.
    """
    out: list[dict] = []
    for page in range(max_pages):
        p = dict(params, limit=PAGE_LIMIT, offset=page * PAGE_LIMIT)
        for attempt in range(5):
            r = requests.get(url, params=p, timeout=120)
            if r.status_code == 429:
                wait = 2 ** attempt
                print(f"    429 rate-limit, waiting {wait}s…", flush=True)
                time.sleep(wait)
                continue
            r.raise_for_status()
            break
        else:
            raise RuntimeError(f"persistent 429 at offset {page * PAGE_LIMIT}")
        body = r.json()
        chunk = body.get("data") or []
        if not chunk:
            break
        out.extend(item.get("data", item) for item in chunk)
        if len(chunk) < PAGE_LIMIT:
            break
        time.sleep(0.6)
    return out


def pull_institutions() -> pd.DataFrame:
    print("Pulling all FDIC-insured institutions…", flush=True)
    rows = paged_get(API_INST, {"fields": INST_FIELDS})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df.columns = [c.strip() for c in df.columns]
    # FDIC API returns FED_RSSD; rename to RSSDID for downstream consistency
    if "FED_RSSD" in df.columns and "RSSDID" not in df.columns:
        df = df.rename(columns={"FED_RSSD": "RSSDID"})
    if "RSSDID" in df.columns:
        df["RSSDID"] = df["RSSDID"].astype(str).str.strip()
    if "CERT" in df.columns:
        df["CERT"] = df["CERT"].astype(str).str.strip()
    return df


def pull_assets_year(year: int) -> pd.DataFrame:
    """Pull Call Report ASSET per institution at year-end."""
    repdte = f"{year}-12-31"
    print(f"  {year}: pulling ASSET as of {repdte}…", flush=True)
    rows = paged_get(API_FIN, {"fields": FIN_FIELDS, "filters": f"REPDTE:{repdte.replace('-', '')}"})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["year"] = year
    df["CERT"] = df["CERT"].astype(str).str.strip()
    df["total_assets_k"] = pd.to_numeric(df["ASSET"], errors="coerce")
    return df[["year", "CERT", "total_assets_k"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs="*", type=int, default=list(range(2009, 2025)))
    ap.add_argument("--skip-institutions", action="store_true")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not args.skip_institutions:
        inst_df = pull_institutions()
        if inst_df.empty:
            print("ERROR: empty institutions response — check API status", file=sys.stderr)
            sys.exit(1)
        inst_path = OUT_DIR / "institutions.csv"
        inst_df.to_csv(inst_path, index=False)
        print(f"  → {inst_path}  ({len(inst_df):,} institutions)", flush=True)

    parts = []
    for y in args.years:
        try:
            df = pull_assets_year(y)
        except Exception as e:
            print(f"  {y}: failed — {e}", file=sys.stderr)
            continue
        if not df.empty:
            parts.append(df)
            print(f"    {len(df):,} institutions reporting", flush=True)

    if parts:
        combined = pd.concat(parts, ignore_index=True)
        out = OUT_DIR / "assets_by_year.csv"
        combined.to_csv(out, index=False)
        print(f"\n→ {out}  ({len(combined):,} rows × {combined['year'].nunique()} years)", flush=True)


if __name__ == "__main__":
    main()
