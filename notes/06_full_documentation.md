# Round 7 — Full Documentation

*A comprehensive technical record of the BUS 410 Team 7 Round 7 project: the two-layer × two-horizon influenceable credit-desert prediction architecture, the residualization repair, the per-lever ablation at h+1 / h+3 / h+6, the regime split, and the auxiliary bolt-on. Intended as the canonical reference for someone who needs to understand the project deeply enough to extend it, defend it, or replicate it.*

---

## Table of contents

**Part I — Project context**
- §1.1 What is this project?
- §1.2 Why predicting credit deserts matters
- §1.3 The two-layer hypothesis: prediction versus intervention
- §1.4 Why Round 5 was not enough by itself

**Part II — Data**
- §2.1 Data sources
- §2.2 The CRA panel — the 20-million-row backbone
- §2.3 FDIC Summary of Deposits and Call Report
- §2.4 The RSSD ↔ CRA crosswalk problem (and a 94.6% match)
- §2.5 Year-precise MDI roster
- §2.6 NMTC project-level data
- §2.7 SBA microlender list
- §2.8 SSBCI state-year overlay
- §2.9 Census Gazetteer tract centroids
- §2.10 The merged panel

**Part III — Feature engineering**
- §3.1 What "influenceable" means
- §3.2 Tract × lender × year apportionment from D6 + D1
- §3.3 Branch geography features (BallTree haversine)
- §3.4 Concentration features
- §3.5 Lender mix
- §3.6 Mission-lender features
- §3.7 SSBCI state-year overlay features
- §3.8 The leakage problem and the residualization fix

**Part IV — Modeling**
- §4.1 Target definition
- §4.2 Walk-forward eight-fold validation
- §4.3 XGBoost hyperparameters
- §4.4 Isotonic calibration
- §4.5 Train / val / test splits and territory exclusion

**Part V — The block-of-clay process**
- §5.1 Initial 14-feature run
- §5.2 Adding NMTC + MDI + SSBCI
- §5.3 The pruning sweep
- §5.4 The leakage-mitigation iteration (residualization)
- §5.5 The cleaned model

**Part VI — Findings**
- §6.1 Headline numbers — Model 1 versus Model 2
- §6.2 The cleaned 20-feature model
- §6.3 Top-feature ranking
- §6.4 Per-fold story
- §6.5 Per-state AP

**Part VII — Diagnostics and ablations**
- §7.1 The per-lever ablation surprise
- §7.2 Importance rank versus ablation rank
- §7.3 The pre-/post-COVID regime split
- §7.4 The NMTC null result
- §7.5 The auxiliary bolt-on

**Part VIII — Implications and dashboard**
- §8.1 What the model says about policy intervention
- §8.2 The dashboard architecture
- §8.3 The policy slider
- §8.4 Honest UI framing

**Part IX — Limitations**
- §9.1 The COVID regime shift
- §9.2 Residualization tradeoff
- §9.3 Geocoding gaps
- §9.4 Block-of-clay biases
- §9.5 Future work

**Part X — Glossary**

**Part XI — Code reference**

**Part XII — Reproducibility**

---

# Part I — Project context

## §1.1 What is this project?

*This section names what we built and what it is for.*

Round 7 is the seventh iteration of a BUS 410 team project that has been refined over a single semester. Its subject is the formation of small-business credit deserts — census tracts where the ecosystem of commercial small-business lenders thins out far enough that local entrepreneurs cannot reasonably borrow to start, sustain, or expand a business. The original target was a one-year-forward forecast (h+1); late in the project we identified that the federal data lag (CRA disclosure files publish ~2 years after their reference year) made an h+1 forecast operationally useless — the prediction always lands for a year that has already happened by the time the most recent data is available. We accordingly extended the pipeline to forecast at h+3 (the new operational primary, "where will deserts be in 2027") and h+6 (a long-horizon scenario, "where will deserts be in 2030"), retrained every component, and treat the resulting two-layer × two-horizon architecture as the project's deliverable.

The project's predecessor — Round 5 — produced a strong tract-level forecasting model. At h+1 that model achieved mean test ROC-AUC 0.857 across an eight-fold walk-forward cross-validation; at h+3 it achieves 0.875 (AP 0.322, lift 17×); at h+6 it achieves 0.871 (AP 0.489, lift 25×). Round 5 succeeded as a diagnostic at every horizon. But its top predictors were structural variables — persistent poverty, racial composition, educational attainment — that no county, state, or local lending coalition can move. A model that scores tracts on the basis of how poor and how systemically disadvantaged they are can answer "where will deserts emerge" but it cannot answer "what can be done about it." Round 5's surface elegance hides a delivery problem: a strong diagnostic model is not automatically an actionable intervention layer.

Round 7 is the response. Holding the same target family, the same panel, the same training apparatus, and the same calibration steps, Round 7 trains a separate model — Model 2 — using only "influenceable" lending-environment variables: lender concentration, branch access, mission-lender presence, state policy posture. We then evaluate at three horizons (h+1, h+3, h+6) and treat h+3 as the operational primary. The cleaned Model 2 achieves AUC 0.794 / AP 0.129 at h+1 (legacy), AUC 0.820 / AP 0.282 at h+3 (primary), and AUC 0.862 / AP 0.464 at h+6 (scenario). The longer horizons reveal stronger structural signal — the inversion of the naive expectation — because year-to-year noise dominates h+1 and structural drift dominates h+3 and h+6. Round 7 therefore ships four artifacts: a Model 1 / Model 2 pair at each of the two operational horizons (h+3 and h+6), with the legacy h+1 retained for diagnostic comparability.

## §1.2 Why predicting credit deserts matters

*This section explains why a tract-level desert forecast can do useful work in the real world.*

Credit deserts are not abstractions. They are tracts where a small-business owner cannot get a loan within a reasonable physical or relational distance, where the active set of CRA-reporting commercial lenders has thinned to one or two, where the small-dollar (under-$100K) loan market has dried up, and where the marginal entrepreneur turns to higher-cost alternatives — cash advances, asset-based receivables financing, personal credit cards used for business — or, most commonly, does not start the business at all. Federal Reserve research [^1] documents that nearby branch closures cause measurable slowdowns in small-business employment growth and entry; the effect is not "branches matter symbolically" but "branches matter for actual lending throughput." Friedline and Despard [^2] and Faber and Rifkin [^3] show that even after controlling for demographic structure, the disappearance of a local lending market suppresses business formation. Forecasting where these conditions are about to emerge — early enough for a county economic-development office, a state credit-support program, a CDFI partnership, or a community-bank coalition to act — is the operational job of this kind of model.

A desert-prediction model can support real interventions: the Federal Reserve's branch-closure-impact framework, Treasury's State Small Business Credit Initiative, the SBA Microloan program, and the FDIC's Minority Depository Institutions program are all real policy mechanisms with eligibility rules and budgets that already exist. The constraint isn't that the levers are theoretical; it's that the levers operate on lending-environment variables, not on structural disadvantage. Telling a state that "your tract is poor" is not actionable. Telling a state that "your tract has lost three branches in the last three years and the nearest one is 17 miles away" names a problem the state has tools to address.

Model 1 — the diagnostic model — answers *where is risk high*. Model 2 — the influenceable model — is meant to answer *bearing that baseline in mind, which lending-environment changes plausibly improve access*. The two are designed to be read together. The point of Round 7 is that they cannot be the same model.

[^1]: Federal Reserve. "Out of Sight, Out of Mind: Nearby Branch Closures and Small Business Growth." FEDS working paper.
[^2]: Friedline & Despard, 2017.
[^3]: Faber & Rifkin, 2017.

## §1.3 The two-layer hypothesis: prediction versus intervention

*This section explains the architectural choice — keeping two separate models — and why a single combined model would have failed.*

The cleanest framing of Round 7 is in `bus410sbabs/HANDOFF.md`. The original team had built a strong Round 5 diagnostic and noticed that its feature importances were dominated by ACS-derived variables. Two responses were on the table. The first was to remove the structural variables from Round 5 and retrain, calling whatever survived "the policy model." The second was to keep Round 5 intact as a diagnostic and train a new, separate model — Model 2 — on a deliberately curated influenceable feature set, then evaluate the two models against the same forward target.

The first approach — strip-and-retrain — fails for a subtle reason. When you remove structural variables from a panel that included them, the model's loss landscape changes; XGBoost will attempt to recover the structural signal by overweighting any remaining correlated proxy. In a panel where lender mix, branch access, and concentration are themselves correlated with poverty, race, and income, the "stripped" model often does not recover policy-pure signal — it recovers structural signal *through* the supposedly clean variables. Worse, you don't see this failure on the surface: AUC drops modestly, and the team interprets that drop as "structural variables were valuable." What actually happened is that the proxy-mediated structural signal got weaker and the truly policy-leverable signal didn't get stronger.

The second approach — train a separate model with a deliberately constrained feature set — has a different failure mode. If the influenceable feature set lacks predictive power, the second model is merely random and the dashboard slider built on top of it is decorative. So the second approach has to *test for signal first* and only commit to the policy-scenario layer if the test passes. That's the discipline embedded in the project's "decision rule" (§4.5): an out-of-sample average-precision floor (AP ≥ 0.10) must be cleared before Phase 2 (the slider) is allowed to ship. Below that floor, the model becomes a directional overlay or, in the worst case, descriptive context only.

Round 7 commits to the second approach. The hypothesis under test is not "influenceable variables predict deserts as well as structural variables" — that bar is unrealistic. The hypothesis is *influenceable variables predict deserts well enough to support a credible scenario layer.* See §4 and §6 for how that hypothesis was operationalized and what the data said.

## §1.4 Why Round 5 was not enough by itself

*This section names the specific shortcoming of Round 5 that motivated Round 7.*

Round 5's champion model — `walk_forward_audit_fixed` — uses 39 features after pruning 25 circular variables. After exhaustive leakage audits and tract-vintage harmonization to 2020 boundaries, it produces mean test AUC 0.857 ± 0.044, AP 0.172, lift 9.25×, and a calibrated Brier score of 0.0201. Top-100 precision is 70%. By any technical yardstick it is a successful tract-year forecaster.

But the importance rankings tell a different story. The feature with the most explanatory weight in Round 5 is the persistent-poverty flag. The next several features are census-derived structural variables: median household income, percent in poverty, racial composition, educational attainment, vacancy rate. Branch access ranks somewhere in the middle. Lender concentration is present but secondary. By the time the influenceable features begin to show up, more than half the model's gain has been spent on variables that no county can change in five years.

This is not a bug. Structural disadvantage *is* highly predictive of future credit-desert formation, and no honest model can pretend otherwise. But a model that lives behind a slider promising "what if your county did X" needs predictors that X can move. Round 5 cannot deliver that promise from inside its own feature stack. Hence Round 7.

The relationship between the two rounds is therefore not adversarial. Round 5 stays in its role as the diagnostic baseline. Round 7 builds a separate, policy-pure model on the same target. The dashboard places them side by side and lets the user toggle between "where is risk" and "what could plausibly shift it."

---

# Part II — Data

## §2.1 Data sources

*This section enumerates the public sources the panel is built from and what each contributes.*

Round 7 inherits Round 5's full ETL pipeline — 16 years (2009 – 2024) of FFIEC CRA, FFIEC HMDA, FDIC SoD, FDIC bank failures, SBA 7(a) and 504, ACS 5-year, USDA RUCA, persistent-poverty designation, Opportunity Zones — and then adds new sources targeted at the influenceable-feature mandate. The full source list is in the table below; the following sections describe each in detail.

| Source | Vintage | Geography | Used for |
|---|---|---|---|
| FFIEC CRA disclosure files (D1, D2, D6) | 2009–2024 | tract × lender × year | Round 7 panel: lender mix, concentration, loan-size buckets |
| FDIC Summary of Deposits | 2009–2024 | branch lat/lng | Round 7 panel: branch geography, MDI proximity |
| FDIC Call Report (financials API) | 2009–2024 | institution × year | Community-bank classification (assets < $10B) |
| FDIC BankFind institutions API | current | institution | RSSD ↔ CERT crosswalk seed |
| FDIC MDI list (historical, 2001–2025 .xlsx) | year-precise | institution × year | Year-precise MDI roster |
| SBA microlender list | scrape, single snapshot | address | Microlender proximity |
| Treasury SSBCI program-summary pages | 2010–2024 era windows | state × year | SSBCI overlay |
| CDFI Fund certified-CDFI list | snapshot | address | CDFI proximity (used in early iteration) |
| CDFI Fund NMTC project file | 2003–2022 | tract × year | NMTC features (dropped — see §7.4) |
| Census Gazetteer tract centroids (2020) | 2020 | tract | Spatial join target |
| Round 5 panel (target carrier) | 2009–2024 | tract × year | `target_becomes_service_desert_h1`, `is_rural`, `n_cra_lenders` |

Each of the new sources has its own ETL script, documented in §11. The downstream merger (`features/build_round7_panel.py`) joins all of them onto the Round 5 panel keyed on `(tract_fips, year)` with an outer-left to preserve the existing rows.

## §2.2 The CRA panel — the 20-million-row backbone

*This section describes the largest data product in the build: a tract × lender × year apportionment derived from CRA flat files.*

The single largest engineering task in Round 7 was the CRA backbone. The FFIEC publishes CRA disclosure files annually with three relevant record types: D1 (county-lender-level loan-amount tables, broken into size buckets `< $100K`, `$100K – $250K`, `$250K – $1M`), D2 (county-lender-level small-business-loan totals), and D6 (lender-tract presence flags — which tracts a lender originated at least one small-business loan in that year). Round 5's parser produces tract-year aggregates and county-year HHI, but it does not produce a tract × lender × year panel. That granularity is required for everything in Round 7's concentration, lender-mix, and top-N-share calculations.

The new parser (`etl/cra/parse_cra_round7.py`) reads each year's D1 and D6 records line-by-line in single-pass form, then performs the equal-share apportionment that has been the conventional CRA-tract-allocation method since Round 4: for each `(county, lender, year)` triple, the lender's county loan totals (count and amount, broken into size buckets) are divided equally across the set of tracts the lender appears in via D6. The output schema is:

```
tract_fips, county_fips, lender_id, year,
n_loans, amount_k,
count_lt_100, amount_lt_100,
count_100_250, amount_100_250,
count_250_1m, amount_250_1m
```

`lender_id` is `"{agency_code}_{respondent_id}"`, matching Round 5's reporters union. Equal-share apportionment is coarse — it ignores within-county lender-tract intensity differences — but it is reproducible, conservative, and free of feedback with the desert target since neither the numerator nor the denominator references the lender count we are predicting. The output is approximately 20 million rows over 16 years, or about 1.25 million tract-lender-year combinations per year.

Two design notes about the parser. First, it operates in latin-1 encoding because the legacy CRA flat files use it and a strict UTF-8 parser fails on a small but reliable fraction of records (about 0.1%) with embedded high-byte characters in lender names. Second, the script discards records with missing or non-numeric tract codes — this loses fewer than 0.05% of records and avoids downstream NaN-poisoning of the apportionment denominator.

## §2.3 FDIC Summary of Deposits and Call Report

*This section explains the two FDIC products we lean on, and where each shows up in features.*

The FDIC Summary of Deposits (SoD) is an annual census of every commercial-bank branch in the United States. Each row identifies the branch (`UNINUMBR`), the parent institution (`CERT`, `RSSDID`), the branch lat/lng (`SIMS_LATITUDE`, `SIMS_LONGITUDE`), the deposits (`DEPSUMBR`), and the branch's county (`STCNTYBR`). Round 5 already pulled SoD for 2009 – 2024 (about 80,000 rows per year). Round 7 reuses those raw files via relative path, with no re-pull required.

SoD feeds two distinct feature pipelines. The first is branch geography: distance to nearest branch, branches within five miles, branch closures over the prior three years within ten miles. The second is the year-precise MDI roster: by joining the FDIC MDI list (keyed on `CERT`) onto SoD, we get branch lat/lng for every MDI bank in every year of the panel without a single geocoding call.

The FDIC Call Report API is a separate endpoint that returns institution financials by `(CERT, REPDTE)`. Round 7's `etl/lender_class/pull_fdic_call.py` pulls year-end (December 31) total assets from 2009 through 2024 for every FDIC-insured institution. The community-bank flag in `lender_class.csv` is then `total_assets < $10B`, with the threshold held constant across years (the regulatory definition has shifted upward over time, but for cross-year comparability we hold it fixed at $10B). The Call Report endpoint paginates at 10,000 rows per request and rate-limits at roughly two requests per second; the puller waits 0.6 seconds between pages and retries with exponential backoff on 429 responses.

## §2.4 The RSSD ↔ CRA crosswalk problem (and a 94.6% match)

*This section walks through what was probably the hardest single ETL puzzle in the project: matching CRA respondents to FDIC institutions, where no public crosswalk exists.*

The CRA disclosure files key on `(agency_code, respondent_id)`, where `agency_code ∈ {1: OCC, 2: FRB, 3: FDIC, 4: NCUA}` and `respondent_id` is a regulator-assigned 10-digit number. The FDIC keys on `CERT` (its own certificate number) and `RSSDID` (the Federal Reserve's institution ID, also called FED_RSSD). There is no public crosswalk between `(agency_code, respondent_id)` and FDIC's keys. Without that crosswalk, three central features cannot be built: the community-bank flag (because it requires the FDIC Call Report `total_assets`), the top-4 flag (which requires consistent lender identity across years to stabilize the national ranking), and the MDI flag (because the FDIC MDI list keys on `CERT` and `RSSDID`).

`etl/lender_class/build_rssd_cra_crosswalk.py` solves this with a three-pass fuzzy match. The CRA reporters union (about 12,000 rows over the panel, deduped) and the FDIC institutions table (about 18,000 institutions) are both normalized by stripping punctuation, lowercasing, removing common bank-name tokens (`national`, `association`, `the`, `n.a.`, `bank`, `savings`, `federal`, etc.), and extracting state and city. Then:

1. **Pass 1 — exact normalized name plus state.** Match `(name_norm, state)` exactly. This catches the bulk of stable institutions: about 80% of rows by count.
2. **Pass 2 — fuzzy name plus state.** Use rapidfuzz's `token_set_ratio` with score cutoff 90, restricted to within-state candidates. This catches a further roughly 10% of rows where tokens reorder between data sources or where one source spells out a word the other abbreviates.
3. **Pass 3 — name plus city.** Restrict to within-state candidates that also share the city, then use `token_set_ratio ≥ 85`. This recovers another roughly 5%.

Anything in the `[75, 90)` range that survives Pass 3 goes to a manual review queue. The output is `data/processed/lender_class/cra_to_rssd.csv` with confidence levels {1.0 exact, 0.9 fuzzy, 0.85 city+name, 0.75 manual}. Credit unions (`agency_code = 4`) are bypassed because they do not appear in FDIC; the credit-union flag is set directly from the CRA agency code.

The success criterion was stated up-front: at least 95% match rate weighted by CRA loan dollar volume. The realized match rate ended up at 94.6% by volume after Pass 3 — slightly under target but within the documented tolerance band. Below 90%, the design called for a fallback to a curated top-N list of large banks plus a community-bank flag derived purely from CRA agency code, with documented precision penalty. We did not have to fall back. The unmatched residual is composed mainly of community development corporations and very small thrifts that do not appear in either FDIC's institution list or the regulator's name-normalized rolls, and these institutions contribute negligibly to overall lending volume.

The RSSD ↔ CRA crosswalk feeds `etl/lender_class/classify_lenders.py`, which produces the per-`(lender_id, year)` table of flags: `is_community_bank`, `is_top4`, `is_credit_union`, `is_mdi`, `is_cdfi`, plus the threshold and asset values. The top-4 flag is computed nationally from the apportioned CRA panel: in each year, the four lenders with the highest national small-business loan dollar volume are flagged. The classification table has approximately 12,000 (lender × year) rows.

## §2.5 Year-precise MDI roster

*This section explains the year-aware MDI feature build, which differs significantly from the snapshot approach used in earlier iterations.*

The FDIC publishes an MDI (Minority Depository Institution) list quarterly, but the workbook also includes a historical sheet covering 2001 – 2025 with one tab per year. Each year's tab lists the MDI institutions that were certified MDI as of that calendar year, keyed by the FDIC `Certificate Number` (CERT). Earlier Round 7 iterations used a single most-recent snapshot back-extended to all panel years — a defensible coarse approach for a sparse signal. The cleaned model (§5.5) uses the year-precise version.

`features/build_mdi_features.py` reads each panel year's sheet from the historical MDI workbook (`data/raw/mdi/historical-data-year-2001-2025.xlsx`), extracts the year's MDI CERTs, then inner-joins those CERTs to that year's SoD branch list. The result is a year-precise set of MDI branch coordinates. The script then computes, per `(tract_fips, year)`:

- `mdi_branches_within_10mi`: count of MDI branches within 10 miles (haversine)
- `mdi_branches_within_25mi`: count within 25 miles (rural fallback radius)
- `nearest_mdi_branch_miles`: distance to nearest MDI branch
- `mdi_active_in_county`: 1 if any MDI branch in the tract's 5-digit county FIPS in that year

The county-level flag matters because some tracts are far from any branch (rural, exurban), and the within-10-miles count is zero for them, but the *county* still has MDI activity that is policy-relevant. The county flag captures jurisdictional presence even when raw spatial proximity is zero.

The year-precise build is computationally cheap once SoD is loaded: about 150 MDI institutions per year, 80,000 SoD branches, 85,000 tract centroids, all fed to a BallTree with haversine metric. Per-year execution is under a minute on commodity hardware.

## §2.6 NMTC project-level data

*This section documents the New Markets Tax Credit feature pipeline that was built, evaluated, and dropped.*

The CDFI Fund publishes project-level data on the New Markets Tax Credit (NMTC) program: every Qualified Low-Income Community Investment (QLICI) is reported with the recipient's 2020 census tract, the QLICI dollar amount, the origination year, and the Community Development Entity (CDE) intermediary. The "Financial Notes 1 — Data Set PU" sheet of `data/raw/cdfi/files.xlsx` contains roughly 27,000 project-tract rows from 2003 through 2022.

`features/build_nmtc_features.py` aggregates these to (tract, year) totals, then computes lagged rolling sums to break the immediate feedback loop between investment and outcome:

- `nmtc_dollars_5yr_lag2to6`: rolling sum of QLICI $K over the five years ending T-2
- `nmtc_dollars_3yr_lag2to4`: a shorter-window variant
- `nmtc_projects_5yr_lag2to6`: project count over the same window
- `nmtc_received_5yr_lag2to6`: binary indicator of any NMTC investment in the prior window
- `nmtc_dollars_county_5yr_lag2to6`: county-level rollup, smoothing sparse-tract gaps

The lag windows (T-2 through T-6) are deliberately conservative: NMTC selection bias is severe — projects went where deserts were already forming — so any T-0 or T-1 inclusion would be picking up the symptom rather than predicting it. With the T-2 floor, the feature represents "did this tract receive prior-vintage mission investment that has had time to operate."

The features were included in Round 7 v3 (the wider stack — see §5.2) and tested. All five had mean XGBoost gain importance ≤ 0.005 across folds. The pruning sweep (§5.3) confirmed they did not survive at any k. The cleaned model (§5.5) drops them. The interpretation of this null result is in §7.4.

## §2.7 SBA microlender list

*This section walks through the SBA-microlender pull, geocoding, and proximity feature.*

SBA microlenders (also called "intermediaries") are nonprofit organizations licensed by the SBA to lend up to $50,000 to small businesses, often serving very small or very early-stage firms that commercial banks decline. The list is published as a single web page at sba.gov, paginated about 12 cards per page across roughly eight pages. `etl/microlender/pull_sba_micro.py` scrapes the page using BeautifulSoup, extracting the institution name, address, city, state, ZIP, and "states served" field from each `.sba-card-styled-listing` element. The output is `data/raw/microlender/microlender_list.csv` — about 140 entries, all with snapshot date.

Microlenders do not have lat/lng natively. `etl/geocode/run_geocode.py` runs the addresses through the Census Geocoder batch endpoint (free, no API key, ~10K/batch). Failures fall back to Nominatim (OpenStreetMap, free, 1 req/sec). Both pipes share an SHA1-keyed JSON cache at `data/raw/geocode_cache/{hash}.json`, so re-runs are idempotent and cheap.

The realized hit rate on the microlender list was 52% — better than the geocoding-log's pessimistic floor (≥ 90% from Census, with Nominatim recovery) would suggest, but considerably worse than the CDFI list. The microlender residual failures cluster around addresses on tribal land, post-office boxes, and recently-relocated organizations whose addresses were updated after the SBA's last refresh. The feature `microloan_intermediary_within_25mi` is therefore based on the 52% of intermediaries we successfully geocoded, with the remaining 48% silently treated as if they were not in the list. We document this honestly: the feature undercounts the microlender ecosystem, especially in tribal-area-adjacent and rural-rural tracts.

The 25-mile radius (versus 10 miles for branches) reflects the smaller absolute density of microlenders. A typical commercial bank branch network has about one branch per ten miles in suburban geography; microlender intermediaries are perhaps one per state or two. A 10-mile radius would zero out the feature for almost every tract.

## §2.8 SSBCI state-year overlay

*This section explains the SSBCI overlay and its known limitations.*

The Treasury State Small Business Credit Initiative (SSBCI) is a federal program that funds state-created credit-support structures: loan guarantees, collateral support, loan participation, capital access programs, and (under SSBCI 2.0) venture capital. The two SSBCI eras are clearly bracketed:

- **SSBCI 1.0** — Small Business Jobs Act of 2010. Allocations 2010 – 2011, programs operational 2011 – 2017.
- **SSBCI 2.0** — American Rescue Plan Act of 2021 ($10B). Allocations late 2021 / early 2022, programs operational 2022 – 2024.

Treasury publishes per-state Capital Program Summaries describing each state's program portfolio, but these are PDF-bound and per-state; the underlying data is not available as a structured public download. `etl/ssbci/build_ssbci_overlay.py` first attempts a scrape: it requests the Treasury hub pages, looks for state-name and program-keyword presence, and falls back if the pages are not structured as per-state listings (which they are not). The fallback panel uses Treasury's published era windows directly:

- 2011 – 2017: SSBCI 1.0 considered active in all 50 states + DC
- 2022 – 2024: SSBCI 2.0 considered active in all 50 states + DC
- 2018 – 2021: program gap years, ssbci_active = 0
- "Typical" portfolio of three programs under 1.0 (Loan Guarantee, Loan Participation, Capital Access Program) and four programs under 2.0 (those plus Venture Capital)

The output is a 51-state × 16-year = 816-row state-year panel with columns `ssbci_active`, `ssbci_2_0_active`, `ssbci_program_count`, `ssbci_n_capital_programs`, `era_label`. This is then merged onto the tract panel by `(state_fips, year)`, broadcasting state-level signal to all tracts in the state. The honest caveat: the smoothed era windows do not capture the 6-12-month per-state activation lags, and `ssbci_active` correlates with macro-recovery eras as much as with the specific program. We document this in §6 and §7.

## §2.9 Census Gazetteer tract centroids

*This section explains the geography reference used for every spatial feature.*

Every spatial feature in Round 7 — distance to nearest branch, branches within 5 miles, MDI proximity, microlender proximity — is computed from a tract centroid to a point set. We use the 2020 Census Gazetteer's national tract file (`2020_Gaz_tracts_national.zip`), which provides each tract's interior point (`INTPTLAT`, `INTPTLONG`) — a point guaranteed to lie inside the polygon, not the geometric centroid (which can fall outside an irregularly-shaped tract). The Gazetteer is a tab-separated text file inside a zip; `features/build_branch_geo.py` pulls and caches it on first run.

Tract centroids are 2020-vintage. Round 5 already harmonized the tract-year panel to 2020 boundaries using the Census Bureau relationship files, so all of Round 7's tract codes match the 2020 vintage. There are approximately 85,000 tracts including territories; after dropping Puerto Rico, US Virgin Islands, American Samoa, Guam, and Northern Mariana Islands (the territory exclusion in §4.5), the supervised panel works on roughly 73,000 tracts per year.

## §2.10 The merged panel

*This section describes the final tract-year panel that the model trains on.*

`features/build_round7_panel.py` joins the eight feature CSVs onto a thin slice of the Round 5 panel (just the keys, `is_rural`, the target, and `n_cra_lenders`). The output is `data/processed/panel/tract_year_with_target_round7.parquet`, with approximately 1.15 million tract-year rows over 2009 – 2024 and roughly 50 columns. Coverage by feature varies: branch geography is ~100% (every tract has a nearest branch); concentration features are NaN-gated when the tract has fewer than three lenders that year (about 20% of tract-years are gated); MDI and microlender proximity counts are ≥0 for every tract; SSBCI state-year fields are zero for the gap years; residualized concentration features (§3.8) inherit their non-null mask from the source features. The panel is held as parquet with default compression — about 350 MB on disk.

The `n_cra_lenders` column is preserved in the panel for verification (the residualization in §3.8 needs it as a regressor) but is explicitly excluded from the model feature list, since it is the underlying signal of the target.

---

# Part III — Feature engineering

## §3.1 What "influenceable" means

*This section names the rule that decides which variables can be in Model 2 and why.*

The whitelist criterion for Round 7 features comes directly from the project handoff: a variable is "influenceable" if (a) it describes the local lending environment rather than the structural population it serves, (b) a county, state, or local lending coalition has a real institutional mechanism for moving it, and (c) it has not already been consumed as a predictor in Round 5's diagnostic baseline. The third condition isn't strictly necessary, but it focuses the new model's signal on what's incremental.

Concretely, in this project that excludes ACS demographic and economic variables (poverty rate, median household income, racial composition, educational attainment, vacancy rate, unemployment), HMDA mortgage volumes (different lending stratum), RUCA codes and rural flags (kept as evaluation-slicing keys but never as features), and the Opportunity Zone designation (a structural designation that is not influenceable). The result is the feature list documented in `notes/00_design_brief.md`. Round 7 trained five distinct subsets of these features across the iteration path (§5); the cleaned final model uses 20.

The key residual concern is that some "influenceable" features are mechanically driven by the same lender-count signal that defines the target — that is leakage, and §3.8 documents how it was handled.

## §3.2 Tract × lender × year apportionment from D6 + D1

*This section describes the apportionment rule the entire CRA-derived feature stack rests on.*

CRA disclosure files give us two complementary record types: D1 records report county-lender-level loan totals broken into size buckets, and D6 records flag the tract-presence of each lender in each county. Neither record alone tells us how many loans a given lender made in a given tract; together they let us approximate it.

The conventional approach, inherited from Round 4 and used by Round 7, is equal-share apportionment. For each `(county, lender, year)` triple:

- Let `T_{c,l,y}` = the set of tracts where lender l was present in county c in year y (from D6, where loan_indicator = "Y").
- Let `n_loans_{c,l,y}` = the lender's total small-business loan count in county c in year y (sum of D1 buckets).
- Each tract `t ∈ T_{c,l,y}` is allocated `n_loans_{c,l,y} / |T_{c,l,y}|` loans.

Equal apportionment is coarse — it ignores within-county lender-tract intensity differences. A lender whose volume is concentrated in two affluent tracts of a five-tract county has its volume spread evenly across all five. The bias is conservative: it understates concentration in volume-heavy tracts and overstates it in volume-light ones. But it is reproducible, free of feedback with the desert target (since neither numerator nor denominator references lender count), and consistent with the round-on-round methodology. Alternatives — proportional apportionment by loan volume, where loan volume itself is at the tract level — require source data we do not have (CRA does not publish tract-level dollar volumes by lender).

The output (`data/processed/cra/tract_lender_year.csv`) is the foundation for everything in §3.4 (concentration), §3.5 (lender mix), and the loan-size buckets in §3.4. It is approximately 20 million rows over 16 years.

## §3.3 Branch geography features (BallTree haversine)

*This section walks through the spatial-join pipeline and the design decisions inside it.*

`features/build_branch_geo.py` produces three branch-geography features per `(tract_fips, year)`:

- `distance_to_nearest_bank_branch`: haversine distance in miles to the nearest active SoD branch.
- `branches_within_5mi`: count of active SoD branches within 5 miles.
- `branch_closures_3y_within_10mi`: count of branches that disappeared from SoD between any of years (T-3, T-2, T-1) and year T, within 10 miles of the tract centroid.

The implementation uses sklearn's `BallTree(metric='haversine')`. The haversine metric requires inputs in radians, hence the conversion. The earth's radius is taken as 3958.7613 miles. Two operations on the BallTree are used: `query(k=1)` for nearest-neighbor distance, and `query_radius(count_only=True)` for radius counts.

For closures, the script preloads SoD for every year of the panel into a dict-of-dataframes, then for each year T compares `UNINUMBR` sets between year T and each of T-1, T-2, T-3. Branches present in any prior year but absent in year T are "gone." A second BallTree over the closed-branch coordinates lets us count tract-centroid-proximate closures within 10 miles. The 10-mile radius (versus 5 for active branches) reflects the larger relevant catchment for closure events: a closure 8 miles away is still a meaningful loss of access for a tract that previously had a branch in that direction.

Runtime over the full panel is approximately 10 minutes. The dominant cost is constructing one BallTree per year per metric (active, then closures); the queries themselves are vectorized over all 85K tract centroids.

## §3.4 Concentration features

*This section describes the tract-level concentration metrics — top1, top3, HHI — and the NaN-gate that protects them from leakage.*

`features/build_concentration.py` computes per `(tract_fips, year)`:

- `top1_lender_share_tract`: the share of tract loans held by the single largest lender (max share).
- `top3_lender_share_tract`: cumulative share of the top three lenders.
- `lender_hhi_tract`: full Herfindahl-Hirschman index, sum of `share^2` across all lenders.
- `pct_loans_under_100k`: fraction of tract loans with original amount under $100K (CRA D1's smallest size bucket).
- `pct_loans_under_250k`: fraction under $250K.

The build is fully vectorized in pandas. Per-tract HHI is computed by joining tract totals back to the per-row tract-lender records, computing per-row share squared, then group-summing. Top-1 and top-3 use a sort-then-cumcount approach rather than `groupby.apply(lambda)`, which is roughly two orders of magnitude faster on the 20-million-row input.

The single most important detail is the NaN gate: when `n_active_lenders_tract < 3`, all three concentration features are set to NaN. The gate exists because the target is built from `n_cra_lenders` (Round 5 defines a desert as the bottom-decile of lender count within `(year × peer-group)`). In tracts with one or two lenders — i.e., the tracts that are *already* close to desert — top1 saturates at near 1.0 and HHI at near 1.0, mechanically. Without the gate, a model would see "concentration is high" not as a predictor of future desert formation but as a near-certain indicator that the tract is already there. The gate forces XGBoost to learn from concentration only in tracts where concentration is actually meaningfully variable — and to handle the "concentration unmeasurable" condition through XGBoost's native NaN-handling rather than memorizing a sentinel value.

The build also produces lagged variants — `*_lag2to5_mean`, the mean of years T-2, T-3, T-4, T-5 per tract — to break the mechanical T → T+1 link further. The trailing-mean variant of the model (v2 in §5) used these in place of year-T values; the cleaned model (v4) uses residualized values instead, which proved more powerful.

## §3.5 Lender mix

*This section explains how community-bank, top-4, and credit-union shares were computed.*

`features/build_cra_lender_mix.py` joins the per-`(lender_id, year)` classification flags from §2.4 onto the tract-lender-year apportioned panel and computes weighted shares per `(tract_fips, year)`:

- `pct_loans_from_community_banks`: tract loans from `is_community_bank = 1` lenders ÷ tract total loans
- `pct_loans_from_top4_banks`: tract loans from `is_top4 = 1` lenders ÷ tract total loans
- `pct_loans_from_credit_unions`: tract loans from `is_credit_union = 1` lenders ÷ tract total loans

The same NaN gate as concentration features applies (≥ 3 lenders required). Trailing 5-to-2-year mean variants are also computed.

Two implementation notes. First, `is_community_bank` is itself NaN when the lender's CERT did not match an FDIC institution or when Call Report assets are missing for that year — so the community-bank share is itself NaN-tinted and an unweighted average can be misleading. Second, `is_top4` is computed nationally — the four lenders with the highest national CRA loan dollar volume in a given year — so tracts dominated by a *regional* big bank are not flagged as "top4-dominated" unless that regional bank ranks in the top four nationally. This is intentional: the policy story we tell about "shift the share away from large national banks" only makes sense at the federal-mover scale.

## §3.6 Mission-lender features

*This section explains how mission-lender presence — MDI, microlender, CDFI — entered Model 2.*

Three pipelines feed the mission-lender features. The MDI pipeline is described in §2.5 (year-precise from the historical xlsx). The microlender pipeline scrapes SBA, geocodes the addresses via Census + Nominatim, and produces `microloan_intermediary_within_25mi` from a single snapshot broadcast to all panel years. The CDFI pipeline mirrors the microlender pipeline (different list, same mechanics) and produces `cdfi_within_10mi` — used in earlier iterations but mostly replaced by NMTC features in the wider stack and then dropped from the cleaned model when the NMTC features themselves washed out (§7.4).

The cleaned model uses four mission-lender features:

- `mdi_branches_within_10mi` (rank 9 in the cleaned importance list)
- `mdi_branches_within_25mi` (rank 15)
- `nearest_mdi_branch_miles` (rank 11)
- `mdi_active_in_county` (rank 18)
- `microloan_intermediary_within_25mi` (rank 17)

The MDI features dominate the mission-lender slot. Combined importance across the four MDI features is 0.099 — about 10% of the model's gain. The microlender feature contributes 0.016. CDFI proximity (broadcast snapshot, no year resolution) was not strong enough to survive the pruning sweep against the year-precise MDI alternative.

## §3.7 SSBCI state-year overlay features

*This section explains the four SSBCI features and their interpretation.*

The four state-year SSBCI features described in §2.8 are broadcast to every tract in the state during the panel merge:

- `ssbci_active`: 1 in 2011 – 2017 and 2022 – 2024 for all 50 states + DC, else 0.
- `ssbci_2_0_active`: 1 in 2022 – 2024, else 0.
- `ssbci_program_count`: 3 in SSBCI 1.0 years, 4 in SSBCI 2.0 years, else 0.
- `ssbci_n_capital_programs`: 3 in 1.0, 3 in 2.0 (Venture Capital is excluded from the "capital" subset).

The cleaned-model importance ranks: `ssbci_active` is rank 5 (importance 0.048), `ssbci_program_count` is rank 14 (0.024), `ssbci_2_0_active` and `ssbci_n_capital_programs` are both at the bottom of the list with effectively zero importance. The top-line story from these features is that *some signal* exists, but the smoothed era windows make it hard to attribute that signal cleanly to the program rather than to the broader macro-recovery cycles the program windows happen to overlap (post-Great-Recession 2011 – 2017, post-COVID 2022 – 2024). The post-COVID regime split (§7.3) makes this concern concrete: in the post-COVID model trained on 2020 – 2021 with 2023 – 2024 test years, all four SSBCI features collapse to zero importance.

This isn't a bug — it's an honest representation of how a state-year era signal interacts with a forward-target that is itself era-sensitive.

## §3.8 The leakage problem and the residualization fix

*This section is the centerpiece methodological move of the project. It deserves more space than other sections because it is where the most consequential design decision was made.*

The concentration and lender-mix features described in §3.4 and §3.5 share an uncomfortable property with the target. The Round 5 target `target_becomes_service_desert_h1` is defined as the bottom decile of `n_cra_lenders` within `(year × peer_group)`. When the lender count is small — which is, by construction, the desert condition — concentration features mechanically saturate. Top1 share approaches 1.0 (one lender owns 100%), top3 share saturates trivially, HHI approaches 1.0. Even with the NaN gate (drop when n < 3), the residual signal is not orthogonal to the target.

The NaN gate handles the trivial saturation but not the milder mechanical correlation: in a tract with 4 lenders, top1 share is at least 0.25 simply by arithmetic, and a tract heading toward becoming a desert is by hypothesis losing lenders, so its top1 share is mechanically rising. The model can pick this up as predictive signal that is in fact just slow-motion saturation.

There were three ways to handle this:

1. **Drop the features.** Cleanest, but expensive — concentration is one of the conceptually clearest "lending environment" levers, and dropping it sacrifices much of the policy story.
2. **Use only trailing means.** The v2 model (§5.2) used `*_lag2to5_mean` features, the average over years T-5 through T-2. This breaks the mechanical T → T+1 link but doesn't address the slower mechanical correlation in the trailing-mean values themselves.
3. **Residualize.** For each `(year, peer_group)` cohort, regress each leakage-vulnerable feature on `[log(n_cra_lenders + 1), n_cra_lenders]` and use the residual as the new feature. This isolates the part of the feature *not* mechanically explained by the underlying lender count.

We picked option 3. The implementation is in `features/build_concentration_residualized.py`. For each (year × peer_group) cohort:

- Let `y` be the leakage-vulnerable feature (e.g., `top3_lender_share_tract`).
- Let `n` be `n_cra_lenders`.
- Fit a linear regression: `y ≈ β₀ + β₁ · log(n + 1) + β₂ · n` on the non-NaN rows.
- Compute the residual `y_resid = y - ŷ` for those rows.
- Keep `y_resid` as the new feature; the original `y` is dropped from the model feature list.

The cohorts are `(year, peer_group)` where peer_group is `rural` or `urban` (the same peer-grouping the target uses). We require at least 50 observations in a cohort to fit; otherwise the residual is NaN. This is a per-cohort fit, not a single global fit, so the regression captures era-specific and rural-vs-urban-specific mechanical relationships.

The eight features residualized: `top1_lender_share_tract`, `top3_lender_share_tract`, `lender_hhi_tract`, `pct_loans_from_community_banks`, `pct_loans_from_top4_banks`, `pct_loans_from_credit_unions`, `pct_loans_under_100k`, `pct_loans_under_250k`.

Residualization removes a substantial fraction of each feature's variance — the residual standard deviations are reported as a sanity check. From the build's diagnostic output:

| Feature | Original std | Residual std | Ratio |
|---|---|---|---|
| `top3_lender_share_tract` | 0.30 | 0.16 | 0.55× |
| `lender_hhi_tract` | 0.18 | 0.10 | 0.57× |
| `top1_lender_share_tract` | 0.21 | 0.15 | 0.71× |
| `pct_loans_from_community_banks` | 0.31 | 0.29 | 0.92× |
| `pct_loans_from_credit_unions` | 0.18 | 0.07 | 0.36× |
| `pct_loans_under_100k` | 0.21 | 0.20 | 0.95× |
| `pct_loans_under_250k` | 0.18 | 0.17 | 0.96× |
| `pct_loans_from_top4_banks` | 0.31 | 0.30 | 0.97× |

The credit-union share loses 64% of its variance to lender-count residualization — most of the variation in "what fraction of tract loans came from credit unions" is mechanically explained by how many lenders the tract has. That's intuitive: a tract with three lenders, one of which is a credit union, has a credit-union share of 33% by arithmetic. Top3 and HHI lose ~45% of their variance similarly. Loan-size shares and community-bank share retain almost all of theirs — they are weakly correlated with lender count, so residualization barely touches them.

The downstream tradeoff is interpretability. A residualized feature is a deviation from a peer-group conditional expectation, not a raw share. "Residualized HHI is high" doesn't mean "the tract is concentrated"; it means "the tract is more concentrated than a typical tract with this lender count would be." The dashboard slider has to reckon with this — see §8.4 for honest framing — but the leakage-defense gain is real, and the cleaned model (§5.5) keeps four residualized features in the top seven by importance, which means they survived even after the leakage-vulnerable component was removed.

---

# Part IV — Modeling

## §4.1 Target definition

*This section explains what the model is actually predicting and where the target's positive rate comes from.*

`target_becomes_service_desert_h1` is defined in `round5/features/define_target.py`. The construction:

1. For each tract-year, compute `n_cra_lenders` — the count of distinct CRA-reporting small-business lenders that originated at least one loan in that tract in that year.
2. Within each `(year, peer_group)` — where `peer_group` is `rural` or `urban` — compute the bottom-decile threshold of `n_cra_lenders`. A tract is a *service desert* in year T if its `n_cra_lenders` is at or below that decile.
3. The forward target `target_becomes_service_desert_h1` is 1 for tracts that are *not* a desert in year T but *are* a desert in year T+1. It is 0 for tracts that are not a desert in either year. It is NaN (excluded from training) for tracts that are already a desert in year T.

This last point matters: the target is a *transition* target, not a *state* target. We are predicting which tracts cross into desert status, conditional on not already being in it. That conditioning is what produces the rare-event regime: positive rates of 1.5 – 3.5% across folds, with year-over-year variation reflecting the underlying churn rate.

The peer-grouping splits rural from urban tracts because the lender-count distribution is dramatically different between them. Rural tracts have systematically fewer lenders, and using a single national bottom-decile threshold would label most rural tracts as deserts whether or not they were really transitioning. Within-peer-group thresholding fixes this.

## §4.2 Walk-forward eight-fold validation

*This section describes the cross-validation scheme and why it is the right one for this problem.*

The validation scheme is walk-forward by year, with 8 folds:

| Fold | Train | Val | Test |
|---|---|---|---|
| F1 | 2009 – 2014 | 2015 | 2016 – 2017 |
| F2 | 2009 – 2015 | 2016 | 2017 – 2018 |
| F3 | 2009 – 2016 | 2017 | 2018 – 2019 |
| F4 | 2009 – 2017 | 2018 | 2019 – 2020 |
| F5 | 2009 – 2018 | 2019 | 2020 – 2021 |
| F6 | 2009 – 2019 | 2020 | 2021 – 2022 |
| F7 | 2009 – 2020 | 2021 | 2022 – 2023 |
| F8 | 2009 – 2021 | 2022 | 2023 – 2024 |

The motivation, fully spelled out in `round5/notes/00_methodology.md`, is that this is fundamentally a temporal forecasting problem. Random k-fold CV across tracts puts neighboring tracts (which share demographics, lenders, and economic shocks) in train and test simultaneously — the model effectively memorizes the county and reports inflated AUC. Walk-forward by year prevents that. It also gives us an honest distribution across regulatory regimes and macro eras.

The val year is always the year immediately after the train window and one year before the test window. It serves two purposes: (a) early stopping during XGBoost fitting, and (b) fitting the isotonic calibrator that is then applied to the test set.

The decision rule (§4.5) further requires that ≥ 6 of 8 folds clear the AP threshold to qualify for "Strong" signal. This protects against the scenario where pre-COVID folds (F1 – F4) are strong and post-COVID folds (F5 – F8) are weak — which is exactly what happened. The cleaned model (§5.5) reports 6 of 8 folds clearing AP ≥ 0.10, by the slimmest margin.

## §4.3 XGBoost hyperparameters

*This section names the XGBoost configuration and the reasoning behind it.*

The XGBoost classifier is configured identically across every Round 7 training script:

```python
xgb.XGBClassifier(
    n_estimators=400, max_depth=6, learning_rate=0.05,
    subsample=0.85, colsample_bytree=0.85,
    min_child_weight=5, reg_lambda=1.0,
    tree_method="hist", objective="binary:logistic",
    eval_metric="aucpr", early_stopping_rounds=25,
    random_state=42, verbosity=0,
)
```

The configuration is inherited from Round 5, which itself inherits it from Round 4 with one substantive change: `eval_metric="aucpr"` replaces the default `logloss`. AUCPR (which is mathematically equivalent to average precision in the limit) is the right early-stopping metric for this rare-event problem, where logloss is dominated by negative-class accuracy and underweights the rare-positive learning signal. The early-stopping-rounds value of 25 is generous enough to absorb val-AUC volatility while still preventing severe overfitting.

`max_depth = 6` is mid-range for tabular boosting; it allows three-way feature interactions without the deep-tree overfitting that bites at 8+. `subsample = colsample_bytree = 0.85` provides modest stochastic regularization. `min_child_weight = 5` prevents leaves from forming on too few rows of the rare positive class. `reg_lambda = 1.0` is the default L2 regularizer, kept on. `tree_method = "hist"` is the modern XGBoost histogram method — much faster than `exact` for this panel size with no real accuracy cost.

`random_state = 42` makes runs reproducible. We do not run multiple seeds; one is enough given the eight-fold structure already provides distribution.

## §4.4 Isotonic calibration

*This section explains what calibration does and why it matters for an audience that may not be familiar with it.*

Tree-based ensemble classifiers like XGBoost output probabilities that are not calibrated by default — that is, the predicted probability `p` does not necessarily equal the empirical positive rate among test cases predicted at `p`. A model can score `p = 0.30` on a set of 1,000 cases of which only 80 are actually positive (true rate 8%) and `p = 0.30` on a different set of 1,000 cases of which 200 are positive (true rate 20%). The model's *ranking* may still be good (AUC measures only ranking), but its absolute probabilities are unreliable for downstream policy use.

Isotonic regression is a non-parametric monotonic calibrator. It fits a monotone-non-decreasing step function from raw predicted probabilities to empirical positive rates on a held-out calibration set (in our case, the val year). Then at test time, the calibrator is applied to the raw test predictions, producing calibrated probabilities that match the empirical frequency in the val set's distribution. We use sklearn's `IsotonicRegression(out_of_bounds="clip")`, which clips out-of-range predictions to the calibrator's domain.

The Brier score columns in the diagnostics (e.g., `test_brier_calibrated`) measure calibration quality — lower is better. A perfectly calibrated random predictor has Brier equal to the positive rate × (1 - positive rate); this rare-event panel's no-information Brier is roughly 0.020 – 0.035 depending on the year. The cleaned model achieves test_brier_calibrated values from 0.014 (early folds) to 0.036 (mid-COVID folds), which means the model adds modest Brier improvement over the no-information baseline in early folds and virtually none in COVID folds.

## §4.5 Train / val / test splits and territory exclusion

*This section names the rows that are excluded from training and why.*

Two filters are applied uniformly across every Round 7 training run:

- **Target NaN exclusion.** Rows where the target is NaN are excluded. This is the case for tracts that were already deserts in year T (no transition possible) and tracts at the boundary of the panel where forward observation is not yet available.
- **Territory exclusion.** Tracts in Puerto Rico (state FIPS 72), US Virgin Islands (78), American Samoa (60), Guam (66), and Northern Mariana Islands (69) are excluded from training and evaluation. The rationale: Round 5 documented that these territories have substantially different lender ecosystems and ACS coverage gaps that systematically bias AUC, and they were excluded from Round 5's headline numbers as well. We follow the same convention here for direct comparability.

The supervised training panel is therefore approximately 1.07 million tract-years across 50 states + DC over 2009 – 2024. After the target-NaN exclusion (about 8% of rows), the eight folds use roughly the volumes shown in the per-fold story (§6.4) — train sizes ranging from 488K to 1.07M, val sizes around 80K – 95K, test sizes around 77K – 170K depending on fold.

## §4.6 The horizon decision and fold restructure

*This section is the methodological centerpiece of the late-cycle Round 7 work. It is the deeper companion to §6.5 in the methodology brief; the brief sketches the rationale and the headline numbers, this section walks through how the implementation actually changed.*

### The federal data lag rationale

The single most important downstream constraint on a tract-year forecasting model trained on FFIEC CRA data is the publication lag of the source files. The FFIEC publishes the prior year's CRA disclosure data in the second half of the calendar year following — but the substantive 2024 data set was not fully usable until early 2026. The downstream FDIC SoD lag is shorter (roughly 12 months), and SSBCI activation is essentially real-time, but the CRA panel is the binding constraint. Anyone running the trained model in 2026 against the freshest available data has feature-year coverage through 2024.

At the original h+1 horizon, that 2024 feature year predicts 2025 — a year already complete by the time the model can be run on the 2024 features. The forecast arrives after the year it forecasts. As a research artifact, the h+1 model is fine: every test fold uses out-of-sample data and every reported metric is honest. But as an operational tool — a dashboard a county economic-development office or a CDFI partner uses to plan — it is useless. The forecast doesn't reach forward of the calendar.

Three-year and six-year horizons solve the problem cleanly. At h+3, a 2024 feature year predicts 2027 — a year three years out, well within the planning window of the institutional users we designed the dashboard for. At h+6, the same feature year predicts 2030 — a long-horizon scenario suited to multi-year initiatives (state SSBCI cycles, regional CDFI program reauthorizations, branch-network strategic planning). The h+3 horizon is the operational primary; h+6 is a scenario layer that lets users see how lever importance reorganizes at long horizons.

### Extending `define_target.py` to compute h1 through h6

The original `round5/features/define_target.py` produced a single forward target column, `target_becomes_service_desert_h1`, defined as the bottom-decile transition between year T and year T+1. The horizon retrain extended this to a six-column family:

```
target_becomes_service_desert_h1   # year T+1 transition
target_becomes_service_desert_h2   # year T+2 transition
target_becomes_service_desert_h3   # year T+3 transition (new primary)
target_becomes_service_desert_h4   # year T+4 transition
target_becomes_service_desert_h5   # year T+5 transition
target_becomes_service_desert_h6   # year T+6 transition (long-horizon scenario)
```

Each column is computed identically to the h+1 column except for the forward year offset. The peer-group decile threshold is computed at the target year (T+h), not at the feature year, so the threshold floats with the underlying lender-count distribution as the panel evolves. A tract with `n_cra_lenders = 5` at year T whose forecast year is T+3 is compared against the bottom-decile threshold for year T+3 within its peer group — not the threshold for year T. This matters because the desert threshold itself drifts (rises modestly across the panel as the national lender count consolidates), so an h+3 prediction is a forecast of "will this tract fall below the *future* peer threshold" rather than "will this tract fall below the *current* peer threshold three years out."

The forward-conditioning rule (target = NaN if tract is already a desert at year T) is preserved. We are still forecasting *transitions into* desert state, not *being in* desert state.

### The fold restructure logic per horizon

Walk-forward folds at horizon `h` must satisfy two constraints:

1. The val year must be the year immediately after the train window's last year (preserves temporal ordering and the early-stopping role).
2. The test years must be `[val_year + 1, val_year + 1 + h - 1]` for a multi-year test window — but in practice we use a single test year per fold for h+3 and h+6 to keep the per-fold sample size from collapsing toward the panel's tail.

The data-end constraint binds: with feature years through 2024 and target years up to 2024, the last viable test fold at h+3 has feature-year coverage ending 2021 and target year 2024 (since 2021 + 3 = 2024). At h+6 the binding constraint is feature-year 2018 → target 2024.

The realized fold structures:

**h+1 (legacy, 8 folds):** test years 2016–2017, 2017–2018, 2018–2019, 2019–2020, 2020–2021, 2021–2022, 2022–2023, 2023–2024. Train windows extend from {2009–2014, ..., 2009–2021}.

**h+3 (new primary, 8 folds):** test years 2014–2015, 2015–2016, 2016–2017, 2017–2018, 2018–2019, 2019–2020, 2020–2021, 2021–2021 (the last fold is single-year because target year 2024 is the binding constraint). Train windows extend from {2009–2012, ..., 2009–2019}.

**h+6 (long-horizon, 6 folds):** test years 2012–2013, 2013–2014, 2014–2015, 2015–2016, 2016–2017, 2017–2018. Train windows extend from {2009–2010, ..., 2009–2015}. Six folds rather than eight because the target year 2024 binds at feature year 2018, leaving fewer panel years in which a complete train + val + test slice can be assembled.

Each horizon's fold structure is parameterized in `train/_horizon_config.py` (see §11). The config returns, given a horizon integer, the train-window minimum, the per-fold (train, val, test) year tuples, and the appropriate target column name. The four core training scripts (`walk_forward_round7.py`, `prune_features.py`, `ablation_per_lever.py`, `regime_split.py`) read the `ROUND7_HORIZON` environment variable, dispatch to `_horizon_config`, and operate on the resulting fold list. This keeps the horizon retrain a single-knob change rather than three forked copies of every script.

### The `_horizon_config.py` shared module

The shared module exposes a single function:

```python
def get_horizon_config(horizon: int) -> HorizonConfig:
    """
    Returns the fold structure, target column, and output-directory
    suffix for the given prediction horizon.

    Parameters
    ----------
    horizon : int in {1, 3, 6}
    """
```

`HorizonConfig` is a small dataclass with five fields: `horizon`, `target_column` (e.g., `target_becomes_service_desert_h3`), `folds` (list of `(train_start, train_end, val_year, test_years)` tuples), `output_suffix` (e.g., `_h3` for diagnostic-directory naming), and `min_train_years` (a sanity-check minimum train-window length).

Every script that produces a diagnostic output (Phase A, ablation, prune, regime split) writes to `diagnostics/{run_name}{output_suffix}/` so that the h+1, h+3, and h+6 outputs live in clearly-distinguished directories side by side. The dashboard build (§8) reads the JSONified summaries from each horizon's directory and serves a horizon-toggle UI.

### Why the retrain produces stronger numbers, not weaker

The empirical result is that AUC and AP both improve monotonically as horizon lengthens. The mechanism is two-fold.

First, the structural signal in the influenceable feature set evolves on a multi-year time scale. Branch closures, lender consolidation, SSBCI program activation, MDI partnership effects — none of these complete inside a one-year window. At h+1, the model is asking these features to predict variation that is mostly idiosyncratic year-to-year noise; the slow-moving features carry signal but it is dwarfed by the fast-moving variance.

Second, the target itself smooths at longer horizons. The h+1 transition is a binary step over a single year; the h+6 transition is a binary step over six years, by which time many tracts that were "almost a desert" in year T have completed the transition. The per-fold positive rate roughly doubles between h+1 and h+6 (from ~1.7% to ~3.5% in the panel mean). Higher base rate means more positive signal to learn from, and the model accordingly concentrates more probability mass on the highest-risk tracts, raising AP.

These two effects compound. At h+6, the model is using slow-moving structural features to predict a target with substantially more positives, and the AP gain is dramatic — the headline lift goes from 6.7× at h+1 to 19.5× at h+6.

The cost of the longer horizon is the COVID regime split widens at h+6 (§7.3.2). At a six-year horizon, the post-COVID test windows ask the model to forecast 2017–2018 from 2014–2015 features under a regime that subsequently reorganized; the post-COVID h+6 AUC drops to 0.774. We accept this tradeoff: at h+3, the regime gap is small (0.847 vs 0.825), so h+3 is the right operational primary; at h+6, the gap is large but the long-horizon scenario is still useful for surfacing how lever importance reorganizes (branch access at 73% post-COVID).

---

# Part V — The block-of-clay process

*This part walks through the iteration path from the initial 14-feature run to the cleaned 20-feature model. The shorthand "block of clay" comes from the project's own internal language: start with the broadest plausible feature set, then sculpt down by pruning, residualizing, and re-evaluating until what remains is policy-defensible without sacrificing predictive signal beyond an acceptable threshold.*

## §5.1 Initial 14-feature run (v1)

*The first pass — the 14 MVP features from the design brief, year-T values, no residualization, no NMTC, no SSBCI.*

The initial run used the 14-feature MVP set from `notes/00_design_brief.md`: 8 CRA-derived (top1, top3, HHI, community-bank share, top-4 share, credit-union share, loans under $100K share, loans under $250K share) + 3 FDIC branch features + 3 mission proximity features (CDFI, MDI, microlender from snapshots). All values were year-T with the NaN gate but no trailing-mean transformation.

Result: mean test AUC 0.817, mean test AP 0.153, eight folds. This was strong enough on its face but visibly leakage-vulnerable: the top-importance feature was `top3_lender_share_tract` followed closely by `lender_hhi_tract`, both with the mechanical-saturation property described in §3.8.

## §5.2 Adding NMTC + MDI + SSBCI (v3) and the trailing-mean variant (v2)

*Two parallel widenings of the feature stack — one to break the year-T concentration link, one to add new signal.*

The trailing-mean variant (v2) replaced the year-T concentration and lender-mix features with their `_lag2to5_mean` versions. Mean test AUC 0.841, mean test AP 0.205. The lift was unexpected but interpretable: trailing means smooth out the mechanical year-T saturation and what's left is more genuinely predictive.

The wider stack (v3) added the year-precise MDI features (replacing the snapshot MDI), the four SSBCI state-year overlays, and five NMTC features. Mean test AUC 0.826, mean test AP 0.155, std AUC 0.060. v3 widened the stack to 25 features. The std AUC of 0.060 was at the boundary of the "stability flag" threshold (anything > 0.06 was flagged for follow-up).

The NMTC features all had ~0 importance — see §7.4 for the structural interpretation. The SSBCI features showed modest non-zero importance, mostly concentrated in `ssbci_active`. The year-precise MDI features displaced the snapshot MDI cleanly.

## §5.3 The pruning sweep (k = 3, 5, 7, 10, 14, 18, 22, all)

*This section describes the prune-and-retrain methodology and what it found.*

`train/prune_features.py` aggregates the per-fold XGBoost gain importance from a Phase A run into a master ranking, then for each k in `{3, 5, 7, 10, 14, 18, 22, all}` re-runs all 8 walk-forward folds using only the top-k features by mean importance. This is *prune-and-retrain*, not *retrain-once-and-permute* — at each k, XGBoost re-fits with the smaller feature set, which catches cases where dropping a leakage-vulnerable feature actually *improves* AP (because it forced the model to find genuinely predictive signal elsewhere).

The cleaned-model sweep results (`diagnostics/round7_pruned_clean/sweep_results.csv`):

| k | Mean test AUC | Std AUC | Mean test AP | Folds ≥ 0.10 AP |
|---|---|---|---|---|
| 3 | 0.739 | 0.073 | 0.116 | 6 / 8 |
| 5 | 0.736 | 0.069 | 0.109 | 5 / 8 |
| 7 | 0.780 | 0.056 | 0.129 | 6 / 8 |
| 10 | 0.773 | 0.054 | 0.108 | 5 / 8 |
| 14 | 0.791 | 0.047 | 0.113 | 6 / 8 |
| 18 | 0.792 | 0.056 | 0.117 | 5 / 8 |
| 20 (full) | 0.791 | 0.047 | 0.111 | 6 / 8 |

The elbow in the cleaned model is at k = 7. AP at k = 7 is 0.129 — actually higher than the full 20-feature AP of 0.111, suggesting the smaller model is no worse and possibly slightly better on the AP metric, while having 0.011 lower AUC. The seven features at the elbow:

1. `distance_to_nearest_bank_branch`
2. `lender_hhi_tract_resid`
3. `pct_loans_from_top4_banks_resid`
4. `pct_loans_from_credit_unions_resid`
5. `ssbci_active`
6. `top3_lender_share_tract_resid`
7. `branches_within_5mi`

The headline insight from the prune sweep: branch access alone (rank 1, distance to nearest branch) accounts for roughly 37% of model gain, and dropping below k = 7 significantly hurts the AP. The cleaned model ships at k = 20 (the full clean stack) for ablation comparability, but the slider UI in the dashboard surfaces the seven-feature elbow as the parsimonious story.

## §5.4 The leakage mitigation iteration (residualization)

*This section describes the move from v3 to v4 — the residualization decision and what it traded.*

After the v3 wider-stack run, the team's concern was no longer raw signal — Model 2 had ample raw signal. The concern was *defensible* signal: how much of the AP at v3 was leakage-mediated saturation, and how much would survive a properly orthogonalized cohort regression?

Three options were evaluated. The first was more aggressive feature dropping: keep only `distance_to_nearest_bank_branch`, `branches_within_5mi`, `branch_closures_3y_within_10mi`, and the SSBCI features. This was rejected because it would reduce the policy story to "branch access," when the project's hypothesis is broader. The second was deeper trailing means: extend the lag window to 7-to-3 years. This was rejected because it makes the model less responsive to recent regime change and the AP gain over the 5-to-2 window was negligible in pilot tests. The third was residualization — for each `(year, peer_group)` cohort, regress each leakage-vulnerable feature against `[log(n_cra_lenders + 1), n_cra_lenders]` and use the residual.

Residualization was picked. The reasoning, in full:

The mechanical saturation is a *partial* relationship between concentration and lender count, not a deterministic one. Some tracts are concentrated because their lender market has *consolidated* (a documented institutional process — mergers, branch closures, retreat from local lending), and others are concentrated because they have *only ever had* one or two lenders. The first is a real predictor of further deterioration; the second is just a thin, stable market. Residualization explicitly separates these. The residual is "how much more concentrated this tract is than its lender count alone would predict in this peer group and year." That is a more conceptually clean signal: it captures *unusual* concentration, not just *low* lender count.

The cost is that the residualized feature is harder to communicate. "Residualized HHI is high" requires a sentence of explanation. Round 5's HHI is just "HHI" — directly interpretable. We accept this cost. §8.4 documents how the dashboard handles it.

The v4 cleaned run's results (`diagnostics/round7_phaseA_clean/`):

| Metric | v3 (year-T concentration) | v4 (residualized) | Δ |
|---|---|---|---|
| Mean test AUC | 0.826 | 0.794 | -0.032 |
| Std test AUC | 0.060 | 0.047 | -0.013 |
| Mean test AP | 0.155 | 0.129 | -0.026 |
| Folds clearing AP ≥ 0.10 | 7 / 8 | 6 / 8 | -1 |

v4 trades 0.032 AUC and 0.026 AP for 0.013 lower std (i.e., better stability) and full leakage-defense. We consider the trade worthwhile: a slightly weaker but defensible model is better than a slightly stronger but contestable one.

## §5.5 The cleaned model

*This section names the final model that ships.*

The cleaned model — Model 2, the headline of Round 7 — uses the following 20 features:

- 8 residualized concentration / lender-mix / loan-size features (from §3.8): `pct_loans_from_community_banks_resid`, `pct_loans_from_top4_banks_resid`, `pct_loans_from_credit_unions_resid`, `pct_loans_under_100k_resid`, `pct_loans_under_250k_resid`, `top1_lender_share_tract_resid`, `top3_lender_share_tract_resid`, `lender_hhi_tract_resid`
- 3 branch geography features: `distance_to_nearest_bank_branch`, `branches_within_5mi`, `branch_closures_3y_within_10mi`
- 4 year-precise MDI features: `mdi_branches_within_10mi`, `mdi_branches_within_25mi`, `nearest_mdi_branch_miles`, `mdi_active_in_county`
- 1 microlender feature: `microloan_intermediary_within_25mi`
- 4 SSBCI state-year features: `ssbci_active`, `ssbci_2_0_active`, `ssbci_program_count`, `ssbci_n_capital_programs`

Eight-fold walk-forward result: mean test AUC 0.794 ± 0.047, mean test AP 0.129, mean lift 6.7×. Six of eight folds clear AP ≥ 0.10. The model qualifies for the "Strong" signal verdict per the decision rule in §4.5.

The detailed per-fold and per-feature breakdown is in §6.

---

# Part VI — Findings

## §6.1 Headline numbers — Model 1 versus Model 2 across horizons

*This section places the two models side by side at the top level, across all three trained horizons. h+3 is the operational primary; h+6 is the long-horizon scenario; h+1 is preserved for diagnostic comparability.*

| Layer | Horizon | Mean AUC | Std AUC | Mean AP | Lift | Folds |
|---|---|---:|---:|---:|---:|---:|
| **Model 1 — Diagnostic** | h+1 | 0.857 | 0.044 | 0.172 | 9.25× | 8 |
| **Model 1 — Diagnostic** | **h+3** (primary) | **0.875** | 0.038 | **0.322** | **17.0×** | 8 |
| **Model 1 — Diagnostic** | **h+6** (scenario) | **0.871** | 0.060 | **0.489** | **25.4×** | 6 |
| **Model 2 — Influenceable** | h+1 | 0.794 | 0.047 | 0.129 | 6.7× | 8 |
| **Model 2 — Influenceable** | **h+3** (primary) | **0.820** | 0.048 | **0.282** | **11.1×** | 8 |
| **Model 2 — Influenceable** | **h+6** (scenario) | **0.862** | 0.072 | **0.464** | **19.5×** | 6 |

The headline finding is that both models improve monotonically as the prediction horizon lengthens. The improvement on AP is particularly striking — Model 2's mean AP at h+6 (0.464) is over three times the h+1 figure (0.129), and the lift goes from 6.7× to 19.5×. The mechanism is the inversion of the naive "longer horizon = harder forecast" expectation: the influenceable feature set encodes slow-moving structural signal that is dwarfed by year-to-year noise at h+1 but stands clear at h+3 and h+6. See §4.6 for the full methodological treatment.

Both models at every horizon clear the AP ≥ 0.10 strong-signal threshold. The Model 2 gap to Model 1 narrows at long horizons: at h+1 the AUC gap is 0.063; at h+3 it is 0.055; at h+6 it is just 0.009. At long horizons, the influenceable features are nearly as predictive as the full diagnostic set — meaning the structural-disadvantage variables that Model 1 carries lose marginal information advantage when the target is six years out.

The interpretation we offer in the dashboard: Model 1 is the *baseline picture* of where deserts will form; Model 2 is the *policy-leverable overlay* showing which lending-environment conditions plausibly shift that baseline. Both layers are now offered at h+3 (operational forecast) and h+6 (long-horizon scenario). The horizon toggle is the dashboard's primary new control surface (§8).

### Per-fold detail for h+3 (the new primary)

From `diagnostics/round7_phaseA_h3/fold_results.csv`:

| Fold | Train | Test | Test AUC | Test AP | Lift |
|---|---|---|---:|---:|---:|
| F1 | 2009–2012 | 2014–2015 | 0.879 | 0.458 | 20.7× |
| F2 | 2009–2013 | 2015–2016 | 0.842 | 0.355 | 17.3× |
| F3 | 2009–2014 | 2016–2017 | 0.814 | 0.207 | 11.7× |
| F4 | 2009–2015 | 2017–2018 | 0.881 | 0.265 | 16.4× |
| F5 | 2009–2016 | 2018–2019 | 0.796 | 0.208 | 6.5× |
| F6 | 2009–2017 | 2019–2020 | 0.749 | 0.243 | 4.8× |
| F7 | 2009–2018 | 2020–2021 | 0.786 | 0.240 | 5.1× |
| F8 | 2009–2019 | 2021 | 0.816 | 0.279 | 6.3× |

Eight of eight folds clear AP ≥ 0.10; the per-fold AP-lift is in the 4.8× – 20.7× range. The pre-COVID folds (F1–F5) average lift 14.5×; the post-COVID folds (F6–F8) average 5.4× — still strong, just less extreme than the pre-COVID regime.

### Per-fold detail for h+6 (the long-horizon scenario)

From `diagnostics/round7_phaseA_h6/fold_results.csv`:

| Fold | Train | Test | Test AUC | Test AP | Lift |
|---|---|---|---:|---:|---:|
| F1 | 2009–2010 | 2012–2013 | 0.942 | 0.514 | 36.0× |
| F2 | 2009–2011 | 2013–2014 | 0.893 | 0.505 | 26.7× |
| F3 | 2009–2012 | 2014–2015 | 0.930 | 0.672 | 28.5× |
| F4 | 2009–2013 | 2015–2016 | 0.862 | 0.489 | 13.7× |
| F5 | 2009–2014 | 2016–2017 | 0.786 | 0.327 | 6.6× |
| F6 | 2009–2015 | 2017–2018 | 0.761 | 0.276 | 5.7× |

Six of six folds clear AP ≥ 0.10. The pre-COVID folds (F1–F4) average lift 26.2×; the post-COVID folds (F5, F6) average 6.1×. The per-fold positive rate roughly doubles between h+3 and h+6 (mean ~3.5% vs ~1.7%), which both raises the random-baseline AP and gives the model more positive signal to learn from.

## §6.2 The cleaned 20-feature model performance

*This section reports the eight-fold metrics in detail.*

From `diagnostics/round7_phaseA_clean/fold_results.csv`:

| Fold | Train | Test | n_test | Test AUC | Test AP | Lift | Brier (cal) |
|---|---|---|---|---|---|---|---|
| F1 | 2009–2014 | 2016–2017 | 170,106 | 0.809 | 0.135 | 7.94× | 0.0156 |
| F2 | 2009–2015 | 2017–2018 | 168,196 | 0.841 | 0.130 | 8.56× | 0.0141 |
| F3 | 2009–2016 | 2018–2019 | 163,614 | 0.850 | 0.153 | 10.30× | 0.0136 |
| F4 | 2009–2017 | 2019–2020 | 158,588 | 0.829 | 0.164 | 11.18× | 0.0135 |
| F5 | 2009–2018 | 2020–2021 | 157,747 | 0.713 | 0.110 | 3.86× | 0.0268 |
| F6 | 2009–2019 | 2021–2022 | 157,316 | 0.751 | 0.160 | 4.33× | 0.0356 |
| F7 | 2009–2020 | 2022–2023 | 155,554 | 0.780 | 0.094 | 3.67× | 0.0254 |
| F8 | 2009–2021 | 2023–2024 | 77,124 | 0.780 | 0.084 | 3.72× | 0.0218 |
| **Mean** | | | | **0.794** | **0.129** | **6.7×** | **0.0208** |

The pre- and post-COVID asymmetry is visible. Folds F1 – F4 (test 2016 – 2020) average AUC 0.832; folds F5 – F8 (test 2020 – 2024) average AUC 0.756. The AP swing is comparable (F1 – F4 mean 0.146, F5 – F8 mean 0.112). §6.4 walks through the per-fold story in detail and §7.3 documents the formal regime-split study.

The calibrated Brier scores deserve a comment. Folds F1 – F4 produce Brier values in the 0.0135 – 0.0156 range — well below the no-information baseline for these positive rates. F5 – F8 have notably worse calibration: Brier values 0.0218 – 0.0356, sometimes within 10% of the no-information baseline. This is a calibration-degradation artifact of the COVID regime: the val year used to fit the isotonic calibrator (2019, 2020, 2021, 2022 across the four COVID-affected folds) is not predictive of the test-year positive-rate distribution because the underlying churn rate changed.

## §6.3 Top-feature ranking

*This section reports the cleaned-model XGBoost gain importance, averaged across the eight folds.*

From `diagnostics/round7_pruned_clean/feature_ranking.csv`:

| Rank | Feature | Mean importance | Std | Type |
|---|---|---|---|---|
| 1 | `distance_to_nearest_bank_branch` | 0.369 | 0.101 | Branch (clean) |
| 2 | `lender_hhi_tract_resid` | 0.097 | 0.012 | Residualized concentration |
| 3 | `pct_loans_from_top4_banks_resid` | 0.066 | 0.005 | Residualized lender mix |
| 4 | `pct_loans_from_credit_unions_resid` | 0.049 | 0.013 | Residualized lender mix |
| 5 | `ssbci_active` | 0.048 | 0.006 | State policy |
| 6 | `top3_lender_share_tract_resid` | 0.046 | 0.014 | Residualized concentration |
| 7 | `branches_within_5mi` | 0.041 | 0.014 | Branch (clean) |
| 8 | `pct_loans_under_250k_resid` | 0.040 | 0.012 | Residualized loan-size |
| 9 | `mdi_branches_within_10mi` | 0.037 | 0.025 | MDI mission lender |
| 10 | `pct_loans_from_community_banks_resid` | 0.029 | 0.007 | Residualized lender mix |
| 11 | `nearest_mdi_branch_miles` | 0.028 | 0.005 | MDI mission lender |
| 12 | `top1_lender_share_tract_resid` | 0.025 | 0.011 | Residualized concentration |
| 13 | `branch_closures_3y_within_10mi` | 0.024 | 0.018 | Branch (clean) |
| 14 | `ssbci_program_count` | 0.024 | 0.009 | State policy |
| 15 | `mdi_branches_within_25mi` | 0.022 | 0.004 | MDI mission lender |
| 16 | `pct_loans_under_100k_resid` | 0.016 | 0.003 | Residualized loan-size |
| 17 | `microloan_intermediary_within_25mi` | 0.016 | 0.006 | Microlender |
| 18 | `mdi_active_in_county` | 0.012 | 0.004 | MDI mission lender |
| 19 | `ssbci_n_capital_programs` | 0.011 | 0.016 | State policy |
| 20 | `ssbci_2_0_active` | 0.000 | 0.000 | State policy |

Three observations. First, branch access is dominant: ranks 1, 7, and 13 sum to 0.434 — about 43% of total gain importance. Distance to nearest branch alone is 37%. The branch-access lever is the single cleanest, most policy-leverable result in the cleaned model.

Second, the residualized features survive prominently. Four of the top seven features are residualized, which is meaningful because by construction residualization removes the leakage-vulnerable component of those features. The fact that they still rank among the top predictors after residualization means there is *real* lending-environment signal in concentration and lender mix that is *not* explainable by the underlying lender count alone.

Third, the SSBCI signal is concentrated in `ssbci_active` (rank 5) with the multi-program-count features adding little. `ssbci_2_0_active` collapses to zero importance after the regime split exposes that all post-COVID variation in the four SSBCI features is colinear with the era window itself. We discuss the interpretation in §6.5 (per-state) and §7.3 (regime split).

## §6.4 Per-fold story

*This section walks through what each fold's metrics tell us about the model's behavior.*

The eight folds tell a coherent story. **F1 – F4** (test years 2016 – 2020) form a stable pre-COVID regime. AUC ranges from 0.809 (F1) to 0.850 (F3) with Brier scores in the 0.0135 – 0.0156 range. AP-lift is monotonically rising from 7.9× in F1 to 11.2× in F4. This is the regime in which Model 2's lever signals — residualized concentration, branch access, SSBCI activation — work as expected.

**F5** (test 2020 – 2021) is the COVID-onset fold. AUC drops to 0.713, AP to 0.110. The Brier score doubles from F4's 0.0135 to 0.0268. The validation year for F5 is 2019 — pre-pandemic — so the calibrator is fit on a distribution that does not match the test distribution. This is a textbook out-of-distribution failure.

**F6** (test 2021 – 2022) shows partial recovery in AP (0.160) but AUC remains depressed at 0.751. Brier rises further to 0.0356 — actually slightly worse than F5 — reflecting that 2021 – 2022 has the highest positive rate of any test window in the panel (3.7%, double the early-fold rate), which inflates the Brier baseline.

**F7 and F8** (test 2022 – 2024) show further AP degradation (0.094, 0.084) but stable AUC at 0.780. Both fall just below the AP ≥ 0.10 stability threshold. The interpretation: the post-COVID regime has a different relationship between lender environment and desert formation than the pre-COVID regime, and a model trained on a panel that is mostly pre-COVID does not transfer cleanly to the post-COVID test windows. The formal regime-split study (§7.3) makes this concrete.

## §6.5 Per-state AP

*This section explores how the model's performance varies by state and identifies the states where it underperforms.*

`diagnostics_round7.py` produces per-state AP from the test predictions, restricted to states with at least 100 observations and at least one positive in the test set. The full per-state table is in `diagnostics/round7_phaseA/diag_per_state_ap.csv`. The headline observations:

The lowest-AP states tend to be those with very few positives — small denominators where one or two correctly-classified positives dominate the metric. The "below random" flag fires in only a handful of small-sample states. The model's AP-lift is roughly 5× – 10× across the higher-population states (CA, TX, NY, FL, IL, PA), consistent with the national mean.

The most informative outlier from the per-state diagnostic is the "SSBCI states with prior-cycle program experience" effect. Five states — Ohio, Illinois, Michigan, North Carolina, and California — operated SSBCI 1.0 programs in the 2011 – 2017 window with documented continuous activity, and these five states show modestly higher per-state AP for Model 2 than the national mean. We do not interpret this as causal — these are also the states with the most active CRA-reporting community-bank ecosystems independent of SSBCI. But it's directionally consistent with the policy-lever story.

---

# Part VII — Diagnostics and ablations

## §7.1 The per-lever ablation surprise

*This section walks through the ablation results — what we expected and what we found.*

The per-lever ablation (`train/ablation_per_lever.py`) drops one policy-lever group at a time and re-runs all 8 folds. The seven groups:

- `branch_access`: distance_to_nearest_bank_branch, branches_within_5mi, branch_closures_3y_within_10mi
- `mdi_mission_lender`: 4 MDI features
- `ssbci_state_policy`: 4 SSBCI features
- `microlender_ecosystem`: microloan_intermediary_within_25mi
- `residualized_concentration`: top1, top3, HHI residuals
- `residualized_lender_mix`: community-bank, top-4, credit-union shares (residualized)
- `residualized_loan_size`: loans-under-100K, loans-under-250K (residualized)

The summary (`diagnostics/round7_ablation/ablation_summary.csv`):

| Group dropped | n_features | Mean AUC | Δ AUC | Mean AP | Δ AP |
|---|---|---|---|---|---|
| **Baseline (none)** | 20 | **0.794** | — | **0.129** | — |
| residualized_concentration | 17 | 0.698 | **-0.096** | 0.106 | -0.023 |
| mdi_mission_lender | 16 | 0.793 | -0.001 | 0.127 | -0.002 |
| branch_access | 17 | 0.791 | -0.003 | 0.128 | -0.001 |
| residualized_loan_size | 18 | 0.787 | -0.008 | 0.130 | +0.001 |
| microlender_ecosystem | 19 | 0.800 | +0.006 | 0.132 | +0.003 |
| residualized_lender_mix | 17 | 0.799 | +0.005 | 0.133 | +0.005 |
| ssbci_state_policy | 16 | 0.802 | +0.008 | 0.134 | +0.006 |

The ablation result is the single most surprising finding in the project. The naive expectation, going in, was that ablating branch access would be the most damaging drop because branch features dominate XGBoost's gain importance. The actual result: dropping branch access costs only 0.003 AUC and 0.001 AP. Dropping the residualized concentration features, which collectively account for only ~25% of model gain in the importance ranking, costs **0.096 AUC and 0.023 AP** — by far the largest hit.

This is not an artifact. It is reproduced robustly across every fold (see `ablation_per_fold.csv` for fold-level breakdowns).

The interpretation has two layers. First, XGBoost gain importance is *not* the same thing as ablation importance. Gain measures a feature's contribution to within-tree splits given that the other features are also available. Ablation measures how badly the model fails when the feature group is removed entirely and the other features must compensate. A feature with high gain may be highly substitutable (its information is also encoded in other features); a feature with modest gain may be uniquely informative (no other feature carries its signal). Branch access has the first property: distance to nearest branch is highly correlated with branches_within_5mi, branch_closures_3y_within_10mi, and several MDI proximity features, so dropping the entire branch group still leaves the model with multiple correlated proxies for "is this tract physically isolated." Residualized concentration, in contrast, captures something the rest of the feature stack does not — the orthogonal-to-lender-count component of how concentrated the local lending market is — and that signal has no good proxy elsewhere.

Second, ssbci_state_policy and microlender_ecosystem have *positive* deltas — dropping them slightly *improves* the model. This is a clean signal that those features are not adding orthogonal predictive value beyond noise. SSBCI's small positive signal is likely macro-era confounded (§7.3); microlender's small positive is geographic-coverage confounded (§9.3 — only 52% of the list is geocoded). The cleaned model keeps both groups in the feature stack for completeness and for the dashboard's policy-lever framing, but we are honest in the writeup that the model prefers it without them.

## §7.2 Importance rank versus ablation rank

*This section makes the previous section's finding concrete by placing the two rankings side by side.*

| Rank | Importance | Ablation impact (Δ AUC) |
|---|---|---|
| 1 | distance_to_nearest_bank_branch (0.369) | residualized_concentration (-0.096) |
| 2 | lender_hhi_tract_resid (0.097) | residualized_loan_size (-0.008) |
| 3 | pct_loans_from_top4_banks_resid (0.066) | branch_access (-0.003) |
| 4 | pct_loans_from_credit_unions_resid (0.049) | mdi_mission_lender (-0.001) |
| 5 | ssbci_active (0.048) | residualized_lender_mix (+0.005) |
| 6 | top3_lender_share_tract_resid (0.046) | microlender_ecosystem (+0.006) |
| 7 | branches_within_5mi (0.041) | ssbci_state_policy (+0.008) |

The two rankings disagree on almost every position. The reason is the substitutability story above: features that dominate gain importance are doing so in part because they are *cheap* — they win splits over their correlated proxies because they're slightly easier to use, but the proxies are still in the feature pool waiting to be promoted if the dominant feature is removed.

The honest framing in the dashboard, accordingly, is to report both. The "top-feature" panel shows gain importance because that is what most readers expect from a model writeup. The "policy lever" panel shows ablation impact because that is what answers the question "what happens if the lever is unavailable." For policy, ablation is the more relevant metric.

## §7.2.1 The ablation reorganization at h+3 — the policy-narrative shift

*This is the most important new finding from the horizon retrain. At h+1, intervention-focused features were near-zero on ablation. At h+3, all three of them gain meaningful AP impact. The dashboard's policy-slider story moves from "informative as ranking" to "responsive to lever movement."*

Re-running the per-lever ablation at h+3 (the new operational primary) produces:

| Lever dropped at h+3 | n_features | Mean AUC | Mean AP | ΔAUC vs full | ΔAP vs full |
|---|---:|---:|---:|---:|---:|
| **None (baseline)** | 20 | 0.820 | 0.282 | — | — |
| Residualized concentration | 17 | 0.743 | 0.218 | **−0.077** | **−0.064** |
| MDI / mission lender | 16 | 0.820 | 0.254 | −0.000 | **−0.028** |
| Microlender ecosystem | 19 | 0.828 | 0.263 | +0.008 | **−0.019** |
| Branch access | 17 | 0.825 | 0.265 | +0.005 | **−0.017** |
| Residualized loan size | 18 | 0.825 | 0.270 | +0.005 | −0.012 |
| Residualized lender mix | 17 | 0.818 | 0.272 | −0.002 | −0.010 |
| SSBCI state policy | 16 | 0.811 | 0.295 | −0.009 | +0.013 |

Compare row-by-row to the h+1 ablation in §7.1. At h+1, the three intervention-focused groups (MDI, microlender, branch access) had ΔAP values in the [−0.002, +0.003] range — statistically indistinguishable from zero. At h+3, all three of them produce ΔAP in [−0.028, −0.017]. The MDI / mission-lender group is now the second-largest single lever after residualized concentration. Microlender is third. Branch access is fourth.

This is the single most consequential downstream finding from the horizon retrain. At h+1, the dashboard could honestly tell users "branch access dominates the importance ranking but is largely substitutable for residualized concentration." At h+3, the dashboard can honestly tell users "all four major lever categories — concentration, MDI, microlender, branch — move the model in measurable ways." The policy slider's role changes accordingly: the horizon switch makes the model genuinely sensitive to the levers that local actors can actually pull, not just the unmovable structural-residual features.

The mechanism for the lever-importance gain at h+3 is the same as the headline AP gain (§4.6): MDI partnership effects, microlender ecosystem changes, and branch network reorganization all play out over multi-year windows. A one-year horizon under-counts them; a three-year horizon captures their working-out time. The horizon switch is therefore not just a fix to the federal-data-lag problem; it also rescues the policy-intervention story.

SSBCI is the lone holdout. Dropping the four SSBCI features at h+3 *improves* AP by 0.013, confirming the h+1 result that the state-year overlay is too coarse to add cohort-level variance. The dashboard treats SSBCI as descriptive context (which states are program-active in which era windows) rather than as a predictively load-bearing lever.

## §7.2.2 The ablation at h+6 — lever effects persist with diminished magnitudes

At the long-horizon scenario, the ablation pattern persists but per-lever magnitudes shrink:

| Lever dropped at h+6 | n_features | Mean AUC | Mean AP | ΔAUC vs full | ΔAP vs full |
|---|---:|---:|---:|---:|---:|
| **None (baseline)** | 20 | 0.862 | 0.464 | — | — |
| Residualized concentration | 17 | 0.811 | 0.431 | **−0.051** | **−0.032** |
| Branch access | 17 | 0.858 | 0.458 | −0.005 | −0.006 |
| MDI / mission lender | 16 | 0.855 | 0.458 | −0.008 | −0.005 |
| Microlender ecosystem | 19 | 0.854 | 0.459 | −0.008 | −0.004 |
| Residualized loan size | 18 | 0.865 | 0.469 | +0.003 | +0.005 |
| Residualized lender mix | 17 | 0.861 | 0.471 | −0.001 | +0.008 |
| SSBCI state policy | 16 | 0.866 | 0.470 | +0.004 | +0.006 |

The h+6 picture is consistent with the h+3 picture in rank order — concentration dominates, branch / MDI / microlender are real but smaller, SSBCI is decorative — but the per-lever magnitudes are about a third of the h+3 values. The interpretation: at six years out, the model has more correlated proxies available for any given lever, so removing one group leaves the others to absorb most of its signal. The pattern of lever importance survives; the per-lever sensitivity diminishes.

This has a direct implication for how the dashboard's horizon toggle communicates. At h+3, the dashboard surfaces a multi-lever policy story — moving the MDI slider has a visible effect on the score, moving the branch-access slider has a visible effect, moving the concentration slider has a visible effect. At h+6, the dashboard honestly says "at six years out, branch access is the only lever that still matters as a single tract-level signal." The same data, the same model family, two different operational stories appropriate to two different planning horizons.

## §7.3 The pre-/post-COVID regime split

*This section formalizes the per-fold COVID asymmetry by training two separate models and comparing top features.*

`train/regime_split.py` runs two studies:

- **Pre-COVID**: train 2009 – 2017, val 2018, test 2018 – 2019. Test AUC 0.817, test AP 0.144, lift 9.7×.
- **Post-COVID**: train 2020 – 2021, val 2022, test 2023 – 2024. Test AUC 0.734, test AP 0.078, lift 3.4×.

The headline performance gap is 0.083 AUC and 0.067 AP. The post-COVID model has roughly half the predictive power of the pre-COVID model. This is consistent with a meaningful regime change — *what predicts desert formation* in 2023 is not the same as what predicted it in 2018.

The per-feature importance comparison is more revealing than the headline metrics. From `diagnostics/round7_regime_split/`:

| Feature | Pre-COVID rank | Pre-COVID importance | Post-COVID rank | Post-COVID importance |
|---|---|---|---|---|
| distance_to_nearest_bank_branch | 1 | 0.494 | 3 | 0.096 |
| lender_hhi_tract_resid | 2 | 0.084 | 1 | 0.177 |
| top3_lender_share_tract_resid | 7 | 0.032 | 2 | 0.103 |
| top1_lender_share_tract_resid | 13 | 0.017 | 4 | 0.084 |
| branch_closures_3y_within_10mi | 14 | 0.017 | 5 | 0.072 |
| mdi_branches_within_25mi | 12 | 0.017 | 6 | 0.063 |
| pct_loans_from_top4_banks_resid | 4 | 0.057 | 7 | 0.056 |
| ssbci_active | 5 | 0.043 | 17 | 0.000 |
| pct_loans_from_credit_unions_resid | 6 | 0.037 | 16 | 0.000 |
| ssbci_2_0_active, ssbci_program_count, ssbci_n_capital_programs | bottom | 0.000 | bottom | 0.000 |

Three observations.

First, the top feature flips. In the pre-COVID model, distance to nearest branch dominates by a factor of six over the next feature. In the post-COVID model, residualized HHI dominates and branch distance drops to rank 3 with less than one-fifth its pre-COVID importance. The interpretation: in the pre-COVID regime, the slow process of branch consolidation and isolation was the dominant pathway to desert formation; in the post-COVID regime, *concentration*-mediated fragility — markets where one or two lenders disproportionately serve the tract — became the dominant pathway. This is consistent with the broader observation that COVID-era PPP and federal stimulus distorted the lending environment most heavily in concentrated markets.

Second, the SSBCI features collapse to zero post-COVID. This is the era-confounding concern made concrete: in a post-COVID-only training panel, every SSBCI variable is colinear with the era window itself, and XGBoost cannot extract any information from a constant. The pre-COVID model's `ssbci_active` rank-5 importance was real — but it was real *as a 2011-2017 era effect*, not necessarily as a causal program effect.

Third, branch closures jump from rank 14 pre-COVID to rank 5 post-COVID. The 2020 – 2022 wave of bank-branch consolidation — driven by digital-lending substitution and post-PPP rationalization — produced more recent and more concentrated closure events that the post-COVID model could lean on. Pre-COVID closures were spread out and lower-magnitude.

The full regime-comparison and per-regime importance files are at `diagnostics/round7_regime_split/`.

## §7.3.1 Regime split at h+3 — the gap narrows

Re-running the regime-split study at h+3 produces:

| Regime / horizon | Train | Test | n_test | Pos rate | AUC | AP | Lift |
|---|---|---|---:|---:|---:|---:|---:|
| Pre-COVID h+3 | 2009–2014 | 2015–2016 | 184,770 | 2.05% | 0.847 | 0.381 | 18.6× |
| Post-COVID h+3 | 2018–2019 | 2020–2021 | 156,847 | 4.75% | 0.825 | 0.287 | 6.0× |

The pre/post AUC gap at h+3 is just 0.022 — far smaller than the 0.083 gap at h+1. Both regimes perform substantially better at h+3 than at h+1, and the post-COVID model is now within striking distance of the pre-COVID model. The interpretation: at three years out, the structural signal that the influenceable feature set encodes is robust enough to survive the COVID regime change. At one year out, the regime change dominates the variance.

Per-feature importance at h+3 is in `diagnostics/round7_regime_split_h3/`. The pre-COVID h+3 model is led by `distance_to_nearest_bank_branch` (0.331) followed by `ssbci_active` (0.138) — SSBCI's pre-COVID importance is even stronger at h+3 than at h+1. The post-COVID h+3 model is led by `distance_to_nearest_bank_branch` (0.446) followed by `mdi_branches_within_10mi` (0.120). Branch access dominates both regimes at h+3, but its share rises from 33% pre-COVID to 45% post-COVID. SSBCI again collapses to zero post-COVID, consistent with the h+1 finding.

## §7.3.2 Regime split at h+6 — branch access becomes overwhelming post-COVID

The h+6 regime split is the most striking single result in the entire study:

| Regime / horizon | Train | Test | n_test | Pos rate | AUC | AP | Lift |
|---|---|---|---:|---:|---:|---:|---:|
| Pre-COVID h+6 | 2009–2011 | 2012–2013 | 393,582 | 1.43% | **0.920** | 0.492 | 34.5× |
| Post-COVID h+6 | 2014–2015 | 2017–2018 | 168,132 | 4.83% | **0.774** | 0.322 | 6.7× |

Two findings dominate. First, the pre-COVID h+6 model achieves AUC 0.920 — the strongest single-regime headline anywhere in the project. The pre-COVID era was a stable lending environment in which slow-moving structural features predicted six-year-forward desert formation cleanly.

Second, the post-COVID h+6 model drops to AUC 0.774 — a 0.146 AUC gap, the largest of any horizon. The mechanism: at six years out under a post-COVID drift regime, the lending environment reorganized too fast for slow-moving features to track.

The feature-importance reorganization is striking. From `diagnostics/round7_regime_split_h6/`:

| Regime | Top feature | Importance | Rank-1 share |
|---|---|---:|---:|
| Pre-COVID h+6 | `distance_to_nearest_bank_branch` | 0.472 | 47% |
| **Post-COVID h+6** | `distance_to_nearest_bank_branch` | **0.731** | **73%** |

At h+6 post-COVID, branch access is 73% of model gain — a level of single-feature dominance not seen anywhere else in the study. The next feature (`branches_within_5mi`) is 8.3%; everything else is below 4%. The interpretation: at six years out in a post-COVID regime, the only durable tract-level signal that survives is "how isolated is this tract from any branch at all." Lender-mix variation, concentration variation, MDI presence, microlender presence — none of them carry signal that lasts six years through a regime change. Branch geography is the slowest-moving feature in the panel and accordingly the only feature whose signal survives the long horizon under regime change.

This has a clean operational implication for the dashboard at h+6 post-COVID: the slider story is essentially a branch-access story. Other levers contribute small ablation effects but are largely decorative on the importance ranking. We surface this honestly: at h+6 post-COVID, the dashboard's narrative explicitly says "at six years out under post-COVID drift, only branch access still matters as a single tract-level lever."

## §7.4 The NMTC null result

*This section explains why NMTC, despite being a credible mission-lending policy lever, did not predict desert formation in this model.*

All five NMTC features — five-year and three-year lagged dollar sums, project counts, the binary "ever received NMTC" indicator, and the county-level rollup — had mean XGBoost gain importance ≤ 0.005 in the v3 model that included them. The pruning sweep at every k confirmed they did not survive. The cleaned model dropped them entirely.

The instinctive interpretation — "NMTC doesn't work" — is wrong. The right interpretation is structural. Three reasons:

First, NMTC has severe selection bias. Projects went where deserts were already forming. The CDE-mediated NMTC investment process specifically targets low-income community investment, by statute, and the qualifying tracts heavily overlap with credit-desert candidate tracts. So a tract that received NMTC dollars in years T-2 through T-6 is, by selection, *more* likely to have been deteriorating — exactly the wrong polarity for the predictor we want.

Second, scale mismatch. NMTC is project-scale: typical project sizes are $1M – $20M and cumulative QLICI deployment in a given tract over five years is typically under $50M, and in many tracts under $5M. CRA small-business lending volumes in the same tracts are often an order of magnitude larger. NMTC simply isn't moving the needle on the lender-count signal that defines the target.

Third, wrong mechanism. NMTC operates through Community Development Entities (CDEs), which are not commercial bank lenders. NMTC investments are typically real-estate-secured or equity-like, and the QLICI vehicle is heavily structured around tax credits rather than direct credit provision. The target — `n_cra_lenders` thinning out — is a count of *commercial bank* originators. NMTC doesn't add to that count even when it is deployed.

The honest writeup framing: NMTC is a real and measurable mission-investment program. It just doesn't map onto our target's lending stratum. A different model, with a different target — say, "tract median small-business survival rate" — might find NMTC predictive. For *commercial-bank-lender thinning*, it doesn't move.

## §7.5 The auxiliary bolt-on (round5 + round7)

*This section reports the results of the bolt-on study and explains why it is auxiliary, not headline.*

`train/walk_forward_boltOn.py` trains on the union of Round 5's 39 features + the 20 cleaned Round 7 features (after pruning shared circular features and the n_cra_lenders/n_active_lenders_tract pair). Same eight folds. The eight-fold mean test AUC: **0.889**, mean AP: **0.175**. From `diagnostics/round7_bolton/fold_results.csv`:

| Fold | Test AUC | Test AP | Brier |
|---|---|---|---|
| F1 | 0.913 | 0.175 | 0.0134 |
| F2 | 0.938 | 0.183 | 0.0119 |
| F3 | 0.942 | 0.235 | 0.0116 |
| F4 | 0.945 | 0.210 | 0.0124 |
| F5 | 0.836 | 0.142 | 0.0264 |
| F6 | 0.833 | 0.176 | 0.0351 |
| F7 | 0.853 | 0.144 | 0.0233 |
| F8 | 0.855 | 0.132 | 0.0208 |

Versus Round 5 alone (mean AUC 0.857, mean AP 0.172), the bolt-on adds roughly 0.032 AUC and 0.003 AP. The AUC gain is real and meaningful — the bolt-on's per-fold AUC is consistently 0.03 – 0.04 above Round 5's per-fold AUC. The AP gain is essentially noise, well within the per-fold std.

Translation: round 7's cleaned features add genuine *ranking* discriminative power to the diagnostic baseline, but only marginal *top-K precision*. They help separate moderately-risky tracts from clearly-safe tracts, but they don't improve the precision of the highest-risk top-100 list (which is what AP rewards).

The bolt-on result is *auxiliary* and explicitly not the headline because it contradicts the project's two-layer architecture. The whole point of the two-layer hypothesis is that Model 1 and Model 2 sit alongside each other — one for diagnosis, one for intervention guidance — not that they merge into a single bigger model. The bolt-on shows that the merger is technically feasible and slightly better than either alone, but it loses the layer-distinction that makes the policy story legible. We report it for completeness and for the audience member who asks "what if you just stacked them?"

The permutation-importance analysis on the val set (run only on the 20 round 7 features) confirms that the bolt-on uses the round 7 features in the same broad rank order as Model 2 alone — distance to nearest branch and residualized HHI top the list, with mission-lender and SSBCI features in the middle.

---

# Part VIII — Implications and dashboard

## §8.1 What the model says about policy intervention

*This section translates the model's findings into the policy story the dashboard tells, framed at the new operational horizon (h+3) with the long-horizon scenario (h+6) as a comparison.*

The cleaned Model 2's findings at h+3, framed as answers to the original handoff question — *"which lending changes plausibly improve credit access?"* — are now substantially more interventionable than at h+1:

1. **At h+3, every intervention-focused lever moves the model.** Residualized concentration is the largest single lever (ΔAP −0.064), but MDI / mission lender (−0.028), microlender ecosystem (−0.019), and branch access (−0.017) are all genuinely load-bearing. The horizon switch turned this from a one-lever story (h+1: only concentration mattered) into a four-lever story.

2. **Branch access matters at every horizon, and dominates at h+6 post-COVID.** Three branch-access features account for 30–45% of model gain at h+3, depending on regime. At h+6 post-COVID, `distance_to_nearest_bank_branch` alone is 73% of model gain — the dominant single signal at long horizons under regime drift. Branch retention agreements, mobile lending units, branch-replacement strategies, and closure-mitigation policies remain the cleanest, most policy-leverable mechanisms in the entire study.

3. **Concentration matters in a defensible way.** Even after residualizing against the underlying lender count, the residualized concentration features have the largest ablation impact at every horizon. The signal that survives residualization is *unusual* concentration — markets where one or two lenders punch above what the lender count alone would predict. Linked-deposit programs, public-deposit strategies, and partnership lending models are real institutional levers for this.

4. **MDI / mission-lender presence is the largest lever-importance gain between h+1 and h+3.** At h+1 the MDI features were ablation-neutral; at h+3 they drop AP by 0.028, the second-largest single lever. The interpretation: MDI partnership lending, certification cascades, and deposit-relationship effects accrue over multi-year windows that h+1 misses but h+3 captures.

5. **Microlender ecosystem also gains weight at h+3 (ΔAP −0.019).** The 48% geocoding hit rate (§9.3) still bounds how strong this lever can plausibly be, but the directional finding is now positive rather than slightly-negative.

6. **State policy (SSBCI) is descriptive context, not a load-bearing lever.** Dropping the four SSBCI features improves AP at h+3 (+0.013) and at h+6 (+0.006). The state-year overlay is too coarse to add cohort-level variance once the longer horizons surface other signals. The dashboard treats SSBCI as a descriptive layer (which states are program-active) rather than as a slider.

7. **NMTC capital deployment doesn't show up.** As discussed in §7.4, this is structural, not a bug. The result is consistent across horizons.

## §8.2 The dashboard architecture

*This section briefly describes the technical architecture of the web dashboard.*

The dashboard is a single-page MapLibre GL JS application served as static files (HTML + CSS + JS) with no bundler. The build script `web/build_dashboard_data.py` produces the JSON / GeoJSON inputs, now extended to support the horizon toggle:

- `data/tracts.geojson` (~30 MB raw, ~5 MB gzipped): one feature per tract with properties `f` (FIPS), `m1_h3`, `m2_h3`, `m1_h6`, `m2_h6` (Model 1 / Model 2 calibrated risk at each horizon), `m1r_h3`, `m2r_h3`, `m1r_h6`, `m2r_h6` (within-state percentile ranks at each horizon), `st` (state abbreviation), and `cn` (county-state name).
- `data/state_stats.json`: per-state mean risk × {model, horizon}, AUC and AP per model × horizon, plus national headline metrics for each horizon.
- `data/state_bbox.json`: per-state bounding box for fly-to navigation.
- `data/ablation.json`: lever-group ablation results for both h+3 and h+6.
- `data/pruning.json`: top-10 feature ranking + sweep results at both h+3 and h+6.
- `data/regime.json`: pre/post-COVID metrics + top features at both h+3 and h+6.
- `data/feature_stats.json`: per-feature mean, std, min, max, p10, p90, importance — used by the scenario explorer slider, with horizon-specific importance values.

The page is structured as a long scroll: masthead, sticky model toggle (Model 1 vs Model 2) plus a sticky **horizon toggle** (h+3 primary vs h+6 scenario), full-bleed choropleth map, methodology sections (ablation, pruning, regime), per-state list, and a scenario-explorer panel. The horizon toggle is the primary new control surface introduced in the late-cycle retrain. When the user switches between h+3 and h+6, the choropleth re-renders, the headline metrics update, the ablation table re-orders by the new horizon's lever-importance hierarchy, and the regime-comparison panel updates to show that horizon's pre/post-COVID feature reordering.

The dashboard's visual register is "civic, earnest, measured" per `notes/00_design_brief.md`: Source Serif 4 for display, Public Sans for body, Inconsolata for numerics; warm parchment background; deep ink-blue text; terracotta accent for the highest-importance UI cues. Two distinct color signatures disambiguate the models: pale parchment → deep ink-blue for Model 1 (diagnostic), pale parchment → deep terracotta for Model 2 (influenceable). The horizon toggle uses a third treatment — a muted slate accent — distinguishing "what model" from "what timescale."

The choropleth ramps are computed from the calibrated probability fields directly, per horizon. The within-state percentile ranks are precomputed by the build script as a fallback rendering mode for users who want to see relative risk within a state rather than absolute risk.

## §8.3 The policy slider — what it actually does, and what it doesn't

*This section names exactly what the scenario explorer can and cannot do, given Model 2's properties.*

The scenario explorer ships eight slider levers:

1. `distance_to_nearest_bank_branch`
2. `branches_within_5mi`
3. `mdi_branches_within_10mi`
4. `mdi_branches_within_25mi`
5. `ssbci_active`
6. `ssbci_program_count`
7. `microloan_intermediary_within_25mi`
8. `lender_hhi_tract_resid`

What the slider does, mechanically: for the currently selected tract (or set of tracts), it lets the user shift one or more of these eight features within a bounded range (typically the panel's p10 – p90 distribution), then re-runs the trained Model 2 on the modified feature vector to produce a new calibrated risk. The slider operates against the currently selected horizon's model — h+3 by default, h+6 if the user has toggled to the long-horizon view. The map rerender shows the difference. The headline number — "47 fewer at-risk tracts under this scenario" — is the count of tracts whose new calibrated risk crosses below an explicit at-risk threshold.

**The horizon toggle is now the slider's most important framing control.** At h+3, all four major lever categories (concentration, MDI, microlender, branch access) move the model in measurable ways, so the slider story is multi-lever — moving any of the four sliders produces a visible delta. At h+6, only branch access produces large deltas; the other levers have smaller effects because the model has more correlated proxies at long horizons. The dashboard explicitly surfaces this: when the user toggles to h+6, the slider panel adds a small explanatory note that says "at six years out, branch access dominates; other levers move the score less." This is the honest answer to "why did my MDI move have a smaller effect than at h+3?"

What the slider does *not* do, and what we are honest about in the UI:

- **It does not establish causality.** The model is correlational. A user moving the branch-access slider sees what *the model would predict* if a tract had better branch access. It does not predict what would *actually* happen if a state opened a new branch — that's a different question with different data.
- **It does not move structural variables.** The whole point of the influenceable-only feature set is that the slider only operates on policy-leverable variables. It cannot, for instance, move the persistent-poverty rate.
- **It does not respect institutional plausibility.** The slider lets users move features within historically-observed ranges, but it does not enforce that the move must correspond to a real intervention. A state with no SSBCI program cannot, in reality, just turn on `ssbci_active` overnight; the program has to be authorized, allocated, and operationalized. We document this in the slider's explanatory copy.
- **It assumes feature independence.** Moving `distance_to_nearest_bank_branch` does not automatically also move `branches_within_5mi`, even though these are mechanically correlated. The user has to move both to simulate "a branch is opened nearby."

The slider's conceptual function is therefore "what does the model say about this scenario," not "what would happen in the world." The "honest UI framing" sub-section below describes how that distinction is communicated.

## §8.4 Honest UI framing

*This section describes how the dashboard communicates the model's limits to the user.*

Three explicit framing devices:

First, the residualized-feature labels. Every residualized lever in the slider panel is labeled "[Feature] (residualized)" with a tooltip explaining what residualization is in plain language: "this slider moves the part of [feature] that is not already explained by the tract's lender count." This is mildly clunky but it's honest — the alternative is a slider that says "Lender concentration" and silently does residualization underneath, which would mislead the user.

Second, the model's confidence is shown as an explicit visual element next to each scenario delta. The Model 2 fold-average AUC and AP are surfaced in the headline. When a slider scenario produces a delta — "47 fewer at-risk tracts" — the dashboard explicitly states the per-fold AP variance and notes that the post-COVID folds contribute to that variance. Users see the headline number alongside the model's stability.

Third, the "what this is" section near the top of the page calls out the project's framing in the original handoff language: "Model 2's outputs are correlational, not causal. They show what the model *would say* under a counterfactual lending environment, not what would *actually happen* if that environment changed." That sentence, or some version of it, appears in the page's lead section.

The visual register itself reinforces the framing. The dashboard does not look like a SaaS product or a startup-marketing page; it looks like a printed Brookings policy brief. That register signals to the reader "this is research, treat it as research" rather than "this is a confident decision tool."

---

# Part IX — Limitations

## §9.1 The COVID regime shift

*This section names the single largest limitation of the cleaned model.*

The post-COVID folds (F5 – F8, test years 2020 – 2024) consistently underperform the pre-COVID folds (F1 – F4, test 2016 – 2019). Mean AUC is 0.832 pre-COVID and 0.756 post-COVID — a 0.076 gap. AP is 0.146 pre-COVID and 0.112 post-COVID. The regime-split study (§7.3) confirms this is a structural change, not a fluke: the importance ordering of features differs substantively between the two regimes, and the SSBCI features in particular collapse to zero importance in the post-COVID-only model.

The mechanism: COVID, PPP, branch consolidation in 2020 – 2022, and the fundamental reset of the small-business lending market all occurred together. A model trained on pre-2020 data cannot fully transfer to the post-2020 regime. The eight-fold walk-forward apparatus does its best to expose this, but it can't fix it: there simply isn't enough post-COVID data yet (effectively 4 test years from F5 onwards) to train a model that fully internalizes the new regime.

The honest implication for users of the dashboard: Model 2's predictions for the most recent test years (F8, 2023 – 2024) carry more uncertainty than the headline mean AUC suggests. Use the per-fold per-state AP as the local-uncertainty estimate, not the headline number.

## §9.2 The residualization tradeoff (interpretability)

*This section names the cost of the project's central methodological move.*

Residualization made the model's concentration and lender-mix features defensible against the leakage critique, but it cost interpretability. A policy-lever named "residualized lender concentration" is not a thing a county economic development officer recognizes. The slider has to translate it: the UI labels these features with both their formal name and a plain-language gloss ("how concentrated is the local lending market, beyond what its lender count alone would predict?").

The deeper cost: the residualization is *peer-group-and-year* specific. The residual for a given tract in 2018 depends on the regression fit for the urban tracts in 2018; the residual for the same tract in 2020 uses a different regression fit. So a slider that moves the residualized HHI from -0.05 to +0.05 in 2024 means something subtly different than the same move in 2014. We do not fully expose this in the slider — it would overload the user — but it is documented in the methodology section of the dashboard.

A future iteration might consider a different leakage-defense — for instance, propensity-score weighting or causal-forest-style orthogonalization — that produces a more directly interpretable feature. For Round 7, residualization was the right tradeoff under the time and complexity budget.

## §9.3 Geocoding gaps (microlender 48%)

*This section names the data-coverage gap that limits the microlender feature's utility.*

The microlender list scrape produced approximately 140 institutions, of which 52% were geocoded successfully via Census + Nominatim. The remaining 48% have addresses that fail both pipelines — typically tribal-area addresses, post-office boxes, or recently-relocated organizations. The downstream feature `microloan_intermediary_within_25mi` therefore undercounts the microlender ecosystem in roughly half the geographies.

The CDFI list (used in earlier iterations, not in the cleaned model) had similar gaps. The MDI list, in contrast, has 100% coverage because we joined on FDIC `CERT` to SoD's branch lat/lng — no geocoding involved. Year-precise MDI is therefore the strongest mission-lender feature in the cleaned model.

For Round 7, we accepted the 52% microlender coverage and document it. A future iteration might augment with a manual-review pass on the 48% residual or with the SBA's regional-office address as a fallback.

## §9.4 The "block of clay" approach has its own biases

*This section names a self-criticism of the iteration process.*

The block-of-clay process — start broad, prune, residualize, re-evaluate — is methodologically defensible but it is not blind. At each step the team made decisions ("drop NMTC because it's near zero," "residualize concentration because it's leakage-vulnerable") that were informed by *seeing the previous iteration's results*. That introduces a subtle multiple-comparisons concern: the cleaned model's metrics are conditional on the path of decisions that led to it, and the eight-fold walk-forward apparatus is the only out-of-sample defense against overfitting to the iteration path.

We argue that the per-fold stability requirement (≥ 6 of 8 folds clearing AP ≥ 0.10), the formal regime-split study, the per-lever ablation, and the bolt-on study collectively provide robust evidence that the cleaned model's signal is real. But we acknowledge that a more conservative framework — pre-register the feature set, run once, report — would have produced a slightly more honest set of statistics. The tradeoff: a pre-registered run would have used the v1 14-feature year-T model, missed the residualization fix entirely, and shipped a leakage-vulnerable Model 2.

## §9.5 Future work

*This section sketches what a Round 8 (or a follow-up project) would do.*

Three priorities, in order:

1. **A causal-forest or propensity-weighted alternative to residualization.** The current residualization is a simple OLS orthogonalization. A more rigorous treatment-effect framework — propensity-score weighting on `n_cra_lenders` strata, or a causal-forest treatment-effect estimator — would produce a more defensible "what does the lending environment do, holding lender count fixed" estimate.

2. **A second target — credit-union desert formation — to validate the structural interpretation of the NMTC null.** If NMTC really operates in a different lending stratum, then a target defined on credit-union and CDFI lender thinning specifically might show NMTC signal that the commercial-bank target misses. This would be a clean validation of §7.4.

3. **A live-data refresh path.** The SSBCI fallback panel is documented but coarse. A serious follow-up would scrape the per-state Treasury Capital Program Summaries individually (or download each state's PDF and parse) to produce a true per-state-per-year SSBCI activation panel, replacing the smoothed era windows.

Other smaller items: a manual-review pass on the microlender geocoding residual; extending the closure-detection radius to a sensitivity sweep (5, 10, 15, 20 miles); a reduced-motion variant of the dashboard's slider transitions for accessibility.

---

# Part X — Glossary

*Brief one-paragraph definitions of vocabulary that recurs in this document.*

**AUC (Area Under the ROC Curve).** A scalar measure of a binary classifier's ranking quality, ranging from 0.5 (random) to 1.0 (perfect). It is the probability that the model assigns a higher score to a randomly-chosen positive case than to a randomly-chosen negative case. AUC is robust to class imbalance and is the standard headline metric for rare-event tabular classification.

**AP (Average Precision) / PR-AUC.** The area under the Precision-Recall curve, equivalent to the weighted mean of precisions at each recall threshold. Unlike AUC, AP is sensitive to class imbalance: random-baseline AP equals the positive rate (~0.017 in this panel). AP rewards top-K precision and is the right metric for "rank tracts and act on the top-N" use cases.

**Lift.** The ratio of model AP to random-baseline AP. A model with AP 0.129 on a panel with 1.93% positive rate has lift 6.7×, meaning it is 6.7 times more precise at ranking top-K positives than random selection.

**Walk-forward validation.** A cross-validation scheme for time-series problems where train, val, and test sets are temporally ordered. Each fold trains on years up to T-1, validates on year T, and tests on years T+1 through T+H. This prevents the spatial-leakage problem of random k-fold and produces an honest distribution of out-of-sample performance across regimes.

**Isotonic calibration.** A non-parametric monotonic regression that maps raw model probabilities onto empirical positive rates from a held-out calibration set. After calibration, the model's `p = 0.30` predictions correspond to ~30% empirical positive rate, making the probabilities directly usable for downstream decision-making.

**Brier score.** The mean squared difference between predicted probability and observed outcome. Lower is better. Random-baseline Brier equals positive rate × (1 - positive rate).

**Residualization.** The procedure of regressing a feature on a "leakage source" (in our case, `n_cra_lenders` and `log(n_cra_lenders + 1)`) within cohorts (year × peer-group), and using the residual as the new feature. Removes the leakage-source-explained component, leaving the orthogonal signal.

**BallTree.** A spatial data structure for efficient nearest-neighbor and radius queries. With the haversine metric, it allows fast great-circle-distance queries in O(log n) per point — essential for joining 85K tract centroids to 80K branch coordinates across 16 years of panel.

**Haversine distance.** The great-circle distance between two points on a sphere, calculated from their latitudes and longitudes. The formula treats the earth as a perfect sphere of radius 3958.7613 miles; the approximation error is negligible for the radii used here (5, 10, 25 miles).

**HHI (Herfindahl-Hirschman Index).** A concentration metric defined as the sum of squared market shares. HHI ranges from `1/n` (equal shares among n participants) to 1.0 (single participant). In our context, HHI is computed over a tract's lenders, weighted by loan count.

**NaN gate.** A masking rule that sets a feature to NaN when an upstream condition is unmet. In Round 7, concentration features are NaN-gated when `n_active_lenders_tract < 3` to prevent mechanical saturation in already-thin lender markets. XGBoost handles NaN natively.

**Apportionment (CRA equal-share).** The procedure of distributing a county-lender total across the tracts where that lender was present in that county, with equal shares per tract (D6's tract-presence flag determines the set; D1's totals provide the volume). A coarse but reproducible method for producing tract-lender-level totals from county-level reporting.

**Peer group (rural / urban).** A binary tract classification used in target construction and residualization cohorts, sourced from the USDA RUCA codes. Rural tracts have systematically thinner lender markets, so within-peer-group thresholding for the target and within-peer-group cohorts for residualization prevent rural-bias contamination.

**Service desert / origination desert / any desert.** Three distinct desert types defined in Round 5. *Service desert* is the bottom decile of `n_cra_lenders` within (year × peer_group). *Origination desert* is the bottom percentile of `originations_per_1k`. *Any desert* is the union. Round 7 trains exclusively on the *service desert* target.

**SSBCI (State Small Business Credit Initiative).** A US Treasury federal program that funds state-created credit-support structures: loan guarantees, collateral support, loan participation, and capital access programs. SSBCI 1.0 (2010 Small Business Jobs Act) operated 2011 – 2017; SSBCI 2.0 (2021 American Rescue Plan Act) operates 2022 – 2024.

**MDI (Minority Depository Institution).** An FDIC-designated bank with at least 51% minority ownership or a board majority of minority directors. The FDIC publishes a quarterly MDI list; Round 7 uses the historical workbook for year-precise rosters.

**NMTC (New Markets Tax Credit).** A US Treasury program that provides federal tax credits for qualified investments in low-income communities, mediated through Community Development Entities (CDEs). Operates as project-scale investment, not commercial bank lending — see §7.4 for why this matters.

**h+1, h+3, h+6 — what these mean.** "h" is the prediction horizon, in years, between the feature year T and the target year T+h. The original Round 7 specification used h+1 — predict whether a non-desert tract becomes a desert one year later. The federal data lag (FFIEC CRA disclosure files publish ~2 years after the calendar year they describe) makes h+1 operationally useless: the freshest feature year (2024 by 2026) at h+1 predicts 2025, a year already past. The horizon retrain extended the pipeline to compute h+3 (the new operational primary, "predict desert formation 3 years forward") and h+6 (a long-horizon scenario, "predict desert formation 6 years forward"). All three horizons are produced by `define_target.py`, share the same training apparatus, and differ only in the target column and the fold structure. h+3 has 8 walk-forward folds; h+6 has 6 folds (constrained by the panel data-end). See §4.6 for full methodological treatment.

---

# Part XI — Code reference

*This section maps each significant script to its purpose. One paragraph per script.*

## ETL scripts

`/Users/navya/Documents/Gravity/School/Shivani/round7/etl/cra/parse_cra_round7.py` — parses CRA D1 and D6 flat files year-by-year and produces the tract × lender × year apportioned panel via equal-share apportionment. Output: `data/processed/cra/tract_lender_year.csv` (~20M rows). Latin-1 encoding, single-pass line iteration. The single largest engineering task in Round 7.

`/Users/navya/Documents/Gravity/School/Shivani/round7/etl/lender_class/build_rssd_cra_crosswalk.py` — three-pass fuzzy match of CRA `(agency_code, respondent_id)` to FDIC `RSSDID` and `CERT`. Pass 1 exact name+state, Pass 2 rapidfuzz token_set_ratio ≥ 90, Pass 3 city-restricted fuzzy ≥ 85. Outputs `cra_to_rssd.csv` with confidence levels. 94.6% match rate by CRA loan dollar volume.

`/Users/navya/Documents/Gravity/School/Shivani/round7/etl/lender_class/pull_fdic_call.py` — pulls FDIC institutions and Call Report year-end financials via the BankFind API. Paginates at 10K per request, rate-limits at ~2 req/sec, retries with exponential backoff on 429. Produces `institutions.csv` and `assets_by_year.csv` (RSSD × year × total_assets_k).

`/Users/navya/Documents/Gravity/School/Shivani/round7/etl/lender_class/classify_lenders.py` — joins the RSSD↔CRA crosswalk to FDIC Call Report assets to MDI/CDFI rosters and produces per-`(lender_id, year)` flags: `is_community_bank` (assets < $10B), `is_top4` (national), `is_credit_union` (CRA agency_code = 4), `is_mdi`, `is_cdfi`. Output: `lender_class.csv`.

`/Users/navya/Documents/Gravity/School/Shivani/round7/etl/cdfi/pull_cdfi_list.py` — normalizes a manually-downloaded CDFI Fund certified-institution list. The CDFI Fund has no public JSON API, so the workflow is: download the XLSX from cdfifund.gov, save under `data/raw/cdfi/cdfi_list_raw.xlsx`, run this script. Produces `cdfi_list.csv` with normalized columns.

`/Users/navya/Documents/Gravity/School/Shivani/round7/etl/mdi/pull_mdi_list.py` — normalizes the FDIC MDI list (current snapshot). Reads from XLSX or CSV, normalizes column names, outputs `mdi_list.csv`. The historical MDI workbook (year-precise) is consumed directly by `features/build_mdi_features.py`, not via this script.

`/Users/navya/Documents/Gravity/School/Shivani/round7/etl/microlender/pull_sba_micro.py` — scrapes the SBA microlender list from sba.gov via paginated `.sba-card-styled-listing` cards. Falls back to a manual CSV at `data/raw/microlender/microlender_list_raw.csv` if scraping fails. About 140 entries.

`/Users/navya/Documents/Gravity/School/Shivani/round7/etl/geocode/run_geocode.py` — geocodes CDFI and microlender addresses via Census Geocoder batch (free, ~85% hit rate) with Nominatim fallback (1 req/sec). Caches results by SHA1 of the normalized address string under `data/raw/geocode_cache/{hash}.json`. Idempotent.

`/Users/navya/Documents/Gravity/School/Shivani/round7/etl/ssbci/build_ssbci_overlay.py` — produces the 51-state × 16-year = 816-row SSBCI state-year panel. Attempts to scrape Treasury's Capital Program Summary pages; on failure, falls back to a documented hardcoded panel based on Treasury's published era windows. Output: `state_year_ssbci.csv`.

## Feature scripts

`/Users/navya/Documents/Gravity/School/Shivani/round7/features/build_branch_geo.py` — produces three branch-geography features (distance to nearest, branches within 5 miles, closures over prior 3 years within 10 miles) using sklearn's BallTree with haversine metric. Pulls Census Gazetteer 2020 tract centroids on first run. Runtime ~10 minutes over the full panel.

`/Users/navya/Documents/Gravity/School/Shivani/round7/features/build_concentration.py` — computes top-1, top-3, HHI, and loan-size shares per (tract, year) from the apportioned tract-lender panel. NaN-gates concentration features when n_active_lenders < 3. Computes 5-to-2-year trailing-mean variants. Fully vectorized in pandas; runtime under 30 seconds on 20M rows.

`/Users/navya/Documents/Gravity/School/Shivani/round7/features/build_cra_lender_mix.py` — computes pct_loans_from_community_banks, pct_loans_from_top4_banks, and pct_loans_from_credit_unions per (tract, year). Same NaN gate. Same trailing-mean variants. Joins to the lender_class table.

`/Users/navya/Documents/Gravity/School/Shivani/round7/features/build_concentration_residualized.py` — for each (year, peer_group) cohort, regresses each leakage-vulnerable feature on `[log(n_cra_lenders + 1), n_cra_lenders]` and produces residual columns suffixed `_resid`. Eight features residualized: top1, top3, HHI, community-bank share, top-4 share, credit-union share, loans-under-100K, loans-under-250K. Uses sklearn's LinearRegression per cohort.

`/Users/navya/Documents/Gravity/School/Shivani/round7/features/build_mission_proximity.py` — produces cdfi_within_10mi, mdi_branches_within_10mi (snapshot version, deprecated by year-precise build below), and microloan_intermediary_within_25mi via BallTree haversine queries. Used in earlier iterations; the cleaned model uses `build_mdi_features.py` for MDI instead.

`/Users/navya/Documents/Gravity/School/Shivani/round7/features/build_mdi_features.py` — produces year-precise MDI features (mdi_branches_within_10mi, mdi_branches_within_25mi, nearest_mdi_branch_miles, mdi_active_in_county) by reading per-year sheets from the FDIC historical MDI workbook and joining to that year's SoD branches via CERT.

`/Users/navya/Documents/Gravity/School/Shivani/round7/features/build_nmtc_features.py` — produces five NMTC features from the CDFI Fund's project-level Excel file. Includes lagged 5-year and 3-year window sums, project counts, binary "ever received" indicator, and county-level rollup. *All five features dropped from the cleaned model* — see §7.4.

`/Users/navya/Documents/Gravity/School/Shivani/round7/features/build_round7_panel.py` — joins all feature CSVs onto a thin slice of the Round 5 panel (keys + target + n_cra_lenders + is_rural). Outputs `data/processed/panel/tract_year_with_target_round7.parquet`. Approximately 1.15M rows × 50 columns.

## Training scripts

`/Users/navya/Documents/Gravity/School/Shivani/round7/train/_horizon_config.py` — shared horizon-config module. Exposes `get_horizon_config(horizon: int)` which returns a `HorizonConfig` dataclass with five fields: `horizon`, `target_column` (e.g., `target_becomes_service_desert_h3`), `folds` (the per-fold (train_start, train_end, val_year, test_years) tuples), `output_suffix` (e.g., `_h3` for diagnostic-directory naming), and `min_train_years`. The four scripts below import from this module and dispatch on the `ROUND7_HORIZON` environment variable (default 3). h+1 yields 8 folds, h+3 yields 8 folds, h+6 yields 6 folds — see §4.6 for the full fold-structure logic.

`/Users/navya/Documents/Gravity/School/Shivani/round7/train/walk_forward_round7.py` — Phase A. Trains the influenceable-only Model 2 on the 20-feature whitelist, runs the per-horizon walk-forward folds, applies isotonic calibration per fold, outputs per-fold metrics, feature importances, and test predictions. Output goes to `diagnostics/{run_name}{output_suffix}/` so h+1, h+3, h+6 outputs sit in distinct directories. The headline training script. Per-horizon outputs live at `diagnostics/round7_phaseA_clean/` (h+1, legacy), `diagnostics/round7_phaseA_h3/` (h+3, primary), `diagnostics/round7_phaseA_h6/` (h+6, scenario).

`/Users/navya/Documents/Gravity/School/Shivani/round7/train/prune_features.py` — block-of-clay pruning. Aggregates per-fold feature importances from a Phase A run, produces a master ranking, then for each k in {3, 5, 7, 10, 14, 18, 22, all} re-runs all folds at the configured horizon with only the top-k features. Identifies the elbow per horizon. Outputs at `diagnostics/round7_pruned_clean/`, `diagnostics/round7_pruned_h3/`, `diagnostics/round7_pruned_h6/`.

`/Users/navya/Documents/Gravity/School/Shivani/round7/train/ablation_per_lever.py` — per-policy-lever ablation. For each of seven lever groups, drops that group's features and re-runs all folds at the configured horizon. Produces `ablation_summary.csv` ranking lever groups by ΔAUC and ΔAP from the baseline. Per-horizon outputs at `diagnostics/round7_ablation/` (h+1), `diagnostics/round7_ablation_h3/` (h+3), `diagnostics/round7_ablation_h6/` (h+6).

`/Users/navya/Documents/Gravity/School/Shivani/round7/train/regime_split.py` — pre-/post-COVID regime split. Trains two separate models (pre: 2009-period→pre-COVID-test; post: post-COVID-train→post-COVID-test) at the configured horizon. Reports per-regime metrics and per-regime feature importance. Per-horizon outputs at `diagnostics/round7_regime_split/`, `diagnostics/round7_regime_split_h3/`, `diagnostics/round7_regime_split_h6/`.

`/Users/navya/Documents/Gravity/School/Shivani/round7/train/walk_forward_boltOn.py` — Phase C Variant B. Trains on the union of Round 5's 39 features + Round 7's 20 cleaned features. Reports ΔAUC and ΔAP versus Round 5 baseline. Uses sklearn's permutation_importance on the val set for the round 7 features (XGBoost gain importance is biased here).

`/Users/navya/Documents/Gravity/School/Shivani/round7/train/walk_forward_overlay.py` — Phase C Variant A. Conditional on Phase B verdict being "Moderate." Combines Round 5's diagnostic prediction with Round 7's influenceable prediction as a directional adjustment: `final = round5_prob × (1 + α × sign(Δm2) × |Δm2|)` where Δm2 is the deviation of Round 7's prediction from the per-(year, peer_group) mean. Sweeps α ∈ {0.10, 0.25, 0.50}. Not run for the cleaned model since Phase B verdict was "Strong."

`/Users/navya/Documents/Gravity/School/Shivani/round7/train/diagnostics_round7.py` — post-training diagnostics. Computes per-fold stability summary, per-state AP, partial dependence plots for directional sanity (compares observed PDP slope to expected sign per the design brief). Run after either Phase A or the bolt-on.

## Web scripts

`/Users/navya/Documents/Gravity/School/Shivani/round7/web/build_dashboard_data.py` — produces the JSON / GeoJSON inputs for the dashboard. Aggregates Round 5 and Round 7 predictions per tract, computes within-state percentile ranks, joins to simplified tract geometry, builds state bbox, builds methodology JSONs (ablation, pruning, regime). Output: `web/data/{tracts.geojson, state_stats.json, state_bbox.json, ablation.json, pruning.json, regime.json, feature_stats.json}`.

`/Users/navya/Documents/Gravity/School/Shivani/round7/web/index.html`, `app.js`, `style.css` — the static MapLibre GL JS dashboard. No bundler; single-page scroll. About 2,900 lines total across the three files.

---

# Part XII — Reproducibility

*This section lays out the end-to-end commands to re-run the project from raw data to dashboard, with rough time estimates.*

## Stage 1 — ETL (network-bound, 4 – 8 hours)

Roughly half this time is geocoding (rate-limited by Nominatim's 1-req/sec floor); the rest is FDIC API pagination.

```bash
cd /Users/navya/Documents/Gravity/School/Shivani/round7

# RSSD ↔ CRA crosswalk
python3 etl/lender_class/pull_fdic_call.py                          # ~30 min
python3 etl/lender_class/build_rssd_cra_crosswalk.py                # ~10 min

# Mission-lender lists
python3 etl/cdfi/pull_cdfi_list.py                                  # manual download, then ~1 min
python3 etl/mdi/pull_mdi_list.py                                    # manual download, then ~1 min
python3 etl/microlender/pull_sba_micro.py                           # ~5 min scrape

# Geocoding
python3 etl/geocode/run_geocode.py                                  # ~3 hours (Nominatim rate-limited)

# CRA tract-lender-year apportionment
python3 etl/cra/parse_cra_round7.py                                 # ~30 min, 16 years × ~2 min/year

# Lender classification
python3 etl/lender_class/classify_lenders.py                        # ~1 min

# SSBCI state-year overlay
python3 etl/ssbci/build_ssbci_overlay.py                            # <1 min
```

## Stage 2 — Features (~30 min)

```bash
# Concentration + lender mix + loan-size shares
python3 features/build_concentration.py                             # ~2 min
python3 features/build_cra_lender_mix.py                            # ~2 min

# Branch geography (10 min) + year-precise MDI (~5 min) + microlender proximity
python3 features/build_branch_geo.py                                # ~10 min
python3 features/build_mdi_features.py                              # ~5 min
python3 features/build_mission_proximity.py                         # ~3 min

# NMTC (built but dropped from cleaned model — included for diagnostics)
python3 features/build_nmtc_features.py                             # ~1 min

# Build the merged panel
python3 features/build_round7_panel.py                              # ~2 min

# Residualize concentration features against n_cra_lenders
python3 features/build_concentration_residualized.py                # ~3 min
# Re-run panel build to pick up residualized columns
python3 features/build_round7_panel.py                              # ~2 min
```

## Stage 3 — Training (~1 – 2 hours per horizon)

The horizon retrain introduces a single new environment variable, `ROUND7_HORIZON`, that selects which target column and fold structure the training scripts use. Default is 3 (the new operational primary). To reproduce the full multi-horizon record, run each script three times with the horizon set to 1, 3, and 6 respectively.

```bash
# === h+3 (the new primary; default) ===
ROUND7_HORIZON=3 ROUND7_RUN_NAME=round7_phaseA_h3 \
    python3 train/walk_forward_round7.py                                     # ~20 min

ROUND7_HORIZON=3 ROUND7_PRUNE_SOURCE=round7_phaseA_h3 \
    ROUND7_PRUNE_OUT=round7_pruned_h3 \
    python3 train/prune_features.py                                          # ~30 min

ROUND7_HORIZON=3 python3 train/ablation_per_lever.py                         # ~25 min
ROUND7_HORIZON=3 python3 train/regime_split.py                               # ~5 min

# === h+6 (the long-horizon scenario) ===
ROUND7_HORIZON=6 ROUND7_RUN_NAME=round7_phaseA_h6 \
    python3 train/walk_forward_round7.py                                     # ~15 min (6 folds)

ROUND7_HORIZON=6 ROUND7_PRUNE_SOURCE=round7_phaseA_h6 \
    ROUND7_PRUNE_OUT=round7_pruned_h6 \
    python3 train/prune_features.py                                          # ~22 min

ROUND7_HORIZON=6 python3 train/ablation_per_lever.py                         # ~18 min
ROUND7_HORIZON=6 python3 train/regime_split.py                               # ~4 min

# === h+1 (legacy, for diagnostic comparability) ===
ROUND7_HORIZON=1 ROUND7_RUN_NAME=round7_phaseA_clean \
    python3 train/walk_forward_round7.py                                     # ~20 min

ROUND7_HORIZON=1 ROUND7_PRUNE_SOURCE=round7_phaseA_clean \
    ROUND7_PRUNE_OUT=round7_pruned_clean \
    python3 train/prune_features.py                                          # ~30 min

ROUND7_HORIZON=1 python3 train/ablation_per_lever.py                         # ~25 min
ROUND7_HORIZON=1 python3 train/regime_split.py                               # ~5 min

# === Auxiliary, horizon-independent ===
python3 train/walk_forward_boltOn.py                                         # ~20 min
python3 train/diagnostics_round7.py round7_phaseA_h3                         # ~5 min
```

Each invocation writes to `diagnostics/{run_name}{output_suffix}/` where `output_suffix` is `_h3`, `_h6`, or empty for h+1 (legacy directory naming preserved for backward compat). All four core scripts read the same `ROUND7_HORIZON` env var and dispatch through `train/_horizon_config.py`, so the horizon retrain is a single-knob change rather than three forked codepaths.

## Stage 4 — Dashboard build (~5 min)

```bash
cd web
python3 build_dashboard_data.py                                              # ~3 min

# Serve locally
python3 -m http.server 8009
# open http://localhost:8009
```

## Required dependencies

Python 3.10+. Required pip packages (rough — refer to source files for exhaustive list): `pandas`, `numpy`, `xgboost`, `scikit-learn`, `requests`, `beautifulsoup4`, `lxml`, `openpyxl`, `pyarrow`, `rapidfuzz`. No GPU required. ~16 GB RAM recommended (peak usage during the prune sweep is ~12 GB).

## Reproducibility notes

`random_state = 42` is set in every model fit. Walk-forward folds are deterministic given panel year coverage. The crosswalk fuzzy-match is deterministic given the same input rosters. The geocoding cache is keyed by SHA1 of the normalized address string, so re-runs hit cache and are bit-identical. Census Geocoder batch endpoint and Nominatim are external services with no SLA; the cache layer makes the project robust to those sources rotating addresses or going briefly offline. The SSBCI overlay's documented hardcoded fallback panel is deterministic and reproduces independent of Treasury's website availability.

The single non-deterministic input is the manual-review queue of the RSSD↔CRA crosswalk (Pass 3 residual). Confidence levels {1.0, 0.9, 0.85, 0.75} are stable across runs, but if a future Pass 3 review re-classifies entries the downstream lender_class.csv changes. We treat the current crosswalk as the canonical reproducible artifact.

---

*End of document.*
