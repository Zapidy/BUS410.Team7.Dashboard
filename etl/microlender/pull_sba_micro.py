#!/usr/bin/env python3
"""Pull SBA microlender intermediary list.

Source: https://www.sba.gov/funding-programs/loans/microloans/list-microlenders

The list paginates ~12 items per page across ~8 pages. Each microlender appears
as a `<div class="sba-card-styled-listing node--type-contact contact">` card
with a microformat address (`address-line1`, `locality`, `administrative-area`,
`postal-code`) and a title in `views-field-title`.

Output:
    data/raw/microlender/microlender_list.csv
        columns: name, address, city, state, zip, states_served, snapshot_date

Falls back to a manual-CSV path if scraping fails — save the curated list at
`data/raw/microlender/microlender_list_raw.csv` and re-run.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "raw" / "microlender"

BASE_URL = "https://www.sba.gov/funding-programs/loans/microloans/list-microlenders"
USER_AGENT = "Mozilla/5.0"


def parse_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select(".sba-card-styled-listing.node--type-contact.contact")
    out: list[dict] = []
    for card in cards:
        title = card.select_one(".views-field-title")
        title_text = title.get_text(strip=True) if title else ""
        # First address block (primary address)
        addrs = card.select(".address")
        primary = addrs[0] if addrs else None
        line1 = primary.select_one(".address-line1") if primary else None
        city = primary.select_one(".locality") if primary else None
        state = primary.select_one(".administrative-area") if primary else None
        zip_ = primary.select_one(".postal-code") if primary else None
        states_served = card.select_one(".views-field-field-contact-states-served")
        out.append({
            "name": title_text,
            "address": line1.get_text(strip=True) if line1 else "",
            "city": city.get_text(strip=True) if city else "",
            "state": state.get_text(strip=True) if state else "",
            "zip": zip_.get_text(strip=True) if zip_ else "",
            "states_served": states_served.get_text(strip=True) if states_served else "",
        })
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Manual override
    manual = OUT_DIR / "microlender_list_raw.csv"
    if manual.exists():
        df = pd.read_csv(manual, dtype=str)
        df["snapshot_date"] = pd.Timestamp.today().date().isoformat()
        df.to_csv(OUT_DIR / "microlender_list.csv", index=False)
        print(f"Loaded {len(df):,} microlenders from manual CSV", flush=True)
        return

    rows: list[dict] = []
    sess = requests.Session()
    sess.headers["User-Agent"] = USER_AGENT

    page = 0
    while True:
        url = BASE_URL if page == 0 else f"{BASE_URL}?page={page}"
        print(f"  page={page}…", flush=True)
        try:
            r = sess.get(url, timeout=60)
            r.raise_for_status()
        except Exception as e:
            print(f"    failed: {e}", file=sys.stderr)
            break
        new_rows = parse_page(r.text)
        if not new_rows:
            print(f"    no rows — end of pagination", flush=True)
            break
        rows.extend(new_rows)
        page += 1
        time.sleep(1.0)
        if page > 20:  # safety stop
            break

    if not rows:
        print("\nNo microlenders extracted.", file=sys.stderr)
        print(f"Manual fallback: save a CSV at {manual} with columns", file=sys.stderr)
        print(f"  name, address, city, state, zip, states_served", file=sys.stderr)
        sys.exit(1)

    df = pd.DataFrame(rows).drop_duplicates(subset=["name", "city", "state"])
    df["snapshot_date"] = pd.Timestamp.today().date().isoformat()
    out = OUT_DIR / "microlender_list.csv"
    df.to_csv(out, index=False)
    print(f"\n→ {out}  ({len(df):,} microlenders)", flush=True)


if __name__ == "__main__":
    main()
