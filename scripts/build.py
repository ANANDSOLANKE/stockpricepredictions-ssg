#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SGG-1 build.py — Data/LastTradingDay + fast logos + Change% column + AI button
-------------------------------------------------------------------------------
- Reads Data/LastTradingDay/<Group>/<country>.csv
- Keeps your original UI (static/styles.css + static/app.js)
- Adds "Change%" column after Close
- Replaces Signal cell with a clickable "AI Prediction" button
- Faster logos: optional skip copying with env SKIP_LOGOS=1 (uses placeholder)
"""

import csv, html, json, os, re, unicodedata, shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

# ----------------- Paths & Config -----------------
ROOT = Path(__file__).resolve().parents[1]
DATA_LAST = ROOT / "Data" / "LastTradingDay"
DIST = ROOT / "dist"

CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
BASE_URL = CFG.get("base_url", "").rstrip("/")

IMG_EXTS = {".png", ".jpg", ".jpeg", ".svg", ".webp"}

# Toggle: skip copying/scanning logos to make builds faster (placeholder used)
SKIP_LOGOS = os.environ.get("SKIP_LOGOS", "0") == "1"

# ----------------- Helpers -----------------
def ensure_dir(p: Path): p.mkdir(parents=True, exist_ok=True)
def write_text(p: Path, s: str): p.parent.mkdir(parents=True, exist_ok=True); p.write_text(s, encoding="utf-8")
def write_json(p: Path, obj): p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")

def slug(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "item"

INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]+')
def safe_filename(name: str) -> str:
    return INVALID_FILENAME_CHARS.sub("_", (name or "").strip())

def classify(o,h,l,c):
    rng = max(h,l) - min(h,l)
    body = abs(c-o)
    if rng <= 0: return "Sideways", 0.5, "No range"
    ratio = body/rng if rng else 0.0
    if ratio < 0.2: return "Sideways", 0.5, "Small body vs range — indecision"
    if c > o: return "Bullish", min(0.9, 0.6 + ratio/2), "Close above open"
    if c < o: return "Bearish", min(0.9, 0.6 + ratio/2), "Close below open"
    return "Sideways", 0.5, "Flat"

def next_business_day(d):
    wd = d.weekday()
    if wd == 4: return d + timedelta(days=3)
    if wd == 5: return d + timedelta(days=2)
    return d + timedelta(days=1)

def read_csv_safe(p: Path) -> List[Dict[str,str]]:
    rows: List[Dict[str,str]] = []
    with open(p, "r", encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            rows.append({(k or "").strip().lower(): (v or "").strip() for k, v in r.items()})
    # ensure keys used downstream
    need = ["symbol","description","exchange","sector","industry","open","high","low","close","change_percent","change%"]
    for r in rows:
        for k in need:
            r.setdefault(k, "")
    return rows

# ----------------- Assets (css/js/logos) -----------------
def copy_static_assets():
    ensure_dir(DIST / "static")
    for name in ("styles.css","app.js"):
        src = ROOT / "static" / name
        if src.exists():
            shutil.copy2(src, DIST / "static" / name)

def ensure_placeholder_logo():
    svg = """<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64' viewBox='0 0 64 64'>
<rect width='64' height='64' rx='12' fill='#0e1729' stroke='#223157'/>
<path d='M20 36h24M20 28h24' stroke='#4f8cff' stroke-width='3' stroke-linecap='round'/>
</svg>"""
    p = DIST / "static" / "logo-placeholder.svg"
    if not p.exists():
        ensure_dir(p.parent); p.write_text(svg, encoding="utf-8")

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Z0-9]", "", s.upper())

def name_tokens(name: str):
    toks = re.split(r"[^A-Za-z0-9]+", name or "")
    STOP = {"LTD","LIMITED","CO","COMPANY","PLC","INC","LLC","SA","SAA","SAS",
            "BSC","BSC.","B.S.C","ORD","PREF","THE","OF","AND","HOLDINGS",
            "HOLDING","GROUP","CORP","CORPORATION","BANK","INDUSTRIES","INDUSTRY"}
    toks = [t for t in toks if t and t.upper() not in STOP]
    return toks[:3]

def load_logos_index() -> Dict[tuple, str]:
    for p in [ROOT / "logos_index.json", ROOT / "logos" / "logos_index.json"]:
        if p.exists():
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
                flat = {}
                for exch, mp in (raw or {}).items():
                    for sym, rel in (mp or {}).items():
                        flat[(exch.upper(), _norm(sym))] = str(rel).lstrip("/\\")
                return flat
            except Exception:
                pass
    return {}

def build_scan_index():
    base = ROOT / "logos"
    idx = {}
    if not base.exists(): return idx
    for root, _, files in os.walk(base):
        for f in files:
            if os.path.splitext(f)[1].lower() not in IMG_EXTS: continue
            full = Path(root) / f
            rel = full.relative_to(base).as_posix()
            exch = full.parent.name  # last folder name as exchange
            stem = os.path.splitext(f)[0]
            stem = re.sub(r"(--|_|-)?\d{2,4}$", "", stem)  # drop size suffixes
            idx.setdefault(exch.upper(), []).append((_norm(stem), rel))
    return idx

class LogoResolver:
    def __init__(self):
        self.placeholder = f"{BASE_URL}/static/logo-placeholder.svg"
        if SKIP_LOGOS:
            self.curated = {}
            self.scan = {}
        else:
            # Copy logos folder once (fast if small; if big, set SKIP_LOGOS=1)
            src = ROOT / "logos"
            dst = DIST / "logos"
            if src.exists():
                if not dst.exists():
                    shutil.copytree(src, dst)
            self.curated = load_logos_index()
            self.scan = build_scan_index()
        self.cache = {}

    def url_for(self, exchange: str, symbol: str, name: str = "") -> str:
        key = (exchange or "", symbol or "")
        if key in self.cache: return self.cache[key]
        if SKIP_LOGOS:
            self.cache[key] = self.placeholder
            return self.placeholder

        exch = (exchange or "").upper()
        symn = _norm(symbol)

        # curated exact
        rel = self.curated.get((exch, symn))
        if rel:
            url = f"{BASE_URL}/logos/{rel}"
            self.cache[key] = url; return url

        candidates = self.scan.get(exch, [])
        # exact filename == symbol
        for stem_norm, rel in candidates:
            if stem_norm == symn:
                url = f"{BASE_URL}/logos/{rel}"
                self.cache[key] = url; return url
        # contains relationship
        for stem_norm, rel in candidates:
            if symn and (symn in stem_norm or stem_norm in symn):
                url = f"{BASE_URL}/logos/{rel}"
                self.cache[key] = url; return url
        # name tokens score
        toks = [_norm(t) for t in name_tokens(name)]
        best = (0.0, None)
        for stem_norm, rel in candidates:
            hits = sum(1 for t in toks if t and t in stem_norm)
            if hits:
                score = hits * (10.0 / (1.0 + len(stem_norm)))
                if score > best[0]: best = (score, rel)
        if best[1]:
            url = f"{BASE_URL}/logos/{best[1]}"
            self.cache[key] = url; return url

        self.cache[key] = self.placeholder
        return self.placeholder

# ----------------- Load Data/LastTradingDay -----------------
def load_tree_from_last_trading_day():
    """
    Returns tree[group_slug][country_slug] = {
        group_name, group_slug, country_name, country_slug, csv_path, rows
    }
    """
    tree: Dict[str, Dict[str, Dict]] = {}
    if not DATA_LAST.exists():
        return tree

    for group_dir in sorted([d for d in DATA_LAST.iterdir() if d.is_dir()]):
        group_name = group_dir.name
        group_slug = slug(group_name)
        tree.setdefault(group_slug, {})
        for csvp in sorted(group_dir.glob("*.csv")):
            country_slug = csvp.stem
            country_name = country_slug.replace("-", " ").title()
            rows = read_csv_safe(csvp)
            tree[group_slug][country_slug] = {
                "group_name": group_name,
                "group_slug": group_slug,
                "country_name": country_name,
                "country_slug": country_slug,
                "csv_path": csvp,
                "rows": rows
            }
    return tree

# ----------------- Templating -----------------
def tpl_base(title, description, body, canonical):
    meta_kw = ", ".join(CFG.get("keywords", []))
    author = CFG.get("author", {})
    site_tagline = CFG.get("site_tagline", "")
    build_time = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    css = f"{BASE_URL}/static/styles.css"
    js  = f"{BASE_URL}/static/app.js"
    # simple button style (for AI Prediction)
    extra_css = """
    <style>.btn{display:inline-block;padding:.35rem .7rem;border:1px solid #27406b;border-radius:8px}
    .btn:hover{background:#122036}</style>"""
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="canonical" href="{canonical}">
<meta name="description" content="{html.escape(description)}">
<meta name="keywords" content="{html.escape(meta_kw)}">
<meta name="author" content="{html.escape(author.get('name',''))}">
<link rel="stylesheet" href="{css}">{extra_css}
</head>
<body>
<div class="container">
<header class="hero card">
  <div class="breadcrumbs"><a href="{BASE_URL}/">Home</a></div>
  <h1 class="h1">{html.escape(title)}</h1>
  <p class="small">{html.escape(site_tagline)}</p>
  <div class="kv">
    <div><strong>Purpose:</strong> Transparent, reproducible SSG for daily stock pages.</div>
    <div><strong>Last build:</strong> {build_time}</div>
  </div>
</header>
<main class="grid">
{body}
</main>
<footer class="footer">
  <div>E-E-A-T: Author <strong>{html.escape(author.get('name',''))}</strong> · Org: {html.escape(author.get('org','',))} · Contact: <a href="mailto:{html.escape(author.get('contact_email',''))}">{html.escape(author.get('contact_email',''))}</a></div>
  <div>Data provenance: Trading day snapshots. Prediction target = next business day.</div>
</footer>
</div>
<script>window.SPP_BASE="{BASE_URL}";window.SPP_INDEX_URL="{BASE_URL}/static/index.json";</script>
<script src="{js}" defer></script>
</body></html>"""

# ----------------- Build -----------------
def main():
    # Note: keep dist; overwrite files (faster than full delete + copy logos)
    ensure_dir(DIST / "static")
    copy_static_assets()
    ensure_placeholder_logo()

    # Load data
    tree = load_tree_from_last_trading_day()
    resolver = LogoResolver()

    # Home shell
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
    write_text(DIST / "index.html", tpl_base(
        f"{CFG.get('site_title','')} — {CFG.get('site_tagline','')}",
        "Interactive drilldown: region → country → exchange → stocks.",
        home_body, f"{BASE_URL}/"
    ))

    # JSON index for drilldown
    site_index = {"regions": []}

    # groups
    for gslug in sorted(tree.keys()):
        any_country = next(iter(tree[gslug].values()))
        gname = any_country["group_name"]

        region_entry = {"name": gname, "slug": gslug, "url": f"{BASE_URL}/{gslug}/", "countries": []}
        site_index["regions"].append(region_entry)

        # country list page
        countries = sorted(tree[gslug].keys())
        links = []
        for cslug in countries:
            cname = tree[gslug][cslug]["country_name"]
            region_entry["countries"].append({"name": cname, "slug": cslug, "url": f"{BASE_URL}/{gslug}/{cslug}/", "exchanges": []})
            links.append(f"<li><a href='{BASE_URL}/{gslug}/{cslug}/'>{html.escape(cname)}</a></li>")
        write_text(DIST / gslug / "index.html",
                   tpl_base(f"{gname} Markets — {CFG.get('site_title','')}",
                           f"Browse stock markets in {gname}.",
                           f"<section class='card'><h2 class='h2'>Countries in {html.escape(gname)}</h2><ul>{''.join(links)}</ul></section>",
                           f"{BASE_URL}/{gslug}/"))

        # countries → exchanges
        for c in region_entry["countries"]:
            cslug, cname = c["slug"], c["name"]
            rows = tree[gslug][cslug]["rows"]

            # group by exchange
            by_exch: Dict[str, List[Dict[str,str]]] = {}
            for r in rows:
                exch = (r.get("exchange") or "UNKNOWN").strip()
                by_exch.setdefault(exch, []).append(r)

            e_links = []
            for exch, erows in sorted(by_exch.items(), key=lambda kv: kv[0].lower()):
                e_slug = slug(exch)
                e_url  = f"{BASE_URL}/{gslug}/{cslug}/{e_slug}/"
                c["exchanges"].append({"name": exch, "slug": e_slug, "url": e_url})
                e_links.append(f"<li><a href='{e_url}'>{html.escape(exch)}</a></li>")

                # table rows + JSON rows
                table_rows_html, json_rows = [], []
                for r in erows:
                    sym = (r.get("symbol") or "").strip()
                    name = (r.get("description") or sym or "").strip()
                    sec  = (r.get("sector") or "").strip()
                    # OHLC + change%
                    def _f(x):
                        try: return float(x)
                        except: return None
                    o = _f(r.get("open")); h = _f(r.get("high")); l = _f(r.get("low")); cclose = _f(r.get("close"))
                    chg_pct_raw = r.get("change_percent") or r.get("change%") or ""
                    try:
                        chg_pct = float(chg_pct_raw)
                    except:
                        chg_pct = None

                    s_slug = slug(sym)
                    sig, conf, reason = ("",0,"")
                    if None not in (o,h,l,cclose):
                        sig, conf, reason = classify(o,h,l,cclose)

                    # per-stock page path
                    stock_url = f"{BASE_URL}/{gslug}/{cslug}/{e_slug}/{s_slug}/prediction-tomorrow/"

                    # AI Prediction button in Signal column
                    btn = f"<a class='btn' href='{stock_url}'>AI Prediction</a>"

                    # table row
                    table_rows_html.append(
                        "<tr>"
                        f"<td><a href='{stock_url}'>{html.escape(sym)}</a></td>"
                        f"<td><a href='{stock_url}'>{html.escape(name)}</a></td>"
                        f"<td>{html.escape(sec)}</td>"
                        f"<td>{'' if o is None else f'{o:.2f}'}</td>"
                        f"<td>{'' if h is None else f'{h:.2f}'}</td>"
                        f"<td>{'' if l is None else f'{l:.2f}'}</td>"
                        f"<td>{'' if cclose is None else f'{cclose:.2f}'}</td>"
                        f"<td>{'' if chg_pct is None else f'{chg_pct:.2f}%'}</td>"
                        f"<td>{btn}</td>"
                        "</tr>"
                    )

                    # JSON row (kept for app.js)
                    logo_url = resolver.url_for(exch, sym, name)
                    json_rows.append({
                        "symbol": sym,
                        "name": name,
                        "sector": sec,
                        "open": None if o is None else round(o,2),
                        "high": None if h is None else round(h,2),
                        "low":  None if l is None else round(l,2),
                        "close":None if cclose is None else round(cclose,2),
                        "change_percent": None if chg_pct is None else round(chg_pct,4),
                        "signal": sig,
                        "logo": logo_url,
                        "url": stock_url
                    })

                    # quick per-stock SEO page (lightweight, no charts)
                    if sym and None not in (o,h,l,cclose):
                        pred = next_business_day(datetime.utcnow().date())
                        title = f"AI Analysis of {sym} Tomorrow | {name} Stock Prediction"
                        h1    = f"AI Analysis of {sym} ({name}) Stock for Tomorrow"
                        mdesc = f"Get AI prediction and analysis of {sym} ({name}) for tomorrow. Forecast and trend insights for {exch}."
                        body  = f"""
<article class="card">
  <h2 class="h2">{html.escape(h1)}</h2>
  <p class="small">Region: {html.escape(gname)} · Country: {html.escape(cname)} · Exchange: {html.escape(exch)}</p>
  <p class="small">OHLC: O {o:.2f}, H {h:.2f}, L {l:.2f}, C {cclose:.2f} · Change%: {'' if chg_pct is None else f'{chg_pct:.2f}%'}</p>
  <div class="card">
    <h3 class="h3">Prediction for {pred.isoformat()}</h3>
    <p><strong>{html.escape(sig or 'Signal')}</strong> — {html.escape(reason or 'Model-based signal')} (confidence {int(conf*100)}%).</p>
  </div>
</article>"""
                        write_text(DIST / gslug / cslug / e_slug / s_slug / "prediction-tomorrow" / "index.html",
                                   tpl_base(title, mdesc, body, stock_url))

                # page for the exchange
                table_html = (
                    "<table class='table'>"
                    "<thead><tr>"
                    "<th>Symbol</th><th>Name</th><th>Sector</th>"
                    "<th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Change%</th><th>Signal</th>"
                    "</tr></thead><tbody>"
                    + "\n".join(table_rows_html) + "</tbody></table>"
                )
                write_text(DIST / gslug / cslug / e_slug / "index.html",
                           tpl_base(f"{cname} {exch} — {CFG.get('site_title','')}",
                                    f"Browse {exch} listings in {cname}.",
                                    table_html, f"{BASE_URL}/{gslug}/{cslug}/{e_slug}/"))

                # JSON for app.js
                write_json(DIST / "static" / "exchanges" / gslug / cslug / f"{e_slug}.json",
                           {"region": gname, "country": cname, "exchange": exch, "rows": json_rows})

            # country landing (links to exchanges)
            write_text(DIST / gslug / cslug / "index.html",
                       tpl_base(f"{cname} — {CFG.get('site_title','')}",
                                f"Browse exchanges in {cname}.",
                                "<section class='card'><h2 class='h2'>Exchanges</h2><ul>"
                                + "".join([f"<li><a href='{BASE_URL}/{gslug}/{cslug}/{e['slug']}/'>{html.escape(e['name'])}</a></li>"
                                           for e in c['exchanges']]) +
                                "</ul></section>",
                                f"{BASE_URL}/{gslug}/{cslug}/"))

    # top-level index.json for the drilldown
    write_json(DIST / "static" / "index.json", site_index)

    # robots + sitemap (light)
    write_text(DIST / "robots.txt", f"Sitemap: {BASE_URL}/sitemap.xml\nUser-agent: *\nAllow: /\n")
    urls = []
    for p in DIST.rglob("index.html"):
        rel = "/" + str(p.relative_to(DIST)).replace("\\", "/")
        urls.append(f"{BASE_URL}{rel[:-10]}")
    urls = sorted(set(urls))
    write_text(
        DIST / "sitemap.xml",
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
        + "".join([f"<url><loc>{u}</loc></url>" for u in urls]) + "</urlset>"
    )
    print("Build complete →", DIST)

if __name__ == "__main__":
    main()
