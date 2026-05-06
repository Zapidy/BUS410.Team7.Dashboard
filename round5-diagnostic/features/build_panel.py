#!/usr/bin/env python3
"""Build the unified Round-5 tract-year panel.

Joins all per-source processed CSVs into one tract-year parquet:
  data/processed/panel/tract_year.parquet

Sources joined (by `tract_fips × year` unless noted):
  - CRA tract-year                (data/processed/cra/tract_year.csv)
  - CRA county-year               (data/processed/cra/county_year.csv)        — joined via county_fips
  - FDIC SoD county-year          (data/processed/fdic/county_year.csv)       — joined via county_fips
  - ACS tract-year                (data/processed/acs/tract_year.csv)         — joined via tract_fips × matched vintage (lag-aware: vintage_end < year)
  - HMDA tract-year               (data/raw/hmda/tract_aggregates_*/*.csv)    — only 2018-2024
  - USDA RUCA                     (data/raw/usda/ruca_2020_tracts.xlsx)
  - Opportunity Zones             (data/raw/oz/opportunity_zones.csv)
  - USDA County Typology          (data/raw/usda/county_typology_2025.xlsx)   — for persistent poverty flag

Lag-aware ACS join rule: for prediction year P, use the latest ACS vintage
whose end year < P. Vintage `2022` (5-year ACS 2018–2022) is published in
late 2023, so it can be a feature for prediction years ≥ 2024 ONLY. Strict
rule prevents the lookahead leak documented in notes/00_methodology.md §2.2.

The panel is restricted to tract_fips × year ∈ {2009..2024}.
"""
from __future__ import annotations
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
OUT = PROC / "panel"
OUT.mkdir(parents=True, exist_ok=True)

PANEL_YEARS = list(range(2009, 2025))


def load_cra_tract():
    # Prefer harmonized version if it exists (Phase 2.5 output)
    harm = PROC / "cra" / "tract_year_h2020.csv"
    src = harm if harm.exists() else (PROC / "cra" / "tract_year.csv")
    df = pd.read_csv(src, dtype={"tract_fips": str, "county_fips": str})
    df["year"] = df["year"].astype(int)
    print(f"  CRA tract-year:   {len(df):>9,} rows  ({src.name})")
    return df


def load_cra_county():
    df = pd.read_csv(PROC / "cra" / "county_year.csv", dtype={"county_fips": str})
    df["year"] = df["year"].astype(int)
    print(f"  CRA county-year:  {len(df):>9,} rows")
    return df


def load_fdic():
    df = pd.read_csv(PROC / "fdic" / "county_year.csv", dtype={"county_fips": str})
    df["year"] = df["year"].astype(int)
    print(f"  FDIC county-year: {len(df):>9,} rows")
    return df


def load_acs():
    harm = PROC / "acs" / "tract_year_h2020.csv"
    src = harm if harm.exists() else (PROC / "acs" / "tract_year.csv")
    df = pd.read_csv(src, dtype={"tract_fips": str})
    df["vintage"] = df["vintage"].astype(int)
    print(f"  ACS tract-year:   {len(df):>9,} rows × {df['vintage'].nunique()} vintages ({src.name})")
    return df


def lag_aware_acs_merge(panel: pd.DataFrame, acs: pd.DataFrame) -> pd.DataFrame:
    """For each (tract_fips, year), pick the latest ACS vintage whose end-year < year.

    ACS 5-year is named after its end year (e.g. vintage 2020 = 2016-2020 5-year).
    The vintage labeled `V` is published in AUTUMN of year V+1, so its earliest
    valid use as a feature for prediction at the START of year P is when V+1 < P,
    i.e. V <= P - 2.

    Round-5 audit fix (2026-04-28): tightened from `vintage <= year - 1` to
    `vintage <= year - 2` to eliminate the ACS publication-lag forward leak.
    See CHANGES.md §13 fix #2.
    """
    available = sorted(acs["vintage"].unique())
    print(f"  ACS vintages available: {available}  (using vintage <= year - 2 lag rule)")
    rows = []
    acs_indexed = {v: acs[acs["vintage"] == v].set_index("tract_fips") for v in available}

    panel_keys = panel[["tract_fips", "year"]].drop_duplicates()
    for _, kr in panel_keys.iterrows():
        year = int(kr["year"])
        tract = kr["tract_fips"]
        # Find latest available vintage with vintage <= year - 2 (publication-lag-safe)
        usable = [v for v in available if v <= year - 2]
        if not usable:
            continue
        v = max(usable)
        try:
            row = acs_indexed[v].loc[tract]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            rec = row.to_dict()
            rec["tract_fips"] = tract
            rec["year"] = year
            rec["acs_vintage_used"] = v
            rows.append(rec)
        except KeyError:
            continue
    out = pd.DataFrame(rows)
    print(f"  ACS-merged rows: {len(out):>9,}")
    return out


def load_hmda():
    """Concat all per-state HMDA aggregate CSVs into one tract-year."""
    rows = []
    for year_dir in sorted((RAW / "hmda").glob("tract_aggregates_*")):
        try:
            year = int(year_dir.name.split("_")[-1])
        except ValueError:
            continue
        for state_csv in sorted(year_dir.glob("*.csv")):
            df = pd.read_csv(state_csv, dtype={"tract_fips": str, "state": str})
            df["year"] = year
            rows.append(df)
    if not rows:
        print("  HMDA: no files yet (still pulling — re-run after pull completes)")
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True)
    print(f"  HMDA tract-year:  {len(out):>9,} rows × {out['year'].nunique()} years: {sorted(out['year'].unique())}")
    return out


def load_oz():
    """Load Opportunity Zones tract list. Tries CSV then xlsx; falls back to skip."""
    f_csv = RAW / "oz" / "opportunity_zones.csv"
    f_xlsx = RAW / "oz" / "designated_qozs.xlsx"

    # The HUD CSV download was an HTML stub on this pull. Try the CDFI xlsx first.
    if f_xlsx.exists():
        try:
            df = pd.read_excel(f_xlsx, dtype=str)
            tract_col = next((c for c in df.columns if "tract" in c.lower() or "geoid" in c.lower()), None)
            if tract_col is not None:
                df["tract_fips"] = df[tract_col].astype(str).str.zfill(11)
                df["is_opportunity_zone"] = 1
                out = df[["tract_fips", "is_opportunity_zone"]].drop_duplicates("tract_fips")
                print(f"  Opportunity Zones (xlsx): {len(out):>5,} tracts")
                return out
        except Exception as e:
            print(f"  OZ xlsx load failed: {e}")

    # Try CSV — but check first that it's not HTML
    if f_csv.exists():
        with f_csv.open("r", encoding="utf-8", errors="replace") as fh:
            first = fh.read(64).lstrip()
        if first.startswith("<"):
            print(f"  OZ CSV is HTML stub, skipping. Manual download needed.")
            return pd.DataFrame()
        try:
            df = pd.read_csv(f_csv, dtype=str)
            tract_col = next((c for c in df.columns if "tract" in c.lower() or "geoid" in c.lower()), None)
            if tract_col is not None:
                df["tract_fips"] = df[tract_col].str.zfill(11)
                df["is_opportunity_zone"] = 1
                out = df[["tract_fips", "is_opportunity_zone"]].drop_duplicates("tract_fips")
                print(f"  Opportunity Zones (csv): {len(out):>5,} tracts")
                return out
        except Exception as e:
            print(f"  OZ CSV load failed: {e}")
    print("  Opportunity Zones: skipping (no usable file)")
    return pd.DataFrame()


def load_ruca():
    f = RAW / "usda" / "ruca_2020_tracts.xlsx"
    if not f.exists():
        return pd.DataFrame()
    df = pd.read_excel(f, sheet_name="RUCA2020 Tract Data", skiprows=1)
    out = pd.DataFrame({
        "tract_fips": df["TractFIPS20"].astype(str).str.zfill(11),
        "ruca_code": pd.to_numeric(df["PrimaryRUCA"], errors="coerce"),
    }).dropna(subset=["ruca_code"]).drop_duplicates("tract_fips")
    out["is_rural"] = (out["ruca_code"] >= 7).astype(int)
    print(f"  RUCA tract codes: {len(out):>5,} tracts ({out['is_rural'].sum():,} rural)")
    return out


def load_persistent_poverty():
    f = RAW / "usda" / "county_typology_2025.xlsx"
    if not f.exists():
        return pd.DataFrame()
    df = pd.read_excel(f, sheet_name="2025 ERS County Typology Codes")
    out = pd.DataFrame({
        "county_fips": df["FIPStxt"].astype(str).str.zfill(5),
        "is_persistent_poverty": pd.to_numeric(df["Persistent_Poverty_1721"], errors="coerce").fillna(0).astype(int),
    }).drop_duplicates("county_fips")
    print(f"  Persistent poverty counties: {out['is_persistent_poverty'].sum():,} of {len(out):,}")
    return out


def main():
    print("Loading sources…")
    cra_tract = load_cra_tract()
    # CRA county fields already named cra_county_*; preserve them as-is
    cra_county = load_cra_county()
    # FDIC fields already named fdic_*; preserve as-is
    fdic = load_fdic()
    acs = load_acs()
    hmda = load_hmda()
    oz = load_oz()
    ruca = load_ruca()
    persistent_poverty = load_persistent_poverty()

    # ---- Filter to panel years ----
    cra_tract = cra_tract[cra_tract["year"].isin(PANEL_YEARS)]

    # ---- Start the panel from CRA tract-year (largest spine) ----
    panel = cra_tract.copy()
    print(f"\nPanel skeleton (CRA tract-year, {min(PANEL_YEARS)}-{max(PANEL_YEARS)}): {len(panel):,} rows")

    # ---- Merge CRA county features ----
    cra_county = cra_county[cra_county["year"].isin(PANEL_YEARS)]
    panel = panel.merge(cra_county, on=["county_fips", "year"], how="left")
    print(f"After CRA county merge:  {len(panel):>9,} rows × {panel.shape[1]} cols")

    # ---- Merge FDIC SoD county features ----
    fdic = fdic[fdic["year"].isin(PANEL_YEARS)]
    panel = panel.merge(fdic, on=["county_fips", "year"], how="left")
    print(f"After FDIC merge:        {len(panel):>9,} rows × {panel.shape[1]} cols")

    # ---- Merge HMDA tract-year (only 2018-2024) ----
    if not hmda.empty:
        hmda = hmda[hmda["year"].isin(PANEL_YEARS)]
        panel = panel.merge(
            hmda.drop(columns=["state"], errors="ignore"),
            on=["tract_fips", "year"],
            how="left",
        )
        panel["has_hmda"] = (panel["year"] >= 2018).astype(int)
        print(f"After HMDA merge:        {len(panel):>9,} rows × {panel.shape[1]} cols")
    else:
        panel["has_hmda"] = 0

    # ---- Merge ACS with lag rule ----
    print("\nMerging ACS (lag-aware)…")
    acs_panel = lag_aware_acs_merge(panel[["tract_fips", "year"]].drop_duplicates(), acs)
    panel = panel.merge(acs_panel, on=["tract_fips", "year"], how="left")
    print(f"After ACS merge:         {len(panel):>9,} rows × {panel.shape[1]} cols")

    # ---- Merge Opportunity Zones (static designation, post-2017) ----
    if not oz.empty:
        panel = panel.merge(oz, on="tract_fips", how="left")
        panel["is_opportunity_zone"] = panel["is_opportunity_zone"].fillna(0).astype(int)
        # OZ designation took effect in 2018; flag = 0 for years < 2018 even if tract is OZ
        panel.loc[panel["year"] < 2018, "is_opportunity_zone"] = 0
        print(f"After OZ merge:          {len(panel):>9,} rows × {panel.shape[1]} cols")

    # ---- Merge USDA RUCA (rural-urban continuum, static 2020) ----
    if not ruca.empty:
        panel = panel.merge(ruca, on="tract_fips", how="left")
        panel["is_rural"] = panel["is_rural"].fillna(0).astype(int)
        print(f"After RUCA merge:        {len(panel):>9,} rows × {panel.shape[1]} cols")

    # ---- Merge persistent poverty county flag (static designation) ----
    if not persistent_poverty.empty:
        panel = panel.merge(persistent_poverty, on="county_fips", how="left")
        panel["is_persistent_poverty"] = panel["is_persistent_poverty"].fillna(0).astype(int)
        print(f"After PP merge:          {len(panel):>9,} rows × {panel.shape[1]} cols")

    # ---- Write output ----
    out_path = OUT / "tract_year.parquet"
    panel.to_parquet(out_path, index=False)
    out_csv = OUT / "tract_year.head.csv"
    panel.head(50).to_csv(out_csv, index=False)
    print(f"\n→ {out_path}")
    print(f"  shape: {panel.shape}")
    print(f"  size:  {out_path.stat().st_size / 1e6:.1f} MB")
    print(f"  cols:  {list(panel.columns)}")
    print(f"\n→ {out_csv} (sample)")


if __name__ == "__main__":
    main()
