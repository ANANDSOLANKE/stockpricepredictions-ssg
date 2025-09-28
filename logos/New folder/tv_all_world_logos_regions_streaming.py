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
OUT_DIR = Path("tv-logos")
CSV_OUT = Path("tv_world_logos_regions_streaming.csv")

# Valid TradingView scanner regions (use these, not "world")
REGIONS = ["america", "europe", "asia", "oceania", "middle_east", "africa"]

STEP = 500            # rows per scanner request (TV caps ~500)
CONCURRENCY = 8       # lower to 4 if you hit HTTP 429/403

LOGO_RE = re.compile(r"https://s3-symbol-logo\.tradingview\.com/[^\"'\s>]+?\.(?:svg|png)")
SYMBOL_PAGE = "https://www.tradingview.com/symbols/{exchange}-{ticker}/"

def filename_from_url(url: str) -> str:
    name = os.path.basename(urlparse(url).path)
    return name.split("?")[0]

async def fetch_json(session, url, payload):
    async with session.post(url, json=payload, timeout=45) as r:
        # TV returns 404 for non-existent regions; we handle that above by using only valid ones
        r.raise_for_status()
        return await r.json()

async def fetch_text(session, url):
    async with session.get(url, timeout=45) as r:
        if r.status != 200:
            return ""
        return await r.text()

async def fetch_symbols_for_region(session, region):
    """
    Scan a region endpoint and return list of "EXCHANGE:TICKER" strings.
    We advance 'offset' by len(rows) until zero rows are returned.
    """
    symbols = []
    offset = 0
    page_idx = 0
    endpoint = f"https://scanner.tradingview.com/{region}/scan"

    while True:
        page_idx += 1
        payload = {
            "filter": [
                {"left": "type", "operation": "in_range", "right": ["stock"]},
            ],
            "options": {"lang": "en"},
            "symbols": {"query": {"types": []}, "tickers": []},
            "columns": ["name"],  # minimal columns; 's' (EX:TK) is always included
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

async def discover_logo_for_symbol(session, exchange, ticker):
    """Open the symbol page and extract the TradingView s3 symbol-logo URL."""
    url = SYMBOL_PAGE.format(exchange=exchange, ticker=ticker)
    html = await fetch_text(session, url)
    if not html:
        return None, None, url
    m = LOGO_RE.search(html)
    if not m:
        return None, None, url
    logo_url = m.group(0)
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

    # Resume: skip symbols already written for this region
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

            # append CSV row immediately (resume-friendly)
            async with lock:
                with CSV_OUT.open("a", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow([region, ex, tk, sym_url, logo_url or "", logo_file or ""])

            # download if found & not already present
            if logo_url and logo_file:
                dest = OUT_DIR / logo_file
                if not dest.exists():
                    ok = await download_logo(session, logo_url, dest)
                    if ok:
                        print(f"[{region}] Saved {logo_file}")

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
