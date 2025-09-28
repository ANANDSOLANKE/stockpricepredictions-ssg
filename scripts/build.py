#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re, json, shutil, datetime, os
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "Data"
DIST = ROOT / "dist"

CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
BASE_URL = CFG.get("base_url", "").rstrip("/")

IMG_EXTS = {".png", ".jpg", ".jpeg", ".svg", ".webp"}

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

# ---------- Logos: index + fallback scan ----------
def ensure_placeholder_logo():
    placeholder = (DIST / "static" / "logo-placeholder.svg")
    if not placeholder.exists():
        svg = """<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64' viewBox='0 0 64 64'>
<rect width='64' height='64' rx='12' fill='#0e1729' stroke='#223157'/>
<path d='M20 36h24M20 28h24' stroke='#4f8cff' stroke-width='3' stroke-linecap='round'/>
</svg>"""
        placeholder.write_text(svg, encoding="utf-8")

def copy_logos_folder():
    src = ROOT / "logos"
    dst = DIST / "logos"
    if dst.exists():
        shutil.rmtree(dst)
    if src.exists():
        shutil.copytree(src, dst)

def normalize_symbol(s: str) -> str:
    # Uppercase; keep only letters/numbers; strip size suffixes like -600/_128 etc.
    s = (s or "").upper()
    s = re.sub(r"[\W_]+", "", s)  # remove non-alnum
    s = re.sub(r"(?:[0-9]{2,4})$", "", s)  # drop trailing size numbers if any
    return s

def load_logos_index():
    # Try repo root first, then logos/
    for p in [ROOT / "logos_index.json", ROOT / "logos" / "logos_index.json"]:
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                # Flatten to {(EXCH,SYMBOL)->relative_path}
                flat = {}
                for exch, mp in data.items():
                    for sym, rel in mp.items():
                        flat[(exch.upper(), normalize_symbol(sym))] = str(rel).lstrip("/\\")
                return flat
            except Exception:
                pass
    return {}

def build_logo_scan_index():
    """
    Walk logos/ once and build a best-effort index:
    key: (EXCHANGE_UPPER, BASENAME_NORMALIZED) -> relative path under logos/
    Uses the *last* directory as 'exchange' (works for logos/argentina/BCBA/*.png and logos/NSE/*.png)
    """
    base = ROOT / "logos"
    idx = {}
    if not base.exists():
        return idx
    for root, dirs, files in os.walk(base):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in IMG_EXTS: continue
            full = Path(root) / f
            rel = full.relative_to(base)
            exchange = full.parent.name  # last folder name = exchange
            name = os.path.splitext(f)[0]
            # also try to remove common size suffixes like --600, _600, -128
            name_norm = normalize_symbol(re.sub(r"(--|_|-)?\d{2,4}$", "", name))
            idx[(exchange.upper(), name_norm)] = str(rel).replace("\\", "/")
    return idx

class LogoResolver:
    def __init__(self):
        self.index = load_logos_index()
        self.scan = {} if self.index else build_logo_scan_index()  # only scan if no explicit index
        ensure_placeholder_logo()
        copy_logos_folder()

    def url_for(self, exchange: str, symbol: str) -> str:
        if not exchange or not symbol:
            return f"{BASE_URL}/static/logo-placeholder.svg"
        key = (exchange.upper(), normalize_symbol(symbol))
        rel = self.index.get(key)
        if not rel:
            rel = self.scan.get(key)
        if rel:
            return f"{BASE_URL}/logos/{rel}"
        return f"{BASE_URL}/static/logo-placeholder.svg"

# ---------- Build ----------
def main():
    date_dir, date_obj = find_latest_date_folder()

    # clean dist
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "static").mkdir(parents=True, exist_ok=True)

    # assets
    css_src = ROOT / "static" / "styles.css"
    if css_src.exists():
        shutil.copy2(css_src, DIST / "static" / "styles.css")
    js_src = ROOT / "static" / "app.js"
    if js_src.exists():
        shutil.copy2(js_src, DIST / "static" / "app.js")

    resolver = LogoResolver()

    # Home (JS drilldown page)
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

    # Regions
    regions = [p for p in date_dir.iterdir() if p.is_dir()]
    regions.sort(key=lambda x: x.name.lower())

    site_index = {"regions": []}

    for region in regions:
        r_name = region.name
        r_slug = slug(r_name)
        r_entry = {"name": r_name, "slug": r_slug, "url": f"{BASE_URL}/{r_slug}/", "countries": []}
        site_index["regions"].append(r_entry)

        # Region HTML
        country_links = []
        for csv in sorted(region.glob("*.csv"), key=lambda x: x.name.lower()):
            country_name = csv.stem.replace("-", " ").title()
            c_slug = slug(country_name)
            r_entry["countries"].append({"name": country_name, "slug": c_slug, "url": f"{BASE_URL}/{r_slug}/{c_slug}/", "exchanges": []})
            country_links.append((country_name, c_slug))
        lis = "".join([f"<li><a href='{BASE_URL}/{r_slug}/{slug(cn)}/'>{cn}</a></li>" for (cn, _) in country_links])
        write(DIST / r_slug / "index.html",
              tpl_base(f"{r_name} Markets — {CFG.get('site_title','')}",
                       f"Browse stock markets in {r_name}.",
                       f"<section class='card'><h2 class='h2'>Countries in {r_name}</h2><ul>{lis}</ul></section>",
                       f"{BASE_URL}/{r_slug}/"))

        # Countries
        for c in r_entry["countries"]:
            country_name, c_slug = c["name"], c["slug"]
            csv = region / f"{country_name.lower().replace(' ', '-')}.csv"
            if not csv.exists():
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
                    dict(sym=sym,name=name,sec=sec,ind=ind,o=o,h=h,l=l,c=cclose,exch=exch)
                )

            exch_links = []
            for exch, rows in sorted(by_exch.items(), key=lambda kv: kv[0].lower()):
                e_slug = slug(exch)
                e_url = f"{BASE_URL}/{r_slug}/{c_slug}/{e_slug}/"
                c["exchanges"].append({"name": exch, "slug": e_slug, "url": e_url})
                exch_links.append(f"<li><a href='{e_url}'>{exch}</a></li>")

                # Table + JSON
                table_rows_html, json_rows = [], []
                for rowd in rows:
                    sym,name,sec,ind,o,h,l,cclose,exch_name = rowd["sym"],rowd["name"],rowd["sec"],rowd["ind"],rowd["o"],rowd["h"],rowd["l"],rowd["c"],rowd["exch"]
                    s_slug = slug(sym)
                    sig, conf, reason = ("",0,"")
                    if None not in (o,h,l,cclose): sig, conf, reason = classify(o,h,l,cclose)

                    # per-stock page
                    if None not in (o,h,l,cclose):
                        pred = next_business_day(date_obj)
                        title = f"AI Analysis of {sym} Tomorrow | {name} Stock Prediction"
                        h1    = f"AI Analysis of {sym} ({name}) Stock for Tomorrow"
                        mdesc = f"Get AI prediction and analysis of {sym} stock ({name}) for tomorrow. Forecast, price target, bullish or bearish trend insights for {exch_name}."
                        stock_body = f"""
<article class="card">
  <h2 class="h2">{h1}</h2>
  <p class="small">Region: {r_name} · Country: {country_name} · Exchange: {exch_name}</p>
  <p class="small">Session Date: {date_obj.isoformat()} · OHLC: O {o}, H {h}, L {l}, C {cclose}</p>
  <div class="card">
    <h3 class="h3">Prediction for {pred.isoformat()}</h3>
    <p><strong>{sig}</strong> — {reason} (confidence {int(conf*100)}%).</p>
  </div>
</article>"""
                        stock_url = f"{BASE_URL}/{r_slug}/{c_slug}/{e_slug}/{s_slug}/prediction-tomorrow/"
                        write(DIST / r_slug / c_slug / e_slug / s_slug / "prediction-tomorrow" / "index.html",
                              tpl_base(title, mdesc, stock_body, stock_url))

                    # HTML table row
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

                    logo_url = resolver.url_for(exch_name, sym)

                    json_rows.append({
                        "symbol": sym,
                        "name": name,
                        "sector": sec,
                        "open": None if o is None else round(o, 2),
                        "high": None if h is None else round(h, 2),
                        "low":  None if l is None else round(l, 2),
                        "close":None if cclose is None else round(cclose, 2),
                        "signal": sig,
                        "logo": logo_url,
                        "url": f"{BASE_URL}/{r_slug}/{c_slug}/{e_slug}/{s_slug}/prediction-tomorrow/"
                    })

                # Exchange HTML page
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

                # JSON for drilldown
                write(DIST / "static" / "exchanges" / r_slug / c_slug / f"{e_slug}.json",
                      json.dumps({"region": r_name, "country": country_name, "exchange": exch, "rows": json_rows}, ensure_ascii=False))

            # Country landing
            write(DIST / r_slug / c_slug / "index.html",
                  tpl_base(f"{country_name} — {CFG.get('site_title','')}",
                           f"Browse exchanges in {country_name}.",
                           "<section class='card'><h2 class='h2'>Exchanges</h2><ul>" +
                           "".join([f"<li><a href='{BASE_URL}/{r_slug}/{c_slug}/{e['slug']}/'>{e['name']}</a></li>"
                                    for e in c['exchanges']]) +
                           "</ul></section>",
                           f"{BASE_URL}/{r_slug}/{c_slug}/"))

    # Homepage index JSON
    write(DIST / "static" / "index.json", json.dumps(site_index, ensure_ascii=False))

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
