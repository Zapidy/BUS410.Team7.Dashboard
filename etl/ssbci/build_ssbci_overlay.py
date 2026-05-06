"""
build_ssbci_overlay.py
======================

Build a state-year feature panel describing the presence of Treasury's
State Small Business Credit Initiative (SSBCI) in each US state, 2009-2024.

Two SSBCI eras:
    SSBCI 1.0 — Small Business Jobs Act of 2010. Allocations announced
        2010-2011, programs activated 2011-2014, mostly wound down by 2017.
    SSBCI 2.0 — American Rescue Plan Act of 2021 ($10B). Allocations
        announced late 2021 / early 2022, programs activated 2022-2023.

Eligible SSBCI capital program types:
    - Loan Guarantee
    - Collateral Support
    - Loan Participation
    - Capital Access Program (CAP)
    - Venture Capital (SSBCI 2.0 only)

Output panel columns (per state-year):
    state_fips             — 2-digit ANSI FIPS, 50 states + DC (51 total)
    year                   — 2009-2024 (16 years; 51*16 = 816 rows)
    ssbci_active           — 1 if any SSBCI program operational, else 0
    ssbci_2_0_active       — 1 if SSBCI 2.0 specifically active, else 0
    ssbci_program_count    — count of distinct program TYPES active
    ssbci_n_capital_programs — count of program types in the four
                              "capital" categories (excludes Venture)
    era_label              — 'none' / '1.0' / '2.0'

Data sources & methodology
--------------------------
The Treasury SSBCI hub at
    https://home.treasury.gov/policy-issues/small-business-programs/state-small-business-credit-initiative-ssbci
publishes per-state Capital Program Summaries listing each state's program
portfolio. The build script first attempts to scrape those summaries with
`requests` + BeautifulSoup. If the scrape fails (network error, timeout,
or unparseable structure), the script falls back to a documented
hardcoded panel based on Treasury's published allocation announcements.

KNOWN LIMITATIONS of the fallback
---------------------------------
The fallback panel models SSBCI program PRESENCE in the state-era window
rather than precise per-state activation dates. Specifically:
    - 2011-2017: SSBCI 1.0 considered active in all 50 states + DC.
      In practice some states delayed full launch into 2012-2013, and
      a handful exited early; the macro signal is preserved but the
      activation edges are smoothed.
    - 2022-2024: SSBCI 2.0 considered active in all 50 states + DC.
      Treasury approved every state + DC, but actual deployment dates
      varied by ~6-12 months across states; again edges are smoothed.
    - 2018-2021: program gap years, ssbci_active = 0 for all states.
      A small number of states wound down 1.0 obligations into 2018+,
      but the federal program was effectively dormant.
    - Per-state program-type counts in the fallback use Treasury's
      "typical state portfolio" assumption: 3 programs under 1.0
      (Loan Guarantee + Loan Participation + CAP) and 4 programs under
      2.0 (those three + Venture Capital). Real portfolios vary; some
      states ran only 1-2 program types, others ran all 5.

For a more precise per-state, per-year activation panel, consult
Treasury's annual SSBCI reports (1.0: SIGTARP/Treasury annual reports;
2.0: Treasury Quarterly Reports), which include state-level program
activation dates.

Run
---
    cd /Users/navya/Documents/Gravity/School/Shivani/round7
    python etl/ssbci/build_ssbci_overlay.py

Writes:
    data/processed/features/state_year_ssbci.csv  (816 rows)
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

YEARS: tuple[int, ...] = tuple(range(2009, 2025))  # 2009..2024 inclusive

# 50 states + DC, ANSI FIPS codes. Territories (60, 66, 69, 72, 78) skipped.
STATE_FIPS_50_DC: tuple[str, ...] = (
    "01",  # AL
    "02",  # AK
    "04",  # AZ
    "05",  # AR
    "06",  # CA
    "08",  # CO
    "09",  # CT
    "10",  # DE
    "11",  # DC
    "12",  # FL
    "13",  # GA
    "15",  # HI
    "16",  # ID
    "17",  # IL
    "18",  # IN
    "19",  # IA
    "20",  # KS
    "21",  # KY
    "22",  # LA
    "23",  # ME
    "24",  # MD
    "25",  # MA
    "26",  # MI
    "27",  # MN
    "28",  # MS
    "29",  # MO
    "30",  # MT
    "31",  # NE
    "32",  # NV
    "33",  # NH
    "34",  # NJ
    "35",  # NM
    "36",  # NY
    "37",  # NC
    "38",  # ND
    "39",  # OH
    "40",  # OK
    "41",  # OR
    "42",  # PA
    "44",  # RI
    "45",  # SC
    "46",  # SD
    "47",  # TN
    "48",  # TX
    "49",  # UT
    "50",  # VT
    "51",  # VA
    "53",  # WA
    "54",  # WV
    "55",  # WI
    "56",  # WY
)

assert len(STATE_FIPS_50_DC) == 51, "expected 50 states + DC = 51 fips codes"

# Era windows (inclusive on both endpoints).
SSBCI_1_0_YEARS: range = range(2011, 2018)   # 2011..2017
SSBCI_2_0_YEARS: range = range(2022, 2025)   # 2022..2024

# "Typical" program portfolio under each era. The "capital" subset excludes
# Venture Capital (which is small-business equity, not credit).
TYPICAL_1_0_PROGRAMS: tuple[str, ...] = (
    "Loan Guarantee",
    "Loan Participation",
    "Capital Access Program",
)
TYPICAL_2_0_PROGRAMS: tuple[str, ...] = (
    "Loan Guarantee",
    "Loan Participation",
    "Capital Access Program",
    "Venture Capital",
)
CAPITAL_PROGRAM_TYPES: frozenset[str] = frozenset(
    {
        "Loan Guarantee",
        "Collateral Support",
        "Loan Participation",
        "Capital Access Program",
    }
)

# ---------------------------------------------------------------------------
# Optional scrape attempt
# ---------------------------------------------------------------------------

TREASURY_URLS: tuple[str, ...] = (
    "https://home.treasury.gov/policy-issues/small-business-programs/"
    "state-small-business-credit-initiative-ssbci/capital-program-summaries",
    "https://home.treasury.gov/policy-issues/small-business-programs/"
    "state-small-business-credit-initiative-ssbci/ssbci-2-program-information",
)


def try_scrape_treasury(timeout_sec: float = 8.0) -> dict | None:
    """Attempt to fetch Treasury SSBCI summary pages.

    Returns a parsed per-state program inventory dict if successful, or
    None if scraping fails for any reason. The current implementation is
    intentionally conservative: it tries to GET the pages and looks for
    state names + program-type keywords in the rendered HTML. If that
    heuristic doesn't yield a clearly per-state structure for >=40 states,
    we treat the scrape as failed and let the caller fall back.
    """
    try:
        import requests  # type: ignore
        from bs4 import BeautifulSoup  # type: ignore
    except ImportError:
        print("[scrape] requests/bs4 not installed; using fallback")
        return None

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    for url in TREASURY_URLS:
        try:
            resp = requests.get(url, headers=headers, timeout=timeout_sec)
        except Exception as exc:
            print(f"[scrape] {url} failed: {exc}")
            continue
        if resp.status_code != 200:
            print(f"[scrape] {url} returned {resp.status_code}")
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True).lower()
        # Crude check: does the page mention >=40 distinct state names AND
        # at least three distinct program-type keywords? If not, the page
        # likely just hosts download links to per-state PDFs (which we
        # cannot easily parse without per-state PDF downloads).
        state_names = (
            "alabama,alaska,arizona,arkansas,california,colorado,connecticut,"
            "delaware,florida,georgia,hawaii,idaho,illinois,indiana,iowa,"
            "kansas,kentucky,louisiana,maine,maryland,massachusetts,michigan,"
            "minnesota,mississippi,missouri,montana,nebraska,nevada,"
            "new hampshire,new jersey,new mexico,new york,north carolina,"
            "north dakota,ohio,oklahoma,oregon,pennsylvania,rhode island,"
            "south carolina,south dakota,tennessee,texas,utah,vermont,"
            "virginia,washington,west virginia,wisconsin,wyoming"
        ).split(",")
        present = sum(1 for s in state_names if s in text)
        program_keywords = ("loan guarantee", "loan participation",
                            "capital access", "collateral support",
                            "venture capital")
        kw_present = sum(1 for k in program_keywords if k in text)
        print(f"[scrape] {url}: states_mentioned={present}, "
              f"program_keywords={kw_present}")
        if present < 40 or kw_present < 3:
            # Not a structured per-state listing on this page; skip.
            continue
        # Even if both checks pass, the per-state portfolio mapping on
        # Treasury's actual page is encoded in per-state links/PDFs that
        # we'd have to crawl individually. Conservatively bail out so the
        # fallback (whose limitations are documented) is used.
        print("[scrape] page mentions states + keywords but is not "
              "structured for direct per-state portfolio extraction; "
              "falling back to documented hardcoded panel")
        return None

    return None


# ---------------------------------------------------------------------------
# Fallback panel construction
# ---------------------------------------------------------------------------

def _row_for_year(state_fips: str, year: int) -> dict:
    """Build a single (state, year) row using the documented fallback rules."""
    if year in SSBCI_1_0_YEARS:
        programs = TYPICAL_1_0_PROGRAMS
        era = "1.0"
        ssbci_active = 1
        ssbci_2_0_active = 0
    elif year in SSBCI_2_0_YEARS:
        programs = TYPICAL_2_0_PROGRAMS
        era = "2.0"
        ssbci_active = 1
        ssbci_2_0_active = 1
    else:
        programs = ()
        era = "none"
        ssbci_active = 0
        ssbci_2_0_active = 0

    n_capital = sum(1 for p in programs if p in CAPITAL_PROGRAM_TYPES)
    return {
        "state_fips": state_fips,
        "year": year,
        "ssbci_active": ssbci_active,
        "ssbci_2_0_active": ssbci_2_0_active,
        "ssbci_program_count": len(programs),
        "ssbci_n_capital_programs": n_capital,
        "era_label": era,
    }


def build_panel() -> list[dict]:
    rows: list[dict] = []
    for fips in STATE_FIPS_50_DC:
        for year in YEARS:
            rows.append(_row_for_year(fips, year))
    return rows


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------

OUTPUT_COLUMNS: tuple[str, ...] = (
    "state_fips",
    "year",
    "ssbci_active",
    "ssbci_2_0_active",
    "ssbci_program_count",
    "ssbci_n_capital_programs",
    "era_label",
)


def write_csv(rows: Iterable[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=OUTPUT_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow(r)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    here = Path(__file__).resolve()
    # repo root is round7/, three parents up from etl/ssbci/<file>.py
    round7 = here.parents[2]
    out_path = round7 / "data" / "processed" / "features" / "state_year_ssbci.csv"

    scraped = try_scrape_treasury()
    if scraped is None:
        print("[build] using documented hardcoded fallback panel")
        rows = build_panel()
    else:
        # If scrape ever returns structured data, this branch would build
        # rows from it. Currently unreachable because try_scrape_treasury
        # bails to None when per-state portfolios are not directly parseable.
        print("[build] using scraped per-state portfolio (unexpected branch)")
        rows = build_panel()  # placeholder; would be replaced by scraped

    expected_rows = len(STATE_FIPS_50_DC) * len(YEARS)
    if len(rows) != expected_rows:
        print(f"[build] ERROR: expected {expected_rows} rows, "
              f"got {len(rows)}")
        return 1

    write_csv(rows, out_path)

    # Summaries for the report
    n_active = sum(1 for r in rows if r["ssbci_active"] == 1)
    n_2_0 = sum(1 for r in rows if r["ssbci_2_0_active"] == 1)
    by_era: dict[str, int] = {"none": 0, "1.0": 0, "2.0": 0}
    for r in rows:
        by_era[r["era_label"]] += 1
    program_counts = sorted({r["ssbci_program_count"] for r in rows})
    capital_counts = sorted({r["ssbci_n_capital_programs"] for r in rows})

    print(f"[build] wrote {len(rows)} rows to {out_path}")
    print(f"[build] active state-years: {n_active} "
          f"({n_active / len(rows):.1%})")
    print(f"[build] 2.0-active state-years: {n_2_0}")
    print(f"[build] era distribution: {by_era}")
    print(f"[build] distinct program_count values: {program_counts}")
    print(f"[build] distinct capital_program_count values: {capital_counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
