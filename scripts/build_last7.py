#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
build_last7.py
----------------------------------
Add-on builder for "Last 7-Day Performance" tables.

• Reads historical CSVs from Data/Historical/YYYY-MM-DD/<Group>/<country>.csv
• For each symbol:
    - Computes the last 7 AI predictions & actual results
    - Counts wins/losses and calculates win%
• Injects the 7-day performance table below the prediction card
  in every stock’s AI Prediction page under dist/
• Does NOT modify your original build.py logic.
• Keeps your proprietary rule private.
"""

import os, re, csv, html, json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
DATA_HIST = ROOT / "Data" / "Historical"
DIST = ROOT / "dist"

# ---------------- helpers ----------------
def _f(x):
    try: return float(x)
    except: return None

def list_recent_dates(n=20):
    """Return sorted list of recent YYYY-MM-DD directories in Data/Historical."""
    if not DATA_HIST.exists(): return []
    dates=[d.name for d in DATA_HIST.iterdir() if d.is_dir() and re.match(r"^\d{4}-\d{2}-\d{2}$", d.name)]
    dates.sort()
    return dates[-n:]

def read_country_csv(date_folder, group, country):
    path = DATA_HIST / date_folder / group / f"{country}.csv"
    if not path.exists(): return []
    out=[]
    with open(path,"r",encoding="utf-8") as f:
        rdr=csv.DictReader(f)
        for r in rdr:
            sym=(r.get("symbol") or "").strip().upper()
            close=_f(r.get("close"))
            out.append((sym,close))
    return out

def make_history_map(group,country,how_many=9):
    """Return dict[symbol] = [(date, close), ...] for last N days."""
    dates=list_recent_dates(how_many*2)
    hist={}
    for d in dates:
        rows=read_country_csv(d,group,country)
        for sym,close in rows:
            if sym not in hist: hist[sym]=[]
            hist[sym].append((d,close))
    # Keep only chronological last `how_many`
    for s,v in hist.items():
        v.sort(key=lambda x:x[0])
        hist[s]=v[-how_many:]
    return hist

def ai_prediction(prev_close, prev2_close):
    """Your hidden rule → returns 'Buy' or 'Sell' (logic not exposed)."""
    if prev_close is None or prev2_close is None:
        return None
    # internal logic: (hidden, simplified as placeholder)
    return "Buy" if prev_close > prev2_close else "Sell"

def actual_result(today_close, prev_close):
    if today_close is None or prev_close is None:
        return None
    return "Buy" if today_close > prev_close else "Sell"

# ---------------- build ----------------
def build_last7():
    count=0
    for stock_html in DIST.rglob("prediction-tomorrow/index.html"):
        parts=stock_html.parts
        if len(parts)<6: continue
        country=parts[-4]; group=parts[-5]  # dist/<group>/<country>/<exchange>/<symbol>/prediction-tomorrow
        symbol_folder=Path(*parts[-3:-1])
        symbol=symbol_folder.parts[-2].upper()
        group_name=group; country_slug=country

        hist=make_history_map(group_name,country_slug,how_many=10)
        closes=hist.get(symbol)
        if not closes or len(closes)<3: continue

        # derive last 7
        preds=[]
        for i in range(2,len(closes)):
            d_t, c_t = closes[i]
            _, c_t1 = closes[i-1]
            _, c_t2 = closes[i-2]
            pred = ai_prediction(c_t1,c_t2)
            actual = actual_result(c_t,c_t1)
            win = (pred==actual)
            preds.append((d_t,pred,actual,win))
        preds=preds[-7:]

        total=len(preds); wins=sum(1 for *_,w in preds if w)
        win_pct=round(wins/total*100,2) if total else 0.0

        # build table html
        rows=[]
        for d,p,a,w in preds:
            cls="green" if w else "red"
            rows.append(f"<tr><td>{html.escape(d)}</td><td>{html.escape(p or '-')}</td><td>{html.escape(a or '-')}</td><td class='{cls}'>{'Win' if w else 'Loss'}</td></tr>")

        table_html=(
            "<div class='card'>"
            "<h3 class='h3'>Last 7-Day Performance</h3>"
            f"<p class='small'>Win Ratio: <strong style='color:#3ddc97'>{win_pct}%</strong> ({wins}/{total} Wins)</p>"
            "<div class='table-wrap'><table class='table'>"
            "<thead><tr><th>Date</th><th>AI Prediction</th><th>Actual</th><th>Result</th></tr></thead>"
            f"<tbody>{''.join(rows) if rows else '<tr><td colspan=4>No data</td></tr>'}</tbody></table></div></div>"
        )

        # inject below existing prediction card
        html_txt=stock_html.read_text(encoding="utf-8")
        new_html=html_txt.replace("</main>", table_html+"</main>")
        stock_html.write_text(new_html,encoding="utf-8")
        count+=1
    print(f"[OK] Injected last-7 performance into {count} pages.")

if __name__=="__main__":
    build_last7()
