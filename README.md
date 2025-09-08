# SSG Starter for StockPricePredictions.com

**Goal:** Push CSVs under `Data/` to GitHub; GitHub Actions builds SEO pages into `gh-pages` automatically.

## How it works
- Your repo contains:
  - `Data/` (you push daily)
  - `logos/` (you upload once, including `logos_index.json`)
  - `scripts/build.py`, `templates/`, `static/`, `config.json`
  - `.github/workflows/ssg.yml`

- On each push (or nightly), the workflow runs `scripts/build.py`:
  1. Finds the *latest date* folder inside `Data/` (e.g., `03.09.2025`).
  2. Scans region/country CSVs.
  3. Generates pages at `dist/region/country/stock-name-slug/index.html` and supporting indexes.
  4. Builds `sitemap.xml` and `robots.txt`.
  5. Publishes `dist/` to the `gh-pages` branch (served by GitHub Pages).

## CSV schema expected (columns)
`symbol, description, exchange, sector, industry, open, high, low, close`

Case-insensitive. Extra columns are ignored.

## Logos
Provide a `logos/logos_index.json` that maps `{ "EXCHANGE|SYMBOL": "relative/path/to/logo.png" }`.
Images live under `logos/`. The site links to them directly.

## Local build
```bash
pip install -r requirements.txt
python scripts/build.py
# output in ./dist
```

## Configure Pages
- Settings → Pages → Source: **Deploy from a branch** → Branch: `gh-pages` (root).
- Set Custom domain: `stockpricepredictions.com` (optional).

## Trigger rules
- Pushes affecting `Data/**`, `scripts/**`, `templates/**`, `static/**`, `config.json` rebuild the site.
- A nightly cron (`23:05 UTC`) also rebuilds.

## SEO/E‑E‑A‑T
- Titles, descriptions, canonical URLs, and keyword injection powered by `config.json` and templates.
- Breadcrumbs and clean hierarchy for crawlability.
- Per‑stock pages also at `/by-name/<slug>/` for name‑based discovery.
- Sitemap includes all pages.

## Updating keywords
Edit `config.json` → `keywords`. Rebuilds will automatically place them into `<meta name="keywords">`.

---

Made for your dataset + workflow. Drop in your `Data/` and push!