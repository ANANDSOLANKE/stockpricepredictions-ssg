# scripts/market_time.py
from __future__ import annotations
import csv
from dataclasses import dataclass
from datetime import datetime, date, time, timedelta
from pathlib import Path

import pytz  # make sure 'pytz' is in requirements

# Where we expect the config to live (repo root)
CONFIG_PATH = Path(__file__).resolve().parents[1] / "markets_config.csv"

# Fallback defaults if a row is missing in the CSV
DEFAULT_TZ = "UTC"
DEFAULT_BUSDAYS = {0, 1, 2, 3, 4}  # Mon-Fri
DEFAULT_CLOSE = time(16, 0)        # 16:00 local

WEEKDAY_MAP = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6
}

@dataclass
class MarketInfo:
    exchange: str
    tz: str
    close_local: time
    busdays: set[int]

def _parse_busdays(s: str | None) -> set[int]:
    """
    Accepts "Mon-Fri", "Mon,Tue,Wed,Thu,Fri" or empty -> Mon-Fri
    """
    if not s:
        return set(DEFAULT_BUSDAYS)
    s = s.strip().lower()
    if "-" in s:
        a, b = [x.strip() for x in s.split("-", 1)]
        if a in WEEKDAY_MAP and b in WEEKDAY_MAP:
            ai, bi = WEEKDAY_MAP[a], WEEKDAY_MAP[b]
            if ai <= bi:
                return set(range(ai, bi + 1))
            # wrap-around (e.g., Fri-Mon)
            return set(list(range(ai, 7)) + list(range(0, bi + 1)))
    # comma-separated list
    out = set()
    for part in s.replace(" ", "").split(","):
        if part in WEEKDAY_MAP:
            out.add(WEEKDAY_MAP[part])
    return out or set(DEFAULT_BUSDAYS)

def _parse_hhmm(s: str | None) -> time:
    """
    Accepts "15:30" or "1530". Falls back to DEFAULT_CLOSE.
    """
    if not s:
        return DEFAULT_CLOSE
    s = s.strip()
    try:
        if ":" in s:
            hh, mm = s.split(":", 1)
        else:
            hh, mm = s[:-2], s[-2:]
        return time(int(hh), int(mm))
    except Exception:
        return DEFAULT_CLOSE

def _load_config() -> dict[str, MarketInfo]:
    d: dict[str, MarketInfo] = {}
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ex = (row.get("exchange") or "").strip().lower()
                if not ex:
                    continue
                tz = (row.get("tz") or DEFAULT_TZ).strip()
                close_local = _parse_hhmm(row.get("close_local_hhmm"))
                busdays = _parse_busdays(row.get("business_days"))
                d[ex] = MarketInfo(exchange=ex, tz=tz, close_local=close_local, busdays=busdays)
    return d

_CONFIG = _load_config()

def _get_info(exchange: str) -> MarketInfo:
    ex = (exchange or "").strip().lower()
    mi = _CONFIG.get(ex)
    if mi:
        return mi
    # unknown exchange → sensible defaults
    return MarketInfo(exchange=ex, tz=DEFAULT_TZ, close_local=DEFAULT_CLOSE, busdays=set(DEFAULT_BUSDAYS))

def _next_business_day(d: date, allowed: set[int]) -> date:
    nd = d
    while True:
        nd += timedelta(days=1)
        if nd.weekday() in allowed:
            return nd

def next_prediction_date(exchange: str, now_utc: datetime | None = None) -> str:
    """
    Returns the prediction date (YYYY-MM-DD) for an exchange,
    using its local timezone and local close time, Mon-Fri by default.
    Logic:
      - If local time < close → predict for 'today' (T)
      - Else → predict for next business day (T+1)
    """
    mi = _get_info(exchange)
    tz = pytz.timezone(mi.tz)
    now_utc = now_utc or datetime.utcnow()
    local_now = now_utc.replace(tzinfo=pytz.utc).astimezone(tz)

    local_today = local_now.date()
    local_close_dt = datetime.combine(local_today, mi.close_local, tzinfo=tz)

    if local_now < local_close_dt:
        # if today's weekday is not a business day, jump to next business day
        return (local_today if local_today.weekday() in mi.busdays else _next_business_day(local_today, mi.busdays)).isoformat()
    else:
        return _next_business_day(local_today, mi.busdays).isoformat()
