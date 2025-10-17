#!/usr/bin/env python3
from __future__ import annotations
import re, sys
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Tuple, Dict, Optional
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
HIST = ROOT / "Data" / "Historical"

REGION_MAP = {
    "asia-pacific": "Asia - Pacific",
    "europe": "Europe",
    "north-america": "North America",
    "mexico-south-america": "Mexico - South America",
    "middle-east-africa": "Middle East - Africa",
    "global-indices": "Global Indices",
}

LAST7_RE = re.compile(r"<!--\s*LAST7:START\s*-->.*?<!--\s*LAST7:END\s*-->", re.S | re.I)

def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")

def latest_hist_dates(n:int=20)->List[str]:
    if not HIST.exists(): return []
    ds=[d.name for d in HIST.iterdir() if d.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d.name)]
    ds.sort(reverse=True)
    return ds[:n]

def load_country_csv(date_str:str, region_folder:str, country_slug:str)->Optional[pd.DataFrame]:
    p = HIST / date_str / region_folder / f"{country_slug.lower()}.csv"
    if not p.exists(): return None
    try:
        df = pd.read_csv(p)
        cols = {c.lower(): c for c in df.columns}
        need = ["symbol","exchange","close"]
        for k in need:
            if k not in cols:
                # exact lower-case match only; if missing, bail
                return None
        df = df.rename(columns={cols["symbol"]:"symbol", cols["exchange"]:"exchange", cols["close"]:"close"})
        return df
    except Exception:
        return None

def pick_row(df: pd.DataFrame, symbol:str, exchange:str)->Optional[pd.Series]:
    # strict: symbol + exchange
    mask = (df["symbol"].astype(str).str.upper() == symbol.upper()) & \
           (df["exchange"].astype(str).str.upper() == exchange.upper())
    if mask.any():
        return df.loc[mask].iloc[0]
    # fallback: symbol only (any exchange)
    mask2 = (df["symbol"].astype(str).str.upper() == symbol.upper())
    if mask2.any():
        return df.loc[mask2].iloc[0]
    return None

def compute_last7(region_slug:str, country_slug:str, exchange_slug:str, symbol:str)->List[Tuple[str,str,str,str]]:
    region_folder = REGION_MAP.get(region_slug.lower(), region_slug)
    ex = exchange_slug.upper()

    series: List[Tuple[str,float]] = []
    for d in sorted(latest_hist_dates(30)):  # chronological
        df = load_country_csv(d, region_folder, country_slug)
        if df is None: continue
        row = pick_row(df, symbol, ex)
        if row is None: continue
        try:
            c = float(row["close"])
            series.append((d, c))
        except Exception:
            pass

    if len(series) < 3: return []

    out: List[Tuple[str,str,str,str]] = []
    for i in range(2, len(series)):
        d_tgt, c_tgt = series[i]
        _, c_prev = series[i-1]
        _, c_prev2 = series[i-2]
        ai = "Bullish" if c_prev > c_prev2 else "Bearish"
        actual = "Bullish" if c_tgt > c_prev else "Bearish"
        res = "Win" if ai == actual else "Loss"
        out.append((d_tgt, ai, actual, res))

    # de-dup by target date (keep last)
    uniq: Dict[str, Tuple[str,str,str,str]] = {}
    for r in out: uniq[r[0]] = r
    return list(uniq.values())[-7:]

def cls(v:str)->str:
    return "text-green-400 font-bold" if v.lower() in ("win","bullish") else "text-red-400 font-bold"

def render_table(rows:List[Tuple[str,str,str,str]])->str:
    wins = sum(1 for *_,r in rows if r=="Win")
    rate = f"{(wins/len(rows))*100:.2f}% ({wins}/{len(rows)})" if rows else "—"
    body = "\n".join(
        f'<tr><td class="font-mono">{d}</td>'
        f'<td class="{cls(p)}">{p}</td>'
        f'<td class="{cls(a)}">{a}</td>'
        f'<td class="{cls(r)}">{r}</td></tr>'
        for d,p,a,r in rows
    )
    return f"""<!-- LAST7:START -->
<h3 class="text-xl font-bold text-white mb-3">Last 7-Day Performance</h3>
<div class="mb-3 p-3 bg-slate-800 rounded-lg border border-slate-700 flex items-center justify-between">
  <span class="text-slate-300 text-sm">Last 7-Day Accuracy:</span>
  <span class="text-green-400 font-extrabold">{rate}</span>
</div>
<div class="overflow-x-auto rounded-lg border border-slate-700">
<table class="performance-table min-w-full">
  <thead><tr><th>Date</th><th>AI Prediction</th><th class="text-left">Actual</th><th class="text-left">Result</th></tr></thead>
  <tbody>
{body}
  </tbody>
</table>
</div>
<!-- LAST7:END -->"""

def inject_block(html:str, block:str)->str:
    if LAST7_RE.search(html):
        return LAST7_RE.sub(block, html)
    # if markers not present, drop it before </main> or </body>
    for tag in ("</main>", "</body>"):
        i = html.lower().rfind(tag)
        if i != -1: return html[:i] + "\n" + block + "\n" + html[i:]
    return html + "\n" + block + "\n"

def find_pages()->List[Path]:
    return list(DIST.glob("**/prediction-tomorrow/index.html"))

def parse_from_path(p:Path)->Tuple[str,str,str,str]:
    parts = p.parts
    k = parts.index("dist")
    return parts[k+1], parts[k+2], parts[k+3], parts[k+4]

def main()->int:
    pages = find_pages()
    print(f"[scan] prediction-tomorrow pages: {len(pages)}", flush=True)
    injected = 0
    debug_left = 8  # limit log noise

    for page in pages:
        region, country, exchange, symbol = parse_from_path(page)
        rows = compute_last7(region, country, exchange, symbol)
        if not rows:
            if debug_left:
                reg_folder = REGION_MAP.get(region.lower(), region)
                print(f"[miss] {page} | try Data/Historical/*/{reg_folder}/{country}.csv | exch={exchange.upper()} sym={symbol}", flush=True)
                debug_left -= 1
            continue

        html = page.read_text(encoding="utf-8", errors="ignore")
        new_html = inject_block(html, render_table(rows))
        if new_html != html:
            page.write_text(new_html, encoding="utf-8")
            injected += 1

    print(f"[OK] injected: {injected}", flush=True)
    return 0

if __name__ == "__main__":
    sys.exit(main())
