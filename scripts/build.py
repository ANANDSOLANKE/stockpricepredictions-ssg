#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Static Site Generator for StockPricePredictions (robust columns)
- Reads CSVs from Data/<DD.MM.YYYY>/<Region>/<country>.csv
- Normalizes CSV headers to lowercase; tolerates missing/variant columns
- Generates HTML pages per stock, and an interactive homepage powered by static/app.js
- Produces /data/index.json for the homepage Regions→Countries→Exchanges→Stocks explorer
- Copies static assets: styles.css, app.js, favicon.ico
"""

from pathlib import Path
import shutil, json
import pandas as pd
from datetime import datetime

# ------------------------------
# Paths
# ------------------------------
ROOT   = Path(__file__).resolve().parent.parent  # repo root
DATA   = ROOT / "Data"
DIST   = ROOT / "dist"
STATIC = ROOT / "static"

# ------------------------------
# Helpers
# ------------------------------
def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    out = []
    prev_dash = False
    for ch in s:
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        else:
            if not prev_dash:
                out.append("-")
            prev_dash = True
    res = "".join(out).strip("-")
    return res or "item"

def latest_date_folder() -> Path:
    """Pick the most recent 'DD.MM.YYYY' folder under Data/."""
    if not DATA.exists():
        raise FileNotFoundError("ERROR: Data/ folder not found at repo root.")
    dated = []
    for p in DATA.iterdir():
        if p.is_dir():
            try:
                _ = datetime.strptime(p.name, "%d.%m.%Y")
                dated.append(p)
            except Exception:
                # ignore non-date folders
                pass
    if not dated:
        raise FileNotFoundError("ERROR: No dated subfolder in Data/ (expected DD.MM.YYYY).")
    # newest by parsed date
    dated.sort(key=lambda x: datetime.strptime(x.name, "%d.%m.%Y"), reverse=True)
    return dated[0]

def read_csv_robust(path: Path) -> pd.DataFrame:
    """Read CSV and normalize headers to lowercase, trimmed.
       Ensure canonical columns exist, even if missing in source."""
    df = pd.read_csv(path, low_memory=False)
    # normalize headers
    df.columns = [str(c).strip().lower() for c in df.columns]

    # map common variants to canonical names
    aliases = {
        "description": ["name", "company", "companyname", "securityname"],
        "exchange":    ["exch", "market", "exchange_name"],
        "sector":      ["sectorname", "industrysector"],
        "industry":    ["industryname"],
        "open":        ["o", "opn"],
        "high":        ["h", "hi"],
        "low":         ["l", "lo"],
        "close":       ["c", "cls", "closing"],
        "signal":      ["prediction", "trend"],
    }

    def ensure(col):
        if col not in df.columns:
            # look for an alias
            for alt in aliases.get(col, []):
                if alt in df.columns:
                    df.rename(columns={alt: col}, inplace=True)
                    return
            # not found → create
            df[col] = "" if col in ("symbol","description","exchange","sector","industry","signal") else None

    # canonical set (symbol must exist; if not, create empty)
    for need in ["symbol","description","exchange","sector","industry","open","high","low","close","signal"]:
        ensure(need)

    # coerce numeric OHLC (where present)
    for c in ["open","high","low","close"]:
        try:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        except Exception:
            pass

    # fill strings
    for c in ["symbol","description","exchange","sector","industry","signal"]:
        df[c] = df[c].fillna("").astype(str)

    return df

def copy_static():
    (DIST / "static").mkdir(parents=True, exist_ok=True)

    # styles.css
    css_src = STATIC / "styles.css"
    if css_src.exists():
        shutil.copy2(css_src, DIST / "static" / "styles.css")
    else:
        # minimal fallback so page is readable
        (DIST / "static" / "styles.css").write_text(
            "body{font-family:system-ui;background:#0b1220;color:#e8f0fe;margin:0}"
            ".container{max-width:1100px;margin:0 auto;padding:24px}"
            "h1,h2{margin:.5rem 0} .hidden{display:none}"
            "table{border-collapse:collapse;width:100%}"
            "th,td{border-bottom:1px solid #1f2a44;padding:6px 8px}",
            encoding="utf-8"
        )

    # app.js
    app_src = STATIC / "app.js"
    if app_src.exists():
        shutil.copy2(app_src, DIST / "static" / "app.js")
    else:
        (DIST / "static" / "app.js").write_text(
            "console.error('Missing static/app.js at build time.');",
            encoding="utf-8"
        )

    # favicon (optional)
    fav = STATIC / "favicon.ico"
    if fav.exists():
        shutil.copy2(fav, DIST / "favicon.ico")

def write_home():
    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Stock Predictions Explorer</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <div class="container">
    <header style="text-align:center;margin-bottom:16px;">
      <h1>🌍 Stock Predictions Explorer</h1>
      <p style="color:#9fb3c8">AI forecast for tomorrow’s prices — browse by Region → Country → Exchange</p>
    </header>

    <section>
      <h2>Regions</h2>
      <div id="regions"></div>
    </section>

    <section id="countries-section" class="hidden" style="margin-top:16px;">
      <h2>Countries</h2>
      <div id="countries"></div>
    </section>

    <section id="exchanges-section" class="hidden" style="margin-top:16px;">
      <h2>Exchanges</h2>
      <div id="exchanges"></div>
    </section>

    <section id="stocks-section" class="hidden" style="margin-top:16px;">
      <h2>Stocks</h2>
      <div id="stocks"></div>
    </section>
  </div>
  <script src="/static/app.js"></script>
</body>
</html>"""
    (DIST / "index.html").write_text(html, encoding="utf-8")

# ------------------------------
# Build
# ------------------------------
def build():
    # clean dist
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True, exist_ok=True)

    # copy static assets (css/js/favicon)
    copy_static()

    # pick date folder
    date_dir = latest_date_folder()

    # JSON structure for app.js
    site = {"data": {}}

    # iterate regions
    for region_dir in sorted([p for p in date_dir.iterdir() if p.is_dir()], key=lambda x: x.name.lower()):
        r_name = region_dir.name
        r_slug = slugify(r_name)
        site["data"][r_slug] = {"label": r_name, "countries": {}}

        # each country is a CSV file
        for csv_path in sorted(region_dir.glob("*.csv"), key=lambda x: x.name.lower()):
            country_name = csv_path.stem.replace("-", " ").title()
            c_slug = slugify(country_name)
            site["data"][r_slug]["countries"][c_slug] = {"label": country_name, "exchanges": {}}

            # read CSV robustly
            df = read_csv_robust(csv_path)

            # group by exchange (fill 'unknown' if blank)
            if "exchange" not in df.columns:
                df["exchange"] = ""

            for exch, df_ex in df.groupby(df["exchange"].replace("", "unknown"), dropna=False):
                e_name = exch or "unknown"
                e_slug = slugify(e_name)
                exch_obj = {"label": e_name, "stocks": []}
                site["data"][r_slug]["countries"][c_slug]["exchanges"][e_slug] = exch_obj

                # create stock pages and build JSON array
                for _, row in df_ex.iterrows():
                    sym = str(row.get("symbol", "")).strip()
                    desc = str(row.get("description", "")).strip() or sym
                    sec = str(row.get("sector", "")).strip()
                    o = row.get("open", None)
                    h = row.get("high", None)
                    l = row.get("low",  None)
                    c = row.get("close", None)
                    sig = str(row.get("signal", "")).strip()

                    s_slug = slugify(desc or sym)
                    stock_dir = DIST / r_slug / c_slug / e_slug / s_slug
                    stock_dir.mkdir(parents=True, exist_ok=True)

                    # very simple stock page (SEO pages are separate from JS explorer)
                    stock_html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{desc} — Stock Prediction</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <div class="container">
    <h1>{desc}</h1>
    <p><strong>Symbol:</strong> {sym} · <strong>Exchange:</strong> {e_name} · <strong>Sector:</strong> {sec}</p>
    <table>
      <thead><tr><th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Signal</th></tr></thead>
      <tbody><tr>
        <td>{'' if pd.isna(o) else f'{float(o):.2f}'}</td>
        <td>{'' if pd.isna(h) else f'{float(h):.2f}'}</td>
        <td>{'' if pd.isna(l) else f'{float(l):.2f}'}</td>
        <td>{'' if pd.isna(c) else f'{float(c):.2f}'}</td>
        <td>{sig}</td>
      </tr></tbody>
    </table>
    <p><a href="/">← Back to Home</a></p>
  </div>
</body>
</html>"""
                    (stock_dir / "index.html").write_text(stock_html, encoding="utf-8")

                    # add to JSON list for the exchange
                    exch_obj["stocks"].append({
                        "symbol": sym,
                        "name": desc,            # app.js reads name/description
                        "description": desc,
                        "sector": sec,
                        "open": None if pd.isna(o) else float(o),
                        "high": None if pd.isna(h) else float(h),
                        "low":  None if pd.isna(l) else float(l),
                        "close": None if pd.isna(c) else float(c),
                        "signal": sig,
                    })

    # write JSON for the explorer
    data_dir = DIST / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "index.json").write_text(json.dumps(site, ensure_ascii=False), encoding="utf-8")

    # write interactive homepage (uses static/app.js to read /data/index.json)
    write_home()

    print("Build complete →", DIST)

if __name__ == "__main__":
    build()
