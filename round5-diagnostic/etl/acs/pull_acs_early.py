#!/usr/bin/env python3
"""Pull early ACS 5-year vintages (2009-2013) with reduced variable set.

The default `pull_acs.py` uses B15003_* (educational attainment) which only
exists from 2012+. For early vintages we use B15002 (the legacy var) + the
core demographic/income/poverty/race/housing/employment variables that have
been stable since 2005.
"""
from __future__ import annotations
import json
import ssl
import time
import urllib.request
import urllib.parse
from pathlib import Path

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "raw" / "acs"
UA = "Mozilla/5.0"

# Core variables that exist in ACS 2010-2013 5-year
EARLY_VARS = [
    "NAME",
    "B01003_001E",                                              # population
    "B19013_001E",                                              # median HH income
    "B17001_001E", "B17001_002E",                               # poverty
    "B02001_001E", "B02001_002E", "B02001_003E",                # race universe / white / black
    "B03003_003E",                                              # hispanic
    "B25001_001E", "B25002_003E",                               # housing units / vacant
    "B23001_001E",                                              # employment universe
    # B15002_001E is the pre-2012 educational attainment universe
    "B15002_001E", "B15002_015E", "B15002_016E",                # universe + bachelor's male/female
    "B15002_017E", "B15002_018E",                               # master's male/female
    "B15002_032E", "B15002_033E", "B15002_034E", "B15002_035E", # bachelors+ female part
]

STATES = [
    "01","02","04","05","06","08","09","10","11","12","13","15","16","17","18",
    "19","20","21","22","23","24","25","26","27","28","29","30","31","32","33",
    "34","35","36","37","38","39","40","41","42","44","45","46","47","48","49",
    "50","51","53","54","55","56","72",
]


def fetch(year: int, state: str) -> int:
    out = OUT_DIR / f"acs5_{year}" / f"state_{state}.json"
    if out.exists() and out.stat().st_size > 0:
        return -1
    out.parent.mkdir(parents=True, exist_ok=True)
    params = {"get": ",".join(EARLY_VARS), "for": "tract:*", "in": f"state:{state}"}
    url = f"https://api.census.gov/data/{year}/acs/acs5?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as resp:
            body = resp.read()
        out.write_bytes(body)
        return body.count(b"[") - 1
    except urllib.error.HTTPError as e:
        return 0 if e.code == 404 else -2


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    years = [2010, 2011, 2012, 2013]
    print(f"Early ACS pull → years={years}")
    for year in years:
        total = 0
        for s in STATES:
            n = fetch(year, s)
            if n >= 0:
                total += n
            time.sleep(0.05)
        print(f"  {year}: {total:,} tracts")


if __name__ == "__main__":
    main()
