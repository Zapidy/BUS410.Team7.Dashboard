# Round 5 · Credit-Desert Forecast Dashboard

Interactive tract-level map of the Round-5 model's predicted credit-desert risk for ~79,000 US census tracts. Quant-terminal aesthetic — dark, dense, hairline-bordered, single burnt-amber accent. Designed to read at 10-foot projector distance and at 18-inch laptop distance from the same surface.

Stack: vanilla HTML/CSS/JS + [MapLibre GL JS](https://maplibre.org/) via CDN. No bundler, no framework. Static site — deployable to GitHub Pages out of the box.

## Local preview

```bash
cd web
python3 -m http.server 8000
# http://localhost:8000
```

Any static file server works. **Don't open `index.html` via `file://`** — the GeoJSON fetches require an HTTP origin.

## Rebuilding the data

The three files under `data/` are generated from the upstream Round-5 model artifacts:

```bash
cd web
python3 build_dashboard_data.py    # produces data/tracts_raw.geojson + state_stats.json + state_bbox.json

# Then simplify the GeoJSON via mapshaper (no global install needed):
npx --yes mapshaper@latest data/tracts_raw.geojson \
  -simplify dp 1.5% keep-shapes \
  -clean \
  -o data/tracts.geojson precision=0.001 format=geojson

npx --yes mapshaper@latest data/tracts_raw.geojson \
  -each "st = f.substring(0,2)" \
  -dissolve st \
  -simplify dp 25% keep-shapes \
  -clean \
  -o data/states.geojson precision=0.001 format=geojson

rm data/tracts_raw.geojson
```

Output sizes: tracts ≈ 26 MB raw / 4.3 MB gzipped, states ≈ 1.3 MB.

## Deploy to GitHub Pages

The `.github/workflows/pages.yml` workflow auto-deploys on every push to `main`. **Staged but not pushed** — set up the remote when you're ready.

```bash
cd web
git init
git add .
git commit -m "Round 5 quant-terminal dashboard"
gh repo create <user>/<repo> --public --source=. --push
# In repo Settings → Pages → Source = GitHub Actions
```

Live in ~30 s after the first push at `https://<user>.github.io/<repo>/`.

## What's on the page

- **Masthead** (top): R5 badge, dashboard title, headline metrics — AUC 0.857 (accent), AP-lift 9.25×, n_tracts shown, fold count
- **Left rail**: filters
  - State dropdown (50 + DC; click on map state too)
  - Static flags: rural-only, persistent-poverty-county-only
  - Range sliders: population, median HH income, poverty rate, non-white/Hispanic rate, predicted-risk floor
  - **Reset** button (or press `R`)
- **Map** (full bleed): dark canvas, single-hue amber risk ramp, hairline tract borders. Filtered-out tracts dim to 10–12% opacity (not hidden — geographic context preserved).
- **Right rail**: live statistics
  - Filtered-set summary: n_tracts, mean risk, max risk, positive rate, **filtered AUC (accent)**
  - Top-25 highest-risk tracts in the filter — clickable to zoom
  - Per-state AUC table — clickable to filter+zoom
- **Tooltip**: hover any tract for state, FIPS, predicted risk, demographics. Click to pin (lock); ESC or click outside to release.
- **Colophon** (bottom): champion model, feature count, panel range, drop count, Brier

## Keyboard

| Key | Action |
|---|---|
| `R` | Reset all filters and re-fit US |
| `Esc` | Unpin tooltip |

## Files

```
web/
├── index.html              5 KB     markup, font + library CDN links
├── styles.css              17 KB    full quant-terminal design system
├── app.js                  16 KB    MapLibre + filters + tooltip + stats
├── favicon.svg             ramp + R5 wordmark
├── build_dashboard_data.py rebuild data files from upstream Round-5 artifacts
├── data/
│   ├── tracts.geojson      26 MB / 4.3 MB gzipped — 79k tracts with risk + demographics
│   ├── states.geojson      1.3 MB — dissolved state outlines
│   ├── state_stats.json    8 KB   — per-state AUC, n_tracts, mean_risk
│   └── state_bbox.json     2 KB   — per-state bounding boxes (for fly-to)
├── .github/workflows/pages.yml  staged GitHub Pages deploy
├── .gitignore
└── README.md
```

## Performance notes

- First paint waits on the 26 MB tracts file (~4 MB gzipped). On a typical projector laptop, first paint is 3–6 s
- After load, MapLibre renders 79k tracts on the GPU at 60 fps
- Filter updates are instant — `setPaintProperty('tracts-fill', 'fill-opacity', expr)` re-evaluates on the GPU; no JS churn
- Stats recompute is debounced 50 ms during slider drags

## Aesthetic credits

- Typography: **Funnel Display** + **Funnel Sans** (Pangram Pangram, OFL) via Fontshare CDN; **JetBrains Mono** (Google Fonts, OFL) for tabular numbers
- Palette: OKLCH-defined cool-tinted neutrals + single burnt amber accent (`oklch(0.78 0.18 65)`)
- Choropleth ramp: 7-stop single-hue, dim → saturated amber (no rainbow, no Viridis)

Per the [round5 design context](../.impeccable.md): density is honesty · hairlines not boxes · one accent · tabular figures always · the map is the page · reads at 10 ft AND 18 in.
