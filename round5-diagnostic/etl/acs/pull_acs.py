#!/usr/bin/env python3
"""Pull ACS 5-year tract-level data from the US Census API — no key required.

Pulls ALL US census tracts (~74k) for a set of years, from the ACS 5-year
estimates. One JSON file per state-year. Idempotent.

Variables pulled:
    NAME             — tract description (text)
    B01003_001E      — total population
    B19013_001E      — median household income
    B17001_001E      — universe for poverty status
    B17001_002E      — population below poverty
    B02001_001E      — total population (race)
    B02001_002E      — white alone
    B02001_003E      — Black/African American alone
    B03003_003E      — Hispanic/Latino
    B25001_001E      — total housing units
    B25002_003E      — vacant housing units
    B23025_005E      — unemployed
    B23025_002E      — labor force
    B15003_022E      — bachelor's degree
    B15003_023E      — master's
    B15003_024E      — professional
    B15003_025E      — doctorate
    B15003_001E      — universe for educational attainment

Lag rule: the ACS 5-year vintage labeled (T-4 .. T) was published in the FALL
of year T+1. To predict desert formation in year P, only use ACS vintages
whose end-year < P. The features/build_panel script enforces this.
"""
from __future__ import annotations
import argparse
import json
import ssl
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "raw" / "acs"

VARS = [
    "NAME",
    "B01003_001E",                                              # population
    "B19013_001E",                                              # median HH income
    "B17001_001E", "B17001_002E",                               # poverty
    "B02001_001E", "B02001_002E", "B02001_003E",                # race
    "B03003_003E",                                              # hispanic
    "B25001_001E", "B25002_003E",                               # housing
    "B23025_002E", "B23025_005E",                               # labor force / unemployed
    "B15003_022E", "B15003_023E", "B15003_024E",
    "B15003_025E", "B15003_001E",                               # educational attainment
]

# State FIPS for all 50 + DC + PR
STATES = [
    "01","02","04","05","06","08","09","10","11","12","13","15","16","17","18",
    "19","20","21","22","23","24","25","26","27","28","29","30","31","32","33",
    "34","35","36","37","38","39","40","41","42","44","45","46","47","48","49",
    "50","51","53","54","55","56","72",
]


def fetch_state_year(year: int, state: str) -> int:
    out = OUT_DIR / f"acs5_{year}" / f"state_{state}.json"
    if out.exists() and out.stat().st_size > 0:
        return -1  # skipped
    out.parent.mkdir(parents=True, exist_ok=True)
    params = {"get": ",".join(VARS), "for": "tract:*", "in": f"state:{state}"}
    url = f"https://api.census.gov/data/{year}/acs/acs5?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as resp:
            body = resp.read()
        out.write_bytes(body)
        return body.count(b"[") - 1  # rows ≈ # of "[" minus the outer wrap
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return 0  # state not available for that year (e.g., PR pre-2010)
        raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs="*", type=int,
                    default=[2010, 2015, 2020, 2022])
    ap.add_argument("--states", nargs="*", default=STATES)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"ACS 5-year tract pull → {OUT_DIR}")
    print(f"Years: {args.years}")
    print(f"States: {len(args.states)} states")

    grand_total = 0
    skipped = 0
    for year in args.years:
        year_total = 0
        for s in args.states:
            try:
                n = fetch_state_year(year, s)
                if n == -1:
                    skipped += 1
                    continue
                year_total += n
                print(f"  {year} state={s}: {n:>5,} tracts", flush=True)
                time.sleep(0.05)
            except Exception as e:
                print(f"  ERR {year} state={s}: {e}", flush=True)
        print(f"  -- {year} total: {year_total:,} tracts --")
        grand_total += year_total

    print(f"\nGrand total tracts pulled: {grand_total:,} (skipped {skipped} already on disk)")


if __name__ == "__main__":
    main()
