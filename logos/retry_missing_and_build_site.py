# --- Windows asyncio fix ---
import sys, asyncio
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import csv, os, re, json, string, random, time, html as htmllib
from pathlib import Path
from typing import Optional
import aiohttp

# =================== CONFIG ===================
ROOT = Path(r"C:\Users\USER\Desktop\project share")
CSV_PATH = ROOT / "tv_from_links_names_and_logos.csv"
BASE_DIR = ROOT / "tv-logos"             # folder where logos live
BASE_WEB_PATH = "tv-logos"               # how your site serves the logos

# Only retry / (re)discover these countries (lowercase slugs).
TARGET_COUNTRIES = {"russia", "sri-lanka"}   # set() to process ALL countries

CONCURRENCY = 2            # keep low to avoid throttling
TIMEOUT_TOTAL = 18         # per HTTP call
TIMEOUT_CONNECT = 8
TIMEOUT_SOCK_READ = 8

# progress verbosity
LOG_EVERY = 10             # print a line every N processed
JITTER_MIN = 0.25
JITTER_MAX = 0.65

# Outputs (rebuilt every run)
OUT_JSON = ROOT / "tv_logos_manifest.json"
OUT_HTML = ROOT / "tv_logos_index.html"
FAIL_LOG = ROOT / "tv_symbol_fetch_fail.log"

# Country name used by scanner "country" filter
COUNTRY_NAME = {
    "russia": "Russia",
    "sri-lanka": "Sri Lanka",
}

# For symbol-search fallback, try these exchange codes
EXCHANGE_HINTS = {
    "russia":   ["MOEX", "SPB", "SPBX"],   # broad net for Russian listings
    "sri-lanka":["CSELK"],                 # Colombo Stock Exchange
}

# Datasets to try for scanner discovery (best-first per country)
DATASETS_FOR = {
    "russia":   ["russia", "europe", "america"],
    "sri-lanka":["sri-lanka", "asia", "america"],
}

# Group label to write in CSV (cosmetic)
GROUP_FOR = {
    "russia": "Europe",
    "sri-lanka": "Asia - Pacific",
}

# =============== Parsers / cleaners ===============
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
    "euronextams","euronextpar","moex","cselk","spb","spbx"
}

TAG_RE = re.compile(r"<[^>]+>")
ALLOWED_TK = re.compile(r"[^A-Za-z0-9.\-]")  # keep letters, digits, dot, dash
ALLOWED_EX = re.compile(r"[^A-Za-z0-9]")     # exchanges: letters/digits only

def is_exchange_slug(slug: str, exchange: str) -> bool:
    s = slug.lower(); ex = (exchange or "").lower()
    return s in EXCHANGE_BADGES or s == ex

def filename_from_url(url: str) -> str:
    return os.path.basename(url.split("?",1)[0])

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

def to_web_path(p: Path) -> str:
    return str(p).replace("\\","/")

def clean_ticker(t: str) -> str:
    t = htmllib.unescape(t or "")
    t = TAG_RE.sub("", t)
    t = ALLOWED_TK.sub("", t)
    return t.upper()

def clean_exchange(ex: str) -> str:
    ex = htmllib.unescape(ex or "")
    ex = TAG_RE.sub("", ex)
    ex = ALLOWED_EX.sub("", ex)
    return ex.upper()

# ================= HTTP / Scanner / Search =================
STEP = 500

ASYM_HOSTS = ["https://www.tradingview.com", "https://in.tradingview.com"]
ASYM_PATHS = ["/symbols/{ex}-{tk}/", "/symbols/{ex}-{tk}/overview/"]

def tjitter():
    return JITTER_MIN + random.random()*(JITTER_MAX - JITTER_MIN)

async def fetch_symbol_html(session, exchange: str, ticker: str) -> str:
    """Try multiple hosts/paths for a symbol page, log failures with status, be chatty."""
    ex = clean_exchange(exchange)
    tk = clean_ticker(ticker)
    last_status = None
    for host in ASYM_HOSTS:
        for path in ASYM_PATHS:
            if not tk: continue
            url = f"{host}{path.format(ex=ex, tk=tk)}"
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(
                    total=TIMEOUT_TOTAL, connect=TIMEOUT_CONNECT, sock_read=TIMEOUT_SOCK_READ
                )) as r:
                    if r.status == 200:
                        return await r.text()
                    last_status = r.status
            except Exception as e:
                last_status = str(e)
            await asyncio.sleep(tjitter())
    with FAIL_LOG.open("a", encoding="utf-8") as fl:
        fl.write(f"{ex},{tk},{last_status}\n")
    return ""

async def post_json(session, url, payload):
    async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(
        total=TIMEOUT_TOTAL, connect=TIMEOUT_CONNECT, sock_read=TIMEOUT_SOCK_READ
    )) as r:
        if r.status == 404:
            raise aiohttp.ClientResponseError(r.request_info, r.history, status=404, message="Not Found")
        r.raise_for_status()
        return await r.json()

async def scanner_discover(session, slug: str):
    """Try to list (exchange, ticker, name) by country via scanner endpoints."""
    cn = COUNTRY_NAME.get(slug)
    if not cn:
        return []
    datasets = DATASETS_FOR.get(slug, [slug, "america"])
    symbols = []
    for ds in datasets:
        endpoint = f"https://scanner.tradingview.com/{ds}/scan"
        offset = 0
        page = 0
        got_any = False
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
            try:
                data = await post_json(session, endpoint, payload)
            except aiohttp.ClientResponseError:
                break  # 404 -> try next dataset
            rows = data.get("data") or []
            if not rows:
                break
            got_any = True
            for row in rows:
                s = row.get("s") or ""     # e.g., "MOEX:FMC"
                nm = ""
                d = row.get("d") or []
                if d and isinstance(d, list): nm = d[0] or ""
                if ":" in s:
                    ex, tk = s.split(":", 1)
                    ex = clean_exchange(ex)
                    tk = clean_ticker(tk)
                    if ex and tk:
                        symbols.append((ex, tk, nm))
            offset += len(rows)
        if got_any:
            break
    # dedup
    out = {}
    for ex, tk, nm in symbols:
        out.setdefault((ex, tk), nm)
    return [(ex, tk, out[(ex, tk)]) for (ex, tk) in sorted(out.keys())]

async def symbol_search_discover(session, slug: str):
    """Fallback: use symbol-search across EXCHANGE_HINTS[slug]; NO highlight."""
    exchanges = EXCHANGE_HINTS.get(slug, [])
    base = "https://symbol-search.tradingview.com/symbol_search/"
    chars = list(string.ascii_uppercase) + list(string.digits)
    out = {}
    for ex in exchanges:
        ex_clean = clean_exchange(ex)
        for ch in chars:
            # NOTE: removed hl=1 to avoid <em>…</em> in results
            url = f"{base}?text={ch}&exchange={ex_clean}&type=stock&lang=en"
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(
                    total=TIMEOUT_TOTAL, connect=TIMEOUT_CONNECT, sock_read=TIMEOUT_SOCK_READ
                )) as r:
                    if r.status != 200: continue
                    data = await r.json()
            except Exception:
                continue
            for it in data or []:
                e = clean_exchange(str(it.get("exchange","")))
                t = clean_ticker(str(it.get("symbol","")))
                n = it.get("description") or ""
                if e and t:
                    out.setdefault((e, t), n)
        print(f"  SymbolSearch {slug}/{ex_clean}: {sum(1 for k in out if k[0]==ex_clean)}")
    return [(ex, tk, out[(ex, tk)]) for (ex, tk) in sorted(out.keys())]

# ================= CSV / file utils =================
def compute_current_path(row: dict) -> Optional[Path]:
    c = (row.get("country_slug","") or "").strip()
    ex = (row.get("exchange","") or "").strip()
    logo_file = (row.get("logo_file","") or "").strip()
    rel = (row.get("logo_relpath","") or "").strip()
    if rel:
        return BASE_DIR / Path(rel)
    if c and ex and logo_file:
        return BASE_DIR / c / ex / logo_file
    if logo_file:
        return BASE_DIR / logo_file
    return None

def ensure_columns(fieldnames, rows):
    required = ["group","country_slug","country_name","exchange","ticker",
                "company_name","symbol_url","logo_url","logo_file","logo_relpath"]
    for col in required:
        if col not in fieldnames:
            fieldnames.append(col)
            for r in rows:
                r.setdefault(col, "")
    return fieldnames

def add_rows(rows, slug, discovered):
    """Append discovered symbols into rows if not already present."""
    seen = {( (r.get("country_slug","") or "").lower(),
              (r.get("exchange","") or "").upper(),
              (r.get("ticker","") or "").upper() ) for r in rows}
    added = 0
    for ex, tk, nm in discovered:
        ex = clean_exchange(ex)
        tk = clean_ticker(tk)
        key = (slug, ex, tk)
        if not ex or not tk or key in seen:
            continue
        rows.append({
            "group": GROUP_FOR.get(slug, ""),
            "country_slug": slug,
            "country_name": COUNTRY_NAME.get(slug, ""),
            "exchange": ex,
            "ticker": tk,
            "company_name": nm or "",
            "symbol_url": f"https://www.tradingview.com/symbols/{ex}-{tk}/",
            "logo_url": "",
            "logo_file": "",
            "logo_relpath": "",
        })
        added += 1
    return added

def build_manifest(rows):
    manifest = []
    for r in rows:
        c = r.get("country_slug","") or ""
        ex = r.get("exchange","") or ""
        tk = r.get("ticker","") or ""
        nm = r.get("company_name","") or ""
        rel = r.get("logo_relpath","") or ""
        if not rel:
            lf = r.get("logo_file","") or ""
            if lf and c and ex:
                rel = str(Path(c)/ex/lf)
        if not rel:
            continue
        full = BASE_DIR / Path(rel)
        if not full.exists():
            continue
        manifest.append({
            "country": c,
            "exchange": ex,
            "ticker": tk,
            "name": nm,
            "logo": to_web_path(Path(BASE_WEB_PATH) / Path(rel)),
        })
    manifest.sort(key=lambda x: (x["country"] or "~", x["exchange"] or "~", x["ticker"] or "~"))
    return manifest

# ================= MAIN =================
async def main():
    if not CSV_PATH.exists():
        print("CSV not found:", CSV_PATH)
        return

    # Load CSV
    with CSV_PATH.open("r", encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        fieldnames = list(rdr.fieldnames or [])
        rows = list(rdr)
    fieldnames = ensure_columns(fieldnames, rows)

    # Normalize tickers/exchanges in-memory (defensive)
    for r in rows:
        ex = clean_exchange(r.get("exchange",""))
        tk = clean_ticker(r.get("ticker",""))
        if ex and ex != r.get("exchange",""):
            r["exchange"] = ex
        if tk and tk != r.get("ticker",""):
            r["ticker"] = tk
        if ex and tk:
            r["symbol_url"] = f"https://www.tradingview.com/symbols/{ex}-{tk}/"

    # If target countries have 0 rows, discover and append rows first
    counts = {}
    for slug in TARGET_COUNTRIES or { (r.get("country_slug","") or "").lower() for r in rows }:
        counts[slug] = sum(1 for r in rows if (r.get("country_slug","") or "").lower() == slug)

    connector = aiohttp.TCPConnector(limit=CONCURRENCY)
    async with aiohttp.ClientSession(connector=connector, headers={
        "Accept":"text/html,application/json,*/*;q=0.9",
        "Accept-Language":"en-US,en;q=0.9",
        "Origin":"https://www.tradingview.com",
        "Referer":"https://www.tradingview.com/",
        "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    }) as session:
        for slug in (TARGET_COUNTRIES or []):
            if counts.get(slug,0) == 0:
                print(f"[discover] No rows in CSV for {slug}. Trying scanner…")
                discovered = await scanner_discover(session, slug)
                if not discovered:
                    print(f"[discover] Scanner empty/blocked for {slug}. Trying symbol-search…")
                    discovered = await symbol_search_discover(session, slug)
                added = add_rows(rows, slug, discovered)
                print(f"[discover] Added {added} rows for {slug}")

        # Worklist: only rows for target countries whose logo file is missing
        work = []
        for i, r in enumerate(rows):
            c_slug = (r.get("country_slug","") or "").lower()
            if TARGET_COUNTRIES and c_slug not in TARGET_COUNTRIES:
                continue
            full = compute_current_path(r)
            if not full or not full.exists():
                work.append((i, r))
        total = len(work)
        print(f"Will process {total} rows in {sorted(TARGET_COUNTRIES) if TARGET_COUNTRIES else 'ALL'}")

        saved_count = 0
        processed = 0
        started_at = time.time()
        sem = asyncio.Semaphore(CONCURRENCY)

        async def do_one(idx, r):
            nonlocal saved_count, processed
            c = r.get("country_slug","") or ""
            ex = clean_exchange(r.get("exchange","") or "")
            tk = clean_ticker(r.get("ticker","") or "")
            name_fallback = r.get("company_name","") or ""

            async with sem:
                html = await fetch_symbol_html(session, ex, tk)
                if not html:
                    processed += 1
                    if processed % LOG_EVERY == 0:
                        print(f" ..progress {processed}/{total} (saved {saved_count})")
                    return
                url = pick_company_logo_from_html(html, ex)
                disp_name = extract_company_name(html, tk, name_fallback)
                if disp_name and disp_name != r.get("company_name",""):
                    r["company_name"] = disp_name
                if url:
                    file = filename_from_url(url)
                    dest = BASE_DIR / c / ex / file
                    ok = False
                    try:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(
                            total=TIMEOUT_TOTAL, connect=TIMEOUT_CONNECT, sock_read=TIMEOUT_SOCK_READ
                        )) as dl:
                            if dl.status == 200:
                                b = await dl.read()
                                if b:
                                    dest.parent.mkdir(parents=True, exist_ok=True)
                                    dest.write_bytes(b)
                                    ok = True
                    except Exception:
                        ok = False
                    if ok:
                        r["logo_url"] = url
                        r["logo_file"] = file
                        r["logo_relpath"] = str(Path(c) / ex / file)
                        saved_count += 1
                        print(f"[{c} | {ex}] Saved {file}  --> {saved_count} total")
                r["symbol_url"] = f"https://www.tradingview.com/symbols/{ex}-{tk}/"
                r["exchange"] = ex
                r["ticker"] = tk
                rows[idx] = r

                processed += 1
                if processed % LOG_EVERY == 0:
                    elapsed = time.time() - started_at
                    print(f" ..progress {processed}/{total} (saved {saved_count})  ~{elapsed:.0f}s elapsed")

                await asyncio.sleep(JITTER_MIN + random.random()*(JITTER_MAX - JITTER_MIN))

        tasks = [do_one(i, r) for (i, r) in work]
        if tasks:
            await asyncio.gather(*tasks)
        elapsed = time.time() - started_at
        print(f"SAVED logos this run: {saved_count} in ~{elapsed:.0f}s")

    # Write CSV back (overwrite)
    with CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=fieldnames)
        wr.writeheader()
        wr.writerows(rows)
    print("CSV updated:", CSV_PATH)

    # Build manifest + HTML
    manifest = build_manifest(rows)
    OUT_JSON.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("JSON written:", OUT_JSON)

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
    const DATA = {json.dumps(manifest, ensure_ascii=False)};
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
          </div>`;
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
    print("HTML written:", OUT_HTML)

if __name__ == "__main__":
    asyncio.run(main())
