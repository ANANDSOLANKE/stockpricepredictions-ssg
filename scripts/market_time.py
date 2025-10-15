from __future__ import annotations
import csv
from datetime import datetime, date, timedelta, time
from pathlib import Path
from zoneinfo import ZoneInfo

# markets_config.csv columns (header required):
# region,country,exchange,tz,open_local,close_local,weekend (e.g. "sat,sun"),holidays_csv(optional)
# Example:
# Asia - Pacific,India,NSE,Asia/Kolkata,09:15,15:30,sat,sun

def _load_markets_cfg() -> list[dict]:
    cfg_path = Path("markets_config.csv")
    rows: list[dict] = []
    if not cfg_path.exists():
        return rows
    with cfg_path.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append({k.strip(): (v or "").strip() for k, v in row.items()})
    return rows

def _find_market_tz(region: str, country: str, exchange: str) -> ZoneInfo:
    for row in _load_markets_cfg():
        if (
            row.get("region") == region
            and row.get("country") == country
            and row.get("exchange") == exchange
        ):
            tz = row.get("tz") or "UTC"
            return ZoneInfo(tz)
    return ZoneInfo("UTC")

def _weekend_set(region: str, country: str, exchange: str) -> set[int]:
    # default: Sat/Sun
    wk = {"sat","sun"}
    for row in _load_markets_cfg():
        if (
            row.get("region") == region
            and row.get("country") == country
            and row.get("exchange") == exchange
        ):
            s = (row.get("weekend") or "sat,sun").lower()
            wk = {p.strip() for p in s.split(",") if p.strip()}
            break
    # map to weekday(): Mon=0..Sun=6
    m = {"mon":0,"tue":1,"wed":2,"thu":3,"fri":4,"sat":5,"sun":6}
    return {m.get(x, 6) for x in wk}

def _is_holiday(d: date, region: str, country: str, exchange: str) -> bool:
    # optional holidays list: YYYY-MM-DD per line in a csv pointed by holidays_csv column
    for row in _load_markets_cfg():
        if (
            row.get("region") == region
            and row.get("country") == country
            and row.get("exchange") == exchange
        ):
            hp = row.get("holidays_csv") or ""
            if hp:
                p = Path(hp)
                if p.exists():
                    with p.open(newline="", encoding="utf-8") as f:
                        rr = csv.reader(f)
                        for r in rr:
                            if not r:
                                continue
                            try:
                                if date.fromisoformat(r[0].strip()) == d:
                                    return True
                            except Exception:
                                pass
    return False

def next_business_day_utc(
    region: str, country: str, exchange: str, now_utc: datetime | None = None
) -> date:
    """
    Return the 'target prediction date' (T or T+1) in **local market time**,
    then convert to a UTC date to display consistently.

    Rule: if 'now' (in market local tz) is before LOCAL close, predict for 'today';
          otherwise predict for the next business day (skip weekends/holidays).
    """
    if now_utc is None:
        now_utc = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))

    tz = _find_market_tz(region, country, exchange)
    local_now = now_utc.astimezone(tz)

    # close time: try to read from config; else 17:00 local
    close_local = time(17, 0)
    for row in _load_markets_cfg():
        if (
            row.get("region") == region
            and row.get("country") == country
            and row.get("exchange") == exchange
        ):
            hh, mm = 17, 0
            c = (row.get("close_local") or "").strip()
            if c:
                try:
                    hh, mm = [int(x) for x in c.split(":")[:2]]
                except Exception:
                    pass
            close_local = time(hh, mm)
            break

    weekend = _weekend_set(region, country, exchange)
    target = local_now.date()
    if local_now.time() >= close_local:
        target = target + timedelta(days=1)

    # roll forward to next business day
    while target.weekday() in weekend or _is_holiday(target, region, country, exchange):
        target += timedelta(days=1)

    # We return a date (no tz) – it’s already the correct *local* T/T+1
    # You can display it directly; the pages remain under 'prediction-tomorrow/' route.
    return target
