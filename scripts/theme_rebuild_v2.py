# scripts/theme_rebuild_v2.py
# v2.5 — CSV-first rebuild aligned with dark index tables.
# - Reads Date + O H L C + %Change from Data/LastTradingDay/<Region>/<country>.csv
# - Header shows: Date: {date} • O {o} H {h} L {l} C {c} • % Change {chg}
# - Banner shows: AI Prediction: {Full Name} for {Next trading date}
# - Theme/HTML structure unchanged
# - Robust header normalization so "Change%" is recognized as percent

import re, csv
import datetime as dt
from pathlib import Path
from html import escape

DIST_ROOT = "dist"
DATA_ROOT = Path("Data") / "LastTradingDay"
STAMP = f"<!-- v2-rebuild-light {dt.datetime.now(dt.timezone.utc).isoformat()} -->"

# ---------- helpers ----------
def rx(pat, s, flags=re.I | re.S, group=1, default=""):
    m = re.search(pat, s, flags)
    return (m.group(group).strip() if m else default).strip()

def next_weekday(iso_date: str) -> str:
    try:
        d = dt.date.fromisoformat(iso_date)
    except Exception:
        return "—"
    while True:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            return d.isoformat()

def number_str(x):
    sx = str(x).strip()
    if sx == "" or sx == "—":
        return "—"
    return sx.replace(",", "")

def pct_to_str(val):
    if val is None or val == "":
        return "—"
    try:
        f = float(val)
    except Exception:
        return "—"
    return f"{f:.2f}%"

# ---------- HTML fallbacks (unchanged look) ----------
def get_symbol_and_fullname(html: str):
    sym = rx(r"AI\s+Analysis\s+of\s+([A-Z0-9.\-]+)\s*\(", html)
    full = rx(r"AI\s+Analysis\s+of\s+[A-Z0-9.\-]+\s*\(([^)]+)\)", html)
    if not full:
        h1 = rx(r"<h1[^>]*>(.*?)</h1>", html)
        clean = re.sub(r"<[^>]+>", "", h1)
        full = rx(r"AI\s+Analysis\s+of\s+(.+?)\s+\(", clean)
        sym2 = rx(r"\(([^)]+)\)", clean)
        if full and not sym:
            sym = sym2
    return sym or "", full or ""

def get_prediction_date_explicit(html: str):
    d = rx(r"Prediction\s+for\s+([0-9]{4}-[0-9]{2}-[0-9]{2})", html, default="")
    if d: return d
    d = rx(r"Next\s*(?:Trading\s*)?Day\s*[:\-]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", html, default="")
    if d: return d
    d = rx(r"AI\s+Prediction\s*[:\-]\s*.*?\b([0-9]{4}-[0-9]{2}-[0-9]{2})\b", html, default="")
    return d or ""

def extract_table_block(html: str) -> str:
    return rx(r"(<table[^>]*>.*?</table>)", html, group=1, default="")

def get_max_table_date(html: str) -> str:
    tbl = extract_table_block(html)
    if not tbl:
        return ""
    dates = re.findall(r"\b([0-9]{4}-[0-9]{2}-[0-9]{2})\b", tbl)
    if not dates:
        return ""
    try:
        dates_parsed = sorted({dt.date.fromisoformat(x) for x in dates})
        return dates_parsed[-1].isoformat()
    except Exception:
        return ""

def get_ohlc_and_change_from_html(html: str):
    o = h = l = c = chg = "—"
    m = re.search(
        r"OHLC:\s*O\s*([0-9.,\-]+).*?H\s*([0-9.,\-]+).*?L\s*([0-9.,\-]+).*?C\s*([0-9.,\-]+)",
        html, re.I | re.S
    )
    if m:
        o, h, l, c = [g.strip().replace(",", "") for g in m.groups()]

    cutoff_idx = len(html)
    for marker in ("Model Performance", "Last 7-Day Accuracy", "Model vs. Actual"):
        i = html.lower().find(marker.lower())
        if i != -1: cutoff_idx = min(cutoff_idx, i)
    scope = html[:cutoff_idx]
    patt = re.compile(
        r"(?:Change%\s*|Change\s*%\s*|Change\s*|Chg%\s*|Chg\s*|Day\s*Change\s*|[Δ∆]\s*%)"
        r"[:\-]?\s*([+\-]?\s*\d+(?:[.,]\d+)?)\s*%", re.I | re.S
    )
    k = patt.search(scope)
    if k:
        chg = k.group(1).replace(" ", "").replace(",", ".") + "%"
    return o, h, l, c, chg

def get_signal(html: str):
    tb = rx(r"<table[^>]*>.*?<thead.*?</thead>.*?<tbody[^>]*>(.*?)</tbody>", html, group=1, default="")
    if tb:
        r = re.search(r"<tr[^>]*>.*?<td[^>]*>.*?</td>.*?<td[^>]*>(Bullish|Bearish)</td>", tb, re.I | re.S)
        if r: return r.group(1).title()
    return "—"

def arrow_for(signal: str):
    return "▲" if signal.lower()=="bullish" else ("▼" if signal.lower()=="bearish" else "—")

def banner_class_for(signal: str):
    return "green" if signal.lower()=="bullish" else ("red" if signal.lower()=="bearish" else "")

def scrape_accuracy(html: str):
    chip = rx(r"([0-9]{1,3}\.[0-9]{2}%\s*\([0-9]+/[0-9]+\))", html, default="")
    return (chip or "—"), ("Last 7-Day Accuracy" if chip else "Accuracy unavailable")

def build_table(html: str):
    table = extract_table_block(html)
    if not table:
        return ('<table class="table"><thead><tr><th>Date</th><th>AI Prediction</th>'
                '<th>Actual</th><th>Result</th></tr></thead>'
                '<tbody><tr><td>—</td><td>—</td><td>—</td><td>—</td></tr></tbody></table>')
    table = re.sub(r">Win<",  r'><span class="win">Win</span><',  table, flags=re.I)
    table = re.sub(r">Loss<", r'><span class="loss">Loss</span><', table, flags=re.I)
    table = re.sub(r"<table([^>]*)>", r'<table class="table"\1>', table, count=1, flags=re.I)
    return table

# ---------- region folder mapping (dist → Data/LastTradingDay names) ----------
REGION_MAP = {
    "asia-pacific": "Asia - Pacific",
    "europe": "Europe",
    "north-america": "North America",
    "mexico-south-america": "Mexico - South America",
    "middle-east-africa": "Middle East - Africa",
    "global-indices": "Global Indices",
}

def country_to_csv_name(country: str) -> str:
    # CSV filenames are lowercase with hyphens
    return country.lower().replace(" ", "-") + ".csv"

def parse_path_parts(p: Path):
    # dist/<region>/<country>/<exchange>/<symbol>/prediction-tomorrow/index.html
    parts = [x for x in p.parts]
    try:
        i = parts.index(DIST_ROOT)
    except ValueError:
        i = next((k for k, s in enumerate(parts) if s.lower()=="dist"), -1)
    if i == -1 or len(parts) < i+6:
        return None
    region_slug = parts[i+1].lower()
    country = parts[i+2]
    exchange = parts[i+3]
    symbol_slug = parts[i+4]  # folder name equals symbol slug
    return {
        "region_slug": region_slug,
        "region_data": REGION_MAP.get(region_slug, region_slug),
        "country": country,
        "exchange": exchange,
        "symbol_upper": symbol_slug.upper()
    }

# ---------- CSV cache ----------
class CSVCache:
    def __init__(self, base: Path):
        self.base = base
        self.cache = {}  # (region_data, country_csv) -> list of rows
        self.index = {}  # (region_data, country_csv) -> {symbol_upper: row}
        self.country_last_date = {}  # fallback date if row has no date

    @staticmethod
    def _normalize_headers(headers):
        # Normalize headers: lower, remove spaces/underscores, map '%' → 'pct'
        # So "Change%" becomes "changepct"
        return [h.strip().lower().replace(" ", "").replace("_", "").replace("%", "pct") for h in headers]

    @staticmethod
    def _float_or_none(v):
        if v is None: return None
        s = str(v).replace(",", "").strip()
        if s == "": return None
        try: return float(s)
        except Exception: return None

    @staticmethod
    def _parse_pct(v):
        if v is None: return None
        s = str(v).strip().replace("%","").replace(",","")
        if s == "": return None
        try:
            num = float(s)
        except Exception:
            return None
        # Treat <=1 as likely fraction; multiply to %
        if abs(num) <= 1.0:
            num *= 100.0
        return round(num, 2)

    def _row_to_obj(self, headers_norm, row_vals):
        raw = {k:v for k,v in zip(headers_norm, row_vals)}
        def get(*names, default=""):
            for n in names:
                if n in raw and raw[n] not in (None,""):
                    return raw[n]
            return default

        symbol  = str(get("symbol","ticker")).strip().upper()
        exchange= str(get("exchange","exch")).strip().lower()
        date    = str(get("date","lastdate","tradingdate")).strip()

        o = number_str(get("open","o"))
        h = number_str(get("high","h"))
        l = number_str(get("low","l"))
        c = number_str(get("close","c","last"))

        # percent candidates (after normalization "Change%" -> "changepct")
        pct_keys = [
            "changepct","changepercent","percentchange","pctchange",
            "changepercentage","changeperc","change_pct",
            "pchange","chgpct","chgpercent","chgperc",
            "daychangepct","daychangepct"
        ]
        chg_pct = None
        for k in pct_keys:
            if k in raw and str(raw[k]).strip()!="":
                chg_pct = self._parse_pct(raw[k]); break

        # compute from prev/abs if needed
        if chg_pct is None:
            prev = self._float_or_none(get("prevclose","previousclose","pclose","pc","yclose","prev"))
            close_f = self._float_or_none(c)
            if close_f is not None and prev not in (None,0):
                chg_pct = round((close_f - prev) / prev * 100.0, 2)
            else:
                abschg = self._float_or_none(get("change","chg","daychange","pricechange","changevalue","chgvalue"))
                if abschg is not None and close_f not in (None,0):
                    prev_est = close_f - abschg
                    if prev_est:
                        chg_pct = round((close_f - prev_est) / prev_est * 100.0, 2)

        return {
            "symbol": symbol, "exchange": exchange, "date": date,
            "o": o, "h": h, "l": l, "c": c, "chg_pct": chg_pct
        }

    def _load(self, region_folder: str, country_csv: str):
        key = (region_folder, country_csv)
        if key in self.cache: return
        fp = self.base / region_folder / country_csv
        rows = []
        idx = {}
        last_date = ""
        if fp.exists():
            with fp.open("r", encoding="utf-8", newline="") as f:
                rr = csv.reader(f)
                rows_all = list(rr)
            if rows_all:
                headers_norm = self._normalize_headers(rows_all[0])
                for r in rows_all[1:]:
                    obj = self._row_to_obj(headers_norm, r)
                    rows.append(obj)
                    if obj["symbol"]:
                        idx[obj["symbol"]] = obj
                    if obj["date"]:
                        last_date = obj["date"]
        self.cache[key] = rows
        self.index[key] = idx
        self.country_last_date[key] = last_date

    def lookup(self, region_folder: str, country_csv: str, symbol_upper: str):
        self._load(region_folder, country_csv)
        key = (region_folder, country_csv)
        return self.index[key].get(symbol_upper), self.country_last_date.get(key,"")

CSV = CSVCache(DATA_ROOT)

# ---------- THEME (unchanged) ----------
CSS = r"""
:root {
  --blue:#2563eb; --blue-weak:#dbeafe;
  --green1:#16a34a; --green2:#22c55e;
  --red1:#ef4444; --red2:#f87171;
  --green-deep:#15803d; --red-deep:#b91c1c;
  --border:#e5e7eb; --bg:#f9fafb; --text:#111827;
  --shadow:0 1px 4px rgba(0,0,0,0.06);
  --shadow-lg:0 10px 30px rgba(0,0,0,.06);
}
*{box-sizing:border-box}
body { background:var(--bg); color:var(--text); font:16px/1.45 system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Inter", sans-serif; margin:0; padding:20px; }
.wrap { max-width:1100px; margin:0 auto; }

a { color:var(--blue); text-decoration:none; }
a:hover { text-decoration:underline; }

.badge { display:inline-block; background:#fef08a; color:#78350f; border-radius:10px; padding:6px 10px; font-weight:700; margin-right:10px; font-size:14px; box-shadow:var(--shadow); }

.header {
  display:flex; align-items:flex-start; gap:14px;
  background:white; border:1px solid var(--border); border-radius:12px; padding:14px 18px; box-shadow:var(--shadow);
}
.header .title { font-weight:800; font-size:20px; }
.header .sub { font-size:13px; opacity:.7; }
.header .ohlc-line { margin-top:6px; font-size:13px; font-weight:700; color:#0f172a; }

.banner { margin:18px 0; border-radius:14px; padding:22px; color:#fff; box-shadow:var(--shadow-lg); }
.banner.green { background:linear-gradient(180deg,var(--green1),var(--green2)); }
.banner.red { background:linear-gradient(180deg,var(--red1),var(--red2)); }
.banner .t { opacity:.95; margin-bottom:8px; }
.banner .signal { font-size:48px; font-weight:900; margin:6px 0; display:flex; align-items:center; gap:10px; }

.grid3 { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin:16px 0; }
.card {
  background:#fff; border:1px solid var(--border); border-radius:12px; padding:16px;
  box-shadow:var(--shadow); position:relative; overflow:hidden; transition:.25s transform, .25s box-shadow;
}
.card:hover{ transform:translateY(-2px); box-shadow:0 14px 30px rgba(0,0,0,.07); }
.card::before{
  content:""; position:absolute; left:0; top:0; width:100%; height:4px; background:linear-gradient(90deg,var(--blue),#60a5fa);
}
.card h4 { margin:6px 0 10px 0; font-size:14px; color:var(--blue); font-weight:800; }
.card .big { font-size:28px; font-weight:900; color:#15803d; }
.card .note { font-size:13px; opacity:.85; }

.table-card { background:#fff; border:1px solid var(--border); border-radius:12px; padding:8px 0 16px 0; box-shadow:var(--shadow); }
.table-card h3 { margin:12px 16px; color:#2563eb; font-weight:800; }

.table { width:100%; border-collapse:collapse; }
.table th, .table td { padding:12px 14px; border-top:1px solid var(--border); }
.table th { font-size:13px; text-align:left; opacity:.9; }
.win { background:#dcfce7; color:#15803d; padding:3px 8px; border-radius:6px; font-weight:700; }
.loss { background:#fee2e2; color:#b91c1c;  padding:3px 8px; border-radius:6px; font-weight:700; }

.footer-card { background:#fff; border:1px solid var(--border); border-radius:12px; padding:16px; margin:18px 0; box-shadow:var(--shadow); }
.footer-card h3{ color:#2563eb; font-weight:800; margin:0 0 8px 0; }
.footer-card .note { font-size:13px; opacity:.9; }
"""

HTML = """{stamp}
<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{page_title}</title>
<style>{css}</style>
</head><body>
<div class="wrap">

  <div class="header">
    <span class="badge">{symbol}</span>
    <div class="header-col">
      <div class="title">{full_name} ({symbol})</div>
      <div class="sub">Next-day stock movement • Last build: {build_time}</div>
      <div class="ohlc-line">Date: {last_date} • O {o} H {h} L {l} C {c} • % Change {chg}</div>
    </div>
  </div>

  <div class="banner {banner_class}">
    <div class="t">AI Prediction: <b>{full_name}</b> for <b>{pred_date}</b></div>
    <div class="signal">{banner_arrow} {signal}</div>
  </div>

  <div class="grid3">
    <div class="card">
      <h4>Model Performance</h4>
      <div class="big">{acc_pct}</div>
      <div class="note">{acc_note}</div>
    </div>
    <div class="card">
      <h4>Our Methodology</h4>
      <div class="note">We analyze 50+ factors including volume, momentum (RSI, MACD), and key support levels using our deep learning model.</div>
    </div>
    <div class="card">
      <h4>Important Disclosures</h4>
      <div class="note">This is <b>not</b> financial advice. For informational purposes only. Trading carries inherent risk.</div>
    </div>
  </div>

  <div class="table-card">
    <h3>Model vs. Actual: Last 7 Days Performance</h3>
    {table_html}
  </div>

  <div class="footer-card">
    <h3>In-Depth Technical Analysis of {full_name}</h3>
    <div class="note">Our analysis leverages the latest market close data to determine the highest probability direction for the next trading day.</div>
  </div>

</div>
</body></html>
"""

# ---------- rebuild ----------
def rebuild_page(p: Path):
    html = p.read_text(encoding="utf-8")
    symbol, full_name = get_symbol_and_fullname(html)

    # defaults from HTML (safe fallback)
    last_date = get_max_table_date(html) or "—"
    o, h, l, c, chg = get_ohlc_and_change_from_html(html)

    parts = parse_path_parts(p)
    if parts:
        region_folder = parts["region_data"]
        country_csv = country_to_csv_name(parts["country"])
        sym_u = parts["symbol_upper"]

        row, country_last_date = CSV.lookup(region_folder, country_csv, sym_u)
        if row:
            last_date = row["date"] or country_last_date or last_date
            o = number_str(row["o"]); h = number_str(row["h"])
            l = number_str(row["l"]); c = number_str(row["c"])
            chg = pct_to_str(row["chg_pct"])

    # Banner date
    pred_date = get_prediction_date_explicit(html) or (next_weekday(last_date) if last_date and last_date!="—" else "—")

    signal = get_signal(html)
    acc_pct, acc_note = scrape_accuracy(html)
    table_html = build_table(html)

    out = HTML.format(
        stamp=STAMP,
        page_title=f"{full_name or symbol} Stock Prediction",
        css=CSS,
        symbol=escape(symbol or "—"),
        full_name=escape(full_name or "Stock"),
        build_time=dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        last_date=escape(last_date or "—"),
        o=o, h=h, l=l, c=c, chg=escape(chg or "—"),
        pred_date=escape(pred_date or "—"),
        signal=signal,
        banner_arrow=arrow_for(signal),
        banner_class=banner_class_for(signal),
        acc_pct=acc_pct, acc_note=acc_note,
        table_html=table_html
    )
    p.write_text(out, encoding="utf-8")
    print(f"[v2.5-csv] {p}")

def main():
    root = Path(DIST_ROOT)
    count = 0
    for f in root.rglob("index.html"):
        if "prediction-tomorrow" in str(f).replace("\\","/"):
            rebuild_page(f)
            count += 1
    print(f"[v2.5-csv] finished; pages rebuilt: {count}")

if __name__ == "__main__":
    main()
