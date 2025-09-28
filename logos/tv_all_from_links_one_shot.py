# --- Windows asyncio fix ---
import sys, asyncio
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import os, re, csv, json, string
from pathlib import Path
from urllib.parse import urlparse, urlencode
import aiohttp

# ===================== YOUR LINKS (exactly as provided) =====================
LINK_GROUPS = {
    "North America": [
        "https://in.tradingview.com/markets/stocks-usa/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-canada/market-movers-all-stocks/",
    ],
    "Europe": [
        "https://in.tradingview.com/markets/stocks-austria/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-italy/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-belgium/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-lithuania/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-switzerland/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-latvia/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-cyprus/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-luxembourg/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-czech/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-netherlands/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-germany/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-norway/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-denmark/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-poland/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-estonia/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-portugal/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-spain/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-serbia/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-finland/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-russia/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-france/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-romania/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-greece/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-sweden/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-hungary/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-slovakia/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-ireland/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-turkey/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-iceland/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-united-kingdom/market-movers-all-stocks/",
    ],
    "Middle East - Africa": [
        "https://in.tradingview.com/markets/stocks-uae/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-bahrain/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-nigeria/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-egypt/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-qatar/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-israel/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-ksa/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-kenya/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-tunisia/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-kuwait/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-south-africa/market-movers-all-stocks/",
    ],
    "Mexico - South America": [
        "https://in.tradingview.com/markets/stocks-argentina/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-mexico/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-brazil/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-peru/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-chile/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-venezuela/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-colombia/market-movers-all-stocks/",
    ],
    "Asia - Pacific": [
        "https://in.tradingview.com/markets/stocks-australia/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-malaysia/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-bangladesh/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-new-zealand/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-china/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-philippines/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-hong-kong/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-pakistan/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-indonesia/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-singapore/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-india/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-thailand/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-japan/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-taiwan/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-korea/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-vietnam/market-movers-all-stocks/",
        "https://in.tradingview.com/markets/stocks-sri-lanka/market-movers-all-stocks/",
    ],
}

# Country slug -> exchange codes (used for symbol-search fallback)
PAGE_EXCHANGES = {
    "usa": ["NASDAQ","NYSE","NYSEARCA","CBOE","OTC"],
    "canada": ["TSX","TSXV","CSE","NEO"],
    "austria": ["VIE"],
    "belgium": ["EURONEXTBRU"],
    "switzerland": ["SIX","BX"],
    "cyprus": ["CSECY"],
    "czech": ["PSECZ"],
    "germany": ["FWB","SWB","XETR","BER","DUS","HAM","HAN","MUN","TRADEGATE","LS","LSX","GETTEX"],
    "denmark": ["OMXCOP"],
    "estonia": ["OMXTSE"],
    "spain": ["BME"],
    "finland": ["OMXHEX"],
    "france": ["EURONEXTPAR"],
    "greece": ["ATHEX"],
    "hungary": ["BET"],
    "ireland": ["EURONEXTDUB"],
    "iceland": ["OMXICE"],
    "italy": ["MIL","EUROTLX"],
    "lithuania": ["OMXVSE"],
    "latvia": ["OMXRSE"],
    "luxembourg": ["LUXSE"],
    "netherlands": ["EURONEXTAMS"],
    "norway": ["OSE","OSL","EURONEXTOSE"],
    "poland": ["GPW","NEWCONNECT"],
    "portugal": ["EURONEXTLIS"],
    "serbia": ["BELEX"],
    "romania": ["BVB"],
    "sweden": ["NGM","OMXSTO"],
    "slovakia": ["BSSE"],
    "turkey": ["BIST"],
    "united-kingdom": ["LSE","LSIN","AQUIS","AQSE"],
    "russia": ["RUS"],
    "uae": ["DFM","ADX","NASDAQDUBAI"],
    "bahrain": ["BAHRAIN"],
    "egypt": ["EGX"],
    "israel": ["TASE"],
    "kenya": ["NSEKE"],
    "kuwait": ["KSE"],
    "morocco": ["CSEMA"],
    "nigeria": ["NSENG"],
    "qatar": ["QSE"],
    "ksa": ["TADAWUL"],
    "tunisia": ["BVMT"],
    "south-africa": ["JSE"],
    "argentina": ["BYMA","BCBA"],
    "brazil": ["BMFBOVESPA"],
    "chile": ["BCS"],
    "colombia": ["BVC"],
    "mexico": ["BMV","BIVA"],
    "peru": ["BVL"],
    "venezuela": ["BVCV"],
    "australia": ["ASX"],
    "bangladesh": ["DSEBD"],
    "china": ["SSE","SZSE"],
    "hong-kong": ["HKEX"],
    "indonesia": ["IDX"],
    "india": ["NSE","BSE"],
    "japan": ["TSE","JASDAQ","NAG","FSE","SAPSE"],
    "korea": ["KRX"],
    "sri-lanka": ["CSELK"],
    "malaysia": ["MYX"],
    "new-zealand": ["NZX"],
    "philippines": ["PSE"],
    "pakistan": ["PSX"],
    "singapore": ["SGX"],
    "thailand": ["SET","MAI"],
    "taiwan": ["TWSE","TPEX"],
    "vietnam": ["HOSE","HNX","UPCOM"],
}

# slug -> printable country name
COUNTRY_NAME = {
    "usa":"United States","canada":"Canada",
    "austria":"Austria","italy":"Italy","belgium":"Belgium","lithuania":"Lithuania",
    "switzerland":"Switzerland","latvia":"Latvia","cyprus":"Cyprus","luxembourg":"Luxembourg",
    "czech":"Czech Republic","netherlands":"Netherlands","germany":"Germany","norway":"Norway",
    "denmark":"Denmark","poland":"Poland","estonia":"Estonia","portugal":"Portugal","spain":"Spain",
    "serbia":"Serbia","finland":"Finland","russia":"Russia","france":"France","romania":"Romania",
    "greece":"Greece","sweden":"Sweden","hungary":"Hungary","slovakia":"Slovakia","ireland":"Ireland",
    "turkey":"Turkey","iceland":"Iceland","united-kingdom":"United Kingdom",
    "uae":"United Arab Emirates","bahrain":"Bahrain","nigeria":"Nigeria","egypt":"Egypt","qatar":"Qatar",
    "israel":"Israel","ksa":"Saudi Arabia","kenya":"Kenya","tunisia":"Tunisia","kuwait":"Kuwait",
    "south-africa":"South Africa",
    "argentina":"Argentina","mexico":"Mexico","brazil":"Brazil","peru":"Peru","chile":"Chile",
    "venezuela":"Venezuela","colombia":"Colombia",
    "australia":"Australia","malaysia":"Malaysia","bangladesh":"Bangladesh","new-zealand":"New Zealand",
    "china":"China","philippines":"Philippines","hong-kong":"Hong Kong","pakistan":"Pakistan",
    "indonesia":"Indonesia","singapore":"Singapore","india":"India","thailand":"Thailand",
    "japan":"Japan","taiwan":"Taiwan","korea":"South Korea","vietnam":"Vietnam","sri-lanka":"Sri Lanka",
}

# Which datasets to try per group; we also try the country slug itself first.
GROUP_DATASETS = {
    "North America": ["america"],
    "Europe": ["europe","america"],
    "Middle East - Africa": ["middle_east","africa","america"],
    "Mexico - South America": ["america","brazil","mexico"],
    "Asia - Pacific": ["asia","australia","america"],
}

# ============= OUTPUT =============
BASE_DIR = Path("tv-logos")  # logos folder
OUT_CSV = Path("tv_from_links_names_and_logos.csv")
OUT_JSON = Path("tv_logos_manifest.json")
OUT_HTML = Path("tv_logos_index.html")
BASE_WEB_PATH = "tv-logos"   # how your site will serve the logos

# ============= Parsers for logo + name =============
OG_IMG_RE = re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https://s3-symbol-logo\.tradingview\.com/[^"\']+\.(?:svg|png))["\']', re.I)
TW_IMG_RE = re.compile(r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\'](https://s3-symbol-logo\.tradingview\.com/[^"\']+\.(?:svg|png))["\']', re.I)
JSONLD_LOGO_RE = re.compile(r'"logo"\s*:\s*"(?P<url>https://s3-symbol-logo\.tradingview\.com/[^"]+\.(?:svg|png))"', re.I)
ALL_LOGOS_RE  = re.compile(r"https://s3-symbol-logo\.tradingview\.com/([a-z0-9\-]+)\.(svg|png)", re.I)

JSONLD_NAME_RE = re.compile(r'"@type"\s*:\s*"Organization"[^}]*?"name"\s*:\s*"([^"]+)"', re.I)
OG_TITLE_RE    = re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', re.I)
TITLE_RE       = re.compile(r"<title>([^<]+)</title>", re.I)

EXCHANGE_BADGES = {
    "nasdaq","nyse","amex","nysearca","cboe","otc","tsx","tsx-venture","tmx","lse","euronext","xetra",
    "bse","nse","asx","hkex","tse","szse","sse","kospi","bovespa","bmv","jse","six","sgx","tadawul",
    "nzx","idx","bist","bme","bvb","bolsa-madrid","gettex","tradegate","ls","lsx","ose","osl",
    "euronextams","euronextpar",
}

# ============= HTTP helpers =============
STEP = 500
CONCURRENCY = 8

async def fetch_json(session, url, payload):
    async with session.post(url, json=payload, timeout=60) as r:
        if r.status == 404:
            raise aiohttp.ClientResponseError(r.request_info, r.history, status=404, message="Not Found")
        r.raise_for_status()
        return await r.json()

async def fetch_text(session, url):
    async with session.get(url, timeout=60) as r:
        if r.status != 200: return ""
        return await r.text()

async def download_logo(session, url, dest: Path, tries=3):
    last = None
    for i in range(tries):
        try:
            async with session.get(url, timeout=60) as r:
                if r.status == 200:
                    data = await r.read()
                    if data:
                        dest.write_bytes(data); return True
                last = f"HTTP {r.status}"
        except Exception as e:
            last = str(e)
        await asyncio.sleep(1.0 * (i + 1))
    print(f"  ! Failed {url}: {last}")
    return False

# ============= Page parsing =============
def filename_from_url(url: str) -> str:
    return os.path.basename(urlparse(url).path).split("?")[0]

def is_exchange_slug(slug: str, exchange: str) -> bool:
    s = slug.lower()
    ex = (exchange or "").lower()
    return s in EXCHANGE_BADGES or s == ex

def pick_company_logo_from_html(html: str, exchange: str):
    for rx in (OG_IMG_RE, TW_IMG_RE, JSONLD_LOGO_RE):
        m = rx.search(html)
        if m:
            url = m.group(1) if rx is not JSONLD_LOGO_RE else m.group("url")
            sm = ALL_LOGOS_RE.search(url)
            if sm and not is_exchange_slug(sm.group(1), exchange):
                return url
    for mm in ALL_LOGOS_RE.finditer(html):
        if not is_exchange_slug(mm.group(1), exchange):
            return mm.group(0)
    return None

def clean_display_name(name: str, ticker: str=""):
    if not name: return ""
    name = re.sub(r"\s*\((?:[A-Z\.\-]+)\)\s*—\s*[A-Za-z0-9\- ]+$", "", name).strip()
    name = re.sub(r"\s*[\|\-–—]\s*[A-Za-z0-9\- ]+$", "", name).strip()
    if ticker and ticker in name:
        parts = [p.strip() for p in re.split(r"[–—\-|]", name) if p.strip()]
        if len(parts) >= 2:
            chosen = max((p for p in parts if ticker not in p), key=len, default=name)
            return chosen.strip()
    return name

def extract_company_name(html: str, ticker: str, fallback: str):
    for rx in (JSONLD_NAME_RE, OG_TITLE_RE, TITLE_RE):
        m = rx.search(html)
        if m:
            return clean_display_name(m.group(1), ticker)
    return fallback.strip() if isinstance(fallback, str) else ""

# ============= Symbol discovery =============
def slug_from_url(url: str):
    try:
        for p in url.strip("/").split("/"):
            if p.startswith("stocks-"):
                return p.replace("stocks-","")
    except Exception:
        pass
    return None

def datasets_for(group: str, slug: str):
    return [slug] + GROUP_DATASETS.get(group, ["america"])

async def fetch_symbols_for_country(session, dataset: str, slug: str):
    cn = COUNTRY_NAME.get(slug)
    if not cn:
        return []
    endpoint = f"https://scanner.tradingview.com/{dataset}/scan"
    symbols = []
    offset = 0
    page = 0
    while True:
        page += 1
        payload = {
            "filter": [
                {"left":"country","operation":"equal","right": cn},
                {"left":"type","operation":"in_range","right":["stock"]},
            ],
            "options":{"lang":"en"},
            "symbols":{"query":{"types":[]}, "tickers":[]},
            "columns":["name"],
            "sort":{"sortBy":"name","sortOrder":"asc"},
            "range":[offset, offset + STEP - 1]
        }
        data = await fetch_json(session, endpoint, payload)
        rows = data.get("data") or []
        if not rows: break
        got = len(rows)
        for row in rows:
            s = row.get("s") or ""
            nm = ""
            d = row.get("d") or []
            if d and isinstance(d, list): nm = d[0] or ""
            if ":" in s:
                ex, tk = s.split(":", 1)
                symbols.append((ex.strip().upper(), tk.strip().upper(), nm))
        print(f"    {dataset}/{slug}: page {page} -> {got} rows (offset {offset})")
        offset += got
    # de-dup
    ded = {}
    for ex, tk, nm in symbols:
        ded.setdefault((ex, tk), nm)
    return [(ex, tk, ded[(ex, tk)]) for (ex, tk) in sorted(ded.keys())]

async def symbol_search_fallback(session, slug: str):
    """Use TV symbol search (50 per query) across exchanges we mapped for this slug."""
    exchanges = PAGE_EXCHANGES.get(slug, [])
    base = "https://symbol-search.tradingview.com/symbol_search/"
    chars = list(string.ascii_uppercase) + list(string.digits)
    out = {}
    for ex in exchanges:
        for ch in chars:
            qs = urlencode({"text": ch, "exchange": ex, "type": "stock", "hl": 1, "lang": "en"})
            url = f"{base}?{qs}"
            try:
                async with session.get(url, timeout=30) as r:
                    if r.status != 200: continue
                    data = await r.json()
            except Exception:
                continue
            for it in data or []:
                exchange = str(it.get("exchange","")).upper()
                ticker   = str(it.get("symbol","")).upper()
                name     = it.get("description") or ""
                if exchange and ticker:
                    out.setdefault((exchange, ticker), name)
        print(f"    SymbolSearch {slug}/{ex}: {sum(1 for k in out if k[0]==ex)}")
    return [(ex, tk, out[(ex, tk)]) for (ex, tk) in sorted(out.keys())]

# ============= CSV + manifest =============
def init_csv():
    if not OUT_CSV.exists():
        with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(
                ["group","country_slug","country_name","exchange","ticker","company_name",
                 "symbol_url","logo_url","logo_file","logo_relpath"]
            )

def to_web_path(p: Path) -> str:
    return str(p).replace("\\","/")

async def process_country_link(session, group: str, url: str, sem_global: asyncio.Semaphore):
    slug = slug_from_url(url)
    if not slug:
        print(f"!! Skipping unknown url format: {url}")
        return
    country_name = COUNTRY_NAME.get(slug, "")
    print(f"\n==> {group} | {slug}")

    # discover symbols
    datasets = datasets_for(group, slug)
    syms, last_err = None, None
    for ds in datasets:
        try:
            syms = await fetch_symbols_for_country(session, ds, slug)
            if syms: break
        except aiohttp.ClientResponseError as e:
            last_err = e; continue
        except Exception as e:
            last_err = e; continue
    if not syms:
        print(f"  !! Scanner empty/blocked for {slug}. Trying Symbol Search fallback…")
        syms = await symbol_search_fallback(session, slug)
    if not syms:
        print(f"  !! No symbols for {slug}. Last error: {last_err}")
        return
    print(f"  Listed {len(syms)} for {slug}")

    # resume set
    done = set()
    if OUT_CSV.exists():
        try:
            with OUT_CSV.open("r", encoding="utf-8", newline="") as f:
                rdr = csv.DictReader(f)
                for r in rdr:
                    done.add((r.get("country_slug",""), r.get("exchange",""), r.get("ticker","")))
        except Exception:
            pass

    lock = asyncio.Lock()

    async def worker(ex, tk, nm):
        key = (slug, ex, tk)
        if key in done:
            return
        async with sem_global:
            sym_url = f"https://www.tradingview.com/symbols/{ex}-{tk}/"
            html = await fetch_text(session, sym_url)
            if not html:
                # append CSV as seen but no logo/name yet
                async with lock:
                    with OUT_CSV.open("a", newline="", encoding="utf-8") as f:
                        csv.writer(f).writerow([group, slug, country_name, ex, tk, nm, sym_url, "", "", ""])
                return

            # parse logo + name
            logo_url = pick_company_logo_from_html(html, ex)
            name = extract_company_name(html, tk, nm)
            relpath = ""
            logo_file = ""
            if logo_url:
                logo_file = filename_from_url(logo_url)
                folder = BASE_DIR / slug / ex
                folder.mkdir(parents=True, exist_ok=True)
                dest = folder / logo_file
                relpath = str(Path(slug) / ex / logo_file)
                if not dest.exists():
                    ok = await download_logo(session, logo_url, dest)
                    if ok:
                        print(f"[{slug} | {ex}] Saved {logo_file}")
            # write row
            async with lock:
                with OUT_CSV.open("a", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow([group, slug, country_name, ex, tk, name, sym_url, logo_url or "", logo_file or "", relpath])

    await asyncio.gather(*[worker(ex, tk, nm) for (ex, tk, nm) in syms])

def build_manifest_and_html():
    # build json from CSV, include only rows where file exists
    rows = []
    if not OUT_CSV.exists():
        return
    with OUT_CSV.open("r", encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            country = r.get("country_slug","")
            exchange = r.get("exchange","")
            ticker = r.get("ticker","")
            name = r.get("company_name","")
            logo_file = r.get("logo_file","")
            rel = r.get("logo_relpath","")
            if rel:
                relpath = Path(rel)
            elif country and exchange and logo_file:
                relpath = Path(country) / exchange / logo_file
            else:
                continue
            full = BASE_DIR / relpath
            if not full.exists():
                continue
            rows.append({
                "country": country,
                "exchange": exchange,
                "ticker": ticker,
                "name": name,
                "logo": to_web_path(Path(BASE_WEB_PATH) / relpath)
            })

    rows.sort(key=lambda x: (x["country"] or "~", x["exchange"] or "~", x["ticker"] or "~"))

    OUT_JSON.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>TV Logos Index</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 24px; }}
    #q {{ padding: 8px 12px; width: 420px; max-width: 90%; font-size: 16px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; margin-top: 16px; }}
    .card {{ border: 1px solid #eee; border-radius: 12px; padding: 12px; display:flex; gap:10px; align-items:center; }}
    .logo {{ width: 36px; height: 36px; object-fit: contain; background:#fff; border:1px solid #eee; border-radius:8px; }}
    .meta {{ line-height: 1.25; }}
    .name {{ font-weight: 600; }}
    .sub {{ color:#666; font-size: 12px; }}
  </style>
</head>
<body>
  <h1>TradingView Logos</h1>
  <input id="q" placeholder="Search by name, ticker, exchange, country…">
  <div class="grid" id="grid"></div>

  <script>
    const DATA = {json.dumps(rows, ensure_ascii=False)};
    const grid = document.getElementById('grid');
    const q = document.getElementById('q');

    function render(list) {{
      grid.innerHTML = '';
      for (const r of list) {{
        const div = document.createElement('div');
        div.className = 'card';
        div.innerHTML = `
          <img class="logo" src="${{r.logo}}" alt="${{r.ticker}} logo">
          <div class="meta">
            <div class="name">${{r.name || r.ticker}}</div>
            <div class="sub">${{r.exchange}} · ${{r.ticker}} · ${{r.country || ''}}</div>
          </div>
        `;
        grid.appendChild(div);
      }}
    }}
    function match(r, s) {{
      s = s.toLowerCase();
      return (r.name||'').toLowerCase().includes(s)
          || (r.ticker||'').toLowerCase().includes(s)
          || (r.exchange||'').toLowerCase().includes(s)
          || (r.country||'').toLowerCase().includes(s);
    }}
    q.addEventListener('input', () => {{
      const s = q.value.trim();
      if (!s) return render(DATA);
      render(DATA.filter(r => match(r, s)));
    }});
    render(DATA);
  </script>
</body>
</html>
"""
    OUT_HTML.write_text(html, encoding="utf-8")

async def main():
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    init_csv()

    connector = aiohttp.TCPConnector(limit=12)
    async with aiohttp.ClientSession(connector=connector, headers={
        "Accept": "text/html,application/json,*/*;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.tradingview.com",
        "Referer": "https://www.tradingview.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    }) as session:
        sem_global = asyncio.Semaphore(CONCURRENCY)

        # iterate all your links
        for group, urls in LINK_GROUPS.items():
            for url in urls:
                try:
                    await process_country_link(session, group, url, sem_global)
                except Exception as e:
                    print(f"!! Skipping {url} due to error: {e}")

    # build website manifest + demo html
    build_manifest_and_html()
    print("\n==> Done.")
    print(f"CSV  -> {OUT_CSV.resolve()}")
    print(f"JSON -> {OUT_JSON.resolve()}")
    print(f"HTML -> {OUT_HTML.resolve()}")
    print(f"Logos-> {BASE_DIR.resolve()}")

if __name__ == "__main__":
    asyncio.run(main())
