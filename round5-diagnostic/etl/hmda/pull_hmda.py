#!/usr/bin/env python3
"""Pull HMDA loan-level data from the CFPB Data Browser API.

API year coverage: 2018–2024 (per the CFPB API docs and live probe 2026-04-28).
Pre-2018 HMDA must be downloaded manually from the legacy FFIEC site.

Strategy: stream the per-state CSV endpoint, aggregate to tract-year on the
fly (origination count, denial count, total loan amount, lender diversity,
mean loan size, etc.), and write one small parquet/CSV per year. We never
keep the full LAR on disk — that would be 30–60 GB. Tract-year aggregates
are O(100 MB) for the full 7-year panel.

Endpoint: GET https://ffiec.cfpb.gov/v2/data-browser-api/view/csv
Required: years + (state | county | msamd | lei) + ≥1 HMDA data filter
We use actions_taken=1,2,3,4,5,6,7,8 (all actions) per state per year.

Usage:
    python pull_hmda.py                          # 2018-2024, all states
    python pull_hmda.py --years 2023 2024        # specific years
    python pull_hmda.py --states DC DE           # subset for testing
"""
from __future__ import annotations
import argparse
import csv
import io
import json
import ssl
import sys
import time
import urllib.request
import urllib.parse
from collections import defaultdict
from pathlib import Path

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
REFERER = "https://ffiec.cfpb.gov/data-browser/"

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "raw" / "hmda"

US_STATES = [
    "AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL",
    "IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE",
    "NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD",
    "TN","TX","UT","VT","VA","WA","WV","WI","WY","PR",
]

# action_taken codes per HMDA spec:
#   1=originated, 2=approved-not-accepted, 3=denied,
#   4=withdrawn, 5=incomplete, 6=purchased,
#   7=preapproval-denied, 8=preapproval-approved-not-accepted
ALL_ACTIONS = "1,2,3,4,5,6,7,8"


def stream_state_year(year: int, state: str):
    """Yield dict-rows from the CFPB CSV endpoint, streaming."""
    params = {
        "years": str(year),
        "states": state,
        "actions_taken": ALL_ACTIONS,
    }
    url = f"https://ffiec.cfpb.gov/v2/data-browser-api/view/csv?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": REFERER,
        "Accept": "text/csv",
    })
    with urllib.request.urlopen(req, timeout=120, context=SSL_CTX) as resp:
        # The response is streamed text/csv; wrap it for the csv module
        text_stream = io.TextIOWrapper(resp, encoding="utf-8", errors="replace", newline="")
        reader = csv.DictReader(text_stream)
        for row in reader:
            yield row


def aggregate_state_year(year: int, state: str, out_path: Path) -> dict:
    """Stream LAR, aggregate to tract-year, write CSV. Return summary."""
    if out_path.exists() and out_path.stat().st_size > 0:
        return {"skipped": True, "rows": -1}

    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Per-tract accumulators
    counts = defaultdict(int)            # n applications total
    originated = defaultdict(int)        # action_taken == 1
    denied = defaultdict(int)            # action_taken == 3
    withdrawn = defaultdict(int)         # action_taken == 4
    purchased = defaultdict(int)         # action_taken == 6
    sum_loan = defaultdict(float)        # sum of loan_amount
    n_with_amount = defaultdict(int)
    lenders = defaultdict(set)           # unique LEI per tract
    races = defaultdict(lambda: defaultdict(int))   # by primary race code
    ethnicities = defaultdict(lambda: defaultdict(int))

    rows_seen = 0
    try:
        for row in stream_state_year(year, state):
            tract = row.get("census_tract", "").strip()
            if not tract or tract == "NA":
                continue
            try:
                action = int(row.get("action_taken", "0"))
            except (TypeError, ValueError):
                continue

            counts[tract] += 1
            if action == 1: originated[tract] += 1
            elif action == 3: denied[tract] += 1
            elif action == 4: withdrawn[tract] += 1
            elif action == 6: purchased[tract] += 1

            try:
                amt = float(row.get("loan_amount", "") or 0)
                if amt > 0:
                    sum_loan[tract] += amt
                    n_with_amount[tract] += 1
            except (TypeError, ValueError):
                pass

            lei = (row.get("lei") or "").strip()
            if lei:
                lenders[tract].add(lei)

            race = (row.get("derived_race") or "").strip()
            if race:
                races[tract][race] += 1
            eth = (row.get("derived_ethnicity") or "").strip()
            if eth:
                ethnicities[tract][eth] += 1

            rows_seen += 1
    except Exception as e:
        print(f"    ERR  {year} {state}: {e}", flush=True)
        if rows_seen == 0:
            return {"skipped": False, "rows": 0, "error": str(e)}

    # Write per-tract aggregates
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "year", "state", "tract_fips",
            "n_applications", "n_originated", "n_denied", "n_withdrawn", "n_purchased",
            "approval_rate", "denial_rate",
            "sum_loan_amount", "mean_loan_amount",
            "n_distinct_lenders",
            "n_white", "n_black", "n_asian", "n_hispanic", "n_other_race",
        ])
        for t in sorted(counts):
            n = counts[t]
            ori = originated[t]
            den = denied[t]
            with_amt = n_with_amount[t]
            mean_amt = (sum_loan[t] / with_amt) if with_amt else 0
            decided = ori + den + withdrawn[t]
            ar = (ori / decided) if decided else 0
            dr = (den / decided) if decided else 0
            r = races[t]
            white = r.get("White", 0)
            black = r.get("Black or African American", 0)
            asian = r.get("Asian", 0)
            other_race = sum(v for k, v in r.items() if k not in ("White", "Black or African American", "Asian"))
            hisp = ethnicities[t].get("Hispanic or Latino", 0)
            w.writerow([
                year, state, t,
                n, ori, den, withdrawn[t], purchased[t],
                f"{ar:.4f}", f"{dr:.4f}",
                f"{sum_loan[t]:.0f}", f"{mean_amt:.0f}",
                len(lenders[t]),
                white, black, asian, hisp, other_race,
            ])

    return {"skipped": False, "rows": rows_seen, "tracts": len(counts)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs="*", type=int,
                    default=[2018, 2019, 2020, 2021, 2022, 2023, 2024])
    ap.add_argument("--states", nargs="*", default=US_STATES)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"HMDA tract-aggregate pull → {OUT_DIR}/tract_aggregates_{{year}}/")
    print(f"Years: {args.years}")
    print(f"States: {len(args.states)}")
    print()

    grand = {"rows": 0, "tracts": 0, "skipped": 0, "errors": 0}
    for year in args.years:
        year_dir = OUT_DIR / f"tract_aggregates_{year}"
        year_dir.mkdir(parents=True, exist_ok=True)
        year_total_rows = 0
        year_total_tracts = 0
        t0 = time.time()
        for state in args.states:
            out = year_dir / f"{state}.csv"
            try:
                res = aggregate_state_year(year, state, out)
                if res.get("skipped"):
                    grand["skipped"] += 1
                    print(f"  SKIP  {year} {state}", flush=True)
                    continue
                if "error" in res:
                    grand["errors"] += 1
                    continue
                year_total_rows += res["rows"]
                year_total_tracts += res.get("tracts", 0)
                print(f"  OK    {year} {state}: {res['rows']:>9,} rows → {res.get('tracts', 0):>5,} tracts",
                      flush=True)
                time.sleep(0.05)
            except Exception as e:
                grand["errors"] += 1
                print(f"  ERR   {year} {state}: {e}", flush=True)
        elapsed = time.time() - t0
        print(f"  ── {year}: {year_total_rows:,} rows across {year_total_tracts:,} tracts ({elapsed:.0f}s) ──")
        grand["rows"] += year_total_rows
        grand["tracts"] += year_total_tracts

    print(f"\nGrand total: {grand['rows']:,} LAR rows → {grand['tracts']:,} tract-state-years")
    print(f"Skipped: {grand['skipped']} | Errors: {grand['errors']}")


if __name__ == "__main__":
    main()
