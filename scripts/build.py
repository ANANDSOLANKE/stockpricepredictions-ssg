#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Static Site Generator for StockPricePredictions
- Reads CSVs from Data/<date>/<region>/<country>.csv
- Generates HTML pages per stock, exchange, country, region
- Copies static assets (styles.css, app.js, favicon.ico) into dist/
"""

import os, sys, shutil, json
from pathlib import Path
import pandas as pd
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "Data"
DIST = ROOT / "dist"
STATIC = ROOT / "static"

# ------------------------------
# Helpers
# ------------------------------
def slugify(s: str) -> str:
    return (
        s.lower()
        .replace("&", "and")
        .replace(" ", "-")
        .replace("/", "-")
        .replace("_", "-")
    )

def latest_date_folder():
    if not DATA.exists():
        raise FileNotFoundError("Data/ folder not found")
    subs = [p for p in DATA.iterdir() if p.is_dir()]
    if not subs:
        raise FileNotFoundError("No dated subfolder in Data/")
    # Expect names like DD.MM.YYYY
    def parse_date(name):
        try:
            return datetime.strptime(name, "%d.%m.%Y")
        except Exception:
            return datetime.min
    latest = max(subs, key=lambda p: parse_date(p.name))
    return latest

# ------------------------------
# Core Build
# ------------------------------
def build():
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    date_folder = latest_date_folder()
    site_index = {"data": {}}

    # Walk regions/countries
    for region in sorted(date_folder.iterdir()):
        if not region.is_dir():
            continue
        rslug = slugify(region.name)
        site_index["data"][rslug] = {"label": region.name, "countries": {}}
        for country_file in sorted(region.glob("*.csv")):
            cslug = slugify(country_file.stem)
            df = pd.read_csv(country_file)
            countries = site_index["data"][rslug]["countries"]
            countries[cslug] = {"label": country_file.stem, "exchanges": {}}

            for exch in df["exchange"].unique():
                eslug = slugify(str(exch))
                exch_df = df[df["exchange"] == exch]
                exchanges = countries[cslug]["exchanges"]
                exchanges[eslug] = {"label": exch, "stocks": []}

                for _, row in exch_df.iterrows():
                    stock_slug = slugify(str(row["description"]))
                    stock_dir = DIST / rslug / cslug / eslug / stock_slug
                    stock_dir.mkdir(parents=True, exist_ok=True)
                    # stock page
                    html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{row['description']} — Stock Prediction</title>
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <h1>{row['description']}</h1>
  <p>Symbol: {row['symbol']}</p>
  <p>Exchange: {row['exchange']}</p>
  <p>Sector: {row.get('sector','')}</p>
  <p>Open: {row['open']}, High: {row['high']}, Low: {row['low']}, Close: {row['Close']}</p>
  <p>Signal: {row.get('signal','')}</p>
  <p><a href="/">Home</a></p>
</body>
</html>
"""
                    (stock_dir / "index.html").write_text(html, encoding="utf-8")

                    exchanges[eslug]["stocks"].append(
                        {
                            "symbol": row["symbol"],
                            "description": row["description"],
                            "sector": row.get("sector", ""),
                            "open": row.get("open", ""),
                            "high": row.get("high", ""),
                            "low": row.get("low", ""),
                            "close": row.get("Close", ""),
                            "signal": row.get("signal", ""),
                        }
                    )

    # Write site index JSON
    data_dir = DIST / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "index.json").write_text(json.dumps(site_index, indent=2), encoding="utf-8")

    # Copy static assets
    static_out = DIST / "static"
    static_out.mkdir(parents=True, exist_ok=True)

    # CSS
    css_src = STATIC / "styles.css"
    if css_src.exists():
        shutil.copy2(css_src, static_out / "styles.css")
    else:
        (static_out / "styles.css").write_text("body{font-family:sans-serif}", encoding="utf-8")

    # JS
    js_src = STATIC / "app.js"
    if js_src.exists():
        shutil.copy2(js_src, static_out / "app.js")
    else:
        (static_out / "app.js").write_text("console.error('app.js missing');", encoding="utf-8")

    # Favicon (optional)
    fav_src = STATIC / "favicon.ico"
    if fav_src.exists():
        shutil.copy2(fav_src, DIST / "favicon.ico")

    # Home index
    home = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Stock Predictions Explorer</title>
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <div id="app" class="container">
    <h1>🌍 Stock Predictions Explorer</h1>
    <p>AI forecast for tomorrow’s prices — browse by Region → Country → Exchange</p>
    <h2>Regions</h2>
    <div id="regions"></div>
    <div id="countries-section" class="hidden"><h2>Countries</h2><div id="countries"></div></div>
    <div id="exchanges-section" class="hidden"><h2>Exchanges</h2><div id="exchanges"></div></div>
    <div id="stocks-section" class="hidden"><h2>Stocks</h2><div id="stocks"></div></div>
  </div>
  <script src="/static/app.js"></script>
</body>
</html>
"""
    (DIST / "index.html").write_text(home, encoding="utf-8")


if __name__ == "__main__":
    build()
    print("Build complete.")
