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
    { key: "distance_to_nearest_bank_branch",
      label: "Bank branch distance",
      unit: "mi",
      group: "branch_access",
      polarity: -1,         // farther → MORE risk (we model -polarity*z*w)
      hint: "Median miles to nearest branch.",
    },
    { key: "branches_within_5mi",
      label: "Branches within 5 mi",
      unit: "branches",
      group: "branch_access",
      polarity: +1,
      hint: "More branches → less risk.",
    },
    { key: "mdi_branches_within_25mi",
      label: "MDI branch reach",
      unit: "MDI within 25 mi",
      group: "mdi_mission_lender",
      polarity: +1,
      hint: "Minority Depository Institution presence.",
    },
    { key: "ssbci_active",
      label: "SSBCI program coverage",
      unit: "share active",
      group: "ssbci_state_policy",
      polarity: +1,
      hint: "State Small Business Credit Initiative.",
    },
    { key: "microloan_intermediary_within_25mi",
      label: "Microlender ecosystem",
      unit: "intermediaries",
      group: "microlender_ecosystem",
      polarity: +1,
      hint: "SBA microloan intermediaries within 25 mi.",
    },
    { key: "lender_hhi_tract_resid",
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
  const HZ_DESC = {
    h3: "2027 forecast: trained on data through 2021, predicts state at 2024. Federal CRA reporting lags about 2 years, so this is the soonest-actionable forecast.",
    h6: "2030 scenario: trained on data through 2018, predicts state at 2024. Same target year, longer reach; a stress-test scenario for the 2030 horizon.",
  };
  const HZ_META = {
    h3: "2027 forecast · trained on data through 2021 · target 2024",
    h6: "2030 scenario · trained on data through 2018 · target 2024",
  };

  const GEO_META = {
    county: {
      label: "County",
      plural: "counties",
      detail: "County detail",
      intro: "One U.S. county, shown as a population-weighted rollup of the tracts inside it. Every prediction below estimates the chance this county becomes a small-business credit desert by the year shown.",
      forecastLabel: "Forecasts for this county",
      scenarioTitle: "Counties that crossed the high-risk line",
      histLabel: "Counties per risk decile",
      focusTopLabel: "Top 5 counties in state",
    },
    tract: {
      label: "Tract",
      plural: "tracts",
      detail: "Tract detail",
      intro: "One U.S. census tract, roughly a neighborhood of 4,000 people. Every prediction below estimates the chance this neighborhood becomes a small-business credit desert by the year shown.",
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
    focusedState: null,           // state abbreviation, or null
    sliderShifts: {},             // key → z-score shift
    feat: null,                   // feature_stats.json (flat: { key: {...} })
    states: null,                 // state_stats.json
    countyStats: null,            // county_stats.json
    bbox: null,                   // state_bbox.json
    abl: { h3: null, h6: null },  // ablation_h{3,6}.json
    pruning: { h3: null, h6: null },
    regime: { h3: null, h6: null },
    rafId: null,
    pinnedFeature: null,          // active geography properties object (or null)
    shap: null,                   // shap_top.json (lazily loaded)
    shapLoading: false,
    shapTried: false,
    // Scenario-linearized override values for the pinned feature's drawer.
    // Populated by applyScenarioToDrawer() whenever a slider is non-baseline.
    // Cleared (set null) when all sliders are at 0. When non-null, renderDrawer
    // and renderDrawerShap read from these instead of the raw feature properties.
    scenarioAdjustedRisks: null,  // { m1_h3, m1_h6, m2_h3, m2_h6 }
    scenarioAdjustedShap: null,   // { m1_h3: [[f,v],...], m1_h6:..., m2_h3:..., m2_h6:... }
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

  // Plain-English explainer for every feature that may show up in SHAP top-N.
  // Each entry: {what: definition, read: how to interpret}.
  const FEATURE_DESCRIPTION = {
    // ─── Round 7 / Model 2 — branch geography ────────────────────────────
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
    // ─── Round 7 — MDI / mission lender ──────────────────────────────────
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
    // ─── Round 7 — microlender / SBA ─────────────────────────────────────
    microloan_intermediary_within_25mi: {
      what: "Count of SBA-designated microlender intermediaries within 25 miles. These are non-bank organizations that disburse small SBA-backed loans.",
      read: "Higher means stronger small-loan ecosystem for tiny businesses.",
    },
    // ─── Round 7 — SSBCI state policy ────────────────────────────────────
    ssbci_active: {
      what: "1 if the State Small Business Credit Initiative (SSBCI) had an active program in this state-year; 0 otherwise. SSBCI 1.0 ran 2011–2017; SSBCI 2.0 runs 2022–present.",
      read: "1 means the federal-state program supporting small-business lenders was active.",
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
    // ─── Round 7 — residualized concentration / lender mix ───────────────
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
    // ─── Round 5 / Model 1 — ACS demographics ────────────────────────────
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
    // ─── Round 5 — FDIC concentration ────────────────────────────────────
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
    // ─── Round 5 — CRA churn / county concentration ──────────────────────
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
    // ─── Round 5 — HMDA mortgage features ────────────────────────────────
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

  // Even-distributed hues for state-tint overlay. Adjacency is good enough
  // since adjacent states will be ~7° apart in hue around the wheel.
  const STATE_TINT = (() => {
    const STATES = ["AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI",
                    "ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN",
                    "MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH",
                    "OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA",
                    "WV","WI","WY"];
    const out = {};
    STATES.forEach((st, i) => {
      const hue = (i / STATES.length) * 360;
      out[st] = `hsl(${hue.toFixed(1)}, 50%, 60%)`;
    });
    return out;
  })();
  const STATE_TINT_OPACITY = 0.22; // tested over dark navy + mustard/chartreuse


  // ---------------------------------------------------------------------
  // BASE MAP STYLE — dark, no labels on basemap, hairline borders
  // ---------------------------------------------------------------------
  const BASE_STYLE = {
    version: 8,
    glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
    sources: {
      carto: {
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
    },
    layers: [
      { id: "bg", type: "background", paint: { "background-color": "#040c13" } },
      { id: "base", type: "raster", source: "carto",
        paint: {
          "raster-opacity": 0.55,
          "raster-saturation": -0.4,
          "raster-contrast": -0.05,
          "raster-brightness-min": 0.02,
        }
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
    const histCaption = `${meta.histLabel} · active model × horizon. Long left tail = most ${meta.plural} read low risk; the rightmost bar is the high-risk shoulder.`;
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
    const ramp = RAMPS[STATE.activeModel];
    const m = riskProp();
    return [
      "case",
      ["==", ["get", m], null], "#0c1318",
      ["interpolate", ["linear"], ["get", m], ...ramp.flat()]
    ];
  };

  // Tint opacity expression: 0 for focused state, baseline for everyone else.
  const tintOpacityExpr = () => {
    if (!STATE.focusedState) {
      return STATE_TINT_OPACITY;
    }
    return [
      "case",
      ["==", ["get", "st"], STATE.focusedState], 0,
      STATE_TINT_OPACITY,
    ];
  };

  // ---------------------------------------------------------------------
  // BOOT
  // ---------------------------------------------------------------------
  document.addEventListener("DOMContentLoaded", boot);

  async function boot() {
    document.body.dataset.geo = "county";
    document.body.dataset.model = "m1";
    document.body.dataset.horizon = "h3";

    const [feat, states, countyStats, bbox, ablH3, ablH6, regH3, regH6, prH3, prH6] = await Promise.all([
      fetchOptional("data/feature_stats.json"),
      fetchOptional("data/state_stats.json"),
      fetchOptional("data/county_stats.json"),
      fetchOptional("data/state_bbox.json"),
      fetchOptional("data/ablation_h3.json"),
      fetchOptional("data/ablation_h6.json"),
      fetchOptional("data/regime_h3.json"),
      fetchOptional("data/regime_h6.json"),
      fetchOptional("data/pruning_h3.json"),
      fetchOptional("data/pruning_h6.json"),
    ]);
    STATE.feat    = feat;
    STATE.states  = states;
    STATE.countyStats = countyStats;
    STATE.bbox    = bbox;
    STATE.abl     = { h3: ablH3, h6: ablH6 };
    STATE.regime  = { h3: regH3, h6: regH6 };
    STATE.pruning = { h3: prH3, h6: prH6 };

    initMap();
    initToggles();
    renderHeadline();
    renderTopStates();
    renderHistogram();
    renderSliders();
    renderMethodology();
    bindReset();
    bindFocusClose();
    bindDrawerClose();
    syncHorizonAffordances();
    initAccordions();
    renderGeoCopy();
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
      map.addSource("tracts", {
        type: "geojson",
        data: "data/tracts.geojson",
        generateId: false,
        tolerance: 0.5,
      });
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
          "fill-color-transition": { duration: 500, delay: 0 },
        },
      });

      // Tract fill — base coloring on the active model × horizon
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
          "fill-color-transition": { duration: 500, delay: 0 },
        },
      });

      // State-tint overlay — peripheral spatial context (visible state boundaries
      // without a dedicated state polygon source). Sits ABOVE choropleth fill,
      // BELOW hover/edge lines. Hidden for the focused state.
      const stateTintMatch = ["match", ["get", "st"]];
      Object.entries(STATE_TINT).forEach(([st, color]) => {
        stateTintMatch.push(st, color);
      });
      stateTintMatch.push("hsl(0, 0%, 50%)"); // fallback
      map.addLayer({
        id: "state-tint-overlay",
        type: "fill",
        source: "tracts",
        paint: {
          "fill-color": stateTintMatch,
          "fill-opacity": tintOpacityExpr(),
          "fill-opacity-transition": { duration: 350, delay: 0 },
        },
      });

      // Tract outline — appears on hover only
      map.addLayer({
        id: "tracts-outline-hover",
        type: "line",
        source: "tracts",
        filter: ["==", ["get", "f"], "__none__"],
        paint: {
          "line-color": "#fc5855",
          "line-width": 1.2,
          "line-opacity": 1,
        },
      });

      // Pinned tract outline — visible only for the currently pinned tract.
      // Uses a layer-level filter so it disappears when nothing is pinned.
      map.addLayer({
        id: "tracts-outline-pinned",
        type: "line",
        source: "tracts",
        filter: ["==", ["get", "f"], "__none__"],
        paint: {
          "line-color": "#fc5855",
          "line-width": 1.5,
          "line-opacity": 1,
        },
      });

      // Faint hairline tract boundary at higher zoom
      map.addLayer({
        id: "tracts-edge",
        type: "line",
        source: "tracts",
        paint: {
          "line-color": "#0a1319",
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
      map.addLayer({
        id: "counties-outline-hover",
        type: "line",
        source: "counties",
        filter: ["==", ["get", "f"], "__none__"],
        paint: {
          "line-color": "#fc5855",
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
          "line-color": "#fc5855",
          "line-width": 1.8,
          "line-opacity": 1,
        },
      });
      map.addLayer({
        id: "counties-edge",
        type: "line",
        source: "counties",
        paint: {
          "line-color": "#0a1319",
          "line-width": 0.45,
          "line-opacity": 0.5,
        },
      });

      if (!REDUCED) {
        map.setPaintProperty("tracts-fill", "fill-opacity", [
          "case",
          ["==", ["get", riskProp()], null], 0.18,
          0.92
        ]);
      }

      syncGeoLayers();
      bindHover();
      bindClick();
    });
  }

  function syncGeoLayers() {
    if (!map) return;
    const countyVis = isCountyMode() ? "visible" : "none";
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
      ["state-tint-overlay", tractVis],
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
      const chip = document.getElementById("tipChip");
      if (chip) chip.style.background = STATE_TINT[p.st] || "hsl(0, 0%, 50%)";

      // Active row vs other row
      const active = STATE.activeModel;
      const other  = active === "m1" ? "m2" : "m1";
      const labels = { m1: "Diagnostic", m2: "Influenceable" };

      const aRow = document.getElementById("tipRowActive");
      const oRow = document.getElementById("tipRowOther");
      aRow.classList.remove("is-h3", "is-h6");
      aRow.classList.add(`is-${STATE.activeHorizon}`);

      document.getElementById("tipDotActive").className = "tip__dot tip__dot--" + active;
      document.getElementById("tipDotOther").className  = "tip__dot tip__dot--" + other;
      document.getElementById("tipLActive").textContent = labels[active];
      document.getElementById("tipLOther").textContent  = labels[other];

      const vals = { m1: { h3: m1_h3, h6: m1_h6 }, m2: { h3: m2_h3, h6: m2_h6 } };
      document.getElementById("tipActive_h3").textContent = fmt(vals[active].h3);
      document.getElementById("tipActive_h6").textContent = fmt(vals[active].h6);
      document.getElementById("tipOther_h3").textContent  = fmt(vals[other].h3);
      document.getElementById("tipOther_h6").textContent  = fmt(vals[other].h6);

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
      if (tx + w > innerWidth - 8)  tx = x - w - 16;
      if (ty + h > innerHeight - 8) ty = y - h - 16;
      tip.style.left = tx + "px";
      tip.style.top  = ty + "px";
      map.getCanvas().style.cursor = "crosshair";
    });

    map.on("mouseleave", fillLayerId, () => {
      if (fillLayerId !== activeFillLayerId()) return;
      resetHover();
    });
  }

  function bindHover() {
    bindHoverForLayer("counties-fill", "counties-outline-hover");
    bindHoverForLayer("tracts-fill", "tracts-outline-hover");
  }

  function bindClick() {
    const bindClickForLayer = (fillLayerId) => map.on("click", fillLayerId, (e) => {
      if (fillLayerId !== activeFillLayerId()) return;
      if (!e.features || !e.features.length) return;
      const p = e.features[0].properties;
      // Toggle pin: click same geography again closes the drawer.
      if (STATE.pinnedFeature && STATE.pinnedFeature.f === p.f) {
        unpinFeature();
      } else {
        pinFeature(p);
      }
    });
    bindClickForLayer("counties-fill");
    bindClickForLayer("tracts-fill");
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
    if (map && map.getLayer("state-tint-overlay")) {
      map.setPaintProperty("state-tint-overlay", "fill-opacity", tintOpacityExpr());
    }
    renderFocusPanel();
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
    const focusEl  = document.getElementById("modeFocus");
    const sumEl    = document.getElementById("modeSummary");
    const scenEl   = document.getElementById("modeScenario");
    const anyShift = Object.values(STATE.sliderShifts).some(z => Math.abs(z) > 0.01);

    if (!STATE.focusedState) {
      if (focusEl) focusEl.hidden = true;
      // restore the appropriate non-focus mode
      if (sumEl)  sumEl.hidden  = anyShift;
      if (scenEl) scenEl.hidden = !anyShift;
      return;
    }
    // Focused: hide both summary + scenario, show focus
    if (sumEl)  sumEl.hidden  = true;
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
    if (!isCountyMode()) ensureShap();   // lazy-load SHAP attribution on first tract pin
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
    // Force a frame to commit the hidden→visible state before transitioning.
    requestAnimationFrame(() => {
      dr.classList.add("is-open");
      dr.setAttribute("aria-hidden", "false");
    });
  }

  function closeDrawer() {
    const dr = document.getElementById("drawer");
    if (!dr) return;
    dr.classList.remove("is-open");
    dr.setAttribute("aria-hidden", "true");
    document.body.classList.remove("is-drawer-open");
    // After transition, hide for a11y. Reduced-motion: hide immediately.
    if (REDUCED) {
      dr.hidden = true;
    } else {
      setTimeout(() => {
        if (!dr.classList.contains("is-open")) dr.hidden = true;
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

  // Apply linearized scenario adjustment to the pinned tract's risks and SHAP.
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

    if (isCountyMode()) {
      STATE.scenarioAdjustedShap = null;
      return;
    }

    // 2) Adjusted SHAP top-N for the active (model × horizon).
    // We apply per-feature shifts to the existing top-8 list, then re-rank.
    // Features that aren't currently in the top-8 might come into the top-5
    // under a strong scenario, but we don't have their base SHAP value here
    // (it's not in shap_top.json). For completeness we synthesize an entry
    // for any lever feature whose adjusted magnitude exceeds the 5th-place
    // threshold; we treat its base as 0 and use Δshap as the new value.
    if (STATE.shap) {
      const fips = p.f;
      const entry = STATE.shap[fips];
      const adjShap = {};
      ["m1_h3", "m1_h6", "m2_h3", "m2_h6"].forEach(key => {
        const base = entry && entry[key] ? entry[key] : null;
        if (!base) { adjShap[key] = null; return; }
        const isM2 = key.startsWith("m2_");
        // Build a map of feature → adjusted SHAP value.
        const adj = new Map();
        base.forEach(([feat, val]) => {
          adj.set(feat, Number(val) || 0);
        });
        Object.entries(dShapByFeat).forEach(([leverKey, dS]) => {
          // Apply with same model dampening as the risk calc.
          const localD = isM2 ? dS : (dS * 0.4);
          const cur = adj.get(leverKey) || 0;
          adj.set(leverKey, cur + localD);
        });
        // Sort by absolute value, take top-8.
        const sorted = [...adj.entries()]
          .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
          .slice(0, 8)
          .map(([f, v]) => [f, v]);
        adjShap[key] = sorted;
      });
      STATE.scenarioAdjustedShap = adjShap;
    } else {
      STATE.scenarioAdjustedShap = null;
    }

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
    const YEAR_OF    = { h3: "2027 forecast", h6: "2030 scenario" };
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
          rankTxt = `Higher risk than ${above}% of ${stAbbr || "state"} ${activeGeoMeta().plural}`;
        } else {
          rankTxt = `Lower risk than ${below}% of ${stAbbr || "state"} ${activeGeoMeta().plural}`;
        }
      }
      const barW = (c.r == null) ? 0 : Math.max(1, Math.min(100, c.r));
      const valTxt = (c.v == null) ? "–" : `${(c.v * 100).toFixed(1)}%`;
      div.innerHTML = `
        <div class="drawcell__head">${MODEL_NAME[c.m]} · ${YEAR_OF[c.h]}</div>
        <div class="drawcell__v">${valTxt}</div>
        <div class="drawcell__sub">chance of becoming a credit desert</div>
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
        headline: "The two lenses disagree, and the structural lens flags higher risk",
        body: "The Diagnostic lens reads this neighborhood as risky because of structural conditions, poverty, demographics, weak labor market. But the Influenceable lens, which only looks at the lending environment, sees a relatively healthy local market. Practical reading: this place has structural disadvantage, but credit access here is better than the demographic profile would predict.",
      };
    }
    if (m1 < 0.02 && m2 >= 0.05) {
      return {
        headline: "The two lenses disagree, and the lending-environment lens flags higher risk",
        body: "The Diagnostic lens reads this neighborhood as low-risk because the demographic profile looks ordinary. But the Influenceable lens sees a fragile lending environment: thin local lender depth, sparse mission-lender presence, or weakening branch access. Practical reading: this place's credit access could deteriorate faster than the demographics would suggest, which is exactly the kind of signal the Influenceable model is designed to surface.",
      };
    }
    if (m1 >= 0.05 && m2 >= 0.05) {
      const higher = m2 > m1 ? "Influenceable" : "Diagnostic";
      return {
        headline: "Both lenses see elevated risk; they differ on how much",
        body: "Both lenses flag this neighborhood as elevated risk. The " + higher + " lens reads it higher because the lending-environment signals here are weaker than what the demographic profile alone would predict. Local action on lending access could matter here.",
      };
    }
    if (m1 < 0.02 && m2 < 0.02) {
      return {
        headline: "Both lenses see this as low-risk overall",
        body: "Both lenses see this as low-risk overall. The small disagreement is not load-bearing; either model is fine for this neighborhood.",
      };
    }
    const higher = m2 > m1 ? "Influenceable" : "Diagnostic";
    return {
      headline: "The two lenses disagree on this neighborhood",
      body: "The " + higher + " lens reads this neighborhood as higher risk than the other lens does. The disagreement comes from one model seeing a signal the other does not, either structural disadvantage or lending-environment fragility. Read both numbers together rather than relying on one.",
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
    if (shapSection) shapSection.hidden = isCountyMode();
    if (isCountyMode()) return;
    const m = STATE.activeModel;
    const h = STATE.activeHorizon;
    const MODEL_NAME = { m1: "Diagnostic", m2: "Influenceable" };
    const YEAR_OF    = { h3: "2027 forecast", h6: "2030 scenario" };
    hzLbl.textContent = `${MODEL_NAME[m]} · ${YEAR_OF[h]}`;

    wrap.innerHTML = "";

    if (STATE.shapLoading) {
      const li = document.createElement("li");
      li.className = "drawshap__empty";
      li.textContent = "Loading drivers…";
      wrap.appendChild(li);
      return;
    }
    if (!STATE.shap) {
      const li = document.createElement("li");
      li.className = "drawshap__empty";
      li.textContent = STATE.shapTried
        ? "Drivers not yet computed for this build."
        : "Drivers not yet computed.";
      wrap.appendChild(li);
      return;
    }

    const fips = STATE.pinnedFeature && STATE.pinnedFeature.f;
    const entry = fips ? STATE.shap[fips] : null;
    const key = `${m}_${h}`;
    const list = entry && entry[key] ? entry[key] : null;

    if (!list || !list.length) {
      const li = document.createElement("li");
      li.className = "drawshap__empty";
      li.textContent = "Drivers not available for this tract.";
      wrap.appendChild(li);
      return;
    }

    // Cache stores top-8; we display top-5 with a render-time exclusion list
    // for any features deemed misleading for the policy audience.
    const RENDER_EXCLUDE = new Set(["has_hmda"]);
    const filtered = list.filter(([f, _]) => !RENDER_EXCLUDE.has(f));
    const top5 = filtered.slice(0, 5);
    const maxAbs = Math.max(...top5.map(([, v]) => Math.abs(Number(v) || 0))) || 1e-6;

    // Translate raw SHAP magnitude into plain-English tiers.
    // SHAP values here are log-odds; the strongest in our data top out around
    // 2.0. We bucket relative to maxAbs so the label scales with what's
    // currently visible, not an absolute scale the user has to interpret.
    const tierLabel = (absV) => {
      const r = absV / maxAbs;
      if (r >= 0.75) return "Strongly";
      if (r >= 0.40) return "Moderately";
      if (r >= 0.15) return "Slightly";
      return "Marginally";
    };

    top5.forEach(([feat, val]) => {
      const v = Number(val) || 0;
      const isPos = v >= 0;
      const widthPct = Math.max(4, (Math.abs(v) / maxAbs) * 100);
      const li = document.createElement("li");
      li.className = "drawshap";
      li.dataset.feat = feat;  // for tooltip binding
      li.tabIndex = 0;          // keyboard-focusable
      const pretty = FEATURE_LABEL[feat] || feat.replace(/_/g, " ");
      const tier = tierLabel(Math.abs(v));
      const direction = isPos ? "raises" : "lowers";
      const arrow = isPos ? "▲" : "▼";
      const phrase = `${tier} ${direction} risk`;
      li.innerHTML = `
        <span class="drawshap__nm">
          <span class="drawshap__arrow ${isPos ? "pos" : "neg"}" aria-hidden="true">${arrow}</span>
          ${pretty}
        </span>
        <span class="drawshap__bar"><span class="drawshap__bar-fill ${isPos ? "pos" : "neg"}" style="width:${widthPct}%;"></span></span>
        <span class="drawshap__v ${isPos ? "pos" : "neg"}">${phrase}</span>
      `;
      // Tooltip handlers — show feature description on hover/focus
      li.addEventListener("mouseenter", (e) => showFeatureTip(feat, li));
      li.addEventListener("mouseleave", () => hideFeatureTip());
      li.addEventListener("focus", () => showFeatureTip(feat, li));
      li.addEventListener("blur", () => hideFeatureTip());
      wrap.appendChild(li);
    });
  }

  // Feature tooltip — explains what each SHAP-listed feature is and how to read it.
  function showFeatureTip(featKey, anchorEl) {
    const tip = document.getElementById("featTip");
    if (!tip) return;
    const desc = FEATURE_DESCRIPTION[featKey];
    const label = FEATURE_LABEL[featKey] || featKey.replace(/_/g, " ");
    const what = desc ? desc.what : "Feature definition not yet documented.";
    const read = desc ? desc.read : "";
    tip.innerHTML = `
      <div class="featTip__nm">${label}</div>
      <div class="featTip__rule"></div>
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
      if (top + tipRect.height > window.innerHeight - 8) {
        top = window.innerHeight - tipRect.height - 8;
      }
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
      if (top < 8) top = 8;
      if (top + tipRect.height > window.innerHeight - 8) {
        top = window.innerHeight - tipRect.height - 8;
      }
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
    fetch("data/shap_top.json")
      .then(r => r.ok ? r.json() : null)
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
          x.setAttribute("aria-selected", x.dataset.model === m ? "true" : "false");
        });
        STATE.activeModel = m;
        document.body.dataset.model = m;
        applyActive();
      });
    });

    // Horizon
    document.querySelectorAll(".horizon").forEach(b => {
      b.addEventListener("click", () => {
        const h = b.dataset.horizon;
        if (h === STATE.activeHorizon) return;
        document.querySelectorAll(".horizon").forEach(x => {
          x.classList.toggle("is-active", x.dataset.horizon === h);
          x.setAttribute("aria-selected", x.dataset.horizon === h ? "true" : "false");
        });
        STATE.activeHorizon = h;
        document.body.dataset.horizon = h;
        applyActive();
      });
    });

    // Geography
    document.querySelectorAll(".geo").forEach(b => {
      b.addEventListener("click", () => {
        const g = b.dataset.geo;
        if (!g || g === STATE.geoMode) return;
        STATE.geoMode = g;
        document.querySelectorAll(".geo").forEach(x => {
          x.classList.toggle("is-active", x.dataset.geo === g);
          x.setAttribute("aria-selected", x.dataset.geo === g ? "true" : "false");
        });
        document.body.dataset.geo = g;
        unpinFeature();
        syncGeoLayers();
        applyActive();
      });
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
    document.getElementById("metaHorizon").textContent  = HZ_META[STATE.activeHorizon];
    document.getElementById("legendHorizon").textContent = HZ_YEAR[STATE.activeHorizon] + " forecast";
    document.getElementById("railHorizon").textContent =
      STATE.activeHorizon === "h3" ? "2027 forecast" : "2030 scenario";
    document.getElementById("railHorizonDesc").textContent = HZ_DESC[STATE.activeHorizon];
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
        ? "All 39 features. Round-5 champion. The strongest predictor of future credit deserts, but it leans on supply-side signal we can't move."
        : "Twenty influenceable features, residualized against demographics. A quieter forecast, but every signal in it is something policy could fund or build.";

    if (!head) {
      document.getElementById("bigAuc").textContent = "–";
      document.getElementById("bigAp").textContent  = "–";
      document.getElementById("bigSpread").textContent = "–";
      return;
    }
    tweenNumber(document.getElementById("bigAuc"), head.mean_auc, 3, 1.0);
    tweenNumber(document.getElementById("bigAp"),  head.mean_ap,  3, 1.0);
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
    const aucK  = `auc_${m}_${h}`;

    const states = STATE.states.states.filter(s => s[meanK] != null);

    const top = [...states].sort((a, b) => b[meanK] - a[meanK]).slice(0, 6);
    const tEl = document.getElementById("topStates");
    tEl.innerHTML = "";
    top.forEach((s, i) => {
      const li = document.createElement("li");
      li.className = "topstate";
      li.innerHTML = `
        <span class="topstate__rk">${String(i+1).padStart(2,"0")}</span>
        <span class="topstate__nm">${s.state}</span>
        <span class="topstate__v">${(s[meanK]*100).toFixed(2)}%</span>
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
        <span class="topstate__rk">${String(i+1).padStart(2,"0")}</span>
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
      bar.dataset.c = `${(lo*100).toFixed(0)}–${(hi*100).toFixed(0)}%: ${c.toLocaleString()}`;
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
      rng.addEventListener("input",  (e) => onSliderInput(lev, parseFloat(e.target.value)));
      rng.addEventListener("change", (e) => onSliderInput(lev, parseFloat(e.target.value)));

      // Lever tooltip — only for sliders we have locked plain-language copy for.
      // Attach to the row CONTAINER (not the input), so dragging stays smooth.
      // Focus/blur on the inner input bubble up via focusin/focusout for keyboard a11y.
      if (LEVER_TOOLTIP_CONTENT[lev.key]) {
        div.addEventListener("mouseenter", () => showLeverTip(lev.key, div));
        div.addEventListener("mouseleave", () => hideLeverTip());
        div.addEventListener("focusin",   () => showLeverTip(lev.key, div));
        div.addEventListener("focusout",  () => hideLeverTip());
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
        : Math.abs(shifted) >= 10  ? shifted.toFixed(1)
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
    const ramp = RAMPS[STATE.activeModel];
    const m = riskProp();
    const effect = scenarioLogitEffect(STATE.activeModel);
    if (Math.abs(effect) < 0.0005) {
      return rampToExpr();
    }
    const stops = ramp.flatMap(([t, c]) => [t, c]);
    return [
      "case",
      ["==", ["get", m], null], "#0c1318",
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
    const net   = document.getElementById("netDelta");

    cntUp.textContent = (delta > 0 ? "+" : "") + Math.round(Math.max(0,  delta)).toLocaleString();
    cntDn.textContent = (delta < 0 ? "−" : "") + Math.round(Math.max(0, -delta)).toLocaleString();
    net.textContent = `net ${delta >= 0 ? "+" : "−"}${Math.abs(Math.round(delta)).toLocaleString()} ${activeGeoMeta().plural} · estimated national shift ${(shift*100 >= 0?"+":"")}${(shift*100).toFixed(2)} percentage points`;
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
  // METHODOLOGY
  // ---------------------------------------------------------------------
  function renderMethodology() {
    if (!STATE.states) return;
    const head = STATE.states.headline || {};
    const h = STATE.activeHorizon;

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
    setText("t_m1ap",  m1k && m1k.mean_ap  != null ? m1k.mean_ap.toFixed(3)  : "–");
    setText("t_m2ap",  m2k && m2k.mean_ap  != null ? m2k.mean_ap.toFixed(3)  : "–");
    setText("t_m1folds", m1k && m1k.n_folds != null ? String(m1k.n_folds) : "–");
    setText("t_m2folds", m2k && m2k.n_folds != null ? String(m2k.n_folds) : "–");

    // Sections 2 + 3 horizon labels
    setText("ablHzLabel", h === "h3" ? "2027 forecast" : "2030 scenario");
    setText("regHzLabel", h === "h3" ? "2027 forecast" : "2030 scenario");

    setText("topFeatHzLabel", h === "h3" ? "2027 forecast" : "2030 scenario");

    renderAblation();
    renderTopFeats();
    renderRegime();
  }

  function renderTopFeats() {
    const wrap = document.getElementById("topFeats");
    if (!wrap) return;
    wrap.innerHTML = "";
    const pr = STATE.pruning && STATE.pruning[STATE.activeHorizon];
    if (!pr || !pr.ranking) {
      wrap.innerHTML = `<li class="topfeat" style="grid-template-columns:1fr"><span class="toptract__nm">Top-features data pending.</span></li>`;
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

    const abl = STATE.abl[STATE.activeHorizon];
    if (!abl || !abl.levers) {
      wrap.innerHTML = `
        <div class="ablempty">
          <div class="kicker">Category-dependence check pending</div>
          <p>The ${STATE.activeHorizon === "h3" ? "2027 forecast" : "2030 scenario"} category-dependence table is being regenerated. Reload after <span class="mono">build_dashboard_data.py</span> picks up the new scenario-weight output.</p>
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
    pct_minority_resid: "% minority",
    median_household_income: "Median household income",
  };

  function renderRegime() {
    const wrap = document.getElementById("regimeRow");
    if (!wrap) return;
    wrap.innerHTML = "";
    const reg = STATE.regime[STATE.activeHorizon];
    if (!reg) {
      wrap.innerHTML = `<div class="regime"><div class="regime__head"><span class="regime__lbl">COVID-split data pending</span></div></div>`;
      return;
    }

    const pre  = (reg.rows || []).find(r => r.regime === "precovid");
    const post = (reg.rows || []).find(r => r.regime === "postcovid");
    const rows = [
      { ...pre,  label: "Pre-COVID",  top: reg.precovid_top,  key: "precovid"  },
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
                <span>${String(t.rank).padStart(2,"0")}</span>
                <b>${FEAT_LBL[t.feature] || t.feature.replace(/_/g," ")}</b>
                <span>${t.importance.toFixed(3)}</span>
              </li>`).join("")}
          </ol>
        </div>
      `;
      wrap.appendChild(div);
    });
  }

})();
