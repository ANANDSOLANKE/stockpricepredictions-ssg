# --- Windows asyncio fix (hides "Event loop is closed" warnings) ---
import sys, asyncio
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import os, re, csv
from pathlib import Path
from urllib.parse import urlparse
import aiohttp
import pandas as pd

# ========= SETTINGS =========
OUT_DIR = Path("tv-logos")                               # base folder for logos
CSV_OUT = Path("tv_world_logos_regions_streaming.csv")   # append/resume mapping CSV

# Choose how to organize files:
#   "exchange" -> tv-logos/NASDAQ/..., tv-logos/NYSE/...
#   "region"   -> tv-logos/america/..., tv-logos/europe/...
#   "region_exchange" -> tv-logos/america/NASDAQ/...
#   "flat"     -> all files directly in tv-logos/
FOLDER_SCHEME = "exchange"

# Valid TradingView scanner regions
REGIONS = ["america", "europe", "asia", "oceania", "middle_east", "africa"]

STEP = 500            # rows per scanner request (TV caps ~500)
CONCURRENCY = 8       # lower to 4 if you hit HTTP 429/403

SYMBOL_PAGE = "https://www.tradingview.com/symbols/{exchange}-{ticker}/"

# Prefer meta tags / JSON-LD first (more accurate), then fallback to any s3-symbol-logo
OG_IMG_RE = re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https://s3-symbol-logo\.tradingview\.com/[^"\']+\.(?:svg|png))["\']', re.I)
TW_IMG_RE = re.compile(r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\'](https://s3-symbol-logo\.tradingview\.com/[^"\']+\.(?:svg|png))["\']', re.I)
JSONLD_LOGO_RE = re.compile(r'"logo"\s*:\s*"(?P<url>https://s3-symbol-logo\.tradingview\.com/[^"]+\.(?:svg|png))"', re.I)
ALL_LOGOS_RE = re.compile(r"https://s3-symbol-logo\.tradingview\.com/([a-z0-9\-]+)\.(svg|png)", re.I)

# Common exchange badge filenames to ignore (extend if you spot more)
EXCHANGE_LOGO_BLOCKLIST = {
    "nasdaq", "nyse", "amex", "nysearca", "cboe", "otc",
    "tsx", "tsx-venture", "tmx", "lse", "euronext", "xetra",
    "bse", "nse", "asx", "hkex", "tse", "szse", "sse", "kospi",
    "bovespa", "bmv", "jse", "six", "sgx", "tadawul",
    "nzx", "idx", "bist", "bme", "bvb", "bolsa-madrid"
}

def filename_from_url(url: str) -> str:
    name = os.path.basename(urlparse(url).path)
    return name.split("?")[0]

def is_exchange_slug(slug: str, exchange: str) -> bool:
    s = slug.lower()
    ex = (exchange or "").lower()
    if s in EXCHANGE_LOGO_BLOCKLIST:
        return True
    # exact exchange name (e.g., "nasdaq", "nyse", "otc")
    if s == ex:
        return True
    return False

def build_dest_dir(base: Path, region: str, exchange: str) -> Path:
    if FOLDER_SCHEME == "exchange":
        return base / (exchange or "UNKNOWN")
    elif FOLDER_SCHEME == "region":
        return base / (region or "unknown-region")
    elif FOLDER_SCHEME == "region_exchange":
        return base / (region or "unknown-region") / (exchange or "UNKNOWN")
    else:
        return base

async def fetch_json(session, url, payload):
    async with session.post(url, json=payload, timeout=45) as r:
        r.raise_for_status()
        return await r.json()

async def fetch_text(session, url):
    async with session.get(url, timeout=45) as r:
        if r.status != 200:
            return ""
        return await r.text()

async def fetch_symbols_for_region(session, region):
    """
    Scan a region endpoint and return list of (EXCHANGE, TICKER).
    Advance 'offset' by len(rows) until zero rows are returned.
    """
    symbols = []
    offset = 0
    page_idx = 0
    endpoint = f"https://scanner.tradingview.com/{region}/scan"

    while True:
        page_idx += 1
        payload = {
            "filter": [
                {"left": "type", "operation": "in_range", "right": ["stock"]},  # stocks only
            ],
            "options": {"lang": "en"},
            "symbols": {"query": {"types": []}, "tickers": []},
            "columns": ["name"],  # minimal columns; 's' (EX:TK) is in each row
            "sort": {"sortBy": "name", "sortOrder": "asc"},
            "range": [offset, offset + STEP - 1],  # inclusive
        }

        data = await fetch_json(session, endpoint, payload)
        rows = data.get("data") or []
        if not rows:
            break

        got = len(rows)
        for row in rows:
            s = row.get("s") or ""
            if ":" in s:
                ex, tk = s.split(":", 1)
                symbols.append((ex.strip().upper(), tk.strip().upper()))

        print(f"  {region}: page {page_idx} -> {got} rows (offset {offset})")
        offset += got

    # de-dup within region
    return sorted(set(symbols))

def pick_company_logo_from_html(html: str, exchange: str):
    """
    Prefer meta og:image / twitter:image / JSON-LD "logo".
    Fall back to the first ALL_LOGOS_RE match that is NOT an exchange badge.
    Return url or None.
    """
    # 1) og:image
    m = OG_IMG_RE.search(html)
    if m:
        url = m.group(1)
        slug_m = ALL_LOGOS_RE.search(url)
        if slug_m:
            slug = slug_m.group(1).lower()
            if not is_exchange_slug(slug, exchange):
                return url

    # 2) twitter:image
    m = TW_IMG_RE.search(html)
    if m:
        url = m.group(1)
        slug_m = ALL_LOGOS_RE.search(url)
        if slug_m:
            slug = slug_m.group(1).lower()
            if not is_exchange_slug(slug, exchange):
                return url

    # 3) JSON-LD "logo"
    m = JSONLD_LOGO_RE.search(html)
    if m:
        url = m.group("url")
        slug_m = ALL_LOGOS_RE.search(url)
        if slug_m:
            slug = slug_m.group(1).lower()
            if not is_exchange_slug(slug, exchange):
                return url

    # 4) any s3 symbol-logo on page, skipping exchange badges
    matches = list(ALL_LOGOS_RE.finditer(html))
    for mm in matches:
        slug = mm.group(1).lower()
        if not is_exchange_slug(slug, exchange):
            return mm.group(0)

    return None

async def discover_logo_for_symbol(session, exchange, ticker):
    """
    Open the symbol page and select the first non-exchange s3-symbol-logo.
    If only exchange badges exist, return (None, None, url).
    """
    url = SYMBOL_PAGE.format(exchange=exchange, ticker=ticker)
    html = await fetch_text(session, url)
    if not html:
        return None, None, url

    logo_url = pick_company_logo_from_html(html, exchange)
    if not logo_url:
        return None, None, url

    return logo_url, filename_from_url(logo_url), url

async def download_logo(session, url, dest: Path, tries=3):
    last = None
    for i in range(tries):
        try:
            async with session.get(url, timeout=45) as r:
                if r.status == 200:
                    data = await r.read()
                    if data:
                        dest.write_bytes(data)
                        return True
                last = f"HTTP {r.status}"
        except Exception as e:
            last = str(e)
        await asyncio.sleep(1.0 * (i + 1))
    print(f"  ! Failed {url}: {last}")
    return False

def init_csv(path: Path):
    if not path.exists():
        with path.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["region", "exchange", "ticker", "symbol_url", "logo_url", "logo_file"])

async def process_region(session, region):
    """Fetch symbols in one region, then stream logo discovery + download."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    init_csv(CSV_OUT)

    # Pull all symbols for this region
    syms = await fetch_symbols_for_region(session, region)
    print(f"{region}: {len(syms)} symbols after pagination")

    # Resume: skip tickers already written for this region
    done_keys = set()
    if CSV_OUT.exists():
        try:
            df_done = pd.read_csv(CSV_OUT, usecols=["region", "exchange", "ticker"])
            for _, r in df_done[df_done["region"] == region].iterrows():
                done_keys.add((r["exchange"], r["ticker"]))
        except Exception:
            pass

    sem = asyncio.Semaphore(CONCURRENCY)
    lock = asyncio.Lock()  # guard CSV appends

    async def worker(ex, tk):
        if (ex, tk) in done_keys:
            return
        async with sem:
            logo_url, logo_file, sym_url = await discover_logo_for_symbol(session, ex, tk)

            # append to CSV immediately (resume-friendly)
            async with lock:
                with CSV_OUT.open("a", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow([region, ex, tk, sym_url, logo_url or "", logo_file or ""])

            # download if found & not already present
            if logo_url and logo_file:
                dest_dir = build_dest_dir(OUT_DIR, region, ex)
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / logo_file
                if not dest.exists():
                    ok = await download_logo(session, logo_url, dest)
                    if ok:
                        print(f"[{region} | {ex}] Saved {logo_file}")

    await asyncio.gather(*[worker(ex, tk) for ex, tk in syms])

async def main():
    connector = aiohttp.TCPConnector(limit=CONCURRENCY)
    async with aiohttp.ClientSession(connector=connector, headers={
        "Accept": "text/html,application/json,*/*;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.tradingview.com",
        "Referer": "https://www.tradingview.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }) as session:

        for region in REGIONS:
            print(f"=== Processing {region.upper()} ===")
            try:
                await process_region(session, region)
            except Exception as e:
                print(f"  ! Skipping {region} due to error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
