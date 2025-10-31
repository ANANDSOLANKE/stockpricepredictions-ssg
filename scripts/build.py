#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Builds the site from Data/LastTradingDay.

Outputs
- /index.html (your Ravensight hero + injected All Markets grid + Global Search)
- /<region>/index.html
- /<region>/<country>/index.html
- /<region>/<country>/<exchange>/index.html
- /<region>/<country>/<exchange>/<symbol>/prediction-tomorrow/index.html
- /static/exchanges/<region>/<country>/<exchange>.json
- robots.txt, sitemap.xml
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
BASE_URL = (CFG.get("base_url", "") or "").rstrip("/")

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

# always ship flags even if SKIP_LOGOS is set
def ensure_countryflags():
    src = ROOT / "logos" / "countryflags"
    dst = DIST / "logos" / "countryflags"
    if src.exists():
        sync_tree(src, dst)

# ---------- market config ----------
class MarketTimes:
    def __init__(self):
        self._by_key: Dict[Tuple[str, str, str], Dict[str, str]] = {}
        self._load()

    def _load(self):
        p = ROOT / "markets_config.csv"
        if not p.exists(): return
        with open(p, "r", encoding="utf-8", newline="") as f:
            rdr = csv.DictReader(f)
            for r in rdr:
                row = {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
                region, country, exch = row.get("region",""), row.get("country",""), row.get("exchange","")
                tz, close = row.get("timezone",""), row.get("close_local","")
                if region and country and exch and tz and close:
                    self._by_key[(region.lower(), country.lower(), exch.lower())] = {"tz": tz, "close": close}

    def prediction_date(self, *, region: str, country: str, exchange: str) -> str:
        key = (region.lower(), country.lower(), exchange.lower())
        item = self._by_key.get(key)
        if not item or not zoneinfo:
            return next_business_day(datetime.utcnow().date()).isoformat()
        try:
            hh, mm = [int(x) for x in item["close"].split(":", 1)]
            close_t = time(hour=hh, minute=mm)
            tz = zoneinfo.ZoneInfo(item["tz"])
            now_local = datetime.now(tz)
            close_local = datetime.combine(now_local.date(), close_t, tzinfo=tz)
            target = now_local.date() if now_local < close_local else next_business_day(now_local.date())
            return target.isoformat()
        except Exception:
            return next_business_day(datetime.utcnow().date()).isoformat()

# ---------- data ----------
def read_csv_rows(p: Path) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    with open(p, "r", encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            out.append({(k or "").strip().lower(): (v or "").strip() for k, v in r.items()})
    # normalize
    need = ["symbol","description","exchange","sector","industry","open","high","low","close","change_percent","change%","currency"]
    for r in out:
        for k in need: r.setdefault(k, "")
    return out

def load_last_trading_day():
    """
    tree[gslug][cslug_raw] = { group_name, group_slug, country_name, country_slug(raw), rows }
    where gslug = slug(RegionFolderName); cslug_raw = CSV stem as-is
    """
    tree: Dict[str, Dict[str, Dict[str, object]]] = {}
    if not DATA_LAST.exists(): return tree
    for gdir in sorted(d for d in DATA_LAST.iterdir() if d.is_dir()):
        gname, gslug = gdir.name, slug(gdir.name)
        tree.setdefault(gslug, {})
        for csvp in sorted(gdir.glob("*.csv")):
            cslug_raw = csvp.stem
            cname = cslug_raw.replace("-", " ").title()
            rows = read_csv_rows(csvp)
            tree[gslug][cslug_raw] = {
                "group_name": gname, "group_slug": gslug,
                "country_name": cname, "country_slug": cslug_raw,
                "rows": rows,
            }
    return tree

# ---------- assets / logos ----------
def copy_static_assets():
    ensure_dir(DIST / "static")
    for name in ("styles.css", "app.js"):
        s = ROOT / "static" / name
        if s.exists(): shutil.copy2(s, DIST / "static" / name)

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
    if not base.exists(): return idx
    for root, _, files in os.walk(base):
        for f in files:
            if os.path.splitext(f)[1].lower() not in IMG_EXTS: continue
            full = Path(root) / f
            rel = full.relative_to(base).as_posix()
            exch = full.parent.name
            stem = os.path.splitext(f)[0]
            stem = re.sub(r"(--|_|-)?\d{2,4}$", "", stem)
            idx.setdefault(exch.upper(), []).append((_norm(stem), rel))
    return idx

def _same_file(src: Path, dst: Path) -> bool:
    try:
        s, d = src.stat(), dst.stat()
        return (s.st_size == d.st_size) and (int(s.st_mtime) == int(d.st_mtime))
    except Exception:
        return False

def sync_tree(src: Path, dst: Path) -> None:
    ensure_dir(dst)
    for root, _, files in os.walk(src):
        rel_root = Path(root).relative_to(src)
        out_root = dst / rel_root
        ensure_dir(out_root)
        for f in files:
            s, d = Path(root)/f, out_root/f
            if not _same_file(s, d):
                ensure_dir(d.parent); shutil.copy2(s, d)
    for root, dirs, files in os.walk(dst):
        rel_root = Path(root).relative_to(dst)
        in_src = src / rel_root
        for f in files:
            if not (in_src/f).exists():
                try: (Path(root)/f).unlink()
                except: pass
        for dname in list(dirs):
            dst_d, src_d = Path(root)/dname, in_src/dname
            if not src_d.exists():
                try: shutil.rmtree(dst_d)
                except: pass

# ---- curated logos via CSV (optional) ----
def find_logo_relpath_by_filename(filename: str) -> Optional[str]:
    if not filename:
        return None
    target = filename.strip().lower()
    base = ROOT / "logos"
    if not base.exists():
        return None
    for root, _, files in os.walk(base):
        for f in files:
            if f.lower() == target:
                return (Path(root) / f).relative_to(base).as_posix()
    return None

def load_logos_from_csv() -> Dict[Tuple[str, str], str]:
    p = ROOT / "logos" / "map" / "logos.csv"
    out: Dict[Tuple[str, str], str] = {}
    if not p.exists():
        return out
    with open(p, "r", encoding="utf-8", newline="") as f:
        sample = f.read(4096); f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        except Exception:
            dialect = csv.excel
        rdr = csv.DictReader(f, dialect=dialect)
        for r in rdr:
            exchange = (r.get("exchange") or r.get("Exchange") or "").strip()
            symbol   = (r.get("symbol") or r.get("Symbol") or "").strip()
            path     = (r.get("path") or r.get("Path") or "").strip()
            filename = (r.get("filename") or r.get("file") or r.get("logo") or r.get("Logo") or "").strip()
            if not exchange or not symbol:
                continue
            rel = path.lstrip("/\\") if path else find_logo_relpath_by_filename(filename)
            if rel:
                out[(exchange.upper(), _norm(symbol))] = rel
    return out

def merge_curated_maps(a: Dict[Tuple[str, str], str], b: Dict[Tuple[str, str], str]) -> Dict[Tuple[str, str], str]:
    merged = dict(a)
    for k, v in b.items():
        merged.setdefault(k, v)
    return merged

# ---------- logo resolver ----------
class LogoResolver:
    def __init__(self):
        self.placeholder = f"{BASE_URL}/static/logo-placeholder.svg"
        src, dst = ROOT / "logos", DIST / "logos"
        if src.exists():
            sync_tree(src, dst)
        curated_json = load_logos_index()
        curated_csv  = load_logos_from_csv()
        self.curated = merge_curated_maps(curated_json, curated_csv)
        self.scan = {} if SKIP_LOGOS else build_scan_index()
        self.cache: Dict[Tuple[str, str], str] = {}

    def url_for(self, exchange: str, symbol: str, name: str = "") -> str:
        key = (exchange or "", symbol or "")
        if key in self.cache:
            return self.cache[key]
        exch = (exchange or "").upper()
        symn = _norm(symbol)
        rel = self.curated.get((exch, symn))
        if rel:
            url = f"{BASE_URL}/logos/{rel}"
            self.cache[key] = url; return url
        if self.scan:
            for stem, rel in self.scan.get(exch, []):
                if stem == symn:
                    url = f"{BASE_URL}/logos/{rel}"
                    self.cache[key] = url; return url
        self.cache[key] = self.placeholder
        return self.placeholder

# ---------- dark template helpers (for internal pages) ----------
def tpl_base(title: str, description: str, body: str, canonical: str) -> str:
    meta_kw = ", ".join(CFG.get("keywords", []))
    author = CFG.get("author", {})
    css = f"{BASE_URL}/static/styles.css"
    js = f"{BASE_URL}/static/app.js"
    extra_css = """
    <style>
      body{background:#0e1729;color:#fff}
      .btn{display:inline-block;padding:.35rem .7rem;border:1px solid #27406b;border-radius:8px}
      .btn:hover{background:#122036}
      .pct{font-weight:700}.pct.pos{color:#3ddc97}.pct.neg{color:#ff6b6b}
      .logo{width:20px;height:20px;border-radius:4px;object-fit:cover;vertical-align:middle;margin-right:8px;box-shadow:0 0 0 1px #22395f}
      .exchange-bar{display:flex;flex-direction:column;gap:.5rem;margin-bottom:1rem;padding:.6rem 1rem;background:#111a25;border-radius:10px;box-shadow:0 0 6px #0006;border:1px solid #22395f}
      .exchange-bar .flagwrap{display:flex;align-items:center;gap:.6rem}
      .exchange-bar .flag{width:36px;height:24px;border-radius:4px;object-fit:cover}
      .exchange-bar .cname{font-weight:600;font-size:1.08em;color:#00b7ff}
      .exchange-bar .chipswrap{display:flex;flex-wrap:wrap;gap:.45rem;margin-left:2.6rem;margin-top:.2rem}
      .exchange-bar .exchip{padding:.28rem .7rem;border:1px solid #284472;border-radius:999px;background:#0d1117;text-decoration:none;color:#fff;font-size:.8em;transition:.2s}
      .exchange-bar .exchip:hover{background:#00b7ff33;border-color:#4f7bff}
      .exchange-bar .exchip.active{background:#284cff44;border-color:#4f7bff}
      .tools{display:flex;gap:.6rem;align-items:center;margin:.4rem 0 0 2.6rem;flex-wrap:wrap}
      .search-input{padding:.45rem .6rem;border:1px solid #2b4a70;background:#0d1117;color:#fff;border-radius:8px;min-width:260px}
      .loadmore-wrap{text-align:center;margin:.6rem 0}
      .table-wrap{overflow:auto}
      .region{margin:20px;padding:20px;background:#111a25;border-radius:10px;box-shadow:0 0 10px #0006}
      .region h2{color:#00b7ff;margin:0 0 10px}
      .countries{display:flex;flex-wrap:wrap;gap:16px}
      .country-card{background:#192b43;border:1px solid #2b4a70;border-radius:10px;width:190px;padding:10px;text-align:center;transition:.25s}
      .country-card:hover{background:#203553;transform:translateY(-3px)}
      .country-flag{width:40px;height:26px;border-radius:4px;object-fit:cover;display:block;margin:0 auto 6px}
      .country-name{font-weight:700;color:#00b7ff;margin-bottom:8px}
      .exchange-list a{display:inline-block;background:#0d1117;color:#fff;padding:3px 6px;margin:2px;border-radius:8px;border:1px solid #284472;font-size:.8em;text-decoration:none}
      .exchange-list a:hover{background:#00b7ff33;border-color:#4f7bff}
      header.hero{padding:20px}
      .h1{font-size:1.6rem;color:#00b7ff;margin:6px 0 0}
      .container{max-width:1100px;margin:0 auto}
      .th-sort{cursor:pointer; user-select:none}
      .th-sort .arrow{opacity:.55; font-size:.9em; margin-left:.25rem}
      .th-sort.active{color:#9fd0ff}
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
  <div class="breadcrumbs"><a style="color:#7fb1ff;text-decoration:none" href="{BASE_URL}/">Home</a></div>
  <h1 class="h1">{html.escape(title)}</h1>
  <div class="kv"><div><strong>Last build:</strong> {build_time}</div></div>
</header>
<main class="grid">
{body}
</main>
<footer class="footer" style="padding:20px 0 40px;color:#9fb3ce">
  <div>E-E-A-T: Author <strong>{html.escape(author.get('name',''))}</strong> · Org: {html.escape(author.get('org',''))}</div>
</footer>
</div>
<script>window.SPP_BASE="{BASE_URL}";</script>
<script src="{js}" defer></script>
</body></html>"""

# ---------- render markets (light theme) & inject into Ravensight homepage ----------
def render_markets_section_light(tree: Dict[str, Dict[str, Dict[str, object]]], base_url: str) -> str:
    sections = []
    for gslug in sorted(tree.keys()):
        first = next(iter(tree[gslug].values()))
        gname = first["group_name"]

        cards = []
        for cslug_raw in sorted(tree[gslug].keys()):
            country = tree[gslug][cslug_raw]
            cname = country["country_name"]
            cslug_dir = slug(cslug_raw)
            rows = country["rows"]

            seen, ex_list = set(), []
            for r in rows:
                ex = (r.get("exchange") or "").strip()
                if not ex or ex.upper() == "UNKNOWN": 
                    continue
                key = ex.lower()
                if key in seen: 
                    continue
                seen.add(key)
                ex_list.append(ex)

            flag_url = f"{base_url}/logos/countryflags/{cslug_dir}.svg"
            chips = "".join(
                f"<a href='/{gslug}/{cslug_dir}/{slug(ex)}/' class='px-2.5 py-1 rounded-full border text-xs text-slate-700 border-slate-300 hover:border-indigo-400 hover:text-indigo-700 transition'>{html.escape(ex)}</a>"
                for ex in sorted(ex_list)
            ) or "<span class='text-xs text-slate-400'>No exchanges</span>"

            cards.append(
                "<div class='rounded-xl border border-slate-200 bg-white p-4 shadow-sm'>"
                f"  <img src='{flag_url}' alt='{html.escape(cname)} flag' class='w-8 h-5 rounded object-cover shadow-sm mb-2'/>"
                f"  <div class='font-semibold text-slate-800 mb-2'>{html.escape(cname)}</div>"
                f"  <div class='flex flex-wrap gap-2'>{chips}</div>"
                "</div>"
            )

        region_block = (
            "<section class='mb-10'>"
            f"  <h3 class='text-lg font-bold text-slate-800 mb-4'>{html.escape(gname)}</h3>"
            f"  <div class='grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4'>{''.join(cards)}</div>"
            "</section>"
        )
        sections.append(region_block)

    search_block = """
<div id="global-search" class="max-w-6xl mx-auto mb-8">
  <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
    <label class="block text-sm font-medium text-slate-700 mb-2">Global Search</label>
    <!-- search.js will build input + results here -->
  </div>
</div>
"""

    return (
        "<!-- AUTO-INJECTED: All Markets section -->"
        "<section id='all-markets' class='pt-6 pb-16'>"
        "  <div class='max-w-6xl mx-auto px-4 md:px-8'>"
        "    <h2 class='text-2xl md:text-3xl font-extrabold tracking-tight text-slate-900 mb-4'>Browse All Markets</h2>"
        "    <p class='text-slate-600 mb-6'>Explore countries and jump straight into their exchanges, or use the global search below to find a stock by symbol or name.</p>"
        f"    {search_block}"
        f"    {''.join(sections)}"
        "  </div>"
        "</section>"
        "<!-- /AUTO-INJECTED -->"
    )

def inject_into_home(dist_index: Path, markets_html: str, base_url: str) -> None:
    if not dist_index.exists():
        print("⚠️  inject_into_home: dist index.html not found", dist_index)
        return
    html_txt = dist_index.read_text(encoding="utf-8")

    # insert before </main> (preferred), else before </footer>, else before </body>, else append
    inserted = False
    for marker in ["</main>", "</footer>", "</body>"]:
        idx = html_txt.lower().rfind(marker)
        if idx != -1:
            html_txt = html_txt[:idx] + markets_html + html_txt[idx:]
            inserted = True
            break
    if not inserted:
        html_txt += markets_html

    # ensure search.js is referenced
    script_tag = f"<script src=\"{base_url}/static/search.js\" defer></script>"
    if script_tag not in html_txt:
        pos = html_txt.lower().rfind("</body>")
        if pos != -1:
            html_txt = html_txt[:pos] + script_tag + "\n" + html_txt[pos:]
        else:
            html_txt += script_tag

    dist_index.write_text(html_txt, encoding="utf-8")
    print("✅ Injected All Markets section + global search into homepage.")

# ---------- landing builder for internal “dark” index (kept for /regions etc.) ----------
def build_landing(tree: Dict[str, Dict[str, Dict[str, object]]]) -> None:
    sections = []
    for gslug in sorted(tree.keys()):
        gname = next(iter(tree[gslug].values()))["group_name"]
        cards = []
        for cslug_raw in sorted(tree[gslug].keys()):
            cname = tree[gslug][cslug_raw]["country_name"]
            cslug_dir = slug(cslug_raw)
            rows = tree[gslug][cslug_raw]["rows"]
            ex_set, seen = [], set()
            for r in rows:
                ex = (r.get("exchange") or "").strip()
                if not ex or ex.upper()=="UNKNOWN": continue
                if ex.lower() in seen: continue
                seen.add(ex.lower()); ex_set.append(ex)
            ex_links = "".join(
                f"<a href='/{gslug}/{cslug_dir}/{slug(ex)}/'>{html.escape(ex)}</a>"
                for ex in sorted(ex_set)
            )
            flag = f"{BASE_URL}/logos/countryflags/{cslug_dir}.svg"
            cards.append(
                "<div class='country-card'>"
                f"<img src='{flag}' alt='{html.escape(cname)} flag' class='country-flag'/>"
                f"<div class='country-name'>{html.escape(cname)}</div>"
                f"<div class='exchange-list'>{ex_links or '<span class=\"small\">No exchanges</span>'}</div>"
                "</div>"
            )
        sections.append(
            "<section class='region'>"
            f"<h2>{html.escape(gname)}</h2>"
            f"<div class='countries'>{''.join(cards)}</div>"
            "</section>"
        )

    click_js = """
<script>
(function(){
  const $$=(s,r=document)=>Array.from(r.querySelectorAll(s));
  $$('.country-card').forEach(card=>{
    const firstEx=card.querySelector('.exchange-list a[href]');
    if(!firstEx)return;
    const u=new URL(firstEx.getAttribute('href'), location.origin);
    const parts=u.pathname.split('/').filter(Boolean);
    if(parts.length<3)return;
    const countryUrl='/' + parts[0] + '/' + parts[1] + '/';
    card.style.cursor='pointer';
    card.addEventListener('click', ev=>{
      if(ev.target.closest('.exchange-list a')) return;
      location.href=countryUrl;
    });
    const nameEl=card.querySelector('.country-name');
    if(nameEl){
      nameEl.style.textDecoration='underline';
      nameEl.style.textUnderlineOffset='2px';
      nameEl.style.cursor='pointer';
      nameEl.addEventListener('click', ev=>{ev.stopPropagation(); location.href=countryUrl;});
    }
  });
})();
</script>
"""
    landing_html = tpl_base(
        "🌍 Global Stock Markets",
        "Browse world markets by region, country and exchange.",
        "".join(sections) + click_js,
        f"{BASE_URL}/"
    )
    write_text(DIST / "index.html", landing_html)

# ---------- build ----------
def main() -> None:
    ensure_dir(DIST / "static")
    copy_static_assets()
    ensure_placeholder_logo()
    ensure_countryflags()

    tree = load_last_trading_day()
    resolver = LogoResolver()
    mkt = MarketTimes()

    # internal pages (dark theme): region/country/exchange + stock pages
    # build_landing(tree)  # no need to overwrite index.html now; we inject into Ravensight page instead

    for gslug in sorted(tree.keys()):
        gname = next(iter(tree[gslug].values()))["group_name"]

        links = []
        for cslug_raw in sorted(tree[gslug].keys()):
            cname = tree[gslug][cslug_raw]["country_name"]
            cslug_dir = slug(cslug_raw)
            links.append(f"<li><a href='/{gslug}/{cslug_dir}/'>{html.escape(cname)}</a></li>")

        write_text(
            DIST / gslug / "index.html",
            tpl_base(
                f"{gname} Markets",
                "Countries list",
                "<section class='card'><ul>" + "".join(links) + "</ul></section>",
                f"{BASE_URL}/{gslug}/",
            ),
        )

        for cslug_raw, country in tree[gslug].items():
            cname = country["country_name"]
            rows = country["rows"]
            cslug_dir = slug(cslug_raw)

            by: Dict[str, List[Dict[str, str]]] = {}
            for r in rows:
                by.setdefault((r.get("exchange") or "UNKNOWN").strip(), []).append(r)

            def build_exchange_bar(region_slug, country_slug, country_name, exchanges, active_slug: Optional[str] = None):
                flag_path = f"{BASE_URL}/logos/countryflags/{country_slug}.svg"
                chips = []
                chips.append("<a href='#' data-ex='all' class='exchip'>All</a>")
                for ex_name in sorted(e for e in exchanges if e and e.upper() != "UNKNOWN"):
                    ex_slug = slug(ex_name)
                    chips.append(f"<a href='#' data-ex='{ex_slug}' class='exchip'>{html.escape(ex_name)}</a>")
                tools = (
                    "<div class='tools'>"
                    "<input id='cty-search' class='search-input' type='search' placeholder='Search symbol or name…'>"
                    "</div>"
                )
                return (
                    "<div class='exchange-bar'>"
                    "<div class='flagwrap'>"
                    f"<img src='{flag_path}' alt='{html.escape(country_name)} flag' class='flag'>"
                    f"<span class='cname'>{html.escape(country_name)}</span>"
                    "</div>"
                    f"<div class='chipswrap'>{''.join(chips)}</div>"
                    f"{tools}"
                    "</div>"
                )

            all_exchanges = sorted(k for k in by.keys() if k and k.upper() != "UNKNOWN")

            for exch, erows in sorted(by.items(), key=lambda kv: kv[0].lower()):
                e_slug = slug(exch)
                table_rows = []
                json_rows = []
                _ = mkt.prediction_date(region=gname, country=cname, exchange=exch)

                for r in erows:
                    sym = (r.get("symbol") or "").strip()
                    name = (r.get("description") or sym or "").strip()
                    sec = (r.get("sector") or "").strip()
                    o, h, l, cl = _f(r.get("open")), _f(r.get("high")), _f(r.get("low")), _f(r.get("close"))
                    ch_raw = r.get("change_percent") or r.get("change%") or ""
                    try: ch = float(ch_raw)
                    except Exception: ch = None

                    s_slug = slug(sym)
                    stock_url = f"{BASE_URL}/{gslug}/{cslug_dir}/{e_slug}/{s_slug}/prediction-tomorrow/"
                    logo_url = resolver.url_for(exch, sym, name)
                    ch_html = "" if ch is None else f"<span class='pct {'pos' if ch and ch>0 else ('neg' if ch and ch<0 else '')}'>{'' if ch is None else f'{ch:.2f}%'}</span>"

                    table_rows.append(
                        "<tr>"
                        f"<td><img class='logo' src='{logo_url}' alt=''> <a href='{stock_url}'>{html.escape(sym)}</a></td>"
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

                    json_rows.append({
                        "symbol": sym, "name": name, "sector": sec,
                        "open": None if o is None else round(o,2),
                        "high": None if h is None else round(h,2),
                        "low":  None if l is None else round(l,2),
                        "close":None if cl is None else round(cl,2),
                        "change_percent": None if ch is None else round(ch,4),
                        "url": stock_url,
                        "logo": logo_url,
                    })

                    if sym and None not in (o, h, l, cl):
                        title = f"AI Analysis of {sym} Tomorrow | {name} Stock Prediction"
                        head = (
                            "<div class='card'>"
                            f"<h2 class='h2'>AI Analysis of {html.escape(sym)} ({html.escape(name)})</h2>"
                            f"<p class='small'>Region: {html.escape(gname)} · Country: {html.escape(cname)} · Exchange: {html.escape(exch)}</p>"
                            f"<p class='small'>OHLC: O {'{:.2f}'.format(o)}, H {'{:.2f}'.format(h)}, L {'{:.2f}'.format(l)}, C {'{:.2f}'.format(cl)}</p>"
                            "</div>"
                        )
                        write_text(
                            DIST / gslug / cslug_dir / e_slug / s_slug / "prediction-tomorrow" / "index.html",
                            tpl_base(title, title, head, f"{BASE_URL}/{gslug}/{cslug_dir}/{e_slug}/{s_slug}/prediction-tomorrow/"),
                        )

                table_html = (
                    "<div class='table-wrap'>"
                    "<table class='table'>"
                    "<thead><tr><th>Symbol</th><th>Name</th><th>Sector</th><th>Open</th><th>High</th>"
                    "<th>Low</th><th>Close</th><th>Change%</th><th>Signal</th></tr></thead>"
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

                write_json(
                    DIST / "static" / "exchanges" / gslug / cslug_dir / f"{e_slug}.json",
                    {"region": gname, "country": cname, "exchange": exch, "rows": json_rows},
                )

            default_ex_slug = slug(all_exchanges[0]) if all_exchanges else ""

            loader_js = f"""
<script>
(function(){{
  const BASE = "{BASE_URL}/static/exchanges/{gslug}/{cslug_dir}/";
  const chips = Array.from(document.querySelectorAll('.exchange-bar .exchip'));
  const tableHost = document.getElementById('ex-table');
  const searchEl = document.getElementById('cty-search');
  const PAGE_SIZE = 50;

  let active = "{default_ex_slug}" || "all";
  let page = 1;
  let sortMode = 'chg-asc';
  const dataByEx = Object.create(null);
  let allMerged = [];

  function ensureLoadMoreArea(){{
    let wrap = document.getElementById('load-more-wrap');
    if (!wrap){{
      wrap = document.createElement('div');
      wrap.id = 'load-more-wrap';
      wrap.className = 'loadmore-wrap';
      wrap.innerHTML = "<button id='load-more' class='btn'>Load more</button>";
      tableHost.insertAdjacentElement('afterend', wrap);
      wrap.addEventListener('click', function(ev){{
        const btn = document.getElementById('load-more');
        if (ev.target === btn) {{ page += 1; render(); }}
      }});
    }}
  }}

  function compare(a,b,mode){{
    const sa = (a.symbol||'').toLowerCase(), sb = (b.symbol||'').toLowerCase();
    const na = (a.name||'').toLowerCase(), nb = (b.name||'').toLowerCase();
    const ca = (a.change_percent==null)?0:a.change_percent;
    const cb = (b.change_percent==null)?0:b.change_percent;
    switch(mode){{
      case 'sym-asc': return sa<sb?-1:sa>sb?1:0;
      case 'sym-desc': return sa>sb?-1:sa<sb?1:0;
      case 'name-asc': return na<nb?-1:na>nb?1:0;
      case 'name-desc': return na>nb?-1:na<nb?1:0;
      case 'chg-asc': return (ca - cb);
      case 'chg-desc': return (cb - ca);
      default: return 0;
    }}
  }}

  function filterRows(rows, q){{
    if (!q) return rows;
    const s = q.toLowerCase();
    return rows.filter(r => (r.symbol && r.symbol.toLowerCase().includes(s)) || (r.name && r.name.toLowerCase().includes(s)));
  }}

  function fmt(v){{ return (v==null || v==='') ? '' : (''+v); }}

  function headerArrow(mode){{
    switch(mode){{
      case 'sym-asc': return {{col:'sym', arrow:'▲'}};
      case 'sym-desc': return {{col:'sym', arrow:'▼'}};
      case 'name-asc': return {{col:'name', arrow:'▲'}};
      case 'name-desc': return {{col:'name', arrow:'▼'}};
      case 'chg-asc': return {{col:'chg', arrow:'▲'}};
      case 'chg-desc': return {{col:'chg', arrow:'▼'}};
      default: return {{col:'', arrow:''}};
    }}
  }}

  function render(){{
    ensureLoadMoreArea();
    const q = searchEl.value.trim();

    let base = (active==='all') ? allMerged : (dataByEx[active]||[]);
    let rows = filterRows(base, q).slice();
    rows.sort((a,b)=>compare(a,b,sortMode));

    const total = rows.length;
    const upto = Math.min(total, page*PAGE_SIZE);
    const view = rows.slice(0, upto);

    const hd = headerArrow(sortMode);

    let html = "";
    html += "<div class='table-wrap'><table class='table'><thead>";
    html += "<tr>";
    html += "<th class='th-sort"+(hd.col==='sym'?" active":"")+"' data-sort='sym'>Symbol<span class='arrow'>"+(hd.col==='sym'?hd.arrow:"")+"</span></th>";
    html += "<th class='th-sort"+(hd.col==='name'?" active":"")+"' data-sort='name'>Name<span class='arrow'>"+(hd.col==='name'?hd.arrow:"")+"</span></th>";
    html += "<th>Sector</th><th>Open</th><th>High</th><th>Low</th><th>Close</th>";
    html += "<th class='th-sort"+(hd.col==='chg'?" active":"")+"' data-sort='chg'>Change%<span class='arrow'>"+(hd.col==='chg'?hd.arrow:"")+"</span></th>";
    html += "<th>Signal</th>";
    html += "</tr></thead><tbody>";

    for (let i=0;i<view.length;i++) {{
      const r = view[i];
      const v = (r.change_percent==null) ? null : (r.change_percent*1);
      const chg = (v==null) ? "" : (v.toFixed(2) + "%");
      const cls = (v==null) ? "" : (v>0 ? "pct pos" : (v<0 ? "pct neg" : "pct"));
      html += "<tr>"
           + "<td>" + (r.logo ? "<img class='logo' src='" + r.logo + "' alt=''> " : "") + "<a href='" + fmt(r.url) + "'>" + fmt(r.symbol) + "</a></td>"
           + "<td>" + fmt(r.name) + "</td>"
           + "<td>" + fmt(r.sector) + "</td>"
           + "<td>" + fmt(r.open) + "</td>"
           + "<td>" + fmt(r.high) + "</td>"
           + "<td>" + fmt(r.low) + "</td>"
           + "<td>" + fmt(r.close) + "</td>"
           + "<td>" + (chg?("<span class='" + cls + "'>" + chg + "</span>"):"") + "</td>"
           + "<td><a class='btn' href='" + fmt(r.url) + "'>AI Prediction</a></td>"
           + "</tr>";
    }}
    html += "</tbody></table></div>";

    tableHost.innerHTML = html;

    Array.from(tableHost.querySelectorAll('.th-sort')).forEach(th => {{
      th.addEventListener('click', () => {{
        const k = th.getAttribute('data-sort');
        if (k==='sym') sortMode = (sortMode==='sym-asc') ? 'sym-desc' : 'sym-asc';
        if (k==='name') sortMode = (sortMode==='name-asc') ? 'name-desc' : 'name-asc';
        if (k==='chg') sortMode = (sortMode==='chg-asc') ? 'chg-desc' : 'chg-asc';
        page = 1; render();
      }});
    }});

    const moreBtn = document.getElementById('load-more');
    if (moreBtn) moreBtn.style.display = (upto < total) ? '' : 'none';
  }}

  async function fetchExchange(slug){{
    if (slug==='all') {{
      const exSlugs = chips.map(c=>c.dataset.ex).filter(x=>x && x!=='all');
      await Promise.all(exSlugs.map(s => fetchExchange(s)));
      const merged = []; const dedup = new Set();
      exSlugs.forEach(s => {{
        (dataByEx[s]||[]).forEach(r => {{
          const key = (r.symbol||'') + "|" + (r.url||'');
          if (!dedup.has(key)) {{ dedup.add(key); merged.push(r); }}
        }});
      }});
      allMerged = merged;
      return merged;
    }}
    if (dataByEx[slug]) return dataByEx[slug];
    try {{
      const res = await fetch(BASE + slug + ".json");
      const data = await res.json();
      dataByEx[slug] = data.rows || [];
      return dataByEx[slug];
    }} catch(e) {{
      dataByEx[slug] = [];
      return dataByEx[slug];
    }}
  }}

  async function activate(slug){{
    active = slug || 'all';
    page = 1;
    chips.forEach(c=>c.classList.toggle('active', c.dataset.ex===active));
    await fetchExchange(active);
    render();
  }}

  chips.forEach(c=>c.addEventListener('click', ev=>{{ ev.preventDefault(); activate(c.dataset.ex||'all'); }}));
  searchEl.addEventListener('input', function(){{ page=1; render(); }});

  activate(active || 'all');
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

    # --- Copy your Ravensight landing page (exact, unmodified) ---
    candidates = [
        ROOT / "index.html",                 # preferred: repo root
        ROOT / "static" / "index.html",
        ROOT / "scripts" / "index.html",
        ROOT / "landing" / "index.html",
    ]
    landing_src = next((p for p in candidates if p.exists()), None)
    landing_dst = DIST / "index.html"
    if landing_src:
        shutil.copyfile(landing_src, landing_dst)
        print("Landing page copied →", landing_dst)
    else:
        print("⚠️  Landing page not found in any of:", ", ".join(str(p) for p in candidates))

    # --- Inject All Markets (countries + flags + exchanges) + Global Search below your hero ---
    markets_html = render_markets_section_light(tree, BASE_URL)
    inject_into_home(landing_dst, markets_html, BASE_URL)

# ---------- entry ----------
if __name__ == "__main__":
    main()
