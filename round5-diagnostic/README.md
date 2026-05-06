# Round 5 — Credit Desert Prediction (Rebuild)

Rebuild of the BUS410 Team 7 credit-desert model with a longer panel, additional supply-side data sources, and walk-forward temporal validation. The Round-4 single-split methodology is preserved in [../round4/](../round4/) as historical reference.

## Why a rebuild

Round 4 was data-constrained, not architecture-constrained:

- CRA disclosure files only loaded 2014–2023 → pre-2014 train years had 0% CRA coverage → CRA had to be bolted on as a separate post-2014 model track.
- No HMDA, no SBA — the two largest supply-side credit-access datasets were missing.
- Single chronological split (train 2014–2017, val 2018, test 2019) — a single point estimate of out-of-sample AUC, no walk-forward distribution.
- Multiple plausible leakage paths (ACS 5-year forward leak, behavioral-feature target-leakage, CRA-reporter survivor bias) not addressed in the methodology.

Round 5 fixes all five.

## Key decisions

- **Temporal scope:** 15 years, **2009–2024**. Rationale in [notes/00_methodology.md §1](notes/00_methodology.md).
- **Data sources:** HMDA (loan-level mortgage), CRA disclosure (full backfill), SBA 7(a)/504, FDIC SoD, FDIC failures, NIC structure, ACS 5-year (lag-aware), USDA RUCA, EIG DCI, Opportunity Zones, persistent poverty.
- **Validation:** 8-fold walk-forward by year + leave-one-state-out and leave-one-MSA-out as spatial-leakage robustness checks.
- **Target:** continuous lender-presence regression, with three flavors (branch / origination / service desert) modeled jointly. Survival framing as alternative.
- **Tract harmonization:** project all years onto 2020 tract vintage via Census Bureau relationship files (already pulled — no NHGIS account needed).

## Read first

1. [notes/00_methodology.md](notes/00_methodology.md) — full methodology, leakage taxonomy, ETL plan, feature additions, validation framework, and overlooked failure modes.

## Layout

```
round5/
├── notes/         methodology + running logs + findings
├── etl/           per-source ingestion scripts
├── data/
│   ├── raw/       source files (gitignored)
│   ├── processed/ per-source tract-year parquets
│   └── crosswalks/ NHGIS, GeoCorr, ZIP-tract
├── features/      panel assembly
├── train/         walk-forward + calibration
├── models/        trained model artifacts per fold
└── diagnostics/   robustness checks, ablations, figures
```

## Phases

| Phase | Focus | Effort |
|---|---|---|
| 0 | Alignment (methodology brief) | done |
| 1 | ETL all six sources | 5–8 d |
| 2 | Features + target + tract harmonization | 3–4 d |
| 3 | Walk-forward training, calibration, top-N precision | 3–5 d |
| 4 | Diagnostics + writeup | 2–3 d |
| 5 | Refreshed showcase map with CI bands | 2 d |

**Total: 15–22 working days of focused effort.**
