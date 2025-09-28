#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re, json, shutil, datetime
from pathlib import Path
import pandas as pd

# ---------- Paths & Config ----------
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "Data"
DIST = ROOT / "dist"

CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
BASE_URL = CFG.get("base_url", "").rstrip("/")
DEFAULT_REGION = re.sub(r"[^a-z0-9]+", "-", CFG.get("default_region","").strip().lower()).strip("-")
DEFAULT_COUNTRY = re.sub(r"[^a-z0-9]+", "-", CFG.get("default_country","").strip().lower()).strip("-")

# ---------- Helpers ----------
def find_latest_date_folder():
    if not DATA_DIR.exists():
        raise SystemExit("Missing Data/ directory at repo root.")
    candidates = []
    for p in DATA_DIR.iterdir():
        if p.is_dir() and re.match(r"^\d{2}\.\d{2}\.\d{4}$", p.name):
            d = datetime.datetime.strptime(p.name, "%d.%m.%Y").date()
            candidates.append((d, p))
    if not candidates:
        raise SystemExit("No dated folder like DD.MM.YYYY inside Data/.")
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1], candidates[0][0]

def next_business_day(d: datetime.date):
    wd = d.weekday()
    if wd == 4:  # Fri
        return d + datetime.timedelta(days=3)
    if wd == 5:  # Sat
        return d + datetime.timedelta(days=2)
    return d + datetime.timedelta(days=1)

def classify(o,h,l,c):
    rng = max(h,l) - min(h,l)
    body = abs(c-o)
    if rng <= 0: return "Sideways", 0.5, "No range"
    ratio = body/rng if rng else 0.0
    if ratio < 0.2: return "Sideways", 0.5, "Small body vs range — indecision"
    if c > o: return "Bullish", min(0.9, 0.6 + ratio/2), "Close above open"
    if c < o: return "Bearish", min(0.9, 0.6 + ratio/2), "Close below open"
    return "Sideways", 0.5, "Flat"

def read_csv_safe(p: Path):
    df = pd.read_csv(p, low_memory=False)
    cols = {c: c.strip().lower() for c in df.columns}
    df = df.rename(columns=cols)
    for c in ["symbol","description","exchange","sector","industry","open","high","low","close"]:
        if c not in df.columns:
            df[c] = "" if c not in ["open","high","low","close"] else None
    return df

def slug(s: str):
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "stock"

def write_html(path: Path, html: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")

def tpl_page(title, description, body, canonical):
    meta_kw = ", ".join(CFG.get("keywords", []))
    author = CFG.get("author", {})
    build_time = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    css = f"{BASE_URL}/static/styles.css"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<link rel="canonical" href="{canonical}">
<meta name="description" content="{description}">
<meta name="keywords" content="{meta_kw}">
<meta name="author" content="{author.get('name','')}">
<link rel="stylesheet" href="{css}">
</head>
<body>
<div class="container">
<header class="hero card">
  <div class="breadcrumbs"><a href="{BASE_URL}/">Home</a></div>
  <h1 class="h1">{title}</h1>
  <p class="small">{CFG.get('site_tagline','')}</p>
  <div class="kv"><div><strong>Last build:</strong> {build_time}</div></div>
</header>
<main class="grid">
{body}
</main>
<footer class="footer">
  <div>E-E-A-T: Author <strong>{author.get('name','')}</strong> · Org: {author.get('org','')}</div>
</footer>
</div>
</body>
</html>"""

def tpl_homepage(canonical):
    # Tailwind UI + our app.js
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Global AI Stock Predictions — Choose Region, Country, Exchange</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="canonical" href="{canonical}">
<script src="https://cdn.tailwindcss.com"></script>
<link rel="stylesheet" href="{BASE_URL}/static/styles.css">
<script>window.BASE_URL={json.dumps(BASE_URL)};window.DEFAULTS={{region:{json.dumps(DEFAULT_REGION)},country:{json.dumps(DEFAULT_COUNTRY)}}};</script>
<script defer src="{BASE_URL}/static/app.js"></script>
</head>
<body class="bg-gray-950 text-gray-100">
  <div class="max-w-7xl mx-auto p-6">
    <header class="mb-6 text-center">
      <h1 class="text-3xl font-bold">🌍 Stock Predictions Explorer</h1>
      <p class="text-gray-400">AI forecast for tomorrow’s prices — browse by Region → Country → Exchange</p>
    </header>

    <section>
      <h2 class="text-xl font-semibold mb-2">Regions</h2>
      <div id="regions" class="flex flex-wrap gap-3"></div>
    </section>

    <section class="mt-6 hidden" id="countries-section">
      <h2 class="text-xl font-semibold mb-2">Countries</h2>
      <div id="countries" class="flex flex-wrap gap-3"></div>
    </section>

    <section class="mt-6 hidden" id="exchanges-section">
      <h2 class="text-xl font-semibold mb-2">Exchanges</h2>
      <div id="exchanges" class="flex flex-wrap gap-3"></div>
    </section>

    <section class="mt-6 hidden" id="stocks-section">
      <h2 class="text-xl font-semibold mb-2">Stocks</h2>
      <div class="overflow-x-auto rounded-xl shadow-lg ring-1 ring-white/10">
        <table class="w-full text-sm text-left">
          <thead class="bg-gray-900/50">
            <tr>
              <th class="px-3 py-2">Symbol</th>
              <th class="px-3 py-2">Name</th>
              <th class="px-3 py-2">Sector</th>
              <th class="px-3 py-2">Open</th>
              <th class="px-3 py-2">High</th>
              <th class="px-3 py-2">Low</th>
              <th class="px-3 py-2">Close</th>
              <th class="px-3 py-2">Signal</th>
            </tr>
          </thead>
          <tbody id="stocks" class="divide-y divide-gray-800 bg-gray-900/20"></tbody>
        </table>
      </div>
    </section>
  </div>
</body>
</html>"""

# ---------- SEO text helpers ----------
def stock_title(symbol, name): return f"AI Analysis of {symbol} Tomorrow | {name} Stock Prediction"
def stock_h1(symbol, name):    return f"AI Analysis of {symbol} ({name}) Stock for Tomorrow"
def stock_meta_desc(symbol, name, exchange):
    return f"Get AI prediction and analysis of {symbol} stock ({name}) for tomorrow. Forecast, price target, bullish or bearish trend insights for {exchange}."

# ---------- Build ----------
def main():
    date_dir, date_obj = find_latest_date_folder()

    # reset dist
    if DIST.exists(): shutil.rmtree(DIST)
    (DIST / "static").mkdir(parents=True, exist_ok=True)
    (DIST / "data").mkdir(parents=True, exist_ok=True)

    # copy CSS (fallback if missing)
    css_src = ROOT / "static" / "styles.css"
    if css_src.exists():
        shutil.copy2(css_src, DIST / "static" / "styles.css")
    else:
        (DIST / "static" / "styles.css").write_text(
            "body{font-family:system-ui;background:#0b1220;color:#e8f0fe;margin:0}"
            ".container{max-width:1100px;margin:0 auto;padding:24px}"
            ".card{background:#111a2b;border-radius:16px;padding:16px}"
            ".h1{font-size:28px}.h2{font-size:22px}.h3{font-size:18px}"
            ".grid{display:grid;gap:16px}.table{width:100%;border-collapse:collapse}"
            ".table td,.table th{border-bottom:1px solid #1f2a44;padding:8px}"
            ".small{color:#9fb3c8}", encoding="utf-8"
        )

    # ----- Build all pages + collect structure for homepage JSON -----
    site = {"data": {}, "meta": {"generated": datetime.datetime.utcnow().isoformat() + "Z"}}
    sitemap_urls = [f"{BASE_URL}/"]

    regions = [p for p in date_dir.iterdir() if p.is_dir()]
    regions.sort(key=lambda x: x.name.lower())

    for region in regions:
        r_name = region.name
        r_slug = slug(r_name)
        site["data"].setdefault(r_slug, {"display": r_name, "countries": {}})

        # CSV per country
        for csv in sorted([p for p in region.glob("*.csv")], key=lambda x: x.name.lower()):
            country_name = csv.stem.replace("-", " ").title()
            c_slug = slug(country_name)
            site["data"][r_slug]["countries"].setdefault(c_slug, {"display": country_name, "exchanges": {}})

            df = read_csv_safe(csv)

            # Group by exchange
            by_exch = {}
            for _, row in df.iterrows():
                sym = str(row["symbol"]).strip()
                name = str(row["description"]).strip() or sym
                exch = (str(row["exchange"]).strip() or "UNKNOWN")
                sec  = str(row["sector"]).strip() or "Unknown"
                ind  = str(row["industry"]).strip()
                try:
                    o = float(row["open"]); h = float(row["high"]); l = float(row["low"]); c = float(row["close"])
                    sig, conf, reason = classify(o,h,l,c)
                except Exception:
                    o=h=l=c=None; sig=conf=reason=""
                by_exch.setdefault(exch, []).append(dict(
                    symbol=sym, name=name, sector=sec, industry=ind,
                    open=o, high=h, low=l, close=c, signal=sig
                ))

            # Write exchange index + stock pages and fill JSON
            for exch, rows in sorted(by_exch.items(), key=lambda kv: kv[0].lower()):
                e_slug = slug(exch)
                site["data"][r_slug]["countries"][c_slug]["exchanges"].setdefault(e_slug, {"display": exch, "stocks": []})

                # Build table rows + stock pages
                tr = []
                for it in rows:
                    sym,name,sec,o,h,l,c,sig = it["symbol"],it["name"],it["sector"],it["open"],it["high"],it["low"],it["close"],it["signal"]
                    s_slug = slug(sym)

                    # Create stock page (/prediction-tomorrow/)
                    if None not in (o,h,l,c):
                        pred = next_business_day(date_obj)
                        page = f"""
<article class="card">
  <h2 class="h2">{stock_h1(sym, name)}</h2>
  <p class="small">Region: {r_name} · Country: {country_name} · Exchange: {exch}</p>
  <p class="small">Session Date: {date_obj.isoformat()} · OHLC: O {o}, H {h}, L {l}, C {c}</p>
  <div class="card"><h3 class="h3">Prediction for {pred.isoformat()}</h3>
  <p><strong>{sig}</strong> (heuristic). For education only.</p></div>
</article>"""
                        stock_url = f"{BASE_URL}/{r_slug}/{c_slug}/{e_slug}/{s_slug}/prediction-tomorrow/"
                        write_html(DIST / r_slug / c_slug / e_slug / s_slug / "prediction-tomorrow" / "index.html",
                                   tpl_page(stock_title(sym,name), stock_meta_desc(sym,name,exch), page, stock_url))
                        sitemap_urls.append(stock_url.rstrip("/"))

                    # For exchange table
                    tr.append(
                        f"<tr>"
                        f"<td><a href='{BASE_URL}/{r_slug}/{c_slug}/{e_slug}/{s_slug}/prediction-tomorrow/'>{sym}</a></td>"
                        f"<td><a href='{BASE_URL}/{r_slug}/{c_slug}/{e_slug}/{s_slug}/prediction-tomorrow/'>{name}</a></td>"
                        f"<td>{sec}</td>"
                        f"<td>{'' if o is None else f'{o:.2f}'}</td>"
                        f"<td>{'' if h is None else f'{h:.2f}'}</td>"
                        f"<td>{'' if l is None else f'{l:.2f}'}</td>"
                        f"<td>{'' if c is None else f'{c:.2f}'}</td>"
                        f"<td>{sig}</td>"
                        f"</tr>"
                    )

                    # Add to JSON
                    site["data"][r_slug]["countries"][c_slug]["exchanges"][e_slug]["stocks"].append({
                        "symbol": sym, "name": name, "sector": sec,
                        "open": o, "high": h, "low": l, "close": c, "signal": sig,
                        "url": f"{BASE_URL}/{r_slug}/{c_slug}/{e_slug}/{s_slug}/prediction-tomorrow/"
                    })

                # Exchange index page
                exch_table = (
                    "<table class='table'>"
                    "<thead><tr><th>Symbol</th><th>Name</th><th>Sector</th>"
                    "<th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Signal</th></tr></thead>"
                    "<tbody>" + "\n".join(tr) + "</tbody></table>"
                )
                exch_body = f"<section class='card'><h2 class='h2'>{country_name} — {exch}</h2>{exch_table}</section>"
                exch_url = f"{BASE_URL}/{r_slug}/{c_slug}/{e_slug}/"
                write_html(DIST / r_slug / c_slug / e_slug / "index.html",
                           tpl_page(f"{country_name} {exch} — {CFG.get('site_title','')}",
                                    f"Browse {exch} listings in {country_name}.",
                                    exch_body, exch_url))
                sitemap_urls.append(exch_url.rstrip("/"))

            # Country page (links to exchanges)
            links = []
            for e_slug, ed in site["data"][r_slug]["countries"][c_slug]["exchanges"].items():
                links.append(f"<li><a href='{BASE_URL}/{r_slug}/{c_slug}/{e_slug}/'>{ed['display']}</a></li>")
            country_url = f"{BASE_URL}/{r_slug}/{c_slug}/"
            write_html(DIST / r_slug / c_slug / "index.html",
                       tpl_page(f"{country_name} — {CFG.get('site_title','')}",
                                f"Browse exchanges and sectors in {country_name}.",
                                f"<section class='card'><h2 class='h2'>{country_name} — Exchanges</h2><ul>{''.join(links)}</ul></section>",
                                country_url))
            sitemap_urls.append(country_url.rstrip("/"))

        # Region page
        c_links = []
        for c_slug, cd in site["data"][r_slug]["countries"].items():
            c_links.append(f"<li><a href='{BASE_URL}/{r_slug}/{c_slug}/'>{cd['display']}</a></li>")
        region_url = f"{BASE_URL}/{r_slug}/"
        write_html(DIST / r_slug / "index.html",
                   tpl_page(f"{r_name} Markets — {CFG.get('site_title','')}",
                            f"Browse stock markets in {r_name}.",
                            f"<section class='card'><h2 class='h2'>Countries in {r_name}</h2><ul>{''.join(c_links)}</ul></section>",
                            region_url))
        sitemap_urls.append(region_url.rstrip("/"))

    # ----- Write homepage JSON for app.js -----
    (DIST / "data" / "index.json").write_text(json.dumps(site, ensure_ascii=False), encoding="utf-8")

    # ----- Write interactive homepage -----
    write_html(DIST / "index.html", tpl_homepage(f"{BASE_URL}/"))

    # robots + sitemap
    (DIST / "robots.txt").write_text(f"Sitemap: {BASE_URL}/sitemap.xml\nUser-agent: *\nAllow: /\n", encoding="utf-8")
    sm = "<?xml version='1.0' encoding='UTF-8'?><urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>" \
         + "".join([f"<url><loc>{u}</loc></url>" for u in sorted(set(sitemap_urls))]) + "</urlset>"
    (DIST / "sitemap.xml").write_text(sm, encoding="utf-8")

    print("Build complete →", DIST)

if __name__ == "__main__":
    main()
