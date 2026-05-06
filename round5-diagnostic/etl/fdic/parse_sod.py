#!/usr/bin/env python3
"""Parse FDIC Summary of Deposits CSVs into county-year branch/concentration features.

Mirrors the logic in `../round4/supply_side_features.py:build_fdic_county_features()`,
but stdlib-only and operates on the per-year CSVs produced by `pull_sod.py`.

Inputs:  data/raw/fdic/sod/sod_{year}.csv   (one row per branch per year)
Output:  data/processed/fdic/county_year.csv
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "fdic" / "sod"
OUT = ROOT / "data" / "processed" / "fdic"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    years_seen = set()

    # county-year aggregates: {(year, county_fips): {cert: deposits_k}}
    bank_deposits: dict[tuple[int, str], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    branch_count: dict[tuple[int, str], int] = defaultdict(int)
    total_dep: dict[tuple[int, str], float] = defaultdict(float)

    files = sorted(RAW.glob("sod_*.csv"))
    if not files:
        print(f"No SoD CSVs under {RAW}", file=sys.stderr)
        sys.exit(1)

    for path in files:
        year = int(path.stem.replace("sod_", ""))
        years_seen.add(year)
        with path.open("r", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                stcnty = (row.get("STCNTYBR") or "").strip().zfill(5)
                if not stcnty.isdigit() or len(stcnty) != 5:
                    continue
                cert = (row.get("CERT") or "").strip()
                if not cert:
                    continue
                try:
                    dep = float(row.get("DEPSUMBR") or 0)
                except ValueError:
                    dep = 0.0
                key = (year, stcnty)
                bank_deposits[key][cert] += dep
                branch_count[key] += 1
                total_dep[key] += dep
        print(f"  {year}: {sum(branch_count.get((year, k), 0) for k in {k for (_, k), _ in branch_count.items() if _ == year} or set()):>6}", flush=True)

    # Build county-year output rows
    print("\nBuilding county-year features…", flush=True)
    rows = []
    for (year, county) in sorted(bank_deposits):
        per_bank = bank_deposits[(year, county)]
        n_branches = branch_count[(year, county)]
        n_banks = len(per_bank)
        total = total_dep[(year, county)]
        avg_branch = (total / n_branches) if n_branches else 0
        if total > 0:
            shares = [v / total for v in per_bank.values()]
            hhi = sum(s * s for s in shares)
            top_share = max(shares)
        else:
            hhi = 0.0
            top_share = 0.0
        rows.append({
            "year": year,
            "county_fips": county,
            "fdic_branch_count": n_branches,
            "fdic_bank_count": n_banks,
            "fdic_total_branch_deposits_k": f"{total:.0f}",
            "fdic_avg_branch_deposits_k": f"{avg_branch:.2f}",
            "fdic_deposit_hhi": f"{hhi:.6f}",
            "fdic_top_bank_share": f"{top_share:.6f}",
        })

    # Year-over-year deltas (1yr + 3yr)
    print("Computing deltas…", flush=True)
    by_county: dict[str, dict[int, dict]] = defaultdict(dict)
    for r in rows:
        by_county[r["county_fips"]][r["year"]] = r
    for county, by_year in by_county.items():
        ys = sorted(by_year)
        for y in ys:
            cur = by_year[y]
            prev1 = by_year.get(y - 1)
            prev3 = by_year.get(y - 3)
            for col in ("fdic_branch_count", "fdic_bank_count",
                        "fdic_total_branch_deposits_k",
                        "fdic_avg_branch_deposits_k",
                        "fdic_deposit_hhi", "fdic_top_bank_share"):
                cv = float(cur[col]) if cur[col] != "" else None
                p1 = float(prev1[col]) if prev1 else None
                p3 = float(prev3[col]) if prev3 else None
                cur[f"{col}_chg1yr"] = (f"{cv-p1:.4f}" if cv is not None and p1 is not None else "")
                cur[f"{col}_chg3yr"] = (f"{cv-p3:.4f}" if cv is not None and p3 is not None else "")
            # pct changes for total deposits
            cv = float(cur["fdic_total_branch_deposits_k"])
            p1d = float(prev1["fdic_total_branch_deposits_k"]) if prev1 else None
            p3d = float(prev3["fdic_total_branch_deposits_k"]) if prev3 else None
            cur["fdic_total_branch_deposits_k_pctchg1yr"] = (
                f"{(cv-p1d)/p1d*100:.4f}" if p1d not in (None, 0) else ""
            )
            cur["fdic_total_branch_deposits_k_pctchg3yr"] = (
                f"{(cv-p3d)/p3d*100:.4f}" if p3d not in (None, 0) else ""
            )

    # Flatten back
    out_rows = sorted(rows, key=lambda r: (r["county_fips"], r["year"]))
    fieldnames = list(out_rows[0].keys())
    out_path = OUT / "county_year.csv"
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)
    print(f"  → {out_path}  ({len(out_rows):,} rows across {len(by_county):,} counties × {len(years_seen)} years)")


if __name__ == "__main__":
    main()
