name: Build logos (mapping)

on:
  workflow_dispatch:

permissions:
  contents: write

jobs:
  logos:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Build ticker-named logos from mapping
        run: |
          python - <<'PY'
          import sys, csv, pathlib, shutil
          repo = pathlib.Path(__file__).resolve().parents[2]
          map_csv = repo/'logos'/'_map'/'logos.csv'
          src_root = repo/'logos'   # where your source logo files live (by country/exchange)
          out_root = repo/'logos'   # write canonical/ticker files also under logos/

          # example columns: group,country_slug,country_name,exchange,ticker,company_name,logo_file
          with map_csv.open(newline='', encoding='utf-8') as f:
            r = csv.DictReader(f)
            n = 0
            for row in r:
              ex = (row.get('exchange') or '').strip()
              tk = (row.get('ticker') or '').strip()
              lf = (row.get('logo_file') or '').strip()
              if not (ex and tk and lf):
                continue

              # find the file under logos/<country>/<exchange>/<logo_file> or logos/<exchange>/<logo_file>
              candidates = list(src_root.rglob(lf))
              if not candidates:
                print(f"[skip] not found: {lf}")
                continue

              src = candidates[0]
              # write a clean ticker-named copy alongside your logos tree:
              # e.g., logos/<exchange>/<TICKER>.png  (or keep .webp/.png extension)
              ext = src.suffix
              dst = out_root/ex/f"{tk.upper()}{ext}"
              dst.parent.mkdir(parents=True, exist_ok=True)
              if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
                shutil.copy2(src, dst)
                n += 1
                print(f"[ok] {dst.relative_to(repo)}")
          print(f"[DONE] wrote/updated {n} logo files")
          PY

      - name: Commit & push dist logos
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          # IMPORTANT: only add 'logos' — do NOT add 'dist' here
          git add logos
          git commit -m "Logos: refresh mapping $(date -u +'%Y-%m-%dT%H:%M:%SZ')" || echo "No logo changes"
          git push
