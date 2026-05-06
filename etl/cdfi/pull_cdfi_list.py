#!/usr/bin/env python3
"""Normalize the CDFI Fund certified-institution list.

The CDFI Fund publishes a Certified CDFI list quarterly. There is no clean
public JSON API. The recommended approach is a manual download:

    https://www.cdfifund.gov/programs-training/certification/cdfi

Click "Search for Certified CDFIs" → export to CSV/Excel.

Manual download steps:
    1. Save the export at `data/raw/cdfi/cdfi_list_raw.xlsx` or `.csv`.
    2. Re-run this script.

Expected source columns (rename in this script):
    Organization Name → name
    Address → address
    City → city
    State → state
    ZIP Code → zip
    CDFI Type / Organization Type → type
    Certification Date → certification_date
    RSSD ID → RSSDID  (only the small subset of CDFIs that are FDIC-insured)

Output:
    data/raw/cdfi/cdfi_list.csv
        columns: cdfi_id, name, address, city, state, zip, type,
                 certification_date, RSSDID, snapshot_date
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "cdfi"
OUT = RAW_DIR / "cdfi_list.csv"


def load_raw():
    for p in sorted(RAW_DIR.glob("cdfi_list_raw*")):
        if p.suffix.lower() in (".xlsx", ".xls"):
            print(f"Reading {p.name}…", flush=True)
            return pd.read_excel(p, dtype=str), p
        if p.suffix.lower() == ".csv":
            print(f"Reading {p.name}…", flush=True)
            return pd.read_csv(p, dtype=str), p
    return None, None


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.strip() for c in df.columns]
    rename = {}
    for src in df.columns:
        s = src.lower()
        if s in {"organization name", "name", "institution name"} and "name" not in rename.values():
            rename[src] = "name"
        elif s in {"address", "street address", "street"}:
            rename[src] = "address"
        elif s in {"city"}:
            rename[src] = "city"
        elif s in {"state", "st", "stalp"}:
            rename[src] = "state"
        elif s in {"zip", "zip code", "zipcode"}:
            rename[src] = "zip"
        elif s in {"cdfi type", "organization type", "type"}:
            rename[src] = "type"
        elif s in {"certification date", "cert date", "certification_date"}:
            rename[src] = "certification_date"
        elif "rssd" in s:
            rename[src] = "RSSDID"
    df = df.rename(columns=rename)
    keep = [c for c in ["name", "address", "city", "state", "zip", "type", "certification_date", "RSSDID"] if c in df.columns]
    return df[keep].copy()


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    df, source = load_raw()
    if df is None or df.empty:
        print("\nNo CDFI raw download found.", file=sys.stderr)
        print(f"Manual step:", file=sys.stderr)
        print(f"  1. Visit https://www.cdfifund.gov/programs-training/certification/cdfi", file=sys.stderr)
        print(f"  2. Export the Certified CDFIs list as XLSX or CSV", file=sys.stderr)
        print(f"  3. Save under {RAW_DIR}/cdfi_list_raw.xlsx (or .csv)", file=sys.stderr)
        print(f"  4. Re-run this script", file=sys.stderr)
        sys.exit(1)

    df = normalize(df)
    if "name" not in df.columns:
        print("ERROR: no `name` column after normalization. Inspect raw file.", file=sys.stderr)
        sys.exit(2)

    df["RSSDID"] = df.get("RSSDID", "").fillna("").astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    df["cdfi_id"] = df["name"].astype(str).str.upper().str.replace(r"\W+", "_", regex=True).str.strip("_")
    df["snapshot_date"] = pd.Timestamp.today().date().isoformat()
    df["snapshot_year_extrapolated"] = 0
    df.to_csv(OUT, index=False)

    n_with_rssd = (df["RSSDID"].str.strip() != "").sum()
    print(f"\n→ {OUT}  ({len(df):,} CDFIs from {source.name})", flush=True)
    print(f"  with RSSDID (FDIC-insured CDFIs): {n_with_rssd:,}")


if __name__ == "__main__":
    main()
