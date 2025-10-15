#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
# Make imports reliable both locally and in GitHub Actions
# -----------------------------------------------------------------------------
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.market_time import get_prediction_date  # noqa: E402

# -----------------------------------------------------------------------------
# Existing imports (keep)
# -----------------------------------------------------------------------------
import json
from datetime import datetime
import pandas as pd
from slugify import slugify

DATA_DIR = REPO_ROOT / "Data"
LAST_DIR = DATA_DIR / "LastTradingDay"
HIST_DIR = DATA_DIR / "Historical"
DIST_DIR = REPO_ROOT / "dist"

def decide_signal(prev_close: float, close: float) -> str:
    # your private rule; do not display on the site
    if pd.isna(prev_close) or pd.isna(close):
        return "Neutral"
    return "Bullish" if close > prev_close else "Bearish"

def load_history_for(country: str, region: str, symbol: str) -> pd.DataFrame:
    # scan last 10 calendar days folders (if present) and collate this symbol
    if not HIST_DIR.exists():
        return pd.DataFrame()
    frames = []
    for day_dir in sorted(HIST_DIR.iterdir(), reverse=True):
        if not day_dir.is_dir():
            continue
        # expect Region / Country / country.csv
        csv_path = day_dir / region / f"{country}.csv"
        if not csv_path.exists():
            continue
        try:
            df = pd.read_csv(csv_path)
            df = df[df["symbol"] == symbol]
            if not df.empty:
                df["asof"] = day_dir.name  # folder date
                frames.append(df)
        except Exception:
            continue
        if len(frames) >= 10:
            break
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    # keep last 8 rows (we need 7 results using prev_close vs close)
    out = out.sort_values("asof").tail(8).reset_index(drop=True)
    return out

def inject_last7():
    total_pages = 0
    injected = 0

    # walk all prediction pages we just generated
    pred_roots = list((DIST_DIR).rglob("prediction-tomorrow"))
    for pred_root in pred_roots:
        total_pages += 1
        try:
            # derive region/country/symbol from path
            parts = pred_root.parts
            # ... /dist/<region>/<country>/<symbol>/prediction-tomorrow
            region = parts[-4]
            country = parts[-3]
            symbol_slug = parts[-2]

            # open last-trading-day csv for metadata (name/exchange) if needed
            ltd_csv = LAST_DIR / region.replace("-", " ") / country.replace("-", " ") / f"{country}.csv"
            if not ltd_csv.exists():
                continue
            ltd = pd.read_csv(ltd_csv)
            # map symbol via slug
            def to_slug(s): return slugify(str(s).lower())
            row = None
            for _, r in ltd.iterrows():
                if to_slug(r["symbol"]) == symbol_slug:
                    row = r
                    break
            if row is None:
                continue
            symbol = row["symbol"]
            exchange = row.get("exchange", "")
            # load recent history
            hist = load_history_for(country.replace("-", " "), region.replace("-", " "), symbol)
            if hist.empty or len(hist) < 2:
                # write empty note so template won’t crash
                (pred_root / "_last7.json").write_text(json.dumps(None), encoding="utf-8")
                continue

            # compute last 7 outcomes
            out_rows = []
            wins = 0
            # ensure ordering by date ascending
            hist = hist.sort_values("asof").reset_index(drop=True)
            # columns expected in your CSVs
            close_col = "Close" if "Close" in hist.columns else "close"
            for i in range(1, min(8, len(hist))):
                prev_close = hist.loc[i-1, close_col]
                close = hist.loc[i, close_col]
                pred = decide_signal(prev_close, close)
                result = "Win" if ((pred == "Bullish" and close > prev_close) or
                                   (pred == "Bearish" and close <= prev_close)) else "Loss"
                if result == "Win":
                    wins += 1
                out_rows.append({
                    "date": str(hist.loc[i, "asof"]),
                    "pred": pred,
                    "actual": f"{float(close):.2f}" if not pd.isna(close) else "-",
                    "result": result
                })

            win_pct = f"{(wins/len(out_rows))*100:.2f}%"
            payload = {"wins": wins, "win_pct": win_pct, "rows": out_rows[-7:]}
            (pred_root / "_last7.json").write_text(json.dumps(payload), encoding="utf-8")
            injected += 1
        except Exception:
            # don't fail the build on any single page
            (pred_root / "_last7.json").write_text(json.dumps(None), encoding="utf-8")

    print(f"[scan] prediction-tomorrow pages: {total_pages}")
    print(f"[OK] injected: {injected}")

def main():
    inject_last7()

if __name__ == "__main__":
    main()
