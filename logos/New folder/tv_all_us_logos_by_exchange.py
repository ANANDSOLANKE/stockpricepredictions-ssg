# --- Windows asyncio fix (hides "Event loop is closed" noise) ---
import sys, asyncio
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import os, re
from pathlib import Path
from urllib.parse import urlparse
import aiohttp
import pandas as pd

# ========= SETTINGS =========
OUT_DIR = Path("tv-logos")
CSV_OUT = Path("tv_us_logos_by_exchange.csv")

# Add/remove exchanges as you like.
# Tip: start with listed (NASDAQ, NYSE, AMEX) before adding OTC & CBOE (huge).
EXCHANGES = [
    "NASDAQ", "NYSE", "AMEX", "OTC", "CBOE"  # "NYSEARCA" is mostly ETFs; add if needed
]

STEP = 500            # rows per request (TV caps ~500 per call)
CONCURRENCY = 8       # lower if you see 429/403

SCAN_URL = "https://scanner.tradingview.com/america/scan"
SYMBOL_PAGE = "https://in.tradingview.com/symbols/{exchange}-{ticker}/"
LOGO_RE = re.compile(r"https://s3-symbol-logo\.tradingview\.com/[^\"'\s>]+?\.(?:svg|png)")

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

async def fetch_symbols_for_exchange(session, exchange):
    """
    Page through one exchange and return [(EX, TICKER), ...].
    IMPORTANT: we advance offset by len(rows) (not STEP) and stop only when rows == 0.
    """
    symbols = []
    offset = 0
    page_idx = 0
    while True:
        page_idx += 1
        payload = {
            "filter": [
                {"left": "exchange", "operation": "equal", "right": exchange},
                # If you want ONLY common equities, uncomment the next line:
                # {"left": "typespecs", "operation": "in_range", "right": ["common"]},
            ],
            "options": {"lang": "en"},
            "symbols": {"query": {"types": []}, "tickers": []},
            "columns": ["name"],
            "sort": {"sortBy": "name", "sortOrder": "asc"},
            "range": [offset, offset + STEP - 1],  # inclusive range
        }
        data = await fetch_json(session, SCAN_URL, payload)
        rows = data.get("data") or []
        if not rows:
            break

        for row in rows:
            s = row.get("s") or ""
            if ":" in s:
                ex, tk = s.split(":", 1)
                symbols.append((ex.strip().upper(), tk.strip().upper()))

        got = len(rows)
        # progress log
        print(f"  {exchange}: page {page_idx} -> {got} rows (offset {offset})")
        # advance by what we actually received
        offset += got

        # DO NOT stop just because got < STEP — TV sometimes returns 499
        # We stop only when the next request returns 0 rows.

    # de-dup in case TV returns overlaps
    return sorted(set(symbols))

async def discover_logo_for_symbol(session, exchange, ticker):
    url = SYMBOL_PAGE.format(exchange=exchange, ticker=ticker)
    html = await fetch_text(session, url)
    if not html:
        return None, None, url
    m = LOGO_RE.search(html)
    if not m:
        return None, None, url
    logo_url = m.group(0)
    return logo_url, filename_from_url(logo_url), url

async def download_one(session, url, dest: Path, tries=3):
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

async def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    connector = aiohttp.TCPConnector(limit=CONCURRENCY)
    async with aiohttp.ClientSession(connector=connector, headers={
        "Accept": "text/html,application/json,*/*;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://in.tradingview.com",
        "Referer": "https://in.tradingview.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }) as session:

        # 1) Gather symbols per exchange WITH REAL PAGINATION
        all_symbols = []
        for ex in EXCHANGES:
            print(f"Fetching symbols for {ex} …")
            syms = await fetch_symbols_for_exchange(session, ex)
            print(f"  {ex}: {len(syms)} symbols (after pagination)")
            all_symbols.extend(syms)

        # de-dup across exchanges
        all_symbols = sorted(set(all_symbols))
        print(f"Total unique symbols: {len(all_symbols)}")

        # 2) Discover logos
        records = []
        sem = asyncio.Semaphore(CONCURRENCY)

        async def work(ex, tk):
            async with sem:
                logo_url, logo_file, sym_url = await discover_logo_for_symbol(session, ex, tk)
                records.append({
                    "exchange": ex,
                    "ticker": tk,
                    "symbol_url": sym_url,
                    "logo_url": logo_url or "",
                    "logo_file": logo_file or "",
                })

        await asyncio.gather(*[work(ex, tk) for ex, tk in all_symbols])

        df = pd.DataFrame(records)
        df.to_csv(CSV_OUT, index=False, encoding="utf-8")
        print(f"Saved mapping -> {CSV_OUT.resolve()}")

        # 3) Download logos
        found = [r for r in records if r["logo_url"]]
        print(f"Downloading {len(found)} logos …")

        async def dl(rec):
            dest = OUT_DIR / rec["logo_file"]
            if dest.exists():
                return True
            return await download_one(session, rec["logo_url"], dest)

        oks = await asyncio.gather(*[dl(r) for r in found])
        ok = sum(1 for x in oks if x)
        fail = len(found) - ok
        print(f"Done. Saved={ok}, Failed={fail}, Folder={OUT_DIR.resolve()}")

if __name__ == "__main__":
    asyncio.run(main())
