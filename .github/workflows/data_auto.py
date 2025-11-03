name: Auto download market data and build & deploy SSG
on:
  workflow_dispatch:
  schedule:
    - cron: "45 6 * * 1-5"    # APAC ex-India
    - cron: "15 10 * * 1-5"   # India (NSE/BSE)
    - cron: "15 11 * * 0-4"   # Gulf / Middle East
    - cron: "15 16 * * 1-5"   # Europe & UK
    - cron: "15 21 * * 1-5"   # US & Canada

permissions:
  contents: write
  pages: write
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 600

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install pandas jinja2 python-slugify

      - name: Ensure country flags present (robust)
        run: |
          mkdir -p dist/logos/countryflags
          rsync -a logos/countryflags/ dist/logos/countryflags/ 2>/dev/null || true
          if [ -z "$(ls -A dist/logos/countryflags 2>/dev/null)" ]; then
            cp -r logos/countryflags/* dist/logos/countryflags/ 2>/dev/null || true
          fi

      # ✅ NEW: Ensure main site logo always exists
      - name: Verify site logo present
        run: |
          mkdir -p dist/logos/site
          if [ -f logos/site/logo.png ]; then
            cp -f logos/site/logo.png dist/logos/site/logo.png
            echo "✅ Copied and verified site logo: dist/logos/site/logo.png"
          else
            echo "❌ logos/site/logo.png not found!"
            exit 1
          fi

      - name: Run data downloader
        run: python -u scripts/data_auto.py

      - name: Build site
        run: python -u scripts/build.py

      - name: Rebuild search index
        run: python -u scripts/search_setup.py

      - name: Inject last-7 performance
        run: python -u scripts/build_last7.py

      - name: Inject logos from mapping
        run: python -u scripts/inject_logos.py

      - name: Apply V2 rebuild theme
        run: python -u scripts/theme_rebuild_v2.py

      - name: Cleanup old sitemap folder
        run: |
          rm -rf dist/sitemaps || true
          echo "🧹 Old /sitemaps folder removed"

      - name: Split sitemap into chunks + index
        run: python -u scripts/sitemap_split.py

      - name: Upload Pages artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: dist

      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4

      - name: Notify Search Engines (Google, Bing, Yandex, DuckDuckGo)
        if: success()
        run: |
          SITEMAP_URL="https://stockpricepredictions.com/sitemap.xml"
          echo "🔍 Pinging search engines with $SITEMAP_URL ..."
          curl -fsS "https://www.google.com/ping?sitemap=${SITEMAP_URL}" -o /dev/null || true
          curl -fsS "https://www.bing.com/ping?sitemap=${SITEMAP_URL}" -o /dev/null || true
          curl -fsS "https://yandex.com/ping?sitemap=${SITEMAP_URL}" -o /dev/null || true
          curl -fsS "https://duckduckgo.com/ping?sitemap=${SITEMAP_URL}" -o /dev/null || true
          echo "✅ Sitemap ping sent."
