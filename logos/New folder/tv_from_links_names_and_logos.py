# --- Windows asyncio fix (hides "Event loop is closed" warnings) ---
import sys, asyncio
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import os, re, csv, json
from pathlib import Path
from urllib.parse import urlparse
import aiohttp
import pandas as pd

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

# Country slug -> exchange codes (you can tweak as you wish)
PAGE_EXCHANGES = {
    "usa": ["NASDAQ","NYSE","NYSEARCA","OTC","CBOE"],
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
    "thailand": ["SET"],
    "taiwan": ["TWSE","TPEX"],
    "vietnam": ["HOSE","HNX","UPCOM"],
}

# slug -> nice country name for 'country' filter (used on fallback datasets)
COUNTRY_NAME = {
    "usa": "United States", "canada": "Canada",
    "austria": "Austria","italy":"Italy","belgium":"Belgium","lithuania":"Lithuania",
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

# Which dataset(s) to try per group/country; if 404, we fall back to 'america'
GROUP_DATASETS = {
    "North America": ["america"],
    "Europe": ["europe","america"],
    "Middle East - Africa": ["middle_east","africa","america"],
    "Mexico - South America": ["america","brazil","mexico"],
    "Asia - Pacific": ["asia","australia","america"],
}

# ========= OUTPUT LAYOUT =========
BASE_DIR = Path("tv-logos")  # base folder
CSV_OUT = Path("tv_from_links_names_and_logos.csv")

# ========= LOGO + NAME PARSERS =========
OG_IMG_RE = re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https://s3-symbol-logo\.tradingview\.com/[^"\']+\.(?:svg|png))["\']', re.I)
TW_IMG_RE = re.compile(r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\'](https://s3-symbol-logo\.tradingview\.com/[^"\']+\.(?:svg|png))["\']', re.I)
JSONLD_LOGO_RE = re.compile(r'"logo"\s*:\s*"(?P<url>https://s3-symbol-logo\.tradingview\.com/[^"]+\.(?:svg|png))"', re.I)
ALL_LOGOS_RE = re.compile(r"https://s3-symbol-logo\.tradingview\.com/([a-z0-9\-]+)\.(svg|png)", re.I)

JSONLD_NAME_RE = re.compile(r'"@type"\s*:\s*"Organization"[^}]*?"name"\s*:\s*"([^"]+)"', re.I)
OG_TITLE_RE  = re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', re.I)
TITLE_RE     = re.compile(r"<title>([^<]+)</title>", re.I)

EXCHANGE_BADGES = {
    "nasdaq","nyse","amex","nysearca","cboe","otc",
    "tsx","tsx-venture","tmx","lse","euronext","xetra",
    "bse","nse","asx","hkex","tse","szse","sse","kospi",
    "bovespa","bmv","jse","six","sgx","tadawul","nzx","idx","bist",
    "bme","bvb","bolsa-madrid","gettex","tradegate","ls","lsx","ose","osl","euronextams","euronextpar",
}

def filename_from_url(url: str) -> str:
    from urllib.parse import urlparse
    name = os.path.basename(urlparse(url).path)
    return name.split("?")[0]

def is_exchange_slug(slug: str, exchange: str) -> bool:
    s = slug.lower()
    ex = (exchange or "").lower()
    return s in EXCHANGE_BADGES or s == ex

def pick_company_logo_from_html(html: str, exchange: str):
    for rx in (OG_IMG_RE, TW_IMG_RE, JSONLD_LOGO_RE):
        m = rx.search(html)
        if m:
            url = m.group(1) if m.re is not JSONLD_LOGO_RE else m.group("url")
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

# ========= HTTP HELPERS =========
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

async def discover_logo_and_name(session, exchange, ticker, fallback_name=""):
    symbol_url = f"https://www.tradingview.com/symbols/{exchange}-{ticker}/"
    html = await fetch_text(session, symbol_url)
    if not html: return None, None, symbol_url, fallback_name or ""
    logo_url = pick_company_logo_from_html(html, exchange)
    name = extract_company_name(html, ticker, fallback_name or "")
    return logo_url, filename_from_url(logo_url) if logo_url else None, symbol_url, name

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

# ========= SCAN HELPERS =========
STEP = 500
def country_from_slug(slug: str): return COUNTRY_NAME.get(slug, None)

def slug_from_url(url: str):
    # .../markets/stocks-<slug>/market-movers...
    try:
        parts = url.strip("/").split("/")
        for p in parts:
            if p.startswith("stocks-"):
                return p.replace("stocks-","")
    except Exception:
        pass
    return None

def datasets_for_group(group_name: str):
    return GROUP_DATASETS.get(group_name, ["america"])

async def fetch_symbols_for_exchange(session, dataset: str, slug: str, exchange: str):
    """
    Pull EXCHANGE symbols from a dataset. If dataset isn't available in your region,
    the caller should catch 404 and try a fallback dataset.
    """
    endpoint = f"https://scanner.tradingview.com/{dataset}/scan"
    symbols = []
    offset = 0
    page = 0
    filters = [{"left": "exchange", "operation": "equal", "right": exchange},
               {"left": "type", "operation": "in_range", "right": ["stock"]}]
    # On cross-dataset fallback we also pass a country condition when we know it
    cn = country_from_slug(slug)
    if cn:
        filters.append({"left": "country", "operation": "equal", "right": cn})

    while True:
        page += 1
        payload = {
            "filter": filters,
            "options": {"lang": "en"},
            "symbols": {"query": {"types": []}, "tickers": []},
            "columns": ["name"],
            "sort": {"sortBy": "name", "sortOrder": "asc"},
            "range": [offset, offset + STEP - 1],
        }
        data = await fetch_json(session, endpoint, payload)
        rows = data.get("data") or []
        if not rows: break
        got = len(rows)
        for row in rows:
            s = row.get("s") or ""
            nm = ""
            try: nm = (row.get("d") or [""])[0] or ""
            except Exception: pass
            if ":" in s:
                ex, tk = s.split(":", 1)
                symbols.append((ex.strip().upper(), tk.strip().upper(), nm))
        print(f"    {dataset}/{slug}/{exchange}: page {page} -> {got} rows (offset {offset})")
        offset += got
    # de-dup keep first name
    ded = {}
    for ex, tk, nm in symbols:
        ded.setdefault((ex, tk), nm)
    return [(ex, tk, ded[(ex, tk)]) for (ex, tk) in sorted(ded.keys())]

# ========= PIPELINE =========
def dest_dir_for(country_slug: str, exchange: str):
    return BASE_DIR / country_slug / exchange

def init_csv():
    if not CSV_OUT.exists():
        with CSV_OUT.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(
                ["group","country_slug","country_name","exchange","ticker","company_name",
                 "symbol_url","logo_url","logo_file","logo_relpath"]
            )

async def process_country_link(session, group: str, url: str):
    slug = slug_from_url(url)
    if not slug:
        print(f"!! Skipping unknown url format: {url}")
        return

    country_exchanges = PAGE_EXCHANGES.get(slug, [])
    if not country_exchanges:
        print(f"!! No exchanges configured for slug '{slug}' -> {url}")
        return

    datasets = datasets_for_group(group)
    print(f"\n==> {group} | {slug} | exchanges: {country_exchanges} | datasets: {datasets}")

    # gather all symbols for this country by exchange with dataset fallbacks
    all_syms = []
    for ex in country_exchanges:
        syms = None
        last_err = None
        for ds in datasets:
            try:
                syms = await fetch_symbols_for_exchange(session, ds, slug, ex)
                if syms: break
            except aiohttp.ClientResponseError as e:
                last_err = e
                continue
            except Exception as e:
                last_err = e
                continue
        if syms is None:
            print(f"  !! Failed to list {slug}/{ex} due to {last_err}")
            continue
        print(f"  Listed {len(syms)} for {slug}/{ex}")
        all_syms.extend([(slug, *row) for row in syms])  # (slug, EX, TK, name)

    # resume: read existing rows to skip downloaded
    done = set()
    if CSV_OUT.exists():
        try:
            df_done = pd.read_csv(CSV_OUT, usecols=["country_slug","exchange","ticker"])
            for _, r in df_done.iterrows():
                done.add((str(r["country_slug"]), str(r["exchange"]), str(r["ticker"])))
        except Exception:
            pass

    sem = asyncio.Semaphore(8)
    lock = asyncio.Lock()

    async def worker(country_slug, ex, tk, nm):
        if (country_slug, ex, tk) in done:
            return
        async with sem:
            logo_url, logo_file, sym_url, disp_name = await discover_logo_and_name(session, ex, tk, nm)
            # save immediately
            relpath = ""
            if logo_url and logo_file:
                folder = dest_dir_for(country_slug, ex)
                folder.mkdir(parents=True, exist_ok=True)
                dest = folder / logo_file
                relpath = str(Path(country_slug) / ex / logo_file)
                if not dest.exists():
                    ok = await download_logo(session, logo_url, dest)
                    if ok:
                        print(f"[{country_slug} | {ex}] Saved {logo_file}")
            async with lock:
                with CSV_OUT.open("a", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow([
                        group, country_slug, country_from_slug(country_slug) or "",
                        ex, tk, disp_name, sym_url, logo_url or "", logo_file or "", relpath
                    ])

    await asyncio.gather(*[worker(slug, ex, tk, nm) for (slug, ex, tk, nm) in all_syms])

async def main():
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    init_csv()

    connector = aiohttp.TCPConnector(limit=12)
    async with aiohttp.ClientSession(connector=connector, headers={
        "Accept": "text/html,application/json,*/*;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.tradingview.com",
        "Referer": "https://www.tradingview.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }) as session:
        # iterate your groups/links
        for group, urls in LINK_GROUPS.items():
            for url in urls:
                try:
                    await process_country_link(session, group, url)
                except Exception as e:
                    print(f"!! Skipping {url} due to error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
