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

# -------- slug -> data folder mappings --------
REGION_MAP = {
    "asia-pacific": "Asia - Pacific",
    "europe": "Europe",
    "north-america": "North America",
    "mexico-south-america": "Mexico - South America",
    "middle-east-africa": "Middle East - Africa",
    "global-indices": "Global Indices",
}

# ---------- helpers ----------
def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

def hist_dates_latest(n: int = 20) -> List[str]:
    if not HIST.exists():
        return []
    dates = [d.name for d in HIST.iterdir()
             if d.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d.name)]
    dates.sort(reverse=True)
    return dates[:n]

def load_country_frame(date_str: str, region_folder: str, country_slug: str) -> Optional[pd.DataFrame]:
    p = HIST / date_str / region_folder / f"{country_slug}.csv"
    if not p.exists():
        return None
    try:
        df = pd.read_csv(p)
        # normalize minimal columns we need
        cols_lower = {c.lower(): c for c in df.columns}
        # we need: symbol, exchange, close
        need = ["symbol", "exchange", "close"]
        for k in need:
            if k not in cols_lower:
                match = [c for c in df.columns if c.lower() == k]
                if match:
                    cols_lower[k] = match[0]
        if not all(k in cols_lower for k in need):
            return None

        df = df.rename(columns={
            cols_lower["symbol"]: "symbol",
            cols_lower["exchange"]: "exchange",
            cols_lower["close"]: "close",
        })
        return df
    except Exception:
        return None

def compute_last7_for_symbol(region_slug: str, country_slug: str, exchange_slug: str, symbol: str) -> List[Tuple[str, str, str, str]]:
    # map from URL slugs to actual data folders / values
    region_folder = REGION_MAP.get(region_slug.lower(), region_slug)
    exchange = exchange_slug.upper()

    # collect closes across last dates
    series: List[Tuple[str, float]] = []
    for d in sorted(hist_dates_latest(20)):  # chronological
        df = load_country_frame(d, region_folder, country_slug.lower())
        if df is None:
            continue
        row = df[(df["symbol"].astype(str) == symbol) & (df["exchange"].astype(str).str.upper() == exchange)]
        if not row.empty:
            try:
                c = float(row.iloc[0]["close"])
                series.append((d, c))
            except Exception:
                pass

    # need at least 3 points to compute first prediction+actual
    if len(series) < 3:
        return []

    out: List[Tuple[str, str, str, str]] = []
    for i in range(2, len(series)):
        d_tgt, close_tgt = series[i]
        _, c_prev = series[i - 1]
        _, c_prev2 = series[i - 2]

        ai_pred = "Bullish" if c_prev > c_prev2 else "Bearish"
        actual = "Bullish" if close_tgt > c_prev else "Bearish"
        result = "Win" if ai_pred == actual else "Loss"
        out.append((d_tgt, ai_pred, actual, result))

    # dedupe by TARGET date, keep latest
    seen: Dict[str, Tuple[str, str, str, str]] = {}
    for row in out:
        seen[row[0]] = row
    rows = list(seen.values())[-7:]  # last 7 targets
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
    return f"""
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
<!-- LAST7:END -->""".strip()

LAST7_RE = re.compile(r"<!--\s*LAST7:START\s*-->.*?<!--\s*LAST7:END\s*-->", re.S | re.I)

def inject_html(page_html: str, block: str) -> str:
    if LAST7_RE.search(page_html):
        return LAST7_RE.sub(block, page_html)
    for tag in ("</main>", "</body>"):
        idx = page_html.lower().rfind(tag)
        if idx != -1:
            return page_html[:idx] + "\n" + block + "\n" + page_html[idx:]
    return page_html + "\n" + block + "\n"

def scan_prediction_pages() -> List[Path]:
    return list(DIST.glob("**/prediction-tomorrow/index.html"))

def parse_parts_from_path(p: Path) -> Tuple[str, str, str, str]:
    # dist/<region>/<country>/<exchange>/<symbol>/prediction-tomorrow/index.html
    parts = p.parts
    try:
        k = parts.index("dist")
        return parts[k+1], parts[k+2], parts[k+3], parts[k+4]
    except Exception:
        # fallback from end
        return parts[-6], parts[-5], parts[-4], parts[-3]

def main() -> int:
    pages = scan_prediction_pages()
    print(f"[scan] prediction-tomorrow pages: {len(pages)}", flush=True)

    injected = 0
    debug_misses = 0

    for page in pages:
        region, country, exchange, symbol = parse_parts_from_path(page)
        rows = compute_last7_for_symbol(region, country, exchange, symbol)

        if not rows:
            # print a few sample misses to help troubleshooting (won't spam logs)
            if debug_misses < 5:
                region_folder = REGION_MAP.get(region.lower(), region)
                print(f"[miss] {page} | try Data/Historical/*/{region_folder}/{country}.csv | exch={exchange.upper()} sym={symbol}", flush=True)
                debug_misses += 1
            continue

        wins = sum(1 for *_ , r in rows if r == "Win")
        block = render_last7_html(rows, f"{(wins/len(rows))*100:.2f}% ({wins}/{len(rows)})")

        html = page.read_text(encoding="utf-8", errors="ignore")
        new_html = inject_html(html, block)

        if new_html != html:
            page.write_text(new_html, encoding="utf-8")
            injected += 1

    print(f"[OK] injected: {injected}", flush=True)
    return 0

if __name__ == "__main__":
    sys.exit(main())
