#!/usr/bin/env python3
"""Pull macroeconomic time-series from FRED (St. Louis Fed) — no API key required.

Uses the public fredgraph.csv endpoint, which serves any series ID as CSV.

Series pulled by default:
    UNRATE     - Unemployment rate (monthly)
    DGS10      - 10-year Treasury yield (daily)
    CPIAUCSL   - CPI All Urban Consumers (monthly)
    HOUST      - Housing starts (monthly)
    DRTSCILM   - Senior loan officer survey: net % tightening C&I standards (quarterly)
    FEDFUNDS   - Effective federal funds rate (monthly)

These are time-varying but tract-invariant — they let the model learn cyclical
context without overfitting it to specific tracts.
"""
from __future__ import annotations
import ssl
import urllib.request
import urllib.parse
from pathlib import Path

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "raw" / "macro"

SERIES = {
    "UNRATE":   "Unemployment rate (monthly, 1948–)",
    "DGS10":    "10-year Treasury constant-maturity yield (daily)",
    "CPIAUCSL": "CPI All Urban Consumers (monthly)",
    "HOUST":    "Housing starts (monthly)",
    "DRTSCILM": "Senior Loan Officer Survey — % tightening C&I standards (quarterly)",
    "FEDFUNDS": "Effective federal funds rate (monthly)",
}

START = "2009-01-01"
END = "2024-12-31"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for series_id, desc in SERIES.items():
        url = (f"https://fred.stlouisfed.org/graph/fredgraph.csv?"
               f"id={series_id}&cosd={START}&coed={END}")
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        out = OUT_DIR / f"{series_id}.csv"
        try:
            with urllib.request.urlopen(req, timeout=20, context=SSL_CTX) as resp:
                body = resp.read()
            out.write_bytes(body)
            n_lines = body.count(b"\n")
            print(f"  OK    {series_id:10s}  {len(body):>9,} bytes, {n_lines} rows  — {desc}")
        except Exception as e:
            print(f"  ERR   {series_id}: {e}")


if __name__ == "__main__":
    main()
