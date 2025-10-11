#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SGG-1 build.py
- Uses Data/LastTradingDay/<Group>/<country>.csv as main source
- Adds per-stock prediction pages with:
   * Inline SVG historical close-price chart (last up to 10 days)
   * Closing price under stock name
   * Two tables: Top Rising (same sector) & Top Losing (same sector), 50 rows each
- Keeps only the last 10 days in Data/Historical/* (auto-prune)
- Writes exchange JSON used by static/app.js (unchanged interface)
- Colors %Change in per-stock pages via CSS classes; list pages colored by app.js

Speed:
- Honors SKIP_LOGOS=1 to skip logo scanning/copying during CI runs
"""

import csv, html, json, os, re, unicodedata, shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

ROOT = Path(__file__).resolve().parents[1]
DATA_LAST = ROOT / "Data" / "LastTradingDay"
DATA_HIST = ROOT / "Data" / "Historical"
DIST = ROOT / "dist"

CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
BASE_URL = CFG.get("base_url", "").rstrip("/")

IMG_EXTS = {".png", ".jpg", ".jpeg", ".svg", ".webp"}
SKIP_LOGOS = os.environ.get("SKIP_LOGOS", "0") == "1"

# ----------------- helpers -----------------
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
    return rows

# ----------------- assets (css/js/logos) -----------------
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

        rel = self.curated.get((exch, symn))
        if rel:
            url = f"{BASE_URL}/logos/{rel}"
            self.cache[key] = url; return url

        candidates = self.scan.get(exch, [])
        for stem_norm, rel in candidates:
            if stem_norm == symn:
                url = f"{BASE_URL}/logos/{rel}"
                self.cache[key] = url; return url
        for stem_norm, rel in candidates:
            if symn and (symn in stem_norm or stem_norm in symn):
                url = f"{BASE_URL}/logos/{rel}"
                self.cache[key] = url; return url

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

# ----------------- data load -----------------
def load_tree_from_last_trading_day():
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

# ----------------- historical utils -----------------
def prune_historical_keep_last_10():
    if not DATA_HIST.exists(): return
    dated = sorted([d for d in DATA_HIST.iterdir() if d.is_dir()], key=lambda p: p.name)
    if len(dated) <= 10: return
    for old in dated[:-10]:
        try:
            shutil.rmtree(old)
        except Exception:
            pass

def read_close_history_for_symbol(group_name: str, country_slug: str, symbol: str, lookback: int = 10) -> List[Tuple[str, float]]:
    """
    Scans Data/Historical/<YYYY-MM-DD>/<Group>/<country>.csv across most recent dates,
    extracting close prices for the given symbol.
    Returns list of (date_str, close) sorted ascending by date.
    """
    out: List[Tuple[str, float]] = []
    if not DATA_HIST.exists(): return out
    dates = sorted([d.name for d in DATA_HIST.iterdir() if d.is_dir()])[-lookback:]
    for dstr in dates:
        csvp = DATA_HIST / dstr / group_name / f"{country_slug}.csv"
        if not csvp.exists(): 
            continue
        try:
            rows = read_csv_safe(csvp)
            sym_lower = (symbol or "").strip().lower()
            for r in rows:
                if (r.get("symbol") or r.get("ticker") or "").strip().lower() == sym_lower:
                    try:
                        close = float(r.get("close") or r.get("price") or "")
                        out.append((dstr, close))
                    except Exception:
                        pass
                    break
        except Exception:
            pass
    out.sort(key=lambda t: t[0])
    return out

def svg_line_chart(data: List[Tuple[str,float]], width=900, height=220, pad=28) -> str:
    """Generates an inline SVG area chart for (date, close)."""
    if not data:
        return "<div class='muted'>No historical data</div>"
    xs = list(range(len(data)))
    ys = [v for _, v in data]
    x_min, x_max = 0, max(xs) if xs else 1
    y_min, y_max = min(ys), max(ys)
    if y_max <= y_min:
        y_max = y_min + 1.0

    def sx(i):  # scale x
        return pad + (i - x_min) * (width - 2*pad) / max(1, (x_max - x_min))
    def sy(v):  # scale y (invert)
        return height - pad - (v - y_min) * (height - 2*pad) / (y_max - y_min)

    # path
    points = [(sx(i), sy(v)) for i, (_, v) in enumerate(data)]
    path_d = "M " + " L ".join(f"{x:.2f} {y:.2f}" for x,y in points)
    area_d = path_d + f" L {sx(x_max):.2f} {height-pad:.2f} L {sx(x_min):.2f} {height-pad:.2f} Z"

    # x labels (dates)
    labels = "".join(
        f"<text x='{sx(i):.2f}' y='{height-6}' text-anchor='middle' class='axis'>{html.escape(d[-5:])}</text>"
        for i,(d,_) in enumerate(data)
    )

    svg = f"""
<svg class="spark" viewBox="0 0 {width} {height}" preserveAspectRatio="none" aria-label="Historical close price">
  <defs>
    <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#22c55e" stop-opacity="0.28"/>
      <stop offset="100%" stop-color="#22c55e" stop-opacity="0.02"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="{width}" height="{height}" rx="14" class="spark-bg"/>
  <path d="{area_d}" class="spark-area"/>
  <path d="{path_d}" class="spark-line"/>
  {labels}
</svg>"""
    return svg

# ----------------- templating -----------------
def tpl_base(title, description, body, canonical):
    meta_kw = ", ".join(CFG.get("keywords", []))
    author = CFG.get("author", {})
    site_tagline = CFG.get("site_tagline", "")
    build_time = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    css = f"{BASE_URL}/static/styles.css"
    js  = f"{BASE_URL}/static/app.js"
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="canonical" href="{canonical}">
<meta name="description" content="{html.escape(description)}">
<meta name="keywords" content="{html.escape(meta_kw)}">
<meta name="author" content="{html.escape(author.get('name',''))}">
<link rel="stylesheet" href="{css}">
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

# ----------------- build -----------------
def main():
    # prepare
    ensure_dir(DIST / "static")
    copy_static_assets()
    ensure_placeholder_logo()
    prune_historical_keep_last_10()

    tree = load_tree_from_last_trading_day()
    resolver = LogoResolver()

    # homepage shell (unchanged)
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

    site_index = {"regions": []}

    for gslug in sorted(tree.keys()):
        any_country = next(iter(tree[gslug].values()))
        gname = any_country["group_name"]

        region_entry = {"name": gname, "slug": gslug, "url": f"{BASE_URL}/{gslug}/", "countries": []}
        site_index["regions"].append(region_entry)

        # region page
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

                table_rows_html, json_rows = [], []
                for r in erows:
                    sym = (r.get("symbol") or "").strip()
                    name = (r.get("description") or sym or "").strip()
                    sec  = (r.get("sector") or "").strip()
                    def _f(x):
                        try: return float(x)
                        except: return None
                    o = _f(r.get("open")); h = _f(r.get("high")); l = _f(r.get("low")); cclose = _f(r.get("close"))
                    chg_raw = r.get("change_percent") or r.get("change%") or ""
                    try: chg_pct = float(chg_raw)
                    except: chg_pct = None

                    s_slug = slug(sym)
                    sig, conf, reason = ("",0,"")
                    if None not in (o,h,l,cclose):
                        sig, conf, reason = classify(o,h,l,cclose)

                    stock_url = f"{BASE_URL}/{gslug}/{cslug}/{e_slug}/{s_slug}/prediction-tomorrow/"
                    logo_url = resolver.url_for(exch, sym, name)

                    # Exchange table row (displayed by /groups/... page)
                    chg_txt = "" if chg_pct is None else f"{chg_pct:.2f}%"
                    chg_cls = "chg-pos" if (chg_pct or 0) > 0 else ("chg-neg" if (chg_pct or 0) < 0 else "muted")
                    table_rows_html.append(
                        "<tr>"
                        f"<td><a href='{stock_url}'>{html.escape(sym)}</a></td>"
                        f"<td><a href='{stock_url}' class='name-with-logo'><img class='logo-ico' src='{logo_url}' alt=''>{html.escape(name)}</a></td>"
                        f"<td>{html.escape(sec)}</td>"
                        f"<td>{'' if o is None else f'{o:.2f}'}</td>"
                        f"<td>{'' if h is None else f'{h:.2f}'}</td>"
                        f"<td>{'' if l is None else f'{l:.2f}'}</td>"
                        f"<td>{'' if cclose is None else f'{cclose:.2f}'}</td>"
                        f"<td class='{chg_cls}'>{chg_txt}</td>"
                        f"<td><a class='btn' href='{stock_url}'>AI Prediction</a></td>"
                        "</tr>"
                    )

                    # JSON row for app.js list view
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

                    # -------- per-stock page --------
                    if sym and None not in (o,h,l,cclose):
                        # inline history (up to 10 days)
                        hist = read_close_history_for_symbol(gname, cslug, sym, lookback=10)
                        chart_html = svg_line_chart(hist)

                        # same sector peers
                        peers = [x for x in erows if (x.get("sector","").strip().lower() == sec.lower())]
                        # attach change% numeric
                        def as_pct(x):
                            try: return float((x.get("change_percent") or x.get("change%") or "").strip())
                            except: return None
                        peers_data = []
                        for pr in peers:
                            psym = (pr.get("symbol") or "").strip()
                            if not psym: continue
                            pc = as_pct(pr)
                            peers_data.append((psym, (pr.get("description") or psym or "").strip(), pc))
                        # sort
                        gainers = sorted([p for p in peers_data if p[2] is not None], key=lambda p: p[2], reverse=True)[:50]
                        losers  = sorted([p for p in peers_data if p[2] is not None], key=lambda p: p[2])[:50]

                        def table_html(rows_list, title, cls):
                            trs = []
                            for psym, pname, pchg in rows_list:
                                link = f"{BASE_URL}/{gslug}/{cslug}/{e_slug}/{slug(psym)}/prediction-tomorrow/"
                                pct = f"{pchg:.2f}%"
                                pct_cls = "chg-pos" if pchg > 0 else ("chg-neg" if pchg < 0 else "muted")
                                trs.append(
                                    "<tr>"
                                    f"<td><a href='{link}'>{html.escape(psym)}</a></td>"
                                    f"<td class='ellipsis'><a href='{link}'>{html.escape(pname)}</a></td>"
                                    f"<td class='{pct_cls}' style='text-align:right'>{pct}</td>"
                                    "</tr>"
                                )
                            body = "".join(trs) or "<tr><td colspan='3' class='muted'>No peers</td></tr>"
                            return f"""
<div class="mini-card">
  <div class="mini-head">{html.escape(title)}</div>
  <div class="mini-table-wrap">
    <table class="mini-table {cls}">
      <thead><tr><th>Stock</th><th>Name</th><th style='text-align:right'>Close %</th></tr></thead>
      <tbody>{body}</tbody>
    </table>
  </div>
</div>"""

                        pred = next_business_day(datetime.utcnow().date())
                        title = f"AI Analysis of {sym} Tomorrow | {name} Stock Prediction"
                        h1    = f"{sym} — {name}"
                        mdesc = f"AI prediction and analysis for {sym} ({name}). Includes recent price chart and top peers by daily % change in the {sec} sector."

                        close_line = f"<div class='now-line'>Close: <strong>{cclose:.2f}</strong></div>"
                        sig, conf, reason = classify(o,h,l,cclose)
                        sig_cls = "bull" if sig=="Bullish" else ("bear" if sig=="Bearish" else "side")

                        page_body = f"""
<article class="card pred-card">
  <div class="pred-head">
    <div class="pred-title">
      <div class="pred-name">{html.escape(h1)}</div>
      {close_line}
      <div class="pred-sig {sig_cls}">{html.escape(sig)}</div>
      <div class="muted small">{html.escape(reason)} · confidence {int(conf*100)}%</div>
    </div>
  </div>

  <div class="chart-card">
    <div class="mini-head">Historical price (last {len(hist)} days) + next day prediction</div>
    {chart_html}
  </div>

  <div class="grid-2">
    {table_html(gainers, f"Top Rising Stocks — {sec}", "rise")}
    {table_html(losers,  f"Top Losing Stocks — {sec}", "fall")}
  </div>
</article>"""
                        write_text(DIST / gslug / cslug / e_slug / s_slug / "prediction-tomorrow" / "index.html",
                                   tpl_base(title, mdesc, page_body, f"{BASE_URL}/{gslug}/{cslug}/{e_slug}/{s_slug}/prediction-tomorrow/"))

                # exchange page
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
                                    f"<div class='table-wrap'>{table_html}</div>",
                                    f"{BASE_URL}/{gslug}/{cslug}/{e_slug}/"))

                write_json(DIST / "static" / "exchanges" / gslug / cslug / f"{e_slug}.json",
                           {"region": gname, "country": cname, "exchange": exch, "rows": json_rows})

            # country landing
            write_text(DIST / gslug / cslug / "index.html",
                       tpl_base(f"{cname} — {CFG.get('site_title','')}",
                                f"Browse exchanges in {cname}.",
                                "<section class='card'><h2 class='h2'>Exchanges</h2><ul>"
                                + "".join([f"<li><a href='{BASE_URL}/{gslug}/{cslug}/{e['slug']}/'>{html.escape(e['name'])}</a></li>"
                                           for e in c['exchanges']]) +
                                "</ul></section>",
                                f"{BASE_URL}/{gslug}/{cslug}/"))

    # index.json for drilldown
    write_json(DIST / "static" / "index.json", site_index)

    # robots + sitemap
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
