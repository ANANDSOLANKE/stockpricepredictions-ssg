#!/usr/bin/env python3
import os
import re
import sys
import csv
import glob
from pathlib import Path
from datetime import datetime, timedelta
from collections import OrderedDict, defaultdict

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]           # repo root
DIST = ROOT / "dist"
DATA = ROOT / "Data" / "Historical"
CONFIG = ROOT / "markets_config.csv"

# ---------- helpers for calendars ----------

WKMAP = {"Mon":0,"Tue":1,"Wed":2,"Thu":3,"Fri":4,"Sat":5,"Sun":6}

def parse_weekmask(s: str):
    """
    Accepts 'Mon-Fri', 'Sun-Thu', or 'Mon,Wed,Fri' (comma list).
    Returns a set of allowed weekday numbers.
    """
    s = (s or "").strip()
    if not s:
        s = "Mon-Fri"
    if "," in s:
        days = [d.strip().title()[:3] for d in s.split(",")]
        return {WKMAP[d] for d in days if d in WKMAP}
    if "-" in s:
        a,b = [p.strip().title()[:3] for p in s.split("-")]
        if a in WKMAP and b in WKMAP:
            ia, ib = WKMAP[a], WKMAP[b]
            if ia <= ib:
                return set(range(ia, ib+1))
            # wrap week (e.g., Fri-Mon)
            return set(list(range(ia,7)) + list(range(0,ib+1)))
    # fallback
    return {0,1,2,3,4}  # Mon-Fri

def load_market_config():
    """
    Build a precedence map:
      (region,country,exchange)->weekmask
      (region,country,None)   ->weekmask
      (region,None,None)      ->weekmask
    """
    maps = defaultdict(lambda: {0,1,2,3,4})
    if not CONFIG.exists():
        return maps

    df = pd.read_csv(CONFIG)
    # normalize columns
    cols = {c.lower():c for c in df.columns}
    region_c = cols.get("region")
    country_c = cols.get("country")
    exch_c    = cols.get("exchange")
    wm_c      = cols.get("weekmask")

    for _, r in df.iterrows():
        region   = str(r.get(region_c,"")).strip()
        country  = str(r.get(country_c,"")).strip().lower()
        exchange = str(r.get(exch_c,"")).strip().lower()
        wm_raw   = str(r.get(wm_c,"Mon-Fri")).strip()
        weeks = parse_weekmask(wm_raw)
        key = (region, country or None, exchange or None)
        maps[key] = weeks
    return maps

CFG = load_market_config()

def get_weekset(region: str, country: str, exchange: str):
    # Try most specific → least specific → default Mon-Fri
    keys = [
        (region, country, exchange),
        (region, country, None),
        (region, None, None),
    ]
    for k in keys:
        if k in CFG:
            return CFG[k]
    return {0,1,2,3,4}

def next_market_day(d: datetime, allowed_weekdays: set[int]):
    nd = d + timedelta(days=1)
    while nd.weekday() not in allowed_weekdays:
        nd += timedelta(days=1)
    return nd

# ---------- HTML injection ----------
START_MARK = "<!-- LAST7:START -->"
END_MARK   = "<!-- LAST7:END -->"

def inject_table(html: str, table_html: str) -> str:
    block = f"{START_MARK}\n{table_html}\n{END_MARK}"
    if START_MARK in html and END_MARK in html:
        return re.sub(
            rf"{re.escape(START_MARK)}.*?{re.escape(END_MARK)}",
            block,
            html,
            flags=re.S
        )
    # append near the end of the page (before footer if possible)
    # try after the main analysis card
    ins_at = html.rfind("</main>")
    if ins_at != -1:
        return html[:ins_at] + "\n" + block + "\n" + html[ins_at:]
    return html + "\n" + block + "\n"

# ---------- core logic per page ----------

def collect_history(region, country, exchange, symbol, need_days=20):
    """
    Read the country-level CSVs across recent historical folders,
    filter strictly by (symbol, exchange), return dataframe with
    columns: date, open, high, low, close, change, exchange, symbol
    """
    # newest first folder names YYYY-MM-DD
    folders = sorted([p for p in DATA.glob("*") if p.is_dir()], reverse=True)
    rows = []
    got = 0

    for folder in folders:
        csv_path = folder / region / f"{country}.csv"
        if not csv_path.exists():
            continue
        try:
            df = pd.read_csv(csv_path)
        except Exception:
            continue

        # Normalize columns
        lower_cols = {c.lower(): c for c in df.columns}
        sym_c   = lower_cols.get("symbol","symbol")
        exch_c  = lower_cols.get("exchange","exchange")
        close_c = lower_cols.get("close","Close")
        open_c  = lower_cols.get("open","open")
        high_c  = lower_cols.get("high","high")
        low_c   = lower_cols.get("low","low")
        chg_c   = lower_cols.get("change%","Change%")
        # Strict filter: symbol + exchange
        m = (
            df[sym_c].astype(str).str.lower() == symbol
        ) & (
            df[exch_c].astype(str).str.lower() == exchange
        )
        cut = df.loc[m, [sym_c, exch_c, open_c, high_c, low_c, close_c, chg_c]].copy()
        if cut.empty:
            continue
        cut.rename(columns={
            sym_c:"symbol",
            exch_c:"exchange",
            open_c:"open",
            high_c:"high",
            low_c:"low",
            close_c:"close",
            chg_c:"change"
        }, inplace=True)
        cut["date"] = datetime.strptime(folder.name, "%Y-%m-%d")
        rows.append(cut)
        got += 1
        if got >= need_days:
            break

    if not rows:
        return pd.DataFrame(columns=["date","open","high","low","close","change","exchange","symbol"])
    all_ = pd.concat(rows, ignore_index=True)
    # order by date ascending (oldest → newest)
    all_.sort_values("date", inplace=True)
    return all_

def make_last7(df: pd.DataFrame, region, country, exchange):
    """
    From chronological df (one row per day for this symbol & exchange),
    produce last 7 unique *target* dates with prediction/actual.
    """
    allowed = get_weekset(region, country, exchange)
    records = []

    # we need at least 2 days to compute a prediction & actual
    # Prediction for day t compares close_t vs close_(t-1)
    # Actual (for target day) compares close_(t+1) vs close_t
    for i in range(1, len(df)-1):
        today = df.iloc[i]
        prev  = df.iloc[i-1]
        nxt   = df.iloc[i+1]

        # target date = next market day after today.date
        target = next_market_day(today["date"], allowed)

        pred = "Bullish" if float(today["close"]) > float(prev["close"]) else "Bearish"
        actual = "Bullish" if float(nxt["close"]) > float(today["close"]) else "Bearish"
        win = (pred == actual)

        records.append({
            "target": target.date(),
            "pred": pred,
            "actual": actual,
            "win": win
        })

    if not records:
        return [], 0, 0

    # De-duplicate by target date: keep the most recent calculation for a given target
    dedup = OrderedDict()
    for r in sorted(records, key=lambda x: x["target"], reverse=True):
        if r["target"] not in dedup:
            dedup[r["target"]] = r
    # Take last 7 (most recent targets), show ascending in the table
    picked = list(dedup.values())[:7]
    picked.sort(key=lambda x: x["target"])

    wins = sum(1 for r in picked if r["win"])
    total = len(picked)
    return picked, wins, total

def render_table(rows, wins, total):
    # badge and rows
    if total == 0:
        acc_html = '<div class="small">Last 7-Day Accuracy: <span class="muted">n/a</span></div>'
    else:
        pct = round(100*wins/total, 2)
        color = "green" if pct >= 50 else "red"
        acc_html = f'<div class="small">Last 7-Day Accuracy: <span class="badge" style="color:{ "var(--success)" if color=="green" else "var(--danger)"}">{pct}% ({wins}/{total})</span></div>'

    def row_html(r):
        res_txt = "Win" if r["win"] else "Loss"
        res_cls = "green" if r["win"] else "red"
        return (
            "<tr>"
            f"<td>{r['target'].isoformat()}</td>"
            f"<td>{r['pred']}</td>"
            f"<td>{r['actual']}</td>"
            f"<td><span class='{res_cls}'>{res_txt}</span></td>"
            "</tr>"
        )

    body = "\n".join(row_html(r) for r in rows)

    table = f"""
<section class="card" aria-label="Last 7-Day Performance">
  <h3 class="h3">Last 7-Day Performance</h3>
  <div class="mb-2">{acc_html}</div>
  <div class="table-wrap">
    <table class="table">
      <thead>
        <tr>
          <th>Date</th>
          <th>AI Prediction</th>
          <th>Actual</th>
          <th>Result</th>
        </tr>
      </thead>
      <tbody>
        {body}
      </tbody>
    </table>
  </div>
</section>
""".strip()
    return table

def process_page(page_path: Path):
    # Expect path like: dist/<region>/<country>/<exchange>/<symbol>/prediction-tomorrow/index.html
    parts = page_path.parts
    try:
        idx = parts.index("dist")
        region   = parts[idx+1]
        country  = parts[idx+2].lower()
        exchange = parts[idx+3].lower()
        symbol   = parts[idx+4].lower()
    except Exception:
        return False, "skip (path shape)"

    df = collect_history(region, country, exchange, symbol, need_days=40)
    if df.empty or len(df) < 3:
        return False, "no history"

    rows, wins, total = make_last7(df, region, country, exchange)
    table_html = render_table(rows, wins, total)

    html = page_path.read_text(encoding="utf-8")
    html2 = inject_table(html, table_html)
    if html2 != html:
        page_path.write_text(html2, encoding="utf-8")
        return True, f"injected {total}"
    return False, "no change"

def main():
    pages = list(DIST.rglob("prediction-tomorrow/index.html"))
    injected = 0
    scanned = 0
    for p in pages:
        scanned += 1
        ok, msg = process_page(p)
        if ok:
            injected += 1
    print(f"[scan] prediction-tomorrow pages: {scanned}  [OK] injected: {injected}")

if __name__ == "__main__":
    sys.exit(main())
