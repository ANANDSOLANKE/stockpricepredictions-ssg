# app.py
# TradingView World Downloader — Desktop (Tk)
# v6.2 — Stock snapshot includes Change % and Market Cap (plus Volume & Currency).
# Columns for stocks CSVs:
#   symbol, description, exchange, sector, industry, open, high, low, Close, Change%, MarketCap, Volume, Currency
# Indices CSV unchanged.

import os, re, time, threading, subprocess, itertools, json, csv
import requests, pandas as pd
from datetime import datetime, timedelta
from urllib.parse import urlparse
from tkinter import *
from tkinter import ttk, filedialog, messagebox
from pytz import timezone
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter, Retry

APP_TITLE = "TradingView World Downloader — Desktop (Tk)"

# -------------------- LINKS --------------------
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

INDICES_GROUP = "Global Indices"
INDICES_URL = "https://www.tradingview.com/markets/indices/quotes-all/"
INDICES_SLUG = "indices"
INDICES_TARGET_ROWS = 80

PAGE_EXCHANGES = {
    "usa": ["NASDAQ","NYSE","NYSEARCA","OTC"],
    "canada": ["TSX","TSXV","CSE","NEO"],
    "austria": ["VIE"], "belgium": ["EURONEXTBRU"], "switzerland": ["SIX","BX"],
    "cyprus": ["CSECY"], "czech": ["PSECZ"], "germany": ["FWB","SWB","XETR","BER","DUS","HAM","HAN","MUN","TRADEGATE","LS","LSX","GETTEX"],
    "denmark": ["OMXCOP"], "estonia": ["OMXTSE"], "spain": ["BME"], "finland": ["OMXHEX"], "france": ["EURONEXTPAR"],
    "greece": ["ATHEX"], "hungary": ["BET"], "ireland": ["EURONEXTDUB"], "iceland": ["OMXICE"],
    "italy": ["MIL","EUROTLX"], "lithuania": ["OMXVSE"], "latvia": ["OMXRSE"], "luxembourg": ["LUXSE"],
    "netherlands": ["EURONEXTAMS"], "norway": ["OSE","OSL","EURONEXTOSE"], "poland": ["GPW","NEWCONNECT"],
    "portugal": ["EURONEXTLIS"], "serbia": ["BELEX"], "romania": ["BVB"], "sweden": ["NGM","OMXSTO"],
    "slovakia": ["BSSE"], "turkey": ["BIST"], "united-kingdom": ["LSE","LSIN","AQUIS","AQSE"], "russia": ["RUS"],
    "uae": ["DFM","ADX","NASDAQDUBAI"], "bahrain": ["BAHRAIN"], "egypt": ["EGX"], "israel": ["TASE"], "kenya": ["NSEKE"],
    "kuwait": ["KSE"], "morocco": ["CSEMA"], "nigeria": ["NSENG"], "qatar": ["QSE"], "ksa": ["TADAWUL"], "tunisia": ["BVMT"],
    "south-africa": ["JSE"], "argentina": ["BYMA","BCBA"], "brazil": ["BMFBOVESPA"], "chile": ["BCS"], "colombia": ["BVC"],
    "mexico": ["BMV","BIVA"], "peru": ["BVL"], "venezuela": ["BVCV"], "australia": ["ASX"], "bangladesh": ["DSEBD"],
    "china": ["SSE","SZSE","SHFE","ZCE","CFFEX"], "hong-kong": ["HKEX"], "indonesia": ["IDX"], "india": ["NSE","BSE"],
    "japan": ["TSE","NAG","FSE","SAPSE"], "korea": ["KRX"], "sri-lanka": ["CSELK"], "malaysia": ["MYX"], "new-zealand": ["NZX"],
    "philippines": ["PSE"], "pakistan": ["PSX"], "singapore": ["SGX"], "thailand": ["SET"], "taiwan": ["TWSE","TPEX"], "vietnam": ["HOSE","HNX","UPCOM"],
}

SLUG_ALIASES = {"united-kingdom":["uk","europe"],"hong-kong":["hongkong","asia"],"new-zealand":["newzealand","australia"],"south-africa":["southafrica","africa"],"czech":["czechrepublic","europe"]}
GROUP_FALLBACK_REGION = {"Europe":["europe"],"North America":["america","canada"],"Mexico - South America":["brazil","mexico","america"],"Middle East - Africa":["middleeast","africa"],"Asia - Pacific":["asia","australia","japan","china","india","hongkong"]}

TZ_OPEN_CLOSE = {
    "usa": ("America/New_York","09:30","16:00"), "canada": ("America/Toronto","09:30","16:00"),
    "austria": ("Europe/Vienna","09:04","17:30"), "italy": ("Europe/Rome","09:00","17:30"),
    "belgium": ("Europe/Brussels","09:00","17:30"), "lithuania": ("Europe/Vilnius","10:00","16:00"),
    "switzerland": ("Europe/Zurich","09:00","17:20"), "latvia": ("Europe/Riga","10:00","16:00"),
    "cyprus": ("Asia/Nicosia","10:00","17:20"), "luxembourg": ("Europe/Luxembourg","09:00","17:35"),
    "czech": ("Europe/Prague","09:15","16:30"), "netherlands": ("Europe/Amsterdam","09:00","17:30"),
    "germany": ("Europe/Berlin","08:00","22:00"), "norway": ("Europe/Oslo","09:00","16:25"),
    "denmark": ("Europe/Copenhagen","09:00","16:55"), "poland": ("Europe/Warsaw","09:00","16:50"),
    "estonia": ("Europe/Tallinn","10:00","16:00"), "portugal": ("Europe/Lisbon","09:00","17:30"),
    "spain": ("Europe/Madrid","09:00","17:30"), "peru": ("America/Lima","09:30","14:00"),
    "finland": ("Europe/Helsinki","10:00","18:25"), "russia": ("Europe/Moscow","10:00","18:40"),
    "france": ("Europe/Paris","09:00","17:30"), "romania": ("Europe/Bucharest","10:00","17:55"),
    "greece": ("Europe/Athens","10:30","17:20"), "sweden": ("Europe/Stockholm","09:00","17:25"),
    "hungary": ("Europe/Budapest","09:00","17:00"), "slovakia": ("Europe/Bratislava","11:00","16:00"),
    "ireland": ("Europe/Dublin","08:00","16:30"), "turkey": ("Europe/Istanbul","10:00","18:00"),
    "iceland": ("Atlantic/Reykjavik","09:30","15:25"), "united-kingdom": ("Europe/London","08:00","16:30"),
    "uae": ("Asia/Dubai","10:00","15:00"), "bahrain": ("Asia/Bahrain","10:00","12:30"),
    "nigeria": ("Africa/Lagos","10:00","14:20"), "egypt": ("Africa/Cairo","10:00","14:30"),
    "qatar": ("Asia/Qatar","09:30","13:15"), "israel": ("Asia/Jerusalem","09:59","17:25"),
    "ksa": ("Asia/Riyadh","10:00","16:00"), "kenya": ("Africa/Nairobi","09:30","15:00"),
    "tunisia": ("Africa/Tunis","09:00","14:10"), "kuwait": ("Asia/Kuwait","09:00","12:45"),
    "south-africa": ("Africa/Johannesburg","09:00","17:00"), "argentina": ("America/Argentina/Buenos_Aires","11:00","17:00"),
    "mexico": ("America/Mexico_City","08:30","15:00"), "brazil": ("America/Sao_Paulo","10:00","16:55"),
    "chile": ("America/Santiago","09:30","16:00"), "venezuela": ("America/Caracas","09:00","13:00"),
    "colombia": ("America/Bogota","09:00","16:00"), "australia": ("Australia/Sydney","10:00","16:00"),
    "malaysia": ("Asia/Kuala_Lumpur","09:00","17:00"), "bangladesh": ("Asia/Dhaka","10:00","14:20"),
    "new-zealand": ("Pacific/Auckland","10:00","16:45"), "china": ("Asia/Shanghai","09:30","16:00"),
    "philippines": ("Asia/Manila","09:30","15:00"), "hong-kong": ("Asia/Hong_Kong","09:30","16:00"),
    "pakistan": ("Asia/Karachi","09:30","15:30"), "indonesia": ("Asia/Jakarta","09:00","15:00"),
    "singapore": ("Asia/Singapore","09:00","17:00"), "india": ("Asia/Kolkata","09:15","15:30"),
    "thailand": ("Asia/Bangkok","10:00","16:30"), "japan": ("Asia/Tokyo","09:00","15:00"),
    "taiwan": ("Asia/Taipei","09:00","13:30"), "korea": ("Asia/Seoul","09:00","15:30"),
    "vietnam": ("Asia/Ho_Chi_Minh","09:00","15:00"), "sri-lanka": ("Asia/Colombo","10:30","14:30"),
    "indices": ("UTC","00:00","23:59"),
}

FRI_SAT_WEEKEND = {"ksa","uae","qatar","kuwait","bahrain"}
def is_weekend_local(slug, local_dt):
    wd = local_dt.weekday()
    if slug in FRI_SAT_WEEKEND: return wd in (4,5)
    return wd in (5,6)

def load_holidays(path="holidays.csv"):
    dates, why = {}, {}
    if not os.path.exists(path): return dates, why
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            slug = (row.get("slug") or "").strip()
            d    = (row.get("date") or "").strip()
            reason = (row.get("reason") or "").strip()
            if not slug or not d: continue
            dates.setdefault(slug, set()).add(d)
            if reason: why.setdefault(slug, {})[d] = reason
    return dates, why
HOLI_DATES, HOLI_WHY = load_holidays()
def is_holiday(slug, local_dt):
    d = local_dt.strftime("%Y-%m-%d")
    if slug in HOLI_DATES and d in HOLI_DATES[slug]:
        return True, HOLI_WHY.get(slug, {}).get(d, "")
    return False, ""

def most_recent_trading_day(slug: str, tz, from_dt=None):
    if from_dt is None:
        from_dt = datetime.now(tz)
    d = from_dt.date()
    while True:
        local_midnight = tz.localize(datetime(d.year, d.month, d.day))
        hol, _ = is_holiday(slug, local_midnight)
        if (not is_weekend_local(slug, local_midnight)) and (not hol):
            return d
        d = d - timedelta(days=1)

HEADERS = {"User-Agent":"Mozilla/5.0","Content-Type":"application/json","Origin":"https://in.tradingview.com","Referer":"https://in.tradingview.com/markets/"}
BASE_COLUMNS = ["name","exchange","close","currency"]
CANDIDATE_COLUMNS = ["change","change_abs","open","high","low","volume","description","sector","industry","type","subtype","market_cap_basic","price_earnings_ttm","earnings_per_share_basic_ttm","dividends_yield_current","book_value_per_share_quarterly"]

def slug_from_url(u: str) -> str:
    if "markets/indices/quotes-all" in u: return INDICES_SLUG
    m = re.search(r"/markets/stocks-([^/]+)/", urlparse(u).path)
    return m.group(1) if m else "unknown"
def scan_url(region: str) -> str: return f"https://scanner.tradingview.com/{region}/scan"
def tv_post(url, payload, s):
    r = s.post(url, headers=HEADERS, json=payload, timeout=60)
    if r.status_code >= 400: raise RuntimeError(f"{url} -> HTTP {r.status_code}: {r.text[:200]}")
    return r.json()

_region_cols_cache = {}
def probe_region_columns(region: str):
    if region in _region_cols_cache: return _region_cols_cache[region]
    url = scan_url(region); s = requests.Session()
    base = {"symbols":{"tickers":[],"query":{"types":[]}},"columns":BASE_COLUMNS,"filter":[],"sort":{"sortBy":"name","sortOrder":"asc"},"options":{"lang":"en"},"range":[0,1]}
    tv_post(url, base, s)
    cols = list(BASE_COLUMNS)
    for c in CANDIDATE_COLUMNS:
        base["columns"] = cols + [c]
        try: tv_post(url, base, s); cols.append(c)
        except Exception: pass
    _region_cols_cache[region] = cols
    return cols

def candidate_regions_for(slug: str, group: str):
    if slug == INDICES_SLUG: return []
    cands = [slug]
    if slug in SLUG_ALIASES: cands += SLUG_ALIASES[slug]
    cands += GROUP_FALLBACK_REGION.get(group, [])
    cands += ["america","europe","asia","australia","middleeast","africa","india","canada","uk","japan","china","brazil","russia","mexico","argentina","chile","colombia","peru"]
    out=[]; seen=set()
    for r in cands:
        if r not in seen: seen.add(r); out.append(r)
    return out

def resolve_region(slug: str, group: str):
    if slug == INDICES_SLUG: return None, None
    for reg in candidate_regions_for(slug, group):
        try:
            cols = probe_region_columns(reg)
            return reg, cols
        except Exception:
            continue
    return None, None

def fetch_all(region: str, columns, exchanges=None, page_size=1000, pause=0.15):
    url = scan_url(region); s = requests.Session()
    def run_pass(exch_list):
        filt = []
        if exch_list: filt.append({"left":"exchange","operation":"in_range","right":exch_list})
        rows, start = [], 0
        while True:
            payload = {"symbols":{"tickers":[],"query":{"types":[]}},"columns":columns,"filter":filt,"sort":{"sortBy":"name","sortOrder":"asc"},"options":{"lang":"en"},"range":[start,start+page_size]}
            try: resp = tv_post(url, payload, s)
            except Exception as e: return [], str(e)
            data = resp.get("data") or []
            if not data: break
            for item in data:
                d = {}
                for c, v in itertools.zip_longest(columns, item.get("d", [])):
                    if c is not None: d[c] = v
                rows.append(d)
            start += page_size; time.sleep(pause)
        return rows, None
    rows, err = run_pass(exchanges)
    if (err is not None) or (len(rows)==0):
        rows, err2 = run_pass(None)
        if err2: return pd.DataFrame(), f"fetch error: {err2}"
    if not rows: return pd.DataFrame(), "no rows"
    df = pd.DataFrame(rows)
    def split_name(n):
        if isinstance(n, str) and ":" in n:
            ex, sym = n.split(":", 1); return ex, sym
        return None, n
    df[["ex_from_name","symbol"]] = df["name"].apply(lambda n: pd.Series(split_name(n)))
    if "exchange" in df.columns: df["exchange"] = df["exchange"].fillna(df["ex_from_name"])
    else: df["exchange"] = df["ex_from_name"]
    df.drop(columns=["ex_from_name"], inplace=True, errors="ignore")
    preferred = ["symbol","description","exchange","close","currency","change","change_abs","volume","market_cap_basic","sector","industry","type","subtype","name","open","high","low"]
    order = [c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]
    df = df[order].drop_duplicates().reset_index(drop=True)
    return df, None

STOCK_SNAPSHOT_ORDER = ["symbol","description","exchange","sector","industry","open","high","low","Close","Change%","MarketCap","Volume","Currency"]

def make_stock_snapshot_df(df: pd.DataFrame) -> pd.DataFrame:
    snap = df.copy()
    for col in ["symbol","description","exchange","sector","industry","open","high","low","close","change","market_cap_basic","volume","currency"]:
        if col not in snap.columns: snap[col] = pd.NA
    snap = snap.rename(columns={"close":"Close","change":"Change%","market_cap_basic":"MarketCap","volume":"Volume","currency":"Currency"})
    return snap[[c for c in STOCK_SNAPSHOT_ORDER if c in snap.columns]]

INDICES_ORDER = ["symbol","name","price","currency","change_percent","change_points","day_high","day_low","tech_rating"]

def indices_session() -> requests.Session:
    s = requests.Session()
    retries = Retry(total=5, backoff_factor=0.6, status_forcelist=(429,500,502,503,504), allowed_methods=("GET",), raise_on_status=False)
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.headers.update({"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36","Accept":"text/html,application/json;q=0.9,*/*;q=0.8","Accept-Language":"en-US,en;q=0.9","Referer":"https://www.tradingview.com/","Origin":"https://www.tradingview.com","Connection":"keep-alive"})
    return s

def _num(txt: str):
    if not txt: return None
    t = txt.replace("\u2212","-").replace(",","").strip()
    if t in {"–","-",""}: return None
    t = re.sub(r"\s+[A-Z]{3}$","",t)
    try: return float(t)
    except: return None

def _pct(txt: str):
    if not txt: return None
    t = txt.replace("\u2212","-").replace("%","").replace(",","").strip()
    if t in {"–","-",""}: return None
    try: return float(t)
    except: return None

def _split_val_ccy(txt: str):
    if not txt or txt.strip() in {"–","-"}: return (None,None)
    s = txt.strip()
    m = re.search(r"([A-Za-z]{3})$", s)
    ccy = m.group(1) if m else None
    num_part = s if not ccy else s[: s.rfind(ccy)].strip()
    return (_num(num_part), ccy)

def parse_indices_ssr(html: str):
    soup = BeautifulSoup(html, "html.parser")
    data = []
    rows = soup.select("[role='table'] [role='row']")
    if len(rows) <= 1:
        rows = soup.select("table tr")
    for r in rows[1:]:
        cells = r.select("[role='cell']") or r.select("td")
        if len(cells) < 7: continue
        cell0 = cells[0].get_text(" ", strip=True)
        sym_candidate = None
        for t in (cells[0].select("a, span, div") or []):
            tt = t.get_text(" ", strip=True)
            m = re.match(r"^([A-Z0-9\.\-:]{1,15})$", tt)
            if m: sym_candidate = m.group(1); break
        if not sym_candidate:
            m = re.match(r"^\s*([A-Z0-9\.\-:]{1,15})\s+(.*)$", cell0)
            if m: sym_candidate = m.group(1); name_candidate = m.group(2)
            else:
                parts = cell0.split()
                if len(parts) >= 2: sym_candidate, name_candidate = parts[0], " ".join(parts[1:])
                else: continue
        else:
            name_candidate = cell0.replace(sym_candidate, "", 1).strip(" -—•\u2009")

        price_txt = cells[1].get_text(" ", strip=True)
        chg_pct_txt = cells[2].get_text(" ", strip=True)
        chg_pts_txt = cells[3].get_text(" ", strip=True)
        high_txt = cells[4].get_text(" ", strip=True)
        low_txt = cells[5].get_text(" ", strip=True)
        tech = cells[6].get_text(" ", strip=True)

        price, ccy = _split_val_ccy(price_txt)
        high, ccy_h = _split_val_ccy(high_txt)
        low, ccy_l = _split_val_ccy(low_txt)
        currency = ccy or ccy_h or ccy_l

        data.append({"symbol":sym_candidate.strip(),"name":name_candidate.strip(),"price":price,"currency":currency,"change_percent":_pct(chg_pct_txt),"change_points":_num(chg_pts_txt),"day_high":high,"day_low":low,"tech_rating":tech})
        if len(data) >= 80: break
    return data

def fetch_indices_df():
    s = indices_session()
    resp = s.get(INDICES_URL, timeout=30); resp.raise_for_status()
    rows = parse_indices_ssr(resp.text)
    if not rows: return pd.DataFrame(), "no rows"
    df = pd.DataFrame(rows)[["symbol","name","price","currency","change_percent","change_points","day_high","day_low","tech_rating"]]
    df = df.drop_duplicates(subset=["symbol","name"]).head(80)
    return df, None

def aware_dt(tz, date_obj, time_str):
    t = datetime.strptime(time_str, "%H:%M").time()
    return tz.localize(datetime.combine(date_obj, t))

class App:
    def __init__(self, root):
        self.root = root; root.title(APP_TITLE)
        self.data_folder = StringVar(value="data")
        self.run_window_mins = StringVar(value="120")
        self.auto_push = BooleanVar(value=False)
        self.gh_owner = StringVar(value=""); self.gh_repo = StringVar(value="")
        self.gh_branch = StringVar(value="main"); self.gh_token = StringVar(value="")
        self.rows = self._build_rows()
        self._build_controls(); self._build_table()
        self._load_meta(); self._apply_meta_to_table()
        self._tick(); self.auto_running = False; self.log("Ready.")

    def _meta_path(self): return os.path.join(self.data_folder.get(), "_status.json")
    def _load_meta(self):
        try:
            with open(self._meta_path(), "r", encoding="utf-8") as f: self.meta = json.load(f)
        except Exception: self.meta = {}
    def _save_meta(self):
        os.makedirs(self.data_folder.get(), exist_ok=True)
        with open(self._meta_path(), "w", encoding="utf-8") as f: json.dump(self.meta, f, indent=2)
    def _apply_meta_to_table(self):
        for slug, m in (self.meta or {}).items():
            if not self.tree.exists(slug): continue
            self.tree.set(slug, "last_run", m.get("last_run","-"))
            self.tree.set(slug, "rows", m.get("rows", 0))
            self.tree.set(slug, "dl_for", m.get("dl_for","-"))
            self.tree.set(slug, "dl_time", m.get("dl_time","-"))
            self.tree.set(slug, "push", m.get("push","-"))
    def _update_meta_after_run(self, slug, rows, dl_for, push_msg="-"):
        self.meta.setdefault(slug, {})
        self.meta[slug]["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.meta[slug]["dl_time"]  = datetime.now().strftime("%H:%M:%S")
        self.meta[slug]["rows"]     = int(rows)
        self.meta[slug]["dl_for"]   = dl_for
        self.meta[slug]["push"]     = push_msg
        self._save_meta()

    def _build_rows(self):
        rows=[]
        for group, links in LINK_GROUPS.items():
            for url in dict.fromkeys(links):
                slug = slug_from_url(url); tz, op, cl = TZ_OPEN_CLOSE.get(slug, ("UTC","09:00","16:00"))
                rows.append({"group":group,"slug":slug,"tz":tz,"open":op,"close":cl,"last_run":"-","rows":0,"status":"Idle","next_due":"-"})
        tz, op, cl = TZ_OPEN_CLOSE.get("indices", ("UTC","00:00","23:59"))
        rows.append({"group":"Global Indices","slug":"indices","tz":tz,"open":op,"close":cl,"last_run":"-","rows":0,"status":"Idle","next_due":"-"})
        return rows

    def _build_controls(self):
        frm = Frame(self.root); frm.pack(fill=X, padx=8, pady=6)
        Label(frm, text="Data folder").grid(row=0, column=0, sticky=W, padx=4)
        Entry(frm, textvariable=self.data_folder, width=32).grid(row=0, column=1, sticky=W)
        Button(frm, text="Browse", command=self.browse_folder).grid(row=0, column=2, padx=4)
        Label(frm, text="Run window (min after close)").grid(row=0, column=3, sticky=E, padx=8)
        Entry(frm, textvariable=self.run_window_mins, width=8).grid(row=0, column=4, sticky=W)
        Checkbutton(frm, text="Auto push to GitHub", variable=self.auto_push).grid(row=0, column=5, padx=8)
        Label(frm, text="Owner").grid(row=1, column=0, sticky=E); Entry(frm,textvariable=self.gh_owner, width=18).grid(row=1,column=1,sticky=W)
        Label(frm, text="Repo").grid(row=1, column=2, sticky=E); Entry(frm,textvariable=self.gh_repo,  width=18).grid(row=1,column=3,sticky=W)
        Label(frm, text="Branch").grid(row=1, column=4, sticky=E); Entry(frm,textvariable=self.gh_branch,width=10).grid(row=1,column=5,sticky=W)
        Label(frm, text="Token").grid(row=1, column=6, sticky=E); Entry(frm,textvariable=self.gh_token, show="*", width=32).grid(row=1,column=7,sticky=W)
        frm2 = Frame(self.root); frm2.pack(fill=X, padx=8, pady=6)
        Button(frm2, text="Save Settings", command=self.save_settings).pack(side=LEFT, padx=4)
        Button(frm2, text="Start Auto", command=self.start_auto).pack(side=LEFT, padx=4)
        Button(frm2, text="Stop Auto", command=self.stop_auto).pack(side=LEFT, padx=4)
        Button(frm2, text="Run Selected", command=self.run_selected).pack(side=LEFT, padx=4)
        Button(frm2, text="Run All Now", command=self.run_all_now).pack(side=LEFT, padx=4)
        Button(frm2, text="Refresh", command=self.refresh_table).pack(side=LEFT, padx=4)
        self.log_box = Text(self.root, height=7); self.log_box.pack(fill=BOTH, padx=8, pady=(0,8))

    def _build_table(self):
        cols=("group","slug","tz","open","close","localnow","status","timer","next_due","last_run","rows","dl_for","dl_time","err","push")
        self.tree = ttk.Treeview(self.root, columns=cols, show="headings")
        headers=["Group","Slug","Timezone","Open","Close","Local Now","Status (OPEN/CLOSE/Holiday)","Timer to Close","Next Due","Last Run","Rows","Downloaded for Date","Downloaded at","Error?","Git Push"]
        for c,h in zip(cols,headers):
            self.tree.heading(c, text=h); self.tree.column(c, width=140 if c in ("group","slug","tz") else 120, anchor=W)
        self.tree.pack(fill=BOTH, expand=True, padx=8, pady=(0,8))
        for r in self.rows:
            self.tree.insert("", "end", iid=r["slug"], values=(r["group"],r["slug"],r["tz"],r["open"],r["close"],"-","-","-","-","-",0,"-","-","-","-"))

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S"); self.log_box.insert(END, f"[{ts}] {msg}\n"); self.log_box.see(END)

    def browse_folder(self):
        d = filedialog.askdirectory(initialdir=".")
        if d: self.data_folder.set(d); self._load_meta(); self._apply_meta_to_table()

    def save_settings(self):
        cfg = {"data_folder":self.data_folder.get(),"run_window_mins":self.run_window_mins.get(),"auto_push":self.auto_push.get(),"gh_owner":self.gh_owner.get(),"gh_repo":self.gh_repo.get(),"gh_branch":self.gh_branch.get(),"when_saved":datetime.now().isoformat(timespec="seconds")}
        with open("settings.json","w",encoding="utf-8") as f: json.dump(cfg, f, indent=2)
        self._load_meta(); self._apply_meta_to_table(); self.log("Settings saved.")

    def _tick(self):
        for r in self.rows:
            slug=r["slug"]; tzname, open_s, close_s = TZ_OPEN_CLOSE.get(slug, ("UTC","09:00","16:00")); tz=timezone(tzname)
            now_local = datetime.now(tz)
            self.tree.set(slug, "localnow", now_local.strftime("%Y-%m-%d %H:%M"))
            holiday, why = is_holiday(slug, now_local); weekend = is_weekend_local(slug, now_local)
            open_t = aware_dt(tz, now_local.date(), open_s)
            close_t= aware_dt(tz, now_local.date(), close_s)
            if slug == "indices":
                status="OPEN"; timer="-"
            elif holiday: status="Holiday"; timer=why or "-"
            elif weekend: status="Closed (Weekend)"; timer="-"
            elif now_local < open_t: status="Closed (Pre-open)"; timer=f"closes {close_s}"
            elif now_local >= close_t: status="Closed"; timer="-"
            else: status="OPEN"; timer=str(close_t-now_local).split(".")[0]
            self.tree.set(slug,"status",status); self.tree.set(slug,"timer",timer)
            mins=max(0,int(self.run_window_mins.get() or "0"))
            next_due_dt = close_t + timedelta(minutes=mins)
            if now_local > next_due_dt:
                next_due_dt = aware_dt(tz, (now_local + timedelta(days=1)).date(), close_s) + timedelta(minutes=mins)
            self.tree.set(slug, "next_due", next_due_dt.strftime("%Y-%m-%d %H:%M"))
        self.root.after(30_000, self._tick)

    def start_auto(self):
        if getattr(self,"auto_running",False): self.log("Auto already running."); return
        self.auto_running=True; threading.Thread(target=self._auto_loop, daemon=True).start(); self.log("Auto started.")
    def stop_auto(self): self.auto_running=False; self.log("Auto stopped.")
    def _auto_loop(self):
        while self.auto_running:
            try:
                for r in self.rows:
                    slug=r["slug"]; tzname, _, close_s = TZ_OPEN_CLOSE.get(slug, ("UTC","09:00","16:00")); tz=timezone(tzname)
                    now_local=datetime.now(tz)
                    if slug == "indices":
                        ny_tz = timezone("America/New_York")
                        ny_now = datetime.now(ny_tz)
                        close_t = aware_dt(ny_tz, ny_now.date(), "16:00")
                        window_m=max(0,int(self.run_window_mins.get() or "0"))
                        if close_t <= ny_now <= close_t+timedelta(minutes=window_m):
                            target_date = most_recent_trading_day("usa", ny_tz, ny_now).strftime("%Y-%m-%d")
                            last_for=(self.meta.get(slug, {}) or {}).get("dl_for","")
                            if last_for != target_date: self._run_one(slug, force=False)
                        continue
                    holiday,_=is_holiday(slug,now_local)
                    if holiday or is_weekend_local(slug, now_local): continue
                    close_t=aware_dt(tz, now_local.date(), close_s)
                    window_m=max(0,int(self.run_window_mins.get() or "0"))
                    if close_t <= now_local <= close_t+timedelta(minutes=window_m):
                        target_date = most_recent_trading_day(slug, tz, now_local).strftime("%Y-%m-%d")
                        last_for=(self.meta.get(slug, {}) or {}).get("dl_for","")
                        if last_for != target_date: self._run_one(slug, force=False)
                time.sleep(60)
            except Exception as e:
                self.log(f"[auto] error: {e}"); time.sleep(60)

    def refresh_table(self): self._apply_meta_to_table(); self.log("Refreshed.")
    def run_selected(self):
        sel=self.tree.selection()
        if not sel: messagebox.showinfo("Run Selected","Please select one or more rows."); return
        for iid in sel: self._run_one(iid, force=True)
    def run_all_now(self):
        for r in self.rows: self._run_one(r["slug"], force=True)

    def _run_one(self, slug, force=False):
        r = next((x for x in self.rows if x["slug"]==slug), None)
        if not r: return
        group=r["group"]
        tzname, _, _ = TZ_OPEN_CLOSE.get(slug, ("UTC","09:00","16:00")); tz=timezone(tzname)

        now_local = datetime.now(tz)
        if slug == "indices":
            ny_tz = timezone("America/New_York")
            target_date = most_recent_trading_day("usa", ny_tz, datetime.now(ny_tz)).strftime("%Y-%m-%d")
        else:
            target_date = most_recent_trading_day(slug, tz, now_local).strftime("%Y-%m-%d")

        last_for = (self.meta.get(slug, {}) or {}).get("dl_for","")
        if force and last_for == target_date:
            self.tree.set(slug,"status","Up-to-date"); self.log(f"{slug}: already up-to-date for {target_date}."); return
        holiday,_=is_holiday(slug,now_local)
        if not force and (slug!="indices") and (holiday or is_weekend_local(slug, now_local)):
            self.tree.set(slug,"err","Holiday/Weekend"); self.log(f"{slug}: skip auto (holiday/weekend)."); return

        self.tree.set(slug,"status","Running…"); self.tree.update_idletasks()

        if slug == "indices":
            df, err = fetch_indices_df()
            if err: self.tree.set(slug,"err",err); self.tree.set(slug,"status","Idle"); self.log(f"indices: {err}"); return
            if df.empty: self.tree.set(slug,"err","empty (skipped)"); self.tree.set(slug,"status","Idle"); self.log("indices: empty result (skipped)."); return
            snap_df = df[["symbol","name","price","currency","change_percent","change_points","day_high","day_low","tech_rating"]]
        else:
            region, columns = resolve_region(slug, group)
            if not region:
                self.tree.set(slug,"err","Region not found"); self.tree.set(slug,"status","Idle"); self.log(f"{slug}: region not found."); return
            exchanges = PAGE_EXCHANGES.get(slug)
            df, err = fetch_all(region, columns, exchanges=exchanges)
            if err: self.tree.set(slug,"err",err); self.tree.set(slug,"status","Idle"); self.log(f"{slug}: {err}"); return
            if df.empty: self.tree.set(slug,"err","empty (skipped)"); self.tree.set(slug,"status","Idle"); self.log(f"{slug}: empty result (skipped)."); return
            snap_df = make_stock_snapshot_df(df)

        last_dir = os.path.join(self.data_folder.get(), "LastTradingDay", group.replace("/","-"))
        os.makedirs(last_dir, exist_ok=True)
        last_path = os.path.join(last_dir, f"{slug}.csv")
        snap_df.to_csv(last_path, index=False, encoding="utf-8")

        hist_dir = os.path.join(self.data_folder.get(), "Historical", target_date, group.replace("/","-"))
        os.makedirs(hist_dir, exist_ok=True)
        hist_path = os.path.join(hist_dir, f"{slug}.csv")
        snap_df.to_csv(hist_path, index=False, encoding="utf-8")

        self.tree.set(slug,"rows",len(snap_df))
        self.tree.set(slug,"dl_for",target_date)
        self.tree.set(slug,"dl_time",datetime.now().strftime("%H:%M:%S"))
        self.tree.set(slug,"last_run",datetime.now().strftime("%Y-%m-%d %H:%M"))
        self.tree.set(slug,"err","-")
        self.tree.set(slug,"status","Done (forced)" if force else "Done")
        self.tree.set(slug,"push","-")
        self.log(f"{slug}: LastTradingDay -> {last_path}")
        self.log(f"{slug}: Historical -> {hist_path}")

        if self.auto_push.get():
            msg = git_push(self.data_folder.get(), self.gh_owner.get().strip(), self.gh_repo.get().strip(), (self.gh_branch.get().strip() or "main"), self.gh_token.get().strip(), self.log)
            self.tree.set(slug,"push",msg); self.log(f"{slug}: push -> {msg}")

        self._update_meta_after_run(slug, len(snap_df), target_date, self.tree.set(slug,"push"))

def git_available():
    try:
        subprocess.run(["git","--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return True
    except Exception:
        return False

def git_push(folder, owner, repo, branch, token, log_fn):
    try:
        if not git_available(): return "git not found"
        if not owner or not repo or not token: return "missing GH settings"
        os.makedirs(folder, exist_ok=True)
        subprocess.run(["git","init"], cwd=folder, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git","config","user.email","bot@example.com"], cwd=folder, check=False)
        subprocess.run(["git","config","user.name","TV World Bot"], cwd=folder, check=False)
        remote_url = f"https://{token}@github.com/{owner}/{repo}.git"
        res = subprocess.run(["git","remote","get-url","origin"], cwd=folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0: subprocess.run(["git","remote","add","origin",remote_url], cwd=folder, check=False)
        else: subprocess.run(["git","remote","set-url","origin",remote_url], cwd=folder, check=False)
        subprocess.run(["git","checkout","-B",branch], cwd=folder, check=False)
        subprocess.run(["git","pull","--rebase","origin",branch], cwd=folder, check=False)
        status = subprocess.run(["git","status","--porcelain"], cwd=folder, stdout=subprocess.PIPE, text=True)
        if status.stdout.strip() == "": return "no changes"
        subprocess.run(["git","add","-A"], cwd=folder, check=True)
        msg = f"Update {datetime.now().isoformat(timespec='seconds')}"
        subprocess.run(["git","commit","-m",msg], cwd=folder, check=True)
        push = subprocess.run(["git","push","-u","origin",branch], cwd=folder, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        return "Done" if push.returncode == 0 else f"error: {push.stdout[-200:]}"
    except Exception as e:
        return f"error: {e}"

def main():
    root = Tk(); root.geometry("1220x720"); app = App(root); root.mainloop()

if __name__ == "__main__":
    main()
