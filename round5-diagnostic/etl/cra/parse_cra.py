#!/usr/bin/env python3
"""Parse FFIEC CRA disclosure flat files into tract-year and county-year features.

Adapted from `../round4/supply_side_features.py` (which parses D6 + D1-1/D1-2 records),
but stdlib-only — no pandas dependency. Outputs CSVs into `data/processed/cra/`.

Inputs (per year, under `data/raw/cra/{year}/{kind}/`):
    - discl/  : Disclosure series .dat files (D6 = tract-level lender presence,
                D1-1 / D1-2 = county-level lender loan totals by income-tract)
    - aggr/   : Aggregate files (not used by this script — sanity-check only)
    - trans/  : Transmittal sheet (lender list per year — used for stable-reporter cohort)

Outputs (under `data/processed/cra/`):
    - tract_year.csv  : (tract_fips, county_fips, year, n_cra_lenders,
                         entries/exits/churn at 1yr + 3yr, presence ratio)
    - county_year.csv : (county_fips, year, lender_count, total_loan_count,
                         total_loan_amount_k, count_hhi, amount_hhi, top_share_*)
    - reporters.csv   : (respondent_id, agency_code, year, bank_name) — the
                         union of all transmittal-listed reporters per year
    - stable_reporters.csv : subset that appears in EVERY year of the panel
                         (used to fix the survivor-bias issue described in
                         notes/00_methodology.md §2.6)

Usage:
    python parse_cra.py                  # process all years found
    python parse_cra.py --years 2009 2010
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

# --- Spec slices (1-indexed in PDF, 0-indexed here) ----------------------------
# D6 record (small-business loans summarized by tract income)
D6_SLICES = {
    "table_id":      slice(0, 5),
    "respondent_id": slice(5, 15),
    "agency_code":   slice(15, 16),
    "activity_year": slice(16, 20),
    "state":         slice(20, 22),
    "county":        slice(22, 25),
    "census_tract":  slice(30, 37),
    "loan_indicator": slice(47, 48),
}

# D1-1 / D1-2 record (county-level small business by lender)
D1_SLICES = {
    "table_id":      slice(0, 5),
    "respondent_id": slice(5, 15),
    "agency_code":   slice(15, 16),
    "activity_year": slice(16, 20),
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

# Transmittal record (one per reporter per year)
# Field positions per FFIEC CRA Transmittal Sheet specification.
TRANS_SLICES = {
    "respondent_id": slice(0, 10),
    "agency_code":   slice(10, 11),
    "activity_year": slice(11, 15),
    "name":          slice(15, 45),
    "street":        slice(45, 85),
    "city":          slice(85, 110),
    "state":         slice(110, 112),
    "zip":           slice(112, 122),
}

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "cra"
OUT = ROOT / "data" / "processed" / "cra"


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


def discover(years: list[int] | None = None) -> dict[int, dict[str, list[Path]]]:
    """Return {year: {'discl': [...], 'trans': [...], 'aggr': [...]}}."""
    out: dict[int, dict[str, list[Path]]] = defaultdict(lambda: {"discl": [], "trans": [], "aggr": []})
    if not RAW.exists():
        return out
    for year_dir in sorted(RAW.iterdir()):
        if not year_dir.is_dir():
            continue
        try:
            year = int(year_dir.name)
        except ValueError:
            continue
        if years and year not in years:
            continue
        for kind in ("discl", "trans", "aggr"):
            kdir = year_dir / kind
            if kdir.exists():
                out[year][kind].extend(sorted(p for p in kdir.iterdir() if p.is_file() and p.suffix.lower() in {".dat", ".txt"}))
    return out


def parse_disclosure(year: int, files: list[Path]) -> tuple[dict, dict]:
    """Return (tract_lenders, county_lender_loans) for this year.

    tract_lenders[(tract_fips, county_fips)] = set(lender_id) — D6 lender presence
    county_lender_loans[(county_fips, lender_id)] = (count, amount_k) — D1 totals
    """
    tract_lenders: dict[tuple[str, str], set[str]] = {}
    county_lender_loans: dict[tuple[str, str], list[float]] = {}

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
                key = (f"{state}{county}{tract}", f"{state}{county}")
                tract_lenders.setdefault(key, set()).add(lender)
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
                cnt = (
                    to_int(line[D1_SLICES["count_lt_100"]])
                    + to_int(line[D1_SLICES["count_100_250"]])
                    + to_int(line[D1_SLICES["count_250_1m"]])
                )
                amt = (
                    to_float(line[D1_SLICES["amount_lt_100"]])
                    + to_float(line[D1_SLICES["amount_100_250"]])
                    + to_float(line[D1_SLICES["amount_250_1m"]])
                )
                key = (f"{state}{county}", lender)
                rec = county_lender_loans.setdefault(key, [0.0, 0.0])
                rec[0] += cnt
                rec[1] += amt
    return tract_lenders, county_lender_loans


def parse_transmittal(year: int, files: list[Path]) -> list[dict]:
    """Return list of reporter records for this year."""
    out = []
    for path in files:
        for line in iter_lines(path):
            if len(line) < 122:
                continue
            try:
                rid = line[TRANS_SLICES["respondent_id"]].strip()
                agency = line[TRANS_SLICES["agency_code"]].strip()
                yr_str = line[TRANS_SLICES["activity_year"]].strip()
                if not rid or not agency or len(yr_str) != 4:
                    continue
                out.append({
                    "respondent_id": rid,
                    "agency_code": agency,
                    "activity_year": int(yr_str),
                    "lender_id": f"{agency}_{rid}",
                    "name": line[TRANS_SLICES["name"]].strip(),
                    "city": line[TRANS_SLICES["city"]].strip(),
                    "state": line[TRANS_SLICES["state"]].strip(),
                })
            except Exception:
                continue
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs="*", type=int, default=None)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)

    inventory = discover(args.years)
    if not inventory:
        print(f"No CRA data found under {RAW}", file=sys.stderr)
        sys.exit(1)

    print(f"Years to process: {sorted(inventory)}", flush=True)

    # Per-year tract-lender memory (for entries/exits across years)
    year_tract_lenders: dict[int, dict[tuple[str, str], set[str]]] = {}
    year_county_lender_loans: dict[int, dict[tuple[str, str], list[float]]] = {}
    all_reporters: list[dict] = []

    for year in sorted(inventory):
        files = inventory[year]
        t0 = time.time()
        tract_lenders, county_loans = parse_disclosure(year, files["discl"])
        reporters = parse_transmittal(year, files["trans"])
        elapsed = time.time() - t0
        print(
            f"  {year}  discl={sum(len(v) for v in tract_lenders.values()):>9,} lender×tract  "
            f"county_lender×year={len(county_loans):>7,}  "
            f"reporters={len(reporters):>5,}  ({elapsed:.1f}s)",
            flush=True,
        )
        year_tract_lenders[year] = tract_lenders
        year_county_lender_loans[year] = county_loans
        all_reporters.extend(reporters)

    # ---------- Build tract-year features (with churn across years) ----------
    print("\nBuilding tract-year features…", flush=True)
    tract_rows: list[dict] = []
    # Index: tract_fips → {year: set(lender)}
    tract_history: dict[str, dict[int, set[str]]] = defaultdict(dict)
    tract_county: dict[str, str] = {}
    for year, lenders in year_tract_lenders.items():
        for (tract_fips, county_fips), s in lenders.items():
            tract_history[tract_fips][year] = s
            tract_county[tract_fips] = county_fips

    for tract, by_year in tract_history.items():
        for year, current in sorted(by_year.items()):
            prev1 = by_year.get(year - 1, set())
            prev3 = by_year.get(year - 3, set())
            tract_rows.append({
                "tract_fips": tract,
                "county_fips": tract_county[tract],
                "year": year,
                "n_cra_lenders": len(current),
                "cra_lender_entries_1yr": len(current - prev1),
                "cra_lender_exits_1yr": len(prev1 - current),
                "cra_lender_entries_3yr": len(current - prev3),
                "cra_lender_exits_3yr": len(prev3 - current),
                "cra_lender_churn_1yr": len(current ^ prev1),
                "cra_lender_churn_3yr": len(current ^ prev3),
                "cra_lender_presence_ratio_1yr": (
                    f"{len(current & prev1) / len(prev1):.4f}" if prev1 else ""
                ),
            })

    write_csv(OUT / "tract_year.csv", tract_rows, sort_by=("tract_fips", "year"))
    print(f"  → {OUT/'tract_year.csv'}  ({len(tract_rows):,} rows)", flush=True)

    # ---------- Build county-year features (HHI, top share) ----------
    print("Building county-year features…", flush=True)
    county_rows: list[dict] = []
    for year, loans in year_county_lender_loans.items():
        # Aggregate by county
        county_lenders: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
        for (county, lender_id), (cnt, amt) in loans.items():
            county_lenders[county].append((lender_id, cnt, amt))
        for county, records in county_lenders.items():
            total_count = sum(c for _, c, _ in records)
            total_amount = sum(a for _, _, a in records)
            n_lenders = len(records)
            if total_count > 0:
                count_shares = [c / total_count for _, c, _ in records]
                count_hhi = sum(s * s for s in count_shares)
                top_count = max(count_shares)
            else:
                count_hhi = 0.0; top_count = 0.0
            if total_amount > 0:
                amount_shares = [a / total_amount for _, _, a in records]
                amount_hhi = sum(s * s for s in amount_shares)
                top_amount = max(amount_shares)
            else:
                amount_hhi = 0.0; top_amount = 0.0
            county_rows.append({
                "county_fips": county,
                "year": year,
                "cra_county_lender_count": n_lenders,
                "cra_county_total_loan_count": total_count,
                "cra_county_total_loan_amount_k": f"{total_amount:.0f}",
                "cra_county_count_hhi": f"{count_hhi:.6f}",
                "cra_county_amount_hhi": f"{amount_hhi:.6f}",
                "cra_county_top_lender_share_count": f"{top_count:.6f}",
                "cra_county_top_lender_share_amount": f"{top_amount:.6f}",
            })
    write_csv(OUT / "county_year.csv", county_rows, sort_by=("county_fips", "year"))
    print(f"  → {OUT/'county_year.csv'}  ({len(county_rows):,} rows)", flush=True)

    # ---------- Reporters list + stable-reporter cohort ----------
    print("Building reporter list + stable-reporter cohort…", flush=True)
    write_csv(OUT / "reporters.csv", all_reporters, sort_by=("activity_year", "lender_id"))
    print(f"  → {OUT/'reporters.csv'}  ({len(all_reporters):,} rows)", flush=True)

    # Stable reporters = lenders present in EVERY year of the panel
    by_lender_years: dict[str, set[int]] = defaultdict(set)
    for r in all_reporters:
        by_lender_years[r["lender_id"]].add(r["activity_year"])
    panel_years = set(inventory)
    stable = [
        {"lender_id": lid, "n_years_reporting": len(yrs)}
        for lid, yrs in by_lender_years.items()
        if yrs == panel_years
    ]
    write_csv(OUT / "stable_reporters.csv", stable, sort_by=("lender_id",))
    print(f"  → {OUT/'stable_reporters.csv'}  ({len(stable):,} stable reporters out of {len(by_lender_years):,} ever-seen)",
          flush=True)


def write_csv(path: Path, rows: list[dict], sort_by: tuple[str, ...] = ()):
    if not rows:
        path.write_text("")
        return
    if sort_by:
        rows = sorted(rows, key=lambda r: tuple(r.get(k, "") for k in sort_by))
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
