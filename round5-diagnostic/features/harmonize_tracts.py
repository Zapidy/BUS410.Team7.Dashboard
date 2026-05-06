#!/usr/bin/env python3
"""Harmonize all tract data onto the 2020 vintage.

Census tracts re-draw at each decennial census. The same 11-digit FIPS code
can mean different polygons across vintages. About 5% of tracts split, merge,
or renumber per decade.

In our panel:
  CRA 2009-2011 source files: likely 2000-vintage tract codes
  CRA 2012-2021 source files: 2010-vintage
  CRA 2022-2024 source files: 2020-vintage
  ACS 2010-2013 vintages:     2000-vintage data with mixed coding
  ACS 2015-2022 vintages:     2010-vintage and later 2020-vintage

This module builds two lookup tables from the Census Bureau relationship files
and applies them to the per-source processed CSVs:

  xwalk_00_to_10[tract_2000]  -> [(tract_2010, weight), ...]    (population-weighted)
  xwalk_10_to_20[tract_2010]  -> [(tract_2020, weight), ...]    (land-area-weighted; no pop in modern file)

Composition (xwalk_00_to_20) chains them through.

Application policy:
  - For tract codes that exist in the 2020 vintage tract list, identity (no change).
  - For tract codes that DON'T exist in 2020 but exist in the 2010 vintage,
    apply 10→20 mapping; aggregate any features for the source tract into
    each target tract by weight.
  - For tract codes that don't exist in 2020 OR 2010, try the 00→20 chain.
  - For codes still unmatched, leave as-is and flag.

For COUNT features (population, n_lenders, n_originated, etc.) we apportion proportionally:
    target_value = sum over source overlaps of (source_value * weight)
For RATE features (pct_poverty, denial_rate, etc.) we weight-average using the source population.

Inputs:
    data/raw/census-geo/tract_xwalk_2000_2010.txt   30 cols, comma-delimited, no header
    data/raw/census-geo/tract_xwalk_2010_2020.txt   16 cols, pipe-delimited, has header

Outputs:
    data/processed/cra/tract_year_h2020.csv
    data/processed/acs/tract_year_h2020.csv
    data/processed/crosswalk/xwalk_to_2020.csv         (the unified lookup, debuggable)
    data/processed/crosswalk/_harmonization_log.txt
"""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import csv
import sys

ROOT = Path(__file__).resolve().parents[1]
GEO_DIR = ROOT / "data" / "raw" / "census-geo"
PROC = ROOT / "data" / "processed"
OUT = PROC / "crosswalk"
OUT.mkdir(parents=True, exist_ok=True)

LOG: list[str] = []


def log(msg: str):
    print(msg, flush=True)
    LOG.append(msg)


# 2000 → 2010 crosswalk schema (positional, comma-delimited, no header)
# Per Census Bureau docs:
# 0=STATE00 1=COUNTY00 2=TRACT00 3=GEOID00 4=POP00 5=HU00 6=PART 7=AREA00 8=AREALAND00
# 9=STATE10 10=COUNTY10 11=TRACT10 12=GEOID10 13=POP10 14=HU10 15=PART 16=AREA10 17=AREALAND10
# 18=AREALAND_INT 19=AREALAND_PART
# 20=AREAPCT00PT 21=AREAPCT10PT 22=AREALANDPCT00PT 23=AREALANDPCT10PT
# 24=POP10_PART 25=POPPCT00 26=POPPCT10
# 27=HU10_PART 28=HUPCT00 29=HUPCT10
def load_xwalk_00_to_10() -> dict[str, list[tuple[str, float]]]:
    f = GEO_DIR / "tract_xwalk_2000_2010.txt"
    out: dict[str, list[tuple[str, float]]] = defaultdict(list)
    n = 0
    with f.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.strip().split(",")
            if len(parts) < 27:
                continue
            try:
                src = parts[3].strip().zfill(11)
                dst = parts[12].strip().zfill(11)
                if not src.isdigit() or not dst.isdigit() or len(src) != 11 or len(dst) != 11:
                    continue
                weight = float(parts[25]) / 100.0   # POPPCT00 = % of source pop that landed in this target
            except (ValueError, IndexError):
                continue
            if weight > 0:
                out[src].append((dst, weight))
            n += 1
    log(f"  Loaded {n:,} 2000→2010 pairs covering {len(out):,} unique 2000-vintage tracts")
    return dict(out)


# 2010 → 2020 crosswalk schema (pipe-delimited, has header):
# OID_TRACT_20 | GEOID_TRACT_20 | NAMELSAD_TRACT_20 | AREALAND_TRACT_20 | AREAWATER_TRACT_20
# | MTFCC_TRACT_20 | FUNCSTAT_TRACT_20 | OID_TRACT_10 | GEOID_TRACT_10 | NAMELSAD_TRACT_10
# | AREALAND_TRACT_10 | AREAWATER_TRACT_10 | MTFCC_TRACT_10 | FUNCSTAT_TRACT_10
# | AREALAND_PART | AREAWATER_PART
def load_xwalk_10_to_20() -> dict[str, list[tuple[str, float]]]:
    f = GEO_DIR / "tract_xwalk_2010_2020.txt"
    out: dict[str, list[tuple[str, float]]] = defaultdict(list)
    n = 0
    with f.open("r", encoding="utf-8", errors="replace") as fh:
        header = fh.readline()  # skip BOM-prefixed header
        for line in fh:
            parts = line.strip().split("|")
            if len(parts) < 16:
                continue
            try:
                tract_20 = parts[1].strip().zfill(11)
                tract_10 = parts[8].strip().zfill(11)
                area_part = float(parts[14])
                area_total_10 = float(parts[10])
                if not tract_10.isdigit() or not tract_20.isdigit():
                    continue
                if area_total_10 <= 0:
                    continue
                weight = area_part / area_total_10
            except (ValueError, IndexError):
                continue
            if weight > 0:
                out[tract_10].append((tract_20, weight))
            n += 1
    log(f"  Loaded {n:,} 2010→2020 pairs covering {len(out):,} unique 2010-vintage tracts")
    return dict(out)


def compose_00_to_20(
    xwalk_00_to_10: dict[str, list[tuple[str, float]]],
    xwalk_10_to_20: dict[str, list[tuple[str, float]]],
) -> dict[str, list[tuple[str, float]]]:
    """Multiply through: 2000 → 2010 → 2020."""
    out: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for src_2000, mids in xwalk_00_to_10.items():
        accum: dict[str, float] = defaultdict(float)
        for mid_2010, w1 in mids:
            for dst_2020, w2 in xwalk_10_to_20.get(mid_2010, [(mid_2010, 1.0)]):
                accum[dst_2020] += w1 * w2
        out[src_2000] = sorted(accum.items(), key=lambda x: -x[1])
    log(f"  Composed 2000→2020 covering {len(out):,} unique 2000-vintage tracts")
    return dict(out)


def normalize(weighted: list[tuple[str, float]]) -> list[tuple[str, float]]:
    total = sum(w for _, w in weighted)
    if total <= 0:
        return weighted
    return [(t, w / total) for t, w in weighted]


def build_unified_xwalk(
    xwalk_00_to_10: dict[str, list[tuple[str, float]]],
    xwalk_10_to_20: dict[str, list[tuple[str, float]]],
    xwalk_00_to_20: dict[str, list[tuple[str, float]]],
) -> dict[str, list[tuple[str, float]]]:
    """For ANY source tract, return its 2020-vintage destination(s) with weights.

    Tries 2010→2020 first (most common), then 2000→2020, finally identity.
    """
    unified: dict[str, list[tuple[str, float]]] = {}
    # 2010-vintage tracts → 2020
    for src, dsts in xwalk_10_to_20.items():
        unified[src] = normalize(dsts)
    # 2000-vintage tracts → 2020 (composed). Only adds if not already covered as 2010.
    for src, dsts in xwalk_00_to_20.items():
        if src not in unified:
            unified[src] = normalize(dsts)

    log(f"  Unified xwalk: {len(unified):,} source tracts mapped to 2020 vintage")
    return unified


def harmonize(tract: str, unified: dict[str, list[tuple[str, float]]]) -> list[tuple[str, float]]:
    """Return [(tract_2020, weight), ...]. Identity for unknowns."""
    if not tract or len(tract) != 11:
        return [(tract, 1.0)]
    return unified.get(tract, [(tract, 1.0)])


# ---------- Apply to CRA tract-year ----------
CRA_COUNT_COLS = {
    # These are population/structural levels — apportion proportionally
    # (the model's circular-feature audit dropped these from training, but we keep
    # them in the harmonized panel for diagnostic + descriptive use)
}
CRA_RATE_COLS = {
    "cra_lender_presence_ratio_1yr",  # is a ratio; weight-average
}

def harmonize_cra(unified: dict[str, list[tuple[str, float]]]):
    src = PROC / "cra" / "tract_year.csv"
    dst = PROC / "cra" / "tract_year_h2020.csv"
    if not src.exists():
        log(f"  SKIP CRA: {src} missing")
        return

    # Read all rows
    with src.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    log(f"  Read {len(rows):,} CRA tract-year rows")

    # Re-aggregate per (tract_2020, year)
    agg: dict[tuple[str, int], dict] = {}
    n_changed = 0
    n_split = 0
    n_unchanged = 0
    for r in rows:
        src_t = r["tract_fips"]
        year = int(r["year"])
        targets = harmonize(src_t, unified)
        if len(targets) > 1:
            n_split += 1
        elif targets[0][0] != src_t:
            n_changed += 1
        else:
            n_unchanged += 1
        for tgt, weight in targets:
            key = (tgt, year)
            if key not in agg:
                agg[key] = {
                    "tract_fips": tgt,
                    "county_fips": tgt[:5],
                    "year": year,
                    "n_cra_lenders": 0.0,
                    "cra_lender_entries_1yr": 0.0,
                    "cra_lender_exits_1yr": 0.0,
                    "cra_lender_entries_3yr": 0.0,
                    "cra_lender_exits_3yr": 0.0,
                    "cra_lender_churn_1yr": 0.0,
                    "cra_lender_churn_3yr": 0.0,
                    "_w_total": 0.0,
                    "_ratio_weighted": 0.0,
                }
            a = agg[key]
            for col in ("n_cra_lenders", "cra_lender_entries_1yr", "cra_lender_exits_1yr",
                        "cra_lender_entries_3yr", "cra_lender_exits_3yr",
                        "cra_lender_churn_1yr", "cra_lender_churn_3yr"):
                v = r.get(col, "")
                try:
                    a[col] += float(v) * weight if v else 0.0
                except ValueError:
                    pass
            try:
                ratio = r.get("cra_lender_presence_ratio_1yr") or ""
                if ratio:
                    a["_ratio_weighted"] += float(ratio) * weight
                a["_w_total"] += weight
            except ValueError:
                pass

    # Materialize
    out_rows = []
    for (tgt, year), a in agg.items():
        rec = {
            "tract_fips": tgt,
            "county_fips": tgt[:5],
            "year": year,
        }
        for col in ("n_cra_lenders", "cra_lender_entries_1yr", "cra_lender_exits_1yr",
                    "cra_lender_entries_3yr", "cra_lender_exits_3yr",
                    "cra_lender_churn_1yr", "cra_lender_churn_3yr"):
            rec[col] = round(a[col], 4)
        rec["cra_lender_presence_ratio_1yr"] = (
            round(a["_ratio_weighted"] / a["_w_total"], 4) if a["_w_total"] > 0 else ""
        )
        out_rows.append(rec)

    out_rows.sort(key=lambda r: (r["tract_fips"], r["year"]))
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    log(f"  CRA harmonized: {n_unchanged:,} unchanged · {n_changed:,} renumbered · {n_split:,} split")
    log(f"  → {dst} ({len(out_rows):,} rows)")


# ---------- Apply to ACS tract-year ----------
ACS_COUNT_COLS = {"population", "housing_units"}
ACS_RATE_COLS = {"median_hh_income", "pct_poverty", "pct_minority", "pct_black",
                 "pct_hispanic", "pct_vacant", "unemployment_rate", "pct_bachelor_plus"}

def harmonize_acs(unified: dict[str, list[tuple[str, float]]]):
    src = PROC / "acs" / "tract_year.csv"
    dst = PROC / "acs" / "tract_year_h2020.csv"
    if not src.exists():
        log(f"  SKIP ACS: {src} missing")
        return

    with src.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    log(f"  Read {len(rows):,} ACS tract-year rows")

    agg: dict[tuple[str, int], dict] = {}
    n_changed = n_split = n_unchanged = 0
    for r in rows:
        src_t = r["tract_fips"]
        vintage = int(r["vintage"])
        targets = harmonize(src_t, unified)
        if len(targets) > 1: n_split += 1
        elif targets[0][0] != src_t: n_changed += 1
        else: n_unchanged += 1

        # Use source population as the weight base for rates
        try:
            src_pop = float(r.get("population") or 0)
        except ValueError:
            src_pop = 0

        for tgt, weight in targets:
            key = (tgt, vintage)
            if key not in agg:
                agg[key] = {"tract_fips": tgt, "vintage": vintage, "_pop_weight": 0.0}
                for c in ACS_COUNT_COLS: agg[key][c] = 0.0
                for c in ACS_RATE_COLS: agg[key][f"_{c}_w"] = 0.0
            a = agg[key]
            for c in ACS_COUNT_COLS:
                v = r.get(c, "")
                try:
                    a[c] += float(v) * weight if v else 0.0
                except ValueError:
                    pass
            pw = src_pop * weight
            a["_pop_weight"] += pw
            for c in ACS_RATE_COLS:
                v = r.get(c, "")
                try:
                    if v:
                        a[f"_{c}_w"] += float(v) * pw
                except ValueError:
                    pass

    # Materialize
    out_rows = []
    for (tgt, vintage), a in agg.items():
        rec = {"tract_fips": tgt, "vintage": vintage}
        for c in ACS_COUNT_COLS:
            rec[c] = round(a[c], 2)
        for c in ACS_RATE_COLS:
            rec[c] = round(a[f"_{c}_w"] / a["_pop_weight"], 4) if a["_pop_weight"] > 0 else ""
        out_rows.append(rec)

    out_rows.sort(key=lambda r: (r["tract_fips"], r["vintage"]))
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    log(f"  ACS harmonized: {n_unchanged:,} unchanged · {n_changed:,} renumbered · {n_split:,} split")
    log(f"  → {dst} ({len(out_rows):,} rows)")


def main():
    log("Loading crosswalks…")
    xwalk_00_to_10 = load_xwalk_00_to_10()
    xwalk_10_to_20 = load_xwalk_10_to_20()
    xwalk_00_to_20 = compose_00_to_20(xwalk_00_to_10, xwalk_10_to_20)
    unified = build_unified_xwalk(xwalk_00_to_10, xwalk_10_to_20, xwalk_00_to_20)

    log("\nHarmonizing CRA tract-year…")
    harmonize_cra(unified)

    log("\nHarmonizing ACS tract-year…")
    harmonize_acs(unified)

    (OUT / "_harmonization_log.txt").write_text("\n".join(LOG))
    log(f"\nLog → {OUT/'_harmonization_log.txt'}")


if __name__ == "__main__":
    main()
