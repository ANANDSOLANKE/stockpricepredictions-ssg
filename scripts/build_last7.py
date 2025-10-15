#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Inject "Last 7-Day Performance" tables into every prediction page, using real
data from Data/Historical. Also corrects the "Prediction for YYYY-MM-DD"
header date using per-exchange local close times (via scripts/market_time.py).

Safe to re-run: it replaces content between
  <!-- LAST7:BEGIN --> ... <!-- LAST7:END -->
markers if they already exist.
"""

from __future__ import annotations
import sys
import re
import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import pandas as pd

# Per-exchange local prediction date
from scripts.market_time import get_prediction_date

# --------------------------------------------------------------------------------------
# Configuration that matches your generator
# --------------------------------------------------------------------------------------

DIST_DIR = Path("dist")
DATA_DIR = Path("Data")
HIST_DIR = DATA_DIR / "Historical"  # Data/Historical/YYYY-MM-DD/<Group>/<country>.csv

# Map URL/FS slugs -> folder names used under Data/Historical
GROUP_MAP = {
    "north-america": "North America",
    "europe": "Europe",
    "asia-pacific": "Asia - Pacific",
    "middle-east-africa": "Middle East - Africa",
    "mexico-south-america": "Mexico - South America",
    "global-indices": "Global Indices",
}

# Regex to find/replace the "Prediction for YYYY-MM-DD" header line
PRED_LINE_RE = re.compile(r"(Prediction\s+for\s+)\d{4}-\d{2}-\d{2}")

# Markers to make the injection idempotent
LAST7_BEGIN = "<!-- LAST7:BEGIN -->"
LAST7_END = "<!-- LAST7:END -->"

# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------

def norm_country_slug_to_file(country_slug: str) -> str:
    """
    dist path has 'india', 'united-kingdom', 'hong-kong' etc.
    Historical CSV uses lower-case with hyphens removed? In your repo it's 'india.csv',
    'united-kingdom.csv', 'hong-kong.csv'. So we keep hyphens.
    """
    return f"{country_slug.lower()}.csv"

def find_latest_dates(max_days: int = 10) -> List[str]:
    """Return up to `max_days` most recent dates (YYYY-MM-DD) in Data/Historical/."""
    if not HIST_DIR.exists():
        return []
    dates = []
    for p in HIST_DIR.iterdir():
        if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name):
            dates.append(p.name)
    dates.sort(reverse=True)
    return dates[:max_days]

def load_country_history(group_folder: str, country_slug: str, dates: List[str]) -> pd.DataFrame:
    """
    Load recent history rows for a given <Group>/<country> across the latest `dates`.
    Concatenate newest→oldest, then sort by date ascending for calculations.
    """
    rows = []
    for d in dates:
        csv_path = HIST_DIR / d / group_folder / f"{country_slug}.csv"
        if csv_path.exists():
            try:
                df = pd.read_csv(csv_path)
                df["__date__"] = d
                rows.append(df)
            except Exception as e:
                print(f"[warn] failed reading {csv_path}: {e}", file=sys.stderr)
    if not rows:
        return pd.DataFrame()
    df_all = pd.concat(rows, ignore_index=True)
    # Keep only essential columns (but don't crash if casing differs)
    # Normalize column names
    df_all.columns = [c.strip() for c in df_all.columns]
    # Standardize a few common variants
    rename = {}
    for c in df_all.columns:
        lc = c.lower()
        if lc == "close":
            rename[c] = "Close"
        elif lc == "symbol":
            rename[c] = "symbol"
        elif lc == "exchange":
            rename[c] = "exchange"
    if rename:
        df_all = df_all.rename(columns=rename)
    if "Close" not in df_all.columns or "symbol" not in df_all.columns or "exchange" not in df_all.columns:
        return pd.DataFrame()
    # Sort by date ascending
    df_all = df_all.sort_values(by="__date__")
    return df_all

def compute_last7(symbol: str, exchange: str, df_country: pd.DataFrame) -> Tuple[List[Dict], float]:
    """
    Compute last-7 backtest rows for (symbol, exchange) using simple rule:
      - Prediction for day t uses the SIGN of (Close_{t-1} - Close_{t-2})
      - Result for day t is WIN if (Close_t - Close_{t-1}) has the same sign
    Requires at least 3 consecutive closes; if less, returns empty rows.

    Returns: (rows, win_pct)
      rows: [{date, ai, close, result}, ...] in reverse-chronological (latest first)
      win_pct: float percentage [0..100]
    """
    # Filter just that symbol+exchange
    df = df_country[(df_country["symbol"] == symbol) & (df_country["exchange"].str.upper() == exchange.upper())]
    if df.empty:
        return [], 0.0

    # We need closes by date ascending
    ser_dates = list(df["__date__"])
    ser_close = list(df["Close"])

    # Make sure numeric
    closes = []
    dates = []
    for d, v in zip(ser_dates, ser_close):
        try:
            closes.append(float(v))
            dates.append(str(d))
        except:
            pass

    # Need at least 3 to form one prediction (uses t-1 vs t-2 to predict t)
    if len(closes) < 3:
        return [], 0.0

    rows: List[Dict] = []
    wins = 0
    total = 0

    # Build predictions for t = 2..N-1 (index)
    # We'll take the latest up to 7 rows at the end
    for t in range(2, len(closes)):
        # Prediction for dates[t] based on slope between (t-1) and (t-2)
        slope_prev = closes[t - 1] - closes[t - 2]
        ai = "Bullish" if slope_prev > 0 else ("Bearish" if slope_prev < 0 else "Sideways")

        # Actual move on day t vs t-1
        actual_move = closes[t] - closes[t - 1]
        if (actual_move > 0 and ai == "Bullish") or (actual_move < 0 and ai == "Bearish") or (actual_move == 0 and ai == "Sideways"):
            result = "Win"
            wins += 1
        else:
            result = "Loss"
        total += 1

        rows.append({
            "date": dates[t],
            "ai": ai,
            "close": closes[t],
            "result": result
        })

    # Keep latest 7, reverse-chronological for display
    rows = rows[-7:][::-1]
    win_pct = (wins / total * 100.0) if total else 0.0
    return rows, win_pct

def build_last7_html(symbol: str, exchange: str, rows: List[Dict], win_pct: float) -> str:
    """Return the HTML block to inject (wrapped by markers)."""
    # Accuracy summary line
    wins = sum(1 for r in rows if r["result"] == "Win")
    total = len(rows)
    summary = f"{win_pct:.2f}% ({wins}/{total})" if total else "—"

    # Build table rows
    trs = []
    for r in rows:
        res_cls = "text-green-400 font-bold" if r["result"] == "Win" else "text-red-400 font-bold"
        trs.append(
            f"<tr>"
            f"<td class=\"font-semibold\">{r['date']}</td>"
            f"<td>{r['ai']}</td>"
            f"<td class=\"text-right font-mono\">{r['close']:.2f}</td>"
            f"<td class=\"text-center {res_cls}\">{r['result']}</td>"
            f"</tr>"
        )
    tbody = "\n".join(trs) if trs else (
        "<tr><td colspan=\"4\" class=\"text-center text-slate-400\">Not enough recent history.</td></tr>"
    )

    return f"""
{LAST7_BEGIN}
<div class="card mt-6">
  <h2 class="h2">Last 7-Day Performance</h2>
  <div class="mb-3 p-3 bg-slate-800 rounded-lg border border-slate-700 flex flex-col sm:flex-row justify-between items-start sm:items-center">
    <span class="font-medium text-slate-300 text-sm uppercase tracking-wider mb-2 sm:mb-0">Last 7-Day Accuracy:</span>
    <span class="text-green-400 font-extrabold text-xl">{summary}</span>
  </div>
  <div class="overflow-x-auto rounded-lg border border-slate-700">
    <table class="performance-table min-w-full">
      <thead>
        <tr>
          <th>Date</th>
          <th>AI Prediction</th>
          <th class="text-right">Actual Close</th>
          <th class="text-center">Result</th>
        </tr>
      </thead>
      <tbody>
        {tbody}
      </tbody>
    </table>
  </div>
</div>
{LAST7_END}
""".strip()

def replace_or_append_last7(html: str, new_block: str) -> str:
    """Replace an existing LAST7 block or append at end of main content."""
    if LAST7_BEGIN in html and LAST7_END in html:
        return re.sub(
            re.compile(re.escape(LAST7_BEGIN) + r".*?" + re.escape(LAST7_END), re.DOTALL),
            new_block,
            html,
            count=1
        )
    # Append before closing main/container if possible, else at end
    for anchor in ("</main>", "</div></div></div>", "</body>"):
        pos = html.lower().rfind(anchor)
        if pos != -1:
            return html[:pos] + "\n" + new_block + "\n" + html[pos:]
    return html + "\n" + new_block + "\n"

def fix_prediction_date(html: str, exchange: str) -> str:
    """Ensure 'Prediction for YYYY-MM-DD' uses the market-local date."""
    try:
        local_when = get_prediction_date(exchange)
    except Exception as e:
        # If anything goes wrong, do not break the page
        # print(f"[warn] get_prediction_date failed for {exchange}: {e}", file=sys.stderr)
        return html

    def _repl(m: re.Match) -> str:
        return f"{m.group(1)}{local_when}"

    if PRED_LINE_RE.search(html):
        return PRED_LINE_RE.sub(_repl, html, count=1)
    return html  # no header found; leave intact

# --------------------------------------------------------------------------------------
# Main scan
# --------------------------------------------------------------------------------------

def main() -> int:
    if not DIST_DIR.exists():
        print("[err] dist/ not found. Build the site first.")
        return 1
    if not HIST_DIR.exists():
        print("[err] Data/Historical/ not found.")
        return 1

    latest_dates = find_latest_dates(12)  # collect a bit more than 7 in case of gaps
    if not latest_dates:
        print("[err] No dated folders in Data/Historical/. Nothing to do.")
        return 1

    # Walk all prediction pages
    pages = list(DIST_DIR.rglob("prediction-tomorrow/index.html"))
    print(f"[scan] prediction-tomorrow pages: {len(pages)}")

    injected = 0
    skipped_map = 0
    no_history = 0
    short = 0

    for html_path in pages:
        # Expect path like: dist/<group>/<country>/<exchange>/<slug>/prediction-tomorrow/index.html
        try:
            parts = html_path.parts
            # Find 'dist' index, then relative segments
            try:
                idx = parts.index("dist")
            except ValueError:
                idx = len(parts) - 6  # fallback

            group_slug = parts[idx + 1]
            country_slug = parts[idx + 2]
            exchange = parts[idx + 3]
            # slug = parts[idx + 4]  # not needed

            group_folder = GROUP_MAP.get(group_slug.lower())
            if not group_folder:
                skipped_map += 1
                continue

            # Load history for this country
            country_file = norm_country_slug_to_file(country_slug)
            df_country = load_country_history(group_folder, country_file[:-4], latest_dates)
            if df_country.empty:
                no_history += 1
                continue

            # Extract symbol from page file name OR from slug on the page.
            # We can parse symbol from the <table> list, but the safest is to read it from the page title h1
            html = html_path.read_text(encoding="utf-8", errors="ignore")

            # Try to recover symbol from the first small table / breadcrumb / h1 line already rendered
            # We'll look for "AI Analysis of <SYMBOL> Tomorrow" (your title format)
            m = re.search(r"AI Analysis of\s+([A-Z0-9\-\._]+)\s+Tomorrow", html, re.IGNORECASE)
            if m:
                symbol = m.group(1).upper()
            else:
                # fallback: from URL folder name (often symbol slug). If your slug isn't the symbol, we can't do better
                symbol = parts[idx + 4].upper()

            rows, win_pct = compute_last7(symbol, exchange, df_country)

            # Build & inject block
            block = build_last7_html(symbol, exchange, rows, win_pct)
            html = replace_or_append_last7(html, block)

            # Fix "Prediction for" header date per market local time
            html = fix_prediction_date(html, exchange)

            # Write back
            html_path.write_text(html, encoding="utf-8")
            injected += 1

        except Exception as e:
            print(f"[warn] failed injecting {html_path}: {e}", file=sys.stderr)

    print(f"[OK] injected: {injected}  | [skip-map] {skipped_map}  | [no-history] {no_history}  | short: {short}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
