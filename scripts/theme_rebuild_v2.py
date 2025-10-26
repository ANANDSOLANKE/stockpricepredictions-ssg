# scripts/theme_rebuild_v2.py
# Light UI + 100% CSV-driven OHLC & Change% using FIRST TWO COLUMNS (symbol, description).
# Strict matching: (symbol, description) → exact; fallback to unique symbol-only.
# No computed % change. Uses Data/LastTradingDay as the source of truth.

import csv
import re
import datetime as dt
from pathlib import Path
from html import escape

DIST_ROOT = "dist"
DATA_LAST_TRADING_DAY = "Data/LastTradingDay"
STAMP = f"<!-- v2-rebuild-light {dt.datetime.now(dt.timezone.utc).isoformat()} -->"

# ------------- helpers -------------
def rx(pat, s, flags=re.I | re.S, group=1, default=""):
    m = re.search(pat, s, flags)
    return (m.group(group).strip() if m else default).strip()

def norm_desc(s: str) -> str:
    """Normalize descriptions so matching is robust."""
    if not s:
        return ""
    s = s.lower()
    # common noise words
    repl = [
        ("&", " and "),
        ("limited", " "),
        ("ltd", " "),
        ("public", " "),
        ("company", " "),
        ("co.", " "),
        ("co ", " "),
        ("plc", " "),
        ("inc.", " "),
        ("inc", " "),
        ("corp.", " "),
        ("corporation", " "),
    ]
    for a, b in repl:
        s = s.replace(a, b)
    # drop punctuation/spaces
    s = re.sub(r"[^\w]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def get_symbol_and_fullname(html: str):
    # Try: "AI Analysis of 20MICRONS (20 Microns Limited) ..."
    sym = rx(r"AI\s+Analysis\s+of\s+([A-Z0-9.\-]+)\s*\(", html)
    full = rx(r"AI\s+Analysis\s+of\s+[A-Z0-9.\-]+\s*\(([^)]+)\)", html)
    if not full:
        # fallback: pull from <h1> if present
        h1 = rx(r"<h1[^>]*>(.*?)</h1>", html)
        clean = re.sub(r"<[^>]+>", "", h1)
        full = rx(r"AI\s+Analysis\s+of\s+(.+?)\s+\(", clean)
        sym2 = rx(r"\(([^)]+)\)", clean)
        if full and not sym:
            sym = sym2
    return (sym or "").strip(), (full or "").strip()

def get_prediction_date(html):
    return rx(r"Prediction\s+for\s+([0-9]{4}-[0-9]{2}-[0-9]{2})", html, default="—")

def get_signal(html):
    tb = rx(r"<table[^>]*>.*?<thead.*?</thead>.*?<tbody[^>]*>(.*?)</tbody>", html, group=1, default="")
    if tb:
        r = re.search(r"<tr[^>]*>.*?<td[^>]*>.*?</td>.*?<td[^>]*>(Bullish|Bearish)</td>", tb, re.I|re.S)
        if r:
            return r.group(1).title()
    return "—"

def arrow_for(signal):
    return "▲" if signal.lower() == "bullish" else ("▼" if signal.lower() == "bearish" else "•")

def banner_class_for(signal):
    return "green" if signal.lower() == "bullish" else ("red" if signal.lower() == "bearish" else "")

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

# ------------- CSV Index (symbol, description → row) -------------
# We assume FIRST TWO COLUMNS are: symbol, description
# We then read the rest but only rely on dedicated headers if present: Open, High, Low, Close, Change%
CSV_BY_SYM_DESC = {}     # key: (sym_upper, norm_desc(description)) -> row dict
CSV_BY_SYM = {}          # key: sym_upper -> list[row dict]

CSV_OPEN_KEYS  = ["open", "o"]
CSV_HIGH_KEYS  = ["high", "h"]
CSV_LOW_KEYS   = ["low", "l"]
CSV_CLOSE_KEYS = ["close", "c", "last", "close price"]
CSV_CHG_KEYS   = ["change%", "change %", "pct_change", "percent_change", "pct%", "% change"]

def pick_col(row: dict, keys):
    for k in row.keys():
        if k is None:
            continue
        kl = k.strip().lower()
        if kl in keys:
            return row[k]
    # If headers are positional/named oddly, try numeric-like extraction later
    return ""

def coerce_num(x):
    if x is None:
        return ""
    s = str(x).strip().replace(",", "")
    if s in ("", "—", "-"):
        return ""
    return s

def coerce_pct(x):
    if x is None:
        return ""
    s = str(x).strip().replace(" ", "")
    if not s:
        return ""
    # accept forms like -0.10 or -0.10%
    s = s.replace(",", ".")
    if s.endswith("%"):
        return s
    # If it looks numeric, append %
    if re.match(r"^[+\-]?\d+(\.\d+)?$", s):
        return s + "%"
    return s

def read_all_lastday_csvs():
    root = Path(DATA_LAST_TRADING_DAY)
    if not root.exists():
        print(f"[WARN] {DATA_LAST_TRADING_DAY} not found — CSV override disabled.")
        return

    total = 0
    for csv_path in root.rglob("*.csv"):
        try:
            with csv_path.open("r", encoding="utf-8", newline="") as fh:
                reader = csv.reader(fh)
                rows = list(reader)
                if not rows:
                    continue

                # Build a header map if the file has one; otherwise synthesize indices
                header = [h.strip() if h else "" for h in rows[0]]
                has_header = False
                if len(header) >= 2:
                    # heuristic: first cell looks like a header if it isn't a typical symbol pattern
                    has_header = (header[0].lower() in ("symbol", "ticker", "code"))

                start_idx = 1 if has_header else 0

                # If we have a header row, we’ll build DictReader-style dicts
                if has_header:
                    # Lowercased header names for flexible lookups
                    header_l = [h.lower() for h in header]
                    for r in rows[start_idx:]:
                        if len(r) < 2:
                            continue
                        sym = (r[0] or "").strip()
                        desc = (r[1] or "").strip()
                        if not sym or not desc:
                            continue
                        rd = {header[i]: (r[i] if i < len(r) else "") for i in range(len(header))}
                        rd["_sym_"] = sym
                        rd["_desc_"] = desc
                        # keep a pre-resolved payload for speed
                        rd["_o_"] = coerce_num(pick_col(rd, CSV_OPEN_KEYS))
                        rd["_h_"] = coerce_num(pick_col(rd, CSV_HIGH_KEYS))
                        rd["_l_"] = coerce_num(pick_col(rd, CSV_LOW_KEYS))
                        rd["_c_"] = coerce_num(pick_col(rd, CSV_CLOSE_KEYS))
                        rd["_chg_"] = coerce_pct(pick_col(rd, CSV_CHG_KEYS))

                        key = (sym.upper(), norm_desc(desc))
                        CSV_BY_SYM_DESC[key] = rd
                        CSV_BY_SYM.setdefault(sym.upper(), []).append(rd)
                        total += 1
                else:
                    # No headers: assume columns:
                    # 0:symbol 1:description 2:exchange 3:sector 4:industry 5:open 6:high 7:low 8:close 9:Change%
                    for r in rows[start_idx:]:
                        if len(r) < 2:
                            continue
                        sym = (r[0] or "").strip()
                        desc = (r[1] or "").strip()
                        if not sym or not desc:
                            continue
                        rd = {
                            "_sym_": sym,
                            "_desc_": desc,
                            "open":  (r[5] if len(r) > 5 else ""),
                            "high":  (r[6] if len(r) > 6 else ""),
                            "low":   (r[7] if len(r) > 7 else ""),
                            "close": (r[8] if len(r) > 8 else ""),
                            "change%": (r[9] if len(r) > 9 else ""),
                        }
                        rd["_o_"] = coerce_num(rd["open"])
                        rd["_h_"] = coerce_num(rd["high"])
                        rd["_l_"] = coerce_num(rd["low"])
                        rd["_c_"] = coerce_num(rd["close"])
                        rd["_chg_"] = coerce_pct(rd["change%"])

                        key = (sym.upper(), norm_desc(desc))
                        CSV_BY_SYM_DESC[key] = rd
                        CSV_BY_SYM.setdefault(sym.upper(), []).append(rd)
                        total += 1

        except Exception as e:
            print(f"[WARN] Failed reading {csv_path}: {e}")

    print(f"[CSV] Indexed {total} rows from {root}")

def csv_lookup(sym: str, fullname: str):
    """
    Primary: (symbol, normalized description) exact match.
    Fallback: symbol-only match if it yields exactly one unique description row.
    Returns tuple (o,h,l,c,chg) or ("","","","","") if not found.
    """
    if not sym:
        return "", "", "", "", ""
    key = (sym.upper(), norm_desc(fullname))
    rd = CSV_BY_SYM_DESC.get(key)
    if rd:
        return rd["_o_"], rd["_h_"], rd["_l_"], rd["_c_"], rd["_chg_"]

    # Fallback to unique symbol
    cand = CSV_BY_SYM.get(sym.upper(), [])
    if len(cand) == 1:
        r = cand[0]
        return r["_o_"], r["_h_"], r["_l_"], r["_c_"], r["_chg_"]

    # If multiple with same symbol, try the best description distance (simple contains heuristic)
    if len(cand) > 1 and fullname:
        nfull = norm_desc(fullname)
        best = None
        best_score = -1
        for r in cand:
            nd = norm_desc(r.get("_desc_", ""))
            # score: length of overlap tokens
            overlap = len(set(nfull.split()) & set(nd.split()))
            if overlap > best_score:
                best = r
                best_score = overlap
        if best:
            return best["_o_"], best["_h_"], best["_l_"], best["_c_"], best["_chg_"]

    return "", "", "", "", ""

# ------------- LIGHT THEME CSS (unchanged) -------------
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
  display:flex; align-items:center; gap:14px;
  background:white; border:1px solid var(--border); border-radius:12px; padding:14px 18px; box-shadow:var(--shadow);
}
.header .title { font-weight:800; font-size:20px; }
.header .sub { font-size:13px; opacity:.7; }

.price-chip {
  margin-left:auto; background:#ffffff; border:1px solid var(--border);
  border-radius:10px; padding:10px 14px; display:flex; gap:10px; align-items:center;
  font-weight:800; color:var(--text); box-shadow:var(--shadow);
}
.price-chip .px{opacity:.9}
.price-chip .chg { padding:2px 8px; border-radius:999px; font-weight:800; }
.price-chip .chg.positive { background:#dcfce7; color:var(--green-deep); }
.price-chip .chg.negative { background:#fee2e2; color:#b91c1c; }
.price-chip .arr { font-size:15px; margin-right:4px; }

.banner { margin:18px 0; border-radius:14px; padding:22px; color:#fff; box-shadow:var(--shadow-lg); }
.banner.green { background:linear-gradient(180deg,var(--green1),var(--green2)); }
.banner.red { background:linear-gradient(180deg,var(--red1),var(--red2)); }
.banner .t { opacity:.95; margin-bottom:8px; }
.banner .signal { font-size:48px; font-weight:900; margin:6px 0; display:flex; align-items:center; gap:10px; }
.banner .ohlc { background:rgba(255,255,255,.15); padding:8px 12px; border-radius:10px; display:inline-flex; gap:12px; font-weight:600; }

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
.table-card h3 { margin:12px 16px; color:var(--blue); font-weight:800; }

.table { width:100%; border-collapse:collapse; }
.table th, .table td { padding:12px 14px; border-top:1px solid var(--border); }
.table th { font-size:13px; text-align:left; opacity:.9; }
.win { background:#dcfce7; color:#15803d; padding:3px 8px; border-radius:6px; font-weight:700; }
.loss { background:#fee2e2; color:#b91c1c;  padding:3px 8px; border-radius:6px; font-weight:700; }

.footer-card { background:#fff; border:1px solid var(--border); border-radius:12px; padding:16px; margin:18px 0; box-shadow:var(--shadow); }
.footer-card h3{ color:#2563eb; font-weight:800; margin:0 0 8px 0; }
.footer-card .note { font-size:13px; opacity:.9; }
"""

# ------------- PAGE TEMPLATE -------------
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
      <div class="chg {chg_class}"><span class="arr">{chg_arrow}</span>{chg}</div>
    </div>
  </div>

  <div class="banner {banner_class}">
    <div class="t">AI Prediction: <b>{full_name}</b> for <b>{pred_date}</b></div>
    <div class="signal">{banner_arrow} {signal}</div>
    <div class="ohlc">O {o} H {h} L {l} C {c}</div>
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

# ------------- rebuild logic -------------
def rebuild_page(p: Path):
    html = p.read_text(encoding="utf-8")
    symbol, full_name = get_symbol_and_fullname(html)
    pred_date = get_prediction_date(html)
    signal = get_signal(html)
    acc_pct, acc_note = scrape_accuracy(html)
    table_html = build_table(html)

    # Pull strictly from CSVs using (symbol, description) with fallback to unique symbol.
    o_csv, h_csv, l_csv, c_csv, chg_csv = csv_lookup(symbol, full_name)

    # Apply CSV values if present; otherwise leave blanks (will render as —)
    def dash_if_empty(v): 
        return v if v else "—"

    o = dash_if_empty(o_csv)
    h = dash_if_empty(h_csv)
    l = dash_if_empty(l_csv)
    c = dash_if_empty(c_csv)
    chg = dash_if_empty(chg_csv)

    close_px = c
    chg_arrow = "▲" if chg.startswith("+") else ("▼" if chg.startswith("-") else "•")
    chg_class = "positive" if chg.startswith("+") else ("negative" if chg.startswith("-") else "")
    banner_arrow = arrow_for(signal)

    out = HTML.format(
        stamp=STAMP,
        page_title=f"{full_name or symbol} Stock Prediction",
        css=CSS,
        symbol=escape(symbol or "—"),
        full_name=escape(full_name or "Stock"),
        build_time=dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        close_px=escape(close_px),
        chg=escape(chg or "—"),
        chg_class=chg_class,
        chg_arrow=chg_arrow,
        pred_date=escape(pred_date),
        o=o, h=h, l=l, c=c,
        signal=signal, banner_arrow=banner_arrow,
        banner_class=banner_class_for(signal),
        acc_pct=acc_pct, acc_note=acc_note,
        table_html=table_html
    )
    p.write_text(out, encoding="utf-8")

    # debug prints for visibility during run
    src = "CSV" if o_csv or c_csv or chg_csv else "MISSING"
    print(f"[v2-light] {symbol} • {full_name} → {src} • O:{o} H:{h} L:{l} C:{c} Chg:{chg} • {p}")

def main():
    read_all_lastday_csvs()
    root = Path(DIST_ROOT)
    count = 0
    for f in root.rglob("index.html"):
        if "prediction-tomorrow" in str(f).replace("\\", "/"):
            rebuild_page(f)
            count += 1
    print(f"[v2-light] total rebuilt pages: {count}")

if __name__ == "__main__":
    main()
