#!/usr/bin/env python3
"""Match CRA respondent_id to FDIC RSSD via name + city + state.

CRA disclosure files key on (agency_code, respondent_id) — a regulator-assigned
ID that does NOT match FDIC's RSSDID or CERT. There is no public official
crosswalk. This script does a 3-pass fuzzy match:

    1. Exact normalized name + state.
    2. Fuzzy name (rapidfuzz token_set_ratio ≥ 90) + state.
    3. Name + city, fuzzy ratio ≥ 85.

Anything in [75, 90) is flagged for manual review.

Inputs:
    ../round5/data/processed/cra/reporters.csv      (CRA reporters union)
    data/raw/fdic_call/institutions.csv             (from pull_fdic_call.py)

Output:
    data/processed/lender_class/cra_to_rssd.csv
        columns: lender_id, year, RSSDID, name_cra, name_fdic, state, city,
                 match_method, fuzzy_ratio, confidence

Success criterion: ≥ 95% match rate weighted by CRA loan dollar volume.
Match rate by row count is less important — long-tail lenders contribute little.

Credit unions (agency_code = 4) are NOT in FDIC. They are bypassed here and
flagged downstream via CRA agency_code directly. See classify_lenders.py.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

try:
    from rapidfuzz import fuzz, process
except ImportError:
    print("ERROR: pip install rapidfuzz", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[2]
ROUND5_REPORTERS = ROOT.parent / "round5" / "data" / "processed" / "cra" / "reporters.csv"
FDIC_INST = ROOT / "data" / "raw" / "fdic_call" / "institutions.csv"
OUT_DIR = ROOT / "data" / "processed" / "lender_class"

DROP_TOKENS = {
    "national", "association", "the", "a", "of", "and", "&",
    "co", "company", "corp", "corporation", "inc", "incorporated",
    "fsb", "ssb", "n.a.", "na", "n.a", "nat'l", "natl",
    "trust", "tr", "tc",
    "bank", "banking", "bk",
    "savings", "savg", "sav",
    "federal", "fed", "fdl",
}


def normalize_name(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^\w\s]", " ", s)
    tokens = [t for t in s.split() if t and t not in DROP_TOKENS]
    return " ".join(tokens).strip()


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not ROUND5_REPORTERS.exists():
        raise SystemExit(f"Missing: {ROUND5_REPORTERS}")
    if not FDIC_INST.exists():
        raise SystemExit(f"Missing: {FDIC_INST}\nRun etl/lender_class/pull_fdic_call.py first.")

    cra = pd.read_csv(ROUND5_REPORTERS, dtype=str).fillna("")
    fdic = pd.read_csv(FDIC_INST, dtype=str).fillna("")

    print(f"CRA reporters: {len(cra):,}", flush=True)
    print(f"FDIC institutions: {len(fdic):,}", flush=True)

    # Skip credit unions (agency_code = 4) — bypass FDIC matching entirely
    cra_skip = cra[cra["agency_code"] == "4"].copy()
    cra_match = cra[cra["agency_code"] != "4"].copy()
    print(f"  Credit unions skipped: {len(cra_skip):,}", flush=True)
    print(f"  Banks/thrifts to match: {len(cra_match):,}", flush=True)

    cra_match["name_norm"] = cra_match["name"].map(normalize_name)
    cra_match["state_norm"] = cra_match["state"].str.upper().str.strip()
    cra_match["city_norm"] = cra_match["city"].str.upper().str.strip()

    fdic["name_norm"] = fdic["NAME"].map(normalize_name)
    fdic["state_norm"] = fdic["STALP"].str.upper().str.strip()
    fdic["city_norm"] = fdic["CITY"].str.upper().str.strip()

    by_state = {st: g for st, g in fdic.groupby("state_norm")}

    matches: list[dict] = []

    print("\nPass 1: exact name + state…", flush=True)
    pass1_hits = 0
    unmatched_idx = []
    for idx, row in cra_match.iterrows():
        st = row["state_norm"]
        nm = row["name_norm"]
        candidates = by_state.get(st, pd.DataFrame())
        if candidates.empty:
            unmatched_idx.append(idx)
            continue
        exact = candidates[candidates["name_norm"] == nm]
        if len(exact) >= 1:
            best = exact.iloc[0]
            matches.append({
                "lender_id": row["lender_id"],
                "year": row["activity_year"],
                "RSSDID": best["RSSDID"],
                "CERT": best["CERT"],
                "name_cra": row["name"],
                "name_fdic": best["NAME"],
                "state": st,
                "city": row["city_norm"],
                "match_method": "exact",
                "fuzzy_ratio": 100.0,
                "confidence": 1.0,
            })
            pass1_hits += 1
        else:
            unmatched_idx.append(idx)
    print(f"  hits: {pass1_hits:,}", flush=True)

    print("\nPass 2: fuzzy name (token_set_ratio ≥ 90) + state…", flush=True)
    pass2_hits = 0
    still_unmatched = []
    for idx in unmatched_idx:
        row = cra_match.loc[idx]
        st = row["state_norm"]
        nm = row["name_norm"]
        if not nm:
            still_unmatched.append(idx)
            continue
        candidates = by_state.get(st, pd.DataFrame())
        if candidates.empty:
            still_unmatched.append(idx)
            continue
        # process.extractOne is fastest
        best = process.extractOne(
            nm, candidates["name_norm"].tolist(),
            scorer=fuzz.token_set_ratio, score_cutoff=90,
        )
        if best is None:
            still_unmatched.append(idx)
            continue
        match_str, score, match_idx = best
        f = candidates.iloc[match_idx]
        matches.append({
            "lender_id": row["lender_id"],
            "year": row["activity_year"],
            "RSSDID": f["RSSDID"],
            "CERT": f["CERT"],
            "name_cra": row["name"],
            "name_fdic": f["NAME"],
            "state": st,
            "city": row["city_norm"],
            "match_method": "fuzzy_state",
            "fuzzy_ratio": float(score),
            "confidence": 0.90,
        })
        pass2_hits += 1
    print(f"  hits: {pass2_hits:,}", flush=True)

    print("\nPass 3: city + fuzzy name ≥ 85…", flush=True)
    pass3_hits = 0
    review_queue = []
    truly_unmatched = []
    for idx in still_unmatched:
        row = cra_match.loc[idx]
        st = row["state_norm"]
        ct = row["city_norm"]
        nm = row["name_norm"]
        if not nm or not ct:
            truly_unmatched.append(idx)
            continue
        candidates = by_state.get(st, pd.DataFrame())
        if candidates.empty:
            truly_unmatched.append(idx)
            continue
        in_city = candidates[candidates["city_norm"] == ct]
        if in_city.empty:
            truly_unmatched.append(idx)
            continue
        best = process.extractOne(
            nm, in_city["name_norm"].tolist(),
            scorer=fuzz.token_set_ratio, score_cutoff=75,
        )
        if best is None:
            truly_unmatched.append(idx)
            continue
        match_str, score, match_idx = best
        f = in_city.iloc[match_idx]
        record = {
            "lender_id": row["lender_id"],
            "year": row["activity_year"],
            "RSSDID": f["RSSDID"],
            "CERT": f["CERT"],
            "name_cra": row["name"],
            "name_fdic": f["NAME"],
            "state": st,
            "city": ct,
            "match_method": "city_fuzzy",
            "fuzzy_ratio": float(score),
            "confidence": 0.85 if score >= 85 else 0.60,
        }
        if score >= 85:
            matches.append(record)
            pass3_hits += 1
        else:
            review_queue.append(record)
    print(f"  hits: {pass3_hits:,}  manual queue: {len(review_queue):,}", flush=True)

    out = pd.DataFrame(matches)
    out.to_csv(OUT_DIR / "cra_to_rssd.csv", index=False)
    print(f"\n→ {OUT_DIR / 'cra_to_rssd.csv'}  ({len(out):,} matches)", flush=True)

    if review_queue:
        rq = pd.DataFrame(review_queue)
        rq.to_csv(OUT_DIR / "cra_to_rssd_review_queue.csv", index=False)
        print(f"→ {OUT_DIR / 'cra_to_rssd_review_queue.csv'}  ({len(rq):,} pending)", flush=True)

    total = len(cra_match)
    matched = len(out)
    print(f"\nMatch rate by row: {matched}/{total} = {matched/total*100:.1f}%", flush=True)
    print(f"Unmatched: {len(truly_unmatched):,}  Review pending: {len(review_queue):,}", flush=True)
    print(f"\nNote: target is ≥95% by CRA loan dollar volume — see notes/01_rssd_cra_crosswalk.md", flush=True)


if __name__ == "__main__":
    main()
