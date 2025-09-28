import asyncio
import os
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import aiohttp
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

START_URL = "https://in.tradingview.com/markets/stocks-usa/market-movers-all-stocks/"
OUT_DIR = Path("tv-logos")
CSV_OUT = Path("tv_us_logos_from_page.csv")
HEADLESS = True  # set False to watch it run

LOGO_IMG_SELECTOR = "img[src*='symbol-logo'], img[srcset*='symbol-logo']"

# letters/digits to iterate in the screener search box
QUERY_CHUNKS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")

def filename_from_url(url):
    return os.path.basename(urlparse(url).path).split("?")[0]

async def download_one(session, url, dest, tries=3, timeout=25):
    for i in range(tries):
        try:
            async with session.get(url, timeout=timeout) as r:
                if r.status == 200:
                    data = await r.read()
                    if data:
                        dest.write_bytes(data)
                        return True
        except Exception:
            pass
        await asyncio.sleep(1.0 * (i + 1))
    return False

async def accept_any_cookies(page):
    # best-effort cookie acceptance on the current page
    for sel in [
        "button[aria-label='Accept all']",
        "button:has-text('Accept')",
        "button:has-text('I agree')",
    ]:
        try:
            await page.locator(sel).first.click(timeout=1500)
            break
        except Exception:
            pass

async def find_screener_frame(page):
    # wait for iframes, then pick the one that shows symbol logos
    try:
        await page.wait_for_selector("iframe", timeout=60000)
    except PWTimeout:
        return None
    for _ in range(40):
        for fr in page.frames:
            try:
                if await fr.locator(LOGO_IMG_SELECTOR).count():
                    return fr
            except Exception:
                pass
        await asyncio.sleep(0.5)
    return None

async def find_search_input(frame):
    # Try common selectors the screener uses
    selectors = [
        "input[type=search]",
        "input[placeholder*='Search']",
        "input[aria-label*='Search']",
        "input[placeholder*='Symbol']",
        "input",  # fallback
    ]
    for sel in selectors:
        try:
            loc = frame.locator(sel).first
            if await loc.count():
                if await loc.is_visible():
                    return loc
        except Exception:
            pass
    return None

async def set_search_query(frame, query):
    # focus the search input, clear, type the query, press Enter
    inp = await find_search_input(frame)
    if not inp:
        return False
    try:
        await inp.click()
        # clear existing text (Ctrl+A / Delete)
        await inp.press("Control+A")
        await inp.press("Delete")
        await inp.type(query, delay=50)
        await inp.press("Enter")
        # small wait for results to refresh
        await asyncio.sleep(1.0)
        return True
    except Exception:
        return False

async def collect_logos_once(target, seen):
    # collect currently rendered logos from this view
    handles = await target.locator(LOGO_IMG_SELECTOR).element_handles()
    new_in_pass = 0
    for h in handles:
        src = await h.get_attribute("src")
        if not src:
            srcset = await h.get_attribute("srcset")
            if srcset:
                src = srcset.split(",")[0].strip().split(" ")[0]
        if not src:
            continue
        src = src.split("?")[0]
        name = filename_from_url(src)
        if not name:
            continue
        key = (src, name)
        if key not in seen:
            seen.add(key)
            new_in_pass += 1
    return new_in_pass

async def scroll_target(target, pixels=16000):
    # Try scrolling window; fallback to scrollingElement
    try:
        await target.evaluate("amt => window.scrollBy(0, amt)", pixels)
    except Exception:
        try:
            await target.evaluate("amt => document.scrollingElement && document.scrollingElement.scrollBy(0, amt)", pixels)
        except Exception:
            pass

async def harvest_for_query(frame, query, seen, passes=40, sleep_after_scroll=0.9):
    ok = await set_search_query(frame, query)
    if not ok:
        return 0
    # wait for at least one logo (new list)
    try:
        await frame.wait_for_selector(LOGO_IMG_SELECTOR, timeout=15000)
    except Exception:
        pass

    added_total = 0
    stable_rounds = 0
    for i in range(passes):
        # collect what's currently visible
        added = await collect_logos_once(frame, seen)
        added_total += added
        # scroll down within the iframe to load more
        await scroll_target(frame, 16000)
        await asyncio.sleep(sleep_after_scroll)
        if added == 0:
            stable_rounds += 1
        else:
            stable_rounds = 0
        # if several passes add nothing, likely exhausted for this query
        if stable_rounds >= 3:
            break
    return added_total

async def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=HEADLESS)
        context = await browser.new_context(viewport={"width": 1400, "height": 1000})
        page = await context.new_page()

        # Open the embed page
        await page.goto(START_URL, wait_until="domcontentloaded")
        await accept_any_cookies(page)

        # Find the screener iframe
        frame = await find_screener_frame(page)
        if not frame:
            print("Could not locate the screener iframe. Try HEADLESS=False and re-run.")
            await context.close(); await browser.close(); return

        # Ensure at least one logo is present to confirm we're in the right place
        await frame.wait_for_selector(LOGO_IMG_SELECTOR, timeout=60000)

        seen = set()
        total_before = 0

        # Iterate A..Z, then 0..9
        for q in QUERY_CHUNKS:
            added = await harvest_for_query(frame, q, seen, passes=50, sleep_after_scroll=1.0)
            total_now = len(seen)
            print(f"[query '{q}'] total logos: {total_now} (+{added})")
            # If nothing ever grows for many queries, likely blocked; you can slow down or watch in headful mode
            # brief pause between queries
            await asyncio.sleep(0.5)

        # Save CSV mapping
        records = [{"logo_url": u, "logo_file": n} for (u, n) in sorted(seen, key=lambda x: x[1])]
        pd.DataFrame(records).to_csv(CSV_OUT, index=False, encoding="utf-8")
        print(f"\nCollected {len(records)} unique logos. CSV -> {CSV_OUT.resolve()}")

        # Download all logos concurrently
        async with aiohttp.ClientSession() as session:
            sem = asyncio.Semaphore(10)
            async def task(rec):
                dest = OUT_DIR / rec["logo_file"]
                if dest.exists():
                    return True
                async with sem:
                    ok = await download_one(session, rec["logo_url"], dest)
                print(("Saved " if ok else "Failed ") + rec["logo_file"])
                return ok

            results = await asyncio.gather(*[task(r) for r in records])

        ok = sum(1 for r in results if r)
        fail = len(results) - ok
        print(f"Done. Saved={ok}, Failed={fail}, Folder={OUT_DIR.resolve()}")

        await context.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
