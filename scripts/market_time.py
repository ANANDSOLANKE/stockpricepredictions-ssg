# scripts/market_time.py
from __future__ import annotations
import csv
from datetime import datetime, date, time, timedelta
from pathlib import Path
from typing import Dict, Tuple
import pytz

# Where your CSV lives (adjust if you placed it elsewhere)
CONFIG_PATHS = [
    Path("markets_config.csv"),
    Path("Data/markets_config.csv"),
    Path(".github/markets_config.csv"),
]

# Cache after first load
_MARKET_CFG: Dict[str, Dict] = {}

def _parse_time(s: str) -> time:
    s = (s or "").strip()
    # supports "9:15", "09:15", "09:15:00"
    parts = [int(p) for p in s.split(":")]
    if len(parts) == 2:
        return time(parts[0], parts[1], 0)
    if len(parts) == 3:
        return time(parts[0], parts[1], parts[2])
    raise ValueError(f"Bad time value: {s!r}")

def _parse_weekend(s: str) -> Tuple[int, ...]:
    # Map names to weekday ints (Mon=0 ... Sun=6)
    m = {
        "mon": 0, "monday": 0,
        "tue": 1, "tuesday": 1,
        "wed": 2, "wednesday": 2,
        "thu": 3, "thursday": 3,
        "fri": 4, "friday": 4,
        "sat": 5, "saturday": 5,
        "sun": 6, "sunday": 6,
    }
    items = []
    for tok in (s or "").replace("/", ",").replace("|", ",").split(","):
        tok = tok.strip().lower()
        if not tok:
            continue
        if tok not in m:
            raise ValueError(f"Bad weekend token: {tok!r}")
        items.append(m[tok])
    return tuple(sorted(set(items)))

def _load_config() -> None:
    global _MARKET_CFG
    if _MARKET_CFG:
        return

    path = None
    for p in CONFIG_PATHS:
        if p.exists():
            path = p
            break
    if path is None:
        # Minimal safe defaults if CSV is missing
        _MARKET_CFG = {
            "nse": {"tz": "Asia/Kolkata", "open": time(9,15), "close": time(15,30), "weekend": (5,6)},
            "bse": {"tz": "Asia/Kolkata", "open": time(9,15), "close": time(15,30), "weekend": (5,6)},
        }
        return

    cfg: Dict[str, Dict] = {}
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Accept several common column names
            exch = (row.get("exchange") or row.get("code") or row.get("exch") or row.get("market") or "").strip().lower()
            if not exch:
                continue
            tz = (row.get("tz") or row.get("timezone") or row.get("time_zone") or "UTC").strip()
            open_s = (row.get("open_local") or row.get("open") or "09:00").strip()
            close_s = (row.get("close_local") or row.get("close") or "17:00").strip()
            weekend_s = (row.get("weekend") or "Sat,Sun").strip()

            try:
                cfg[exch] = {
                    "tz": tz,
                    "open": _parse_time(open_s),
                    "close": _parse_time(close_s),
                    "weekend": _parse_weekend(weekend_s),
                }
            except Exception as e:
                # Skip malformed rows but keep going
                print(f"[market_time] Skip row for {exch!r}: {e}")

    # Fallbacks if critical markets not present
    cfg.setdefault("nse", {"tz": "Asia/Kolkata", "open": time(9,15), "close": time(15,30), "weekend": (5,6)})
    cfg.setdefault("bse", {"tz": "Asia/Kolkata", "open": time(9,15), "close": time(15,30), "weekend": (5,6)})

    _MARKET_CFG = cfg

def _next_business_day(d: date, weekend: Tuple[int, ...]) -> date:
    cur = d + timedelta(days=1)
    while cur.weekday() in weekend:
        cur += timedelta(days=1)
    return cur

def get_prediction_date(exchange: str, now_utc: datetime | None = None) -> str:
    """
    Return ISO date string for the *prediction target day* for a given exchange.
    Rule:
      - If local time <= today's local close ⇒ target = today
      - Else ⇒ target = next business day (skipping that market's weekend)
    """
    _load_config()
    exch = (exchange or "").strip().lower()
    cfg = _MARKET_CFG.get(exch, _MARKET_CFG.get("nse"))  # sensible fallback

    tz = pytz.timezone(cfg["tz"])
    now_utc = now_utc or datetime.utcnow()
    local_now = now_utc.replace(tzinfo=pytz.utc).astimezone(tz)
    local_today = local_now.date()

    # Build local datetime objects for today's open/close
    close_dt = tz.localize(datetime.combine(local_today, cfg["close"]))
    # If market hasn’t closed yet, we’re still predicting for *today*
    if local_now <= close_dt and local_today.weekday() not in cfg["weekend"]:
        return local_today.isoformat()

    # Otherwise, predict for the next open day
    next_day = _next_business_day(local_today, cfg["weekend"])
    return next_day.isoformat()
