#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# Make imports reliable both locally and in GitHub Actions
# -----------------------------------------------------------------------------
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.market_time import get_prediction_date  # noqa: E402

# -----------------------------------------------------------------------------
# Existing imports your file already used
# (keep them – these are typical ones used in your project)
# -----------------------------------------------------------------------------
import os
import csv
import json
import math
import shutil
from datetime import datetime, date
from collections import defaultdict

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape
from slugify import slugify

# -----------------------------------------------------------------------------
# CONFIG (same defaults you had)
# -----------------------------------------------------------------------------
DATA_DIR = REPO_ROOT / "Data"
LAST_DIR = DATA_DIR / "LastTradingDay"
HIST_DIR = DATA_DIR / "Historical"
DIST_DIR = REPO_ROOT / "dist"
STATIC_DIR = REPO_ROOT / "static"
LOGOS_DIR = REPO_ROOT / "logos"

TEMPLATES_DIR = REPO_ROOT / "templates" if (REPO_ROOT / "templates").exists() else REPO_ROOT

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"])
)

# If your project uses inline templates, leave this; otherwise Jinja will find template files.
GROUP_TMPL = env.from_string("""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>{{ title }}</title>
<link rel="stylesheet" href="/styles.css"></head><body class="container">
<div class="hero"><div class="breadcrumbs"><a href="/">Home</a></div>
<h1 class="h1">{{ title }}</h1><p class="small">Last build: {{ build_time }}</p></div>
<div class="card">
<div class="toolbar">
  <input id="search" class="input" placeholder="Search symbol or name">
  <select id="sector" class="select"><option value="">All sectors</option>
    {% for s in sectors %}<option value="{{ s }}">{{ s }}</option>{% endfor %}
  </select>
</div>
<div class="table-wrap"><table class="table" id="tbl">
<thead><tr>
  <th>symbol</th><th>exchange</th><th>currency</th>
  <th>sector</th><th>industry</th>
  <th>change%</th><th>close</th><th>description</th>
  <th>AI</th>
</tr></thead>
<tbody>
{% for r in rows %}
<tr>
  <td><a href="{{ r.page_url }}">{{ r.symbol }}</a></td>
  <td>{{ r.exchange }}</td>
  <td>{{ r.currency }}</td>
  <td>{{ r.sector }}</td>
  <td>{{ r.industry }}</td>
  <td class="chg {{ 'up' if (r.change_pct or 0) > 0 else 'down' if (r.change_pct or 0) < 0 else '' }}">
    {% if r.change_pct is not none %}{{ '%.2f'|format(r.change_pct) }}%{% else %}-{% endif %}
  </td>
  <td>{{ '' if r.close is none else '%.2f'|format(r.close) }}</td>
  <td>{{ r.description }}</td>
  <td><a class="chip" href="{{ r.pred_url }}">AI&nbsp;Prediction</a></td>
</tr>
{% endfor %}
</tbody></table></div></div>
<script src="/app.js"></script>
</body></html>
""")

PRED_TMPL = env.from_string("""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>AI Analysis of {{ symbol }} Tomorrow | {{ name }} Stock Prediction</title>
<link rel="stylesheet" href="/styles.css"></head>
<body class="container">
<div class="hero">
  <div class="breadcrumbs"><a href="/">Home</a></div>
  <h1 class="h1">AI Analysis of {{ symbol }} Tomorrow | {{ name }} Stock Prediction</h1>
  <p class="small">Next-day stock movement from yesterday’s OHLC</p>
  <p class="small">Last build: {{ build_time }}</p>
</div>

<div class="card">
  <h2 class="h2">AI Analysis of {{ symbol }} ({{ name }})</h2>
  <p>Region: {{ region }} · Country: {{ country }} · Exchange: {{ exchange }}</p>
  <p>OHLC: O {{ o }}, H {{ h }}, L {{ l }}, C {{ c }} · Change%:
     <span class="{{ 'up' if (chg or 0)>0 else 'down' if (chg or 0)<0 else '' }}">{{ chg_str }}</span>
  </p>
  <div class="card" style="margin-top:12px">
    <h3 class="h3">Prediction for {{ next_date }}</h3>
    <p>Model signal based on the latest day’s action.</p>
  </div>
</div>

{% if last7 %}
<div class="card">
  <h2 class="h2">Last 7-Day Performance</h2>
  <div class="badge">Last 7-Day Accuracy: <strong>{{ last7.win_pct }}</strong> ({{ last7.wins }}/7)</div>
  <div class="table-wrap" style="margin-top:10px">
    <table class="table">
      <thead><tr>
        <th>Date</th><th>AI Prediction</th><th class="text-right">Actual Close</th><th class="text-center">Result</th>
      </tr></thead>
      <tbody>
        {% for r in last7.rows %}
        <tr>
          <td>{{ r.date }}</td>
          <td>{{ r.pred }}</td>
          <td class="text-right">{{ r.actual }}</td>
          <td class="text-center {{ 'up' if r.result=='Win' else 'down' }}">{{ r.result }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endif %}

<div class="footer">E-E-A-T: Author SPP Research · Org: SPP Labs · Contact hello@stockpricepredictions.com</div>
</body></html>
""")

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def ensure_dist():
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    # Fast logos copy (only first time)
    if os.getenv("SKIP_LOGOS") != "1":
        if LOGOS_DIR.exists():
            (DIST_DIR / "logos").mkdir(exist_ok=True)
            # shallow copy (existing repo already has logos in dist from workflow step)
            for p in LOGOS_DIR.rglob("*"):
                if p.is_file():
                    out = DIST_DIR / p.relative_to(LOGOS_DIR.parent)
                    out.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, out)

def read_country_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    # normalize field names used in pages
    rename_map = {
        "Close": "close",
        "Change%": "change_pct",
        "symbol": "symbol",
        "exchange": "exchange",
        "currency": "currency",
        "sector": "sector",
        "industry": "industry",
        "description": "description",
        "open": "open",
        "high": "high",
        "low": "low"
    }
    df = df.rename(columns=rename_map)
    # keep only first occurrence per (symbol, exchange) – prefer NSE over BSE if duplicated
    if {"symbol", "exchange"}.issubset(df.columns):
        df = (df
              .sort_values(["symbol", "exchange"])
              .drop_duplicates(subset=["symbol", "exchange"], keep="first"))
    return df

def out_path_for(region, country, slug, page):
    if page == "group":
        return DIST_DIR / "groups" / slug / "index.html"
    if page == "pred":
        return DIST_DIR / region / country / slug / "prediction-tomorrow" / "index.html"
    if page == "stock":
        return DIST_DIR / region / country / slug / "index.html"
    raise ValueError(page)

def make_urls(region, country, symbol, name):
    sym_slug = slugify(symbol.lower())
    base = f"/{region}/{country}/{sym_slug}"
    return {
        "page_url": f"{base}/",
        "pred_url": f"{base}/prediction-tomorrow/"
    }

def render_group(region, country, df: pd.DataFrame):
    sectors = sorted([s for s in df["sector"].dropna().unique().tolist() if s])
    rows = []
    for _, r in df.iterrows():
        urls = make_urls(region, country, r.get("symbol",""), r.get("description",""))
        rows.append({
            "symbol": r.get("symbol"),
            "exchange": r.get("exchange"),
            "currency": r.get("currency"),
            "sector": r.get("sector"),
            "industry": r.get("industry"),
            "change_pct": None if pd.isna(r.get("change_pct")) else float(r.get("change_pct")),
            "close": None if pd.isna(r.get("close")) else float(r.get("close")),
            "description": r.get("description"),
            **urls
        })
    html = GROUP_TMPL.render(
        title=f"{country.title()} — stocks",
        build_time=datetime.utcnow().isoformat(timespec="seconds")+"Z",
        rows=rows, sectors=sectors
    )
    out = out_path_for("groups", country, slugify(country), "group")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

def render_prediction(region, country, r: dict, hist_df: pd.DataFrame):
    symbol = r["symbol"]
    # next date using correct market calendar
    today_utc = datetime.utcnow().date()
    next_date = get_prediction_date(country=country, exchange=r.get("exchange", ""), today=today_utc)
    # last-7 (if injected file exists, build_last7.py will write JSON next to page path)
    last7_path = DIST_DIR / region / country / slugify(symbol.lower()) / "prediction-tomorrow" / "_last7.json"
    last7 = None
    if last7_path.exists():
        try:
            last7 = json.loads(last7_path.read_text(encoding="utf-8"))
        except Exception:
            last7 = None

    def fmt(x):
        return "-" if x is None or pd.isna(x) else f"{x:.2f}"

    html = PRED_TMPL.render(
        symbol=symbol,
        name=r.get("description",""),
        region=region.replace("-", " ").title(),
        country=country.replace("-", " ").title(),
        exchange=r.get("exchange",""),
        o=fmt(r.get("open")),
        h=fmt(r.get("high")),
        l=fmt(r.get("low")),
        c=fmt(r.get("close")),
        chg=r.get("change_pct"),
        chg_str="-" if pd.isna(r.get("change_pct")) else f"{float(r.get('change_pct')):.2f}%",
        next_date=str(next_date),
        last7=last7,
        build_time=datetime.utcnow().isoformat(timespec="seconds")+"Z",
    )
    out = out_path_for(region, country, slugify(symbol.lower()), "pred")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

def build_all():
    ensure_dist()

    build_time = datetime.utcnow().isoformat(timespec="seconds")+"Z"
    print(f"== Build start @ {build_time} ==")

    # Walk LastTradingDay tree: Region / Country / country.csv
    if not LAST_DIR.exists():
        print("No Data/LastTradingDay – nothing to build")
        return

    for region_dir in sorted(LAST_DIR.iterdir()):
        if not region_dir.is_dir():
            continue
        region = region_dir.name  # e.g., "Asia - Pacific"
        region_slug = slugify(region)
        for country_dir in sorted(region_dir.iterdir()):
            if not country_dir.is_dir():
                continue
            country = country_dir.name   # e.g., "india"
            country_slug = slugify(country)
            csv_path = country_dir / f"{country}.csv"
            df = read_country_csv(csv_path)
            if df.empty:
                continue

            # group page under /groups/<country>/
            try:
                render_group(region_slug, country_slug, df)
            except Exception as e:
                print(f"[WARN] group render failed for {country}: {e}")

            # per-stock pages (+ prediction)
            for _, row in df.iterrows():
                rec = row.to_dict()
                try:
                    render_prediction(region_slug, country_slug, rec, None)
                except Exception as e:
                    print(f"[WARN] prediction page failed for {rec.get('symbol')}: {e}")

    # copy static assets
    if STATIC_DIR.exists():
        for p in STATIC_DIR.iterdir():
            if p.is_file():
                shutil.copy2(p, DIST_DIR / p.name)

    print(f"Build complete -> {DIST_DIR}")

def main():
    build_all()

if __name__ == "__main__":
    main()
