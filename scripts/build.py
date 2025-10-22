#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SGG-1 build.py — fast build from Data/LastTradingDay

What it does
------------
• Reads Data/LastTradingDay/<Group>/<country>.csv
• Adds Change% after Close and produces a simple SSG site (home → region → country → exchange → stock page)
• Signal column is a clickable “AI Prediction” link
• Copies static/styles.css and static/app.js
• Logos: rsync-style sync logos/ → dist/logos/ (so no stale logos)
• Market-aware prediction date using markets_config.csv (timezone + close time)
• Writes static/exchanges/<region>/<country>/<exchange>.json for the homepage table
• Generates robots.txt + sitemap.xml

Inputs
------
• config.json  (expects base_url, author, keywords, etc.)
• markets_config.csv  (columns: region,country,exchange,timezone,close_local)
• logos/ (country/<EXCHANGE>/*.png etc)
• (optional) logos_index.json ({ "NSE": {"TCS": "india/NSE/tcs--600.png", ...}, ... })
"""

import csv, html, json, os, re, unicodedata, shutil
from pathlib import Path
from datetime import datetime, timedelta, time
from typing import Dict, List, Tuple, Optional

try:
    import zoneinfo  # Python 3.9+
except Exception:
    zoneinfo = None

ROOT = Path(__file__).resolve().parents[1]
DATA_LAST = ROOT / "Data" / "LastTradingDay"
DIST = ROOT / "dist"

CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
BASE_URL = CFG.get("base_url", "").rstrip("/")

IMG_EXTS = {".png", ".jpg", ".jpeg", ".svg", ".webp"}
SKIP_LOGOS = os.environ.get("SKIP_LOGOS", "0") == "1"

# ----------------- utils -----------------
def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")

def write_json(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")

def slug(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "item"

def _f(x: Optional[str]) -> Optional[float]:
    try:
        return float(str(x).replace(",", ""))
    except Exception:
        return None

def next_business_day(d: datetime.date) -> datetime.date:
    wd = d.weekday()
    if wd == 4:  # Fri -> Mon
        return d + timedelta(days=3)
    if wd == 5:  # Sat -> Mon
        return d + timedelta(days=2)
    return d + timedelta(days=1)

# ------------- market config (TZ + close) -------------
class MarketTimes:
    def __init__(self):
        self._by_key: Dict[Tuple[str, str, str], Dict[str, str]] = {}
        self._load()

    def _load(self):
        p = ROOT / "markets_config.csv"
        if not p.exists():
            return
        with open(p, "r", encoding="utf-8", newline="") as f:
            rdr = csv.DictReader(f)
            for r in rdr:
                row = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
                region = row.get("region", "")
                country = row.get("country", "")
                exch = row.get("exchange", "")
                tz = row.get("timezone", "")
                close = row.get("close_local", "")
                if not (region and country and exch and tz and close):
                    continue
                self._by_key[(region.lower(), country.lower(), exch.lower())] = {"tz": tz, "close": close}

    def prediction_date(self, *, region: str, country: str, exchange: str) -> str:
        """
        If we know local close time:
          • before close_local (today local): predict for today
          • at/after close_local: predict for next business day (local)
        Else: default to UTC next business day.
        Return ISO date (YYYY-MM-DD).
        """
        key = (region.lower(), country.lower(), exchange.lower())
        item = self._by_key.get(key)
        if not item or not zoneinfo:
            return next_business_day(datetime.utcnow().date()).isoformat()

        tzname = item["tz"]
        hhmm = item["close"]
        try:
            hh, mm = [int(x) for x in hhmm.split(":", 1)]
            close_t = time(hour=hh, minute=mm)
        except Exception:
            return next_business_day(datetime.utcnow().date()).isoformat()

        try:
            tz = zoneinfo.ZoneInfo(tzname)
        except Exception:
            return next_business_day(datetime.utcnow().date()).isoformat()

        now_local = datetime.now(tz)
        close_local = datetime.combine(now_local.date(), close_t, tzinfo=tz)
        target = now_local.date() if now_local < close_local else next_business_day(now_local.date())
        return target.isoformat()

# ----------------- data -----------------
def read_csv_rows(p: Path) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    with open(p, "r", encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            out.append({(k or "").strip().lower(): (v or "").strip() for k, v in r.items()})
    # soften columns
    need = [
        "symbol", "description", "exchange", "sector", "industry",
        "open", "high", "low", "close", "change_percent", "change%", "currency"
    ]
    for r in out:
        for k in need:
            r.setdefault(k, "")
    return out

def load_last_trading_day():
    tree: Dict[str, Dict[str, Dict[str, object]]] = {}
    if not DATA_LAST.exists():
        return tree
    for gdir in sorted(d for d in DATA_LAST.iterdir() if d.is_dir()):
        gname = gdir.name
        gslug = slug(gname)
        tree.setdefault(gslug, {})
        for csvp in sorted(gdir.glob("*.csv")):
            cslug = csvp.stem
            cname = cslug.replace("-", " ").title()
            rows = read_csv_rows(csvp)
            tree[gslug][cslug] = {
                "group_name": gname,
                "group_slug": gslug,
                "country_name": cname,
                "country_slug": cslug,
                "rows": rows,
            }
    return tree

# ----------------- assets -----------------
def copy_static_assets():
    ensure_dir(DIST / "static")
    for name in ("styles.css", "app.js"):
        s = ROOT / "static" / name
        if s.exists():
            shutil.copy2(s, DIST / "static" / name)

def ensure_placeholder_logo():
    svg = """<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64' viewBox='0 0 64 64'>
<rect width='64' height='64' rx='12' fill='#0e1729' stroke='#223157'/>
<path d='M20 36h24M20 28h24' stroke='#4f8cff' stroke-width='3' stroke-linecap='round'/>
</svg>"""
    p = DIST / "static" / "logo-placeholder.svg"
    if not p.exists():
        ensure_dir(p.parent)
        p.write_text(svg, encoding="utf-8")

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Z0-9]", "", s.upper())

def load_logos_index() -> Dict[Tuple[str, str], str]:
    # Optional curated mapping: { "NSE": { "TCS": "india/NSE/tcs--600.png", ... }, ... }
    for p in [ROOT / "logos_index.json", ROOT / "logos" / "logos_index.json"]:
        if p.exists():
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
                out: Dict[Tuple[str, str], str] = {}
                for exch, mp in (raw or {}).items():
                    for sym, rel in (mp or {}).items():
                        out[(exch.upper(), _norm(sym))] = str(rel).lstrip("/\\")
                return out
            except Exception:
                pass
    return {}

def build_scan_index() -> Dict[str, List[Tuple[str, str]]]:
    # Gather ticker-named files by exchange (case preserved in folder names)
    base = ROOT / "logos"
    idx: Dict[str, List[Tuple[str, str]]] = {}
    if not base.exists():
        return idx
    for root, _, files in os.walk(base):
        for f in files:
            if os.path.splitext(f)[1].lower() not in IMG_EXTS:
                continue
            full = Path(root) / f
            rel = full.relative_to(base).as_posix()
            exch = full.parent.name  # e.g., NSE/BSE/ASX/…
            stem = os.path.splitext(f)[0]
            # trim trailing id/hash parts like --600
            stem = re.sub(r"(--|_|-)?\d{2,4}$", "", stem)
            idx.setdefault(exch.upper(), []).append((_norm(stem), rel))
    return idx

def _same_file(src: Path, dst: Path) -> bool:
    try:
        s = src.stat()
        d = dst.stat()
        return (s.st_size == d.st_size) and (int(s.st_mtime) == int(d.st_mtime))
    except FileNotFoundError:
        return False

def sync_tree(src: Path, dst: Path) -> None:
    """Rsync-like sync: copy new/changed files, remove stale files."""
    ensure_dir(dst)
    # copy/update
    for root, _, files in os.walk(src):
        rel_root = Path(root).relative_to(src)
        out_root = dst / rel_root
        ensure_dir(out_root)
        for f in files:
            s = Path(root) / f
            d = out_root / f
            if not _same_file(s, d):
                ensure_dir(d.parent)
                shutil.copy2(s, d)
    # delete stale
    for root, dirs, files in os.walk(dst):
        rel_root = Path(root).relative_to(dst)
        in_src = src / rel_root
        for f in files:
            if not (in_src / f).exists():
                try:
                    (Path(root) / f).unlink()
                except Exception:
                    pass
        for dname in list(dirs):
            dst_d = Path(root) / dname
            src_d = in_src / dname
            if not src_d.exists():
                try:
                    shutil.rmtree(dst_d)
                except Exception:
                    pass

class LogoResolver:
    def __init__(self):
        self.placeholder = f"{BASE_URL}/static/logo-placeholder.svg"
        if SKIP_LOGOS:
            self.curated = {}
            self.scan = {}
        else:
            # Always sync logos → dist/logos so we never serve stale images.
            src = ROOT / "logos"
            dst = DIST / "logos"
            if src.exists():
                sync_tree(src, dst)
            self.curated = load_logos_index()
            self.scan = build_scan_index()
        self.cache: Dict[Tuple[str, str], str] = {}

    def url_for(self, exchange: str, symbol: str, name: str = "") -> str:
        key = (exchange or "", symbol or "")
        if key in self.cache:
            return self.cache[key]
        if SKIP_LOGOS:
            self.cache[key] = self.placeholder
            return self.placeholder
        exch = (exchange or "").upper()
        symn = _norm(symbol)
        # curated wins
        rel = self.curated.get((exch, symn))
        if rel:
            url = f"{BASE_URL}/logos/{rel}"
            self.cache[key] = url
            return url
        # exact file stem
        for stem, rel in self.scan.get(exch, []):
            if stem == symn:
                url = f"{BASE_URL}/logos/{rel}"
                self.cache[key] = url
                return url
        # contains match (fallback)
        for stem, rel in self.scan.get(exch, []):
            if symn and (symn in stem or stem in symn):
                url = f"{BASE_URL}/logos/{rel}"
                self.cache[key] = url
                return url
        self.cache[key] = self.placeholder
        return self.placeholder

# ----------------- template -----------------
def tpl_base(title: str, description: str, body: str, canonical: str) -> str:
    meta_kw = ", ".join(CFG.get("keywords", []))
    author = CFG.get("author", {})
    site_tagline = CFG.get("site_tagline", "")
    build_time = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    css = f"{BASE_URL}/static/styles.css"
    js = f"{BASE_URL}/static/app.js"
    extra_css = """
    <style>
      .btn{display:inline-block;padding:.35rem .7rem;border:1px solid #27406b;border-radius:8px}
      .btn:hover{background:#122036}
      .pct{font-weight:700}.pct.pos{color:#3ddc97}.pct.neg{color:#ff6b6b}
    </style>"""
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
  <div class="kv"><div><strong>Last build:</strong> {build_time}</div></div>
</header>
<main class="grid">
{body}
</main>
<footer class="footer">
  <div>E-E-A-T: Author <strong>{html.escape(author.get('name',''))}</strong> · Org: {html.escape(author.get('org',''))} · Contact: <a href="mailto:{html.escape(author.get('contact_email',''))}">{html.escape(author.get('contact_email',''))}</a></div>
</footer>
</div>
<script>window.SPP_BASE="{BASE_URL}";window.SPP_INDEX_URL="{BASE_URL}/static/index.json";</script>
<script src="{js}" defer></script>
</body></html>"""

# ----------------- build -----------------
def main() -> None:
    ensure_dir(DIST / "static")
    copy_static_assets()
    ensure_placeholder_logo()

    tree = load_last_trading_day()
    resolver = LogoResolver()
    mkt = MarketTimes()

    # Home
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
</section>"""
    write_text(
        DIST / "index.html",
        tpl_base(
            f"{CFG.get('site_title','')} — {CFG.get('site_tagline','')}",
            "Browse by region → country → exchange.",
            home,
            f"{BASE_URL}/",
        ),
    )

    site_index = {"regions": []}

    for gslug in sorted(tree.keys()):
        gname = next(iter(tree[gslug].values()))["group_name"]
        site_index["regions"].append(
            {"name": gname, "slug": gslug, "url": f"{BASE_URL}/{gslug}/", "countries": []}
        )

        # Region page (country links)
        links = []
        for cslug in sorted(tree[gslug].keys()):
            cname = tree[gslug][cslug]["country_name"]
            links.append(f"<li><a href='{BASE_URL}/{gslug}/{cslug}/'>{html.escape(cname)}</a></li>")
            site_index["regions"][-1]["countries"].append(
                {"name": cname, "slug": cslug, "url": f"{BASE_URL}/{gslug}/{cslug}/", "exchanges": []}
            )
        write_text(
            DIST / gslug / "index.html",
            tpl_base(
                f"{gname} Markets",
                "Countries list",
                "<section class='card'><ul>" + "".join(links) + "</ul></section>",
                f"{BASE_URL}/{gslug}/",
            ),
        )

        # Country → exchanges
        for c in site_index["regions"][-1]["countries"]:
            cslug, cname = c["slug"], c["name"]
            rows = tree[gslug][cslug]["rows"]

            # group by exchange
            by: Dict[str, List[Dict[str, str]]] = {}
            for r in rows:
                by.setdefault((r.get("exchange") or "UNKNOWN").strip(), []).append(r)

            ex_links = []
            for exch, erows in sorted(by.items(), key=lambda kv: kv[0].lower()):
                e_slug = slug(exch)
                e_url = f"{BASE_URL}/{gslug}/{cslug}/{e_slug}/"
                c["exchanges"].append({"name": exch, "slug": e_slug, "url": e_url})
                ex_links.append(f"<li><a href='{e_url}'>{html.escape(exch)}</a></li>")

                table_rows = []
                json_rows = []
                exch_pred_date = mkt.prediction_date(region=gname, country=cname, exchange=exch)

                for r in erows:
                    sym = (r.get("symbol") or "").strip()
                    name = (r.get("description") or sym or "").strip()
                    sec = (r.get("sector") or "").strip()
                    o = _f(r.get("open"))
                    h = _f(r.get("high"))
                    l = _f(r.get("low"))
                    cl = _f(r.get("close"))
                    ch_raw = r.get("change_percent") or r.get("change%") or ""
                    try:
                        ch = float(ch_raw)
                    except Exception:
                        ch = None

                    s_slug = slug(sym)
                    stock_url = f"{BASE_URL}/{gslug}/{cslug}/{e_slug}/{s_slug}/prediction-tomorrow/"
                    ch_html = "" if ch is None else f"<span class='pct {'pos' if ch>0 else ('neg' if ch<0 else '')}'>{ch:.2f}%</span>"

                    table_rows.append(
                        "<tr>"
                        f"<td><a href='{stock_url}'>{html.escape(sym)}</a></td>"
                        f"<td><a href='{stock_url}'>{html.escape(name)}</a></td>"
                        f"<td>{html.escape(sec)}</td>"
                        f"<td>{'' if o is None else '{:.2f}'.format(o)}</td>"
                        f"<td>{'' if h is None else '{:.2f}'.format(h)}</td>"
                        f"<td>{'' if l is None else '{:.2f}'.format(l)}</td>"
                        f"<td>{'' if cl is None else '{:.2f}'.format(cl)}</td>"
                        f"<td>{ch_html}</td>"
                        f"<td><a class='btn' href='{stock_url}'>AI Prediction</a></td>"
                        "</tr>"
                    )

                    json_rows.append(
                        {
                            "symbol": sym,
                            "name": name,
                            "sector": sec,
                            "open": None if o is None else round(o, 2),
                            "high": None if h is None else round(h, 2),
                            "low": None if l is None else round(l, 2),
                            "close": None if cl is None else round(cl, 2),
                            "change_percent": None if ch is None else round(ch, 4),
                            "logo": resolver.url_for(exch, sym, name),
                            "url": stock_url,
                        }
                    )

                    # Very light stock page
                    if sym and None not in (o, h, l, cl):
                        title = f"AI Analysis of {sym} Tomorrow | {name} Stock Prediction"
                        head = (
                            "<div class='card'>"
                            f"<h2 class='h2'>AI Analysis of {html.escape(sym)} ({html.escape(name)})</h2>"
                            f"<p class='small'>Region: {html.escape(gname)} · Country: {html.escape(cname)} · Exchange: {html.escape(exch)}</p>"
                            f"<p class='small'>OHLC: O {'{:.2f}'.format(o)}, H {'{:.2f}'.format(h)}, L {'{:.2f}'.format(l)}, C {'{:.2f}'.format(cl)} · Change%: {ch_html}</p>"
                            f"<div class='card'><h3 class='h3'>Prediction for {exch_pred_date}</h3><p><strong>Model signal</strong> based on the latest day’s action.</p></div>"
                            "</div>"
                        )
                        write_text(
                            DIST / gslug / cslug / e_slug / s_slug / "prediction-tomorrow" / "index.html",
                            tpl_base(title, title, head, f"{BASE_URL}/{gslug}/{cslug}/{e_slug}/{s_slug}/prediction-tomorrow/"),
                        )

                table_html = (
                    "<table class='table'>"
                    "<thead><tr><th>Symbol</th><th>Name</th><th>Sector</th>"
                    "<th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Change%</th><th>Signal</th></tr></thead>"
                    f"<tbody>{''.join(table_rows)}</tbody></table>"
                )
                write_text(
                    DIST / gslug / cslug / e_slug / "index.html",
                    tpl_base(
                        f"{cname} {exch} — {CFG.get('site_title','')}",
                        f"Listings for {exch} in {cname}.",
                        table_html,
                        f"{BASE_URL}/{gslug}/{cslug}/{e_slug}/",
                    ),
                )
                write_json(
                    DIST / "static" / "exchanges" / gslug / cslug / f"{e_slug}.json",
                    {"region": gname, "country": cname, "exchange": exch, "rows": json_rows},
                )

            write_text(
                DIST / gslug / cslug / "index.html",
                tpl_base(
                    f"{cname} — {CFG.get('site_title','')}",
                    f"Exchanges in {cname}.",
                    "<section class='card'><ul>" + "".join(ex_links) + "</ul></section>",
                    f"{BASE_URL}/{gslug}/{cslug}/",
                ),
            )

    # index.json for app.js (home pickers)
    write_json(DIST / "static" / "index.json", site_index)

    # robots + sitemap
    write_text(DIST / "robots.txt", f"Sitemap: {BASE_URL}/sitemap.xml\nUser-agent: *\nAllow: /\n")
    urls = []
    for p in DIST.rglob("index.html"):
        rel = "/" + str(p.relative_to(DIST)).replace("\\", "/")
        urls.append(f"{BASE_URL}{rel[:-10]}")
    write_text(
        DIST / "sitemap.xml",
        "<?xml version='1.0' encoding='UTF-8'?><urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
        + "".join([f"<url><loc>{u}</loc></url>" for u in sorted(set(urls))])
        + "</urlset>",
    )
    print("Build complete →", DIST)
        
# --- Copy AI landing page (static/landing/index.html) to dist root (runs AFTER build) ---
def copy_landing_page():
    landing_src = ROOT / "static" / "landing" / "index.html"  # repo-root path
    if landing_src.exists():
        ensure_dir(DIST)
        shutil.copy2(landing_src, DIST / "index.html")
        print("✅ Landing page copied to dist/index.html")
    else:
        print("⚠️ Landing page not found at static/landing/index.html")

if __name__ == "__main__":
    main()
    # run AFTER the build so dist exists
    copy_landing_page()

