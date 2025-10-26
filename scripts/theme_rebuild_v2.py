# scripts/theme_rebuild_v2.py
# Light UI (v2.2):
# - Header line shows LAST trading day's Date + OHLC + %Change (date sourced from 7-day table max date).
# - Banner shows ONLY "AI Prediction: {Full Name} for {Next trading date}".
# - No right-side price chip. No OHLC in banner.

import re
import datetime as dt
from pathlib import Path
from html import escape

DIST_ROOT = "dist"
STAMP = f"<!-- v2-rebuild-light {dt.datetime.now(dt.timezone.utc).isoformat()} -->"

# ---------- helpers ----------
def rx(pat, s, flags=re.I | re.S, group=1, default=""):
    m = re.search(pat, s, flags)
    return (m.group(group).strip() if m else default).strip()

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
    # Primary: your existing "Prediction for YYYY-MM-DD"
    d = rx(r"Prediction\s+for\s+([0-9]{4}-[0-9]{2}-[0-9]{2})", html, default="")
    if d:
        return d
    # Common alternates:
    d = rx(r"Next\s*(?:Trading\s*)?Day\s*[:\-]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", html, default="")
    if d:
        return d
    d = rx(r"AI\s+Prediction\s*[:\-]\s*.*?\b([0-9]{4}-[0-9]{2}-[0-9]{2})\b", html, default="")
    return d or ""

def next_weekday(iso_date: str) -> str:
    # Fallback: compute next Mon–Fri date (no holiday calendar).
    try:
        d = dt.date.fromisoformat(iso_date)
    except Exception:
        return "—"
    while True:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:  # 0=Mon .. 4=Fri
            return d.isoformat()

def extract_table_block(html: str) -> str:
    return rx(r"(<table[^>]*>.*?</table>)", html, group=1, default="")

def get_max_table_date(html: str) -> str:
    """
    Extract all YYYY-MM-DD inside the 7-day table and return the max (LAST trading day).
    Safer than scanning the whole doc (avoids picking the prediction date).
    """
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

def get_last_trading_date(html: str) -> str:
    """
    Priority:
    1) From 7-day table (max date) — usually the true last trading day.
    2) Gentle fallbacks for older pages.
    """
    d = get_max_table_date(html)
    if d:
        return d
    # Fallback patterns (kept conservative)
    pats = [
        r"(?:As\s*of|Last\s*Close|Date)\s*[:\-]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})",
        r"OHLC.{0,200}?(?:on|as\s*of|for)\s*([0-9]{4}-[0-9]{2}-[0-9]{2})",
    ]
    for p in pats:
        d = rx(p, html, default="")
        if d:
            return d
    return "—"

def get_ohlc_and_change(html: str):
    """
    Return (O, H, L, C, chg_str).
    - OHLC from the 'OHLC: O ... H ... L ... C ...' line.
    - % Change ONLY from explicit 'Change' labels (never from accuracy).
    """
    o = h = l = c = chg = "—"

    # 1) OHLC
    m = re.search(
        r"OHLC:\s*O\s*([0-9.,\-]+).*?H\s*([0-9.,\-]+).*?L\s*([0-9.,\-]+).*?C\s*([0-9.,\-]+)",
        html, re.I | re.S
    )
    if m:
        o, h, l, c = [g.strip().replace(",", "") for g in m.groups()]

    # 2) Limit search scope to BEFORE the accuracy/cards to avoid grabbing '42.86% (3/7)'
    cutoff_idx = len(html)
    for marker in ("Model Performance", "Last 7-Day Accuracy", "Model vs. Actual"):
        i = html.lower().find(marker.lower())
        if i != -1:
            cutoff_idx = min(cutoff_idx, i)
    scope = html[:cutoff_idx]

    # 3) % Change — match only labeled variants (no generic percent grabs)
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
        if r:
            return r.group(1).title()
    return "—"

def arrow_for(signal: str):
    return "▲" if signal.lower() == "bullish" else ("▼" if signal.lower() == "bearish" else "—")

def banner_class_for(signal: str):
    return "green" if signal.lower() == "bullish" else ("red" if signal.lower() == "bearish" else "")

def scrape_accuracy(html: str):
    chip = rx(r"([0-9]{1,3}\.[0-9]{2}%\s*\([0-9]+/[0-9]+\))", html, default="")
    return (chip or "—"), ("Last 7-Day Accuracy" if chip else "Accuracy unavailable")

def build_table(html: str):
    table = rx(r"(<table[^>]*>.*?</table>)", html, group=1, default="")
    if not table:
        return ('<table class="table"><thead><tr><th>Date</th><th>AI Prediction</th>'
                '<th>Actual</th><th>Result</th></tr></thead>'
                '<tbody><tr><td>—</td><td>—</td><td>—</td><td>—</td></tr></tbody></table>')
    table = re.sub(r">Win<",  r'><span class="win">Win</span><',  table, flags=re.I)
    table = re.sub(r">Loss<", r'><span class="loss">Loss</span><', table, flags=re.I)
    table = re.sub(r"<table([^>]*)>", r'<table class="table"\1>', table, count=1, flags=re.I)
    return table

# ---------- LIGHT THEME CSS ----------
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

# ---------- page template ----------
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

# ---------- main rebuild ----------
def rebuild_page(p: Path):
    html = p.read_text(encoding="utf-8")

    # Names
    symbol, full_name = get_symbol_and_fullname(html)

    # LAST trading date from the table (robust) + OHLC / Change%
    last_date = get_last_trading_date(html)
    o, h, l, c, chg = get_ohlc_and_change(html)

    # NEXT trading date (banner): read explicit, else compute from last_date
    pred_date = get_prediction_date_explicit(html) or (next_weekday(last_date) if last_date and last_date != "—" else "—")

    # Signal + accuracy + table
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

        # Header (LAST trading day)
        last_date=escape(last_date or "—"),
        o=o, h=h, l=l, c=c, chg=escape(chg or "—"),

        # Banner (NEXT trading day)
        pred_date=escape(pred_date or "—"),
        signal=signal,
        banner_arrow=arrow_for(signal),
        banner_class=banner_class_for(signal),

        # Cards + table
        acc_pct=acc_pct, acc_note=acc_note,
        table_html=table_html
    )
    p.write_text(out, encoding="utf-8")
    print(f"[v2-light] rebuilt: {p}")

def main():
    root = Path(DIST_ROOT)
    count = 0
    for f in root.rglob("index.html"):
        if "prediction-tomorrow" in str(f):
            rebuild_page(f)
            count += 1
    print(f"[v2-light] total rebuilt pages: {count}")

if __name__ == "__main__":
    main()
