# scripts/theme_rebuild_v2.py
# Rebuild each prediction page (".../prediction-tomorrow/index.html")
# to the exact light UI like webpage.html: green banner, 3 info cards,
# last-7 table with colored result cells, and an "In-Depth Technical Analysis" note.
#
# Safe: reads values already on the page (no model reruns). If parsing fails,
# falls back to neutral values and still produces a consistent page.

import os, re, html, datetime
from pathlib import Path

DIST = Path("dist")
PAGE_DIRNAME = "prediction-tomorrow"
STAMP = f"<!-- v2 rebuild applied {datetime.datetime.utcnow().isoformat()}Z -->"

# ---------- helpers to extract data from the OLD html ----------

H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
REGION_LINE_RE = re.compile(r"Region:\s*([^|<]+)\|\s*Country:\s*([^|<]+)\|\s*Exchange:\s*([^<]+)", re.I)
PRED_DATE_RE = re.compile(r"Prediction for\s+(\d{4}-\d{2}-\d{2})", re.I)
OHLC_RE = re.compile(r"OHLC:\s*O\s*([0-9.\-]+).*?H\s*([0-9.\-]+).*?L\s*([0-9.\-]+).*?C\s*([0-9.\-]+)", re.I | re.S)
CHG_RE = re.compile(r"Change%[:\s]*([+\-]?[0-9.]+%)", re.I)

# table parsing: capture rows under the first <tbody> after the last-7 section
TBODY_RE = re.compile(r"<tbody[^>]*>(.*?)</tbody>", re.I | re.S)
ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.I | re.S)

def _strip_tags(x: str) -> str:
    return re.sub(r"<[^>]+>", "", x).strip()

def _get_company(h: str) -> str:
    m = H1_RE.search(h)
    if not m: return "Stock Prediction"
    txt = _strip_tags(m.group(1))
    n = re.search(r"AI Analysis of (.+?) Tomorrow", txt, re.I)
    return n.group(1).strip() if n else txt

def _get_meta(h: str):
    region = country = exch = "—"
    m = REGION_LINE_RE.search(h)
    if m:
        region = _strip_tags(m.group(1))
        country = _strip_tags(m.group(2))
        exch = _strip_tags(m.group(3))
    return region, country, exch

def _get_pred_date(h: str) -> str:
    m = PRED_DATE_RE.search(h)
    return m.group(1) if m else "—"

def _get_ohlc(h: str):
    O=H=L=C="—"
    m = OHLC_RE.search(h)
    if m:
        O,H,L,C = m.group(1), m.group(2), m.group(3), m.group(4)
    k = CHG_RE.search(h)
    chg = k.group(1) if k else "—"
    return O,H,L,C,chg

def _derive_signal(h: str) -> str:
    # try first visible "AI Prediction" cell from the last-7 table
    tb = TBODY_RE.search(h)
    if tb:
        body = tb.group(1)
        for r in ROW_RE.findall(body):
            cells = CELL_RE.findall(r)
            if len(cells) >= 3:
                ai = _strip_tags(cells[1])
                if ai.lower() in ("bullish", "bearish"):
                    return ai.title()
    return "—"

def _parse_last7(h: str):
    """Return list of rows: [{date, ai, actual, result}], and (wins, total)."""
    rows, wins = [], 0
    tb = TBODY_RE.search(h)
    if not tb:
        return rows, wins, 0
    body = tb.group(1)
    for r in ROW_RE.findall(body):
        cells = CELL_RE.findall(r)
        if len(cells) >= 4:
            date  = _strip_tags(cells[0])
            ai    = _strip_tags(cells[1])
            actual= _strip_tags(cells[2])
            result= _strip_tags(cells[3])
            rows.append({"date": date, "ai": ai, "actual": actual, "result": result})
            if result.lower() == "win": wins += 1
    return rows, wins, len(rows)

# ---------- HTML template (light UI like your webpage.html) ----------

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{company} — AI Stock Prediction</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800;900&display=swap" rel="stylesheet">
<style>
:root {{
  --bg:#f5f7fb; --card:#ffffff; --ink:#0f172a; --muted:#475569; --border:#e5e7eb;
  --green:#16a34a; --green-600:#059669; --green-700:#047857;
  --blue:#2563eb; --blue-600:#1d4ed8;
  --rose:#ef4444; --stone:#0f172a;
}}
*{{box-sizing:border-box}}
html,body{{margin:0;padding:0;font-family:'Inter',system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--ink)}}
a{{color:var(--blue-600);text-decoration:none}} a:hover{{text-decoration:underline}}
.wrap{{max-width:980px;margin:20px auto;padding:0 16px}}
.badge{{background:#fff;border:1px solid var(--border);border-radius:12px;display:inline-flex;align-items:center;gap:12px;padding:10px 14px;box-shadow:0 8px 20px rgba(0,0,0,.06)}}
.badge .sym{{height:36px;width:36px;border-radius:10px;background:#14b8a6;color:white;display:flex;align-items:center;justify-content:center;font-weight:800}}
.badge .name{{font-weight:800}} .badge .sub{{font-size:12px;color:var(--muted)}}
.head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:14px;box-shadow:0 10px 18px rgba(2,6,23,.05)}}
.pad{{padding:18px}}
.green-banner{{background:linear-gradient(180deg,#0EA76B 0%,#089963 100%);color:#EFFFF7;border-radius:14px;box-shadow:0 18px 30px rgba(14,167,107,.18);padding:22px 22px 26px 22px}}
.kv{{display:flex;gap:14px;align-items:flex-end;flex-wrap:wrap}}
.kv .title{{font-weight:800;letter-spacing:.2px}}
.kv .date{{font-size:14px;opacity:.85}}
.pill{{background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.25);padding:4px 10px;border-radius:999px;font-weight:800;font-size:12px}}
.signal{{font-weight:900;letter-spacing:.8px;font-size:44px;line-height:1.05;margin:8px 0 8px 0}}
.ohlc{{display:inline-flex;gap:12px;flex-wrap:wrap;background:rgba(255,255,255,.12);border-radius:10px;padding:8px 12px;font-weight:600}}
.ohlc span{{opacity:.95}}
.grid3{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:14px}}
@media (max-width:820px){{.grid3{{grid-template-columns:1fr}}}}
.tcard{{border-radius:12px;border:1px solid var(--border);padding:12px 14px;background:#fff}}
.tcard h4{{margin:0 0 6px 0;font-size:14px;color:#0f172a}}
.tcard .content{{
  font-size:13px;color:var(--muted)
}}
.table-wrap{{margin-top:18px}}
.table-title{{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;border-bottom:1px solid var(--border)}}
.table-title h3{{margin:0;font-size:18px}}
.accu{{font-size:24px;font-weight:900;color:var(--green-700)}}
table{{width:100%;border-collapse:separate;border-spacing:0}}
thead th{{background:#f1f5f9;color:#0f172a;text-align:left;font-size:13px;padding:10px;border-top:1px solid var(--border)}}
thead th:first-child{{border-top-left-radius:10px}} thead th:last-child{{border-top-right-radius:10px}}
tbody td{{padding:12px 10px;border-bottom:1px solid var(--border);font-size:14px}}
tbody tr:nth-child(odd) td{{background:#fff}} tbody tr:nth-child(even) td{{background:#f8fafc}}
td.result.win{{background:#e7f8ee;color:#065f46;font-weight:800;text-align:center;border-left:1px solid #bbf7d0;border-right:1px solid #bbf7d0}}
td.result.lose{{background:#fde2e2;color:#7f1d1d;font-weight:800;text-align:center;border-left:1px solid #fecaca;border-right:1px solid #fecaca}}
.footer{{margin:22px 0 30px 0;border-top:1px solid var(--border);padding-top:14px;font-size:12px;color:#64748b}}
.smallmuted{{font-size:12px;color:#64748b}}
</style>
</head>
<body>
<div class="wrap">
  <div class="head">
    <div class="badge">
      <div class="sym">{sym}</div>
      <div>
        <div class="name">{company}</div>
        <div class="sub">{exch} • Last build: {build_ts}</div>
      </div>
    </div>
  </div>

  <div class="card pad">
    <div class="smallmuted" style="margin-bottom:8px">AI Prediction Summary: Next-Day Movement Analysis</div>
    <div class="green-banner">
      <div class="kv">
        <div class="title">{company}</div>
        <div class="date">{pdate}</div>
        <span class="pill">NEXT-DAY SIGNAL</span>
      </div>
      <div class="signal">{signal}</div>
      <div class="ohlc">
        <span>OHLC:</span>
        <span>O {O}</span>
        <span>H {H}</span>
        <span>L {L}</span>
        <span>C {C}</span>
        <span>• Change% {chg}</span>
      </div>
    </div>

    <div class="grid3">
      <div class="tcard">
        <h4>Model Performance</h4>
        <div class="content">
          <div style="font-size:28px;font-weight:900;color:var(--green-700)">{accu_pct}</div>
          <div>7-Day Accuracy ({wins}/{tot} Wins)</div>
          <div class="smallmuted" style="margin-top:6px">30-Day Accuracy: —  •  Demonstrative Experience*</div>
        </div>
      </div>
      <div class="tcard">
        <h4>Our Methodology</h4>
        <div class="content">
          We analyze 50+ factors including volume, momentum (RSI, MACD), and key support levels via our deep learning model.
          <div style="margin-top:6px"><a href="#" aria-label="Read">Read Our Full Process →</a></div>
        </div>
      </div>
      <div class="tcard">
        <h4>Important Disclosures</h4>
        <div class="content">
          This is <b>NOT</b> financial advice. For informational purposes only. Trading carries inherent risk.
          <div class="smallmuted" style="margin-top:6px">*Establishes Authority & Trustworthiness*</div>
        </div>
      </div>
    </div>

    <div class="table-wrap card">
      <div class="table-title">
        <h3>Model vs. Actual: Last 7 Days Performance</h3>
        <div class="accu">{accu_pct}</div>
      </div>
      <div style="overflow-x:auto">
      <table>
        <thead>
          <tr>
            <th style="width:120px">Date</th>
            <th style="width:160px">AI Prediction</th>
            <th style="width:160px">Actual Movement</th>
            <th style="width:120px">Result</th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
      </div>
    </div>

    <div class="card pad" style="margin-top:14px">
      <div style="font-weight:800;margin-bottom:6px">In-Depth Technical Analysis of {company}</div>
      <div class="smallmuted">
        {company} operates in the {country} market ({region}, {exch}). Our analysis leverages the latest market close data
        to determine the highest probability direction for the next trading day using trend, momentum and volatility factors.
      </div>
    </div>

  </div>

  <div class="footer">
    <div>E-E-A-T: Author <b>StockPricePredictions Research</b> • Org: SPP Labs</div>
    <div>Contact: <a href="mailto:hello@stockpricepredictions.com">hello@stockpricepredictions.com</a></div>
  </div>
</div>
{stamp}
</body>
</html>
"""

def _cells_to_row(date, ai, actual, result):
    cls = "win" if result.lower() == "win" else "lose"
    return f"""<tr>
      <td>{html.escape(date)}</td>
      <td>{html.escape(ai)}</td>
      <td>{html.escape(actual)}</td>
      <td class="result {cls}">{html.escape(result.title())}</td>
    </tr>"""

def rebuild_one(path: Path) -> bool:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    if "v2 rebuild applied" in raw:
        return False

    company = _get_company(raw)
    region, country, exch = _get_meta(raw)
    pdate = _get_pred_date(raw)
    O,H,L,C,chg = _get_ohlc(raw)
    signal = _derive_signal(raw)

    rows, wins, tot = _parse_last7(raw)
    rows_html = "".join(_cells_to_row(r["date"], r["ai"], r["actual"], r["result"]) for r in rows)
    accu_pct = f"{(wins/tot*100):.2f}%" if tot > 0 else "—"

    sym = re.sub(r"[^A-Z0-9]", "", company.split()[0].upper())[:3] or "SPP"
    build_ts = re.search(r"Last build:\s*([0-9TZ:\-]+)", raw)
    build_ts = build_ts.group(1) if build_ts else datetime.datetime.utcnow().isoformat()+"Z"

    out = HTML.format(
        company=html.escape(company),
        exch=html.escape(exch.strip()),
        region=html.escape(region.strip()),
        country=html.escape(country.strip()),
        pdate=html.escape(pdate),
        O=html.escape(O), H=html.escape(H), L=html.escape(L), C=html.escape(C), chg=html.escape(chg),
        signal=html.escape(signal.upper() if signal != "—" else "—"),
        accu_pct=accu_pct,
        wins=wins, tot=tot,
        rows_html=rows_html or '<tr><td colspan="4" class="smallmuted">No recent rows.</td></tr>',
        sym=html.escape(sym),
        build_ts=html.escape(build_ts),
        stamp=STAMP
    )
    path.write_text(out, encoding="utf-8")
    print("rebuilt:", path)
    return True

def main():
    count = 0
    for p in DIST.rglob("index.html"):
        if p.parent.name == PAGE_DIRNAME:
            try:
                if rebuild_one(p):
                    count += 1
            except Exception as e:
                print("skip fail:", p, e)
    print(f"theme_rebuild_v2: pages rebuilt={count}")

if __name__ == "__main__":
    main()
