/* =====================================================================
   ROUND 7 · Two-Layer Credit-Desert Risk
   v3 dashboard — model × horizon, dark, opinionated, tool-first.
   ===================================================================== */

(() => {
  "use strict";

  // ---------------------------------------------------------------------
  // CONFIG
  // ---------------------------------------------------------------------
  const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Lever feature → display label + ablation group key
  const LEVERS = [
    {
      key: "distance_to_nearest_bank_branch",
      label: "Bank branch distance",
      unit: "mi",
      group: "branch_access",
      polarity: -1,         // farther → MORE risk (we model -polarity*z*w)
      hint: "Median miles to nearest branch.",
    },
    {
      key: "branches_within_5mi",
      label: "Branches within 5 mi",
      unit: "branches",
      group: "branch_access",
      polarity: +1,
      hint: "More branches → less risk.",
    },
    {
      key: "mdi_branches_within_25mi",
      label: "MDI branch reach",
      unit: "MDI within 25 mi",
      group: "mdi_mission_lender",
      polarity: +1,
      hint: "Minority Depository Institution presence.",
    },
    {
      key: "ssbci_active",
      label: "SSBCI program coverage",
      unit: "share active",
      group: "ssbci_state_policy",
      polarity: +1,
      hint: "State Small Business Credit Initiative.",
    },
    {
      key: "microloan_intermediary_within_25mi",
      label: "Microlender ecosystem",
      unit: "intermediaries",
      group: "microlender_ecosystem",
      polarity: +1,
      hint: "SBA microloan intermediaries within 25 mi.",
    },
    {
      key: "lender_hhi_tract_resid",
      label: "Lender concentration (resid.)",
      unit: "HHI deviation",
      group: "residualized_concentration",
      polarity: -1,
      hint: "Residualized HHI; the lever that actually moves average precision.",
    },
  ];

  const HZ_LABEL = {
    h3: "2027 forecast",
    h6: "2030 scenario",
  };
  const HZ_YEAR = { h3: "2027", h6: "2030" };
  const HZ_META = {
    h3: "2027 forecast · trained on data through 2021 · target 2024",
    h6: "2030 scenario · trained on data through 2018 · target 2024",
  };

  const GEO_META = {
    county: {
      label: "County",
      plural: "counties",
      detail: "County detail",
      intro: "Population-weighted tract rollup for county-level credit-desert risk.",
      forecastLabel: "Forecasts for this county",
      scenarioTitle: "Counties that crossed the high-risk line",
      histLabel: "Counties per risk decile",
      focusTopLabel: "Top 5 counties in state",
    },
    tract: {
      label: "Tract",
      plural: "tracts",
      detail: "Tract detail",
      intro: "Neighborhood-level credit-desert risk for this census tract.",
      forecastLabel: "Forecasts for this neighborhood",
      scenarioTitle: "Tracts that crossed the high-risk line",
      histLabel: "Tracts per risk decile",
      focusTopLabel: "Top 5 tracts in state",
    },
  };

  // Map data state
  const STATE = {
    geoMode: "county",            // "county" or "tract"
    activeModel: "m1",
    activeHorizon: "h3",          // "h3" or "h6"
    methHorizon: "h3",            // independent horizon for the methodology viz panels
    methHorizonLocked: false,     // true after first user interaction with the meth switcher
    methModel: "diagnostic",      // independent model for methodology cards 02 + 02b
    focusedState: null,           // state abbreviation, or null
    sliderShifts: {},             // key → z-score shift
    feat: null,                   // feature_stats.json (flat: { key: {...} })
    featureDictionary: null,      // feature_dictionary.json
    states: null,                 // state_stats.json
    countyStats: null,            // county_stats.json
    countyStatsLoading: false,
    countyStatsTried: false,
    bbox: null,                   // state_bbox.json
    abl: { h3: null, h6: null },  // ablation_h{3,6}.json
    pruning: { h3: null, h6: null },
    regime: { h3: null, h6: null },
    rafId: null,
    tractLayersReady: false,
    tractSourceReady: false,
    switching: false,
    pendingGeoMode: null,
    geoSwitchToken: 0,
    pinnedFeature: null,          // active geography properties object (or null)
    shap: null,                   // shap_top.json (lazily loaded)
    shapLoading: false,
    shapTried: false,
    // Scenario-linearized override values for the pinned feature's drawer.
    // Populated by applyScenarioToDrawer() whenever a slider is non-baseline.
    // Cleared (set null) when all sliders are at 0. When non-null, renderDrawer
    // and renderDrawerShap read from these instead of the raw feature properties.
    scenarioAdjustedRisks: null,  // { m1_h3, m1_h6, m2_h3, m2_h6 }
    scenarioAdjustedShap: null,   // { m1_h3: [[f,logit_value],...], m1_h6:..., m2_h3:..., m2_h6:... }
    scenarioActiveLevers: null,   // [{label, z}, ...] for the plain-language note
  };

  // SHAP feature label map — humanizes column names for the drawer.
  const FEATURE_LABEL = {
    distance_to_nearest_bank_branch: "Distance to nearest bank branch (mi)",
    branches_within_5mi: "Bank branches within 5mi",
    branch_closures_3y_within_10mi: "Branch closures, 3y within 10mi",
    mdi_branches_within_10mi: "MDI branches within 10mi",
    mdi_branches_within_25mi: "MDI branches within 25mi",
    nearest_mdi_branch_miles: "Nearest MDI branch (mi)",
    mdi_active_in_county: "MDI active in county",
    microloan_intermediary_within_25mi: "Microlender intermediaries within 25mi",
    ssbci_active: "SSBCI program active",
    ssbci_2_0_active: "SSBCI 2.0 active",
    ssbci_program_count: "SSBCI program count",
    ssbci_n_capital_programs: "SSBCI capital programs",
    pct_loans_from_community_banks_resid: "% loans from community banks (residualized)",
    pct_loans_from_top4_banks_resid: "% loans from top-4 banks (residualized)",
    pct_loans_from_credit_unions_resid: "% loans from credit unions (residualized)",
    pct_loans_under_100k_resid: "% loans under $100k (residualized)",
    pct_loans_under_250k_resid: "% loans under $250k (residualized)",
    top1_lender_share_tract_resid: "Top-1 lender share (residualized)",
    top3_lender_share_tract_resid: "Top-3 lender share (residualized)",
    lender_hhi_tract_resid: "Lender HHI (residualized)",
    pct_poverty: "Poverty rate",
    pct_minority: "Pct minority",
    pct_black: "Pct Black",
    pct_hispanic: "Pct Hispanic",
    median_hh_income: "Median household income",
    median_household_income: "Median household income",
    is_persistent_poverty: "In a persistent-poverty county",
    is_rural: "Rural area (USDA classification)",
    ruca_code: "Urban-to-rural classification (USDA RUCA)",
    unemployment_rate: "Unemployment rate",
    pct_bachelor_plus: "Pct bachelor's+",
    pct_vacant: "Pct vacant housing",
    fdic_deposit_hhi: "FDIC deposit HHI",
    fdic_top_bank_share: "FDIC top bank share",
    avg_loan_size_resid: "Avg loan size (residualized)",
    n_lenders_tract_resid: "Lender count (residualized)",
    pct_minority_resid: "% minority (residualized)",
    population: "Population",
    housing_units: "Housing units",
    cra_county_amount_hhi: "County CRA loan-amount HHI",
    cra_county_count_hhi: "County CRA loan-count HHI",
    cra_county_top_lender_share_amount: "County top CRA lender share (amt)",
    cra_county_top_lender_share_count: "County top CRA lender share (count)",
    fdic_deposit_hhi_chg3yr: "FDIC deposit HHI · 3y change",
    has_hmda: "Year ≥ 2018 (HMDA available)",  // structural artifact — filtered server-side from SHAP top-N
    mean_loan_amount: "Mean loan amount",
    sum_loan_amount: "Sum loan amount",
    n_originated: "Originated loans",
    n_denied: "Denied loans",
    n_black: "Black population (count)",
  };

  // Direction convention for the percentile-driven row coloring on the drivers
  // panel. Hand-curated, NOT auto-detected — see
  // docs/superpowers/specs/2026-05-08-driver-percentile-design.md for the rationale.
  //
  //   "lower_is_worse"  (default) → below-median = red (worse), above-median = green (better)
  //   "higher_is_worse"            → above-median = red (worse), below-median = green (better)
  //   "neutral"                    → grey arrow, no green/red coloring
  //
  // Adding a feature: only flip from the default if there is a clear domain
  // reason (concentration, distress measure, distance penalty, etc.).
  // Race / ethnicity composition is intentionally "neutral" to avoid
  // value-judgement coloring of demographic mix.
  const FEATURE_DIRECTION = {
    // Concentration / HHI — higher = more concentrated lending = worse for borrowers
    cra_county_amount_hhi:               "higher_is_worse",
    cra_county_count_hhi:                "higher_is_worse",
    lender_hhi_tract_resid:              "higher_is_worse",
    fdic_deposit_hhi:                    "higher_is_worse",
    fdic_deposit_hhi_chg1yr:             "higher_is_worse",
    fdic_deposit_hhi_chg3yr:             "higher_is_worse",
    // Top-lender shares — higher = single-lender dominance = worse
    top1_lender_share_tract_resid:       "higher_is_worse",
    top3_lender_share_tract_resid:       "higher_is_worse",
    pct_loans_from_top4_banks_resid:     "higher_is_worse",
    cra_county_top_lender_share_count:   "higher_is_worse",
    cra_county_top_lender_share_amount:  "higher_is_worse",
    fdic_top_bank_share:                 "higher_is_worse",
    fdic_top_bank_share_chg1yr:          "higher_is_worse",
    fdic_top_bank_share_chg3yr:          "higher_is_worse",
    // Access penalties — higher distance = harder to reach a branch = worse
    distance_to_nearest_bank_branch:     "higher_is_worse",
    nearest_mdi_branch_miles:            "higher_is_worse",
    branch_closures_3y_within_10mi:      "higher_is_worse",
    // Distress measures — higher = more distress = worse
    unemployment_rate:                   "higher_is_worse",
    pct_vacant:                          "higher_is_worse",
    pct_poverty:                         "higher_is_worse",
    is_persistent_poverty:               "higher_is_worse",
    denial_rate:                         "higher_is_worse",
    n_denied:                            "higher_is_worse",
    n_withdrawn:                         "higher_is_worse",
    // Rurality — USDA RUCA 1-urban → 10-rural; this model penalises rural
    ruca_code:                           "higher_is_worse",

    // Demographic composition — coloring these green/red would imply a
    // value judgement on demographic mix; render arrow grey instead.
    pct_minority:                        "neutral",
    pct_black:                           "neutral",
    pct_hispanic:                        "neutral",
    n_black:                             "neutral",
    n_hispanic:                          "neutral",
    n_asian:                             "neutral",
    n_white:                             "neutral",
    n_other_race:                        "neutral",
    // Loan-size mix has ambiguous direction in this model — leave neutral
    mean_loan_amount:                    "neutral",
  };
  // Default for everything else: "lower_is_worse" (population, income, branches,
  // SSBCI presence, MDI presence, originations, education, etc.).

  // Plain-English explainer for every feature that may show up in SHAP top-N.
  // Each entry: {what: definition, read: how to interpret}.
  const FEATURE_DESCRIPTION = {
    // ─── Influenceable lens — branch geography ────────────────────────────
    distance_to_nearest_bank_branch: {
      what: "Straight-line distance from the tract centroid to the closest FDIC-insured bank branch, in miles.",
      read: "Higher means less physical access to a bank. The single most important feature in the influenceable model.",
    },
    branches_within_5mi: {
      what: "Count of FDIC bank branches within 5 miles of the tract centroid.",
      read: "Higher means more local options. Drops with branch closures.",
    },
    branch_closures_3y_within_10mi: {
      what: "Count of bank branches within 10 miles that disappeared in the prior 3 years.",
      read: "Higher means access is eroding; a leading indicator of credit-desert formation.",
    },
    // ─── Influenceable lens — MDI / mission lender ────────────────────────
    mdi_branches_within_10mi: {
      what: "Count of Minority Depository Institution (MDI) branches within 10 miles. MDIs are FDIC-insured banks majority-owned by minority groups or with majority-minority boards.",
      read: "Higher means stronger mission-lender presence. MDIs disproportionately serve underserved markets.",
    },
    mdi_branches_within_25mi: {
      what: "Count of MDI branches within 25 miles. Wider radius, useful in rural areas where 10mi misses presence.",
      read: "Higher = stronger mission-lender ecosystem at regional scale.",
    },
    nearest_mdi_branch_miles: {
      what: "Distance to the nearest MDI branch, in miles.",
      read: "Higher means farther from mission-lending capacity.",
    },
    mdi_active_in_county: {
      what: "1 if any MDI is headquartered in the tract's county; 0 otherwise.",
      read: "1 means there's a mission-lender presence at the county scale.",
    },
    // ─── Influenceable lens — microlender / SBA ───────────────────────────
    microloan_intermediary_within_25mi: {
      what: "Count of SBA-designated microlender intermediaries within 25 miles. These are non-bank organizations that disburse small SBA-backed loans.",
      read: "Higher means stronger small-loan ecosystem for tiny businesses.",
    },
    // ─── Influenceable lens — SSBCI state policy ──────────────────────────
    ssbci_active: {
      what: "1 if the State Small Business Credit Initiative (SSBCI) had an active program in this state-year; 0 otherwise. SSBCI 1.0 ran 2011–2017; SSBCI 2.0 runs 2022–present.",
      read: "A 1 in the data means the federal-state program supporting small-business lenders was active.",
    },
    ssbci_2_0_active: {
      what: "1 specifically for SSBCI 2.0 (2022+). Distinct from SSBCI 1.0 because the program design shifted toward equity investments.",
      read: "1 means the modern, post-COVID iteration of SSBCI is operating.",
    },
    ssbci_program_count: {
      what: "Count of distinct SSBCI program TYPES active in this state-year (loan guarantee, collateral support, loan participation, capital access, venture).",
      read: "Higher means more diverse state-backed credit-support tools in use.",
    },
    ssbci_n_capital_programs: {
      what: "Subset of program_count restricted to capital-deployment programs (loan guarantee, collateral support, loan participation, capital access). Excludes venture.",
      read: "Higher = more state-backed loan support specifically.",
    },
    // ─── Influenceable lens — residualized concentration / lender mix ─────
    pct_loans_from_community_banks_resid: {
      what: "Share of CRA small-business loans that came from community banks (assets < $10B), residualized against the tract's lender count to remove mechanical leakage.",
      read: "Higher (positive residual) means above-expected community-bank presence given the tract's lender count. A sign of healthy relationship lending.",
    },
    pct_loans_from_top4_banks_resid: {
      what: "Share of CRA loans from the four largest national banks, residualized against lender count.",
      read: "Higher = above-expected top-4 dominance, often a sign of thin local lender depth.",
    },
    pct_loans_from_credit_unions_resid: {
      what: "Share of CRA loans from credit unions, residualized.",
      read: "Higher = above-expected cooperative-lender presence.",
    },
    pct_loans_under_100k_resid: {
      what: "Share of CRA small-business loans below $100K, residualized.",
      read: "Higher = above-expected small-loan supply (loans actually serving very small firms).",
    },
    pct_loans_under_250k_resid: {
      what: "Share of CRA small-business loans below $250K, residualized.",
      read: "Higher = above-expected small/mid-sized loan supply.",
    },
    top1_lender_share_tract_resid: {
      what: "Share of CRA loans held by the single largest lender in the tract, residualized.",
      read: "Higher = above-expected concentration / fragility (one lender dominates).",
    },
    top3_lender_share_tract_resid: {
      what: "Share of CRA loans held by the top-3 lenders combined, residualized.",
      read: "Higher = above-expected concentration in a few hands.",
    },
    lender_hhi_tract_resid: {
      what: "Herfindahl-Hirschman Index of CRA lenders in the tract (sum of squared market shares), residualized. HHI ranges 0 (perfect competition) to 1 (monopoly).",
      read: "Higher = above-expected market concentration. Concentrated markets are more fragile.",
    },
    // ─── Diagnostic lens — ACS demographics ───────────────────────────────
    population: {
      what: "Total population in the tract (ACS 5-year estimate).",
      read: "Smaller populations correlate with thinner credit markets; fewer borrowers means fewer lenders.",
    },
    housing_units: {
      what: "Total housing units in the tract.",
      read: "Smaller = thinner local economy. Strongly correlated with population.",
    },
    pct_vacant: {
      what: "Share of housing units vacant.",
      read: "Higher = distressed neighborhood, weaker housing demand.",
    },
    median_hh_income: {
      what: "Median household income in the tract (ACS 5-year, dollars).",
      read: "Lower = lower-income tract, structurally more likely to face credit access issues.",
    },
    pct_poverty: {
      what: "Share of population below the federal poverty line.",
      read: "Higher = more poverty, structurally higher desert risk.",
    },
    unemployment_rate: {
      what: "Share of labor force unemployed (ACS).",
      read: "Higher = weaker labor market, downstream credit demand suffers.",
    },
    pct_black: {
      what: "Share of population identifying as Black or African-American (ACS).",
      read: "Higher correlates with desert risk because of historical redlining and persistent inequities. NOT a causal demographic feature.",
    },
    pct_hispanic: {
      what: "Share of population identifying as Hispanic or Latino.",
      read: "Higher correlates with desert risk due to historical lending patterns. Not a causal feature.",
    },
    pct_minority: {
      what: "Share of population identifying as a racial or ethnic minority (non-Hispanic White is the reference).",
      read: "Higher correlates with desert risk due to historical disinvestment; diagnostic only, not actionable.",
    },
    pct_bachelor_plus: {
      what: "Share of adults with a bachelor's degree or higher.",
      read: "Lower = lower educational attainment, often correlated with weaker labor markets.",
    },
    is_persistent_poverty: {
      what: "1 if the tract's county is a USDA-designated persistent-poverty county (≥20% poverty for 30+ years). 0 otherwise.",
      read: "1 means structurally entrenched poverty (federal designation, not arbitrary).",
    },
    is_rural: {
      what: "1 if the tract is rural by USDA RUCA classification (codes 7-10). 0 otherwise.",
      read: "1 means rural. Used to peer-stratify the desert target so rural and urban tracts are compared fairly.",
    },
    ruca_code: {
      what: "USDA Rural-Urban Commuting Area code (1-10): 1-3 metropolitan, 4-6 micropolitan, 7-9 small town, 10 isolated rural.",
      read: "Higher = more rural. The model uses this as a finer-grained urban-to-rural spectrum.",
    },
    // ─── Diagnostic lens — FDIC concentration ─────────────────────────────
    fdic_deposit_hhi: {
      what: "Herfindahl-Hirschman Index of bank deposits at the COUNTY level (FDIC Summary of Deposits).",
      read: "Higher = more concentrated deposit market. Often correlates with concentrated lending.",
    },
    fdic_top_bank_share: {
      what: "Largest single bank's share of county deposits.",
      read: "Higher = one bank dominates the county. Fragile if that bank pulls back.",
    },
    fdic_deposit_hhi_chg1yr: {
      what: "Year-over-year change in fdic_deposit_hhi.",
      read: "Positive = concentration growing in the past year (consolidation).",
    },
    fdic_deposit_hhi_chg3yr: {
      what: "3-year change in fdic_deposit_hhi.",
      read: "Positive = sustained consolidation trend.",
    },
    fdic_top_bank_share_chg1yr: {
      what: "Year-over-year change in the top bank's deposit share.",
      read: "Positive = top bank gaining share, others losing.",
    },
    fdic_top_bank_share_chg3yr: {
      what: "3-year change in the top bank's share.",
      read: "Positive = sustained dominance growth.",
    },
    // ─── Diagnostic lens — CRA churn / county concentration ───────────────
    cra_lender_entries_1yr: {
      what: "Count of new CRA lenders that started reporting in this tract in the past year.",
      read: "Higher = new lenders entering the market. Healthy.",
    },
    cra_lender_exits_1yr: {
      what: "Count of CRA lenders that stopped reporting in this tract in the past year.",
      read: "Higher = lender flight. Worrying.",
    },
    cra_lender_churn_1yr: {
      what: "Sum of entries and exits; total turnover in tract lenders.",
      read: "Higher = unstable lender base.",
    },
    cra_lender_presence_ratio_1yr: {
      what: "Share of last year's lenders that are still present this year.",
      read: "Lower = many lenders left.",
    },
    cra_lender_entries_3yr: { what: "3-year version of entries.", read: "Higher = sustained inflow." },
    cra_lender_exits_3yr: { what: "3-year version of exits.", read: "Higher = sustained outflow." },
    cra_lender_churn_3yr: { what: "3-year total churn.", read: "Higher = sustained instability." },
    cra_county_amount_hhi: {
      what: "HHI of CRA loan dollar amounts at the COUNTY level.",
      read: "Higher = a few lenders deploy most of the small-business credit dollars.",
    },
    cra_county_count_hhi: {
      what: "HHI of CRA loan COUNTS at the county level.",
      read: "Higher = fewer lenders make most of the loans.",
    },
    cra_county_top_lender_share_count: {
      what: "County-level: largest lender's share of CRA small-business loans by count.",
      read: "Higher = one lender originates most of the loans.",
    },
    cra_county_top_lender_share_amount: {
      what: "County-level: largest lender's share of CRA loans by dollar amount.",
      read: "Higher = one lender deploys most of the dollars.",
    },
    // ─── Diagnostic lens — HMDA mortgage features ─────────────────────────
    n_applications: { what: "HMDA mortgage applications in the tract-year.", read: "Higher = more borrowing activity. (Mortgage, not small-business.)" },
    n_originated: { what: "HMDA mortgage originations.", read: "Higher = more loans actually approved." },
    n_denied: { what: "HMDA mortgage denials.", read: "Higher = more rejected applicants." },
    n_distinct_lenders: { what: "Distinct HMDA-reporting lenders active in tract.", read: "Higher = more competition for mortgage borrowers." },
    approval_rate: { what: "Share of HMDA applications approved.", read: "Higher = easier credit environment." },
    denial_rate: { what: "Share of HMDA applications denied.", read: "Higher = tighter credit environment." },
    mean_loan_amount: { what: "Average HMDA mortgage loan amount, dollars.", read: "Higher loan sizes = higher-cost or higher-income market." },
    sum_loan_amount: { what: "Sum of HMDA originated loan amounts, dollars.", read: "Higher = more total mortgage capital deployed." },
    n_white: { what: "HMDA applicants identifying as white (count).", read: "Compositional indicator." },
    n_black: { what: "HMDA applicants identifying as Black.", read: "Compositional indicator." },
    n_hispanic: { what: "HMDA applicants identifying as Hispanic.", read: "Compositional indicator." },
    n_asian: { what: "HMDA applicants identifying as Asian.", read: "Compositional indicator." },
    n_other_race: { what: "HMDA applicants of other or unreported race.", read: "Compositional." },
    has_hmda: {
      what: "1 if HMDA data is available for this year (post-2018 in our pipeline). 0 otherwise.",
      read: "Structural artifact; proxy for 'is this a 2018+ observation.' Filtered from policy-audience views.",
    },
  };

  // Plain-language tooltips for the scenario sliders (right rail).
  // Keyed by the actual data-key on each slider (matches LEVERS[].key).
  // Each entry: name, what it represents, and what moving it does.
  const LEVER_TOOLTIP_CONTENT = {
    distance_to_nearest_bank_branch: {
      nm: "Bank branch distance",
      what: "How far the typical neighborhood resident has to travel to a bank branch.",
      does: "Pulling the slider makes branches closer or farther in the model's view. Reflects branch-retention or new-branch policies.",
      note: "Distance receives most of the branch-access scenario weight because it is the strongest branch-access feature.",
    },
    branches_within_5mi: {
      nm: "Branches within 5 miles",
      what: "The count of bank branches within five miles of the neighborhood.",
      does: "Pulling the slider raises or lowers the local-options count. Maps to branch additions or closures.",
      note: "This shares the branch-access group weight with distance, but gets a smaller share because its feature importance is lower.",
    },
    mdi_branches_within_25mi: {
      nm: "MDI branch reach",
      what: "How accessible Minority Depository Institution branches are. MDIs are mission-driven banks serving underserved markets.",
      does: "Pulling the slider models a stronger or weaker MDI presence in the area.",
      note: "The effect comes from how much the model depends on the MDI / mission-lender category, then this feature's share of that category.",
    },
    ssbci_active: {
      nm: "SSBCI program coverage",
      what: "Whether the state has the federal-state Small Business Credit Initiative active and how many program types are running.",
      does: "Slider toggles or expands the state-program presence.",
      note: "This is a broad state-policy signal, so the scenario effect is contextual and should be read cautiously.",
    },
    microloan_intermediary_within_25mi: {
      nm: "Microlender ecosystem",
      what: "How dense the local SBA-microlender network is. Microlenders are non-bank organizations that disburse small SBA-backed loans.",
      does: "Slider models stronger or weaker microlender presence in a 25-mile radius.",
      note: "The effect comes from how much the model depends on the microlender-ecosystem category and is strongest at the 2027 horizon.",
    },
    lender_hhi_tract_resid: {
      nm: "Lender concentration",
      what: "How concentrated small-business lending is after accounting for peer-group and year context.",
      does: "Pulling the slider models a more or less concentrated lender market. More concentration generally raises risk.",
      note: "This is the strongest sensitivity group, but it is less directly policy-actionable than branch, MDI, or microlender access.",
    },
  };



  // ---------------------------------------------------------------------
  // THEME HELPERS
  // ---------------------------------------------------------------------
  const isDarkTheme = () => document.documentElement.dataset.theme !== "light";
  const nullFillColor = () => isDarkTheme() ? "#0c1318" : "#f2f1ee";
  const coralColor = () => isDarkTheme() ? "#fc5855" : "#cc3d3a";
  const edgeColor = () => isDarkTheme() ? "#0a1319" : "#c2cad4";
  const bgColor = () => isDarkTheme() ? "#040c13" : "#f7f5f0";

  // Choropleth ramps — paper→deep-accent for light, dark→bright-accent for dark.
  const RAMPS_DARK = {
    m1: [
      [0.00, "#0e171e"],
      [0.02, "#332e12"],
      [0.05, "#655406"],
      [0.10, "#987500"],
      [0.20, "#c89600"],
      [0.40, "#eeb300"],
      [1.00, "#ffd046"],
    ],
    m2: [
      [0.00, "#0e171e"],
      [0.02, "#193b22"],
      [0.05, "#336627"],
      [0.10, "#56932b"],
      [0.20, "#78bb2f"],
      [0.40, "#a4e550"],
      [1.00, "#c3ff68"],
    ],
  };
  const RAMPS_LIGHT = {
    m1: [
      [0.00, "#f7f5f0"],
      [0.02, "#f0e8c9"],
      [0.05, "#e8d480"],
      [0.10, "#d6b333"],
      [0.20, "#a87f00"],
      [0.40, "#7a5800"],
      [1.00, "#523900"],
    ],
    m2: [
      [0.00, "#f7f5f0"],
      [0.02, "#dde8c4"],
      [0.05, "#bcd385"],
      [0.10, "#92b245"],
      [0.20, "#6c8a1d"],
      [0.40, "#4a6210"],
      [1.00, "#2e3e08"],
    ],
  };
  const ramps = () => isDarkTheme() ? RAMPS_DARK : RAMPS_LIGHT;

  // ---------------------------------------------------------------------
  // BASE MAP STYLE — dual basemap sources for dark/light switching
  // ---------------------------------------------------------------------
  const BASE_STYLE = {
    version: 8,
    glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
    sources: {
      "carto-dark": {
        type: "raster",
        tiles: [
          "https://a.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}.png",
          "https://b.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}.png",
          "https://c.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}.png",
          "https://d.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}.png",
        ],
        tileSize: 256,
        attribution: "© OpenStreetMap contributors © CARTO",
      },
      "carto-light": {
        type: "raster",
        tiles: [
          "https://a.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png",
          "https://b.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png",
          "https://c.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png",
          "https://d.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png",
        ],
        tileSize: 256,
        attribution: "© OpenStreetMap contributors © CARTO",
      },
    },
    layers: [
      { id: "bg", type: "background", paint: { "background-color": bgColor() } },
      {
        id: "base-dark", type: "raster", source: "carto-dark",
        layout: { visibility: isDarkTheme() ? "visible" : "none" },
        paint: { "raster-opacity": 0.55, "raster-saturation": -0.4, "raster-contrast": -0.05, "raster-brightness-min": 0.02 }
      },
      {
        id: "base-light", type: "raster", source: "carto-light",
        layout: { visibility: isDarkTheme() ? "none" : "visible" },
        paint: { "raster-opacity": 0.50, "raster-saturation": -0.20, "raster-contrast": 0.05 }
      },
    ],
  };

  // Risk color ramps — single-hue, dark→accent, sequential.
  const RAMPS = {
    m1: [
      [0.00, "#0e171e"],
      [0.02, "#332e12"],
      [0.05, "#655406"],
      [0.10, "#987500"],
      [0.20, "#c89600"],
      [0.40, "#eeb300"],
      [1.00, "#ffd046"],
    ],
    m2: [
      [0.00, "#0e171e"],
      [0.02, "#193b22"],
      [0.05, "#336627"],
      [0.10, "#56932b"],
      [0.20, "#78bb2f"],
      [0.40, "#a4e550"],
      [1.00, "#c3ff68"],
    ],
  };

  // active risk property name in the geojson, e.g., "m1_h3"
  const riskProp = () => `${STATE.activeModel}_${STATE.activeHorizon}`;
  const rankProp = () => `${STATE.activeModel}r_${STATE.activeHorizon}`;
  const isCountyMode = () => STATE.geoMode === "county";
  const activeGeoMeta = () => GEO_META[STATE.geoMode];
  const activeFillLayerId = () => isCountyMode() ? "counties-fill" : "tracts-fill";
  const activeHoverLayerId = () => isCountyMode() ? "counties-outline-hover" : "tracts-outline-hover";
  const activePinnedLayerId = () => isCountyMode() ? "counties-outline-pinned" : "tracts-outline-pinned";
  const geoMeanKey = (m, h) => isCountyMode() ? `county_mean_${m}_${h}` : `mean_${m}_${h}`;
  const activeStateTopList = (stateRow, key) => isCountyMode()
    ? ((stateRow.top_counties && stateRow.top_counties[key]) || [])
    : ((stateRow.top && stateRow.top[key]) || []);

  function setText(id, t) {
    const el = document.getElementById(id);
    if (el) el.textContent = t;
  }

  function activeFeatureCount() {
    const n = STATE.states && STATE.states.feature_counts
      ? STATE.states.feature_counts[STATE.geoMode]
      : null;
    return n != null ? n : (isCountyMode() ? 0 : 77036);
  }

  function activeHistogramStore() {
    if (!STATE.states) return null;
    if (STATE.states.national_histogram_by_geo) {
      return STATE.states.national_histogram_by_geo[STATE.geoMode] || null;
    }
    return isCountyMode() ? null : (STATE.states.national_histogram || null);
  }

  function renderGeoCopy() {
    const meta = activeGeoMeta();
    document.body.dataset.geo = STATE.geoMode;
    const count = activeFeatureCount();
    setText("titleGeoCount", count ? count.toLocaleString() : "–");
    setText("metaGeoCount", count ? count.toLocaleString() : "–");
    setText("titleGeoLabel", meta.plural);
    setText("metaGeoLabel", meta.plural);
    setText("focusTopLabel", meta.focusTopLabel);
    setText("scenarioTitle", meta.scenarioTitle);
    setText("drawerKicker", meta.detail);
    setText("drawerForecastLabel", meta.forecastLabel);
    setText("drawerIntro", meta.intro);
    const histCaption = `${meta.histLabel} for the active lens and horizon.`;
    setText("histCaption", histCaption);
    const mapEl = document.getElementById("map");
    if (mapEl) mapEl.setAttribute("aria-label", `Choropleth map of U.S. ${meta.plural} colored by risk`);
    const histEl = document.getElementById("natHisto");
    if (histEl) histEl.setAttribute("aria-label", `Histogram of ${STATE.geoMode} risk by decile`);
    const drawer = document.getElementById("drawer");
    if (drawer) drawer.setAttribute("aria-label", meta.detail);
    const close = document.getElementById("drawerClose");
    if (close) close.setAttribute("aria-label", `Close ${meta.detail.toLowerCase()}`);
  }

  const rampToExpr = () => {
    const ramp = ramps()[STATE.activeModel];
    const m = riskProp();
    return [
      "case",
      ["==", ["get", m], null], nullFillColor(),
      ["interpolate", ["linear"], ["get", m], ...ramp.flat()]
    ];
  };

  // State-border paint expressions — thicker/brighter on the focused state.
  const stateBordersOpacity = () => {
    const base = ["interpolate", ["linear"], ["zoom"], 3, 0.35, 5, 0.45, 8, 0.55, 10, 0.65];
    if (!STATE.focusedState) return base;
    const dim = ["interpolate", ["linear"], ["zoom"], 3, 0.25, 5, 0.30, 8, 0.35, 10, 0.40];
    return ["case", ["==", ["get", "st"], STATE.focusedState], 0.95, dim];
  };
  const stateBordersWidth = () => {
    const base = ["interpolate", ["linear"], ["zoom"], 3, 0.6, 6, 1.0, 9, 1.4, 12, 1.8];
    if (!STATE.focusedState) return base;
    return ["case", ["==", ["get", "st"], STATE.focusedState], 2.4, base];
  };

  // ---------------------------------------------------------------------
  // BOOT
  // ---------------------------------------------------------------------
  // ---------------------------------------------------------------------
  // THEME SWITCHING
  // ---------------------------------------------------------------------
  function applyThemeToMap() {
    if (!map) return;
    const dark = isDarkTheme();
    map.setPaintProperty("bg", "background-color", bgColor());
    map.setLayoutProperty("base-dark", "visibility", dark ? "visible" : "none");
    map.setLayoutProperty("base-light", "visibility", dark ? "none" : "visible");
    const outline = coralColor();
    const edge = edgeColor();
    ["counties-outline-hover", "counties-outline-pinned",
      "tracts-outline-hover", "tracts-outline-pinned"].forEach(id => {
        if (map.getLayer(id)) map.setPaintProperty(id, "line-color", outline);
      });
    ["counties-edge", "tracts-edge"].forEach(id => {
      if (map.getLayer(id)) map.setPaintProperty(id, "line-color", edge);
    });
    // Repaint choropleth fill with theme-appropriate ramp
    const fillExpr = computeColorExpr();
    ["counties-fill", "tracts-fill"].forEach(id => {
      if (map.getLayer(id)) map.setPaintProperty(id, "fill-color", fillExpr);
    });
  }

  function setTheme(t) {
    document.documentElement.dataset.theme = t;
    const meta = document.querySelector("meta[name='theme-color']");
    if (meta) meta.content = t === "dark" ? "#1c2230" : "#f7f5f0";
    applyThemeToMap();
  }

  function initTheme() {
    const toggle = document.querySelector("[data-theme-toggle]");
    if (!toggle) return;
    toggle.addEventListener("click", () => {
      const next = isDarkTheme() ? "light" : "dark";
      setTheme(next);
      localStorage.setItem("theme", next);
    });
  }

  document.addEventListener("DOMContentLoaded", boot);

  async function boot() {
    document.body.dataset.geo = "county";
    document.body.dataset.model = "m1";
    document.body.dataset.horizon = "h3";
    STATE.methModel = STATE.activeModel === "m2" ? "influenceable" : "diagnostic";

    const [feat, dict, states, bbox, ablH3, ablH6, regH3, regH6, prH3, prH6, fdist, tfeat, cfeat] = await Promise.all([
      fetchOptional("data/feature_stats.json"),
      fetchOptional("data/feature_dictionary.json"),
      fetchOptional("data/state_stats.json"),
      fetchOptional("data/state_bbox.json"),
      fetchOptional("data/ablation_h3.json"),
      fetchOptional("data/ablation_h6.json"),
      fetchOptional("data/regime_h3.json"),
      fetchOptional("data/regime_h6.json"),
      fetchOptional("data/pruning_h3.json"),
      fetchOptional("data/pruning_h6.json"),
      fetchOptional("data/feature_distributions.json"),
      fetchGzipJson("data/tract_features.json.gz").catch(() => null),
      fetchGzipJson("data/county_features.json.gz").catch(() => null),
    ]);
    STATE.feat = feat;
    STATE.featureDictionary = dict;
    STATE.states = states;
    STATE.bbox = bbox;
    STATE.abl = { h3: ablH3, h6: ablH6 };
    STATE.regime = { h3: regH3, h6: regH6 };
    STATE.pruning = { h3: prH3, h6: prH6 };
    STATE.featureDistributions = fdist;
    STATE.tractFeatures = tfeat;
    STATE.countyFeatures = cfeat;
    if (!fdist || !tfeat) document.body.dataset.noDistributions = "1";
    syncMethodologyModelButtons();

    if (!feat) document.getElementById('sliders')?.insertAdjacentHTML('afterbegin', '<p class="data-missing">Scenario data unavailable</p>');
    if (!states) document.getElementById('topStates')?.insertAdjacentHTML('beforebegin', '<p class="data-missing">State data unavailable</p>');
    if (!ablH3 && !ablH6) document.getElementById('ablChart')?.insertAdjacentHTML('afterbegin', '<p class="data-missing">Ablation data unavailable</p>');

    initTheme();
    initMap();
    initToggles();
    renderHeadline();
    renderTopStates();
    renderHistogram();
    renderSliders();
    renderMethodology();
    bindReset();
    bindMapReload();
    bindFocusClose();
    bindDrawerClose();
    syncHorizonAffordances();
    initAccordions();
    initFeatureDictionary();
    document.querySelector('.guide__card:first-child .accordion__toggle')?.click();
    const stripCtrl = initGuideStrip();
    initSpotlight(stripCtrl);
    renderGeoCopy();
  }

  function initGuideStrip() {
    const el = document.getElementById("useGuide");
    if (!el) return null;
    const btn = el.querySelector(".guide__collapse");

    function setState(s) {
      el.classList.toggle("is-expanded", s === "expanded");
      el.classList.toggle("is-collapsed", s === "collapsed");
      document.body.classList.toggle("is-guide-expanded", s === "expanded");
      document.body.classList.toggle("is-guide-collapsed", s === "collapsed");
      if (btn) {
        btn.setAttribute("aria-expanded", String(s === "expanded"));
        btn.innerHTML = s === "expanded"
          ? '<span>Hide guide</span> <span aria-hidden="true">&#8595;</span>'
          : '<span>Show guide</span> <span aria-hidden="true">&#8593;</span>';
      }
    }

    setState("expanded");

    el.addEventListener("click", (e) => {
      if (el.classList.contains("is-collapsed")) {
        setState("expanded");
        return;
      }
      if (btn && (e.target === btn || btn.contains(e.target))) {
        setState("collapsed");
        localStorage.setItem("guideSeen", "1");
      }
    });

    return { collapse: () => setState("collapsed") };
  }

  function viewportBottomEdge(pad = 8) {
    const guide = document.getElementById("useGuide");
    let inset = 0;
    if (guide) {
      const rect = guide.getBoundingClientRect();
      if (rect.height > 0 && rect.bottom > window.innerHeight - 2) {
        inset = window.innerHeight - Math.max(0, rect.top);
      }
    }
    return window.innerHeight - inset - pad;
  }

  function initSpotlight(stripCtrl) {
    const cards = [...document.querySelectorAll(".guide__card[data-spotlight-target]")];
    if (!cards.length) return;

    const overlay = document.getElementById("spotlight");
    if (!overlay) return;
    const ring = overlay.querySelector(".spotlight__ring");
    const callout = overlay.querySelector(".spotlight__callout");
    const kicker = overlay.querySelector(".spotlight__kicker");
    const titleEl = overlay.querySelector(".spotlight__title");
    const bodyEl = overlay.querySelector(".spotlight__body");
    const prevBtn = overlay.querySelector(".spotlight__prev");
    const nextBtn = overlay.querySelector(".spotlight__next");
    const closeBtn = overlay.querySelector(".spotlight__close");
    const railEl = document.querySelector(".rail");
    const drawerEl = document.getElementById("drawer");
    const viewport = window.visualViewport || null;

    let current = -1;
    let rafId = null;
    let activeTarget = null;
    let activeSelector = "";
    let settleTimer = null;
    let settleCleanup = null;
    let layoutObserver = null;

    function emitDrawerLayoutChange() {
      window.dispatchEvent(new CustomEvent("drawer-layout-change"));
    }

    // wire card clicks + keyboard
    cards.forEach((card, i) => {
      card.addEventListener("click", (e) => { e.stopPropagation(); open(i); });
      card.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(i); }
      });
    });

    prevBtn.addEventListener("click", () => open((current - 1 + cards.length) % cards.length));
    nextBtn.addEventListener("click", () => open((current + 1) % cards.length));
    closeBtn.addEventListener("click", close);

    document.addEventListener("keydown", (e) => {
      if (overlay.hidden) return;
      if (e.key === "Escape") close();
      if (e.key === "ArrowRight") open((current + 1) % cards.length);
      if (e.key === "ArrowLeft") open((current - 1 + cards.length) % cards.length);
    });

    function resolveActiveTarget() {
      if (activeTarget && activeTarget.isConnected) return activeTarget;
      if (!activeSelector) return null;
      activeTarget = document.querySelector(activeSelector);
      return activeTarget;
    }

    function measureTargetRect() {
      const target = resolveActiveTarget();
      if (!target) return null;
      const rect = target.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return null;
      return rect;
    }

    function pointInRect(x, y, rect) {
      return x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom;
    }

    function getDrawerRect() {
      if (!drawerEl || drawerEl.hidden || drawerEl.getAttribute("aria-hidden") === "true") return null;
      const rect = drawerEl.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return null;
      return rect;
    }

    function schedulePosition() {
      if (rafId) cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        rafId = null;
        if (current < 0) return;
        position();
      });
    }

    function watchScrollUntilSettled(scrollers, fallbackMs = 520) {
      const els = scrollers.filter(Boolean);
      if (!els.length) {
        schedulePosition();
        return;
      }

      let idleTimer = null;
      const onScroll = () => {
        clearTimeout(idleTimer);
        idleTimer = setTimeout(() => schedulePosition(), 80);
      };

      clearTimeout(settleTimer);
      if (settleCleanup) settleCleanup();
      els.forEach(el => el.addEventListener("scroll", onScroll, { passive: true }));
      settleCleanup = () => {
        els.forEach(el => el.removeEventListener("scroll", onScroll));
        clearTimeout(idleTimer);
        settleCleanup = null;
      };
      settleTimer = setTimeout(() => {
        if (settleCleanup) settleCleanup();
        schedulePosition();
      }, fallbackMs);
    }

    function onViewportChange() {
      if (overlay.hidden) return;
      schedulePosition();
    }

    function onDocumentPointerDown(e) {
      if (overlay.hidden) return;
      if (callout.contains(e.target)) return;
      const rect = measureTargetRect();
      if (rect && pointInRect(e.clientX, e.clientY, rect)) return;
      e.preventDefault();
      e.stopPropagation();
      close();
    }

    function open(i) {
      const wasOpen = !overlay.hidden;
      current = i;
      const card = cards[i];
      const isCompareGuide = card.dataset.guideAction === "compare-models";
      const selector = isCompareGuide && STATE.pinnedFeature
        ? ".ovl--toggles .toggrp:first-child"
        : card.dataset.spotlightTarget;
      const target = document.querySelector(selector);
      if (!target) return;
      activeSelector = selector;
      activeTarget = target;

      // collapse guide strip
      if (stripCtrl) stripCtrl.collapse();

      // populate callout
      kicker.textContent = `Step ${String(i + 1).padStart(2, "0")} of ${cards.length}`;
      titleEl.textContent = card.querySelector(".guide__h")?.textContent || "";
      bodyEl.innerHTML = card.querySelector(".accordion__body")?.innerHTML || "";
      if (isCompareGuide) {
        bodyEl.innerHTML = STATE.pinnedFeature
          ? "<p>Keep the drawer open and switch Diagnostic ↔ Influenceable. The comparison shows whether risk is coming from status-quo conditions, lending-environment variables, or both.</p>"
          : "<p>Click a county or tract first. The drawer will hold that place in view so you can compare Diagnostic and Influenceable without chasing hover state.</p>";
      }

      // show overlay
      overlay.hidden = false;
      overlay.removeAttribute("aria-hidden");

      // attach persistent listeners only on first open
      if (!wasOpen) {
        window.addEventListener("resize", onViewportChange);
        window.addEventListener("scroll", onViewportChange, { passive: true });
        window.addEventListener("drawer-layout-change", onViewportChange);
        document.addEventListener("pointerdown", onDocumentPointerDown, true);
        if (viewport) {
          viewport.addEventListener("resize", onViewportChange);
          viewport.addEventListener("scroll", onViewportChange);
        }
        if (railEl) railEl.addEventListener("scroll", onViewportChange, { passive: true });
        if (drawerEl) {
          drawerEl.addEventListener("transitionrun", emitDrawerLayoutChange);
          drawerEl.addEventListener("transitionend", emitDrawerLayoutChange);
        }
        if (!layoutObserver) {
          layoutObserver = new MutationObserver(() => {
            if (!overlay.hidden) schedulePosition();
          });
          layoutObserver.observe(document.body, { attributes: true, attributeFilter: ["class"] });
          if (drawerEl) {
            layoutObserver.observe(drawerEl, { attributes: true, attributeFilter: ["hidden", "aria-hidden", "class", "style"] });
          }
        }
      }

      const rect = target.getBoundingClientRect();
      const inView = rect.top >= 0 && rect.bottom <= window.innerHeight &&
        rect.left >= 0 && rect.right <= window.innerWidth;

      // if target IS the rail container and it's scrolled down, reset scroll first
      if (target === railEl && railEl.scrollTop > 0) {
        railEl.scrollTo({ top: 0, behavior: "smooth" });
        watchScrollUntilSettled([railEl], 420);
      } else if (!inView) {
        // target is off-screen: scroll it into view then reposition
        target.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
        watchScrollUntilSettled([window, railEl], 560);
      } else {
        // already in view — defer one frame so callout reflow settles after innerHTML change
        schedulePosition();
      }
    }

    function position() {
      const rect = measureTargetRect();
      if (!rect) return;

      const PAD = 8;
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const drawerRect = getDrawerRect();

      ring.style.left = (rect.left - PAD) + "px";
      ring.style.top = (rect.top - PAD) + "px";
      ring.style.width = (rect.width + PAD * 2) + "px";
      ring.style.height = (rect.height + PAD * 2) + "px";

      const calloutW = 340;
      const calloutH = callout.getBoundingClientRect().height || 260;
      const GAP = 20;
      const minLeft = drawerRect ? Math.max(GAP, drawerRect.right + GAP) : GAP;
      const maxLeft = Math.max(minLeft, vw - calloutW - GAP);

      let left;
      if (rect.right + calloutW + GAP * 2 <= vw) {
        left = rect.right + GAP;
      } else if (rect.left - calloutW - GAP * 2 >= minLeft) {
        left = rect.left - calloutW - GAP;
      } else {
        left = Math.max(minLeft, Math.min(maxLeft, rect.left));
      }

      let top = rect.top + rect.height / 2 - calloutH / 2;
      top = Math.max(GAP, Math.min(vh - calloutH - GAP, top));

      callout.style.left = left + "px";
      callout.style.top = top + "px";
    }

    function close() {
      overlay.hidden = true;
      overlay.setAttribute("aria-hidden", "true");
      current = -1;
      activeTarget = null;
      activeSelector = "";
      clearTimeout(settleTimer);
      if (settleCleanup) settleCleanup();
      if (rafId) cancelAnimationFrame(rafId);
      rafId = null;
      window.removeEventListener("resize", onViewportChange);
      window.removeEventListener("scroll", onViewportChange);
      window.removeEventListener("drawer-layout-change", onViewportChange);
      document.removeEventListener("pointerdown", onDocumentPointerDown, true);
      if (viewport) {
        viewport.removeEventListener("resize", onViewportChange);
        viewport.removeEventListener("scroll", onViewportChange);
      }
      if (railEl) railEl.removeEventListener("scroll", onViewportChange);
      if (drawerEl) {
        drawerEl.removeEventListener("transitionrun", emitDrawerLayoutChange);
        drawerEl.removeEventListener("transitionend", emitDrawerLayoutChange);
      }
      if (layoutObserver) {
        layoutObserver.disconnect();
        layoutObserver = null;
      }
    }
  }

  function initAccordions() {
    document.querySelectorAll(".accordion__toggle").forEach(btn => {
      btn.addEventListener("click", () => {
        const container = btn.closest("[data-accordion]");
        if (!container) return;
        const bodies = container.querySelectorAll(".accordion__body");
        const isOpen = btn.getAttribute("aria-expanded") === "true";
        bodies.forEach(b => b.classList.toggle("is-open", !isOpen));
        btn.setAttribute("aria-expanded", String(!isOpen));
      });
    });
  }

  function initFeatureDictionary() {
    const overlay = document.getElementById("featureDictOverlay");
    const rowsEl = document.getElementById("featureDictRows");
    const titleEl = document.getElementById("featureDictTitle");
    const kickerEl = document.getElementById("featureDictKicker");
    const groupsEl = document.getElementById("featureDictGroups");
    const noteEl = document.getElementById("featureDictNote");
    const closeBtn = document.getElementById("featureDictClose");
    const launchers = Array.from(document.querySelectorAll("[data-feature-dict]"));
    if (!overlay || !rowsEl || !titleEl || !kickerEl || !groupsEl || !noteEl || !closeBtn || !launchers.length) return;

    let lastTrigger = null;
    let activeModel = "diagnostic";
    let activeCategory = "all";

    const meta = {
      diagnostic: {
        title: "Diagnostic feature dictionary",
        label: "Diagnostic",
      },
      influenceable: {
        title: "Influenceable feature dictionary",
        label: "Influenceable",
      },
    };

    const categories = {
      diagnostic: [
        { key: "place", label: "Place context", note: "Rurality, tract scale, and persistent-poverty status. These describe what kind of place the tract is before lending behavior enters." },
        { key: "conditions", label: "People and conditions", note: "Demographics, income, education, unemployment, poverty, and housing vacancy. Diagnostic-only signals, useful for prediction but not policy levers by themselves." },
        { key: "bank_market", label: "Bank market structure", note: "County-level CRA and FDIC concentration. These capture whether local credit supply is broad or dominated by a few institutions." },
        { key: "hmda_flow", label: "Mortgage credit flow", note: "HMDA mortgage activity, approvals, denials, withdrawals, purchases, and lender counts. This is adjacent credit-market evidence, not small-business lending itself." },
        { key: "hmda_applicants", label: "HMDA applicant mix", note: "Race and ethnicity counts among HMDA mortgage applicants. Diagnostic context only; not a recommended intervention target." },
      ],
      influenceable: [
        { key: "lender_mix", label: "Lender mix", note: "Who is making the CRA small-business loans: community banks, top-4 banks, credit unions, and smaller loan-size shares." },
        { key: "concentration", label: "Lender concentration", note: "Whether a tract's small-business lending depends on one or a few lenders after residualization." },
        { key: "branch_access", label: "Branch access", note: "Physical branch distance, nearby branch count, and recent branch closures." },
        { key: "mission_lenders", label: "Mission lenders", note: "Minority Depository Institution branches and SBA microlender intermediaries near the tract." },
        { key: "state_policy", label: "State policy", note: "State Small Business Credit Initiative program availability and breadth." },
      ],
    };

    const categoryByColumn = {
      diagnostic: {
        ruca_code: "place",
        housing_units: "place",
        is_persistent_poverty: "place",
        population: "place",
        is_rural: "place",
        median_hh_income: "conditions",
        pct_black: "conditions",
        pct_minority: "conditions",
        pct_poverty: "conditions",
        pct_vacant: "conditions",
        pct_hispanic: "conditions",
        pct_bachelor_plus: "conditions",
        unemployment_rate: "conditions",
        fdic_deposit_hhi_chg3yr: "bank_market",
        fdic_deposit_hhi: "bank_market",
        fdic_top_bank_share_chg3yr: "bank_market",
        cra_county_amount_hhi: "bank_market",
        cra_county_top_lender_share_count: "bank_market",
        cra_county_count_hhi: "bank_market",
        fdic_top_bank_share: "bank_market",
        cra_county_top_lender_share_amount: "bank_market",
        fdic_deposit_hhi_chg1yr: "bank_market",
        fdic_top_bank_share_chg1yr: "bank_market",
        has_hmda: "hmda_flow",
        sum_loan_amount: "hmda_flow",
        mean_loan_amount: "hmda_flow",
        n_originated: "hmda_flow",
        n_withdrawn: "hmda_flow",
        n_distinct_lenders: "hmda_flow",
        n_denied: "hmda_flow",
        approval_rate: "hmda_flow",
        n_applications: "hmda_flow",
        denial_rate: "hmda_flow",
        n_purchased: "hmda_flow",
        n_white: "hmda_applicants",
        n_hispanic: "hmda_applicants",
        n_other_race: "hmda_applicants",
        n_black: "hmda_applicants",
        n_asian: "hmda_applicants",
      },
      influenceable: {
        pct_loans_from_community_banks_resid: "lender_mix",
        pct_loans_from_top4_banks_resid: "lender_mix",
        pct_loans_from_credit_unions_resid: "lender_mix",
        pct_loans_under_100k_resid: "lender_mix",
        pct_loans_under_250k_resid: "lender_mix",
        top1_lender_share_tract_resid: "concentration",
        top3_lender_share_tract_resid: "concentration",
        lender_hhi_tract_resid: "concentration",
        distance_to_nearest_bank_branch: "branch_access",
        branches_within_5mi: "branch_access",
        branch_closures_3y_within_10mi: "branch_access",
        microloan_intermediary_within_25mi: "mission_lenders",
        mdi_branches_within_10mi: "mission_lenders",
        mdi_branches_within_25mi: "mission_lenders",
        nearest_mdi_branch_miles: "mission_lenders",
        mdi_active_in_county: "mission_lenders",
        ssbci_active: "state_policy",
        ssbci_2_0_active: "state_policy",
        ssbci_program_count: "state_policy",
        ssbci_n_capital_programs: "state_policy",
      },
    };

    function categoryFor(model, item) {
      return (categoryByColumn[model] && categoryByColumn[model][item.column]) || "other";
    }

    function getCategory(model, key) {
      return (categories[model] || []).find(cat => cat.key === key);
    }

    function countByCategory(model, items) {
      const counts = new Map();
      items.forEach(item => counts.set(categoryFor(model, item), (counts.get(categoryFor(model, item)) || 0) + 1));
      return counts;
    }

    function renderCategoryControls(model, items) {
      const counts = countByCategory(model, items);
      groupsEl.replaceChildren();

      const allBtn = document.createElement("button");
      allBtn.type = "button";
      allBtn.className = "featureDict__group";
      allBtn.dataset.category = "all";
      allBtn.setAttribute("aria-pressed", String(activeCategory === "all"));
      allBtn.textContent = `All ${items.length}`;
      groupsEl.appendChild(allBtn);

      (categories[model] || []).forEach(cat => {
        const count = counts.get(cat.key) || 0;
        if (!count) return;
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "featureDict__group";
        btn.dataset.category = cat.key;
        btn.setAttribute("aria-pressed", String(activeCategory === cat.key));
        btn.textContent = `${cat.label} ${count}`;
        groupsEl.appendChild(btn);
      });
    }

    function renderNote(model, items) {
      if (activeCategory === "all") {
        noteEl.textContent = model === "diagnostic"
          ? "Grouped by feature family so the diagnostic model reads as categories, not a wall of columns."
          : "Grouped by policy lever family. Every influenceable feature maps to something a policymaker could plausibly fund, build, or support.";
        return;
      }

      const cat = getCategory(model, activeCategory);
      const count = items.filter(item => categoryFor(model, item) === activeCategory).length;
      noteEl.textContent = cat ? `${cat.label}, ${count} features. ${cat.note}` : "";
    }

    function appendCategoryRow(frag, cat, count) {
      const tr = document.createElement("tr");
      tr.className = "featureDict__catrow";
      const td = document.createElement("td");
      td.colSpan = 3;
      td.innerHTML = `<span>${cat.label}</span><em>${count} features</em><small>${cat.note}</small>`;
      tr.appendChild(td);
      frag.appendChild(tr);
    }

    function appendItemRow(frag, item) {
      const tr = document.createElement("tr");
      [item.column, item.label, item.description].forEach(value => {
        const td = document.createElement("td");
        td.textContent = value || "Not available";
        tr.appendChild(td);
      });
      frag.appendChild(tr);
    }

    function render(model) {
      activeModel = model;
      const items = (STATE.featureDictionary && STATE.featureDictionary[model]) || [];
      const modelMeta = meta[model] || meta.diagnostic;

      overlay.dataset.model = model;
      titleEl.textContent = modelMeta.title;
      kickerEl.textContent = `${modelMeta.label} · ${items.length} features`;
      rowsEl.replaceChildren();
      renderCategoryControls(model, items);
      renderNote(model, items);

      if (!items.length) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 3;
        td.textContent = "Feature dictionary unavailable.";
        tr.appendChild(td);
        rowsEl.appendChild(tr);
        return;
      }

      const frag = document.createDocumentFragment();
      if (activeCategory === "all") {
        (categories[model] || []).forEach(cat => {
          const groupItems = items.filter(item => categoryFor(model, item) === cat.key);
          if (!groupItems.length) return;
          appendCategoryRow(frag, cat, groupItems.length);
          groupItems.forEach(item => appendItemRow(frag, item));
        });
      } else {
        items
          .filter(item => categoryFor(model, item) === activeCategory)
          .forEach(item => appendItemRow(frag, item));
      }
      rowsEl.appendChild(frag);
    }

    function open(model, trigger) {
      lastTrigger = trigger || null;
      activeCategory = "all";
      render(model);
      overlay.hidden = false;
      overlay.setAttribute("aria-hidden", "false");
      document.body.classList.add("is-feature-dict-open");
      requestAnimationFrame(() => closeBtn.focus());
    }

    function close() {
      if (overlay.hidden) return;
      overlay.hidden = true;
      overlay.setAttribute("aria-hidden", "true");
      document.body.classList.remove("is-feature-dict-open");
      if (lastTrigger && document.contains(lastTrigger)) lastTrigger.focus();
      lastTrigger = null;
    }

    launchers.forEach(btn => {
      btn.addEventListener("click", () => open(btn.dataset.featureDict, btn));
    });

    groupsEl.addEventListener("click", e => {
      const btn = e.target.closest("[data-category]");
      if (!btn) return;
      activeCategory = btn.dataset.category || "all";
      render(activeModel);
      btn.focus();
    });

    overlay.querySelectorAll("[data-feature-dict-close]").forEach(btn => {
      btn.addEventListener("click", close);
    });

    document.addEventListener("keydown", e => {
      if (overlay.hidden) return;
      if (e.key === "Escape") {
        e.preventDefault();
        close();
        return;
      }

      if (e.key !== "Tab") return;
      const focusable = Array.from(overlay.querySelectorAll("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])"))
        .filter(el => !el.disabled && el.offsetParent !== null);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    });
  }

  async function fetchOptional(path) {
    try {
      const r = await fetch(path);
      if (!r.ok) return null;
      return await r.json();
    } catch (e) {
      console.warn("[fetch]", path, e && e.message);
      return null;
    }
  }

  // ---------------------------------------------------------------------
  // MAP
  // ---------------------------------------------------------------------
  let map;

  function ensureLayerInteractions(fillLayerId, hoverLayerId) {
    if (!map || !map.getLayer(fillLayerId) || !map.getLayer(hoverLayerId)) return;
    if (!map.__boundHoverLayers) map.__boundHoverLayers = new Set();
    if (!map.__boundClickLayers) map.__boundClickLayers = new Set();

    if (!map.__boundHoverLayers.has(fillLayerId)) {
      bindHoverForLayer(fillLayerId, hoverLayerId);
      map.__boundHoverLayers.add(fillLayerId);
    }
    if (!map.__boundClickLayers.has(fillLayerId)) {
      bindClickForLayer(fillLayerId);
      map.__boundClickLayers.add(fillLayerId);
    }
  }

  function showMapLoading(message) {
    const el = document.getElementById("map-loading");
    if (!el) return;
    const label = el.querySelector("span");
    if (label && message) label.textContent = message;
    el.style.display = "";
  }

  function hideMapLoading() {
    const el = document.getElementById("map-loading");
    if (el) el.style.display = "none";
  }

  function isTractSourceLoaded() {
    if (!map || !map.getSource("tracts")) return false;
    if (STATE.tractSourceReady) return true;
    if (typeof map.isSourceLoaded === "function" && map.isSourceLoaded("tracts")) {
      STATE.tractSourceReady = true;
      return true;
    }
    return false;
  }

  function waitForMapIdle(done, timeout = 1800) {
    if (!map) {
      done();
      return;
    }
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      done();
    };
    const timer = setTimeout(finish, timeout);
    map.once("idle", finish);
  }

  function waitForTractSource(done) {
    if (isTractSourceLoaded()) {
      done(true);
      return;
    }
    const finish = () => {
      map.off("sourcedata", onSource);
      clearTimeout(timer);
      const ready = isTractSourceLoaded();
      if (ready) hideMapLoading();
      done(ready);
    };
    const onSource = (e) => {
      if (e.sourceId === "tracts" && e.isSourceLoaded) {
        STATE.tractSourceReady = true;
        finish();
      }
    };
    const timer = setTimeout(finish, 9000);
    map.on("sourcedata", onSource);
  }

  function warmTractLayers() {
    if (!map || STATE.tractLayersReady) return;
    const warm = () => ensureTractLayers({ showLoading: false });
    if ("requestIdleCallback" in window) {
      window.requestIdleCallback(warm, { timeout: 2200 });
    } else {
      setTimeout(warm, 700);
    }
  }

  function initMap() {
    map = new maplibregl.Map({
      container: "map",
      style: BASE_STYLE,
      center: [-96.5, 38.5],
      zoom: 3.6,
      minZoom: 2.5,
      maxZoom: 11,
      attributionControl: { compact: true },
      renderWorldCopies: false,
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
      doubleClickZoom: false,
      antialias: true,
    });
    map.on("error", (e) => console.warn("[map]", e && e.error ? e.error.message : e));

    map.on("load", () => {
      map.addSource("counties", {
        type: "geojson",
        data: "data/counties.geojson",
        generateId: false,
        tolerance: 0.5,
      });

      map.addLayer({
        id: "counties-fill",
        type: "fill",
        source: "counties",
        paint: {
          "fill-color": rampToExpr(),
          "fill-opacity": [
            "case",
            ["==", ["get", riskProp()], null], 0.18,
            0.92,
          ],
          "fill-opacity-transition": { duration: 600, delay: 0 },
          "fill-color-transition": { duration: REDUCED ? 0 : 500, delay: 0 },
        },
      });
      map.addLayer({
        id: "counties-outline-hover",
        type: "line",
        source: "counties",
        filter: ["==", ["get", "f"], "__none__"],
        paint: {
          "line-color": coralColor(),
          "line-width": 1.4,
          "line-opacity": 1,
        },
      });
      map.addLayer({
        id: "counties-outline-pinned",
        type: "line",
        source: "counties",
        filter: ["==", ["get", "f"], "__none__"],
        paint: {
          "line-color": coralColor(),
          "line-width": 1.8,
          "line-opacity": 1,
        },
      });
      map.addLayer({
        id: "counties-edge",
        type: "line",
        source: "counties",
        paint: {
          "line-color": edgeColor(),
          "line-width": 0.45,
          "line-opacity": 0.5,
        },
      });

      map.addSource("states", {
        type: "geojson",
        data: "data/states.geojson",
        generateId: false,
        tolerance: 0.5,
      });
      map.addLayer({
        id: "state-borders",
        type: "line",
        source: "states",
        paint: {
          "line-color": "#e8edf2",
          "line-opacity": stateBordersOpacity(),
          "line-width": stateBordersWidth(),
          "line-blur": 0.3,
        },
      });

      syncGeoLayers();
      ensureLayerInteractions("counties-fill", "counties-outline-hover");
      applyThemeToMap();
      hideMapLoading();
      waitForMapIdle(warmTractLayers, 900);
    });
  }

  function ensureTractLayers({ showLoading = true } = {}) {
    if (!map || STATE.tractLayersReady) return;

    if (showLoading) showMapLoading("Loading census tracts…");

    map.addSource("tracts", {
      type: "geojson",
      data: "data/tracts.geojson",
      generateId: false,
      tolerance: 0.5,
    });

    map.addLayer({
      id: "tracts-fill",
      type: "fill",
      source: "tracts",
      paint: {
        "fill-color": rampToExpr(),
        "fill-opacity": [
          "case",
          ["==", ["get", riskProp()], null], 0.18,
          REDUCED ? 0.92 : 0,
        ],
        "fill-opacity-transition": { duration: 600, delay: 0 },
        "fill-color-transition": { duration: REDUCED ? 0 : 500, delay: 0 },
      },
    });

    map.addLayer({
      id: "tracts-outline-hover",
      type: "line",
      source: "tracts",
      filter: ["==", ["get", "f"], "__none__"],
      paint: {
        "line-color": coralColor(),
        "line-width": 1.2,
        "line-opacity": 1,
      },
    });

    map.addLayer({
      id: "tracts-outline-pinned",
      type: "line",
      source: "tracts",
      filter: ["==", ["get", "f"], "__none__"],
      paint: {
        "line-color": coralColor(),
        "line-width": 1.5,
        "line-opacity": 1,
      },
    });

    map.addLayer({
      id: "tracts-edge",
      type: "line",
      source: "tracts",
      paint: {
        "line-color": edgeColor(),
        "line-width": 0.3,
        "line-opacity": [
          "interpolate", ["linear"], ["zoom"],
          3, 0,
          5, 0,
          6, 0.4,
          9, 0.7,
        ],
      },
    });

    if (!REDUCED) {
      map.setPaintProperty("tracts-fill", "fill-opacity", [
        "case",
        ["==", ["get", riskProp()], null], 0.18,
        0.92
      ]);
    }

    STATE.tractLayersReady = true;
    ensureLayerInteractions("tracts-fill", "tracts-outline-hover");
    syncGeoLayers();

    map.on('sourcedata', function onTractSource(e) {
      if (e.sourceId === 'tracts' && e.isSourceLoaded) {
        map.off('sourcedata', onTractSource);
        STATE.tractSourceReady = true;
        hideMapLoading();
      }
    });
  }

  function syncGeoLayers({ keepCountyUntilTractsReady = false } = {}) {
    if (!map) return;
    if (!isCountyMode()) ensureTractLayers();
    const countyVis = (isCountyMode() || (keepCountyUntilTractsReady && !isTractSourceLoaded())) ? "visible" : "none";
    const tractVis = isCountyMode() ? "none" : "visible";
    [
      ["counties-fill", countyVis],
      ["counties-outline-hover", countyVis],
      ["counties-outline-pinned", countyVis],
      ["counties-edge", countyVis],
      ["tracts-fill", tractVis],
      ["tracts-outline-hover", tractVis],
      ["tracts-outline-pinned", tractVis],
      ["tracts-edge", tractVis],
    ].forEach(([id, visibility]) => {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", visibility);
    });
    resetHover();
  }

  // ---------------------------------------------------------------------
  // HOVER + CLICK
  // ---------------------------------------------------------------------
  let hoverFips = null;
  function resetHover() {
    hoverFips = null;
    ["tracts-outline-hover", "counties-outline-hover"].forEach(id => {
      if (map && map.getLayer(id)) map.setFilter(id, ["==", ["get", "f"], "__none__"]);
    });
    const tip = document.getElementById("tip");
    if (tip) tip.hidden = true;
    if (map) map.getCanvas().style.cursor = "";
  }

  function bindHoverForLayer(fillLayerId, hoverLayerId) {
    const tip = document.getElementById("tip");

    map.on("mousemove", fillLayerId, (e) => {
      if (fillLayerId !== activeFillLayerId()) return;
      if (!e.features || !e.features.length) return;
      const p = e.features[0].properties;
      hoverFips = p.f;

      map.setFilter(hoverLayerId, ["==", ["get", "f"], hoverFips || "__none__"]);

      tip.hidden = false;

      const num = (v) => (v == null || v === "null") ? null : Number(v);
      const m1_h3 = num(p.m1_h3), m1_h6 = num(p.m1_h6);
      const m2_h3 = num(p.m2_h3), m2_h6 = num(p.m2_h6);
      const m1r_h3 = num(p.m1r_h3), m1r_h6 = num(p.m1r_h6);
      const m2r_h3 = num(p.m2r_h3), m2r_h6 = num(p.m2r_h6);

      const fmt = (v) => (v == null) ? "–" : (v * 100).toFixed(2) + "%";

      document.getElementById("tipState").textContent = p.st || "–";
      document.getElementById("tipFips").textContent = p.f || "–";
      document.getElementById("tipCounty").textContent = p.cn || "–";
      // tipChip background is handled by CSS (uses var(--s2))

      // Active row vs other row
      const active = STATE.activeModel;
      const other = active === "m1" ? "m2" : "m1";
      const labels = { m1: "Diagnostic", m2: "Influenceable" };

      const aRow = document.getElementById("tipRowActive");
      const oRow = document.getElementById("tipRowOther");
      aRow.classList.remove("is-h3", "is-h6");
      aRow.classList.add(`is-${STATE.activeHorizon}`);

      document.getElementById("tipDotActive").className = "tip__dot tip__dot--" + active;
      document.getElementById("tipDotOther").className = "tip__dot tip__dot--" + other;
      document.getElementById("tipLActive").textContent = labels[active];
      document.getElementById("tipLOther").textContent = labels[other];

      const vals = { m1: { h3: m1_h3, h6: m1_h6 }, m2: { h3: m2_h3, h6: m2_h6 } };
      document.getElementById("tipActive_h3").textContent = fmt(vals[active].h3);
      document.getElementById("tipActive_h6").textContent = fmt(vals[active].h6);
      document.getElementById("tipOther_h3").textContent = fmt(vals[other].h3);
      document.getElementById("tipOther_h6").textContent = fmt(vals[other].h6);

      // Percentile is for active (model, horizon)
      const ranks = { m1: { h3: m1r_h3, h6: m1r_h6 }, m2: { h3: m2r_h3, h6: m2r_h6 } };
      const pct = ranks[active][STATE.activeHorizon];
      document.getElementById("tipPct").textContent = (pct == null) ? "–" : "p" + Math.round(pct);
      document.getElementById("tipActiveLabel").textContent =
        (active === "m1" ? "Diagnostic" : "Influenceable") + " · " + HZ_YEAR[STATE.activeHorizon];

      const x = e.originalEvent.clientX, y = e.originalEvent.clientY;
      const rect = tip.getBoundingClientRect();
      const w = rect.width || 280, h = rect.height || 160;
      let tx = x + 16, ty = y + 16;
      const bottomEdge = viewportBottomEdge();
      if (tx + w > innerWidth - 8) tx = x - w - 16;
      if (ty + h > bottomEdge) ty = y - h - 16;
      if (ty + h > bottomEdge) ty = bottomEdge - h;
      if (ty < 8) ty = 8;
      tip.style.left = tx + "px";
      tip.style.top = ty + "px";
      map.getCanvas().style.cursor = "crosshair";
    });

    map.on("mouseleave", fillLayerId, () => {
      if (fillLayerId !== activeFillLayerId()) return;
      resetHover();
    });
  }

  function bindClickForLayer(fillLayerId) {
    map.on("click", fillLayerId, (e) => {
      if (fillLayerId !== activeFillLayerId()) return;
      if (!e.features || !e.features.length) return;
      const p = e.features[0].properties;
      if (STATE.pinnedFeature && STATE.pinnedFeature.f === p.f) {
        unpinFeature();
      } else {
        pinFeature(p);
      }
    });
  }

  async function ensureCountyStats() {
    if (STATE.countyStats || STATE.countyStatsLoading || STATE.countyStatsTried) return;
    STATE.countyStatsLoading = true;
    const data = await fetchOptional("data/county_stats.json?v=drivers-pp-1");
    STATE.countyStats = data;
    STATE.countyStatsLoading = false;
    STATE.countyStatsTried = true;
    if (STATE.pinnedFeature && isCountyMode()) refreshScenarioDrawer();
  }

  async function fetchGzipJson(path) {
    if (typeof DecompressionStream === "undefined") return null;
    const r = await fetch(path);
    if (!r.ok || !r.body) return null;
    const stream = r.body.pipeThrough(new DecompressionStream("gzip"));
    const text = await new Response(stream).text();
    return JSON.parse(text);
  }

  function flyToState(st) {
    if (!STATE.bbox || !STATE.bbox[st]) return;
    setFocusedState(st);
    const bb = STATE.bbox[st];
    map.fitBounds([[bb[0], bb[1]], [bb[2], bb[3]]], {
      padding: { top: 80, bottom: 80, left: 60, right: 380 },
      duration: REDUCED ? 0 : 1100,
      essential: true,
    });
  }

  function setFocusedState(st) {
    STATE.focusedState = st || null;
    if (map && map.getLayer("state-borders")) {
      map.setPaintProperty("state-borders", "line-opacity", stateBordersOpacity());
      map.setPaintProperty("state-borders", "line-width", stateBordersWidth());
    }
    renderFocusPanel();
    // Drivers panel percentiles depend on scope (within-state vs national);
    // refresh the open drawer so they re-rank.
    if (STATE.pinnedFeature) renderDrawerShap();
  }

  function bindFocusClose() {
    const btn = document.getElementById("focusClose");
    if (!btn) return;
    btn.addEventListener("click", () => {
      setFocusedState(null);
      // Reset map to national view
      map.flyTo({
        center: [-96.5, 38.5],
        zoom: 3.6,
        duration: REDUCED ? 0 : 800,
        essential: true,
      });
    });
  }

  function renderFocusPanel() {
    const focusEl = document.getElementById("modeFocus");
    const sumEl = document.getElementById("modeSummary");
    const scenEl = document.getElementById("modeScenario");
    const anyShift = Object.values(STATE.sliderShifts).some(z => Math.abs(z) > 0.01);

    if (!STATE.focusedState) {
      if (focusEl) focusEl.hidden = true;
      // restore the appropriate non-focus mode
      if (sumEl) sumEl.hidden = anyShift;
      if (scenEl) scenEl.hidden = !anyShift;
      return;
    }
    // Focused: hide both summary + scenario, show focus
    if (sumEl) sumEl.hidden = true;
    if (scenEl) scenEl.hidden = true;
    if (focusEl) focusEl.hidden = false;

    const st = STATE.focusedState;
    const stateRow = (STATE.states && STATE.states.states || []).find(s => s.state === st);
    if (!stateRow) {
      document.getElementById("focusName").textContent = st;
      document.getElementById("focusMeta").textContent = "no data";
      return;
    }
    document.getElementById("focusName").textContent = st;
    const aucActive = stateRow[`auc_${STATE.activeModel}_${STATE.activeHorizon}`];
    const focusCount = isCountyMode() ? stateRow.n_counties : stateRow.n_tracts;
    document.getElementById("focusMeta").textContent =
      `${(focusCount || 0).toLocaleString()} ${activeGeoMeta().plural} · AUC ${aucActive != null ? aucActive.toFixed(3) : "–"} (${STATE.activeModel === "m1" ? "Diagnostic" : "Influenceable"} · ${HZ_YEAR[STATE.activeHorizon]})`;

    // 2x2 grid: M1 h+3, M1 h+6, M2 h+3, M2 h+6
    const grid = document.getElementById("focusGrid");
    grid.innerHTML = "";
    const cells = [
      { m: "m1", h: "h3", year: "2027" },
      { m: "m1", h: "h6", year: "2030" },
      { m: "m2", h: "h3", year: "2027" },
      { m: "m2", h: "h6", year: "2030" },
    ];
    // Find max mean across the 4 cells for relative bar widths
    const means = cells.map(c => stateRow[isCountyMode() ? `county_mean_${c.m}_${c.h}` : `mean_${c.m}_${c.h}`]).filter(v => v != null);
    const maxMean = means.length ? Math.max(...means) : 0.1;
    cells.forEach(c => {
      const v = stateRow[isCountyMode() ? `county_mean_${c.m}_${c.h}` : `mean_${c.m}_${c.h}`];
      const auc = stateRow[`auc_${c.m}_${c.h}`];
      const isActive = c.m === STATE.activeModel && c.h === STATE.activeHorizon;
      const div = document.createElement("div");
      div.className = `focuscell focuscell--${c.m}${isActive ? " is-active" : ""}`;
      const widthPct = (v != null && maxMean > 0) ? Math.max(2, (v / maxMean) * 100) : 0;
      div.innerHTML = `
        <div class="focuscell__head">
          <span class="focuscell__tag focuscell__tag--${c.m}">${c.m === "m1" ? "Diagnostic" : "Influenceable"}</span>
          <span>${c.year} ${c.h === "h3" ? "forecast" : "scenario"}</span>
        </div>
        <div class="focuscell__v">${v != null ? (v * 100).toFixed(2) + "%" : "–"}</div>
        <div class="focuscell__bar"><div class="focuscell__bar-fill" style="width: ${widthPct}%"></div></div>
        <div class="focuscell__sub">AUC ${auc != null ? auc.toFixed(3) : "–"}</div>
      `;
      grid.appendChild(div);
    });

    // Top 5 geographies at active (model, horizon)
    const topKey = `${STATE.activeModel}_${STATE.activeHorizon}`;
    const top = activeStateTopList(stateRow, topKey);
    const tEl = document.getElementById("focusTopTracts");
    tEl.innerHTML = "";
    top.forEach((t, i) => {
      const v = t[`${STATE.activeModel}_${STATE.activeHorizon}`];
      const li = document.createElement("li");
      li.className = "toptract";
      li.innerHTML = `
        <span class="toptract__rk">${String(i + 1).padStart(2, "0")}</span>
        <span class="toptract__body">
          <span class="toptract__nm">${t.cn || (isCountyMode() ? "County" : "Census tract")}</span>
          <span class="toptract__fips">${t.f || t.cf || "–"}</span>
        </span>
        <span class="toptract__v">${v != null ? (v * 100).toFixed(1) + "%" : "–"}</span>
      `;
      tEl.appendChild(li);
    });
  }

  // ---------------------------------------------------------------------
  // GEOGRAPHY DETAIL DRAWER
  // ---------------------------------------------------------------------
  function pinFeature(p) {
    STATE.pinnedFeature = p;
    ["tracts-outline-pinned", "counties-outline-pinned"].forEach(id => {
      if (map && map.getLayer(id)) map.setFilter(id, ["==", ["get", "f"], "__none__"]);
    });
    if (map && map.getLayer(activePinnedLayerId())) {
      map.setFilter(activePinnedLayerId(), ["==", ["get", "f"], p.f || "__none__"]);
    }
    openDrawer();
    refreshScenarioDrawer();
    if (isCountyMode()) ensureCountyStats();
    else ensureShap();
  }

  function unpinFeature() {
    STATE.pinnedFeature = null;
    STATE.scenarioAdjustedRisks = null;
    STATE.scenarioAdjustedShap = null;
    STATE.scenarioActiveLevers = null;
    ["tracts-outline-pinned", "counties-outline-pinned"].forEach(id => {
      if (map && map.getLayer(id)) map.setFilter(id, ["==", ["get", "f"], "__none__"]);
    });
    closeDrawer();
  }

  function openDrawer() {
    const dr = document.getElementById("drawer");
    if (!dr) return;
    dr.hidden = false;
    document.body.classList.add("is-drawer-open");
    window.dispatchEvent(new CustomEvent("drawer-layout-change"));
    // Force a frame to commit the hidden→visible state before transitioning.
    requestAnimationFrame(() => {
      dr.classList.add("is-open");
      dr.setAttribute("aria-hidden", "false");
      window.dispatchEvent(new CustomEvent("drawer-layout-change"));
      requestAnimationFrame(() => window.dispatchEvent(new CustomEvent("drawer-layout-change")));
    });
  }

  function closeDrawer() {
    const dr = document.getElementById("drawer");
    if (!dr) return;
    dr.classList.remove("is-open");
    dr.setAttribute("aria-hidden", "true");
    document.body.classList.remove("is-drawer-open");
    window.dispatchEvent(new CustomEvent("drawer-layout-change"));
    // After transition, hide for a11y. Reduced-motion: hide immediately.
    if (REDUCED) {
      dr.hidden = true;
      window.dispatchEvent(new CustomEvent("drawer-layout-change"));
    } else {
      setTimeout(() => {
        if (!dr.classList.contains("is-open")) {
          dr.hidden = true;
          window.dispatchEvent(new CustomEvent("drawer-layout-change"));
        }
      }, 360);
    }
  }

  // Format risk fraction → percent string with two decimals.
  const fmtPct = (v) => (v == null || isNaN(v)) ? "–" : (v * 100).toFixed(2) + "%";

  // ---------------------------------------------------------------------
  // SCENARIO LINEARIZATION FOR THE DRAWER
  //
  // When the user scrubs a slider AND a tract is pinned, we need a fast
  // (per-frame) approximation of how that tract's predictions and SHAP
  // top-N would shift under the scenario. Re-running TreeExplainer in the
  // browser is not feasible; instead we use a linear approximation:
  //
  //   For each lever L with slider z-score δ_L:
  //     Δshap_f ≈ -1 * polarity_L * importance_L * δ_L     (per feature f
  //                                                          tied to lever L)
  //     Δlogit  = Σ_L Δshap_f                              (sum of the shifts)
  //     new_p   = sigmoid(logit(p) + Δlogit · k)
  //
  // The polarity sign matches the scenario math: a higher slider value moves
  // the lever in the "more credit access" direction, which lowers risk for
  // protective levers like MDI reach. Removed-category dependence scores are
  // converted into a bounded logit sensitivity so every surface shares one unit.
  // ---------------------------------------------------------------------
  const SCENARIO_DAMP = 1.0;
  const SCENARIO_AP_TO_LOGIT = 10;
  const PROB_CLIP = 1e-4;

  function logit(p) {
    const c = Math.max(PROB_CLIP, Math.min(1 - PROB_CLIP, p));
    return Math.log(c / (1 - c));
  }
  function sigmoid(z) {
    if (z >= 0) {
      const e = Math.exp(-z);
      return 1 / (1 + e);
    } else {
      const e = Math.exp(z);
      return e / (1 + e);
    }
  }
  function shapToPp(risk, shapValue) {
    if (risk == null || risk === "null") return null;
    const p = Number(risk);
    const v = Number(shapValue);
    if (isNaN(p) || isNaN(v)) return null;
    return (p - sigmoid(logit(p) - v)) * 100;
  }
  function fmtPp(v) {
    const n = Number(v);
    if (n == null || isNaN(n)) return "–";
    const sign = n >= 0 ? "+" : "";
    return `${sign}${n.toFixed(1)} pp`;
  }
  // Same number, '%' suffix — the percentile-aware drivers panel reads "+4.2%"
  // as the per-tract risk delta from this driver. The unit is still
  // percentage points; '%' is a typographic preference, not a unit change.
  function fmtPpAsPct(v) {
    const n = Number(v);
    if (n == null || isNaN(n)) return "–";
    const sign = n >= 0 ? "+" : "";
    return `${sign}${n.toFixed(1)}%`;
  }

  // ─── Driver percentile + bell-curve helpers ─────────────────────────────
  // Wired against the new data files: feature_distributions, tract_features,
  // county_features. All optional — if absent the renderer falls back to
  // the legacy 3-column layout (no value, no bell, no percentile).

  function lookupRawValue(feat, geoid, isCounty) {
    const src = isCounty ? STATE.countyFeatures : STATE.tractFeatures;
    if (!src) return null;
    const rec = src[geoid];
    if (!rec || rec[feat] == null) return null;
    return Number(rec[feat]);
  }

  // Returns 0..100 (linear interp into the 99-quantile array). For
  // categorical features returns the cumulative share at-or-below the bucket.
  // `scope`: state abbreviation, or null for national.
  function featurePercentile(feat, rawValue, scope) {
    const dist = STATE.featureDistributions && STATE.featureDistributions[feat];
    if (!dist || rawValue == null || isNaN(rawValue)) return null;
    let arr = null;
    if (scope && dist.by_state && dist.by_state[scope]) arr = dist.by_state[scope];
    else if (dist.is_categorical) arr = dist.categories;
    else arr = dist.national;
    if (!arr || !arr.length) return null;
    if (dist.is_categorical) {
      // arr is [{value, share}] sorted ascending by value. Cumulative share
      // through the matching bucket. If raw doesn't match any, return null.
      let cum = 0;
      for (const c of arr) {
        cum += Number(c.share) || 0;
        if (Number(c.value) === Number(rawValue)) {
          return Math.max(0, Math.min(100, cum * 100));
        }
      }
      // Not an exact bucket match — interpolate between nearest brackets.
      const sorted = arr.slice().sort((a, b) => Number(a.value) - Number(b.value));
      let belowShare = 0;
      for (const c of sorted) {
        if (Number(c.value) < Number(rawValue)) belowShare += Number(c.share) || 0;
      }
      return Math.max(0, Math.min(100, belowShare * 100));
    }
    // Continuous: binary search into the 99 cutpoints (p1..p99).
    if (rawValue <= arr[0]) return 1;
    if (rawValue >= arr[arr.length - 1]) return 99;
    let lo = 0, hi = arr.length - 1;
    while (lo + 1 < hi) {
      const mid = (lo + hi) >> 1;
      if (rawValue >= arr[mid]) lo = mid; else hi = mid;
    }
    // arr[lo] <= rawValue < arr[hi]; lo is index 0..97 → p(lo+1)..p(hi+1).
    const span = arr[hi] - arr[lo] || 1e-9;
    const t = (rawValue - arr[lo]) / span;
    return (lo + 1) + t;  // returns a percentile in (1,99)
  }

  // For categorical / binary features the percentile (cumulative share) hides
  // the actual category. Map the raw value to a 0..100 position on the
  // category scale instead — matches RUCA's natural 1-10 reading and lets
  // binaries land cleanly at 0% or 100%. Returns null if no scale is known.
  function valuePositionForCategorical(feat, rawValue) {
    const dist = STATE.featureDistributions && STATE.featureDistributions[feat];
    if (!dist || !dist.is_categorical || !dist.categories || !dist.categories.length) return null;
    if (rawValue == null || isNaN(rawValue)) return null;
    const vals = dist.categories.map(c => Number(c.value));
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    if (max === min) return 50;  // single-category degenerate case
    const v = Math.max(min, Math.min(max, Number(rawValue)));
    return ((v - min) / (max - min)) * 100;
  }

  // Short label for the percentile column when the feature is categorical.
  // RUCA → just the integer code. Binary → "yes"/"no". Otherwise the int.
  function categoricalLabel(feat, value) {
    if (value == null || isNaN(value)) return "—";
    const v = Math.round(Number(value));
    if (feat === "ssbci_active" || feat === "ssbci_2_0_active" ||
        feat === "is_persistent_poverty" || feat === "mdi_active_in_county" ||
        feat === "is_rural") {
      return v ? "yes" : "no";
    }
    return String(v);
  }

  // Per-feature formatter for the raw-value column in the drivers panel.
  // Falls back to localized number for anything not specifically registered.
  function formatRawValue(feat, value) {
    if (value == null || isNaN(value)) return "—";
    const v = Number(value);
    // Currency
    if (feat === "median_hh_income" || feat === "median_household_income") {
      return v >= 1000 ? `$${Math.round(v / 1000)}k` : `$${Math.round(v)}`;
    }
    if (feat === "mean_loan_amount" || feat === "sum_loan_amount") {
      if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
      if (v >= 1e3) return `$${Math.round(v / 1e3)}k`;
      return `$${Math.round(v)}`;
    }
    // Percentages — already on 0..100 scale in the panels for these
    if (/^pct_/.test(feat) || feat === "approval_rate" || feat === "denial_rate" || feat === "unemployment_rate") {
      return `${v.toFixed(1)}%`;
    }
    // Distances
    if (/_miles$|_miles$|nearest.*branch_miles$|distance_to/.test(feat)) {
      return `${v.toFixed(1)} mi`;
    }
    // HHI (0..1 scale here) → 4-digit precision
    if (/_hhi(_|$)/.test(feat) || /_hhi$/.test(feat)) {
      return v.toFixed(3);
    }
    // RUCA — show code + plain-language band
    if (feat === "ruca_code") {
      const code = Math.round(v);
      const band = code <= 3 ? "urban" : code <= 6 ? "small town" : "rural";
      return `RUCA ${code} (${band})`;
    }
    // Binary flags
    if (feat === "ssbci_active" || feat === "is_persistent_poverty" ||
        feat === "mdi_active_in_county" || feat === "is_rural" ||
        feat === "ssbci_2_0_active") {
      return Math.round(v) ? "yes" : "no";
    }
    // Counts — integer with commas
    if (/^n_|^branches?_|^housing_units$|^population$|_count$|^cra_county_total/.test(feat)) {
      return Math.round(v).toLocaleString();
    }
    // Default
    return Math.abs(v) < 1 ? v.toFixed(3) : v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }

  // Returns 'drv-good' (green), 'drv-bad' (red), or 'drv-neu' (grey) based on
  // direction convention + percentile. See FEATURE_DIRECTION above.
  function colorClassForRow(feat, percentile) {
    if (percentile == null) return "drv-neu";
    const dir = FEATURE_DIRECTION[feat] || "lower_is_worse";
    if (dir === "neutral") return "drv-neu";
    const above = percentile > 50;
    const below = percentile < 50;
    if (dir === "lower_is_worse") {
      if (below) return "drv-bad";
      if (above) return "drv-good";
    } else {  // higher_is_worse
      if (above) return "drv-bad";
      if (below) return "drv-good";
    }
    return "drv-neu";
  }

  // SVG sparkline: faint normal-curve silhouette + colored marker at percentile.
  function bellSvg(percentile, colorClass) {
    if (percentile == null) return "";
    const W = 80, H = 22, PAD = 6, R = 4.2;  // PAD ≥ R + stroke for clean edges
    const pts = [];
    for (let i = 0; i <= 24; i++) {
      const x = i / 24;
      const z = (x - 0.5) * 6;            // ±3σ across the box
      const y = Math.exp(-0.5 * z * z);   // standard normal, peak = 1
      pts.push([PAD + x * (W - 2 * PAD), H - 3 - y * (H - 6)]);
    }
    const path = "M" + pts.map(p => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join("L");
    let cx = PAD + (percentile / 100) * (W - 2 * PAD);
    cx = Math.max(R + 1, Math.min(W - R - 1, cx));
    const baseY = H - 3;
    return `
      <svg class="drawshap__bell" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">
        <path d="${path}" class="drawshap__bell-curve"/>
        <line x1="${PAD}" x2="${W - PAD}" y1="${baseY}" y2="${baseY}" class="drawshap__bell-axis"/>
        <circle cx="${cx.toFixed(1)}" cy="${baseY - 1}" r="${R}" class="drawshap__bell-dot ${colorClass}"/>
      </svg>
    `;
  }

  // Categorical analog — flat axis with the dot at value/max position.
  function bucketSvg(percentile, colorClass) {
    if (percentile == null) return "";
    const W = 80, H = 22, PAD = 6, R = 4.2;
    let cx = PAD + (percentile / 100) * (W - 2 * PAD);
    cx = Math.max(R + 1, Math.min(W - R - 1, cx));
    const baseY = H / 2;
    return `
      <svg class="drawshap__bell" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">
        <line x1="${PAD}" x2="${W - PAD}" y1="${baseY}" y2="${baseY}" class="drawshap__bell-axis"/>
        <circle cx="${cx.toFixed(1)}" cy="${baseY}" r="${R}" class="drawshap__bell-dot ${colorClass}"/>
      </svg>
    `;
  }


  // List of {label, z} for the plain-language scenario note in the drawer.
  function activeLeversForNote() {
    const out = [];
    LEVERS.forEach(l => {
      const z = STATE.sliderShifts[l.key] || 0;
      if (Math.abs(z) < 0.05) return;
      const az = Math.abs(z);
      let descriptor;
      if (az >= 1.5) descriptor = `far ${z > 0 ? "above" : "below"} average`;
      else if (az >= 0.75) descriptor = `well ${z > 0 ? "above" : "below"} average`;
      else if (az >= 0.25) descriptor = `slightly ${z > 0 ? "above" : "below"} average`;
      else descriptor = `near average`;
      out.push({ label: l.label, descriptor, z });
    });
    return out;
  }

  function totalLeverImportance() {
    if (!STATE.feat) return 1;
    const total = LEVERS.reduce((sum, l) => {
      const fs = STATE.feat[l.key];
      return sum + (fs ? (fs.importance || 0) : 0);
    }, 0);
    return total || 1;
  }

  function leverGroupImportance(lever) {
    if (!STATE.feat) return 0;
    return LEVERS
      .filter(l => l.group === lever.group)
      .reduce((sum, l) => {
        const fs = STATE.feat[l.key];
        return sum + (fs ? (fs.importance || 0) : 0);
      }, 0);
  }

  function scenarioLeverEffect(lever, z = STATE.sliderShifts[lever.key] || 0, horizon = STATE.activeHorizon) {
    if (!STATE.feat || Math.abs(z) < 1e-6) return 0;
    const fs = STATE.feat[lever.key];
    if (!fs) return 0;

    const groupImp = leverGroupImportance(lever);
    const featureShare = groupImp > 0 ? (fs.importance || 0) / groupImp : 1;
    const ablImp = abImpactByGroup(horizon, lever.group);
    const apDrop = ablImp ? Math.max(0, -1 * (Number(ablImp.delta_ap) || 0)) : 0;
    const fallback = Math.min(0.04, ((fs.importance || 0) / totalLeverImportance()) * 0.16);
    const groupStrength = apDrop > 0.005
      ? Math.min(0.42, apDrop * SCENARIO_AP_TO_LOGIT)
      : fallback;

    return -1 * lever.polarity * z * groupStrength * featureShare * SCENARIO_DAMP;
  }

  function scenarioLogitEffect(model = STATE.activeModel) {
    const raw = LEVERS.reduce((sum, l) => sum + scenarioLeverEffect(l), 0);
    return model === "m2" ? raw : raw * 0.4;
  }

  function applyScenarioToRisk(base, model = STATE.activeModel) {
    if (base == null || isNaN(base)) return null;
    return sigmoid(logit(base) + scenarioLogitEffect(model));
  }

  function scenarioRiskExpr(prop, effect) {
    const oddsMultiplier = Math.exp(effect);
    return [
      "let", "p", ["max", 0.000001, ["min", 0.999999, ["get", prop]]],
      ["let", "odds", ["/", ["var", "p"], ["-", 1, ["var", "p"]]],
        ["/",
          ["*", ["var", "odds"], oddsMultiplier],
          ["+", 1, ["*", ["var", "odds"], oddsMultiplier]]
        ]
      ]
    ];
  }

  function scenarioLeverSummary(lever) {
    const horizon = STATE.activeHorizon;
    const base = 0.10;
    const farRightEffect = scenarioLeverEffect(lever, 2, horizon);
    const farRightRisk = sigmoid(logit(base) + farRightEffect);
    const deltaPp = (farRightRisk - base) * 100;
    const ablImp = abImpactByGroup(horizon, lever.group);
    const dAp = ablImp ? Number(ablImp.delta_ap) : null;
    const dir = deltaPp >= 0 ? "increases" : "decreases";
    const strength = Math.abs(deltaPp) >= 2 ? "clear" : (Math.abs(deltaPp) >= 0.75 ? "modest" : "small");
    const dependencyText = dAp == null
      ? "No category-dependence score is available for this horizon."
      : (dAp < -0.01
        ? "The model depends on this category at this horizon."
        : "The model only weakly depends on this category at this horizon.");
    return {
      deltaPp,
      row: `${HZ_LABEL[horizon]} sensitivity: far right ${dir} Influenceable risk by about ${Math.abs(deltaPp).toFixed(2)} percentage points from a 10% baseline (${strength}).`,
      tip: `At the ${HZ_LABEL[horizon]}, far right ${dir} Influenceable risk by about ${Math.abs(deltaPp).toFixed(2)} percentage points from a 10% baseline. Diagnostic uses a damped version. ${dependencyText}`,
    };
  }

  // Read active slider deltas and produce per-feature logit shifts.
  function leverShiftsByFeature() {
    const shifts = {};
    LEVERS.forEach(l => {
      const z = STATE.sliderShifts[l.key] || 0;
      if (Math.abs(z) < 1e-6) return;
      const dShap = scenarioLeverEffect(l, z);
      shifts[l.key] = (shifts[l.key] || 0) + dShap;
    });
    return shifts;
  }

  function driverFeature(row) {
    return Array.isArray(row) ? row[0] : (row && (row.feature || row.f));
  }

  function driverValue(row) {
    if (Array.isArray(row)) return Number(row[1]) || 0;
    return Number(row && (row.value ?? row.shap ?? row.v)) || 0;
  }

  function countyDetailForPinned() {
    const p = STATE.pinnedFeature;
    if (!isCountyMode() || !p || !STATE.countyStats) return null;
    return STATE.countyStats[p.f || p.cf] || null;
  }

  function baseDriverListForKey(key) {
    const p = STATE.pinnedFeature;
    if (!p) return null;
    if (isCountyMode()) {
      const countyDetail = countyDetailForPinned();
      return countyDetail && countyDetail.drivers ? countyDetail.drivers[key] : null;
    }
    const entry = STATE.shap && p.f ? STATE.shap[p.f] : null;
    return entry && entry[key] ? entry[key] : null;
  }

  function adjustedDriverLists(dShapByFeat) {
    const out = {};
    ["m1_h3", "m1_h6", "m2_h3", "m2_h6"].forEach(key => {
      const base = baseDriverListForKey(key);
      if (!base) { out[key] = null; return; }
      const isM2 = key.startsWith("m2_");
      const adj = new Map();
      base.forEach(row => {
        const feat = driverFeature(row);
        if (!feat) return;
        adj.set(feat, driverValue(row));
      });
      Object.entries(dShapByFeat).forEach(([leverKey, dS]) => {
        const localD = isM2 ? dS : (dS * 0.4);
        const cur = adj.get(leverKey) || 0;
        adj.set(leverKey, cur + localD);
      });
      out[key] = [...adj.entries()]
        .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
        .slice(0, 8)
        .map(([f, v]) => [f, v]);
    });
    return out;
  }

  // Apply linearized scenario adjustment to the pinned geography's risks and SHAP.
  // Populates STATE.scenarioAdjustedRisks / scenarioAdjustedShap, or clears
  // them when the scenario is at baseline. Caller should renderDrawer() after.
  function applyScenarioToDrawer() {
    const p = STATE.pinnedFeature;
    if (!p) {
      STATE.scenarioAdjustedRisks = null;
      STATE.scenarioAdjustedShap = null;
      STATE.scenarioActiveLevers = null;
      return;
    }
    const anyShift = Object.values(STATE.sliderShifts).some(z => Math.abs(z) > 0.01);
    if (!anyShift) {
      STATE.scenarioAdjustedRisks = null;
      STATE.scenarioAdjustedShap = null;
      STATE.scenarioActiveLevers = null;
      return;
    }

    const dShapByFeat = leverShiftsByFeature();

    // 1) Adjusted risks per (model × horizon).
    const num = (v) => (v == null || v === "null") ? null : Number(v);
    const baseRisks = {
      m1_h3: num(p.m1_h3),
      m1_h6: num(p.m1_h6),
      m2_h3: num(p.m2_h3),
      m2_h6: num(p.m2_h6),
    };
    const adjRisks = {};
    Object.entries(baseRisks).forEach(([k, base]) => {
      if (base == null) { adjRisks[k] = null; return; }
      const isM2 = k.startsWith("m2_");
      adjRisks[k] = applyScenarioToRisk(base, isM2 ? "m2" : "m1");
    });
    STATE.scenarioAdjustedRisks = adjRisks;
    STATE.scenarioActiveLevers = activeLeversForNote();

    // 2) Adjusted SHAP top-N for the active (model × horizon).
    // We apply per-feature shifts to the existing top-8 list, then re-rank.
    // Features that aren't currently in the top-8 might come into the top-5
    // under a strong scenario, but we don't have their base SHAP value here
    // (it's not in shap_top.json). For completeness we synthesize an entry
    // for any lever feature whose adjusted magnitude exceeds the 5th-place
    // threshold; we treat its base as 0 and use Δshap as the new value.
    STATE.scenarioAdjustedShap = adjustedDriverLists(dShapByFeat);

  }

  function refreshScenarioDrawer() {
    if (!STATE.pinnedFeature) return;
    applyScenarioToDrawer();
    renderDrawer();
  }

  function renderDrawer() {
    const p = STATE.pinnedFeature;
    if (!p) return;

    const num = (v) => (v == null || v === "null") ? null : Number(v);
    const baseM1_h3 = num(p.m1_h3), baseM1_h6 = num(p.m1_h6);
    const baseM2_h3 = num(p.m2_h3), baseM2_h6 = num(p.m2_h6);
    // Active scenario override (linearized). Falls back to base values when
    // the scenario is at baseline (all sliders at 0).
    const adj = STATE.scenarioAdjustedRisks;
    const m1_h3 = adj && adj.m1_h3 != null ? adj.m1_h3 : baseM1_h3;
    const m1_h6 = adj && adj.m1_h6 != null ? adj.m1_h6 : baseM1_h6;
    const m2_h3 = adj && adj.m2_h3 != null ? adj.m2_h3 : baseM2_h3;
    const m2_h6 = adj && adj.m2_h6 != null ? adj.m2_h6 : baseM2_h6;
    const m1r_h3 = num(p.m1r_h3), m1r_h6 = num(p.m1r_h6);
    const m2r_h3 = num(p.m2r_h3), m2r_h6 = num(p.m2r_h6);

    // Header — big heading is human-readable place name; FIPS is metadata.
    const cn = p.cn || "Unknown county";
    const stAbbr = p.st || "";
    const placeName = (stAbbr && !cn.endsWith(", " + stAbbr)) ? `${cn}, ${stAbbr}` : cn;
    document.getElementById("drawerFips").textContent = placeName;
    document.getElementById("drawerSub").textContent = isCountyMode()
      ? `County FIPS ${p.f || p.cf || "–"}`
      : `Census tract ${p.f || "–"}`;
    // Optional metadata line — show n_cra_lenders if it's in the properties.
    const metaEl = document.getElementById("drawerMeta");
    const countyDetail = isCountyMode() && STATE.countyStats ? STATE.countyStats[p.f || p.cf] : null;
    if (isCountyMode() && countyDetail) {
      const bits = [];
      if (countyDetail.n_tracts != null) bits.push(`${countyDetail.n_tracts.toLocaleString()} tracts`);
      if (countyDetail.population != null) bits.push(`${countyDetail.population.toLocaleString()} people`);
      if (countyDetail.weighting) bits.push(countyDetail.weighting.replace(/_/g, " "));
      metaEl.textContent = bits.join(" · ");
      metaEl.hidden = !bits.length;
    } else if (p.n_cra_lenders != null && p.n_cra_lenders !== "") {
      metaEl.textContent = `${p.n_cra_lenders} active CRA lenders in 2024`;
      metaEl.hidden = false;
    } else {
      metaEl.hidden = true;
    }

    // 2x2 grid
    const grid = document.getElementById("drawerGrid");
    grid.innerHTML = "";
    const cells = [
      { m: "m1", h: "h3", v: m1_h3, r: m1r_h3 },
      { m: "m1", h: "h6", v: m1_h6, r: m1r_h6 },
      { m: "m2", h: "h3", v: m2_h3, r: m2r_h3 },
      { m: "m2", h: "h6", v: m2_h6, r: m2r_h6 },
    ];
    const MODEL_NAME = { m1: "Diagnostic", m2: "Influenceable" };
    const YEAR_OF = { h3: "2027 forecast", h6: "2030 scenario" };
    cells.forEach(c => {
      const isActive = c.m === STATE.activeModel && c.h === STATE.activeHorizon;
      const div = document.createElement("div");
      div.className = `drawcell drawcell--${c.m}${isActive ? " is-active" : ""}`;
      // Plain-language percentile: "Higher risk than 79% of WY tracts" or
      // "Lower risk than 79%". Within-state rank reads more humanely as
      // "ahead of N% of state" rather than "21st %ile."
      let rankTxt = "–";
      if (c.r != null) {
        const above = Math.round(c.r);          // % of state's tracts THIS tract beats
        const below = 100 - above;               // % above this tract
        if (above >= 50) {
          rankTxt = `Top ${Math.max(1, below)}% in ${stAbbr || "state"}`;
        } else {
          rankTxt = `Bottom ${Math.max(1, above)}% in ${stAbbr || "state"}`;
        }
      }
      const barW = (c.r == null) ? 0 : Math.max(1, Math.min(100, c.r));
      const valTxt = (c.v == null) ? "–" : `${(c.v * 100).toFixed(1)}%`;
      div.innerHTML = `
        <div class="drawcell__head">${MODEL_NAME[c.m]} · ${YEAR_OF[c.h]}</div>
        <div class="drawcell__v">${valTxt}</div>
        <div class="drawcell__sub">predicted risk</div>
        <div class="drawcell__pct">${rankTxt}</div>
        <div class="drawcell__bar"><div class="drawcell__bar-fill" style="width: ${barW}%;"></div></div>
      `;
      grid.appendChild(div);
    });

    renderDivergenceBlock();
    renderCountyTopTracts(countyDetail);
    renderDrawerShap();
  }

  function renderCountyTopTracts(countyDetail) {
    const wrap = document.getElementById("drawerCountyTopWrap");
    const listEl = document.getElementById("drawerCountyTopTracts");
    if (!wrap || !listEl) return;
    listEl.innerHTML = "";
    if (!isCountyMode() || !countyDetail) {
      wrap.hidden = true;
      return;
    }
    const key = `${STATE.activeModel}_${STATE.activeHorizon}`;
    const rows = countyDetail.top_tracts && countyDetail.top_tracts[key] ? countyDetail.top_tracts[key] : [];
    if (!rows.length) {
      wrap.hidden = true;
      return;
    }
    rows.slice(0, 5).forEach((t, i) => {
      const v = t[key];
      const li = document.createElement("li");
      li.className = "toptract";
      li.innerHTML = `
        <span class="toptract__rk">${String(i + 1).padStart(2, "0")}</span>
        <span class="toptract__body">
          <span class="toptract__nm">${t.cn || "Census tract"}</span>
          <span class="toptract__fips">${t.f || "–"}</span>
        </span>
        <span class="toptract__v">${v != null ? (v * 100).toFixed(1) + "%" : "–"}</span>
      `;
      listEl.appendChild(li);
    });
    wrap.hidden = false;
  }

  // -------------------------------------------------------------------
  // Divergence explainer — surfaces a plain-language paragraph when
  // Model 1 (Diagnostic) and Model 2 (Influenceable) disagree about
  // the pinned tract's risk at the active horizon. Reads scenario-
  // adjusted m1/m2 when sliders are scrubbed; otherwise base values.
  // -------------------------------------------------------------------
  function divergenceCopy(m1, m2) {
    if (m1 >= 0.05 && m2 < 0.02) {
      return {
        headline: "Status-quo risk is higher than lending-environment risk",
        body: "Diagnostic flags the area's social and economic environment. Influenceable sees less lending-access fragility, so the available levers may not fully reach the risk.",
      };
    }
    if (m1 < 0.02 && m2 >= 0.05) {
      return {
        headline: "Lending-environment risk is higher than status-quo risk",
        body: "Diagnostic reads the broader context as lower risk. Influenceable sees weak branch access, mission-lender reach, lender depth, or related credit-access signals.",
      };
    }
    if (m1 >= 0.05 && m2 >= 0.05) {
      const higher = m2 > m1 ? "Influenceable" : "Diagnostic";
      return {
        headline: "Both lenses see elevated risk; they differ on how much",
        body: "Both lenses flag this place. The " + higher + " lens reads it higher, so compare the local drivers before treating the risk as one kind of problem.",
      };
    }
    if (m1 < 0.02 && m2 < 0.02) {
      return {
        headline: "Both lenses see this as low-risk overall",
        body: "The disagreement is small. This place is not where either lens sees the strongest pressure.",
      };
    }
    const higher = m2 > m1 ? "Influenceable" : "Diagnostic";
    return {
      headline: "The two lenses disagree on this neighborhood",
      body: "The " + higher + " lens reads this place as higher risk. Use the gap to separate status-quo pressure from lending-environment pressure.",
    };
  }

  function renderDivergenceBlock() {
    const wrap = document.getElementById("drawerDivergence");
    if (!wrap) return;
    const p = STATE.pinnedFeature;
    if (!p) { wrap.hidden = true; return; }

    const h = STATE.activeHorizon;
    const m1Key = "m1_" + h;
    const m2Key = "m2_" + h;

    // Defensive read: prefer scenario-adjusted m1/m2 when B1's scenario
    // hooks have populated them, otherwise fall back to the tract's base
    // values directly.
    const adj = STATE.scenarioAdjustedRisks;
    const num = (v) => (v == null || v === "null") ? null : Number(v);
    const m1 = num((adj && adj[m1Key] != null) ? adj[m1Key] : p[m1Key]);
    const m2 = num((adj && adj[m2Key] != null) ? adj[m2Key] : p[m2Key]);

    if (m1 == null || m2 == null || isNaN(m1) || isNaN(m2)) {
      wrap.hidden = true;
      return;
    }

    const absDiff = Math.abs(m1 - m2);
    const ratioHigh = (m1 > 0 && (m2 / m1) >= 3) || (m2 > 0 && (m1 / m2) >= 3);
    const triggers = absDiff >= 0.03 || ratioHigh;
    if (!triggers) {
      wrap.hidden = true;
      return;
    }

    const copy = divergenceCopy(m1, m2);
    const headEl = document.getElementById("drawerDivergenceHeadline");
    const bodyEl = document.getElementById("drawerDivergenceBody");
    if (headEl) headEl.textContent = copy.headline;
    if (bodyEl) bodyEl.textContent = copy.body;
    wrap.hidden = false;
  }

  function ordinal(n) {
    if (n == null || isNaN(n)) return "–";
    const s = ["th", "st", "nd", "rd"];
    const v = n % 100;
    return n + (s[(v - 20) % 10] || s[v] || s[0]);
  }

  function renderDrawerShap() {
    const wrap = document.getElementById("drawerShap");
    const hzLbl = document.getElementById("drawerShapHz");
    if (!wrap) return;
    const shapSection = wrap.closest(".drawer__sect");
    if (shapSection) shapSection.hidden = false;
    const m = STATE.activeModel;
    const h = STATE.activeHorizon;
    const MODEL_NAME = { m1: "Diagnostic", m2: "Influenceable" };
    const YEAR_OF = { h3: "2027 forecast", h6: "2030 scenario" };
    hzLbl.textContent = `${MODEL_NAME[m]} · ${YEAR_OF[h]}`;

    wrap.innerHTML = "";

    const countyMode = isCountyMode();
    if ((countyMode && STATE.countyStatsLoading) || (!countyMode && STATE.shapLoading)) {
      const li = document.createElement("li");
      li.className = "drawshap__empty";
      li.textContent = "Loading drivers…";
      wrap.appendChild(li);
      return;
    }
    if (countyMode && !STATE.countyStats) {
      const li = document.createElement("li");
      li.className = "drawshap__empty";
      li.textContent = STATE.countyStatsTried
        ? "Drivers not yet computed for this build."
        : "Drivers not yet loaded.";
      wrap.appendChild(li);
      return;
    }
    if (!countyMode && !STATE.shap) {
      const li = document.createElement("li");
      li.className = "drawshap__empty";
      li.textContent = STATE.shapTried
        ? "Drivers not yet computed for this build."
        : "Drivers not yet computed.";
      wrap.appendChild(li);
      return;
    }

    const key = `${m}_${h}`;
    const p = STATE.pinnedFeature || {};
    const num = (v) => (v == null || v === "null") ? null : Number(v);
    const adj = STATE.scenarioAdjustedRisks;
    const risk = adj && adj[key] != null ? adj[key] : num(p[key]);
    const list = (STATE.scenarioAdjustedShap && STATE.scenarioAdjustedShap[key])
      || baseDriverListForKey(key);

    if (!list || !list.length) {
      const li = document.createElement("li");
      li.className = "drawshap__empty";
      li.textContent = countyMode
        ? "Drivers not available for this county."
        : "Drivers not available for this tract.";
      wrap.appendChild(li);
      return;
    }

    // Cache stores top-8; we display top-5 with a render-time exclusion list
    // for any features deemed misleading for the policy audience.
    const RENDER_EXCLUDE = new Set(["has_hmda"]);
    const rows = list
      .map(row => {
        const feat = driverFeature(row);
        const rawValue = driverValue(row);
        const storedPp = !Array.isArray(row) && row && row.pp != null ? Number(row.pp) : null;
        const pp = (STATE.scenarioAdjustedShap && STATE.scenarioAdjustedShap[key])
          ? shapToPp(risk, rawValue)
          : (storedPp != null && !isNaN(storedPp) ? storedPp : shapToPp(risk, rawValue));
        return { feat, value: rawValue, pp };
      })
      .filter(row => row.feat && !RENDER_EXCLUDE.has(row.feat) && row.pp != null && !isNaN(row.pp))
      .sort((a, b) => Math.abs(b.pp) - Math.abs(a.pp));
    const top5 = rows.slice(0, 5);
    if (!top5.length) {
      const li = document.createElement("li");
      li.className = "drawshap__empty";
      li.textContent = countyMode
        ? "Drivers not available for this county."
        : "Drivers not available for this tract.";
      wrap.appendChild(li);
      return;
    }
    const maxAbs = Math.max(...top5.map(row => Math.abs(row.pp))) || 1e-6;

    // Distribution-aware path: when feature_distributions.json + per-geo
    // raw values are loaded, render the 5-column layout (name | value | bell |
    // pct | pp). Otherwise fall back to the legacy 3-column layout.
    const distOk = !!STATE.featureDistributions && !!(countyMode ? STATE.countyFeatures : STATE.tractFeatures);
    const geoid = countyMode ? (p.f || p.cf) : p.f;
    const scope = STATE.focusedState || null;

    top5.forEach(({ feat, pp }) => {
      const li = document.createElement("li");
      li.className = "drawshap";
      li.dataset.feat = feat;
      li.tabIndex = 0;
      const pretty = FEATURE_LABEL[feat] || feat.replace(/_/g, " ");

      if (!distOk) {
        // ---- Legacy 3-column fallback ----
        const isPos = pp >= 0;
        const widthPct = Math.max(4, (Math.abs(pp) / maxAbs) * 100);
        const arrow = isPos ? "▲" : "▼";
        li.classList.add("drawshap--legacy");
        li.innerHTML = `
          <span class="drawshap__nm">
            <span class="drawshap__arrow ${isPos ? "pos" : "neg"}" aria-hidden="true">${arrow}</span>
            ${pretty}
          </span>
          <span class="drawshap__bar"><span class="drawshap__bar-fill ${isPos ? "pos" : "neg"}" style="width:${widthPct}%;"></span></span>
          <span class="drawshap__v ${isPos ? "pos" : "neg"}">${fmtPp(pp)}</span>
        `;
      } else {
        // ---- Percentile-aware 5-column layout ----
        const rawValue = lookupRawValue(feat, geoid, countyMode);
        const distRec = STATE.featureDistributions[feat];
        const isCat = !!(distRec && distRec.is_categorical);
        // For continuous features: cumulative-distribution percentile.
        // For categoricals/binaries: position on the category value scale
        //   (e.g., RUCA=6 → 56% across a 1..10 scale, ssbci=1 → 100%).
        // The bell marker, color rule, and arrow direction all use the same
        // number — so a categorical row reads as "high RUCA = right side of
        // the scale = red (because higher_is_worse)" without computing a
        // misleading cumulative-share percentile.
        const pos = isCat
          ? valuePositionForCategorical(feat, rawValue)
          : featurePercentile(feat, rawValue, scope);
        const colorCls = colorClassForRow(feat, pos);
        let arrow = "·";
        if (pos != null) {
          if (pos > 50) arrow = "▲";
          else if (pos < 50) arrow = "▼";
        }
        const valueText = formatRawValue(feat, rawValue);
        let pctText;
        if (pos == null) {
          pctText = "—";
        } else if (isCat) {
          pctText = categoricalLabel(feat, rawValue);
        } else {
          pctText = scope ? `${ordinal(Math.round(pos))} in ${scope}` : ordinal(Math.round(pos));
        }
        const bell = isCat ? bucketSvg(pos, colorCls) : bellSvg(pos, colorCls);
        li.dataset.pct = pos == null ? "" : Math.round(pos);
        li.dataset.scope = scope || "national";
        li.dataset.cat = isCat ? "1" : "";
        li.innerHTML = `
          <span class="drawshap__nm">
            <span class="drawshap__arrow ${colorCls}" aria-hidden="true">${arrow}</span>
            ${pretty}
          </span>
          <span class="drawshap__val ${colorCls}">${valueText}</span>
          <span class="drawshap__bellwrap">${bell}</span>
          <span class="drawshap__pct ${colorCls}">${pctText}</span>
          <span class="drawshap__v ${colorCls}">${fmtPpAsPct(pp)}</span>
        `;
      }

      // Tooltip handlers — show feature description on hover/focus
      li.addEventListener("mouseenter", () => showFeatureTip(feat, li));
      li.addEventListener("mouseleave", () => hideFeatureTip());
      li.addEventListener("focus", () => showFeatureTip(feat, li));
      li.addEventListener("blur", () => hideFeatureTip());
      wrap.appendChild(li);
    });
  }

  // Feature tooltip — explains what each SHAP-listed feature is and how to read it.
  // When the row carries percentile/value data (5-column layout), prepend a
  // plain-language summary above the static feature description.
  function showFeatureTip(featKey, anchorEl) {
    const tip = document.getElementById("featTip");
    if (!tip) return;
    const desc = FEATURE_DESCRIPTION[featKey];
    const label = FEATURE_LABEL[featKey] || featKey.replace(/_/g, " ");
    const what = desc ? desc.what : "Feature definition not yet documented.";
    const read = desc ? desc.read : "";

    // Pull the percentile/value off the row's dataset so we don't recompute.
    const pctRaw = anchorEl && anchorEl.dataset ? anchorEl.dataset.pct : "";
    const pct = pctRaw === "" || pctRaw == null ? null : Number(pctRaw);
    const scope = anchorEl && anchorEl.dataset ? anchorEl.dataset.scope : "national";
    const isCat = !!(anchorEl && anchorEl.dataset && anchorEl.dataset.cat);
    const ppEl = anchorEl ? anchorEl.querySelector(".drawshap__v") : null;
    const valEl = anchorEl ? anchorEl.querySelector(".drawshap__val") : null;
    let summary = "";
    if (pct != null && !isNaN(pct) && valEl) {
      const dir = FEATURE_DIRECTION[featKey] || "lower_is_worse";
      const aboveBelow = pct > 50 ? "above-average" : (pct < 50 ? "below-average" : "exactly-average");
      const ppText = ppEl ? ppEl.textContent.trim() : "";
      const verb = ppText.startsWith("+") ? "raises" : (ppText.startsWith("-") || ppText.startsWith("−") ? "lowers" : "shifts");
      const horizonLabel = STATE.activeHorizon === "h6" ? "2030 scenario" : "2027 forecast";
      const scopeLabel = scope === "national" ? "" : ` in ${scope}`;
      const directionNote = dir === "neutral"
        ? ""
        : ` This ${aboveBelow} reading on this driver is `
          + ((dir === "lower_is_worse") === (pct > 50) ? "<b>better</b>" : "<b>worse</b>")
          + " than typical for this metric.";
      // Categorical/binary rows lead with the raw value, not a percentile.
      const lead = isCat
        ? `<b>${valEl.textContent.trim()}</b>${scopeLabel}.`
        : `<b>${valEl.textContent.trim()}</b> · ${ordinal(Math.round(pct))} percentile${scopeLabel}.`;
      summary = `
        <div class="featTip__summary">
          ${lead}
          ${verb.charAt(0).toUpperCase() + verb.slice(1)} the ${horizonLabel} by <b>${ppText}</b>.${directionNote}
        </div>
        <div class="featTip__rule"></div>
      `;
    }

    tip.innerHTML = `
      <div class="featTip__nm">${label}</div>
      <div class="featTip__rule"></div>
      ${summary}
      <div class="featTip__what"><span class="featTip__lbl">What it is</span>${what}</div>
      ${read ? `<div class="featTip__read"><span class="featTip__lbl">How to read it</span>${read}</div>` : ""}
      <div class="featTip__key mono">${featKey}</div>
    `;
    // Position to the RIGHT of the drawer row (drawer is at the left edge).
    const rect = anchorEl.getBoundingClientRect();
    tip.hidden = false;
    tip.style.opacity = "0";
    requestAnimationFrame(() => {
      const tipRect = tip.getBoundingClientRect();
      // Pin to the RIGHT of the anchor, vertically centered with the row.
      let left = rect.right + 12;
      let top = rect.top + rect.height / 2 - tipRect.height / 2;
      // Clamp to viewport — if tooltip would overflow right edge, flip to left.
      if (left + tipRect.width > window.innerWidth - 8) {
        const flipped = rect.left - tipRect.width - 12;
        left = flipped >= 8 ? flipped : window.innerWidth - tipRect.width - 8;
      }
      if (left < 8) left = 8;
      if (top < 8) top = 8;
      const bottomEdge = viewportBottomEdge();
      if (top + tipRect.height > bottomEdge) {
        top = bottomEdge - tipRect.height;
      }
      if (top < 8) top = 8;
      tip.style.left = `${left}px`;
      tip.style.top = `${top}px`;
      tip.style.opacity = "1";
    });
  }

  function hideFeatureTip() {
    const tip = document.getElementById("featTip");
    if (tip) {
      tip.style.opacity = "0";
      setTimeout(() => { if (tip.style.opacity === "0") tip.hidden = true; }, 150);
    }
  }

  // Lever tooltip — explains what each scenario slider represents,
  // what moving it does, and the honest model sensitivity.
  // Reuses the #featTip element so the visual matches the SHAP tooltip.
  function showLeverTip(leverKey, anchorEl) {
    const tip = document.getElementById("featTip");
    if (!tip) return;
    const c = LEVER_TOOLTIP_CONTENT[leverKey];
    if (!c) return;
    const lever = LEVERS.find(l => l.key === leverKey);
    const summary = lever ? scenarioLeverSummary(lever) : null;
    tip.innerHTML = `
      <div class="featTip__nm">${c.nm}</div>
      <div class="featTip__rule"></div>
      <div class="featTip__what"><span class="featTip__lbl">What it represents</span>${c.what}</div>
      <div class="featTip__read"><span class="featTip__lbl">What moving it does</span>${c.does}</div>
      <div class="featTip__impact"><span class="featTip__lbl">Modeled sensitivity</span>${summary ? summary.tip : c.note}</div>
      <div class="featTip__read"><span class="featTip__lbl">How to read it</span>${c.note}</div>
      <div class="featTip__key mono">${leverKey}</div>
    `;
    // Position to the LEFT of the slider row (sliders live on the right rail,
    // so the tooltip expands toward the map / left side of the viewport).
    const rect = anchorEl.getBoundingClientRect();
    tip.hidden = false;
    tip.style.opacity = "0";
    requestAnimationFrame(() => {
      const tipRect = tip.getBoundingClientRect();
      let left = rect.left - tipRect.width - 12;
      let top = rect.top + rect.height / 2 - tipRect.height / 2;
      // If overflowing the left edge, flip to the right of the anchor.
      if (left < 8) {
        const flipped = rect.right + 12;
        left = (flipped + tipRect.width <= window.innerWidth - 8)
          ? flipped
          : 8;
      }
      const bottomEdge = viewportBottomEdge();
      if (top + tipRect.height > bottomEdge) {
        top = bottomEdge - tipRect.height;
      }
      if (top < 8) top = 8;
      tip.style.left = `${left}px`;
      tip.style.top = `${top}px`;
      tip.style.opacity = "1";
    });
  }

  function hideLeverTip() {
    // Same DOM element as the feature tip, so reuse the hide path.
    hideFeatureTip();
  }

  // Lazy-load shap_top.json on first tract pin. ~5MB, so don't block boot.
  function ensureShap() {
    if (STATE.shap || STATE.shapLoading || STATE.shapTried) return;
    STATE.shapLoading = true;
    renderDrawerShap(); // show "Loading attribution…"
    fetchGzipJson("data/shap_top.json.gz")
      .then(j => j || fetchOptional("data/shap_top.json"))
      .then(j => {
        STATE.shap = j;
        STATE.shapLoading = false;
        STATE.shapTried = true;
        renderDrawerShap();
      })
      .catch(() => {
        STATE.shap = null;
        STATE.shapLoading = false;
        STATE.shapTried = true;
        renderDrawerShap();
      });
  }

  function bindDrawerClose() {
    const btn = document.getElementById("drawerClose");
    if (btn) btn.addEventListener("click", () => unpinFeature());
    // ESC key closes the drawer
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && STATE.pinnedFeature) {
        unpinFeature();
      }
    });
  }

  // ---------------------------------------------------------------------
  // TOGGLES
  // ---------------------------------------------------------------------
  function initToggles() {
    // Model
    document.querySelectorAll(".model").forEach(b => {
      b.addEventListener("click", () => {
        const m = b.dataset.model;
        if (m === STATE.activeModel) return;
        document.querySelectorAll(".model").forEach(x => {
          x.classList.toggle("is-active", x.dataset.model === m);
          x.setAttribute("aria-pressed", x.dataset.model === m ? "true" : "false");
        });
        STATE.activeModel = m;
        document.body.dataset.model = m;
        applyActive();
      });
    });

    // Horizon (map) — scoped to [data-horizon] to avoid picking up the meth switcher
    document.querySelectorAll(".horizon[data-horizon]").forEach(b => {
      b.addEventListener("click", () => {
        const h = b.dataset.horizon;
        if (h === STATE.activeHorizon) return;
        document.querySelectorAll(".horizon[data-horizon]").forEach(x => {
          x.classList.toggle("is-active", x.dataset.horizon === h);
          x.setAttribute("aria-pressed", x.dataset.horizon === h ? "true" : "false");
        });
        STATE.activeHorizon = h;
        document.body.dataset.horizon = h;
        // Keep meth switcher in sync until user has taken manual control
        if (!STATE.methHorizonLocked) {
          STATE.methHorizon = h;
          document.querySelectorAll(".horizon[data-meth-horizon]").forEach(x => {
            const on = x.dataset.methHorizon === h;
            x.classList.toggle("is-active", on);
            x.setAttribute("aria-pressed", String(on));
          });
          renderMethodology();
        }
        applyActive();
      });
    });

    // Methodology horizon switcher — independent from the map
    document.querySelectorAll(".horizon[data-meth-horizon]").forEach(b => {
      b.addEventListener("click", () => {
        const h = b.dataset.methHorizon;
        if (h === STATE.methHorizon) return;
        STATE.methHorizon = h;
        STATE.methHorizonLocked = true;
        document.querySelectorAll(".horizon[data-meth-horizon]").forEach(x => {
          const on = x.dataset.methHorizon === h;
          x.classList.toggle("is-active", on);
          x.setAttribute("aria-pressed", String(on));
        });
        renderMethodology();
      });
    });

    // Methodology model switcher — scoped to cards 02 + 02b only
    document.querySelectorAll("[data-meth-model]").forEach(b => {
      b.addEventListener("click", () => {
        const model = b.dataset.methModel;
        if (!model || model === STATE.methModel) return;
        STATE.methModel = model;
        syncMethodologyModelButtons();
        renderMethodology();
      });
    });

    // Geography
    document.querySelectorAll(".geo").forEach(b => {
      b.addEventListener("click", () => requestGeoMode(b.dataset.geo));
    });
  }

  function syncGeoButtons(g) {
    document.querySelectorAll(".geo").forEach(x => {
      x.classList.toggle("is-active", x.dataset.geo === g);
      x.setAttribute("aria-pressed", x.dataset.geo === g ? "true" : "false");
    });
  }

  function getMethodologyModelLabel(model = STATE.methModel) {
    return model === "influenceable" ? "Influenceable" : "Diagnostic";
  }

  function getMethodologyHorizonLabel(horizon = STATE.methHorizon) {
    return horizon === "h3" ? "2027 forecast" : "2030 scenario";
  }

  function syncMethodologyModelButtons() {
    document.querySelectorAll("[data-meth-model]").forEach(x => {
      const on = x.dataset.methModel === STATE.methModel;
      x.classList.toggle("is-active", on);
      x.setAttribute("aria-pressed", String(on));
    });
  }

  function getMethodologyModelPayload(bucket, model = STATE.methModel) {
    if (!bucket) return null;
    if (bucket[model]) return bucket[model];
    if (model === "influenceable" && (bucket.levers || bucket.ranking)) return bucket;
    return null;
  }

  function requestGeoMode(g) {
    if (!g || g === STATE.geoMode && !STATE.switching) return;
    STATE.pendingGeoMode = g;
    if (STATE.switching) {
      syncGeoButtons(g);
      return;
    }
    runPendingGeoSwitch();
  }

  function runPendingGeoSwitch() {
    const g = STATE.pendingGeoMode;
    STATE.pendingGeoMode = null;
    if (!g || g === STATE.geoMode) return;

    const token = STATE.geoSwitchToken + 1;
    STATE.geoSwitchToken = token;
    STATE.switching = true;
    document.body.classList.add("is-switching");

    STATE.geoMode = g;
    syncGeoButtons(g);
    document.body.dataset.geo = g;
    unpinFeature();

    const needsTracts = !isCountyMode() && !isTractSourceLoaded();
    if (needsTracts) {
      showMapLoading("Loading census tracts…");
      ensureTractLayers({ showLoading: false });
      syncGeoLayers({ keepCountyUntilTractsReady: true });
      applyActive();
      waitForTractSource((ready) => {
        if (STATE.geoSwitchToken !== token) return;
        syncGeoLayers({ keepCountyUntilTractsReady: !ready });
        finishGeoSwitch(token);
      });
      return;
    }

    syncGeoLayers();
    applyActive();
    finishGeoSwitch(token);
  }

  function finishGeoSwitch(token) {
    waitForMapIdle(() => {
      if (STATE.geoSwitchToken !== token) return;
      if (isCountyMode() || isTractSourceLoaded()) hideMapLoading();
      STATE.switching = false;
      document.body.classList.remove("is-switching");

      const next = STATE.pendingGeoMode;
      if (next && next !== STATE.geoMode) {
        runPendingGeoSwitch();
      } else {
        STATE.pendingGeoMode = null;
        syncGeoButtons(STATE.geoMode);
      }
    });
  }

  // Apply active (model, horizon) to the map and panels
  function applyActive() {
    document.getElementById("legendModelName").textContent =
      STATE.activeModel === "m1" ? "Diagnostic" : "Influenceable";
    if (map && map.getLayer(activeFillLayerId())) {
      map.setPaintProperty(activeFillLayerId(), "fill-color", computeColorExpr());
      map.setPaintProperty(activeFillLayerId(), "fill-opacity", [
        "case",
        ["==", ["get", riskProp()], null], 0.18,
        0.92
      ]);
    }
    syncHorizonAffordances();
    renderHeadline();
    renderTopStates();
    renderHistogram();
    renderSliders();      // re-render so each slider shows ablation impact at active horizon
    renderMethodology();
    renderFocusPanel();   // refresh focus panel for new (model, horizon)
    renderGeoCopy();
    refreshScenarioDrawer();   // refresh drawer for new (model, horizon)
  }

  function syncHorizonAffordances() {
    document.getElementById("horizonLabel").textContent =
      "Forecasting → " + HZ_YEAR[STATE.activeHorizon];
    document.getElementById("metaHorizon").textContent = HZ_META[STATE.activeHorizon];
    document.getElementById("legendHorizon").textContent = HZ_YEAR[STATE.activeHorizon] + " forecast";
    document.getElementById("railHorizon").textContent =
      STATE.activeHorizon === "h3" ? "2027 forecast" : "2030 scenario";
  }

  // ---------------------------------------------------------------------
  // HEADLINE NUMBERS (right rail)
  // ---------------------------------------------------------------------
  function renderHeadline() {
    if (!STATE.states) return;
    const m = STATE.activeModel;
    const h = STATE.activeHorizon;
    const key = `${m}_${h}`;
    const head = STATE.states.headline ? STATE.states.headline[key] : null;

    document.getElementById("railModelTag").textContent = m === "m1" ? "Lens 1" : "Lens 2";
    document.getElementById("railModelName").textContent =
      m === "m1" ? "Diagnostic" : "Influenceable";
    document.getElementById("railModelDesc").textContent =
      m === "m1"
        ? "Status-quo lens: demographics and environmental conditions show whether local context is driving credit risk."
        : "Lending-environment lens: movable credit-access variables show where risk is tied to things people can change.";

    if (!head) {
      document.getElementById("bigAuc").textContent = "–";
      document.getElementById("bigAp").textContent = "–";
      document.getElementById("bigSpread").textContent = "–";
      return;
    }
    tweenNumber(document.getElementById("bigAuc"), head.mean_auc, 3, 1.0);
    tweenNumber(document.getElementById("bigAp"), head.mean_ap, 3, 1.0);
    document.getElementById("bigSpread").textContent =
      "± " + (head.std_auc != null ? head.std_auc.toFixed(3) : "–");
  }

  function tweenNumber(el, target, decimals = 3, scale = 1.0) {
    if (target == null || isNaN(target)) {
      el.textContent = "–";
      return;
    }
    if (REDUCED) {
      el.textContent = (target * scale).toFixed(decimals);
      return;
    }
    const start = parseFloat(el.dataset.v || "0");
    const t0 = performance.now();
    const dur = 350;
    const tick = (now) => {
      const t = Math.min(1, (now - t0) / dur);
      const eased = 1 - Math.pow(1 - t, 4);
      const v = start + (target - start) * eased;
      el.textContent = (v * scale).toFixed(decimals);
      if (t < 1) requestAnimationFrame(tick);
      else el.dataset.v = String(target);
    };
    requestAnimationFrame(tick);
  }

  // ---------------------------------------------------------------------
  // TOP STATES (summary mode) — uses per-state stats at active (m, h)
  // ---------------------------------------------------------------------
  function renderTopStates() {
    if (!STATE.states || !STATE.states.states) return;
    const m = STATE.activeModel;
    const h = STATE.activeHorizon;
    const meanK = geoMeanKey(m, h);
    const aucK = `auc_${m}_${h}`;

    const states = STATE.states.states.filter(s => s[meanK] != null);

    const top = [...states].sort((a, b) => b[meanK] - a[meanK]).slice(0, 6);
    const tEl = document.getElementById("topStates");
    tEl.innerHTML = "";
    top.forEach((s, i) => {
      const li = document.createElement("li");
      li.className = "topstate";
      li.innerHTML = `
        <span class="topstate__rk">${String(i + 1).padStart(2, "0")}</span>
        <span class="topstate__nm">${s.state}</span>
        <span class="topstate__v">${(s[meanK] * 100).toFixed(2)}%</span>
      `;
      li.addEventListener("click", () => flyToState(s.state));
      tEl.appendChild(li);
    });

    const weak = [...states].filter(s => s[aucK] != null)
      .sort((a, b) => a[aucK] - b[aucK]).slice(0, 5);
    const wEl = document.getElementById("weakStates");
    wEl.innerHTML = "";
    weak.forEach((s, i) => {
      const li = document.createElement("li");
      li.className = "topstate";
      li.innerHTML = `
        <span class="topstate__rk">${String(i + 1).padStart(2, "0")}</span>
        <span class="topstate__nm">${s.state}</span>
        <span class="topstate__v">AUC ${s[aucK].toFixed(3)}</span>
      `;
      li.addEventListener("click", () => flyToState(s.state));
      wEl.appendChild(li);
    });
  }

  // ---------------------------------------------------------------------
  // NATIONAL HISTOGRAM (summary mode)
  // ---------------------------------------------------------------------
  function renderHistogram() {
    const wrap = document.getElementById("natHisto");
    if (!wrap) return;
    wrap.innerHTML = "";
    if (!STATE.states) return;
    const key = `${STATE.activeModel}_${STATE.activeHorizon}`;
    const histStore = activeHistogramStore();
    const hist = histStore ? histStore[key] : null;
    if (!hist) return;
    const max = Math.max(...hist.counts) || 1;
    hist.counts.forEach((c, i) => {
      const bar = document.createElement("div");
      bar.className = "histo__bar";
      const lo = hist.edges[i], hi = hist.edges[i + 1];
      bar.dataset.c = `${(lo * 100).toFixed(0)}–${(hi * 100).toFixed(0)}%: ${c.toLocaleString()}`;
      bar.style.height = `${Math.max(2, (c / max) * 100)}%`;
      wrap.appendChild(bar);
    });
  }

  // ---------------------------------------------------------------------
  // SLIDERS
  // ---------------------------------------------------------------------
  function abImpactByGroup(horizon, groupKey) {
    const abl = STATE.abl[horizon];
    if (!abl || !abl.levers) return null;
    const row = abl.levers.find(l => l.key === groupKey);
    if (!row) return null;
    return { delta_ap: row.delta_ap, delta_auc: row.delta_auc };
  }

  function renderSliders() {
    const wrap = document.getElementById("sliders");
    if (!wrap) return;
    wrap.innerHTML = "";
    if (!STATE.feat) return;

    LEVERS.forEach(lev => {
      const fs = STATE.feat[lev.key];
      if (!fs) return;
      // Preserve any existing slider value on rerender
      const existingZ = STATE.sliderShifts[lev.key] || 0;
      const summary = scenarioLeverSummary(lev);
      const isReal = Math.abs(summary.deltaPp) >= 0.75;

      const div = document.createElement("div");
      div.className = "slider";
      div.dataset.lever = lev.key;
      div.innerHTML = `
        <div class="slider__head">
          <span class="slider__lbl">${lev.label}</span>
          <span class="slider__val" id="sval_${lev.key}">no change yet</span>
        </div>
        <input type="range" class="slider__rng"
               min="-2" max="2" step="0.05" value="${existingZ}"
               data-key="${lev.key}"
               aria-label="${lev.label} (move above or below average)">
        <div class="slider__foot">
          <span class="slider__abl ${isReal ? "is-real" : "is-decoy"}">
            ${summary.row}
          </span>
        </div>
      `;
      wrap.appendChild(div);

      const rng = div.querySelector("input");
      rng.addEventListener("input", (e) => onSliderInput(lev, parseFloat(e.target.value)));
      rng.addEventListener("change", (e) => onSliderInput(lev, parseFloat(e.target.value)));

      // Lever tooltip — only for sliders we have locked plain-language copy for.
      // Attach to the row CONTAINER (not the input), so dragging stays smooth.
      // Focus/blur on the inner input bubble up via focusin/focusout for keyboard a11y.
      if (LEVER_TOOLTIP_CONTENT[lev.key]) {
        div.addEventListener("mouseenter", () => showLeverTip(lev.key, div));
        div.addEventListener("mouseleave", () => hideLeverTip());
        div.addEventListener("focusin", () => showLeverTip(lev.key, div));
        div.addEventListener("focusout", () => hideLeverTip());
      }

      // Restore "shifted" display if user already moved this lever
      if (existingZ !== 0) onSliderInput(lev, existingZ, /*skipRecolor*/ true);
    });
  }

  function onSliderInput(lev, z, skipRecolor) {
    STATE.sliderShifts[lev.key] = z;

    const valEl = document.getElementById("sval_" + lev.key);
    const fs = STATE.feat[lev.key];
    if (!valEl || !fs) return;
    if (z === 0) {
      valEl.textContent = "no change yet";
      valEl.classList.remove("is-shifted");
    } else {
      const shifted = fs.mean + z * fs.std;
      const fmt = lev.unit === "share active"
        ? shifted.toFixed(2)
        : Math.abs(shifted) >= 100 ? shifted.toFixed(0)
          : Math.abs(shifted) >= 10 ? shifted.toFixed(1)
            : shifted.toFixed(2);
      // Plain-language descriptor for how far above/below the national average
      // we are, based on z-score magnitude. Drop greek letters entirely.
      const unitWord = lev.unit === "mi" ? "miles"
        : lev.unit === "branches" ? "branches"
          : lev.unit === "MDI within 25 mi" ? "MDIs within 25 mi"
            : lev.unit === "intermediaries" ? "microlenders"
              : lev.unit === "share active" ? "share active"
                : lev.unit;
      const az = Math.abs(z);
      const direction = z > 0 ? "above" : "below";
      let descriptor;
      if (az >= 1.5) descriptor = `far ${direction} the national average`;
      else if (az >= 0.75) descriptor = `well ${direction} average`;
      else if (az >= 0.25) descriptor = `slightly ${direction} average`;
      else descriptor = `near average`;
      valEl.textContent = `${fmt} ${unitWord}, ${descriptor}`;
      valEl.classList.add("is-shifted");
    }

    if (!skipRecolor) {
      refreshScenarioDrawer();
      scheduleRecolor();
      syncMode();
    }
  }

  function scheduleRecolor() {
    if (STATE.rafId) return;
    STATE.rafId = requestAnimationFrame(() => {
      STATE.rafId = null;
      if (map && map.getLayer(activeFillLayerId())) {
        map.setPaintProperty(activeFillLayerId(), "fill-color", computeColorExpr());
      }
      updateCounters();
    });
  }

  // Compute the active-model national mean risk shift from slider z-scores.
  function computeShift() {
    const baseline = baselineMeanRisk(STATE.activeModel, STATE.activeHorizon);
    const adjusted = applyScenarioToRisk(baseline, STATE.activeModel);
    return adjusted == null ? 0 : adjusted - baseline;
  }

  function computeColorExpr() {
    const ramp = ramps()[STATE.activeModel];
    const m = riskProp();
    const effect = scenarioLogitEffect(STATE.activeModel);
    if (Math.abs(effect) < 0.0005) {
      return rampToExpr();
    }
    const stops = ramp.flatMap(([t, c]) => [t, c]);
    return [
      "case",
      ["==", ["get", m], null], nullFillColor(),
      ["interpolate", ["linear"],
        scenarioRiskExpr(m, effect),
        ...stops
      ]
    ];
  }

  // ---------------------------------------------------------------------
  // SCENARIO COUNTERS
  // ---------------------------------------------------------------------
  function updateCounters() {
    // Use national means roughly inferred from headline AP / mean risk.
    // Keep simple closed-form: use ~0.04 baseline national mean risk.
    const m = STATE.activeModel;
    const h = STATE.activeHorizon;
    const baseline = baselineMeanRisk(m, h);
    const shift = computeShift();
    const N = activeFeatureCount();
    const baseHigh = N * baseline * 1.6;
    const scenarioHigh = N * Math.max(0, baseline + shift) * 1.6;
    const delta = scenarioHigh - baseHigh;

    const cntUp = document.getElementById("cntUp");
    const cntDn = document.getElementById("cntDn");
    const net = document.getElementById("netDelta");

    cntUp.textContent = (delta > 0 ? "+" : "") + Math.round(Math.max(0, delta)).toLocaleString();
    cntDn.textContent = (delta < 0 ? "−" : "") + Math.round(Math.max(0, -delta)).toLocaleString();
    net.textContent = `net ${delta >= 0 ? "+" : "−"}${Math.abs(Math.round(delta)).toLocaleString()} ${activeGeoMeta().plural} · estimated national shift ${(shift * 100 >= 0 ? "+" : "")}${(shift * 100).toFixed(2)} percentage points`;
  }

  function baselineMeanRisk(model, horizon) {
    if (!STATE.states || !STATE.states.states) return 0.04;
    const k = geoMeanKey(model, horizon);
    const vals = STATE.states.states.map(s => s[k]).filter(v => v != null);
    if (!vals.length) return 0.04;
    return vals.reduce((a, b) => a + b, 0) / vals.length;
  }

  function syncMode() {
    const anyShift = Object.values(STATE.sliderShifts).some(z => Math.abs(z) > 0.01);
    if (STATE.focusedState) {
      // Focus mode owns the panel — don't touch summary/scenario visibility here.
      // (renderFocusPanel ensures both are hidden when focused.)
      if (anyShift) updateCounters();
      return;
    }
    document.getElementById("modeSummary").hidden = anyShift;
    document.getElementById("modeScenario").hidden = !anyShift;
    if (anyShift) updateCounters();
  }

  // ---------------------------------------------------------------------
  // RESET
  // ---------------------------------------------------------------------
  function bindReset() {
    document.getElementById("resetBtn").addEventListener("click", () => {
      LEVERS.forEach(l => { STATE.sliderShifts[l.key] = 0; });
      document.querySelectorAll('input[type="range"].slider__rng').forEach(r => {
        r.value = 0;
        const k = r.dataset.key;
        const v = document.getElementById("sval_" + k);
        if (v) { v.textContent = "no change yet"; v.classList.remove("is-shifted"); }
      });
      if (map && map.getLayer(activeFillLayerId())) {
        map.setPaintProperty(activeFillLayerId(), "fill-color", computeColorExpr());
      }
      refreshScenarioDrawer();
      syncMode();
    });
  }

  // ---------------------------------------------------------------------
  // MAP RELOAD
  // ---------------------------------------------------------------------
  function bindMapReload() {
    const btn = document.getElementById('reloadMapBtn');
    if (!btn || !map) return;
    btn.addEventListener('click', () => {
      showMapLoading("Reloading map…");
      STATE.switching = false;
      STATE.pendingGeoMode = null;
      STATE.geoSwitchToken += 1;
      document.body.classList.remove('is-switching');
      unpinFeature();
      if (map.getSource('tracts')) {
        ['tracts-fill', 'tracts-outline-hover', 'tracts-outline-pinned', 'tracts-edge'].forEach(id => {
          if (map.getLayer(id)) map.removeLayer(id);
        });
        map.removeSource('tracts');
      }
      STATE.tractLayersReady = false;
      STATE.tractSourceReady = false;
      syncGeoLayers();
      applyActive();
      waitForMapIdle(() => {
        hideMapLoading();
        if (isCountyMode()) warmTractLayers();
      });
    });
  }

  // ---------------------------------------------------------------------
  // METHODOLOGY
  // ---------------------------------------------------------------------
  function renderMethodology() {
    if (!STATE.states) return;
    const head = STATE.states.headline || {};
    const h = STATE.methHorizon;
    const model = STATE.methModel;
    const modelLabel = getMethodologyModelLabel(model);
    const horizonLabel = getMethodologyHorizonLabel(h);
    syncMethodologyModelButtons();

    // Section 0 — horizon comparison KV
    const t_h3auc = document.getElementById("t_h3auc");
    const t_h6auc = document.getElementById("t_h6auc");
    if (t_h3auc) {
      const a = head.m2_h3, b = head.m2_h6;
      t_h3auc.textContent = a ? `Influenceable AUC ${a.mean_auc.toFixed(3)} · avg precision ${a.mean_ap.toFixed(3)}` : "–";
      t_h6auc.textContent = b ? `Influenceable AUC ${b.mean_auc.toFixed(3)} · avg precision ${b.mean_ap.toFixed(3)}` : "–";
    }

    // Section 1 — table at active horizon
    const m1k = head[`m1_${h}`];
    const m2k = head[`m2_${h}`];
    setText("t_hzlabel", h === "h3" ? "2027 forecast" : "2030 scenario");
    setText("t_m1auc", m1k && m1k.mean_auc != null ? m1k.mean_auc.toFixed(3) : "–");
    setText("t_m2auc", m2k && m2k.mean_auc != null ? m2k.mean_auc.toFixed(3) : "–");
    setText("t_m1ap", m1k && m1k.mean_ap != null ? m1k.mean_ap.toFixed(3) : "–");
    setText("t_m2ap", m2k && m2k.mean_ap != null ? m2k.mean_ap.toFixed(3) : "–");
    setText("t_m1folds", m1k && m1k.n_folds != null ? String(m1k.n_folds) : "–");
    setText("t_m2folds", m2k && m2k.n_folds != null ? String(m2k.n_folds) : "–");

    // Sections 2 + 3 horizon labels
    setText("ablHzLabel", horizonLabel);
    setText("ablModelLabel", modelLabel);
    setText("regHzLabel", horizonLabel);

    setText("topFeatHzLabel", horizonLabel);
    setText("topFeatModelLabel", modelLabel);

    renderAblation();
    renderTopFeats();
    renderRegime();
  }

  function renderTopFeats() {
    const wrap = document.getElementById("topFeats");
    if (!wrap) return;
    wrap.innerHTML = "";
    wrap.dataset.model = STATE.methModel;
    const modelLabel = getMethodologyModelLabel();
    const horizonLabel = getMethodologyHorizonLabel();
    wrap.setAttribute("aria-label", `${modelLabel} top features at ${horizonLabel}`);
    const pr = getMethodologyModelPayload(STATE.pruning && STATE.pruning[STATE.methHorizon]);
    if (!pr || !pr.ranking) {
      wrap.innerHTML = `<li class="topfeat" style="grid-template-columns:1fr"><span class="topfeat__nm">${modelLabel} top-features data unavailable for ${horizonLabel}.</span></li>`;
      return;
    }
    const top8 = pr.ranking.slice(0, 8);
    const max = Math.max(...top8.map(r => r.importance)) || 0.001;
    top8.forEach((r) => {
      const li = document.createElement("li");
      li.className = "topfeat";
      const pretty = FEAT_LBL[r.feature] || r.feature.replace(/_/g, " ");
      const isResid = /_resid$/.test(r.feature);
      const widthPct = Math.max(2, (r.importance / max) * 100);
      li.innerHTML = `
        <span class="topfeat__rk">${String(r.rank).padStart(2, "0")}</span>
        <span class="topfeat__nm">${pretty}${isResid ? ` <span class="mono">_resid</span>` : ""}</span>
        <span class="topfeat__bar"><span class="topfeat__bar-fill" style="width:${widthPct}%"></span></span>
        <span class="topfeat__v">${r.importance.toFixed(3)}</span>
      `;
      wrap.appendChild(li);
    });
  }

  function renderAblation() {
    const wrap = document.getElementById("ablChart");
    if (!wrap) return;
    wrap.innerHTML = "";
    wrap.dataset.model = STATE.methModel;
    const modelLabel = getMethodologyModelLabel();
    const horizonLabel = getMethodologyHorizonLabel();
    wrap.setAttribute("aria-label", `${modelLabel} category-dependence impact by feature group at ${horizonLabel}`);

    const abl = getMethodologyModelPayload(STATE.abl[STATE.methHorizon]);
    if (!abl || !abl.levers) {
      wrap.innerHTML = `
        <div class="ablempty">
          <div class="kicker">${modelLabel} data unavailable</div>
          <p>No category-dependence output is available for the ${horizonLabel} ${modelLabel.toLowerCase()} model yet. Rebuild the methodology JSONs after the upstream diagnostics finish.</p>
        </div>
      `;
      return;
    }

    const rows = [...abl.levers].sort((a, b) => a.delta_ap - b.delta_ap);
    const max = Math.max(...rows.map(r => Math.abs(r.delta_ap))) || 0.025;

    rows.forEach(r => {
      const isNeg = r.delta_ap < 0;
      const widthPct = Math.min(50, (Math.abs(r.delta_ap) / max) * 50);
      const row = document.createElement("div");
      row.className = "ablrow";
      row.innerHTML = `
        <div class="ablrow__lbl">${r.lever}</div>
        <div class="ablrow__bar">
          <div class="ablrow__bar-fill ${isNeg ? "neg" : "pos"}" style="width: ${widthPct}%;"></div>
        </div>
        <div class="ablrow__v ${isNeg ? "neg" : "pos"}">${r.delta_ap >= 0 ? "+" : ""}${r.delta_ap.toFixed(4)}</div>
      `;
      wrap.appendChild(row);
    });
  }

  const FEAT_LBL = {
    distance_to_nearest_bank_branch: "Branch distance",
    lender_hhi_tract_resid: "Lender concentration",
    branches_within_5mi: "Branches within 5 mi",
    pct_loans_from_top4_banks_resid: "Top-4 bank share",
    ssbci_active: "SSBCI active",
    pct_loans_from_credit_unions_resid: "Credit union share",
    top3_lender_share_tract_resid: "Top-3 lender share",
    nearest_mdi_branch_miles: "Nearest MDI branch",
    top1_lender_share_tract_resid: "Top-1 lender share",
    branch_closures_3y_within_10mi: "Branch closures (3y, 10mi)",
    mdi_branches_within_25mi: "MDI within 25 mi",
    mdi_branches_within_10mi: "MDI within 10 mi",
    mdi_active_in_county: "MDI active in county",
    pct_loans_under_250k_resid: "Loans under $250k",
    ssbci_program_count: "SSBCI program count",
    microloan_intermediary_within_25mi: "Microlender ecosystem",
    avg_loan_size_resid: "Average loan size",
    n_lenders_tract_resid: "Lender count",
    ruca_code: "RUCA code",
    housing_units: "Housing units",
    is_persistent_poverty: "Persistent poverty",
    population: "Population",
    median_hh_income: "Median household income",
    pct_black: "% Black",
    pct_minority: "% minority",
    is_rural: "Rural flag",
    fdic_deposit_hhi: "FDIC deposit concentration",
    fdic_deposit_hhi_chg3yr: "FDIC concentration change (3y)",
    fdic_top_bank_share_chg3yr: "Top-bank share change (3y)",
    pct_minority_resid: "% minority",
    median_household_income: "Median household income",
  };

  function renderRegime() {
    const wrap = document.getElementById("regimeRow");
    if (!wrap) return;
    wrap.innerHTML = "";
    const reg = STATE.regime[STATE.methHorizon];
    if (!reg) {
      wrap.innerHTML = `<div class="regime"><div class="regime__head"><span class="regime__lbl">COVID-split data pending</span></div></div>`;
      return;
    }

    const pre = (reg.rows || []).find(r => r.regime === "precovid");
    const post = (reg.rows || []).find(r => r.regime === "postcovid");
    const rows = [
      { ...pre, label: "Pre-COVID", top: reg.precovid_top, key: "precovid" },
      { ...post, label: "Post-COVID", top: reg.postcovid_top, key: "postcovid" },
    ];

    rows.forEach(r => {
      if (!r || r.auc == null) return;
      const top5 = (r.top || []).slice(0, 5);
      const div = document.createElement("div");
      div.className = "regime";
      div.dataset.r = r.key;
      div.innerHTML = `
        <div class="regime__head">
          <span class="regime__lbl">${r.label}</span>
          <span class="regime__yrs">${r.train_years} → ${r.test_years}</span>
        </div>
        <div class="regime__metrics">
          <div class="regime__m">
            <div class="regime__mv">${r.auc.toFixed(3)}</div>
            <div class="regime__ml">AUC</div>
          </div>
          <div class="regime__m">
            <div class="regime__mv">${r.ap.toFixed(3)}</div>
            <div class="regime__ml">Avg precision · ${r.ap_lift.toFixed(1)}× better than random</div>
          </div>
        </div>
        <div class="regime__top">
          <div class="regime__top-h">Top features the model reached for</div>
          <ol>
            ${top5.map(t => `
              <li>
                <span>${String(t.rank).padStart(2, "0")}</span>
                <b>${FEAT_LBL[t.feature] || t.feature.replace(/_/g, " ")}</b>
                <span>${t.importance.toFixed(3)}</span>
              </li>`).join("")}
          </ol>
        </div>
      `;
      wrap.appendChild(div);
    });
  }

})();
