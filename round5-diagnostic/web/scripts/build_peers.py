#!/usr/bin/env python3
"""Compute the 3 demographic peer tracts for every tract.

A peer is:
  1. in the same state
  2. in the *thriving SBA* cohort (sba_score >= 80)
  3. closest to the source tract on z-scored [pov, min, inc, pop]

Output:
    web/data/_lookup/peers.json   {tract_fips: [peer_fips_1, peer_fips_2, peer_fips_3]}

Notes:
    A source tract that is itself thriving still gets peers — it's just
    matched against the rest of the thriving cohort. The dashboard surfaces
    these only when the user clicks a high-risk tract; they exist for all.
    States with fewer than ~10 thriving tracts skip — too few to peer.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
WEB_DATA = ROOT / "web" / "data"
LOOKUP = WEB_DATA / "_lookup"
PANEL_PATH = ROOT / "data" / "processed" / "panel" / "tract_year_with_target.parquet"
SBA_PATH = LOOKUP / "sba_tract.parquet"
OUT = LOOKUP / "peers.json"

THRIVING_THRESHOLD = 80.0
K_PEERS = 3
DEMO_COLS = ["pct_poverty", "pct_minority", "median_hh_income", "population"]
MIN_STATE_POOL = 10


def load_demographics() -> pd.DataFrame:
    print("Loading panel demographics (latest year per tract)…")
    panel = pd.read_parquet(PANEL_PATH, columns=[
        "tract_fips", "year", *DEMO_COLS,
    ])
    panel = panel.dropna(subset=["population"])
    panel = panel.sort_values(["tract_fips", "year"], ascending=[True, False])
    latest = panel.drop_duplicates(subset="tract_fips", keep="first")
    latest = latest.dropna(subset=DEMO_COLS)
    latest["state_fips"] = latest["tract_fips"].str[:2]
    print(f"  tracts with full demographics: {len(latest):,}")
    return latest


def main() -> int:
    if not SBA_PATH.exists():
        print(f"ERROR: missing {SBA_PATH}; run build_sba_tract.py first", file=sys.stderr)
        return 2
    if not PANEL_PATH.exists():
        print(f"ERROR: missing {PANEL_PATH}", file=sys.stderr)
        return 2

    demo = load_demographics()
    sba = pd.read_parquet(SBA_PATH)
    df = demo.merge(sba[["tract_fips", "sba_score"]], on="tract_fips", how="left")
    df["sba_score"] = df["sba_score"].fillna(0.0)

    peers_out: dict[str, list[str]] = {}
    n_states = 0
    n_tracts_with_peers = 0
    for state, sub in df.groupby("state_fips"):
        thriving = sub[sub["sba_score"] >= THRIVING_THRESHOLD].reset_index(drop=True)
        if len(thriving) < MIN_STATE_POOL:
            continue
        n_states += 1

        # z-score on the *full state population* so source and pool share scale
        means = sub[DEMO_COLS].mean()
        stds = sub[DEMO_COLS].std().replace(0, 1.0)
        thriving_z = ((thriving[DEMO_COLS] - means) / stds).to_numpy()
        thriving_fips = thriving["tract_fips"].to_numpy()

        # For each tract in the state (not just high-risk), find 3 nearest peers
        # in the thriving pool. Brute-force is fine — even Texas's ~5500 tracts
        # × ~1100 thriving = 6M floats per state, runs in <1s with numpy.
        sub_z = ((sub[DEMO_COLS] - means) / stds).to_numpy()
        sub_fips = sub["tract_fips"].to_numpy()

        # Pairwise squared distances. dist[i,j] = ||sub_z[i] - thriving_z[j]||^2
        diff = sub_z[:, None, :] - thriving_z[None, :, :]
        dist2 = (diff * diff).sum(axis=2)

        for i, fips in enumerate(sub_fips):
            row = dist2[i]
            # Mask self (if the source tract is in the thriving pool too)
            mask = thriving_fips != fips
            row_masked = np.where(mask, row, np.inf)
            k = min(K_PEERS, mask.sum())
            if k == 0:
                continue
            top = np.argpartition(row_masked, k - 1)[:k]
            top = top[np.argsort(row_masked[top])]
            peers_out[fips] = [str(p) for p in thriving_fips[top]]
            n_tracts_with_peers += 1

    print(f"States with peer pools: {n_states}")
    print(f"Tracts with peers: {n_tracts_with_peers:,}")

    with OUT.open("w") as f:
        json.dump(peers_out, f, separators=(",", ":"))
    print(f"  → {OUT} ({OUT.stat().st_size/1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
