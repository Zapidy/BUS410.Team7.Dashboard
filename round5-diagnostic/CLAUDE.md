# BUS410 Team 7 — Round 5 (Credit Desert Prediction · Rebuild)

Active rebuild of the credit-desert prediction model. 16-year panel (2009–2024), 8-fold walk-forward validation, multiple supply-side data sources beyond Round 4. Round 4 preserved at [../round4/](../round4/) as historical reference.

**Champion model:** `walk_forward_audit_fixed` — XGBoost, 39 features (after 25 circular features removed), tract-vintage-harmonized to 2020, ACS publication-lag-safe, PR/VI excluded from training, isotonic-calibrated. Mean test **AUC 0.8566 ± 0.0443**, **AP-lift 9.25×**, Brier 0.0201. Across 8 walk-forward folds 2016–2024.

Round 4 baseline was AUC 0.7510. Round 5 is **+0.106 AUC** with multiple known leakage paths closed.

Read first: [CHANGES.md](CHANGES.md), [notes/00_methodology.md](notes/00_methodology.md), [.impeccable.md](.impeccable.md).

---

## Design Context

(Canonical content lives in [.impeccable.md](.impeccable.md); duplicated here so future Claude sessions in this folder pick it up automatically.)

### Users

Primary audience: the BUS410 professor and classmates during the final live presentation. Viewing on a classroom projector at roughly 10-foot distance. Five minutes to grok the headline finding, then reward closer interaction during Q&A.

Secondary: portfolio artifact afterward, viewed on a laptop.

Job to be done: convince a quantitatively-literate viewer that the model's tract-level desert-formation forecast is methodologically defensible, with the rigor visible in the surface itself.

### Brand Personality

Three words: **dense, clinical, authoritative.**

The voice of a Bloomberg Terminal screenshot, a Federal Reserve research tool, a TradingView pro-mode chart. Authority over warmth. Numbers over chrome. The interface signals "this is research-grade work" through what it withholds, not what it adds.

### Aesthetic Direction

- **Theme**: dark.
- **References**: Bloomberg Terminal, TradingView pro mode, Federal Reserve research tools, Linear's command palette aesthetic, Datadog/Grafana stripped of chartjunk.
- **Anti-references**: civic-infographic register (Urban Institute / Pew — what this is replacing), generic SaaS dashboards, glassmorphism / glow / gradient-heavy modern web.
- **Choropleth ramp**: single-hue sequential, dim → saturated burnt amber.
- **Typography**: **Funnel Display** + **Funnel Sans** + **JetBrains Mono** (all OFL/free). Aspirational paid: **Söhne**. **Banned reflex defaults**: Inter, DM Sans, Plus Jakarta, Fraunces, Newsreader, Instrument *, Outfit, IBM Plex *, Space *, Cormorant, Crimson, Playfair, Lora, Syne.
- **Palette** (OKLCH): bg `0.18 0.005 240`, surface-1 `0.22 0.005 240`, rule `0.34 0.008 240`, text-primary `0.96 0.003 240`, accent `0.78 0.18 65` (burnt amber).
- **Motion**: minimal, deliberate. Crossfade ~250ms ease-out-quart. No bounce, no elastic.

### Design Principles

1. **Density is honesty.** Don't pad data with whitespace.
2. **Hairlines, not boxes.** 1px rules separate sections; no cards-with-shadows.
3. **One accent color.** Used only for highest-risk tracts, active toggle state, headline AUC, focus rings.
4. **Tabular figures, always.** Mono + tabular-nums for every number.
5. **The map is the page.** Full-bleed dark canvas; controls float above it.
6. **Reads at 10 feet AND at 18 inches.** Same interface works at both distances.
