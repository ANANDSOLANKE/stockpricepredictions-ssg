# scripts/theme_rebuild_v2.py
# Light UI with Date + OHLC + %Change directly under stock name.
# 100% CSV-driven overrides; robust (Symbol, Description) match; clean % formatting.

import csv
import re
import datetime as dt
from pathlib import Path
from html import escape

DIST_ROOT = "dist"
DATA_LAST_TRADING_DAY = "Data/LastTradingDay"
STAMP = f"<!-- v2-rebuild-light {dt.datetime.now(dt.timezone.utc).isoformat()} -->"

# ---------------- helpers ----------------
def rx(pat, s, flags=re.I | re.S, group=1, default=""):
    m = re.search(pat, s, flags)
    return (m.group(group).strip() if m else default).strip()

def norm_desc(s: str) -> str:
    if not s:
        return ""
    s = s.lower()
    repl = [
        ("&", " and "),
        ("limited", " "), ("ltd", " "),
        ("public", " "), ("company", " "), ("co.", " "), ("co ", " "),
        ("plc", " "), ("inc.", " "), ("inc", " "),
        ("corp.", " "), ("corporation", " "),
    ]
    for a, b in repl:
        s = s.replace(a, b)
    s = re.sub(r"[^\w]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

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
    return (sym or "").strip(), (full or "").strip()

def get_prediction_date(html):
    return rx(r"Prediction\s+for\s+([0-9]{4}-[0-9]{2}-[0-9]{2})", html, default="")

def get_signal(html):
    tb = rx(r"<table[^>]*>.*?<thead.*?</thead>.*?<tbody[^>]*>(.*?)</tbody>", html, group=1, default="")
    if tb:
        r = re.search(r"<tr[^>]*>.*?<td[^>]*>.*?</td>.*?<td[^>]*>(Bullish|Bearish)</td>", tb, re.I|re.S)
        if r:
            return r.group(1).title()
    return "—"

def arrow_for(signal):
    return "▲" if signal.lower() == "bullish" else ("▼" if signal.lower() == "bearish" else "•")

def scrape_accuracy(html):
    chip = rx(r"([0-9]{1,3}\.[0-9]{2}%\s*\([0-9]+/[0-9]+\))", html, default="")
    return (chip or "—"), ("Last 7-Day Accuracy" if chip else "Accuracy unavailable")

# ---------------- CSV Index ----------------
CSV_BY_SYM_DESC = {}     # (SYM, norm_desc) -> row dict
CSV_BY_SYM = {}          # SYM -> [row dict]

CSV_OPEN_KEYS  = {"open","o"}
CSV_HIGH_KEYS  = {"high","h"}
CSV_LOW_KEYS   = {"low","l"}
CSV_CLOSE_KEYS = {"close","c","last","close price"}
CSV_CHG_KEYS   = {"change%","change %","pct_change","percent_change","pct%","% change"}
CSV_DATE_KEYS  = {"date","trading_date"}

def coerce_num(x):
    if x is None: return ""
    s = str(x).strip().replace(",", "")
    return "" if s in ("", "—", "-") else s

def normalize_pct(x):
    """Return pretty percent like -0.83% with 2 decimals, handling fraction vs percent."""
    if x is None: return ""
    s = str(x).strip()
    if s == "" or s in {"—","-"}:
        return ""
    # Already has %
    if "%" in s:
        try:
            v = float(s.replace("%","").replace(",","").strip())
            return f"{v:+.2f}%"
        except:
            return s  # keep as-is if weird
    # No %: try to parse numeric
    try:
        v = float(s.replace(",",""))
        # Heuristic: fractions in [-1.5, 1.5] are likely e.g. -0.00829 (i.e., -0.829%)
        if abs(v) <= 1.5:
            v *= 100.0
        return f"{v:+.2f}%"
    except:
        return s

def pick_col(row: dict, keys_set):
    for k in list(row.keys()):
        if k is None: continue
        kl = k.strip().lower()
        if kl in keys_set:
            return row[k]
    return ""

def read_all_lastday_csvs():
    root = Path(DATA_LAST_TRADING_DAY)
    if not root.exists():
        print(f"[WARN] {DATA_LAST_TRADING_DAY} not found — CSV override disabled.")
        return

    total = 0
    for csv_path in root.rglob("*.csv"):
        try:
            with csv_path.open("r", encoding="utf-8", newline="") as fh:
                rows = list(csv.reader(fh))
                if not rows: continue

                header = [h.strip() if h else "" for h in rows[0]]
                has_header = (len(header) >= 2 and header[0].lower() in ("symbol", "ticker", "code"))
                start = 1 if has_header else 0

                if has_header:
                    for r in rows[start:]:
                        if len(r) < 2: continue
                        sym = (r[0] or "").strip()
                        desc = (r[1] or "").strip()
                        if not sym or not desc: continue
                        rd = {header[i]: (r[i] if i < len(r) else "") for i in range(len(header))}
                        rd["_sym_"]  = sym
                        rd["_desc_"] = desc
                        rd["_o_"]    = coerce_num(pick_col(rd, CSV_OPEN_KEYS))
                        rd["_h_"]    = coerce_num(pick_col(rd, CSV_HIGH_KEYS))
                        rd["_l_"]    = coerce_num(pick_col(rd, CSV_LOW_KEYS))
                        rd["_c_"]    = coerce_num(pick_col(rd, CSV_CLOSE_KEYS))
                        rd["_chg_"]  = normalize_pct(pick_col(rd, CSV_CHG_KEYS))
                        rd["_date_"] = (pick_col(rd, CSV_DATE_KEYS) or "").strip()

                        key = (sym.upper(), norm_desc(desc))
                        CSV_BY_SYM_DESC[key] = rd
                        CSV_BY_SYM.setdefault(sym.upper(), []).append(rd)
                        total += 1
                else:
                    # Assume positional layout: 0:sym 1:desc ... 5:O 6:H 7:L 8:C 9:Change%  (and 2 may or may not be Date)
                    for r in rows[start:]:
                        if len(r) < 2: continue
                        sym  = (r[0] or "").strip()
                        desc = (r[1] or "").strip()
                        if not sym or not desc: continue
                        rd = {
                            "_sym_": sym, "_desc_": desc,
                            "_o_": coerce_num(r[5] if len(r) > 5 else ""),
                            "_h_": coerce_num(r[6] if len(r) > 6 else ""),
                            "_l_": coerce_num(r[7] if len(r) > 7 else ""),
                            "_c_": coerce_num(r[8] if len(r) > 8 else ""),
                            "_chg_": normalize_pct(r[9] if len(r) > 9 else ""),
                            "_date_": (r[2] if len(r) > 2 else "").strip(),  # best-effort
                        }
                        key = (sym.upper(), norm_desc(desc))
                        CSV_BY_SYM_DESC[key] = rd
                        CSV_BY_SYM.setdefault(sym.upper(), []).append(rd)
                        total += 1
        except Exception as e:
            print(f"[WARN] Failed reading {csv_path}: {e}")

    print(f"[CSV] Indexed {total} rows from {root}")

def csv_lookup(sym: str, fullname: str):
    if not sym:
        return {"_o_":"","_h_":"","_l_":"","_c_":"","_chg_":"","_date_":""}
    key = (sym.upper(), norm_desc(fullname))
    rd = CSV_BY_SYM_DESC.get(key)
    if rd: return rd

    cand = CSV_BY_SYM.get(sym.upper(), [])
    if len(cand) == 1:
        return cand[0]
    if len(cand) > 1 and fullname:
        nfull = norm_desc(fullname)
        best, score = None, -1
        for r in cand:
            nd = norm_desc(r.get("_desc_", ""))
            overlap = len(set(nfull.split()) & set(nd.split()))
            if overlap > score:
                best, score = r, overlap
        if best: return best
    return {"_o_":"","_h_":"","_l_":"","_c_":"","_chg_":"","_date_":""}

# ---------------- LIGHT THEME CSS ----------------
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
.header .sub { font-size:13px; opacity:.7; margin-top:2px; }
.header .meta { font-size:14px; margin-top:6px; display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
.header .meta .label { opacity:.7; }
.header .meta .chgline.positive { background:#dcfce7; color:var(--green-deep); padding:2px 8px; border-radius:999px; font-weight:800; }
.header .meta .chgline.negative { background:#fee2e2; color:#b91c1c; padding:2px 8px; border-radius:999px; font-weight:800; }

.price-chip {
  margin-left:auto; background:#ffffff; border:1px solid var(--border);
  border-radius:10px; padding:10px 14px; display:flex; gap:10px; align-items:center;
  font-weight:800; color:var(--text); box-shadow:var(--shadow);
}

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
.card::before{ content:""; position:absolute; left:0; top:0; width:100%; height:4px; background:linear-gradient(90deg,var(--blue),#60a5fa);}
.card h4 { margin:6px 0 10px 0; font-size:14px; color:#15803d; font-weight:800; }
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

# ---------------- PAGE TEMPLATE ----------------
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
      <div class="meta">
        <span class="label">Date</span> <b>{last_date}</b>
        <span class="label">•</span> O {o} H {h} L {l} C {c}
        <span class="label">•</span> <span class="chgline {chg_class}">{chg}</span>
      </div>
    </div>
    <div class="price-chip">
      <div>Close</div>
      <div>{close_px}</div>
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

# ---------------- table passthrough ----------------
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

# ---------------- rebuild ----------------
def rebuild_page(p: Path):
    html = p.read_text(encoding="utf-8")
    symbol, full_name = get_symbol_and_fullname(html)
    pred_date = get_prediction_date(html)
    signal = get_signal(html)
    acc_pct, acc_note = scrape_accuracy(html)
    table_html = build_table(html)

    rd = csv_lookup(symbol, full_name)
    o = rd.get("_o_","") or "—"
    h = rd.get("_h_","") or "—"
    l = rd.get("_l_","") or "—"
    c = rd.get("_c_","") or "—"
    chg = rd.get("_chg_","") or "—"
    last_date = rd.get("_date_","") or "—"

    # banner date fallback: if page didn't have "Prediction for YYYY-MM-DD", use CSV date
    pred = pred_date if pred_date else (last_date if last_date != "—" else "—")

    chg_class = "positive" if chg.startswith("+") else ("negative" if chg.startswith("-") else "")
    banner_arrow = arrow_for(signal)

    out = HTML.format(
        stamp=STAMP,
        page_title=f"{full_name or symbol} Stock Prediction",
        css=CSS,
        symbol=escape(symbol or "—"),
        full_name=escape(full_name or "Stock"),
        build_time=dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        last_date=escape(last_date),
        o=o, h=h, l=l, c=c,
        close_px=escape(c),
        chg=escape(chg),
        chg_class=chg_class,
        pred_date=escape(pred),
        signal=signal, banner_arrow=banner_arrow,
        banner_class=("green" if chg_class=="positive" else "red" if chg_class=="negative" else ""),
        acc_pct=acc_pct, acc_note=acc_note,
        table_html=table_html
    )
    p.write_text(out, encoding="utf-8")
    src = "CSV" if (o != "—" or c != "—" or chg != "—") else "MISSING"
    print(f"[v2-light] {symbol} • {full_name} → {src} • Date:{last_date} O:{o} H:{h} L:{l} C:{c} Chg:{chg} • {p}")

def main():
    read_all_lastday_csvs()
    root = Path(DIST_ROOT)
    count = 0
    for f in root.rglob("index.html"):
        if "prediction-tomorrow" in str(f).replace("\\", "/"):
            rebuild_page(f); count += 1
    print(f"[v2-light] total rebuilt pages: {count}")

if __name__ == "__main__":
    main()
