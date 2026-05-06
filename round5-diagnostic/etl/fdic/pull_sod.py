#!/usr/bin/env python3
"""Pull FDIC Summary of Deposits data via api.fdic.gov.

Pulls one CSV per year, writes per-year files into data/raw/fdic/sod/.
Idempotent: skips years whose output file already exists at >0 bytes.

Usage:
    python pull_sod.py                     # default 2020-2024
    python pull_sod.py 2009 2010 2011      # specific years
    python pull_sod.py --start 2009 --end 2024
"""
from __future__ import annotations
import argparse
import ssl
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

# macOS system Python often ships without a cert bundle. The FDIC API is a
# read-only public endpoint, so an unverified context is acceptable here.
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

API = "https://api.fdic.gov/banks/sod"
FIELDS = ["YEAR", "STCNTYBR", "CERT", "RSSDID", "UNINUMBR",
          "DEPSUMBR", "SIMS_LATITUDE", "SIMS_LONGITUDE", "ZIPBR"]
LIMIT = 5000
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "raw" / "fdic" / "sod"


def fetch_year(year: int, out_path: Path) -> int:
    """Pull all SoD records for a single year and write a single CSV. Returns row count."""
    if out_path.exists() and out_path.stat().st_size > 0:
        # Already pulled. Count lines.
        with out_path.open("rb") as f:
            n = sum(1 for _ in f) - 1
        print(f"  SKIP  {year}  ({n} rows already on disk)", flush=True)
        return n

    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    offset = 0
    pages = 0
    with out_path.open("wb") as out:
        while True:
            params = {
                "filters": f"YEAR:{year}",
                "fields": ",".join(FIELDS),
                "limit": str(LIMIT),
                "offset": str(offset),
                "format": "csv",
            }
            url = f"{API}?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            try:
                with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as resp:
                    body = resp.read()
            except Exception as e:
                print(f"  ERR   {year} off={offset}: {e}", flush=True)
                break

            lines = body.count(b"\n")
            if lines <= 1:
                break

            if pages == 0:
                out.write(body)
            else:
                # Skip header on subsequent pages
                first_nl = body.find(b"\n")
                out.write(body[first_nl + 1:])

            rows += lines - 1
            offset += LIMIT
            pages += 1
            if pages > 30:
                print(f"  WARN  {year}: hit page cap (30)", flush=True)
                break
            # gentle rate limit
            time.sleep(0.05)

    print(f"  OK    {year}  {rows} rows in {pages} pages → {out_path.name}", flush=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("years", nargs="*", type=int)
    ap.add_argument("--start", type=int, default=None)
    ap.add_argument("--end", type=int, default=None)
    args = ap.parse_args()

    if args.years:
        years = args.years
    elif args.start and args.end:
        years = list(range(args.start, args.end + 1))
    else:
        years = list(range(2020, 2025))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"FDIC SoD pull → {OUT_DIR}")
    print(f"Years: {years}")

    total = 0
    for year in years:
        out = OUT_DIR / f"sod_{year}.csv"
        total += fetch_year(year, out)

    print(f"\nTotal rows across {len(years)} years: {total:,}")


if __name__ == "__main__":
    main()
