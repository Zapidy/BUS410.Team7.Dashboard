#!/usr/bin/env python3
"""Aggregate SBA 7(a) and 504 loan-level CSVs into ZIP-year features.

SBA loan records carry borrower addresses (street/city/state/zip) but no
tract or county identifier. Geocoding all ~5 M records to tracts via the
Census Geocoder is rate-limited (~10k/day batch). Practical strategy:

  Phase 1 (this script): aggregate to (state, zip5, year). Cheap, accurate
                         at the ZIP level.
  Phase 2 (panel build): apportion ZIP totals to tracts using the HUD
                         ZIP-tract crosswalk (population-weighted). This
                         gives an honest ZIP→tract estimate without
                         geocoding every record.
  Phase 3 (optional):    geocode a sample to validate the apportionment.

Inputs:  data/raw/sba/foia-{7a,504}-*.csv
Output:  data/processed/sba/zip_year.csv
"""
from __future__ import annotations
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "sba"
OUT = ROOT / "data" / "processed" / "sba"


def parse_year(date_str: str) -> int | None:
    """SBA dates are usually YYYY-MM-DD or MM/DD/YYYY."""
    s = (date_str or "").strip()
    if not s:
        return None
    if "-" in s:
        try:
            return int(s.split("-")[0])
        except (ValueError, IndexError):
            return None
    if "/" in s:
        parts = s.split("/")
        if len(parts) == 3 and len(parts[2]) == 4:
            try:
                return int(parts[2])
            except ValueError:
                return None
    return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    # (state, zip5, year) → {n_loans, sum_gross, sum_guaranteed, lenders}
    agg: dict[tuple[str, str, int], dict] = defaultdict(
        lambda: {"n_loans": 0, "n_504": 0, "n_7a": 0,
                 "sum_gross_approval": 0.0, "sum_guaranteed": 0.0,
                 "lenders": set()}
    )

    files = sorted(RAW.glob("foia-*.csv"))
    if not files:
        print(f"No SBA CSVs under {RAW}", file=sys.stderr)
        sys.exit(1)

    for path in files:
        prog = "504" if "504" in path.stem else "7a"
        n_in_file = 0
        with path.open("r", encoding="utf-8", errors="replace") as f:
            r = csv.DictReader(f)
            for row in r:
                state = (row.get("borrstate") or "").strip().upper()
                zipcode = (row.get("borrzip") or "").strip()[:5].zfill(5)
                if not state or not zipcode.isdigit() or len(state) != 2:
                    continue
                year = parse_year(row.get("approvaldate") or row.get("asofdate"))
                if year is None or year < 2009 or year > 2024:
                    continue
                try:
                    gross = float((row.get("grossapproval") or "0").replace(",", "").replace("$", "") or 0)
                except ValueError:
                    gross = 0.0
                try:
                    guar = float((row.get("sbaguaranteedapproval") or "0").replace(",", "").replace("$", "") or 0)
                except ValueError:
                    guar = 0.0
                lender = (row.get("bankname") or row.get("cdc_name") or "").strip()

                key = (state, zipcode, year)
                rec = agg[key]
                rec["n_loans"] += 1
                rec[f"n_{prog}"] += 1
                rec["sum_gross_approval"] += gross
                rec["sum_guaranteed"] += guar
                if lender:
                    rec["lenders"].add(lender)
                n_in_file += 1
        print(f"  {path.name}: {n_in_file:>9,} loans (in 2009–2024 window)")

    # Emit
    rows = []
    for (state, zipcode, year), v in sorted(agg.items()):
        rows.append({
            "state": state,
            "zip5": zipcode,
            "year": year,
            "n_loans": v["n_loans"],
            "n_7a": v["n_7a"],
            "n_504": v["n_504"],
            "sum_gross_approval": f"{v['sum_gross_approval']:.0f}",
            "sum_guaranteed": f"{v['sum_guaranteed']:.0f}",
            "n_distinct_lenders": len(v["lenders"]),
        })
    out_path = OUT / "zip_year.csv"
    if rows:
        with out_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    print(f"\n  → {out_path}  ({len(rows):,} (state, zip, year) rows)")


if __name__ == "__main__":
    main()
