# scripts/theme_rebuild_v2.py
# Rebuilds every prediction page into the "webpage.html" style and
# adds: full company name near symbol, close + change%, and a green/red banner
# with ▲/▼ arrow depending on Bullish/Bearish.

import os
import re
import datetime
from pathlib import Path
from html import escape

DIST_ROOT = "dist"
PRED_DIR = "prediction-tomorrow"
STAMP = f"<!-- v2-rebuild {datetime.datetime.utcnow().isoformat()}Z -->"

# ---------- Helpers: scraping existing HTML ----------

def one(re_pat, text, flags=re.I | re.S, group=1, default=""):
    m = re.search(re_pat, text, flags)
    return (m.group(group).strip() if m else default).strip()

def get_symbol_and_fullname(html):
    """
    Prefer the detail header like:
      AI Analysis of A2ZINFRA (A2Z Infra Engineering Limited)
    Fallback to H1:
      AI Analysis of 360 ONE WAM Limited (360ONE) Stock Prediction
    Returns (symbol, full_name)
    """
    # 1) From detailed H2 line
    sym = one(r"AI\s+Analysis\s+of\s+([A-Z0-9.\-]+)\s*\(", html)
    full = one(r"AI\s+Analysis\s+of\s+[A-Z0-9.\-]+\s*\(([^)]+)\)", html)

    if not full:
        # 2) From H1 if it has "(SYMBOL)"
        h1 = one(r"<h1[^>]*>(.*?)</h1>", html)
        clean = re.sub(r"<[^>]+>", "", h1)
        # e.g., "AI Analysis of 360 ONE WAM Limited (360ONE) | ..."
        full = one(r"AI\s+Analysis\s+of\s+(.+?)\s+\(", clean, default="")
        sym2 = one(r"\(([^)]+)\)", clean, default="")
        if full and not sym:
            sym = sym2

    return sym or "", full or ""

def get_prediction_date(html):
    return one(r"Prediction\s+for\s+([0-9]{4}-[0-9]{2}-[0-9]{2})", html, default="—")

def get_ohlc_and_change(html):
    """
    Returns: (o,h,l,c,chg)
    """
    o = h = l = c = chg = "—"
    m = re.search(r"OHLC:\s*O\s*([0-9.,\-]+).*?H\s*([0-9.,\-]+).*?L\s*([0-9.,\-]+).*?C\s*([0-9.,\-]+)",
                  html, re.I | re.S)
    if m:
        o, h, l, c = [x.replace(",", "") for x in m.groups()]
    k = re.search(r"Change%[:\s]*([+\-]?[0-9.]+%)", html, re.I)
    if k:
        chg = k.group(1)
    return o, h, l, c, chg

def get_signal(html):
    """
    Try first visible table rows under 'Last 7-Day Performance' -> 'AI Prediction'.
    Return 'Bullish'/'Bearish'/'—'
    """
    tb = one(r"<table[^>]*>.*?<thead.*?</thead>.*?<tbody[^>]*>(.*?)</tbody>",
             html, group=1, default="")
    if tb:
        r = re.search(r"<tr[^>]*>.*?<td[^>]*>.*?</td>.*?<td[^>]*>(Bullish|Bearish)</td>",
                      tb, re.I | re.S)
        if r:
            return r.group(1).title()
    return "—"

# ---------- HTML/CSS ----------

CSS = r"""
/* v2 rebuild */
:root{
  --bg:#0b1220; --card:#0f172a; --muted:#9fb3c8; --text:#e6edf6;
  --ring:rgba(148,163,184,.3);
  --green1:#10b981; --green2:#059669;
  --red1:#ef4444; --red2:#b91c1c;
}
body{background:var(--bg);color:var(--text);font:16px/1.45 Inter,system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;padding:28px}
a{color:#93c5fd;text-decoration:none} a:hover{text-decoration:underline}
.wrap{max-width:1100px;margin:0 auto}
.badge{display:inline-block;background:#fde68a;color:#78350f;border-radius:12px;padding:6px 10px;font-weight:700;margin-right:10px;font-size:14px;vertical-align:middle}
.price-chip{margin-left:auto;background:#0b1a2f;color:#b6ffe3;border:1px solid var(--ring);border-radius:10px;padding:10px 14px;display:flex;gap:12px;align-items:center}
.price-chip .px{font-size:20px;font-weight:800}
.header{display:flex;align-items:center;gap:14px;background:var(--card);border:1px solid var(--ring);padding:16px 18px;border-radius:14px}
.header .title{font-weight:800;font-size:22px;letter-spacing:.2px}
.header .sub{opacity:.75;font-size:13px;margin-top:2px}
.header-col{display:flex;flex-direction:column}
.flex{display:flex;gap:14px;align-items:center}

.banner{margin:18px 0;border-radius:16px;padding:22px;border:1px solid var(--ring);box-shadow:0 8px 30px rgba(0,0,0,.25) inset 0 0 0 1px rgba(255,255,255,.03)}
.banner.green{background:linear-gradient(180deg,var(--green1),var(--green2))}
.banner.red{background:linear-gradient(180deg,var(--red1),var(--red2))}
.banner .t{opacity:.9}
.banner .signal{font-size:56px;line-height:1.06;font-weight:900;letter-spacing:.5px;color:#fff;margin:10px 0}
.banner .pill{display:inline-block;background:rgba(255,255,255,.12);color:#def7ec;border-radius:999px;padding:6px 10px;font-weight:800;font-size:12px;margin-right:8px}
.banner .ohlc{display:inline-flex;gap:12px;background:rgba(255,255,255,.11);padding:10px 14px;border-radius:12px;color:#fff;font-weight:600}

.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:16px 0}
.card{background:var(--card);border:1px solid var(--ring);border-radius:14px;padding:16px}
.card h4{margin:0 0 8px 0;font-size:14px;letter-spacing:.4px;opacity:.9}
.card .big{font-size:28px;font-weight:900}
.card .note{opacity:.7;font-size:12px}

.table-card{background:var(--card);border:1px solid var(--ring);border-radius:14px;padding:4px 0;margin:18px 0}
.table-card h3{margin:12px 16px}
.table{width:100%;border-collapse:collapse}
.table th,.table td{padding:12px 14px;border-top:1px solid var(--ring)}
.table th{font-size:13px;letter-spacing:.3px;text-align:left;opacity:.9}
.win{background:#052e1a;color:#86efac}
.loss{background:#2a0b0b;color:#fecaca}

.footer-card{background:var(--card);border:1px solid var(--ring);border-radius:14px;padding:16px;margin:18px 0}
"""

HTML_SHELL = """{stamp}
<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{page_title}</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">

  <!-- HEADER -->
  <div class="header">
    <span class="badge">{symbol}</span>
    <div class="header-col">
      <div class="title">{full_name} ({symbol})</div>
      <div class="sub">Next-day stock movement from yesterday’s OHLC • Last build: {build_time}</div>
    </div>
    <div class="price-chip">
      <div class="px">{close_px}</div>
      <div class="chg">{chg}</div>
    </div>
  </div>

  <!-- BANNER -->
  <div class="banner {banner_class}">
    <div class="t">AI Prediction: <b>{full_name}</b> for <b>{pred_date}</b></div>
    <div class="signal">{arrow} {signal}</div>
    <div class="ohlc">OHLC: <span>O {o}</span><span>H {h}</span><span>L {l}</span><span>C {c}</span></div>
  </div>

  <!-- 3-UP -->
  <div class="grid3">
    <div class="card">
      <h4>Model Performance</h4>
      <div class="big">{acc_pct}</div>
      <div class="note">{acc_note}</div>
    </div>
    <div class="card">
      <h4>Our Methodology</h4>
      <div class="note">We analyze 50+ features including volume, momentum (RSI, MACD), and key support levels via our deep learning model.</div>
    </div>
    <div class="card">
      <h4>Important Disclosures</h4>
      <div class="note">This is <b>not</b> financial advice. For educational purposes only. Trading carries inherent risk.</div>
    </div>
  </div>

  <!-- TABLE -->
  <div class="table-card">
    <h3>Model vs. Actual: Last 7 Days Performance</h3>
    {table_html}
  </div>

  <!-- ANALYSIS -->
  <div class="footer-card">
    <h3>In-Depth Technical Analysis of {full_name}</h3>
    <div class="note">Our analysis leverages the latest market close data to determine the highest probability direction for the next trading day.</div>
  </div>

</div>
</body></html>
"""

def build_table(html):
    """
    Pull the existing 7-day table rows to keep your computed data intact.
    """
    table = one(r"(<table[^>]*>.*?</table>)", html, group=1, default="")
    if not table:
        # fallback: construct a minimal shell so page remains valid
        return ('<table class="table">'
                '<thead><tr><th>Date</th><th>AI Prediction</th><th>Actual</th><th>Result</th></tr></thead>'
                '<tbody><tr><td>—</td><td>—</td><td>—</td><td>—</td></tr></tbody></table>')
    # apply our classes to wins/losses
    table = re.sub(r">Win<", r'><span class="win">Win</span><', table, flags=re.I)
    table = re.sub(r">Loss<", r'><span class="loss">Loss</span><', table, flags=re.I)
    # also ensure our table class is applied
    table = re.sub(r"<table([^>]*)>", r'<table class="table"\1>', table, count=1, flags=re.I)
    return table

def scrape_accuracy(html):
    """
    Pull the green chip like '71.43% (5/7)' if present.
    """
    chip = one(r"([0-9]{1,3}\.[0-9]{2}%\s*\([0-9]+/[0-9]+\))", html, default="")
    return (chip or "—"), ("Last 7-Day Accuracy" if chip else "Accuracy unavailable")

def arrow_for(signal):
    if signal.lower() == "bullish":
        return "▲"
    if signal.lower() == "bearish":
        return "▼"
    return "—"

def banner_class_for(signal):
    return "green" if signal.lower() == "bullish" else ("red" if signal.lower() == "bearish" else "")

# ---------- Main rebuild ----------

def rebuild_page(src_path: Path):
    raw = src_path.read_text(encoding="utf-8")

    symbol, full_name = get_symbol_and_fullname(raw)
    pred_date = get_prediction_date(raw)
    o, h, l, c, chg = get_ohlc_and_change(raw)
    signal = get_signal(raw)
    acc_pct, acc_note = scrape_accuracy(raw)
    table_html = build_table(raw)

    # Build meta
    close_px = c if c != "—" else ""
    page_title = f"{full_name or symbol} Stock Prediction"

    html = HTML_SHELL.format(
        stamp=STAMP,
        page_title=escape(page_title),
        css=CSS,
        symbol=escape(symbol or "—"),
        full_name=escape(full_name or "Stock"),
        build_time=datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        close_px=escape(close_px or "—"),
        chg=escape(chg or ""),
        pred_date=escape(pred_date),
        o=escape(o), h=escape(h), l=escape(l), c=escape(c),
        signal=escape(signal),
        arrow=arrow_for(signal),
        banner_class=banner_class_for(signal),
        acc_pct=escape(acc_pct),
        acc_note=escape(acc_note),
        table_html=table_html
    )

    src_path.write_text(html, encoding="utf-8")
    print(f"[v2] rebuilt: {src_path}")

def main():
    root = Path(DIST_ROOT)
    count = 0
    for p in root.rglob("index.html"):
        if p.parent.name == PRED_DIR:
            rebuild_page(p)
            count += 1
    print(f"[v2] total rebuilt pages: {count}")

if __name__ == "__main__":
    main()
