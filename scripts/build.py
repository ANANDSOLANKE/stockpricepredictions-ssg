#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SSG build — reads Data/LastTradingDay/<RegionName>/*.csv
Generates:
  /<region>/index.html
  /<region>/<country>/index.html  ← country page with exchange chips + dynamic table
  /<region>/<country>/<exchange>/index.html  ← still generated for compatibility
  /<region>/<country>/<exchange>/<symbol>/prediction-tomorrow/index.html
Also writes JSON per exchange used by the country page loader:
  /static/exchanges/<region>/<country>/<exchange>.json
Plus robots.txt and sitemap.xml.
"""

import csv, html, json, os, re, unicodedata, shutil
from pathlib import Path
from datetime import datetime, timedelta, time
from typing import Dict, List, Tuple, Optional

# ---------- paths / config ----------
ROOT = Path(__file__).resolve().parents[1]
DATA_LAST = ROOT / "Data" / "LastTradingDay"
DIST = ROOT / "dist"

CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
BASE_URL = CFG.get("base_url", "").rstrip("/")

IMG_EXTS = {".png", ".jpg", ".jpeg", ".svg", ".webp"}
SKIP_LOGOS = os.environ.get("SKIP_LOGOS", "0") == "1"

try:
    import zoneinfo  # Python 3.9+
except Exception:
    zoneinfo = None

# ---------- utils ----------
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

# ---------- market config (local close -> prediction date) ----------
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

# ---------- data ----------
def read_csv_rows(p: Path) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    with open(p, "r", encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            out.append({(k or "").strip().lower(): (v or "").strip() for k, v in r.items()})
    # standardize some cols
    need = ["symbol", "description", "exchange", "sector", "industry",
            "open", "high", "low", "close", "change_percent", "change%", "currency"]
    for r in out:
        for k in need:
            r.setdefault(k, "")
    return out

def load_last_trading_day():
    """
    returns tree[gslug][cslug_raw] = { group_name, group_slug, country_name, country_slug (raw), rows }
    gslug is slug(RegionFolderName); cslug_raw is CSV stem (kept as-is for data lookup)
    """
    tree: Dict[str, Dict[str, Dict[str, object]]] = {}
    if not DATA_LAST.exists():
        return tree
    for gdir in sorted(d for d in DATA_LAST.iterdir() if d.is_dir()):
        gname = gdir.name
        gslug = slug(gname)
        tree.setdefault(gslug, {})
        for csvp in sorted(gdir.glob("*.csv")):
            cslug_raw = csvp.stem  # keep raw (e.g., "south-africa" or "South Africa")
            cname = cslug_raw.replace("-", " ").title()
            rows = read_csv_rows(csvp)
            tree[gslug][cslug_raw] = {
                "group_name": gname,
                "group_slug": gslug,
                "country_name": cname,
                "country_slug": cslug_raw,
                "rows": rows,
            }
    return tree

# ---------- assets / logos ----------
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
            exch = full.parent.name  # NSE / BSE / etc.
            stem = os.path.splitext(f)[0]
            stem = re.sub(r"(--|_|-)?\d{2,4}$", "", stem)  # trim trailing size/hash
            idx.setdefault(exch.upper(), []).append((_norm(stem), rel))
    return idx

def _same_file(src: Path, dst: Path) -> bool:
    try:
        s = src.stat(); d = dst.stat()
        return (s.st_size == d.st_size) and (int(s.st_mtime) == int(d.st_mtime))
    except FileNotFoundError:
        return False

def sync_tree(src: Path, dst: Path) -> None:
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
                try: (Path(root) / f).unlink()
                except: pass
        for dname in list(dirs):
            dst_d = Path(root) / dname
            src_d = in_src / dname
            if not src_d.exists():
                try: shutil.rmtree(dst_d)
                except: pass

class LogoResolver:
    def __init__(self):
        self.placeholder = f"{BASE_URL}/static/logo-placeholder.svg"
        if SKIP_LOGOS:
            self.curated = {}; self.scan = {}
        else:
            src = ROOT / "logos"; dst = DIST / "logos"
            if src.exists(): sync_tree(src, dst)
            self.curated = load_logos_index(); self.scan = build_scan_index()
        self.cache: Dict[Tuple[str, str], str] = {}

    def url_for(self, exchange: str, symbol: str, name: str = "") -> str:
        key = (exchange or "", symbol or "")
        if key in self.cache: return self.cache[key]
        if SKIP_LOGOS:
            self.cache[key] = self.placeholder; return self.placeholder
        exch = (exchange or "").upper(); symn = _norm(symbol)
        # curated wins
        rel = self.curated.get((exch, symn))
        if rel:
            url = f"{BASE_URL}/logos/{rel}"; self.cache[key] = url; return url
        # exact stem
        for stem, rel in self.scan.get(exch, []):
            if stem == symn:
                url = f"{BASE_URL}/logos/{rel}"; self.cache[key] = url; return url
        # contains match
        for stem, rel in self.scan.get(exch, []):
            if symn and (symn in stem or stem in symn):
                url = f"{BASE_URL}/logos/{rel}"; self.cache[key] = url; return url
        self.cache[key] = self.placeholder; return self.placeholder

# ---------- template ----------
def tpl_base(title: str, description: str, body: str, canonical: str) -> str:
    meta_kw = ", ".join(CFG.get("keywords", []))
    author = CFG.get("author", {})
    css = f"{BASE_URL}/static/styles.css"
    js = f"{BASE_URL}/static/app.js"
    extra_css = """
    <style>
      .btn{display:inline-block;padding:.35rem .7rem;border:1px solid #27406b;border-radius:8px}
      .btn:hover{background:#122036}
      .pct{font-weight:700}.pct.pos{color:#3ddc97}.pct.neg{color:#ff6b6b}
      /* exchange bar */
      .exchange-bar{display:flex;flex-direction:column;gap:.5rem;margin-bottom:1rem;padding:.6rem 1rem;background:#111a25;border-radius:10px;box-shadow:0 0 6px #0006;border:1px solid #22395f}
      .exchange-bar .flagwrap{display:flex;align-items:center;gap:.6rem}
      .exchange-bar .flag{width:36px;height:24px;border-radius:4px;object-fit:cover}
      .exchange-bar .cname{font-weight:600;font-size:1.08em;color:#00b7ff}
      .exchange-bar .chipswrap{display:flex;flex-wrap:wrap;gap:.45rem;margin-left:2.6rem;margin-top:.2rem}
      .exchange-bar .exchip{padding:.28rem .7rem;border:1px solid #284472;border-radius:999px;background:#0d1117;text-decoration:none;color:#fff;font-size:.8em;transition:.2s}
      .exchange-bar .exchip:hover{background:#00b7ff33;border-color:#4f7bff}
      .exchange-bar .exchip.active{background:#284cff44;border-color:#4f7bff}
      /* table wrap */
      .table-wrap{overflow:auto}
    </style>"""
    build_time = datetime.utcnow().isoformat(timespec="seconds") + "Z"
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
  <div class="kv"><div><strong>Last build:</strong> {build_time}</div></div>
</header>
<main class="grid">
{body}
</main>
<footer class="footer">
  <div>E-E-A-T: Author <strong>{html.escape(author.get('name',''))}</strong> · Org: {html.escape(author.get('org',''))} · Contact: <a href="mailto:{html.escape(author.get('contact_email',''))}">{html.escape(author.get('contact_email',''))}</a></div>
</footer>
</div>
<script>window.SPP_BASE="{BASE_URL}";</script>
<script src="{js}" defer></script>
</body></html>"""

# ---------- build ----------
def main() -> None:
    ensure_dir(DIST / "static")
    copy_static_assets()
    ensure_placeholder_logo()

    tree = load_last_trading_day()
    resolver = LogoResolver()
    mkt = MarketTimes()

    # Region pages + country links
    for gslug in sorted(tree.keys()):
        gname = next(iter(tree[gslug].values()))["group_name"]

        # Region page (country links)
        links = []
        for cslug_raw in sorted(tree[gslug].keys()):
            cname = tree[gslug][cslug_raw]["country_name"]
            cslug_dir = slug(cslug_raw)
            links.append(f"<li><a href='{BASE_URL}/{gslug}/{cslug_dir}/'>{html.escape(cname)}</a></li>")

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
        for cslug_raw, country in tree[gslug].items():
            cname = country["country_name"]
            rows = country["rows"]
            cslug_dir = slug(cslug_raw)  # directory/URL-safe

            # group by exchange
            by: Dict[str, List[Dict[str, str]]] = {}
            for r in rows:
                by.setdefault((r.get("exchange") or "UNKNOWN").strip(), []).append(r)

            # helper: top flag + exchange chips
            def build_exchange_bar(region_slug, country_slug, country_name, exchanges, active_slug: Optional[str] = None):
                flag_path = f"{BASE_URL}/logos/countryflags/{country_slug}.svg"
                chips = []
                for ex_name in sorted(e for e in exchanges if e and e.upper() != "UNKNOWN"):
                    ex_slug = slug(ex_name)
                    # country page chips link '#' and JS handles switching
                    chips.append(f"<a href='#' data-ex='{ex_slug}' class='exchip'>{html.escape(ex_name)}</a>")
                return f"""
                <div class='exchange-bar'>
                  <div class='flagwrap'>
                    <img src='{flag_path}' alt='{html.escape(country_name)} flag' class='flag'>
                    <span class='cname'>{html.escape(country_name)}</span>
                  </div>
                  <div class='chipswrap'>{"".join(chips)}</div>
                </div>
                """

            all_exchanges = sorted(k for k in by.keys() if k and k.upper() != "UNKNOWN")

            # ---- build each exchange page (compatibility) + write JSON for dynamic loader
            ex_links = []
            for exch, erows in sorted(by.items(), key=lambda kv: kv[0].lower()):
                e_slug = slug(exch)
                e_url = f"{BASE_URL}/{gslug}/{cslug_dir}/{e_slug}/"
                ex_links.append(f"<li><a href='{e_url}'>{html.escape(exch)}</a></li>")

                table_rows = []
                json_rows = []
                exch_pred_date = mkt.prediction_date(region=gname, country=cname, exchange=exch)

                for r in erows:
                    sym = (r.get("symbol") or "").strip()
                    name = (r.get("description") or sym or "").strip()
                    sec = (r.get("sector") or "").strip()
                    o = _f(r.get("open")); h = _f(r.get("high"))
                    l = _f(r.get("low"));  cl = _f(r.get("close"))
                    ch_raw = r.get("change_percent") or r.get("change%") or ""
                    try:
                        ch = float(ch_raw)
                    except Exception:
                        ch = None

                    s_slug = slug(sym)
                    stock_url = f"{BASE_URL}/{gslug}/{cslug_dir}/{e_slug}/{s_slug}/prediction-tomorrow/"
                    ch_html = "" if ch is None else f"<span class='pct {'pos' if ch>0 else ('neg' if ch<0 else '')}'>{ch:.2f}%</span>"

                    table_rows.append(
                        "<tr>"
                        f"<td><a href='{stock_url}'>{html.escape(sym)}</a></td>"
                        f"<td>{html.escape(name)}</td>"
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

                    # simple stock page
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
                            DIST / gslug / cslug_dir / e_slug / s_slug / "prediction-tomorrow" / "index.html",
                            tpl_base(title, title, head, f"{BASE_URL}/{gslug}/{cslug_dir}/{e_slug}/{s_slug}/prediction-tomorrow/"),
                        )

                # exchange page (compatibility)
                table_html = (
                    "<div class='table-wrap'>"
                    "<table class='table'>"
                    "<thead><tr><th>Symbol</th><th>Name</th><th>Sector</th>"
                    "<th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Change%</th><th>Signal</th></tr></thead>"
                    f"<tbody>{''.join(table_rows)}</tbody></table></div>"
                )
                write_text(
                    DIST / gslug / cslug_dir / e_slug / "index.html",
                    tpl_base(
                        f"{cname} {exch} — {CFG.get('site_title','')}",
                        f"Listings for {exch} in {cname}.",
                        build_exchange_bar(gslug, cslug_dir, cname, all_exchanges, active_slug=e_slug) + table_html,
                        f"{BASE_URL}/{gslug}/{cslug_dir}/{e_slug}/",
                    ),
                )

                # JSON for dynamic loader on country page
                write_json(
                    DIST / "static" / "exchanges" / gslug / cslug_dir / f"{e_slug}.json",
                    {"region": gname, "country": cname, "exchange": exch, "rows": json_rows},
                )

            # country page (bar + dynamic table loader)
            default_ex_slug = slug(all_exchanges[0]) if all_exchanges else ""
            loader_js = f"""
<script>
(function(){{
  const base = "{BASE_URL}/static/exchanges/{gslug}/{cslug_dir}/";
  const chips = document.querySelectorAll('.exchange-bar .exchip');
  const tableHost = document.getElementById('ex-table');
  function renderRows(rows){{
    const cells = r => `
      <tr>
        <td><a href="${{r.url}}">${{r.symbol || ''}}</a></td>
        <td>${{r.name || ''}}</td>
        <td>${{r.sector || ''}}</td>
        <td>${{r.open ?? ''}}</td>
        <td>${{r.high ?? ''}}</td>
        <td>${{r.low ?? ''}}</td>
        <td>${{r.close ?? ''}}</td>
        <td>${{(r.change_percent==null)?'':(r.change_percent*1).toFixed(2)+'%'}}</td>
        <td><a class='btn' href="${{r.url}}">AI Prediction</a></td>
      </tr>`;
    tableHost.innerHTML =
      "<div class='table-wrap'><table class='table'><thead><tr><th>Symbol</th><th>Name</th><th>Sector</th><th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Change%</th><th>Signal</th></tr></thead><tbody>"
      + rows.map(cells).join("") + "</tbody></table></div>";
  }}
  async function loadExchange(slug){{
    chips.forEach(c=>c.classList.toggle('active', c.dataset.ex===slug));
    try {{
      const res = await fetch(base + slug + ".json");
      const data = await res.json();
      renderRows(data.rows||[]);
    }} catch(e) {{
      tableHost.innerHTML = "<p class='small'>Failed to load exchange data.</p>";
    }}
  }}
  chips.forEach(c=>c.addEventListener('click', (ev)=>{{ev.preventDefault(); loadExchange(c.dataset.ex);}}));
  if ("{default_ex_slug}") loadExchange("{default_ex_slug}");
}})();
</script>
"""
            country_body = (
                build_exchange_bar(gslug, cslug_dir, cname, all_exchanges)
                + "<div id='ex-table' class='card'><p class='small'>Loading…</p></div>"
                + loader_js
            )
            write_text(
                DIST / gslug / cslug_dir / "index.html",
                tpl_base(
                    f"{cname} — {CFG.get('site_title','')}",
                    f"Exchanges in {cname}.",
                    country_body,
                    f"{BASE_URL}/{gslug}/{cslug_dir}/",
                ),
            )

    # robots + sitemap (scan all index.html)
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

# ---------- landing page copy (runs after build) ----------
def copy_landing_page():
    landing_src = ROOT / "static" / "landing" / "index.html"  # repo-root path
    if landing_src.exists():
        ensure_dir(DIST)
        shutil.copy2(landing_src, DIST / "index.html")
        print("✅ Landing page copied to dist/index.html")
    else:
        print("⚠️ Landing page not found at static/landing/index.html")

# ---------- entry ----------
if __name__ == "__main__":
    main()
    copy_landing_page()
