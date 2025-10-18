#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Headless runner for TradingView World Downloader.
Writes exactly like the GUI does:

Data/LastTradingDay/<Group>/<slug>.csv
Data/Historical/<YYYY-MM-DD>/<Group>/<slug>.csv

Modes:
  --mode hourly  -> only markets that just closed (window controlled by --window-mins)
  --mode all     -> run all slugs due today (ignore close windows/holidays)
  --mode force   -> run ALL slugs unconditionally

CLI:
  python downloader/run_headless.py --mode hourly --data-folder Data --window-mins 240
"""

import os, sys, argparse, time
from datetime import datetime, timedelta
from pathlib import Path
from pytz import timezone

# --- Make sure repo root is importable (robust on GitHub Actions) -------------
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# -----------------------------------------------------------------------------

# Import helpers & constants from your GUI module (no Tk used here)
from downloader.app import (
    LINK_GROUPS, INDICES_GROUP, INDICES_SLUG, PAGE_EXCHANGES, TZ_OPEN_CLOSE,
    is_weekend_local, is_holiday, most_recent_trading_day, aware_dt,
    resolve_region, fetch_all, fetch_indices_df, make_stock_snapshot_df
)

def _rows_from_links():
    rows=[]
    for group, links in LINK_GROUPS.items():
        seen=set()
        for url in links:
            # expects ".../markets/stocks-<slug>/..."
            slug = url.split("/markets/stocks-")[-1].split("/")[0]
            if slug in seen: 
                continue
            seen.add(slug)
            tz, op, cl = TZ_OPEN_CLOSE.get(slug, ("UTC","09:00","16:00"))
            rows.append({"group":group,"slug":slug,"tz":tz,"open":op,"close":cl})
    # indices (special)
    tz, op, cl = TZ_OPEN_CLOSE.get("indices", ("UTC","00:00","23:59"))
    rows.append({"group":INDICES_GROUP,"slug":INDICES_SLUG,"tz":tz,"open":op,"close":cl})
    return rows

def _target_date(slug, tzname):
    tz = timezone(tzname)
    if slug == INDICES_SLUG:
        ny = timezone("America/New_York")
        return most_recent_trading_day("usa", ny, datetime.now(ny))
    return most_recent_trading_day(slug, tz, datetime.now(tz))

def _is_due_hourly(slug, tzname, close_s, window_mins):
    tz = timezone(tzname)
    now_local = datetime.now(tz)
    if slug == INDICES_SLUG:
        ny = timezone("America/New_York")
        ny_now = datetime.now(ny)
        close_t = aware_dt(ny, ny_now.date(), "16:00")
        return close_t <= ny_now <= close_t + timedelta(minutes=window_mins)

    holiday,_ = is_holiday(slug, now_local)
    if holiday or is_weekend_local(slug, now_local):
        return False
    close_t = aware_dt(tz, now_local.date(), close_s)
    return close_t <= now_local <= close_t + timedelta(minutes=window_mins)

def _write_two_paths(df, data_folder, group, slug, for_date_str):
    """Write LastTradingDay/<Group>/<slug>.csv and Historical/<date>/<Group>/<slug>.csv"""
    safe_group = group.replace("/", "-")
    last_dir = os.path.join(data_folder, "LastTradingDay", safe_group)
    os.makedirs(last_dir, exist_ok=True)
    last_path = os.path.join(last_dir, f"{slug}.csv")
    df.to_csv(last_path, index=False, encoding="utf-8")

    hist_dir = os.path.join(data_folder, "Historical", for_date_str, safe_group)
    os.makedirs(hist_dir, exist_ok=True)
    hist_path = os.path.join(hist_dir, f"{slug}.csv")
    df.to_csv(hist_path, index=False, encoding="utf-8")
    return last_path, hist_path

def run_slug(group, slug, data_folder, mode, window_mins):
    tzname, open_s, close_s = TZ_OPEN_CLOSE.get(slug, ("UTC","09:00","16:00"))

    if mode == "hourly" and not _is_due_hourly(slug, tzname, close_s, window_mins):
        return "SKIP", 0, None, None, "not due now"

    for_date = _target_date(slug, tzname).strftime("%Y-%m-%d")

    if slug == INDICES_SLUG:
        df, err = fetch_indices_df()
        if err or df.empty:
            return "ERR", 0, None, None, err or "empty result"
        out_df = df[["symbol","name","price","currency","change_percent","change_points","day_high","day_low","tech_rating"]]
    else:
        region, columns = resolve_region(slug, group)
        if not region:
            return "ERR", 0, None, None, "region not found"
        exchanges = PAGE_EXCHANGES.get(slug)
        df, err = fetch_all(region, columns, exchanges=exchanges)
        if err or df.empty:
            return "ERR", 0, None, None, err or "empty result"
        out_df = make_stock_snapshot_df(df)

    last_path, hist_path = _write_two_paths(out_df, data_folder, group, slug, for_date)
    return "OK", len(out_df), last_path, hist_path, None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="hourly", choices=["hourly","all","force"])
    ap.add_argument("--data-folder", default="Data")     # matches your repo convention
    ap.add_argument("--window-mins", type=int, default=120)
    args = ap.parse_args()

    rows = _rows_from_links()
    start = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[START] {start}")
    print(f"[INFO] mode={args.mode} data={args.data_folder} window_mins={args.window_mins}")

    total_ok = total_err = total_rows = 0
    for r in rows:
        group, slug = r["group"], r["slug"]

        if args.mode == "force":
            due = True
        elif args.mode == "all":
            due = True
        else:
            due = _is_due_hourly(slug, r["tz"], r["close"], args.window_mins)

        if not due and args.mode == "hourly":
            print(f"SKIP: {slug} ({group}) not due now")
            continue

        status, nrows, last_p, hist_p, err = run_slug(group, slug, args.data_folder, args.mode, args.window_mins)
        if status == "OK":
            total_ok += 1; total_rows += nrows
            print(f"UPDATED: {slug:15s} rows={nrows}  LastTradingDay={last_p}  Historical={hist_p}")
        elif status == "SKIP":
            print(f"SKIP   : {slug:15s} {err}")
        else:
            total_err += 1
            print(f"ERROR  : {slug:15s} {err}")

        time.sleep(0.2)

    end = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[END]   {end}")
    print(f"[SUMMARY] ok={total_ok} err={total_err} rows={total_rows}")
    return 0  # don't fail whole job if a few slugs fail

if __name__ == "__main__":
    sys.exit(main())
