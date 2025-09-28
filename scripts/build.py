#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re, json, shutil, datetime
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "Data"
DIST = ROOT / "dist"

CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
BASE_URL = CFG.get("base_url", "").rstrip("/")

def find_latest_date_folder():
    if not DATA_DIR.exists():
        raise SystemExit("Missing Data/ directory at repo root.")
    cand = []
    for p in DATA_DIR.iterdir():
        if p.is_dir() and re.match(r"^\d{2}\.\d{2}\.\d{4}$", p.name):
            d = datetime.datetime.strptime(p.name, "%d.%m.%Y").date()
            cand.append((d, p))
    if not cand:
        raise SystemExit("No dated folder like DD.MM.YYYY inside Data/.")
    cand.sort(key=lambda x: x[0], reverse=True)
    return cand[0][1], cand[0][0]

def next_business_day(d: datetime.date):
    wd = d.weekday()
    if wd == 4: return d + datetime.timedelta(days=3)
    if wd == 5: return d + datetime.timedelta(days=2)
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

def write(path: Path, content: str, kind="text"):
    path.parent.mkdir(parents=True, exist_ok=True)
    if kind == "text":
        path.write_text(content, encoding="utf-8")
    else:
        path.write_bytes(content)

def tpl_base(title, description, body, canonical):
    meta_kw = ", ".join(CFG.get("keywords", []))
    author = CFG.get("author", {})
    site_tagline = CFG.get("site_tagline", "")
    build_time = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    css = f"{BASE_URL}/static/styles.css"
    js = f"{BASE_URL}/static/app.js"
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
<script>window.SPP_BASE="{BASE_URL}";window.SPP_INDEX_URL="{BASE_URL}/static/index.json";</script>
<script src="{js}" defer></script>
</body>
</html>"""

def main():
    date_dir, date_obj = find_latest_date_folder()

    # clean dist
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "static").mkdir(parents=True, exist_ok=True)

    # CSS (fallback)
    css_src = ROOT / "static" / "styles.css"
    if css_src.exists():
        shutil.copy2(css_src, DIST / "static" / "styles.css")
    else:
        write(DIST / "static" / "styles.css",
              "body{font-family:system-ui;background:#0b1220;color:#e8f0fe;margin:0}"
              " .container{max-width:1100px;margin:0 auto;padding:24px}"
              " .card{background:#111a2b;border-radius:16px;padding:16px}"
              " .h1{font-size:28px} .h2{font-size:22px} .h3{font-size:18px}"
              " .grid{display:grid;gap:16px}"
              " .table{width:100%;border-collapse:collapse}"
              " .table td,.table th{border-bottom:1px solid #1f2a44;padding:8px}"
              " .small{color:#9fb3c8}"
        )

    # JS (fallback) – we always provide app.js so no 404
    js_src = ROOT / "static" / "app.js"
    if js_src.exists():
        shutil.copy2(js_src, DIST / "static" / "app.js")
    else:
        write(DIST / "static" / "app.js", r"""
(function(){
  const $ = s => document.querySelector(s);
  const regionsEl = $("#regions"), countriesEl=$("#countries"), exchangesEl=$("#exchanges"), tableEl=$("#stocks_table");
  const BASE = (window.SPP_BASE||"").replace(/\/$/,"");
  function chip(label, onClick, url){ const a=document.createElement("a"); a.className="chip"; a.textContent=label; a.href=url||"javascript:void(0)"; if(onClick){a.addEventListener("click", e=>{e.preventDefault(); onClick();});} return a; }
  function renderTable(rows){ if(!rows||!rows.length){ tableEl.innerHTML="No stocks found for this exchange."; return; }
    const head = "<thead><tr><th>Symbol</th><th>Name</th><th>Sector</th><th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Signal</th></tr></thead>";
    const body = rows.map(r=>`<tr>
      <td><a href="${r.url}">${r.symbol}</a></td>
      <td><a href="${r.url}">${r.name}</a></td>
      <td>${r.sector||""}</td>
      <td>${r.open ?? ""}</td><td>${r.high ?? ""}</td><td>${r.low ?? ""}</td><td>${r.close ?? ""}</td>
      <td>${r.signal||""}</td></tr>`).join("");
    tableEl.innerHTML = `<table class="table">${head}<tbody>${body}</tbody></table>`;
  }
  function loadExchangeJSON(r,c,e){
    const url = `${BASE}/static/exchanges/${r}/${c}/${e}.json`;
    fetch(url).then(r=>r.json()).then(data=>renderTable(data.rows||[])).catch(()=>{tableEl.innerHTML="Could not load stocks for this exchange.";});
  }
  function renderExchanges(region, country){
    exchangesEl.innerHTML=""; tableEl.innerHTML="Pick an exchange.";
    (country.exchanges||[]).forEach(ex=>{
      exchangesEl.appendChild(chip(ex.name, ()=>loadExchangeJSON(region.slug, country.slug, ex.slug), ex.url));
    });
  }
  function renderCountries(region, all){
    countriesEl.innerHTML=""; exchangesEl.innerHTML=""; tableEl.innerHTML="Pick a country.";
    (region.countries||[]).forEach(c=>{ countriesEl.appendChild(chip(c.name, ()=>renderExchanges(region,c), c.url)); });
  }
  function renderRegions(all){
    regionsEl.innerHTML=""; (all.regions||[]).forEach(r=>{ regionsEl.appendChild(chip(r.name, ()=>renderCountries(r,all), r.url)); });
  }
  fetch(window.SPP_INDEX_URL).then(r=>r.json()).then(data=>{ renderRegions(data); }).catch(()=>{ regionsEl.innerHTML="Could not load regions."; });
})();
""")

    # Home content
    home_body = """
<section class='card'>
  <h2 class='h2'>Browse Markets</h2>
  <div class="picker">
    <div class="row"><div class="row-title">Regions</div><div id="regions" class="chips"></div></div>
    <div class="row"><div class="row-title">Countries</div><div id="countries" class="chips"></div></div>
    <div class="row"><div class="row-title">Exchanges</div><div id="exchanges" class="chips"></div></div>
  </div>
</section>
<section class='card'>
  <h2 class='h2'>Stocks</h2>
  <div id="stocks_table">Pick a region → country → exchange</div>
</section>
"""
    write(DIST / "index.html", tpl_base(
        f"{CFG.get('site_title','')} — {CFG.get('site_tagline','')}",
        "Interactive drilldown: region → country → exchange → stocks.",
        home_body, f"{BASE_URL}/"
    ))

    # Build JSON index + pages
    regions = [p for p in (find_latest_date_folder()[0]).iterdir() if p.is_dir()]
    # we already called find_latest_date_folder above; reuse results properly
    date_dir, date_obj = find_latest_date_folder()
    regions = [p for p in date_dir.iterdir() if p.is_dir()]
    regions.sort(key=lambda x: x.name.lower())

    site_index = {"regions": []}
    sitemap_urls = [f"{BASE_URL}/"]

    for region in regions:
        r_name = region.name
        r_slug = slug(r_name)
        r_entry = {"name": r_name, "slug": r_slug, "url": f"{BASE_URL}/{r_slug}/", "countries": []}
        site_index["regions"].append(r_entry)
        sitemap_urls.append(r_entry["url"].rstrip("/"))

        country_links = []
        for csv in sorted(region.glob("*.csv"), key=lambda x: x.name.lower()):
            country_name = csv.stem.replace("-", " ").title()
            c_slug = slug(country_name)
            c_url = f"{BASE_URL}/{r_slug}/{c_slug}/"
            r_entry["countries"].append({"name": country_name, "slug": c_slug, "url": c_url, "exchanges": []})
            country_links.append((country_name, c_slug))
            sitemap_urls.append(c_url.rstrip("/"))

        lis = "".join([f"<li><a href='{BASE_URL}/{r_slug}/{slug(cn)}/'>{cn}</a></li>" for (cn, _) in country_links])
        write(DIST / r_slug / "index.html",
              tpl_base(f"{r_name} Markets — {CFG.get('site_title','')}",
                       f"Browse stock markets in {r_name}.",
                       f"<section class='card'><h2 class='h2'>Countries in {r_name}</h2><ul>{lis}</ul></section>",
                       f"{BASE_URL}/{r_slug}/"))

        # Build each country
        for c in r_entry["countries"]:
            country_name, c_slug = c["name"], c["slug"]
            csv = region / f"{country_name.lower().replace(' ', '-')}.csv"
            if not csv.exists():  # skip if missing
                continue
            df = read_csv_safe(csv)

            by_exch = {}
            for _, row in df.iterrows():
                sym = str(row["symbol"]).strip()
                name = str(row["description"]).strip() or sym
                exch = str(row["exchange"]).strip()
                sec  = str(row["sector"]).strip() or "Unknown"
                ind  = str(row["industry"]).strip()
                try:
                    o = float(row["open"]); h = float(row["high"]); l = float(row["low"]); cclose = float(row["close"])
                except Exception:
                    o=h=l=cclose=None
                by_exch.setdefault(exch or "UNKNOWN", []).append(
                    dict(sym=sym,name=name,sec=sec,ind=ind,o=o,h=h,l=l,c=cclose)
                )

            exch_links = []
            for exch, rows in sorted(by_exch.items(), key=lambda kv: kv[0].lower()):
                e_slug = slug(exch)
                e_url = f"{BASE_URL}/{r_slug}/{c_slug}/{e_slug}/"
                c["exchanges"].append({"name": exch, "slug": e_slug, "url": e_url})
                sitemap_urls.append(e_url.rstrip("/"))
                exch_links.append(f"<li><a href='{e_url}'>{exch}</a></li>")

                # Build stock pages + exchange HTML + exchange JSON
                table_rows_html, json_rows = [], []
                for rowd in rows:
                    sym,name,sec,ind,o,h,l,cclose = rowd["sym"],rowd["name"],rowd["sec"],rowd["ind"],rowd["o"],rowd["h"],rowd["l"],rowd["c"]
                    s_slug = slug(sym)
                    sig, conf, reason = ("",0,"")
                    if None not in (o,h,l,cclose): sig, conf, reason = classify(o,h,l,cclose)

                    if None not in (o,h,l,cclose):
                        pred = next_business_day(date_obj)
                        title = f"AI Analysis of {sym} Tomorrow | {name} Stock Prediction"
                        h1    = f"AI Analysis of {sym} ({name}) Stock for Tomorrow"
                        mdesc = f"Get AI prediction and analysis of {sym} stock ({name}) for tomorrow. Forecast, price target, bullish or bearish trend insights for {exch}."
                        stock_body = f"""
<article class="card">
  <h2 class="h2">{h1}</h2>
  <p class="small">Region: {r_name} · Country: {country_name} · Exchange: {exch}</p>
  <p class="small">Session Date: {date_obj.isoformat()} · OHLC: O {o}, H {h}, L {l}, C {cclose}</p>
  <div class="card">
    <h3 class="h3">Prediction for {pred.isoformat()}</h3>
    <p><strong>{sig}</strong> — {reason} (confidence {int(conf*100)}%).</p>
  </div>
</article>"""
                        stock_url = f"{BASE_URL}/{r_slug}/{c_slug}/{e_slug}/{s_slug}/prediction-tomorrow/"
                        write(DIST / r_slug / c_slug / e_slug / s_slug / "prediction-tomorrow" / "index.html",
                              tpl_base(title, mdesc, stock_body, stock_url))
                        sitemap_urls.append(stock_url.rstrip("/"))

                    table_rows_html.append(
                        f"<tr>"
                        f"<td><a href='{BASE_URL}/{r_slug}/{c_slug}/{e_slug}/{s_slug}/prediction-tomorrow/'>{sym}</a></td>"
                        f"<td><a href='{BASE_URL}/{r_slug}/{c_slug}/{e_slug}/{s_slug}/prediction-tomorrow/'>{name}</a></td>"
                        f"<td>{sec}</td>"
                        f"<td>{'' if o is None else f'{o:.2f}'}</td>"
                        f"<td>{'' if h is None else f'{h:.2f}'}</td>"
                        f"<td>{'' if l is None else f'{l:.2f}'}</td>"
                        f"<td>{'' if cclose is None else f'{cclose:.2f}'}</td>"
                        f"<td>{sig}</td>"
                        f"</tr>"
                    )

                    json_rows.append({
                        "symbol": sym,
                        "name": name,
                        "sector": sec,
                        "open": None if o is None else round(o, 2),
                        "high": None if h is None else round(h, 2),
                        "low":  None if l is None else round(l, 2),
                        "close":None if cclose is None else round(cclose, 2),
                        "signal": sig,
                        "url": f"{BASE_URL}/{r_slug}/{c_slug}/{e_slug}/{s_slug}/prediction-tomorrow/"
                    })

                exch_table = (
                    "<table class='table'>"
                    "<thead><tr>"
                    "<th>Symbol</th><th>Name</th><th>Sector</th>"
                    "<th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Signal</th>"
                    "</tr></thead><tbody>"
                    + "\n".join(table_rows_html) + "</tbody></table>"
                )
                write(DIST / r_slug / c_slug / e_slug / "index.html",
                      tpl_base(f"{country_name} {exch} — {CFG.get('site_title','')}",
                               f"Browse {exch} listings in {country_name}.",
                               exch_table, e_url))

                exch_json_path = DIST / "static" / "exchanges" / r_slug / c_slug / f"{e_slug}.json"
                write(exch_json_path, json.dumps({
                    "region": r_name, "country": country_name, "exchange": exch,
                    "rows": json_rows
                }, ensure_ascii=False), kind="text")

            # Country landing
            write(DIST / r_slug / c_slug / "index.html",
                  tpl_base(f"{country_name} — {CFG.get('site_title','')}",
                           f"Browse exchanges in {country_name}.",
                           "<section class='card'><h2 class='h2'>Exchanges</h2><ul>" +
                           "".join([f"<li><a href='{BASE_URL}/{r_slug}/{c_slug}/{e['slug']}/'>{e['name']}</a></li>"
                                    for e in c['exchanges']]) +
                           "</ul></section>",
                           f"{BASE_URL}/{r_slug}/{c_slug}/"))

    # Write index.json for the drilldown
    write(DIST / "static" / "index.json", json.dumps(site_index, ensure_ascii=False), kind="text")

    # robots + sitemap
    write(DIST / "robots.txt", f"Sitemap: {BASE_URL}/sitemap.xml\nUser-agent: *\nAllow: /\n")
    urls = []
    for p in DIST.rglob("index.html"):
        rel = "/" + str(p.relative_to(DIST)).replace("\\", "/")
        urls.append(f"{BASE_URL}{rel[:-10]}")
    urls = sorted(set(urls))
    write(DIST / "sitemap.xml",
          "<?xml version='1.0' encoding='UTF-8'?>"
          "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
          + "".join([f"<url><loc>{u}</loc></url>" for u in urls]) + "</urlset>")

    print("Build complete →", DIST)

if __name__ == "__main__":
    main()
