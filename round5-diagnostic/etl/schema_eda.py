#!/usr/bin/env python3
"""Year-over-year schema EDA across Round-5 raw sources.

For each source, sample one file from the earliest, middle, and latest years,
report column lists + types + row counts, and flag differences. Output to
notes/03_schema_audit.md so the panel-build can encode reconciliation rules.

Sources audited:
  - CRA  disclosure (per-year directory of D-files)
  - CRA  aggregate
  - CRA  transmittal
  - FDIC SoD (per-year CSV)
  - SBA  loan-level CSVs
  - HMDA tract-aggregate CSVs (already homogeneous since we control the pull)
  - ACS  state JSON files
"""
from __future__ import annotations
import csv
import json
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "notes" / "03_schema_audit.md"


def emit(lines, *items):
    for it in items:
        lines.append(it)


def cra_dat_columns(path: Path, max_lines: int = 50) -> dict:
    """Return record-type → row count + sample line length."""
    by_type: dict[str, dict] = defaultdict(lambda: {"count": 0, "len_min": 99999, "len_max": 0, "sample": ""})
    n = 0
    with path.open("r", encoding="latin-1", errors="ignore") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if len(line) < 5:
                continue
            rt = line[:5].strip()
            d = by_type[rt]
            d["count"] += 1
            d["len_min"] = min(d["len_min"], len(line))
            d["len_max"] = max(d["len_max"], len(line))
            if d["count"] == 1:
                d["sample"] = line[:80]
            n += 1
            if n > max_lines * 50:
                break
    return dict(by_type)


def audit_cra(lines):
    emit(lines, "## CRA — Disclosure files\n")
    cra_root = RAW / "cra"
    if not cra_root.exists():
        emit(lines, "_(no data)_\n"); return

    years = sorted(int(p.name) for p in cra_root.iterdir() if p.is_dir() and p.name.isdigit())
    samples = [years[0], years[len(years)//2], years[-1]]
    emit(lines, f"Years on disk: {min(years)}–{max(years)} ({len(years)} years)")
    emit(lines, f"Sampling: {samples}\n")

    emit(lines, "| Year | File | Record types found | Row counts |")
    emit(lines, "|---|---|---|---|")
    for y in samples:
        ddir = cra_root / str(y) / "discl"
        if not ddir.exists():
            emit(lines, f"| {y} | _(no discl folder)_ |  |  |"); continue
        files = sorted(ddir.glob("*.dat"))
        for f in files:
            by_type = cra_dat_columns(f)
            type_summary = ", ".join(sorted(by_type.keys())[:6])
            row_summary = ", ".join(f"{k}={v['count']}" for k, v in sorted(by_type.items())[:6])
            emit(lines, f"| {y} | `{f.name}` | {type_summary} | {row_summary} |")
    emit(lines, "")

    # Cross-year file-name comparison
    emit(lines, "**File-name pattern check across all 16 years:**")
    pattern_by_year: dict[int, set] = {}
    for y in years:
        ddir = cra_root / str(y) / "discl"
        if ddir.exists():
            pattern_by_year[y] = {f.name.replace(str(y), "{Y}").replace(str(y)[-2:], "{YY}") for f in ddir.glob("*.dat")}

    if len(set(frozenset(s) for s in pattern_by_year.values())) > 1:
        emit(lines, "Schema drift detected — file-name set differs across years:\n")
        for y in years:
            emit(lines, f"- **{y}**: {len(pattern_by_year.get(y, set()))} files: {sorted(pattern_by_year.get(y, set()))[:5]}…")
    else:
        emit(lines, "No file-name pattern drift.")
    emit(lines, "")


def audit_fdic_sod(lines):
    emit(lines, "## FDIC Summary of Deposits (per-year CSV)\n")
    sod_dir = RAW / "fdic" / "sod"
    if not sod_dir.exists():
        emit(lines, "_(no data)_\n"); return
    files = sorted(sod_dir.glob("sod_*.csv"))
    headers_by_year = {}
    rows_by_year = {}
    for f in files:
        try:
            year = int(f.stem.replace("sod_", ""))
        except ValueError:
            continue
        with f.open("r", encoding="utf-8") as fh:
            rdr = csv.reader(fh)
            try:
                hdr = next(rdr)
            except StopIteration:
                continue
            headers_by_year[year] = hdr
            rows = sum(1 for _ in rdr)
            rows_by_year[year] = rows

    emit(lines, f"Years on disk: {min(headers_by_year)}–{max(headers_by_year)} ({len(headers_by_year)} years)")
    emit(lines, "")

    canonical = headers_by_year[min(headers_by_year)]
    emit(lines, f"Earliest year ({min(headers_by_year)}) columns: `{canonical}`\n")
    emit(lines, "| Year | n_cols | n_rows | Schema diff vs earliest |")
    emit(lines, "|---|---:|---:|---|")
    for y in sorted(headers_by_year):
        cols = headers_by_year[y]
        diff = []
        added = set(cols) - set(canonical)
        removed = set(canonical) - set(cols)
        if added: diff.append(f"+{sorted(added)}")
        if removed: diff.append(f"−{sorted(removed)}")
        emit(lines, f"| {y} | {len(cols)} | {rows_by_year[y]:,} | {', '.join(diff) if diff else '✓ same'} |")
    emit(lines, "")


def audit_sba(lines):
    emit(lines, "## SBA loan-level (each historical period is its own file)\n")
    sba_dir = RAW / "sba"
    files = sorted(sba_dir.glob("foia-*.csv"))
    emit(lines, f"Files: {len(files)}\n")
    headers = {}
    for f in files:
        with f.open("r", encoding="utf-8", errors="replace") as fh:
            rdr = csv.reader(fh)
            try:
                hdr = next(rdr)
            except StopIteration:
                continue
            headers[f.name] = hdr

    if not headers:
        emit(lines, "_(no headers parsed)_\n"); return
    canonical_name = sorted(headers)[0]
    canonical = headers[canonical_name]
    emit(lines, f"Anchor file: `{canonical_name}` ({len(canonical)} cols)\n")
    emit(lines, "| File | n_cols | added vs anchor | removed vs anchor |")
    emit(lines, "|---|---:|---|---|")
    for name, cols in sorted(headers.items()):
        added = sorted(set(cols) - set(canonical))
        removed = sorted(set(canonical) - set(cols))
        added_str = ", ".join(added)[:80] or "✓"
        removed_str = ", ".join(removed)[:80] or "✓"
        emit(lines, f"| `{name}` | {len(cols)} | {added_str} | {removed_str} |")
    emit(lines, "")


def audit_hmda(lines):
    emit(lines, "## HMDA tract-aggregates (we control the schema — should be uniform)\n")
    hmda_dir = RAW / "hmda"
    year_dirs = sorted(d for d in hmda_dir.glob("tract_aggregates_*") if d.is_dir())
    if not year_dirs:
        emit(lines, "_(no data)_\n"); return

    schemas = {}
    for d in year_dirs:
        year = int(d.name.split("_")[-1])
        # Sample first state file
        first = next(iter(sorted(d.glob("*.csv"))), None)
        if not first:
            continue
        with first.open("r", encoding="utf-8") as fh:
            hdr = next(csv.reader(fh))
            schemas[year] = hdr

    canonical = schemas[min(schemas)]
    emit(lines, f"Anchor: {min(schemas)} ({len(canonical)} cols)\n")
    emit(lines, "| Year | n_cols | diff vs anchor |")
    emit(lines, "|---|---:|---|")
    for y in sorted(schemas):
        added = sorted(set(schemas[y]) - set(canonical))
        removed = sorted(set(canonical) - set(schemas[y]))
        diff = []
        if added: diff.append(f"+{added}")
        if removed: diff.append(f"−{removed}")
        emit(lines, f"| {y} | {len(schemas[y])} | {', '.join(diff) if diff else '✓ same'} |")
    emit(lines, "")


def audit_acs(lines):
    emit(lines, "## ACS 5-year per-vintage variable lists\n")
    acs_dir = RAW / "acs"
    vintage_dirs = sorted(d for d in acs_dir.glob("acs5_*") if d.is_dir())
    schemas = {}
    for d in vintage_dirs:
        vintage = int(d.name.split("_")[-1])
        # Sample first state file
        sample = next(iter(sorted(d.glob("*.json"))), None)
        if not sample:
            continue
        try:
            data = json.loads(sample.read_text())
            if data:
                schemas[vintage] = data[0]
        except Exception:
            continue

    canonical = schemas[max(schemas)] if schemas else []
    emit(lines, f"Anchor: latest vintage ({max(schemas) if schemas else '?'}, {len(canonical)} vars)\n")
    emit(lines, "| Vintage | n_vars | diff vs latest |")
    emit(lines, "|---|---:|---|")
    for v in sorted(schemas):
        added = sorted(set(schemas[v]) - set(canonical))
        removed = sorted(set(canonical) - set(schemas[v]))
        diff = []
        if added: diff.append(f"+{added}")
        if removed: diff.append(f"−{removed}")
        emit(lines, f"| {v} | {len(schemas[v])} | {', '.join(diff) if diff else '✓ same'} |")
    emit(lines, "")


def main():
    lines = []
    emit(lines, "# Round 5 — Year-over-Year Schema Audit\n")
    emit(lines, "Generated by `etl/schema_eda.py`. Documents the schema drift across years")
    emit(lines, "for each raw source so the panel build can encode the right reconciliation rules.\n")
    emit(lines, "---\n")

    audit_cra(lines)
    audit_fdic_sod(lines)
    audit_sba(lines)
    audit_hmda(lines)
    audit_acs(lines)

    OUT.write_text("\n".join(lines))
    print(f"→ {OUT}")
    print(f"  ({len(lines)} lines)")


if __name__ == "__main__":
    main()
