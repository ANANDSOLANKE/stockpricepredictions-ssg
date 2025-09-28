import asyncio
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
import pandas as pd

# -------- Settings --------
OUT_DIR = Path("tv-logos")
CSV_OUT = Path("tv_us_logos_from_pages.csv")
COUNTRY = "United States"   # set to None to fetch all Americas
STEP = 500                  # page size per screener call
CONCURRENCY = 12            # concurrent HTTP requests

SCAN_URL = "https://scanner.tradingview.com/america/scan"
SYMBOL_PAGE = "https://in.tradingview.com/symbols/{exchange}-{ticker}/"
LOGO_RE = re.compile(r"https://s3-symbol-logo\.tradingview\.com/[^\"'\s>]+?\.(?:svg|png)")

# -------- Helpers --------
def filename_from_url(url: str) -> str:
    name = os.path.basename(urlparse(url).path)
    return name.split("?")[0]

async def fetch_json(session, url, payload):
    async with session.post(url, json=payload, timeout=45) as r:
        r.raise_for_status()
        return await r.json()

async def fetch_text(session, url):
    async with session.get(url, timeout=45) as r:
        if r.status != 200:
            return ""
        return await r.text()

async def fetch_symbols_us(session):
    """Pull all US stock symbols from TradingView screener by paging 'range'."""
    symbols = []
    offset = 0

    # Filters: only US stocks (COUNTRY) if set
    filters = []
    if COUNTRY:
        filters.append({"left": "country", "operation": "equal", "right": COUNTRY})
    # Ensure it's a stock (avoid funds/forex etc.); if this hides some desired types, remove it
    filters.append({"left": "type", "operation": "in_range", "right": ["stock"]})

    while True:
        payload = {
            "filter": filters,
            "options": {"lang": "en"},
            "symbols": {"query": {"types": []}, "tickers": []},
            # 's' field (EXCHANGE:SYMBOL) is always present; columns can be light
            "columns": ["name"],
            "sort": {"sortBy": "name", "sortOrder": "asc"},
            "range": [offset, offset + STEP - 1],
        }
        data = await fetch_json(session, SCAN_URL, payload)
        rows = data.get("data") or []
        if not rows:
            break
        for row in rows:
            s = row.get("s") or ""
            if ":" not in s:
                continue
            ex, tk = s.split(":", 1)
            symbols.append((ex.strip().upper(), tk.strip().upper()))
        if len(rows) < STEP:
            break
        offset += STEP
    return symbols

async def discover_logo_for_symbol(session, exchange, ticker):
    """Fetch symbol page and extract the first symbol-logo URL."""
    url = SYMBOL_PAGE.format(exchange=exchange, ticker=ticker)
    html = await fetch_text(session, url)
    if not html:
        return None, None, url
    m = LOGO_RE.search(html)
    if not m:
        return None, None, url
    logo_url = m.group(0)
    logo_file = filename_from_url(logo_url)
    return logo_url, logo_file, url

async def download_one(session, url, dest: Path, tries=3):
    last_err = None
    for i in range(tries):
        try:
            async with session.get(url, timeout=45) as r:
                if r.status == 200:
                    data = await r.read()
                    if data:
                        dest.write_bytes(data)
                        return True
                last_err = f"HTTP {r.status}"
        except Exception as e:
            last_err = str(e)
        await asyncio.sleep(1.0 * (i + 1))
    print(f"  ! Failed {url}: {last_err}")
    return False

async def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    connector = aiohttp.TCPConnector(limit=CONCURRENCY)
    async with aiohttp.ClientSession(connector=connector, headers={
        # lightweight headers to look like a browser
        "Accept": "text/html,application/json,*/*;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://in.tradingview.com",
        "Referer": "https://in.tradingview.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }) as session:

        print("Fetching U.S. symbols from TradingView…")
        symbols = await fetch_symbols_us(session)
        print(f"Found {len(symbols)} symbols.")

        # Discover logo URLs by scraping each symbol page
        results = []
        sem = asyncio.Semaphore(CONCURRENCY)

        async def work(ex, tk):
            async with sem:
                logo_url, logo_file, sym_url = await discover_logo_for_symbol(session, ex, tk)
                results.append({
                    "exchange": ex,
                    "ticker": tk,
                    "symbol_url": sym_url,
                    "logo_url": logo_url or "",
                    "logo_file": logo_file or "",
                })

        await asyncio.gather(*[work(ex, tk) for ex, tk in symbols])

        # Save CSV mapping
        df = pd.DataFrame(results)
        df.to_csv(CSV_OUT, index=False, encoding="utf-8")
        print(f"Saved mapping -> {CSV_OUT.resolve()}")

        # Download all discovered logos
        discovered = [r for r in results if r["logo_url"]]
        print(f"Downloading {len(discovered)} logos…")

        async def dl(rec):
            dest = OUT_DIR / rec["logo_file"]
            if dest.exists():
                return True
            return await download_one(session, rec["logo_url"], dest)

        oks = await asyncio.gather(*[dl(r) for r in discovered])
        ok = sum(1 for x in oks if x)
        fail = len(discovered) - ok
        print(f"Done. Saved={ok}, Failed={fail}, Folder={OUT_DIR.resolve()}")

if __name__ == "__main__":
    asyncio.run(main())
