#!/usr/bin/env python3
# scripts/build.py
import csv, json, os, sys, html, shutil
from pathlib import Path
from datetime import datetime, timedelta, timezone
from slugify import slugify

# ---------- Config ----------
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "Data" / "LastTradingDay"
DIST = ROOT / "dist"
LOGOS = DIST / "logos"        # we assume your logos already copied here
CFG_PATH = ROOT / "config.json"

def read_cfg():
    if CFG_PATH.exists():
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "site": {"name": "StockPricePredictions", "baseurl": ""},
        "author": {"name": "StockPricePredictions Research", "org": "SPP Labs", "contact_email": "hello@stockpricepredictions.com"}
    }

CFG = read_cfg()
SITE = CFG.get("site", {})
AUTHOR = CFG.get("author", {})

# ---------- Utils ----------
def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def write_text(path: Path, text: str):
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")

def fmt_pct(v):
    try:
        v = float(v)
        s = f"{v:.2f}%"
        cls = "text-green-400" if v > 0 else ("text-red-400" if v < 0 else "text-gray-300")
        return f'<span class="{cls}">{s}</span>'
    except Exception:
        return "<span class='text-gray-400'>—</span>"

def safe(v):
    return html.escape(str(v)) if v is not None else ""

def next_business_day(d: datetime):
    # naive next business day (Mon-Fri)
    dd = d + timedelta(days=1)
    while dd.weekday() >= 5:
        dd += timedelta(days=1)
    return dd.date().isoformat()

def read_last7_json(region, country, exch, symbol_slug):
    p = DIST / "perf" / region / country / exch / f"{symbol_slug}.json"
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def logo_tag(region, country, symbol):
    # logo path convention: dist/logos/<region>/<country>/<symbol>.png
    logo = LOGOS / region / country / f"{symbol}.png"
    if logo.exists():
        rel = os.path.relpath(logo, start=DIST).replace("\\", "/")
        return f'<img alt="" src="/{rel}" class="h-4 w-4 object-contain inline-block mr-2 align-middle" />'
    return ""

# ---------- Tailwind base ----------
def tpl_base(title: str, description: str, body: str, canonical: str = ""):
    build_time = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{safe(title)}</title>
{"<link rel='canonical' href='" + html.escape(canonical) + "'/>" if canonical else ""}
<script src="https://cdn.tailwindcss.com"></script>
<script>
  tailwind.config = {{
    theme: {{
      extend: {{
        colors: {{
          'primary-dark': '#121212',
          'card-dark': '#1f1f1f',
          'text-light': '#e5e5e5',
        }}
      }}
    }}
  }}
</script>
<style>
  body {{
    font-family: Inter,system-ui,Segoe UI,Roboto,Arial,sans-serif;
    background-color:#121212;
    color:#e5e5e5;
  }}
  .card {{
    background-color:#1f1f1f; border-radius:.5rem; padding:1.5rem;
    box-shadow:0 4px 6px -1px rgba(0,0,0,.1), 0 2px 4px -2px rgba(0,0,0,.1);
  }}
  .filter-button {{
    transition: all .15s ease-in-out; cursor:pointer; text-align:center;
  }}
  .filter-button:hover {{ transform:translateY(-1px); box-shadow:0 2px 4px rgba(0,0,0,.2); }}
  .active-button {{ background-color:#3b82f6; color:#fff; border-color:#3b82f6; }}
  .stock-table th {{ color:#a0a0a0; text-align:left; padding-bottom:.5rem; font-size:.875rem; font-weight:600; }}
  .stock-table td {{ padding:.75rem 0; border-top:1px solid #2d2d2d; }}
</style>
</head>
<body class="min-h-screen">
  <div class="mx-auto px-4 py-8 max-w-screen-2xl xl:px-8">
    <div class="mb-8">
      <p class="text-blue-400 text-sm mb-1">Home</p>
      <h1 class="text-3xl sm:text-4xl font-extrabold mb-1">{safe(title)}</h1>
      <p class="text-gray-400 text-sm mb-4">{safe(description)}</p>
      <p class="text-gray-500 text-xs">Last build: {build_time}</p>
    </div>
    {body}
    <footer class="text-xs text-gray-500 mt-10">
      <p>E-E-A-T: Author <strong>{safe(AUTHOR.get('name',''))}</strong> · Org: {safe(AUTHOR.get('org',''))}
      · Contact: <a class="text-blue-400 hover:underline" href="mailto:{safe(AUTHOR.get('contact_email',''))}">{safe(AUTHOR.get('contact_email',''))}</a></p>
    </footer>
  </div>
</body>
</html>"""

# ---------- Data scan ----------
# Expected tree: Data/LastTradingDay/<Region>/<Country>/<Exchange>.csv
def walk_markets():
    out = []
    if not DATA.exists():
        return out
    for region_dir in sorted(DATA.iterdir()):
        if not region_dir.is_dir(): continue
        region = region_dir.name
        for country_dir in sorted(region_dir.iterdir()):
            if not country_dir.is_dir(): continue
            country = country_dir.name
            for csv_path in sorted(country_dir.iterdir()):
                if csv_path.suffix.lower() != ".csv": continue
                exch = csv_path.stem
                out.append((region, country, exch, csv_path))
    return out

def read_csv_rows(csv_path: Path):
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append(row)
    return rows

# ---------- Chips (left column) ----------
def chip(label, href=None, active=False):
    base = "filter-button block text-sm px-3 py-2 rounded-lg border " \
           + ("active-button border-blue-500" if active else "bg-card-dark text-text-light border-gray-600 hover:bg-gray-700")
    if href:
        return f'<a class="{base} w-[calc(50%-4px)]" href="{html.escape(href)}">{safe(label)}</a>'
    return f'<span class="{base} w-[calc(50%-4px)]">{safe(label)}</span>'

# Build lists for navigation
def nav_regions(markets, current_region=None, current_country=None, current_exch=None):
    regs = sorted(set(r for r,_,_,_ in markets))
    buf = []
    for r in ["Asia - Pacific","Europe","Global Indices","Mexico - South America","Middle East - Africa","North America"]:
        if r in regs:
            href = "/"
            if current_region != r:
                # link to first page for that region (if available)
                try:
                    c0 = next(c for (rr,c,_,_) in markets if rr==r)
                    e0 = next(e for (rr,cc,e,_) in markets if rr==r and cc==c0)
                    href = f"/groups/{slugify(r)}/{slugify(c0)}/{slugify(e0)}/"
                except StopIteration:
                    href = "/"
            buf.append(chip(r, href, active=(r==current_region)))
    return "<div class='flex flex-wrap gap-2'>" + "".join(buf) + "</div>"

def nav_countries(markets, region, current_country=None):
    cs = sorted(set(c for (r,c,_,_) in markets if r==region))
    buf=[]
    for c in cs:
        # link to first exchange page for that country
        e0=None
        for (r,cc,e,_) in markets:
            if r==region and cc==c:
                e0=e; break
        href = f"/groups/{slugify(region)}/{slugify(c)}/{slugify(e0)}/" if e0 else "#"
        buf.append(chip(c, href, active=(c==current_country)))
    return "<div class='flex flex-wrap gap-2'>" + "".join(buf) + "</div>"

def nav_exchanges(markets, region, country, current_exch=None):
    es = sorted(set(e for (r,c,e,_) in markets if r==region and c==country))
    buf=[]
    for e in es:
        href = f"/groups/{slugify(region)}/{slugify(country)}/{slugify(e)}/"
        buf.append(chip(e, href, active=(e==current_exch)))
    return "<div class='flex flex-wrap gap-2'>" + "".join(buf) + "</div>"

# ---------- Table ----------
def stocks_table(region, country, exch, rows):
    # columns: symbol,description,exchange,sector,industry,open,high,low,Close,Change%,MarketCap,Volume,Currency
    head = """
    <div class="overflow-x-auto">
      <table class="w-full stock-table table-auto border-separate" style="border-spacing:0 .5rem;">
        <thead>
          <tr>
            <th class="w-[8%]">Symbol</th>
            <th class="w-[32%]">Name</th>
            <th class="w-[18%] hidden sm:table-cell">Sector</th>
            <th class="w-[8%] hidden lg:table-cell">Open</th>
            <th class="w-[8%] hidden lg:table-cell">High</th>
            <th class="w-[8%] hidden lg:table-cell">Close</th>
            <th class="w-[8%]">Change%</th>
            <th class="w-[10%]">Signal</th>
          </tr>
        </thead>
        <tbody>
    """
    body=[]
    for row in rows[:2000]:  # safety cap
        sym = (row.get("symbol") or "").strip()
        name = row.get("description") or ""
        sector = row.get("sector") or ""
        o = row.get("open") or ""
        h = row.get("high") or ""
        c = row.get("Close") or row.get("close") or ""
        ch = row.get("Change%") or row.get("change%") or ""
        sym_slug = slugify(sym)
        url = f"/{slugify(region)}/{slugify(country)}/{slugify(exch)}/{sym_slug}/prediction-tomorrow/"

        body.append(f"""
        <tr>
          <td class="text-blue-400 font-semibold text-sm">{safe(sym)}</td>
          <td class="text-blue-400 text-sm">{logo_tag(region,country,sym)}{safe(name)}</td>
          <td class="text-gray-300 text-sm hidden sm:table-cell">{safe(sector)}</td>
          <td class="text-gray-300 text-sm hidden lg:table-cell">{safe(o)}</td>
          <td class="text-gray-300 text-sm hidden lg:table-cell">{safe(h)}</td>
          <td class="text-gray-300 text-sm hidden lg:table-cell">{safe(c)}</td>
          <td class="text-sm">{fmt_pct(ch)}</td>
          <td><a class="text-xs font-semibold bg-blue-600/20 text-blue-400 px-3 py-1 rounded-full" href="{url}">AI Prediction</a></td>
        </tr>
        """)
    tail = "</tbody></table></div>"
    return head + "".join(body) + tail

# ---------- Pages ----------
def render_group_page(markets, region, country, exch, rows):
    left = f"""
<div class="grid grid-cols-1 md:grid-cols-4 gap-6">
  <div class="md:col-span-1 space-y-6">
    <div class="card">
      <h2 class="text-xl font-semibold mb-4">Browse Markets</h2>
      <div class="pb-4 mb-4 border-b border-gray-700">
        <p class="text-base font-semibold text-gray-300 mb-3">Regions</p>
        {nav_regions(markets, current_region=region)}
      </div>
      <div class="pb-4 mb-4 border-b border-gray-700">
        <p class="text-base font-semibold text-gray-300 mb-3">Countries</p>
        {nav_countries(markets, region, current_country=country)}
      </div>
      <div>
        <p class="text-base font-semibold text-gray-300 mb-3">Exchanges</p>
        {nav_exchanges(markets, region, country, current_exch=exch)}
      </div>
    </div>
  </div>
  <div class="md:col-span-3">
    <div class="card">
      <h2 class="text-xl font-semibold mb-4">Stocks</h2>
      {stocks_table(region,country,exch,rows)}
    </div>
  </div>
</div>
"""
    title = f"{SITE.get('name','StockPricePredictions')} — {country} / {exch}"
    desc = "Next-day stock movement from yesterday's OHLC"
    return tpl_base(title, desc, left, "")

def render_home(markets):
    # Link to first available page, and show the same two-col shell with empty right.
    if not markets:
        body = "<p>No data.</p>"
        return tpl_base("StockPricePredictions — Home", "Next-day stock movement from yesterday's OHLC", body, "")
    r,c,e,_ = markets[0]
    link = f"/groups/{slugify(r)}/{slugify(c)}/{slugify(e)}/"
    body = f"""
<div class="grid grid-cols-1 md:grid-cols-4 gap-6">
  <div class="md:col-span-1 space-y-6">
    <div class="card">
      <h2 class="text-xl font-semibold mb-4">Browse Markets</h2>
      <div class="pb-4 mb-4 border-b border-gray-700">
        <p class="text-base font-semibold text-gray-300 mb-3">Regions</p>
        {nav_regions(markets)}
      </div>
      <div class="pb-4 mb-4 border-b border-gray-700">
        <p class="text-base font-semibold text-gray-300 mb-3">Countries</p>
        <div class="text-gray-400 text-sm">Pick a region first.</div>
      </div>
      <div>
        <p class="text-base font-semibold text-gray-300 mb-3">Exchanges</p>
        <div class="text-gray-400 text-sm">Pick a country first.</div>
      </div>
    </div>
  </div>
  <div class="md:col-span-3">
    <div class="card">
      <h2 class="text-xl font-semibold mb-4">Stocks</h2>
      <p class="text-sm text-gray-400">Start here → <a class="text-blue-400 underline" href="{link}">{html.escape(c)} / {html.escape(e)}</a></p>
    </div>
  </div>
</div>"""
    return tpl_base("StockPricePredictions — Home", "Next-day stock movement from yesterday's OHLC", body, "")

def render_pred_page(region, country, exch, row):
    # row from LastTradingDay CSV
    sym = (row.get("symbol") or "").strip()
    name = row.get("description") or sym
    o,h,l,c = row.get("open",""), row.get("high",""), row.get("low",""), (row.get("Close") or row.get("close") or "")
    ch = row.get("Change%") or row.get("change%") or ""
    pred_date = next_business_day(datetime.utcnow())
    sym_slug = slugify(sym)

    # last-7 performance (if generated)
    perf = read_last7_json(slugify(region), slugify(country), slugify(exch), sym_slug)
    perf_block = ""
    if perf and perf.get("rows"):
        rows = perf["rows"]
        # de-duplicate by date (if any duplicates slip in)
        seen=set(); de_duped=[]
        for r in rows:
            d=r.get("date")
            if d and d not in seen:
                seen.add(d); de_duped.append(r)
        rows = de_duped[:7]
        wins = sum(1 for r in rows if (r.get("result") or "").lower()=="win")
        total = len(rows)
        pct = f"{(wins*100/total):.2f}%" if total else "0%"
        trs = []
        for r in rows:
            res = r.get("result","")
            color = "text-green-400" if res.lower()=="win" else "text-red-400"
            trs.append(f"""
            <tr>
                <td class="py-2">{safe(r.get("date",""))}</td>
                <td class="py-2">{safe(r.get("pred",""))}</td>
                <td class="py-2">{safe(r.get("actual",""))}</td>
                <td class="py-2 font-semibold {color}">{safe(res)}</td>
            </tr>
            """)
        perf_block = f"""
        <div class="card mt-6">
          <h3 class="text-xl font-semibold mb-4 border-b border-gray-700 pb-2">Last 7-Day Performance</h3>
          <div class="mb-3 p-3 bg-slate-800/40 rounded border border-green-700/30 flex items-center justify-between">
            <span class="text-sm text-slate-300">Last 7-Day Accuracy:</span>
            <span class="text-green-400 text-lg font-extrabold">{pct} ({wins}/{total})</span>
          </div>
          <div class="overflow-x-auto">
            <table class="min-w-full">
              <thead>
                <tr class="text-sm text-slate-400">
                  <th class="text-left py-2">Date</th>
                  <th class="text-left py-2">AI Prediction</th>
                  <th class="text-left py-2">Actual</th>
                  <th class="text-left py-2">Result</th>
                </tr>
              </thead>
              <tbody class="text-sm">
                {''.join(trs)}
              </tbody>
            </table>
          </div>
        </div>
        """

    body = f"""
<div class="grid grid-cols-1 gap-6">
  <div class="card">
    <p class="text-xs font-medium text-slate-400 mb-2 uppercase tracking-widest">Stock Analysis Report</p>
    <div class="flex items-center space-x-3 mb-3">
      <div class="h-10 w-10 rounded-full bg-blue-500/20 border border-blue-400/40 flex items-center justify-center text-blue-300 text-sm font-bold">
        {safe(sym[:4])}
      </div>
      <h2 class="text-2xl font-bold">{safe(name)}</h2>
      <span class="text-slate-400">( {safe(exch)} )</span>
    </div>

    <div class="p-4 bg-slate-800 rounded border border-slate-700">
      <p class="font-bold text-lg mb-3 text-slate-300 border-b border-slate-700 pb-2">Previous Trading Day OHLC</p>
      <div class="grid grid-cols-2 sm:grid-cols-5 gap-3 text-center text-sm">
        <div class="flex flex-col p-2 bg-slate-700/40 rounded"><span class="font-bold text-slate-400">Open</span><span class="text-white font-mono">{safe(o)}</span></div>
        <div class="flex flex-col p-2 bg-slate-700/40 rounded"><span class="font-bold text-slate-400">High</span><span class="text-white font-mono">{safe(h)}</span></div>
        <div class="flex flex-col p-2 bg-slate-700/40 rounded"><span class="font-bold text-slate-400">Low</span><span class="text-white font-mono">{safe(l)}</span></div>
        <div class="flex flex-col p-2 bg-slate-700/40 rounded"><span class="font-bold text-slate-400">Close</span><span class="text-white font-mono">{safe(c)}</span></div>
        <div class="flex flex-col p-2 rounded bg-slate-700/40"><span class="font-bold text-slate-400">Change%</span><span class="text-white font-mono">{safe(ch)}</span></div>
      </div>
    </div>

    <div class="p-5 bg-blue-900/40 rounded-lg mt-6 border-l-4 border-blue-500 shadow-lg">
      <h3 class="text-xl font-bold text-white mb-1">Prediction for {pred_date}</h3>
      <p class="text-slate-300 text-sm">Model signal based on the latest day’s action.</p>
    </div>

    {perf_block}
  </div>
</div>
"""
    title = f"AI Analysis of {sym} Tomorrow | {name} Stock Prediction"
    desc = "Next-day stock movement from yesterday’s OHLC"
    return tpl_base(title, desc, body, "")

# ---------- Build ----------
def main():
    ensure_dir(DIST)

    markets = walk_markets()
    # Home
    write_text(DIST / "index.html", render_home(markets))

    # Group pages & prediction pages
    for (region, country, exch, csv_path) in markets:
        rows = read_csv_rows(csv_path)
        # group page
        html_group = render_group_page(markets, region, country, exch, rows)
        out_dir = DIST / "groups" / slugify(region) / slugify(country) / slugify(exch)
        write_text(out_dir / "index.html", html_group)

        # prediction pages
        for row in rows:
            sym = (row.get("symbol") or "").strip()
            if not sym: continue
            sym_slug = slugify(sym)
            pred_dir = DIST / slugify(region) / slugify(country) / slugify(exch) / sym_slug / "prediction-tomorrow"
            write_text(pred_dir / "index.html", render_pred_page(region, country, exch, row))

    print(f"Build complete -> {DIST}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERROR:", e, file=sys.stderr)
        sys.exit(1)
