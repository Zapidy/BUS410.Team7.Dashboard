#!/usr/bin/env python3
"""Parse CRA flat files into tract×lender×year apportioned loan totals + size buckets.

Round 5's parser produces tract-year aggregates (n_cra_lenders + churn) and
county-year HHI. Round 7 needs **tract×lender** apportioned amounts so that
tract-level concentration features (top1, top3, HHI) and lender-mix features
(community-bank share, top-4 share, credit-union share, loans under $100k)
can be computed.

Apportionment rule (matches round4 conventions):
    For each (county, lender, year):
        - D1 records give county totals: count_lt_100, count_100_250, count_250_1m,
          and matching dollar amounts.
        - D6 records flag tract presence: which tracts of that county had loans
          from that lender that year.
    Equal-share apportionment: each lender's county totals are divided equally
    across the tracts where that lender appears in D6.

That gives, per (tract, lender, year):
    - apportioned count and amount overall
    - apportioned counts/amounts per size bucket (<100k, 100k-250k, 250k-1m)

Inputs:
    ../round5/data/raw/cra/{year}/{discl,trans}/*.dat

Outputs:
    data/processed/cra/tract_lender_year.csv
        (tract_fips, county_fips, lender_id, year,
         n_loans, amount_k, count_lt_100, amount_lt_100,
         count_100_250, amount_100_250, count_250_1m, amount_250_1m)

Notes:
    - lender_id = "{agency_code}_{respondent_id}" (matches round5 reporters.csv)
    - Equal apportionment is coarse but reproducible and consistent with round4.
    - Output is large (~30M rows over 16 years). Consider parquet for downstream
      consumers; CSV used here for inspectability.

Usage:
    python3 parse_cra_round7.py                  # all years 2009-2024
    python3 parse_cra_round7.py --years 2020 2021
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUND5_RAW = ROOT.parent / "round5" / "data" / "raw" / "cra"
OUT = ROOT / "data" / "processed" / "cra"

# Field slices (mirror round5/etl/cra/parse_cra.py)
D6_SLICES = {
    "respondent_id": slice(5, 15),
    "agency_code":   slice(15, 16),
    "state":         slice(20, 22),
    "county":        slice(22, 25),
    "census_tract":  slice(30, 37),
    "loan_indicator": slice(47, 48),
}

D1_SLICES = {
    "respondent_id": slice(5, 15),
    "agency_code":   slice(15, 16),
    "state":         slice(22, 24),
    "county":        slice(24, 27),
    "report_level":  slice(42, 45),
    "count_lt_100":  slice(45, 55),
    "amount_lt_100": slice(55, 65),
    "count_100_250": slice(65, 75),
    "amount_100_250": slice(75, 85),
    "count_250_1m":  slice(85, 95),
    "amount_250_1m": slice(95, 105),
}


def to_int(s: str) -> int:
    s = (s or "").strip()
    return int(s) if s and s.lstrip("-").isdigit() else 0


def to_float(s: str) -> float:
    s = (s or "").strip()
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


def normalize_tract(raw: str) -> str | None:
    t = (raw or "").strip().replace(".", "").replace(" ", "")
    if not t or t.upper() == "NA":
        return None
    t = t.zfill(6)
    return t if t.isdigit() and len(t) == 6 else None


def iter_lines(path: Path):
    with path.open("r", encoding="latin-1", errors="ignore") as f:
        for line in f:
            yield line.rstrip("\r\n")


def discover(years: list[int] | None = None) -> dict[int, list[Path]]:
    out: dict[int, list[Path]] = defaultdict(list)
    for year_dir in sorted(ROUND5_RAW.iterdir()):
        if not year_dir.is_dir():
            continue
        try:
            year = int(year_dir.name)
        except ValueError:
            continue
        if years and year not in years:
            continue
        discl = year_dir / "discl"
        if discl.exists():
            out[year] = sorted(p for p in discl.iterdir() if p.suffix.lower() in {".dat", ".txt"})
    return out


def parse_year(year: int, files: list[Path]):
    """Return (tract_lender_presence, county_lender_buckets).

    tract_lender_presence: {(county_fips, lender_id): set(tract_fips)}
    county_lender_buckets: {(county_fips, lender_id): dict of bucket totals}
    """
    tract_lender_presence: dict[tuple[str, str], set[str]] = defaultdict(set)
    county_lender_buckets: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {
            "count_lt_100": 0, "amount_lt_100": 0.0,
            "count_100_250": 0, "amount_100_250": 0.0,
            "count_250_1m": 0, "amount_250_1m": 0.0,
        }
    )

    for path in files:
        for line in iter_lines(path):
            if line.startswith("D6-0") and len(line) >= 48:
                state = line[D6_SLICES["state"]].strip()
                county = line[D6_SLICES["county"]].strip()
                tract = normalize_tract(line[D6_SLICES["census_tract"]])
                ind = line[D6_SLICES["loan_indicator"]].strip().upper()
                if not state or not county or tract is None or ind != "Y":
                    continue
                lender = (
                    line[D6_SLICES["agency_code"]].strip()
                    + "_"
                    + line[D6_SLICES["respondent_id"]].strip()
                )
                county_fips = f"{state}{county}"
                tract_fips = f"{state}{county}{tract}"
                tract_lender_presence[(county_fips, lender)].add(tract_fips)
            elif (line.startswith("D1-1") or line.startswith("D1-2")) and len(line) >= 145:
                state = line[D1_SLICES["state"]].strip()
                county = line[D1_SLICES["county"]].strip()
                rl = to_int(line[D1_SLICES["report_level"]])
                if not state or not county or rl != 40:
                    continue
                lender = (
                    line[D1_SLICES["agency_code"]].strip()
                    + "_"
                    + line[D1_SLICES["respondent_id"]].strip()
                )
                county_fips = f"{state}{county}"
                rec = county_lender_buckets[(county_fips, lender)]
                rec["count_lt_100"] += to_int(line[D1_SLICES["count_lt_100"]])
                rec["amount_lt_100"] += to_float(line[D1_SLICES["amount_lt_100"]])
                rec["count_100_250"] += to_int(line[D1_SLICES["count_100_250"]])
                rec["amount_100_250"] += to_float(line[D1_SLICES["amount_100_250"]])
                rec["count_250_1m"] += to_int(line[D1_SLICES["count_250_1m"]])
                rec["amount_250_1m"] += to_float(line[D1_SLICES["amount_250_1m"]])

    return tract_lender_presence, county_lender_buckets


def apportion(year: int, presence, buckets) -> list[dict]:
    """Equal-share apportion county-lender bucket totals across tracts where the
    lender is present in that county (per D6)."""
    rows = []
    for key, tracts in presence.items():
        county_fips, lender_id = key
        bucket = buckets.get(key)
        n_tracts = len(tracts)
        if n_tracts == 0:
            continue
        if bucket is None:
            # Lender appeared in D6 (tract presence) but not D1 — treat as zero amounts.
            bucket = {
                "count_lt_100": 0, "amount_lt_100": 0.0,
                "count_100_250": 0, "amount_100_250": 0.0,
                "count_250_1m": 0, "amount_250_1m": 0.0,
            }
        # Equal apportionment
        frac = 1.0 / n_tracts
        for tract in tracts:
            n_loans = (bucket["count_lt_100"] + bucket["count_100_250"] + bucket["count_250_1m"]) * frac
            amount_k = (bucket["amount_lt_100"] + bucket["amount_100_250"] + bucket["amount_250_1m"]) * frac
            rows.append({
                "tract_fips": tract,
                "county_fips": county_fips,
                "lender_id": lender_id,
                "year": year,
                "n_loans": round(n_loans, 4),
                "amount_k": round(amount_k, 2),
                "count_lt_100": round(bucket["count_lt_100"] * frac, 4),
                "amount_lt_100": round(bucket["amount_lt_100"] * frac, 2),
                "count_100_250": round(bucket["count_100_250"] * frac, 4),
                "amount_100_250": round(bucket["amount_100_250"] * frac, 2),
                "count_250_1m": round(bucket["count_250_1m"] * frac, 4),
                "amount_250_1m": round(bucket["amount_250_1m"] * frac, 2),
            })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs="*", type=int, default=None)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    inventory = discover(args.years)
    if not inventory:
        print(f"No CRA data under {ROUND5_RAW}", file=sys.stderr)
        sys.exit(1)

    print(f"Years: {sorted(inventory)}", flush=True)

    out_path = OUT / "tract_lender_year.csv"
    fieldnames = [
        "tract_fips", "county_fips", "lender_id", "year",
        "n_loans", "amount_k",
        "count_lt_100", "amount_lt_100",
        "count_100_250", "amount_100_250",
        "count_250_1m", "amount_250_1m",
    ]

    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for year in sorted(inventory):
            t0 = time.time()
            presence, buckets = parse_year(year, inventory[year])
            rows = apportion(year, presence, buckets)
            rows.sort(key=lambda r: (r["tract_fips"], r["lender_id"]))
            w.writerows(rows)
            print(
                f"  {year}  rows={len(rows):>9,}  "
                f"county-lender pairs={len(presence):>7,}  "
                f"({time.time() - t0:.1f}s)",
                flush=True,
            )

    print(f"\n→ {out_path}", flush=True)


if __name__ == "__main__":
    main()
