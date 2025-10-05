#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SGG-1 build.py — classic build (fast) + Change% column
- Reads Data/LastTradingDay/<Group>/<country>.csv
- Keeps your original UI (styles.css + app.js) and JSON shape
- Copies logos/ once; uses ONE shared LogoResolver (no per-row rescans)
- Generates per-stock SEO pages for all symbols
- Adds Change% (green/red) after Close
"""

import csv, html, json, os, re, unicodedata, shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List

# ---------- paths / config ----------
ROOT = Path(__file__).resolve().parents[1]
DATA_LAST = ROOT / "Data" / "LastTradingDay"
DIST = ROOT / "dist"

CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
BASE_URL = CFG.get("base_url", "").rstrip("/")

IMG_EXTS = {".png", ".jpg", ".jpeg", ".svg", ".webp"}

# ---------- tiny utils ----------
def ensure_dir(p: Path): p.mkdir(parents=True, exist_ok=True)
def write_text(p: Path, s: str): p.parent.mkdir(parents=True, exist_ok=True); p.write_text(s, encoding="utf-8")
def write_json(p: Path, obj): p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")

def slug(s: str) -> str:
    s = (s or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "item"

def next_business_day(d: datetime.date):
    wd = d.weekday()
    if wd == 4: return d.replace(day=d.day) + timedelta(days=3)
    if wd == 5: return d.replace(day=d.day) + timedelta(days=2)
    return d + timedelta(days=1)

def classify(o,h,l,c):
    rng = max(h,l) - min(h,l)
    body = abs(c-o)
    if rng <= 0: return "Sideways", 0.5, "No range"
    ratio = body/rng if rng else 0.0
    if ratio < 0.2: return "Sideways", 0.5, "Small body vs range — indecision"
    if c > o: return "Bullish", min(0.9, 0.6 + ratio/2), "Close above open"
    if c < o: return "Bearish", min(0.9, 0.6 + ratio/2), "Close below open"
    return "Sideways", 0.5, "Flat"

# ---------- data IO ----------
def read_csv_safe(p: Path) -> List[Dict[str,str]]:
    rows: List[Dict[str,str]] = []
    with open(p, "r", encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            rows.append({(k or "").strip().lower(): (v or "").strip() for k, v in r.items()})
    # keys we rely on
    need = ["symbol","description","exchange","sector","industry","open","high","low","close","change_percent"]
    for r in rows:
        for k in need: r.setdefault(k, "")
    return rows

def load_tree():
    tree: Dict[str, Dict[str, Dict]] = {}
    if not DATA_LAST.exists(): return tree
    for gdir in sorted([d for d in DATA_LAST.iterdir() if d.is_dir()]):
        gname = gdir.name
        gslug = slug(gname)
        tree.setdefault(gslug, {})
        for csvp in sorted(gdir.glob("*.csv")):
            cslug = csvp.stem
            cname = cslug.replace("-", " ").title()
            rows = read_csv_safe(csvp)
            tree[gslug][cslug] = dict(group_name=gname, group_slug=gslug,
                                      country_name=cname, country_slug=cslug,
                                      rows=rows)
    return tree

# ---------- assets (css/js/logos) ----------
def copy_static_assets():
    ensure_dir(DIST / "static")
    for name in ("styles.css","app.js"):
        src = ROOT / "static" / name
        if src.exists(): shutil.copy2(src, DIST / "static" / name)

def copy_logos_once():
    src = ROOT / "logos"
    dst = DIST / "logos"
    if dst.exists(): shutil.rmtree(dst)
    if src.exists(): shutil.copytree(src, dst)

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii","ignore").decode("ascii")
    return re.sub(r"[^A-Z0-9]", "", s.upper())

def name_tokens(name: str):
    toks = re.split(r"[^A-Za-z0-9]+", name or "")
    STOP = {"LTD","LIMITED","CO","COMPANY","PLC","INC","LLC","SA","SAA","SAS","BSC","ORD",
            "PREF","THE","OF","AND","HOLDINGS","HOLDING","GROUP","CORP","CORPORATION",
            "BANK","INDUSTRIES","INDUSTRY"}
    return [t for t in toks if t and t.upper() not in STOP][:3]

def load_logos_index() -> Dict[str, Dict[str,str]]:
    for p in [ROOT / "logos_index.json", ROOT / "logos" / "logos_index.json"]:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8")) or {}
            except Exception:
                pass
    return {}

class LogoResolver:
    """Shared (singleton-style) resolver — no rescans per row."""
    def __init__(self):
        self.curated = load_logos_index()          # {EXCH: {SYM: rel}}
        self.cache   = {}
        # simple scan map: {EXCH: [(stem_norm, rel)], ...}
        base = ROOT / "logos"
        self.scan = {}
        if base.exists():
            for root, _, files in os.walk(base):
                for f in files:
                    if Path(f).suffix.lower() not in IMG_EXTS: continue
                    rel = (Path(root)/f).relative_to(base).as_posix()
                    exch = Path(root).name.upper()
                    stem = _norm(Path(f).stem)
                    self.scan.setdefault(exch, []).append((stem, rel))

    def url_for(self, exchange: str, symbol: str, name: str = "") -> str:
        key = (exchange or "", symbol or "")
        if key in self.cache: return self.cache[key]
        placeholder = f"{BASE_URL}/static/logo-placeholder.svg"
        exch = (exchange or "").upper()
        symn = _norm(symbol)

        # curated exact
        rel = (self.curated.get(exch) or {}).get(symbol) or (self.curated.get(exch) or {}).get(symn)
        if rel:
            url = f"{BASE_URL}/logos/{str(rel).lstrip('/\\')}"
            self.cache[key] = url; return url

        for stem, rel in self.scan.get(exch, []):
            if stem == symn:
                url = f"{BASE_URL}/logos/{rel}"
                self.cache[key] = url; return url
        for stem, rel in self.scan.get(exch, []):
            if symn and (symn in stem or stem in symn):
                url = f"{BASE_URL}/logos/{rel}"
                self.cache[key] = url; return url

        toks = [_norm(t) for t in name_tokens(name)]
        best = (0, None)
        for stem, rel in self.scan.get(exch, []):
            score = sum(1 for t in toks if t and t in stem)
            if score > best[0]: best = (score, rel)
        if best[1]:
            url = f"{BASE_URL}/logos/{best[1]}"
            self.cache[key] = url; return url

        self.cache[key] = placeholder
        return placeholder

def ensure_placeholder_logo():
    svg = """<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64' viewBox='0 0 64 64'>
<rect width='64' height='64' rx='12' fill='#0e1729' stroke='#223157'/>
<path d='M20 36h24M20 28h24' stroke='#4f8cff' stroke-width='3' stroke-linecap='round'/>
</svg>"""
    p = DIST / "static" / "logo-placeholder.svg"
    if not p.exists(): write_text(p, svg)

# ---------- templates ----------
def tpl_base(title, description, body, canonical):
    meta_kw = ", ".join(CFG.get("keywords", []))
    author  = CFG.get("author", {})
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
  <div class="kv"><div><strong>Last build:</strong> {build_time}</div></div>
</header>
<main class="grid">{body}</main>
<footer class="footer">
  <div>Contact: <a href="mailto:{html.escape(author.get('contact_email',''))}">{html.escape(author.get('contact_email',''))}</a></div>
</footer>
</div>
<script>window.SPP_BASE="{BASE_URL}";window.SPP_INDEX_URL="{BASE_URL}/static/index.json";</script>
<script src="{js}" defer></script>
</body></html>"""

# ---------- build ----------
def main():
    # clean & assets
    if DIST.exists(): shutil.rmtree(DIST)
    ensure_dir(DIST / "static")
    copy_static_assets()
    copy_logos_once()
    ensure_placeholder_logo()

    tree = load_tree()

    # home shell
    home = """
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
        "Region → Country → Exchange drilldown.", home, f"{BASE_URL}/"
    ))

    site_index = {"regions": []}
    resolver = LogoResolver()  # SINGLE shared instance

    for gslug in sorted(tree.keys()):
        any_country = next(iter(tree[gslug].values()))
        gname = any_country["group_name"]
        region_entry = {"name": gname, "slug": gslug, "url": f"{BASE_URL}/{gslug}/", "countries": []}
        site_index["regions"].append(region_entry)

        # region page
        clinks = []
        for cslug in sorted(tree[gslug].keys()):
            cname = tree[gslug][cslug]["country_name"]
            region_entry["countries"].append({"name": cname, "slug": cslug, "url": f"{BASE_URL}/{gslug}/{cslug}/", "exchanges": []})
            clinks.append(f"<li><a href='{BASE_URL}/{gslug}/{cslug}/'>{html.escape(cname)}</a></li>")
        write_text(DIST / gslug / "index.html",
                   tpl_base(f"{gname} Markets", f"Markets in {gname}.",
                           f"<section class='card'><h2 class='h2'>Countries</h2><ul>{''.join(clinks)}</ul></section>",
                           f"{BASE_URL}/{gslug}/"))

        # countries
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

                table_rows, json_rows = [], []
                for r in erows:
                    sym  = (r.get("symbol") or "").strip()
                    name = (r.get("description") or sym or "").strip()
                    sec  = (r.get("sector") or "").strip()

                    # change%
                    chg_raw = (r.get("change_percent") or r.get("change%") or "").strip()
                    try:
                        chg = float(chg_raw.replace("%",""))
                    except Exception:
                        chg = None
                    if chg is None:
                        chg_html = "<span class='badge sideways'>—</span>"
                    elif chg > 0:
                        chg_html = f"<span class='badge bullish'>+{chg:.2f}%</span>"
                    elif chg < 0:
                        chg_html = f"<span class='badge bearish'>{chg:.2f}%</span>"
                    else:
                        chg_html = "<span class='badge sideways'>0.00%</span>"

                    try:
                        o = float(r.get("open") or ""); h = float(r.get("high") or "")
                        l = float(r.get("low")  or ""); cclose = float(r.get("close") or "")
                        have_ohlc = True
                    except Exception:
                        o=h=l=cclose=None; have_ohlc=False

                    s_slug = slug(sym)
                    sig, conf, reason = ("",0,"")
                    if have_ohlc: sig, conf, reason = classify(o,h,l,cclose)

                    # per-stock SEO page (always on, like classic build)
                    if have_ohlc and sym:
                        pred = next_business_day(datetime.utcnow().date())
                        title = f"{sym} tomorrow — AI analysis"
                        h1    = f"{sym} — {name}"
                        mdesc = f"AI prediction for {sym} on {pred.isoformat()} ({exch}, {cname})."
                        body  = f"""
<article class="card">
  <h2 class="h2">{html.escape(h1)}</h2>
  <p class="small">{html.escape(gname)} · {html.escape(cname)} · {html.escape(exch)}</p>
  <p class="small">OHLC: O {o}, H {h}, L {l}, C {cclose}</p>
  <div class="card"><strong>{html.escape(sig)}</strong> — confidence {int(conf*100)}%</div>
</article>"""
                        stock_url = f"{BASE_URL}/{gslug}/{cslug}/{e_slug}/{s_slug}/prediction-tomorrow/"
                        write_text(DIST / gslug / cslug / e_slug / s_slug / "prediction-tomorrow" / "index.html",
                                   tpl_base(title, mdesc, body, stock_url))

                    logo_url = resolver.url_for(exch, sym, name)  # shared

                    table_rows.append(
                        "<tr>"
                        f"<td><a href='{BASE_URL}/{gslug}/{cslug}/{e_slug}/{s_slug}/prediction-tomorrow/'>{html.escape(sym)}</a></td>"
                        f"<td><a href='{BASE_URL}/{gslug}/{cslug}/{e_slug}/{s_slug}/prediction-tomorrow/'>{html.escape(name)}</a></td>"
                        f"<td>{html.escape(sec)}</td>"
                        f"<td>{'' if o is None else f'{o:.2f}'}</td>"
                        f"<td>{'' if h is None else f'{h:.2f}'}</td>"
                        f"<td>{'' if l is None else f'{l:.2f}'}</td>"
                        f"<td>{'' if cclose is None else f'{cclose:.2f}'}</td>"
                        f"<td>{chg_html}</td>"
                        f"<td><span class='badge {sig.lower()}'>{html.escape(sig or '')}</span></td>"
                        "</tr>"
                    )

                    json_rows.append({
                        "symbol": sym, "name": name, "sector": sec,
                        "open": None if o is None else round(o,2),
                        "high": None if h is None else round(h,2),
                        "low":  None if l is None else round(l,2),
                        "close":None if cclose is None else round(cclose,2),
                        "change_percent": None if chg is None else round(chg,4),
                        "signal": sig, "logo": logo_url,
                        "url": f"{BASE_URL}/{gslug}/{cslug}/{e_slug}/{s_slug}/prediction-tomorrow/"
                    })

                table_html = (
                    "<table class='table'>"
                    "<thead><tr>"
                    "<th>Symbol</th><th>Name</th><th>Sector</th>"
                    "<th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Change%</th><th>Signal</th>"
                    "</tr></thead><tbody>" + "\n".join(table_rows) + "</tbody></table>"
                )

                write_text(DIST / gslug / cslug / e_slug / "index.html",
                           tpl_base(f"{cname} {exch}", f"{exch} listings in {cname}.",
                                   table_html, f"{BASE_URL}/{gslug}/{cslug}/{e_slug}/"))

                write_json(DIST / "static" / "exchanges" / gslug / cslug / f"{e_slug}.json",
                           {"region": gname, "country": cname, "exchange": exch, "rows": json_rows})

            # country landing
            write_text(DIST / gslug / cslug / "index.html",
                       tpl_base(f"{cname}", f"Exchanges in {cname}.",
                                "<section class='card'><h2 class='h2'>Exchanges</h2><ul>"
                                + "".join([f"<li><a href='{BASE_URL}/{gslug}/{cslug}/{e['slug']}/'>{html.escape(e['name'])}</a></li>"
                                           for e in c['exchanges']]) + "</ul></section>",
                                f"{BASE_URL}/{gslug}/{cslug}/"))

    # drilldown index.json
    write_json(DIST / "static" / "index.json", site_index)

    # robots + xml sitemap
    write_text(DIST / "robots.txt", f"Sitemap: {BASE_URL}/sitemap.xml\nUser-agent: *\nAllow: /\n")
    urls = []
    for p in DIST.rglob("index.html"):
        rel = "/" + str(p.relative_to(DIST)).replace("\\", "/")
        urls.append(f"{BASE_URL}{rel[:-10]}")
    write_text(
        DIST / "sitemap.xml",
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
        + "".join(f"<url><loc>{u}</loc></url>" for u in sorted(set(urls)))
        + "</urlset>"
    )
    print("Build complete →", DIST)

if __name__ == "__main__":
    main()
