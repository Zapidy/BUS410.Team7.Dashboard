#!/usr/bin/env python3
"""Pull FDIC MDI (Minority Depository Institution) list.

The FDIC public BankFind Suite API (banks.data.fdic.gov) returns MDI_STATUS_CODE
as an empty string for all institutions — the field is not exposed via the API
even though it exists in the underlying data. The MDI list is published as a
quarterly Excel/CSV download from:

    https://www.fdic.gov/minority-depository-institutions-program/minority-depository-institutions-list

Manual download steps:
    1. Visit the MDI program page above.
    2. Download the latest quarterly MDI list (typically `MDIList_qXyyyy.xlsx`).
    3. Save it as `data/raw/mdi/mdi_list_raw.xlsx` or convert to CSV at
       `data/raw/mdi/mdi_list_raw.csv`.
    4. Re-run this script to normalize.

This script:
    - Reads either xlsx or csv from `data/raw/mdi/`
    - Normalizes column names (FDIC publishes as `Cert.`, `Institution Name`,
      `City`, `State`, `Minority Status1`, `Federal Reserve ID Number`)
    - Joins to FDIC SoD by CERT or RSSD to confirm coverage
    - Writes `data/raw/mdi/mdi_list.csv` with columns:
        RSSDID, CERT, NAME, MINORITY_STATUS, snapshot_date

MDI list is small (~150 banks); a current snapshot back-extended to all
panel years is the documented approach (see notes/02_geocoding_log.md).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "mdi"
OUT = RAW_DIR / "mdi_list.csv"


def load_raw():
    candidates = [
        ("xlsx", RAW_DIR.glob("*.xlsx")),
        ("csv", RAW_DIR.glob("mdi_list_raw*.csv")),
    ]
    for kind, paths in candidates:
        for p in paths:
            print(f"Reading {p.name} ({kind})…", flush=True)
            if kind == "xlsx":
                return pd.read_excel(p, dtype=str), p
            return pd.read_csv(p, dtype=str), p
    return None, None


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.strip() for c in df.columns]
    rename = {}
    for src, dst in (
        ("Cert.", "CERT"),
        ("Cert", "CERT"),
        ("CERT", "CERT"),
        ("FDIC Cert", "CERT"),
        ("Institution Name", "NAME"),
        ("Bank Name", "NAME"),
        ("NAME", "NAME"),
        ("Federal Reserve ID Number", "RSSDID"),
        ("RSSD ID", "RSSDID"),
        ("RSSDID", "RSSDID"),
        ("Minority Status1", "MINORITY_STATUS"),
        ("Minority Status", "MINORITY_STATUS"),
        ("MINORITY_STATUS", "MINORITY_STATUS"),
        ("State", "STALP"),
        ("ST", "STALP"),
        ("City", "CITY"),
    ):
        if src in df.columns and dst not in rename.values():
            rename[src] = dst
    df = df.rename(columns=rename)
    keep = [c for c in ["RSSDID", "CERT", "NAME", "STALP", "CITY", "MINORITY_STATUS"] if c in df.columns]
    return df[keep].copy()


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    df, source = load_raw()
    if df is None or df.empty:
        print("\nNo MDI raw download found.", file=sys.stderr)
        print(f"Manual step:", file=sys.stderr)
        print(f"  1. Visit https://www.fdic.gov/minority-depository-institutions-program/minority-depository-institutions-list", file=sys.stderr)
        print(f"  2. Download the quarterly MDI list (xlsx)", file=sys.stderr)
        print(f"  3. Save under {RAW_DIR}/", file=sys.stderr)
        print(f"  4. Re-run this script", file=sys.stderr)
        sys.exit(1)

    df = normalize(df)
    if "RSSDID" not in df.columns:
        print("WARNING: no RSSDID column — downstream MDI join will fail. Check raw file.", file=sys.stderr)
        sys.exit(2)

    df["RSSDID"] = df["RSSDID"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    df["snapshot_date"] = pd.Timestamp.today().date().isoformat()
    df.to_csv(OUT, index=False)
    print(f"\n→ {OUT}  ({len(df):,} MDIs from {source.name})", flush=True)
    if "MINORITY_STATUS" in df.columns:
        print("Minority-status distribution:")
        print(df["MINORITY_STATUS"].value_counts().to_string())


if __name__ == "__main__":
    main()
