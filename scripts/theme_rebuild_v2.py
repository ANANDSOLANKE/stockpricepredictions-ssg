# scripts/theme_rebuild_v2.py
# Final light-theme rebuild: adds %change beside close price, returns to white background
# and keeps all other logic (symbol, name, green/red signal, etc.)

import os, re, datetime
from pathlib import Path
from html import escape

DIST_ROOT = "dist"
STAMP = f"<!-- v2-rebuild-light {datetime.datetime.utcnow().isoformat()}Z -->"

def rx(p, s, flags=re.I|re.S, group=1, default=""):
    m = re.search(p, s, flags)
    return (m.group(group).strip() if m else default).strip()

def get_symbol_and_fullname(html):
    sym = rx(r"AI\s+Analysis\s+of\s+([A-Z0-9.\-]+)\s*\(", html)
    full = rx(r"AI\s+Analysis\s+of\s+[A-Z0-9.\-]+\s*\(([^)]+)\)", html)
    if not full:
        h1 = rx(r"<h1[^>]*>(.*?)</h1>", html)
        clean = re.sub(r"<[^>]+>", "", h1)
        full = rx(r"AI\s+Analysis\s+of\s+(.+?)\s+\(", clean)
        sym2 = rx(r"\(([^)]+)\)", clean)
        if full and not sym: sym = sym2
    return sym or "", full or ""

def get_prediction_date(html):
    return rx(r"Prediction\s+for\s+([0-9]{4}-[0-9]{2}-[0-9]{2})", html, default="—")

def get_ohlc_and_change(html):
    o = h = l = c = chg = "—"
    m = re.search(r"OHLC:\s*O\s*([0-9.,\-]+).*?H\s*([0-9.,\-]+).*?L\s*([0-9.,\-]+).*?C\s*([0-9.,\-]+)",
                  html, re.I|re.S)
    if m:
        o, h, l, c = [g.replace(",", "") for g in m.groups()]
    k = re.search(r"Change%[:\s]*([+\-]?[0-9.]+%)", html, re.I)
    if k: chg = k.group(1)
    return o, h, l, c, chg

def get_signal(html):
    tb = rx(r"<table[^>]*>.*?<thead.*?</thead>.*?<tbody[^>]*>(.*?)</tbody>", html, group=1, default="")
    if tb:
        r = re.search(r"<tr[^>]*>.*?<td[^>]*>.*?</td>.*?<td[^>]*>(Bullish|Bearish)</td>", tb, re.I|re.S)
        if r: return r.group(1).title()
    return "—"

def arrow_for(signal):
    return "▲" if signal.lower()=="bullish" else ("▼" if signal.lower()=="bearish" else "—")

def banner_class_for(signal):
    return "green" if signal.lower()=="bullish" else ("red" if signal.lower()=="bearish" else "")

def scrape_accuracy(html):
    chip = rx(r"([0-9]{1,3}\.[0-9]{2}%\s*\([0-9]+/[0-9]+\))", html, default="")
    return (chip or "—"), ("Last 7-Day Accuracy" if chip else "Accuracy unavailable")

def build_table(html):
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
  --green1:#16a34a; --green2:#22c55e;
  --red1:#ef4444; --red2:#f87171;
  --border:#e5e7eb; --bg:#f9fafb; --text:#111827;
}
body { background:var(--bg); color:var(--text); font:16px/1.45 'Inter',system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif; margin:0; padding:20px; }
.wrap { max-width:1100px; margin:0 auto; }
a { color:#2563eb; text-decoration:none; }
a:hover { text-decoration:underline; }
.badge { display:inline-block; background:#fef08a; color:#78350f; border-radius:10px; padding:6px 10px; font-weight:700; margin-right:10px; font-size:14px; }
.header { display:flex; align-items:center; gap:14px; background:white; border:1px solid var(--border); border-radius:12px; padding:14px 18px; box-shadow:0 1px 4px rgba(0,0,0,0.06); }
.header .title { font-weight:800; font-size:20px; }
.header .sub { font-size:13px; opacity:.7; }
.price-chip { margin-left:auto; background:#ecfdf5; border:1px solid #d1fae5; border-radius:10px; padding:10px 14px; display:flex; gap:8px; align-items:center; font-weight:700; color:#065f46; }
.price-chip .chg.positive { color:#15803d; }
.price-chip .chg.negative { color:#b91c1c; }
.banner { margin:18px 0; border-radius:14px; padding:22px; color:#fff; }
.banner.green { background:linear-gradient(180deg,var(--green1),var(--green2)); }
.banner.red { background:linear-gradient(180deg,var(--red1),var(--red2)); }
.banner .signal { font-size:52px; font-weight:900; margin:10px 0; }
.banner .ohlc { background:rgba(255,255,255,.15); padding:8px 12px; border-radius:10px; display:inline-flex; gap:12px; font-weight:600; }
.grid3 { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin:16px 0; }
.card { background:#fff; border:1px solid var(--border); border-radius:12px; padding:16px; box-shadow:0 1px 3px rgba(0,0,0,0.05); }
.card h4 { margin:0 0 8px 0; font-size:14px; color:#374151; }
.card .big { font-size:26px; font-weight:900; color:#111827; }
.card .note { font-size:13px; opacity:.8; }
.table-card { background:#fff; border:1px solid var(--border); border-radius:12px; padding:8px 0; box-shadow:0 1px 3px rgba(0,0,0,0.05); }
.table-card h3 { margin:12px 16px; }
.table { width:100%; border-collapse:collapse; }
.table th, .table td { padding:12px 14px; border-top:1px solid var(--border); }
.table th { font-size:13px; text-align:left; opacity:.9; }
.win { background:#dcfce7; color:#166534; padding:3px 8px; border-radius:6px; font-weight:600; }
.loss { background:#fee2e2; color:#b91c1c; padding:3px 8px; border-radius:6px; font-weight:600; }
.footer-card { background:#fff; border:1px solid var(--border); border-radius:12px; padding:16px; margin:18px 0; box-shadow:0 1px 3px rgba(0,0,0,0.05); }
"""

# ---------- HTML TEMPLATE ----------
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
    </div>
    <div class="price-chip">
      <div class="px">{close_px}</div>
      <div class="chg {chg_class}">{chg}</div>
    </div>
  </div>

  <div class="banner {banner_class}">
    <div class="t">AI Prediction: <b>{full_name}</b> for <b>{pred_date}</b></div>
    <div class="signal">{arrow} {signal}</div>
    <div class="ohlc">O {o} H {h} L {l} C {c}</div>
  </div>

  <div class="grid3">
    <div class="card"><h4>Model Performance</h4><div class="big">{acc_pct}</div><div class="note">{acc_note}</div></div>
    <div class="card"><h4>Our Methodology</h4><div class="note">We analyze 50+ factors including volume, momentum (RSI, MACD), and key support levels using our deep learning model.</div></div>
    <div class="card"><h4>Important Disclosures</h4><div class="note">This is <b>not</b> financial advice. For informational purposes only. Trading carries inherent risk.</div></div>
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

# ---------- MAIN ----------
def rebuild_page(p: Path):
    html = p.read_text(encoding="utf-8")
    symbol, full_name = get_symbol_and_fullname(html)
    pred_date = get_prediction_date(html)
    o, h, l, c, chg = get_ohlc_and_change(html)
    signal = get_signal(html)
    acc_pct, acc_note = scrape_accuracy(html)
    table_html = build_table(html)
    close_px = c if c != "—" else "—"
    chg_class = "positive" if chg.startswith("+") else ("negative" if chg.startswith("-") else "")
    out = HTML.format(
        stamp=STAMP,
        page_title=f"{full_name or symbol} Stock Prediction",
        css=CSS,
        symbol=escape(symbol or "—"),
        full_name=escape(full_name or "Stock"),
        build_time=datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        close_px=escape(close_px),
        chg=escape(chg),
        chg_class=chg_class,
        pred_date=escape(pred_date),
        o=o, h=h, l=l, c=c,
        signal=signal, arrow=arrow_for(signal),
        banner_class=banner_class_for(signal),
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
