#!/usr/bin/env python3
"""Pivot Census ACS 5-year tract JSON files into a single tract-year CSV.

Input:  data/raw/acs/acs5_{vintage}/state_{ss}.json   (one file per state-vintage,
        produced by pull_acs.py; first inner array is the header)
Output: data/processed/acs/tract_year.csv

ACS vintage labeling: a vintage labeled `2022` covers years 2018–2022 (5-year ACS).
For Round-5 we treat each vintage's reference year as its end-year (the most recent
year of data inside the vintage). The lag-aware feature build will assign vintages
to forecast years using the rule: feature_vintage_end_year < prediction_year.
"""
from __future__ import annotations
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "acs"
OUT = ROOT / "data" / "processed" / "acs"

# Variable name → output column. Keep consistent across vintages.
RENAME = {
    "B01003_001E": "population",
    "B19013_001E": "median_hh_income",
    "B17001_001E": "poverty_universe",
    "B17001_002E": "below_poverty",
    "B02001_001E": "race_universe",
    "B02001_002E": "n_white",
    "B02001_003E": "n_black",
    "B03003_003E": "n_hispanic",
    "B25001_001E": "housing_units",
    "B25002_003E": "n_vacant",
    "B23025_002E": "labor_force",
    "B23025_005E": "n_unemployed",
    "B15003_022E": "n_bachelors",
    "B15003_023E": "n_masters",
    "B15003_024E": "n_professional",
    "B15003_025E": "n_doctorate",
    "B15003_001E": "edu_universe",
}


def to_num(s):
    """ACS uses -666666666 etc. as null sentinels; convert to ''."""
    if s is None or s == "" or str(s).startswith("-66666"):
        return ""
    try:
        x = float(s)
        return str(int(x)) if x.is_integer() else f"{x:.4f}"
    except (TypeError, ValueError):
        return ""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    out_rows = []
    vintages = sorted(d.name for d in RAW.iterdir() if d.is_dir() and d.name.startswith("acs5_"))
    if not vintages:
        print(f"No ACS vintages under {RAW}", file=sys.stderr)
        sys.exit(1)

    for v in vintages:
        try:
            vintage_year = int(v.split("_")[1])
        except (IndexError, ValueError):
            continue
        v_dir = RAW / v
        states = sorted(v_dir.glob("state_*.json"))
        n_tracts = 0
        for sf in states:
            try:
                data = json.loads(sf.read_text())
            except Exception as e:
                print(f"  WARN  {sf}: {e}", file=sys.stderr)
                continue
            if not data or len(data) < 2:
                continue
            header = data[0]
            for row in data[1:]:
                rec = dict(zip(header, row))
                state = rec.get("state", "").zfill(2)
                county = rec.get("county", "").zfill(3)
                tract = rec.get("tract", "").zfill(6)
                tract_fips = state + county + tract
                if len(tract_fips) != 11 or not tract_fips.isdigit():
                    continue
                out = {"tract_fips": tract_fips, "vintage": vintage_year}
                # Compute derived fractions inline
                pop = to_num(rec.get("B01003_001E"))
                pov_u = to_num(rec.get("B17001_001E"))
                pov   = to_num(rec.get("B17001_002E"))
                race_u = to_num(rec.get("B02001_001E"))
                white  = to_num(rec.get("B02001_002E"))
                black  = to_num(rec.get("B02001_003E"))
                hisp   = to_num(rec.get("B03003_003E"))
                hu     = to_num(rec.get("B25001_001E"))
                vac    = to_num(rec.get("B25002_003E"))
                lf     = to_num(rec.get("B23025_002E"))
                unemp  = to_num(rec.get("B23025_005E"))
                edu_u  = to_num(rec.get("B15003_001E"))
                ba     = to_num(rec.get("B15003_022E"))
                ma     = to_num(rec.get("B15003_023E"))
                pro    = to_num(rec.get("B15003_024E"))
                doc    = to_num(rec.get("B15003_025E"))
                inc    = to_num(rec.get("B19013_001E"))

                out["population"] = pop
                out["median_hh_income"] = inc
                out["pct_poverty"] = (
                    f"{(float(pov)/float(pov_u)*100):.2f}"
                    if pov and pov_u and float(pov_u) > 0 else ""
                )
                out["pct_minority"] = (
                    f"{(1 - float(white)/float(race_u)) * 100:.2f}"
                    if white and race_u and float(race_u) > 0 else ""
                )
                out["pct_black"] = (
                    f"{(float(black)/float(race_u)*100):.2f}"
                    if black and race_u and float(race_u) > 0 else ""
                )
                out["pct_hispanic"] = (
                    f"{(float(hisp)/float(race_u)*100):.2f}"
                    if hisp and race_u and float(race_u) > 0 else ""
                )
                out["housing_units"] = hu
                out["pct_vacant"] = (
                    f"{(float(vac)/float(hu)*100):.2f}"
                    if vac and hu and float(hu) > 0 else ""
                )
                out["unemployment_rate"] = (
                    f"{(float(unemp)/float(lf)*100):.2f}"
                    if unemp and lf and float(lf) > 0 else ""
                )
                ba_total = sum(float(x) for x in (ba, ma, pro, doc) if x)
                out["pct_bachelor_plus"] = (
                    f"{(ba_total/float(edu_u)*100):.2f}"
                    if ba_total and edu_u and float(edu_u) > 0 else ""
                )
                out_rows.append(out)
                n_tracts += 1
        print(f"  {v}: {n_tracts:>6,} tracts × 1 vintage", flush=True)

    if not out_rows:
        print("No rows produced", file=sys.stderr)
        sys.exit(1)

    out_rows.sort(key=lambda r: (r["tract_fips"], r["vintage"]))
    fieldnames = list(out_rows[0].keys())
    out_path = OUT / "tract_year.csv"
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)
    print(f"  → {out_path}  ({len(out_rows):,} rows)")


if __name__ == "__main__":
    main()
