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
BASE_URL = CFG.get("base_url", "").rstrip("/")  # e.g. https://anandsolanke.github.io/stockpricepredictions-ssg

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

def tpl_base(title, description, body, canonical):
    meta_kw = ", ".join(CFG.get("keywords", []))
    author = CFG.get("author", {})
    site_tagline = CFG.get("site_tagline", "")
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
  <p class="small">{site_tagline}</p>
  <div class="kv">
    <div><strong>Purpose:</strong> Transparent, reproducible SSG for daily stock pages.</div>
    <div><strong>Last build:</strong> {build_time}</div>
  </div>
</header>
<main class="grid">
{body}
</main>
<footer class="footer">
  <div>E-E-A-T: Author <strong>{author.get('name','')}</strong> · Org: {author.get('org','')} · Contact: <a href="mailto:{author.get('contact_email','')}">{author.get('contact_email','')}</a></div>
  <div>Data provenance: Uploaded CSVs (OHLC). Session date = exchange local date. Prediction = next business day (holidays not applied).</div>
</footer>
</div>
</body>
</html>"""

def stock_title(symbol, name):
    return f"AI Analysis of {symbol} Tomorrow | {name} Stock Prediction"

def stock_h1(symbol, name):
    return f"AI Analysis of {symbol} ({name}) Stock for Tomorrow"

def stock_meta_desc(symbol, name, exchange):
    return f"Get AI prediction and analysis of {symbol} stock ({name}) for tomorrow. Forecast, price target, bullish or bearish trend insights for {exchange}."

# ---------- Build ----------
def main():
    date_dir, date_obj = find_latest_date_folder()

    # reset dist
    if DIST.exists(): shutil.rmtree(DIST)
    (DIST / "static").mkdir(parents=True, exist_ok=True)

    # copy CSS (fallback if missing)
    css_src = ROOT / "static" / "styles.css"
    if css_src.exists():
        shutil.copy2(css_src, DIST / "static" / "styles.css")
    else:
        (DIST / "static" / "styles.css").write_text(
            "body{font-family:system-ui;background:#0b1220;color:#e8f0fe;margin:0}"
            " .container{max-width:1100px;margin:0 auto;padding:24px}"
            " .card{background:#111a2b;border-radius:16px;padding:16px}"
            " .h1{font-size:28px} .h2{font-size:22px} .h3{font-size:18px}"
            " .grid{display:grid;gap:16px}"
            " .table{width:100%;border-collapse:collapse}"
            " .table td,.table th{border-bottom:1px solid #1f2a44;padding:8px}"
            " .small{color:#9fb3c8}",
            encoding="utf-8"
        )

    # Regions (folders inside latest date)
    regions = [p for p in date_dir.iterdir() if p.is_dir()]
    regions.sort(key=lambda x: x.name.lower())

    # Collect data for the interactive homepage JSON
    site_json = {"regions": []}
    sitemap_urls = [f"{BASE_URL}/"]

    for region in regions:
        r_name = region.name
        r_slug = slug(r_name)
        reg_entry = {"key": r_slug, "name": r_name, "countries": []}

        # Countries (CSV files under region)
        country_csvs = sorted([p for p in region.glob("*.csv")], key=lambda x: x.name.lower())

        for csv in country_csvs:
            country_name = csv.stem.replace("-", " ").title()
            c_slug = slug(country_name)
            df = read_csv_safe(csv)

            # group rows
            by_exch, by_sector = {}, {}
            for _, row in df.iterrows():
                sym = str(row["symbol"]).strip()
                name = str(row["description"]).strip() or sym
                exch = str(row["exchange"]).strip()
                sec  = str(row["sector"]).strip() or "Unknown"
                ind  = str(row["industry"]).strip()
                try:
                    o = float(row["open"]); h = float(row["high"]); l = float(row["low"]); c = float(row["close"])
                except Exception:
                    o=h=l=c=None
                item = dict(sym=sym,name=name,exch=exch,sec=sec,ind=ind,o=o,h=h,l=l,c=c)
                by_exch.setdefault(exch or "UNKNOWN", []).append(item)
                by_sector.setdefault(sec or "Unknown", []).append(item)

            # Build exchange pages + rows, and also collect JSON for homepage
            exch_entries = []
            for exch, rows in sorted(by_exch.items(), key=lambda kv: kv[0].lower()):
                e_slug = slug(exch)
                # Build stock pages and exchange table
                table_rows_html = []
                stocks_for_json = []

                for rowd in rows:
                    sym,name,sec,ind,o,h,l,c = rowd["sym"],rowd["name"],rowd["sec"],rowd["ind"],rowd["o"],rowd["h"],rowd["l"],rowd["c"]
                    s_slug = slug(sym)
                    sig = ""
                    if None not in (o,h,l,c):
                        sig, conf, reason = classify(o,h,l,c)

                        # Stock SEO page
                        pred = next_business_day(date_obj)
                        title = stock_title(sym, name)
                        h1    = stock_h1(sym, name)
                        mdesc = stock_meta_desc(sym, name, exch)
                        stock_body = f"""
<article class="card">
  <h2 class="h2">{h1}</h2>
  <p class="small">Region: {r_name} · Country: {country_name} · Exchange: {exch}</p>
  <p class="small">Session Date: {date_obj.isoformat()} · OHLC: O {o}, H {h}, L {l}, C {c}</p>
  <div class="card">
    <h3 class="h3">Prediction for {pred.isoformat()}</h3>
    <p><strong>{sig}</strong> — confidence {int(conf*100)}%.</p>
  </div>
</article>"""
                        stock_url = f"{BASE_URL}/{r_slug}/{c_slug}/{e_slug}/{s_slug}/prediction-tomorrow/"
                        write_html(
                            DIST / r_slug / c_slug / e_slug / s_slug / "prediction-tomorrow" / "index.html",
                            tpl_base(title, mdesc, stock_body, stock_url)
                        )
                        sitemap_urls.append(stock_url.rstrip("/"))

                    # exchange table row (Symbol | Name | Sector | O | H | L | C | Signal)
                    table_rows_html.append(
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

                    # for homepage JSON (drill-down)
                    stocks_for_json.append({
                        "symbol": sym,
                        "name": name,
                        "sector": sec,
                        "open": o, "high": h, "low": l, "close": c,
                        "signal": sig,
                        "url": f"{BASE_URL}/{r_slug}/{c_slug}/{e_slug}/{s_slug}/prediction-tomorrow/"
                    })

                # exchange page
                exch_table = (
                    "<table class='table'>"
                    "<thead><tr>"
                    "<th>Symbol</th><th>Name</th><th>Sector</th>"
                    "<th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Signal</th>"
                    "</tr></thead><tbody>"
                    + "\n".join(table_rows_html) + "</tbody></table>"
                )
                exch_body = f"<section class='card'><h2 class='h2'>{country_name} — {exch}</h2>{exch_table}</section>"
                exch_url = f"{BASE_URL}/{r_slug}/{c_slug}/{e_slug}/"
                write_html(
                    DIST / r_slug / c_slug / e_slug / "index.html",
                    tpl_base(f"{country_name} {exch} — {CFG.get('site_title','')}",
                             f"Browse {exch} listings in {country_name}.",
                             exch_body,
                             exch_url)
                )
                sitemap_urls.append(exch_url.rstrip("/"))

                exch_entries.append({"key": e_slug, "name": exch, "stocks": stocks_for_json})

            # sector pages (listing)
            for sec, rows in sorted(by_sector.items(), key=lambda kv: kv[0].lower()):
                sec_slug = slug(sec or "Unknown")
                table_rows_html = []
                for rowd in rows:
                    sym,name,exch,ind,o,h,l,c = rowd["sym"],rowd["name"],rowd["exch"],rowd["ind"],rowd["o"],rowd["h"],rowd["l"],rowd["c"]
                    e_slug2 = slug(exch or "UNKNOWN")
                    s_slug2 = slug(sym)
                    sig = ""
                    if None not in (o,h,l,c): sig = classify(o,h,l,c)[0]
                    table_rows_html.append(
                        f"<tr>"
                        f"<td><a href='{BASE_URL}/{r_slug}/{c_slug}/{e_slug2}/{s_slug2}/prediction-tomorrow/'>{sym}</a></td>"
                        f"<td><a href='{BASE_URL}/{r_slug}/{c_slug}/{e_slug2}/{s_slug2}/prediction-tomorrow/'>{name}</a></td>"
                        f"<td>{exch}</td><td>{sec}</td>"
                        f"<td>{'' if o is None else f'{o:.2f}'}</td>"
                        f"<td>{'' if h is None else f'{h:.2f}'}</td>"
                        f"<td>{'' if l is None else f'{l:.2f}'}</td>"
                        f"<td>{'' if c is None else f'{c:.2f}'}</td>"
                        f"<td>{sig}</td>"
                        f"</tr>"
                    )
                sector_table = (
                    "<table class='table'>"
                    "<thead><tr>"
                    "<th>Symbol</th><th>Name</th><th>Exchange</th><th>Sector</th>"
                    "<th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Signal</th>"
                    "</tr></thead><tbody>"
                    + "\n".join(table_rows_html) + "</tbody></table>"
                )
                sector_body = f"<section class='card'><h2 class='h2'>{country_name} — {sec} (Prediction Tomorrow)</h2>{sector_table}</section>"
                sector_url = f"{BASE_URL}/{r_slug}/{c_slug}/sectors/{sec_slug}/prediction-tomorrow/"
                write_html(
                    DIST / r_slug / c_slug / "sectors" / sec_slug / "prediction-tomorrow" / "index.html",
                    tpl_base(f"{country_name} {sec} — AI Stock Predictions",
                             f"All {sec} stocks in {country_name} with next-day AI predictions.",
                             sector_body,
                             sector_url)
                )
                sitemap_urls.append(sector_url.rstrip("/"))

            # country landing (links)
            exch_links = "".join([f"<li><a href='{BASE_URL}/{r_slug}/{c_slug}/{e['key']}/'>{e['name']}</a></li>" for e in exch_entries])
            sectors_hub_url = f"{BASE_URL}/{r_slug}/{c_slug}/sectors/"
            write_html(
                DIST / r_slug / c_slug / "sectors" / "index.html",
                tpl_base(f"{country_name} sectors — {CFG.get('site_title','')}",
                         f"Browse sectors in {country_name}.",
                         "<section class='card'><h2 class='h2'>Choose a sector, then open Prediction Tomorrow pages.</h2></section>",
                         sectors_hub_url)
            )
            sitemap_urls.append(sectors_hub_url.rstrip("/"))

            country_url = f"{BASE_URL}/{r_slug}/{c_slug}/"
            write_html(
                DIST / r_slug / c_slug / "index.html",
                tpl_base(f"{country_name} — {CFG.get('site_title','')}",
                         f"Browse exchanges and sectors in {country_name}.",
                         f"<section class='card'><h2 class='h2'>{country_name} — Exchanges</h2><ul>{exch_links}</ul></section>"
                         f"<section class='card'><h2 class='h2'>Sectors</h2><a href='{BASE_URL}/{r_slug}/{c_slug}/sectors/'>Browse sectors</a></section>",
                         country_url)
            )
            sitemap_urls.append(country_url.rstrip("/"))

            # add to JSON
            reg_entry["countries"].append({
                "key": c_slug,
                "name": country_name,
                "exchanges": exch_entries
            })

        # region index and JSON
        region_url = f"{BASE_URL}/{r_slug}/"
        write_html(
            DIST / r_slug / "index.html",
            tpl_base(f"{r_name} Markets — {CFG.get('site_title','')}",
                     f"Browse stock markets in {r_name}.",
                     f"<section class='card'><h2 class='h2'>Countries in {r_name}</h2><ul>"
                     + "".join([f"<li><a href='{BASE_URL}/{r_slug}/{c['key']}/'>{c['name']}</a></li>" for c in reg_entry["countries"]])
                     + "</ul></section>",
                     region_url)
        )
        sitemap_urls.append(region_url.rstrip("/"))
        site_json["regions"].append(reg_entry)

    # robots + sitemap
    (DIST / "robots.txt").write_text(
        f"Sitemap: {BASE_URL}/sitemap.xml\nUser-agent: *\nAllow: /\n",
        encoding="utf-8"
    )
    sm = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
        + "".join([f"<url><loc>{u}</loc></url>" for u in sorted(set(sitemap_urls))])
        + "</urlset>"
    )
    (DIST / "sitemap.xml").write_text(sm, encoding="utf-8")

    # --------- NEW: write interactive homepage + JSON ---------
    # site-data.json
    (DIST / "site-data.json").write_text(json.dumps(site_json, ensure_ascii=False), encoding="utf-8")

    # interactive index.html (uses Tailwind + client-side filtering)
    interactive_index = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Explore Markets — {CFG.get('site_title','')}</title>
  <meta name="description" content="Browse regions, countries, exchanges and stocks. Next-day signals based on OHLC.">
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-950 text-gray-100">
  <div class="max-w-7xl mx-auto p-6">
    <div class="flex items-baseline justify-between gap-4 mb-6">
      <h1 class="text-3xl font-bold">Explore Markets</h1>
      <a class="text-sm text-blue-400 hover:underline" href="{BASE_URL}/sitemap.xml">Sitemap</a>
    </div>

    <!-- Row 1: Regions -->
    <div class="mb-4">
      <h2 class="text-lg font-semibold mb-2">Regions</h2>
      <div id="regions" class="flex flex-wrap gap-2"></div>
    </div>

    <!-- Row 2: Countries -->
    <div class="mb-4">
      <h2 class="text-lg font-semibold mb-2">Countries</h2>
      <div id="countries" class="flex flex-wrap gap-2"></div>
    </div>

    <!-- Row 3: Exchanges -->
    <div class="mb-4">
      <h2 class="text-lg font-semibold mb-2">Exchanges</h2>
      <div id="exchanges" class="flex flex-wrap gap-2"></div>
    </div>

    <!-- Stocks Table -->
    <div id="stocks" class="overflow-x-auto"></div>
  </div>

  <script>
    let DATA = null;
    let sel = {{ region:null, country:null, exch:null }};

    const btn = (label, active=false) =>
      `<button class="px-3 py-1 rounded border ${active?'bg-blue-600 border-blue-500':'bg-gray-800 border-gray-700 hover:bg-gray-700'}" data-label="\${label}">\${label}</button>`;

    const regionsEl = document.getElementById('regions');
    const countriesEl = document.getElementById('countries');
    const exchangesEl = document.getElementById('exchanges');
    const stocksEl = document.getElementById('stocks');

    async function load() {{
      const res = await fetch('site-data.json');
      DATA = await res.json();

      // Regions row
      regionsEl.innerHTML = DATA.regions.map(r => btn(r.name)).join('');
      regionsEl.onclick = (e) => {{
        const b = e.target.closest('button'); if (!b) return;
        const name = b.dataset.label;
        sel.region = DATA.regions.find(r => r.name === name);
        sel.country = null; sel.exch = null;
        renderCountries(); renderExchanges(); renderStocks(); highlight(regionsEl, name);
      }};
    }}

    function renderCountries() {{
      if (!sel.region) {{ countriesEl.innerHTML = ''; return; }}
      countriesEl.innerHTML = sel.region.countries.map(c => btn(c.name)).join('');
      countriesEl.onclick = (e) => {{
        const b = e.target.closest('button'); if (!b) return;
        const name = b.dataset.label;
        sel.country = sel.region.countries.find(c => c.name === name);
        sel.exch = null;
        renderExchanges(); renderStocks(); highlight(countriesEl, name);
      }};
    }}

    function renderExchanges() {{
      if (!sel.country) {{ exchangesEl.innerHTML = ''; return; }}
      exchangesEl.innerHTML = sel.country.exchanges.map(x => btn(x.name)).join('');
      exchangesEl.onclick = (e) => {{
        const b = e.target.closest('button'); if (!b) return;
        const name = b.dataset.label;
        sel.exch = sel.country.exchanges.find(x => x.name === name);
        renderStocks(); highlight(exchangesEl, name);
      }};
    }}

    function renderStocks() {{
      if (!sel.exch) {{ stocksEl.innerHTML = ''; return; }}
      const rows = sel.exch.stocks.map(s => `
        <tr class="border-b border-gray-800">
          <td class="px-2 py-1"><a class="text-blue-400 hover:underline" href="\${s.url}">\${s.symbol}</a></td>
          <td class="px-2 py-1"><a class="text-blue-400 hover:underline" href="\${s.url}">\${s.name}</a></td>
          <td class="px-2 py-1">\${s.sector||''}</td>
          <td class="px-2 py-1">\${fmt(s.open)}</td>
          <td class="px-2 py-1">\${fmt(s.high)}</td>
          <td class="px-2 py-1">\${fmt(s.low)}</td>
          <td class="px-2 py-1">\${fmt(s.close)}</td>
          <td class="px-2 py-1 font-semibold">\${s.signal||''}</td>
        </tr>`).join('');
      stocksEl.innerHTML = `
        <table class="table-auto w-full text-sm">
          <thead class="bg-gray-900">
            <tr>
              <th class="text-left px-2 py-1">Symbol</th>
              <th class="text-left px-2 py-1">Name</th>
              <th class="text-left px-2 py-1">Sector</th>
              <th class="text-left px-2 py-1">Open</th>
              <th class="text-left px-2 py-1">High</th>
              <th class="text-left px-2 py-1">Low</th>
              <th class="text-left px-2 py-1">Close</th>
              <th class="text-left px-2 py-1">Signal</th>
            </tr>
          </thead>
          <tbody>\${rows}</tbody>
        </table>`;
    }}

    function highlight(container, label) {{
      Array.from(container.querySelectorAll('button')).forEach(b => {{
        const active = b.dataset.label === label;
        b.className = "px-3 py-1 rounded border " + (active ? "bg-blue-600 border-blue-500" : "bg-gray-800 border-gray-700 hover:bg-gray-700");
      }});
    }}

    const fmt = (v) => (v===null||v===undefined||v==="") ? "" : Number(v).toFixed(2);

    load();
  </script>
</body>
</html>
"""
    write_html(DIST / "index.html", interactive_index)

    print("Build complete →", DIST)

if __name__ == "__main__":
    main()
