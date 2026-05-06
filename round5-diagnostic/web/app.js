/* ==============================================================
   ROUND 5 · CREDIT-DESERT FORECAST — Dashboard interaction layer
   MapLibre GL JS · vanilla JS · masked filtering · single accent
   ============================================================== */

(() => {
  'use strict';

  // ---------- Constants ----------
  const STATE_NAME = {
    AL:'Alabama', AK:'Alaska', AZ:'Arizona', AR:'Arkansas', CA:'California',
    CO:'Colorado', CT:'Connecticut', DE:'Delaware', DC:'District of Columbia',
    FL:'Florida', GA:'Georgia', HI:'Hawaii', ID:'Idaho', IL:'Illinois',
    IN:'Indiana', IA:'Iowa', KS:'Kansas', KY:'Kentucky', LA:'Louisiana',
    ME:'Maine', MD:'Maryland', MA:'Massachusetts', MI:'Michigan', MN:'Minnesota',
    MS:'Mississippi', MO:'Missouri', MT:'Montana', NE:'Nebraska', NV:'Nevada',
    NH:'New Hampshire', NJ:'New Jersey', NM:'New Mexico', NY:'New York',
    NC:'North Carolina', ND:'North Dakota', OH:'Ohio', OK:'Oklahoma', OR:'Oregon',
    PA:'Pennsylvania', RI:'Rhode Island', SC:'South Carolina', SD:'South Dakota',
    TN:'Tennessee', TX:'Texas', UT:'Utah', VT:'Vermont', VA:'Virginia',
    WA:'Washington', WV:'West Virginia', WI:'Wisconsin', WY:'Wyoming',
  };

  const HEX = {
    bg:        '#262a30',  // matches OKLCH 0.18 0.005 240 in sRGB ~
    surface1:  '#2e3239',
    surface2:  '#383d46',
    rule:      '#494f5b',
    ruleStrong:'#5e6573',
    accent:    '#ec9c4f',  // ~ oklch(0.78 0.18 65)
    text:      '#f3f3f5',
    textMute:  '#6f7682',
    rampNo:    '#2c3037',  // no-data tracts
    // Stacked-tint colors: cool → warm → accent so layers visually nest.
    // Each is rendered at low opacity below the choropleth.
    tintState: '#3a4453',  // cool slate
    tintCounty:'#4d4438',  // warm earth
    tintPlace: '#6e4a2a',  // amber whisper
  };

  const RAMP_STOPS = [
    [0.00, '#2e3239'],
    [0.02, '#553e2c'],
    [0.05, '#7a4f2c'],
    [0.10, '#a3632e'],
    [0.20, '#c97933'],
    [0.40, '#e69241'],
    [0.80, '#f4ad58'],
  ];

  // ---------- Element refs ----------
  const $ = (id) => document.getElementById(id);
  const tip = $('tip');
  const loader = $('loader');
  const stateSelect = $('filterState');
  const stateTable = $('stateTable');
  const topList = $('topList');

  // ---------- Glossary (one-line definitions for hover) ----------
  const GLOSSARY = {
    auc: {
      term: "AUC (FOLD-AVERAGED)",
      def: "Mean of 8 walk-forward fold AUCs. Each fold trains on years 2009→T, validates on T+1, tests on T+2..T+3 (T=2014..2021). The 0.857 ± 0.044 is the mean ± std of those 8 fold AUCs. This is the canonical headline metric.",
      more: "see METHODS · WALK-FORWARD VALIDATION",
    },
    ap_lift: {
      term: "AP-LIFT",
      def: "Average-Precision lift = AP / base-rate. The top-ranked tracts are ~9.25× more likely to actually become deserts than the panel's base rate.",
      more: "see METHODS · THE FORECASTING PROBLEM",
    },
    n_tracts: {
      term: "N TRACTS",
      def: "Tracts in the test predictions across all 8 walk-forward folds (deduplicated to one prediction per tract — the most recent fold).",
      more: null,
    },
    walk_forward: {
      term: "FOLDS",
      def: "Eight chronological walk-forward folds. Each trains on years up to T, validates on T+1, tests on T+2..T+3. Mirrors deployment.",
      more: "see METHODS · WALK-FORWARD VALIDATION",
    },
    pooled_auc: {
      term: "POOLED AUC",
      def: "Single AUC computed across all currently-visible (filtered) tracts at once. DIFFERENT statistic from the masthead AUC, even with no filters: masthead is the mean of 8 fold AUCs (each on its own test set); pooled treats all 79k tracts as one rank-ordering. With no filter, pooled ≈ 0.75. As you filter, the value shifts because the positive / negative mix changes. Reads 'n=37 · too few' when n_labeled ≤ 50.",
      more: "see METHODS · WHY POOLED AUC ≠ HEADLINE AUC",
    },
    filtered_tracts: {
      term: "FILTERED TRACTS",
      def: "Number of tracts matching all current filters. Recomputes on every slider tick.",
      more: null,
    },
    mean_risk: {
      term: "MEAN RISK",
      def: "Mean predicted P(becomes a desert at year+1) across the filtered tract set. Calibrated probabilities — they should match observed frequencies on average.",
      more: null,
    },
    max_risk: {
      term: "MAX RISK",
      def: "Highest predicted desert-formation probability in the filtered set. The single most-at-risk tract.",
      more: null,
    },
    pos_rate: {
      term: "POSITIVE RATE",
      def: "Fraction of filtered tracts whose H1 transition target = 1 — i.e. they actually became deserts one year forward. The model's job is to outrank this rate via the predicted probabilities.",
      more: null,
    },
    risk: {
      term: "PREDICTED RISK",
      def: "P(tract not currently a desert becomes one at year+1). Calibrated probability output of the audit-fixed XGBoost model. Range 0% to ~88%.",
      more: "see METHODS · CALIBRATION",
    },
    filter_state: {
      term: "STATE FILTER",
      def: "Limits the visible tracts to one of 50 states + DC. Clicking a state in the table on the right also applies this filter and zooms in.",
      more: null,
    },
    static_flags: {
      term: "STATIC FLAGS",
      def: "RURAL = RUCA primary code ≥ 7 (USDA). PERSISTENT POVERTY = USDA 2017–2021 county designation (≥20% poverty rate for 4 decennial-style observations).",
      more: null,
    },
    layer_diag: {
      term: "MODEL LAYER 01 · DIAGNOSTIC 2026",
      def: "Champion XGBoost on the 1-year (H1) transition target. Latest fold (F8) tested 2023→2024; predictions read as a near-term diagnostic — which currently-non-desert tracts are about to flip. Walk-forward AUC 0.857 ± 0.044, calibrated. Already-deserts are excluded from the model and rendered with a distinct flag.",
      more: "see METHODS · WALK-FORWARD VALIDATION",
    },
    layer_fore: {
      term: "MODEL LAYER 02 · FORECAST 2030",
      def: "Sibling model on the 3-year (H3) transition target — same XGBoost architecture, same 39 features, same isotonic calibration. Six walk-forward folds; mean test AUC 0.863 ± 0.043, AP-lift ~11×. Trained model is then scored on 2024 features (no labels available) — these are the long-horizon predictions surfaced as 'Forecast 2030'. Strict reading: 3 years out from 2024 (i.e. 2027); the 2030 framing carries a horizon caveat.",
      more: "see METHODS · LONG-HORIZON FORECAST",
    },
    layers: {
      term: "OVERLAYS & BOUNDARIES",
      def: "Optional reference layers. BANK BRANCHES plots 2024 FDIC Summary-of-Deposits points so 'no loans because no bank' is visually distinguishable from 'no loans despite a bank.' COUNTY / CITY / STATE outlines toggle independently for context. PEER FINDER, when on, surfaces 3 tracts per click that match the source tract's demographics but live in the thriving-SBA quintile.",
      more: null,
    },
    sba: {
      term: "SBA LOANS PER 1K",
      def: "SBA 7(a) + 504 loan count for the latest year (2024), apportioned from ZIP-year totals to this tract using Census ZCTA land-area shares, divided by tract population × 1000.",
      more: null,
    },
    sba_rank: {
      term: "SBA RANK",
      def: "Within-state percentile (0-100) of this tract's SBA-loans-per-1k. The Peer Finder's 'thriving' pool is tracts at rank ≥ 80.",
      more: null,
    },
  };

  // Full glossary for the METHODS panel (subset above is for hover-only items;
  // the METHODS panel adds methodology-only entries that don't appear inline).
  const GLOSSARY_DOCS = [
    ["TRANSITION TARGET", "Tracts that are NOT currently deserts but BECOME deserts at year+1. Excludes already-deserts from the supervised set so the model is doing genuine forecasting (~2.75% positive rate), not predicting a sticky state."],
    ["CIRCULAR FEATURES", "25 features dropped because they leak the target. Tier 1 (CRA-side, 11 features): n_cra_lenders directly defines the desert; lender entries/exits/churn at year T mechanically tied. Tier 2 (CRA county, 3): county lender count and total loans are 'county desert rate' analogs. Tier 3 (FDIC, 11): banks ARE CRA reporters, so fdic_bank_count cross-correlates 0.85 with n_cra_lenders."],
    ["TRACT VINTAGE HARMONIZATION", "Census tracts redraw every decennial. ~5% of tracts split, merge, or renumber per decade. We project all years onto the 2020-vintage tract code using Census Bureau relationship files (population-weighted for 2000→2010, area-weighted for 2010→2020)."],
    ["BRIER SCORE", "Mean squared error between predicted probabilities and observed labels. Lower is better-calibrated. We report 0.020, meaning predictions are within ~14% absolute of true rates on average. Calibration is on top of discrimination."],
    ["ISOTONIC CALIBRATION", "Adjusts predicted probabilities to better match observed frequencies. Fit on validation, applied to test. On Round 5 it was a no-op (Brier moved -0.0002) because the model was already well-calibrated post-FDIC-drop."],
    ["RUCA / PERSISTENT POVERTY", "USDA Rural-Urban Commuting Area code (1-10, 7+ = rural). Persistent poverty county = USDA designation, county had ≥20% poverty rate at 2000, 2010, and 2017-21 ACS measurements."],
    ["ACS LAG-AWARE MERGE", "ACS 5-year vintage V is published in autumn of year V+1. So for predicting at the start of year P, the latest valid vintage is P-2. We enforce this; the prior version had a 6-month forward leak."],
  ];

  // ---------- Filter state ----------
  let filters = defaultFilters();
  let stateBbox = null;
  let nationalAuc = 0.857;

  // Active model layer: 'diag' (H1, ~2026) or 'fore' (H3, ~2030).
  // The choropleth's `fill-color` and the tooltip risk number both read from
  // whichever property name we resolve here.
  let modelLayer = 'diag';
  const LAYER_PROP = { diag: 'yp1', fore: 'yp3' };
  const LAYER_META = {
    diag: { auc: '0.857', band: '±0.044', name: 'DIAGNOSTIC · H1 → 2026' },
    fore: { auc: '0.863', band: '±0.043', name: 'FORECAST · H3 → 2030' },
  };

  function defaultFilters() {
    return {
      state: 'ALL',
      rural: false,
      pp: false,
      popMin: 0, popMax: 20000,
      incMin: 0, incMax: 200000,
      povMin: 0, povMax: 60,
      minMin: 0, minMax: 100,
      riskMin: 0,
    };
  }

  // ---------- MAP ----------
  let map;
  try {
    map = new maplibregl.Map({
      container: 'map',
      style: {
        version: 8,
        sources: {},
        layers: [{ id: 'page-bg', type: 'background', paint: { 'background-color': HEX.bg } }],
      },
      center: [-96.5, 39.0],
      zoom: 3.5,
      minZoom: 3,
      maxZoom: 11,
      maxBounds: [[-179, 14], [-60, 72]],
      attributionControl: false,
      pitchWithRotate: false,
      dragRotate: false,
      touchPitch: false,
      renderWorldCopies: false,
    });
    console.info('[map] MapLibre', maplibregl.version || '?', 'initialized');
  } catch (err) {
    console.error('[map] init failed:', err);
    fatal('Map failed to initialize.');
    return;
  }
  map.touchZoomRotate.disableRotation();
  map.addControl(new maplibregl.NavigationControl({ showCompass: false, visualizePitch: false }), 'top-right');
  map.addControl(new maplibregl.AttributionControl({
    compact: true,
    customAttribution: 'BUS410 Team 7 · Round 5'
  }), 'bottom-left');

  function fatal(msg) {
    if (!loader) return;
    loader.innerHTML = `<p style="font-family:JetBrains Mono;color:${HEX.accent};max-width:32ch;text-align:center;line-height:1.6">
      <strong>DASHBOARD FAILED TO LOAD</strong><br><br>${msg}<br><br>OPEN DEVTOOLS CONSOLE FOR DETAILS.</p>`;
  }

  // ---------- DATA LOAD ----------
  let stateStats = null;
  let statesData = null;
  let tractsData = null;
  let hoveredId = null;
  let pinned = false;

  // Cache buster forces the browser to refetch when underlying data changes
  // (we re-bump it in lockstep with the app.js?v= query in index.html).
  const DATA_VER = 'h3-3';
  Promise.all([
    fetch(`data/state_stats.json?v=${DATA_VER}`).then(r => r.json()),
    fetch(`data/state_bbox.json?v=${DATA_VER}`).then(r => r.json()),
    fetch(`data/states.geojson?v=${DATA_VER}`).then(r => r.json()),
    fetch(`data/tracts.geojson?v=${DATA_VER}`).then(r => r.json()),
  ]).then(([stats, bbox, states, tracts]) => {
    stateStats = stats;
    stateBbox = bbox;
    statesData = states;
    tractsData = tracts;
    nationalAuc = stats.national.auc;

    // Update headline n_tracts only — keep AUC pinned to the fold-averaged
    // 0.857 (the canonical headline from CHANGES.md). The pooled AUC across
    // tractsData is a different statistic and lives in the right-rail filtered
    // AUC (which starts equal to it when no filters are applied).
    $('hNTracts').textContent = stats.national.n_tracts.toLocaleString();

    populateStateSelect(stats);
    populateStateTable(stats);

    if (map.isStyleLoaded()) addLayers();
    else map.once('load', addLayers);
  }).catch((err) => {
    console.error('Data load failed:', err);
    fatal('Could not load data files.');
  });

  function populateStateSelect(stats) {
    const opts = stats.states
      .slice()
      .sort((a, b) => (STATE_NAME[a.state] || a.state).localeCompare(STATE_NAME[b.state] || b.state))
      .map(s => `<option value="${s.state}">${s.state} · ${STATE_NAME[s.state] || s.state}</option>`)
      .join('');
    stateSelect.insertAdjacentHTML('beforeend', opts);
  }

  function populateStateTable(stats) {
    const rows = stats.states
      .slice()
      .sort((a, b) => b.auc - a.auc)
      .map(s => `
        <tr data-state="${s.state}">
          <td>${s.state}</td>
          <td>${s.auc.toFixed(3)}</td>
          <td>${(s.mean_risk * 100).toFixed(1)}%</td>
        </tr>`).join('');
    stateTable.innerHTML = rows;
    stateTable.addEventListener('click', (e) => {
      const tr = e.target.closest('tr[data-state]');
      if (!tr) return;
      const st = tr.dataset.state;
      stateSelect.value = st;
      onFilterChange();
      flyToState(st);
    });
  }

  // ---------- LAYERS ----------
  function addLayers() {
    map.addSource('states', { type: 'geojson', data: statesData });
    // State tint — kept BELOW tract choropleth (no-data fallback color).
    // Visible only in gaps; the visible "regional shade" lives in the
    // overlay tint added later, after tracts-fill.
    map.addLayer({
      id: 'states-fill',
      type: 'fill',
      source: 'states',
      paint: {
        'fill-color': HEX.rampNo,
        'fill-outline-color': 'transparent',
      }
    });

    // Tracts (the heavy layer)
    map.addSource('tracts', {
      type: 'geojson',
      data: tractsData,
      promoteId: 'f',
      generateId: false,
    });

    map.addLayer({
      id: 'tracts-fill',
      type: 'fill',
      source: 'tracts',
      paint: {
        'fill-color': buildRampExpression(),
        'fill-opacity': buildOpacityExpression(),
        'fill-outline-color': 'transparent',
        'fill-color-transition': { duration: 220, delay: 0 },
        'fill-opacity-transition': { duration: 180, delay: 0 },
      }
    }, 'states-line');

    // Hover ring
    map.addLayer({
      id: 'tracts-hover',
      type: 'line',
      source: 'tracts',
      paint: {
        'line-color': HEX.accent,
        'line-width': 1.4,
        'line-opacity': ['case', ['boolean', ['feature-state', 'hover'], false], 1, 0],
      }
    });

    // Pinned ring (when click-locked)
    map.addLayer({
      id: 'tracts-pinned',
      type: 'line',
      source: 'tracts',
      paint: {
        'line-color': HEX.text,
        'line-width': 1.6,
        'line-opacity': ['case', ['boolean', ['feature-state', 'pinned'], false], 1, 0],
      }
    });

    // Peer ring — accent-color outline, distinct line-dasharray so peers
    // visually read as "linked to source tract" not "selected"
    map.addLayer({
      id: 'tracts-peer',
      type: 'line',
      source: 'tracts',
      paint: {
        'line-color': HEX.accent,
        'line-width': 1.4,
        'line-dasharray': [2, 2],
        'line-opacity': ['case', ['boolean', ['feature-state', 'peer'], false], 1, 0],
      }
    });

    // ----- STACKED REGION TINTS (above choropleth, low opacity) -----
    // State tint: cool slate, on top of the choropleth so the boundary
    // shading is visible even over 92%-opaque amber tracts.
    map.addLayer({
      id: 'states-tint',
      type: 'fill',
      source: 'states',
      paint: {
        'fill-color': HEX.tintState,
        'fill-opacity': ['interpolate', ['linear'], ['zoom'], 3, 0.10, 7, 0.07, 10, 0.04],
        'fill-outline-color': 'transparent',
      }
    });
    // State outline — drawn last so boundaries stay crisp.
    map.addLayer({
      id: 'states-line',
      type: 'line',
      source: 'states',
      paint: {
        'line-color': HEX.ruleStrong,
        'line-width': ['interpolate', ['linear'], ['zoom'], 3, 1.0, 6, 1.4, 10, 2.0],
        'line-opacity': 0.95,
      }
    });

    bindMap();
    bindLayerToggles();
    updateStats();
    finishLoad();
  }

  function buildRampExpression() {
    // Read from whichever model layer is active. Diagnostic falls back to the
    // legacy `yp` if cached data predates the yp1/yp3 split. Already-desert
    // tracts get a saturated accent fill (the model has no opinion about them).
    const prop = LAYER_PROP[modelLayer];
    const value = prop === 'yp1'
      ? ['coalesce', ['get', 'yp1'], ['get', 'yp'], 0]
      : ['coalesce', ['get', prop], 0];
    return [
      'case',
      ['==', ['coalesce', ['get', 'dn'], 0], 1],
      HEX.accent,
      ['interpolate', ['linear'], value, ...RAMP_STOPS.flatMap(([k, c]) => [k, c])],
    ];
  }

  // Slider maxes; when the slider is at its max we treat as unbounded
  const SLIDER_MAX = { pop: 20000, inc: 200000, pov: 60, min: 100 };

  // Mask filtering: filtered-IN tracts at full opacity, filtered-OUT at ~0.10
  function buildOpacityExpression() {
    const f = filters;
    const clauses = [];
    if (f.state !== 'ALL') clauses.push(['==', ['get', 'st'], f.state]);
    if (f.rural) clauses.push(['==', ['get', 'ru'], 1]);
    if (f.pp)    clauses.push(['==', ['get', 'pp'], 1]);
    if (f.popMin > 0) clauses.push(['>=', ['coalesce', ['get', 'pop'], -1], f.popMin]);
    if (f.popMax < SLIDER_MAX.pop) clauses.push(['<=', ['coalesce', ['get', 'pop'], 1e9], f.popMax]);
    if (f.incMin > 0) clauses.push(['>=', ['coalesce', ['get', 'inc'], -1], f.incMin]);
    if (f.incMax < SLIDER_MAX.inc) clauses.push(['<=', ['coalesce', ['get', 'inc'], 1e9], f.incMax]);
    if (f.povMin > 0) clauses.push(['>=', ['coalesce', ['get', 'pov'], -1], f.povMin]);
    if (f.povMax < SLIDER_MAX.pov) clauses.push(['<=', ['coalesce', ['get', 'pov'], 1e9], f.povMax]);
    if (f.minMin > 0) clauses.push(['>=', ['coalesce', ['get', 'min'], -1], f.minMin]);
    if (f.minMax < SLIDER_MAX.min) clauses.push(['<=', ['coalesce', ['get', 'min'], 1e9], f.minMax]);
    if (f.riskMin > 0) clauses.push(['>=', ['coalesce', ['get', LAYER_PROP[modelLayer]], 0], f.riskMin / 100]);
    const inExpr = clauses.length ? ['all', ...clauses] : true;
    return [
      'interpolate', ['linear'], ['zoom'],
      3,  ['case', inExpr, 0.92, 0.10],
      8,  ['case', inExpr, 0.96, 0.08],
    ];
  }

  // ---------- INTERACTION ----------
  function bindMap() {
    const canvas = map.getCanvas();

    map.on('mousemove', 'tracts-fill', (e) => {
      if (pinned) return;
      canvas.style.cursor = 'pointer';
      const f = e.features && e.features[0];
      if (!f) return;
      setHover(f.id);
      renderTip(f.properties, e);
    });
    map.on('mouseleave', 'tracts-fill', () => {
      if (pinned) return;
      canvas.style.cursor = '';
      clearHover();
      hideTip();
    });
    map.on('click', 'tracts-fill', (e) => {
      const f = e.features && e.features[0];
      if (!f) return;
      pinTract(f.id, f.properties, e);
    });
    map.on('click', (e) => {
      // Click outside a tract = unpin
      const feats = map.queryRenderedFeatures(e.point, { layers: ['tracts-fill'] });
      if (feats.length === 0 && pinned) unpin();
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { unpin(); }
      if (e.key === 'r' || e.key === 'R') {
        if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'SELECT') {
          resetFilters();
        }
      }
    });
  }

  function setHover(id) {
    if (hoveredId !== null && hoveredId !== id) {
      map.setFeatureState({ source: 'tracts', id: hoveredId }, { hover: false });
    }
    hoveredId = id;
    map.setFeatureState({ source: 'tracts', id }, { hover: true });
  }
  function clearHover() {
    if (hoveredId !== null) {
      map.setFeatureState({ source: 'tracts', id: hoveredId }, { hover: false });
      hoveredId = null;
    }
  }

  let pinnedId = null;
  function pinTract(id, props, e) {
    if (pinnedId !== null) {
      map.setFeatureState({ source: 'tracts', id: pinnedId }, { pinned: false });
    }
    pinnedId = id;
    pinned = true;
    map.setFeatureState({ source: 'tracts', id }, { pinned: true });
    tip.classList.add('is-pinned');
    $('tipHint').textContent = 'CLICK OUTSIDE / ESC TO RELEASE';
    renderTip(props, e);
  }
  function unpin() {
    if (pinnedId !== null) {
      map.setFeatureState({ source: 'tracts', id: pinnedId }, { pinned: false });
      pinnedId = null;
    }
    clearPeerRings();
    pinned = false;
    tip.classList.remove('is-pinned');
    $('tipHint').textContent = 'CLICK TO PIN · ESC TO RELEASE';
    clearHover();
    hideTip();
  }

  // ---------- TOOLTIP ----------
  function renderTip(p, e) {
    $('tipState').textContent = p.st || '—';
    $('tipCounty').textContent = p.cn || '—';
    $('tipFips').textContent = 'TR ' + p.f;
    $('tipZip').textContent = p.zp ? ('ZIP ' + p.zp) : 'ZIP —';
    // Risk reads from the active model layer; mark already-deserts explicitly.
    const ypActive = p[LAYER_PROP[modelLayer]];
    if (p.dn === 1) {
      $('tipRisk').textContent = 'IS DESERT';
    } else if (ypActive == null) {
      $('tipRisk').textContent = '—';
    } else {
      $('tipRisk').textContent = (ypActive * 100).toFixed(1) + '%';
    }
    const lbl = $('tipRiskLbl');
    if (lbl) lbl.textContent = LAYER_META[modelLayer].name;
    $('tipPop').textContent = p.pop != null ? Number(p.pop).toLocaleString() : '—';
    $('tipInc').textContent = p.inc != null ? '$' + Math.round(p.inc / 1000) + 'k' : '—';
    $('tipPov').textContent = p.pov != null ? p.pov.toFixed(1) + '%' : '—';
    $('tipMin').textContent = p.min != null ? p.min.toFixed(1) + '%' : '—';
    $('tipRural').textContent = p.ru ? 'YES' : 'NO';
    $('tipPp').textContent = p.pp ? 'YES' : 'NO';
    $('tipSba').textContent = p.sl != null ? Number(p.sl).toFixed(2) : '—';
    $('tipSbaRank').textContent = p.ss != null ? Math.round(p.ss) : '—';
    renderPeers(p);
    positionTip(e);
    showTip();
  }
  function showTip() { tip.hidden = false; }
  function hideTip() { tip.hidden = true; }
  function positionTip(e) {
    if (!e || !e.point || !e.originalEvent) return;
    const pad = 14;
    const w = tip.offsetWidth || 240;
    const h = tip.offsetHeight || 280;
    let x = e.originalEvent.clientX + pad;
    let y = e.originalEvent.clientY + pad;
    if (x + w > window.innerWidth - 12) x = e.originalEvent.clientX - w - pad;
    if (y + h > window.innerHeight - 12) y = e.originalEvent.clientY - h - pad;
    tip.style.left = Math.max(12, x) + 'px';
    tip.style.top = Math.max(12, y) + 'px';
  }
  window.addEventListener('resize', () => { /* no-op for now */ });

  // ---------- FILTER WIRING ----------
  const filterEls = {
    state: 'filterState',
    rural: 'filterRural',
    pp:    'filterPersistentPov',
    popMin: 'popMin', popMax: 'popMax',
    incMin: 'incMin', incMax: 'incMax',
    povMin: 'povMin', povMax: 'povMax',
    minMin: 'minMin', minMax: 'minMax',
    riskMin: 'riskMin',
  };
  Object.keys(filterEls).forEach(key => {
    const el = $(filterEls[key]);
    if (!el) return;
    const evt = (el.type === 'checkbox') ? 'change' : 'input';
    el.addEventListener(evt, () => {
      readFilters();
      onFilterChange();
    });
  });

  function readFilters() {
    filters.state = stateSelect.value;
    filters.rural = $('filterRural').checked;
    filters.pp    = $('filterPersistentPov').checked;
    filters.popMin = +$('popMin').value;
    filters.popMax = +$('popMax').value;
    filters.incMin = +$('incMin').value;
    filters.incMax = +$('incMax').value;
    filters.povMin = +$('povMin').value;
    filters.povMax = +$('povMax').value;
    filters.minMin = +$('minMin').value;
    filters.minMax = +$('minMax').value;
    filters.riskMin = +$('riskMin').value;

    // Mark ADVANCED section as modified if any of its 4 ranges is off-default
    const advancedActive =
      filters.popMin > 0 || filters.popMax < 20000 ||
      filters.incMin > 0 || filters.incMax < 200000 ||
      filters.povMin > 0 || filters.povMax < 60 ||
      filters.minMin > 0 || filters.minMax < 100;
    const advWrap = document.querySelector('.advanced');
    if (advWrap) advWrap.classList.toggle('is-modified', advancedActive);

    // Reflect range labels
    $('popMinVal').textContent = filters.popMin === 20000 ? '20k+' : filters.popMin.toLocaleString();
    $('popMaxVal').textContent = filters.popMax === 20000 ? '20k+' : filters.popMax.toLocaleString();
    $('incMinVal').textContent = '$' + (filters.incMin/1000) + 'k';
    $('incMaxVal').textContent = filters.incMax === 200000 ? '$200k+' : '$' + (filters.incMax/1000) + 'k';
    $('povMinVal').textContent = filters.povMin + '%';
    $('povMaxVal').textContent = filters.povMax === 60 ? '60%+' : filters.povMax + '%';
    $('minMinVal').textContent = filters.minMin + '%';
    $('minMaxVal').textContent = filters.minMax + '%';
    $('riskMinVal').textContent = filters.riskMin + '%';
  }

  $('filterReset').addEventListener('click', resetFilters);
  function resetFilters() {
    filters = defaultFilters();
    stateSelect.value = 'ALL';
    $('filterRural').checked = false;
    $('filterPersistentPov').checked = false;
    $('popMin').value = 0; $('popMax').value = 20000;
    $('incMin').value = 0; $('incMax').value = 200000;
    $('povMin').value = 0; $('povMax').value = 60;
    $('minMin').value = 0; $('minMax').value = 100;
    $('riskMin').value = 0;
    readFilters();
    onFilterChange();
    map.flyTo({ center: [-96.5, 39.0], zoom: 3.5, duration: 700, essential: true });
  }

  let onFilterChangeTimer = null;
  function onFilterChange() {
    // Update map immediately
    if (map.getLayer('tracts-fill')) {
      map.setPaintProperty('tracts-fill', 'fill-opacity', buildOpacityExpression());
    }
    // Debounce stats recompute (slider drags)
    clearTimeout(onFilterChangeTimer);
    onFilterChangeTimer = setTimeout(updateStats, 50);

    // State filter triggers fly
    if (filters.state !== 'ALL' && stateBbox && stateBbox[filters.state]) {
      flyToState(filters.state);
    }
  }

  function flyToState(state) {
    const bb = stateBbox?.[state];
    if (!bb) return;
    const [minX, minY, maxX, maxY] = bb;
    map.fitBounds([[minX, minY], [maxX, maxY]], {
      padding: { top: 80, right: 280, bottom: 56, left: 280 },
      duration: 700,
      essential: true,
    });
  }

  // ---------- STATS RECOMPUTE ----------
  function tractMatches(p) {
    const f = filters;
    if (f.state !== 'ALL' && p.st !== f.state) return false;
    if (f.rural && !p.ru) return false;
    if (f.pp && !p.pp) return false;
    if (p.pop != null) {
      if (p.pop < f.popMin) return false;
      if (f.popMax < SLIDER_MAX.pop && p.pop > f.popMax) return false;
    }
    if (p.inc != null) {
      if (p.inc < f.incMin) return false;
      if (f.incMax < SLIDER_MAX.inc && p.inc > f.incMax) return false;
    }
    if (p.pov != null) {
      if (p.pov < f.povMin) return false;
      if (f.povMax < SLIDER_MAX.pov && p.pov > f.povMax) return false;
    }
    if (p.min != null) {
      if (p.min < f.minMin) return false;
      if (f.minMax < SLIDER_MAX.min && p.min > f.minMax) return false;
    }
    const yp = p[LAYER_PROP[modelLayer]] ?? 0;
    if (yp * 100 < f.riskMin) return false;
    return true;
  }

  function updateStats() {
    if (!tractsData) return;
    const matched = [];
    let yt0 = 0, yt1 = 0;
    for (const f of tractsData.features) {
      const p = f.properties;
      if (tractMatches(p)) {
        matched.push(p);
        if (p.yt === 1) yt1++;
        else if (p.yt === 0) yt0++;
      }
    }

    $('sNTracts').textContent = matched.length.toLocaleString();

    // Helper: write a value with optional muted state for empty/insufficient
    const setStat = (id, value, muted) => {
      const el = $(id);
      el.textContent = value;
      el.classList.toggle('is-muted', !!muted);
    };

    if (matched.length === 0) {
      setStat('sMeanRisk', 'no match', true);
      setStat('sMaxRisk',  'no match', true);
      setStat('sPosRate',  'no match', true);
      setStat('sAuc',      'no match', true);
      topList.innerHTML = '';
      return;
    }

    const propA = LAYER_PROP[modelLayer];
    const sumRisk = matched.reduce((a, b) => a + (b[propA] ?? 0), 0);
    const meanRisk = sumRisk / matched.length;
    const maxRisk = matched.reduce((m, b) => (b[propA] ?? 0) > m ? (b[propA] ?? 0) : m, 0);
    const labeled = yt0 + yt1;
    const posRate = labeled > 0 ? yt1 / labeled : null;

    setStat('sMeanRisk', (meanRisk * 100).toFixed(2) + '%', false);
    setStat('sMaxRisk',  (maxRisk * 100).toFixed(1) + '%', false);
    if (posRate != null) {
      setStat('sPosRate', (posRate * 100).toFixed(2) + '%', false);
    } else {
      setStat('sPosRate', 'no labels', true);
    }
    if (labeled === 0) {
      setStat('sAuc', 'no labels', true);
    } else if (labeled <= 50) {
      setStat('sAuc', `n=${labeled} · too few`, true);
    } else {
      setStat('sAuc', auc(matched).toFixed(3), false);
    }

    // Top-25 list — sorted on the active model layer
    const propT = LAYER_PROP[modelLayer];
    const top25 = matched.slice().sort((a, b) => (b[propT] ?? 0) - (a[propT] ?? 0)).slice(0, 25);
    topList.innerHTML = top25.map((p, i) => `
      <li class="toplist__row" data-fips="${p.f}">
        <span class="toplist__rank">${(i+1).toString().padStart(2,'0')}</span>
        <span class="toplist__fips">${p.f} <span class="toplist__state">${p.st}</span></span>
        <span class="toplist__risk">${((p[propT] ?? 0)*100).toFixed(1)}%</span>
      </li>`).join('');
    // Click in top-N: fly to the tract AND pin its tooltip (acts like a map click)
    topList.querySelectorAll('.toplist__row').forEach(row => {
      row.addEventListener('click', () => {
        const fips = row.dataset.fips;
        const feat = tractsData.features.find(f => f.properties.f === fips);
        if (!feat) return;
        const c = featureCenter(feat);
        map.flyTo({ center: c, zoom: 9, duration: 700, essential: true });
        // After the fly settles, pin the tract — synthesizes a click event
        map.once('moveend', () => {
          const proj = map.project(c);
          const synthetic = {
            point: proj,
            originalEvent: { clientX: proj.x, clientY: proj.y },
          };
          pinTract(fips, feat.properties, synthetic);
        });
      });
    });
  }

  // Compute AUC via Mann-Whitney U trick. Reasonably fast for ~100k points.
  function auc(rows) {
    let sumRanks = 0;
    let nPos = 0, nNeg = 0;
    const propA = LAYER_PROP[modelLayer];
    const labeled = rows.filter(r => r.yt === 0 || r.yt === 1);
    if (labeled.length < 2) return NaN;
    labeled.sort((a, b) => (a[propA] ?? 0) - (b[propA] ?? 0));
    let i = 0;
    while (i < labeled.length) {
      let j = i;
      while (j + 1 < labeled.length && labeled[j+1].yp === labeled[i].yp) j++;
      const avgRank = (i + 1 + j + 1) / 2;
      for (let k = i; k <= j; k++) {
        if (labeled[k].yt === 1) { sumRanks += avgRank; nPos++; }
        else { nNeg++; }
      }
      i = j + 1;
    }
    if (nPos === 0 || nNeg === 0) return NaN;
    return (sumRanks - nPos*(nPos+1)/2) / (nPos * nNeg);
  }

  function featureCenter(feat) {
    const c = feat.geometry.coordinates;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    function walk(coord) {
      if (typeof coord[0] === 'number') {
        minX = Math.min(minX, coord[0]); minY = Math.min(minY, coord[1]);
        maxX = Math.max(maxX, coord[0]); maxY = Math.max(maxY, coord[1]);
      } else for (const p of coord) walk(p);
    }
    walk(c);
    return [(minX+maxX)/2, (minY+maxY)/2];
  }

  // ---------- LOADING ----------
  function finishLoad() {
    map.once('idle', () => {
      loader.classList.add('is-done');
      document.body.classList.add('is-loaded');
      setTimeout(() => { loader.style.display = 'none'; }, 420);
      readFilters();  // initial label sync
    });
  }

  setTimeout(() => {
    if (loader && !loader.classList.contains('is-done')) {
      $('loaderStatus').textContent = 'still loading… first paint can take 6–10 s';
    }
  }, 4000);

  setTimeout(() => {
    if (loader && !loader.classList.contains('is-done')) {
      console.warn('[map] 30 s elapsed without idle event; forcing loader hide');
      loader.classList.add('is-done');
      document.body.classList.add('is-loaded');
      setTimeout(() => { loader.style.display = 'none'; }, 420);
    }
  }, 30000);

  // ============================================================
  // GLOSSARY HOVER TOOLTIP (small, follows cursor on labels)
  // ============================================================
  const gtip = $('gtip');
  let gtipShown = false;

  function showGtip(key, evt) {
    const entry = GLOSSARY[key];
    if (!entry) return;
    gtip.innerHTML = `
      <span class="gtip__term">${entry.term}</span>
      <span class="gtip__def">${entry.def}</span>
      ${entry.more ? `<span class="gtip__more">${entry.more}</span>` : ''}
    `;
    gtip.hidden = false;
    gtipShown = true;
    positionGtip(evt);
  }
  function hideGtip() {
    gtip.hidden = true;
    gtipShown = false;
  }
  function positionGtip(evt) {
    if (!evt) return;
    const pad = 12;
    const w = gtip.offsetWidth || 280;
    const h = gtip.offsetHeight || 80;
    let x = evt.clientX + pad;
    let y = evt.clientY + pad;
    if (x + w > window.innerWidth - 12) x = evt.clientX - w - pad;
    if (y + h > window.innerHeight - 12) y = evt.clientY - h - pad;
    gtip.style.left = Math.max(12, x) + 'px';
    gtip.style.top  = Math.max(12, y) + 'px';
  }

  // Delegate hover on any element with data-gloss
  document.body.addEventListener('mouseover', (e) => {
    const el = e.target.closest('[data-gloss]');
    if (!el) return;
    const key = el.getAttribute('data-gloss');
    showGtip(key, e);
  });
  document.body.addEventListener('mousemove', (e) => {
    if (!gtipShown) return;
    const el = e.target.closest('[data-gloss]');
    if (!el) { hideGtip(); return; }
    positionGtip(e);
  });
  document.body.addEventListener('mouseout', (e) => {
    const to = e.relatedTarget;
    if (!to || !to.closest || !to.closest('[data-gloss]')) hideGtip();
  });

  // ============================================================
  // METHODS PANEL — slide-in methodology
  // ============================================================
  const docsPanel = $('docsPanel');
  const docsBtn = $('docsBtn');
  const docsClose = $('docsClose');

  function openDocs() {
    docsPanel.hidden = false;
    requestAnimationFrame(() => docsPanel.classList.add('is-open'));
    docsBtn.setAttribute('aria-expanded', 'true');
    docsClose.focus();
  }
  function closeDocs() {
    docsPanel.classList.remove('is-open');
    docsBtn.setAttribute('aria-expanded', 'false');
    setTimeout(() => { docsPanel.hidden = true; }, 320);
    docsBtn.focus();
  }
  function toggleDocs() {
    if (docsPanel.classList.contains('is-open')) closeDocs();
    else openDocs();
  }
  if (docsBtn) docsBtn.addEventListener('click', toggleDocs);
  if (docsClose) docsClose.addEventListener('click', closeDocs);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && docsPanel && docsPanel.classList.contains('is-open')) {
      closeDocs();
    }
    if ((e.key === 'd' || e.key === 'D') && (e.target.tagName !== 'INPUT' && e.target.tagName !== 'SELECT')) {
      toggleDocs();
    }
  });

  // ============================================================
  // ADVANCED filter section — collapsible
  // ============================================================
  const advToggle = $('advancedToggle');
  if (advToggle) {
    advToggle.addEventListener('click', () => {
      const expanded = advToggle.getAttribute('aria-expanded') === 'true';
      advToggle.setAttribute('aria-expanded', String(!expanded));
    });
  }

  // Populate glossary section in METHODS panel
  const glossaryDefs = $('glossaryDefs');
  if (glossaryDefs) {
    // Combine the inline glossary entries + the METHODS-only entries
    const inline = Object.values(GLOSSARY).map(g => [g.term, g.def]);
    const all = [...inline, ...GLOSSARY_DOCS];
    glossaryDefs.innerHTML = all.map(([term, def]) =>
      `<div><dt>${term}</dt><dd>${def}</dd></div>`
    ).join('');
  }

  // ============================================================
  // OVERLAY LAYERS — branches, counties, places (lazy-loaded)
  // ============================================================
  // beforeId rules (applied per layer):
  //   'tracts-fill'  → fill sits BELOW the choropleth (tint shows in gaps + through low-opacity filtered-out tracts)
  //   'tracts-hover' → line sits ABOVE the choropleth but BELOW interaction rings
  //   undefined      → on top of everything (used for branch dots)
  const LAYER_SPECS = {
    layerBranches: {
      url: 'data/branches.geojson',
      sourceId: 'branches',
      sourceOpts: { cluster: true, clusterMaxZoom: 8, clusterRadius: 40 },
      layers: [
        {
          id: 'branches-cluster',
          type: 'circle',
          filter: ['has', 'point_count'],
          beforeId: undefined,
          paint: {
            'circle-color': HEX.accent,
            'circle-opacity': 0.45,
            'circle-radius': ['step', ['get', 'point_count'], 5, 25, 7, 100, 10, 500, 14, 2000, 20],
            'circle-stroke-width': 1,
            'circle-stroke-color': HEX.text,
            'circle-stroke-opacity': 0.55,
          },
        },
        {
          id: 'branches-cluster-count',
          type: 'symbol',
          filter: ['has', 'point_count'],
          beforeId: undefined,
          layout: {
            'text-field': ['get', 'point_count_abbreviated'],
            'text-size': 10,
            'text-font': ['Open Sans Regular'],
            'text-allow-overlap': true,
          },
          paint: { 'text-color': HEX.bg },
        },
        {
          // "Little nodes" — small open circles (dark fill, bright ring) so
          // each branch reads as a deliberate node, not a paint splatter.
          id: 'branches-unclustered',
          type: 'circle',
          filter: ['!', ['has', 'point_count']],
          beforeId: undefined,
          paint: {
            'circle-color': HEX.bg,
            'circle-opacity': 0.95,
            'circle-radius': [
              'interpolate', ['linear'], ['zoom'],
              4, 1.4, 7, 2.0, 10, 3.0,
            ],
            'circle-stroke-width': [
              'interpolate', ['linear'], ['zoom'], 4, 0.8, 10, 1.4,
            ],
            'circle-stroke-color': HEX.text,
            'circle-stroke-opacity': 0.9,
          },
        },
      ],
    },
    layerCounties: {
      url: 'data/counties.geojson',
      sourceId: 'counties',
      layers: [
        {
          // County tint — warm earth, sits ABOVE the state tint so counties
          // visually nest within their state.
          id: 'counties-fill',
          type: 'fill',
          beforeId: 'states-line',
          paint: {
            'fill-color': HEX.tintCounty,
            'fill-opacity': ['interpolate', ['linear'], ['zoom'], 4, 0.06, 7, 0.10, 10, 0.14],
            'fill-outline-color': 'transparent',
          },
        },
        {
          id: 'counties-line',
          type: 'line',
          beforeId: 'states-line',
          paint: {
            'line-color': HEX.rule,
            'line-width': ['interpolate', ['linear'], ['zoom'], 3, 0.4, 7, 0.9, 10, 1.4],
            'line-opacity': 0.7,
          },
        },
      ],
    },
    layerPlaces: {
      url: 'data/places.geojson',
      sourceId: 'places',
      layers: [
        {
          // City tint — amber whisper, ABOVE both state and county tints
          // so cities pop within their county.
          id: 'places-fill',
          type: 'fill',
          beforeId: 'states-line',
          minzoom: 5,
          paint: {
            'fill-color': HEX.tintPlace,
            'fill-opacity': ['interpolate', ['linear'], ['zoom'], 5, 0.07, 8, 0.16, 11, 0.22],
            'fill-outline-color': 'transparent',
          },
        },
        {
          id: 'places-line',
          type: 'line',
          beforeId: 'states-line',
          minzoom: 6,
          paint: {
            'line-color': HEX.text,
            'line-width': ['interpolate', ['linear'], ['zoom'], 6, 0.5, 10, 1.2],
            'line-opacity': 0.55,
          },
        },
      ],
    },
  };

  const layerLoaded = {};
  let branchesPopupBound = false;

  async function loadOverlay(key) {
    if (layerLoaded[key]) return;
    const spec = LAYER_SPECS[key];
    try {
      const data = await fetch(spec.url).then(r => {
        if (!r.ok) throw new Error(`${spec.url} ${r.status}`);
        return r.json();
      });
      map.addSource(spec.sourceId, { type: 'geojson', data, ...(spec.sourceOpts || {}) });
      for (const lyr of spec.layers) {
        const { beforeId, ...rest } = lyr;
        const layerDef = {
          ...rest,
          source: spec.sourceId,
          layout: { ...(rest.layout || {}), visibility: 'visible' },
        };
        const before = beforeId && map.getLayer(beforeId) ? beforeId : undefined;
        map.addLayer(layerDef, before);
      }
      layerLoaded[key] = true;
      if (key === 'layerBranches' && !branchesPopupBound) {
        bindBranchPopup();
        branchesPopupBound = true;
      }
    } catch (err) {
      console.warn(`[overlay] ${key} failed:`, err);
      const cb = $(key);
      if (cb) cb.disabled = true;
    }
  }

  function setOverlayVisibility(key, on) {
    const spec = LAYER_SPECS[key];
    for (const lyr of spec.layers) {
      if (map.getLayer(lyr.id)) {
        map.setLayoutProperty(lyr.id, 'visibility', on ? 'visible' : 'none');
      }
    }
  }

  function bindLayerToggles() {
    const wire = (id, onChange) => {
      const cb = $(id);
      if (!cb) return;
      cb.addEventListener('change', () => onChange(cb.checked));
    };

    for (const key of Object.keys(LAYER_SPECS)) {
      wire(key, async (on) => {
        if (on && !layerLoaded[key]) await loadOverlay(key);
        setOverlayVisibility(key, on);
      });
    }

    // STATE OUTLINES — toggles the regional tint and the boundary line.
    // (states-fill stays as the no-data fallback color; not user-toggleable.)
    wire('layerStates', (on) => {
      ['states-tint', 'states-line'].forEach(id => {
        if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
      });
    });

    // PEER FINDER — purely UI; turning off just suppresses peer rendering on click.
    // No need to toggle a layer; the peerCard is rebuilt on every pin.
  }

  // ============================================================
  // BANK BRANCH POPUP (small inline label following cursor)
  // ============================================================
  const bpop = $('bpop');
  function bindBranchPopup() {
    const canvas = map.getCanvas();
    map.on('mousemove', 'branches-unclustered', (e) => {
      const f = e.features && e.features[0];
      if (!f) return;
      canvas.style.cursor = 'pointer';
      const p = f.properties;
      $('bpopCert').textContent = p.c || '—';
      $('bpopDep').textContent = p.d != null ? '$' + fmtMoney(p.d) : '—';
      bpop.hidden = false;
      positionAtEvent(bpop, e);
    });
    map.on('mouseleave', 'branches-unclustered', () => {
      bpop.hidden = true;
    });
    map.on('click', 'branches-cluster', (e) => {
      const f = e.features && e.features[0];
      if (!f) return;
      const src = map.getSource('branches');
      src.getClusterExpansionZoom(f.properties.cluster_id, (err, zoom) => {
        if (err) return;
        map.easeTo({ center: f.geometry.coordinates, zoom: Math.min(zoom + 0.3, 11), duration: 500 });
      });
    });
  }

  function fmtMoney(kDollars) {
    // DEPSUMBR is in $thousands. Convert to readable string.
    const v = Number(kDollars);
    if (!isFinite(v) || v <= 0) return '0';
    if (v >= 1e6) return (v / 1e6).toFixed(1) + 'B';
    if (v >= 1e3) return (v / 1e3).toFixed(1) + 'M';
    return Math.round(v) + 'K';
  }

  function positionAtEvent(el, e) {
    if (!e || !e.originalEvent) return;
    const pad = 12;
    const w = el.offsetWidth || 200;
    const h = el.offsetHeight || 32;
    let x = e.originalEvent.clientX + pad;
    let y = e.originalEvent.clientY + pad;
    if (x + w > window.innerWidth - 12) x = e.originalEvent.clientX - w - pad;
    if (y + h > window.innerHeight - 12) y = e.originalEvent.clientY - h - pad;
    el.style.left = Math.max(12, x) + 'px';
    el.style.top  = Math.max(12, y) + 'px';
  }

  // ============================================================
  // PEER FINDER — render peer cards inside the pinned tract tip
  // ============================================================
  const peerCard = $('peerCard');
  const peerList = $('peerList');
  const peerRingIds = new Set();

  function clearPeerRings() {
    for (const id of peerRingIds) {
      map.setFeatureState({ source: 'tracts', id }, { peer: false });
    }
    peerRingIds.clear();
  }

  function findFeature(fips) {
    if (!tractsData) return null;
    return tractsData.features.find(f => f.properties.f === fips) || null;
  }

  function renderPeers(p) {
    // Only show on pin (not on hover); only when the peer toggle is on.
    const toggle = $('layerPeers');
    const peerOn = toggle ? toggle.checked : true;
    if (!pinned || !peerOn || !p.pr || !p.pr.length) {
      peerCard.hidden = true;
      clearPeerRings();
      return;
    }

    const rows = p.pr.map((fips, i) => {
      const peer = findFeature(fips);
      if (!peer) return '';
      const pp = peer.properties;
      // Mark peer for ring rendering
      map.setFeatureState({ source: 'tracts', id: fips }, { peer: true });
      peerRingIds.add(fips);
      const inc = pp.inc != null ? '$' + Math.round(pp.inc / 1000) + 'k' : '—';
      const pov = pp.pov != null ? pp.pov.toFixed(0) + '%' : '—';
      const min = pp.min != null ? pp.min.toFixed(0) + '%' : '—';
      const ss  = pp.ss  != null ? Math.round(pp.ss) : '—';
      const sl  = pp.sl  != null ? Number(pp.sl).toFixed(1) : '—';
      const cn  = pp.cn  || pp.f;
      return `
        <li class="peers__row" data-fips="${fips}" title="Click to fly to and pin">
          <span class="peers__rank">P${i + 1}</span>
          <span class="peers__name">${cn}</span>
          <span class="peers__stat" title="Poverty">${pov}</span>
          <span class="peers__stat" title="Non-white %">${min}</span>
          <span class="peers__stat" title="Median income">${inc}</span>
          <span class="peers__stat peers__stat--good" title="SBA loans/1k · within-state rank">${sl} · ${ss}</span>
        </li>`;
    }).join('');

    peerList.innerHTML = rows;
    peerCard.hidden = false;

    peerList.querySelectorAll('.peers__row').forEach(row => {
      row.addEventListener('click', () => {
        const fips = row.dataset.fips;
        const feat = findFeature(fips);
        if (!feat) return;
        const c = featureCenter(feat);
        map.flyTo({ center: c, zoom: 9, duration: 700, essential: true });
        map.once('moveend', () => {
          const proj = map.project(c);
          const synthetic = { point: proj, originalEvent: { clientX: proj.x, clientY: proj.y } };
          pinTract(fips, feat.properties, synthetic);
        });
      });
    });
  }

  // Re-render peers when the toggle flips while a tract is pinned
  const peerToggle = $('layerPeers');
  if (peerToggle) {
    peerToggle.addEventListener('change', () => {
      if (!pinned || pinnedId == null) return;
      const feat = findFeature(pinnedId);
      if (feat) renderPeers(feat.properties);
    });
  }

  // ============================================================
  // MODEL LAYER SWITCH — Diagnostic (H1) vs Forecast (H3)
  // ============================================================
  function setModelLayer(name) {
    if (!LAYER_PROP[name]) return;
    if (name === modelLayer) return;
    modelLayer = name;
    console.info('[layer]', name, '→ paint prop', LAYER_PROP[name]);

    // Recolor + refilter the choropleth in one paint update
    if (map.getLayer('tracts-fill')) {
      map.setPaintProperty('tracts-fill', 'fill-color', buildRampExpression());
      map.setPaintProperty('tracts-fill', 'fill-opacity', buildOpacityExpression());
      map.triggerRepaint();
    }

    // Update masthead AUC headline + button states
    const meta = LAYER_META[name];
    $('hAuc').textContent = meta.auc;
    const nTr = stateStats?.national?.n_tracts;
    const nStr = nTr != null ? nTr.toLocaleString() : '—';
    $('hAucBand').innerHTML = `${meta.band} · n=<span id="hNTracts">${nStr}</span>`;

    document.querySelectorAll('.layer-switch__btn').forEach(btn => {
      const on = btn.dataset.layer === name;
      btn.classList.toggle('is-active', on);
      btn.setAttribute('aria-selected', String(on));
    });

    // Re-render the pinned tip if any (so its risk number updates)
    if (pinned && pinnedId != null) {
      const feat = findFeature(pinnedId);
      if (feat) {
        // Synthesize a no-op event so renderTip doesn't crash on positionTip
        renderTip(feat.properties, { point: null, originalEvent: null });
      }
    }

    // Refresh stats and top-25
    updateStats();
  }

  const layerBtns = document.querySelectorAll('.layer-switch__btn');
  console.info('[layer] switch buttons found:', layerBtns.length);
  layerBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      console.info('[layer] click →', btn.dataset.layer);
      setModelLayer(btn.dataset.layer);
    });
  });

  // Keyboard: 1/2 toggle layers (avoids collision with F/S/D/R/Esc)
  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
    if (e.key === '1') { e.preventDefault(); setModelLayer('diag'); }
    if (e.key === '2') { e.preventDefault(); setModelLayer('fore'); }
  });

  // ============================================================
  // RAIL DRAWERS — distillation: rails default-hidden so the map
  // gets ≥70% of the viewport. Toggles in the masthead + edge tabs
  // open them as overlays. Mutually exclusive (open one closes other).
  // ============================================================
  const RAIL_BODY_CLASS = { filters: 'show-filters', stats: 'show-stats' };
  const RAIL_BTNS = { filters: ['toggleFilters', 'edgeTabLeft'], stats: ['toggleStats', 'edgeTabRight'] };

  function setRail(name, open) {
    const otherName = name === 'filters' ? 'stats' : 'filters';
    document.body.classList.toggle(RAIL_BODY_CLASS[name], open);
    if (open) document.body.classList.remove(RAIL_BODY_CLASS[otherName]);
    syncRailAria();
  }
  function toggleRail(name) {
    const isOpen = document.body.classList.contains(RAIL_BODY_CLASS[name]);
    setRail(name, !isOpen);
  }
  function closeAllRails() {
    document.body.classList.remove(RAIL_BODY_CLASS.filters, RAIL_BODY_CLASS.stats);
    syncRailAria();
  }
  function syncRailAria() {
    const fOn = document.body.classList.contains(RAIL_BODY_CLASS.filters);
    const sOn = document.body.classList.contains(RAIL_BODY_CLASS.stats);
    const tf = $('toggleFilters'); if (tf) tf.setAttribute('aria-expanded', String(fOn));
    const ts = $('toggleStats');   if (ts) ts.setAttribute('aria-expanded', String(sOn));
  }

  RAIL_BTNS.filters.forEach(id => { const el = $(id); if (el) el.addEventListener('click', () => toggleRail('filters')); });
  RAIL_BTNS.stats.forEach(id =>   { const el = $(id); if (el) el.addEventListener('click', () => toggleRail('stats')); });
  const closeF = $('closeFilters'); if (closeF) closeF.addEventListener('click', () => setRail('filters', false));
  const closeS = $('closeStats');   if (closeS) closeS.addEventListener('click', () => setRail('stats',   false));

  // Esc closes rails (in addition to docs/pin); F/S toggle drawers
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeAllRails();
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
    if (e.key === 'f' || e.key === 'F') { e.preventDefault(); toggleRail('filters'); }
    if (e.key === 's' || e.key === 'S') { e.preventDefault(); toggleRail('stats'); }
  });

})();
