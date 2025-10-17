#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
import csv
import re
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Tuple, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
HIST = ROOT / "Data" / "Historical"
MCFG = ROOT / "markets_config.csv"

# ---------- small helpers ----------

def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

def read_markets_config() -> Dict[str, Dict[str, str]]:
    """
    markets_config.csv must minimally have columns: region,country,exchange,tz
    Extra columns are OK and ignored.
    """
    cfg: Dict[str, Dict[str, str]] = {}
    if not MCFG.exists():
        return cfg
    with MCFG.open(newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            key = f"{row.get('region','').strip().lower()}|{row.get('country','').strip().lower()}|{row.get('exchange','').strip().lower()}"
            cfg[key] = {"tz": row.get("tz", "").strip()}
    return cfg

def hist_dates_latest(n: int = 12) -> List[str]:
    """Return the latest N YYYY-MM-DD folders under Data/Historical, newest first."""
    if not HIST.exists():
        return []
    dates = []
    for d in HIST.iterdir():
        if d.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d.name):
            dates.append(d.name)
    dates.sort(reverse=True)
    return dates[:n]

def load_country_frame(date_str: str, region: str, country: str) -> Optional[pd.DataFrame]:
    p = HIST / date_str / region / f"{country}.csv"
    if not p.exists():
        return None
    try:
        df = pd.read_csv(p)
        # normalize columns that we actually use
        cols = {c.lower(): c for c in df.columns}
        need = ["symbol", "exchange", "close", "change%"]
        for k in need:
            if k not in cols:
                # try to be forgiving on case
                match = [c for c in df.columns if c.lower() == k]
                if match:
                    cols[k] = match[0]
        # minimal required: symbol, exchange, close
        if not all(k in cols for k in ["symbol", "exchange", "close"]):
            return None
        # cast Close to float if possible
        df = df.rename(columns={cols.get("symbol"): "symbol",
                                cols.get("exchange"): "exchange",
                                cols.get("close"): "close"})
        # some files use 'Close' capitalized; after rename it's 'close'
        df["exchange"] = df["exchange"].astype(str)
        return df
    except Exception:
        return None

def compute_last7_for_symbol(region: str, country: str, exchange: str, symbol: str) -> List[Tuple[str, str, str, str]]:
    """
    Build rows of (date, ai_pred, actual, result) for the last 7 target trading dates.
    Logic: if day(D-1).close > day(D-2).close => predict Bullish for D
           else => Bearish for D.
    Actual for D: Bullish if close(D) > close(D-1), else Bearish.
    We dedupe by target date and keep the most recent record.
    """
    dates = hist_dates_latest(20)  # grab enough to safely derive 7 targets
    # we need frames for consecutive days (newest..oldest)
    series = []  # list of tuples (date, close)
    for d in sorted(dates):  # ascending chronological to compute deltas
        df = load_country_frame(d, region, country)
        if df is None:
            continue
        row = df[(df["symbol"].astype(str) == symbol) & (df["exchange"].str.upper() == exchange.upper())]
        if not row.empty:
            c = row.iloc[0]["close"]
            try:
                c = float(c)
                series.append((d, c))
            except Exception:
                continue

    # need at least 3 points to get one prediction + actual
    if len(series) < 3:
        return []

    # compute predictions for targets
    out: List[Tuple[str, str, str, str]] = []
    # index i is the "target" date; we need close at i (actual) and i-1, i-2 for prediction reference
    for i in range(2, len(series)):
        d_tgt, close_tgt = series[i]
        _, close_prev = series[i - 1]
        _, close_prev2 = series[i - 2]

        ai_pred = "Bullish" if close_prev > close_prev2 else "Bearish"
        actual = "Bullish" if close_tgt > close_prev else "Bearish"
        result = "Win" if ai_pred == actual else "Loss"
        out.append((d_tgt, ai_pred, actual, result))

    # newest 7 targets, dedup by date (keep last occurrence)
    dedup: Dict[str, Tuple[str, str, str, str]] = {}
    for row in out:  # chronological; later overwrites earlier
        dedup[row[0]] = row
    rows = list(dedup.values())[-7:]  # last 7 in chronological order
    return rows

def render_last7_html(rows: List[Tuple[str, str, str, str]], win_rate_text: str) -> str:
    def cls(x: str) -> str:
        return "text-green-400 font-bold" if x.lower() in ("win", "bullish") else "text-red-400 font-bold"

    body = []
    for d, pred, actual, res in rows:
        body.append(
            f"""<tr>
  <td class="font-mono">{d}</td>
  <td class="{cls(pred)}">{pred}</td>
  <td class="{cls(actual)}">{actual}</td>
  <td class="{cls(res)}">{res}</td>
</tr>"""
        )
    table = f"""
<!-- LAST7:START -->
<h3 class="text-xl font-bold text-white mb-3">Last 7-Day Performance</h3>
<div class="mb-3 p-3 bg-slate-800 rounded-lg border border-slate-700 flex items-center justify-between">
  <span class="text-slate-300 text-sm">Last 7-Day Accuracy:</span>
  <span class="text-green-400 font-extrabold">{win_rate_text}</span>
</div>
<div class="overflow-x-auto rounded-lg border border-slate-700">
<table class="performance-table min-w-full">
  <thead>
    <tr>
      <th>Date</th><th>AI Prediction</th><th class="text-left">Actual</th><th class="text-left">Result</th>
    </tr>
  </thead>
  <tbody>
    {"".join(body)}
  </tbody>
</table>
</div>
<!-- LAST7:END -->"""
    return table.strip()

LAST7_RE = re.compile(r"<!--\s*LAST7:START\s*-->.*?<!--\s*LAST7:END\s*-->", re.S | re.I)

def inject_html(page_html: str, block: str) -> str:
    if LAST7_RE.search(page_html):
        return LAST7_RE.sub(block, page_html)
    # try before </main>, else before </body>
    for tag in ("</main>", "</body>"):
        idx = page_html.lower().rfind(tag)
        if idx != -1:
            return page_html[:idx] + "\n" + block + "\n" + page_html[idx:]
    # fallback: append
    return page_html + "\n" + block + "\n"

def scan_prediction_pages() -> List[Path]:
    return list(DIST.glob("**/prediction-tomorrow/index.html"))

def parse_parts_from_path(p: Path) -> Tuple[str, str, str, str]:
    """
    Expect: dist/<region>/<country>/<exchange>/<symbol>/prediction-tomorrow/index.html
    """
    parts = p.parts
    # find 'dist' index
    try:
        k = parts.index('dist')
    except ValueError:
        # safety: assume fixed positions from tail
        region, country, exchange, symbol = parts[-6], parts[-5], parts[-4], parts[-3]
        return region, country, exchange, symbol

    region, country, exchange, symbol = parts[k+1], parts[k+2], parts[k+3], parts[k+4]
    return region, country, exchange, symbol

def main() -> int:
    pages = scan_prediction_pages()
    print(f"[scan] prediction-tomorrow pages: {len(pages)}", flush=True)
    mcfg = read_markets_config()

    injected = 0
    for page in pages:
        try:
            region, country, exchange, symbol = parse_parts_from_path(page)
        except Exception:
            continue

        rows = compute_last7_for_symbol(region, country, exchange, symbol)
        if not rows:
            # nothing to inject for this page
            continue

        wins = sum(1 for _, _, _, r in rows if r == "Win")
        win_rate_text = f"{(wins/len(rows))*100:.2f}% ({wins}/{len(rows)})"
        block = render_last7_html(rows, win_rate_text)

        html = page.read_text(encoding="utf-8", errors="ignore")
        new_html = inject_html(html, block)

        if new_html != html:
            page.write_text(new_html, encoding="utf-8")
            injected += 1

    print(f"[OK] injected: {injected}", flush=True)
    return 0

if __name__ == "__main__":
    sys.exit(main())
