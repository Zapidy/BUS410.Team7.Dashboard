#!/usr/bin/env python3
"""Apportion ZIP-level SBA loan totals down to census tracts.

Inputs (already on disk):
    data/processed/sba/zip_year.csv           ZIP-year SBA totals
    web/data/_lookup/zcta_tract.txt           Census ZCTA-Tract relationship (2020)
    data/processed/panel/tract_year_with_target.parquet   For tract population

Output:
    web/data/_lookup/sba_tract.parquet        tract_fips, sba_loans, sba_loans_per_1k, sba_score

Method:
    For each (zcta, tract) pair compute the share of the ZCTA's land area
    that lies in the tract. We treat ZCTA ≈ ZIP (Census's intent). Apportion
    each ZIP's SBA loan count to its overlapping tracts by that share.
    Then divide by tract population to get per-capita intensity, and rank
    tracts within state into a 0-100 percentile (`sba_score`). The "thriving"
    cohort used by the Peer Finder is sba_score >= 80.

    Land-area weighting is a defensible default given the data on disk;
    HUD's business-weighted USPS crosswalk would be marginally more accurate
    but is auth-locked and not worth a dependency.
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
WEB_DATA = WEB / "data"
LOOKUP = WEB_DATA / "_lookup"
LOOKUP.mkdir(parents=True, exist_ok=True)

SBA_PATH = ROOT / "data" / "processed" / "sba" / "zip_year.csv"
ZT_PATH = LOOKUP / "zcta_tract.txt"
PANEL_PATH = ROOT / "data" / "processed" / "panel" / "tract_year_with_target.parquet"
OUT = LOOKUP / "sba_tract.parquet"


def load_zcta_tract_weights() -> pd.DataFrame:
    """Return a DataFrame [zcta, tract_fips, weight] where weight is the
    share of the ZCTA's land area that falls inside the tract.
    """
    rows = []
    with ZT_PATH.open("r", encoding="utf-8-sig", errors="replace") as f:
        next(f)  # header
        for line in f:
            parts = line.rstrip("\r\n").split("|")
            if len(parts) < 16:
                continue
            zcta = parts[1].strip()
            tract = parts[9].strip().zfill(11)
            try:
                area_part = int(parts[15] or 0)
            except (ValueError, IndexError):
                continue
            if not zcta or not tract.isdigit() or len(tract) != 11 or area_part <= 0:
                continue
            rows.append((zcta, tract, area_part))
    df = pd.DataFrame(rows, columns=["zcta", "tract_fips", "area_part"])
    zip_total = df.groupby("zcta")["area_part"].transform("sum")
    df["weight"] = df["area_part"] / zip_total
    return df[["zcta", "tract_fips", "weight"]]


def main() -> int:
    if not SBA_PATH.exists():
        print(f"ERROR: missing {SBA_PATH}", file=sys.stderr)
        return 2
    if not ZT_PATH.exists():
        print(f"ERROR: missing {ZT_PATH}", file=sys.stderr)
        return 2
    if not PANEL_PATH.exists():
        print(f"ERROR: missing {PANEL_PATH}", file=sys.stderr)
        return 2

    print("Loading SBA zip_year…")
    sba = pd.read_csv(SBA_PATH, dtype={"zip5": str})
    sba["zip5"] = sba["zip5"].str.zfill(5)
    latest_year = int(sba["year"].max())
    sba_latest = sba[sba["year"] == latest_year].copy()
    print(f"  rows: {len(sba):,} · using year {latest_year} ({len(sba_latest):,} ZIPs)")

    print("Loading ZCTA-Tract land-area weights…")
    weights = load_zcta_tract_weights()
    print(f"  pairs: {len(weights):,} · unique zctas: {weights['zcta'].nunique():,}")

    print("Apportioning SBA loans to tracts…")
    merged = sba_latest.merge(
        weights, left_on="zip5", right_on="zcta", how="inner",
    )
    merged["sba_loans_apportioned"] = merged["n_loans"] * merged["weight"]
    merged["sba_amount_apportioned"] = merged["sum_gross_approval"] * merged["weight"]
    tract_sba = (
        merged.groupby("tract_fips")
        .agg(sba_loans=("sba_loans_apportioned", "sum"),
             sba_amount=("sba_amount_apportioned", "sum"))
        .reset_index()
    )
    print(f"  tracts with any SBA: {len(tract_sba):,}")

    print("Loading tract populations from panel (latest year per tract)…")
    panel = pd.read_parquet(PANEL_PATH, columns=["tract_fips", "year", "population"])
    panel = panel.dropna(subset=["population"])
    panel = panel.sort_values(["tract_fips", "year"], ascending=[True, False])
    pop = panel.drop_duplicates(subset="tract_fips", keep="first")[["tract_fips", "population"]]
    print(f"  tracts with pop: {len(pop):,}")

    df = pop.merge(tract_sba, on="tract_fips", how="left")
    df["sba_loans"] = df["sba_loans"].fillna(0.0)
    df["sba_amount"] = df["sba_amount"].fillna(0.0)
    # Per-1k-residents intensity. Avoid div-by-zero for empty tracts.
    df["sba_loans_per_1k"] = df.apply(
        lambda r: (r["sba_loans"] / r["population"] * 1000.0)
        if r["population"] and r["population"] > 0 else 0.0,
        axis=1,
    )
    df["state_fips"] = df["tract_fips"].str[:2]

    # Within-state percentile rank (0-100). Tracts with zero loans get 0.
    print("Ranking within state…")
    df["sba_score"] = (
        df.groupby("state_fips")["sba_loans_per_1k"]
        .rank(method="average", pct=True) * 100.0
    )
    df["sba_score"] = df["sba_score"].fillna(0.0).round(1)
    df["sba_loans_per_1k"] = df["sba_loans_per_1k"].round(3)
    df["sba_loans"] = df["sba_loans"].round(2)

    out = df[["tract_fips", "sba_loans", "sba_loans_per_1k", "sba_score"]]
    out.to_parquet(OUT, index=False)
    print(f"  → {OUT} ({len(out):,} rows)")
    print(f"  thriving (sba_score>=80): {(out['sba_score'] >= 80).sum():,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
