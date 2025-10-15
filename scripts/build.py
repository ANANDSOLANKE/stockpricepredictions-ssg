from __future__ import annotations
import os, csv, math, json, shutil
from datetime import datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
import pandas as pd
from slugify import slugify

# LOCAL helper import – no "scripts." prefix
from market_time import next_business_day_utc

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "Data"
DIST = ROOT / "dist"
TEMPLATES = ROOT / "static"  # keep your templates here (header, layout, etc.)

def _jinja():
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env

def _ensure_base():
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True, exist_ok=True)
    # Keep custom domain working
    (DIST/"CNAME").write_text("stockpricepredictions.com\n", encoding="utf-8")

def _read_last_trading_csv(region: str, country: str) -> pd.DataFrame:
    p = DATA / "LastTradingDay" / f"{region}" / f"{slugify(country)}.csv"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p)
    return df

def _format_pct(x):
    try:
        return f"{float(x):+.2f}%"
    except Exception:
        return ""

def _row_change_color(x: float) -> str:
    try:
        v = float(x)
    except Exception:
        return ""
    return "green" if v > 0 else ("red" if v < 0 else "")

def build_country(env, region: str, country: str, exchange: str):
    df = _read_last_trading_csv(region, country)
    if df.empty:
        return 0

    # compute target (T or T+1) based on market local close
    target_d = next_business_day_utc(region, country, exchange)
    target_str = target_d.isoformat()

    # country listing page (already existed in your SSG; keep pathing)
    out_dir = DIST / "groups" / slugify(region) / slugify(country)
    out_dir.mkdir(parents=True, exist_ok=True)

    tmpl = env.get_template("country_list.html")  # your existing list template
    html = tmpl.render(
        region=region,
        country=country,
        exchange=exchange,
        rows=[
            {
                "symbol": r.get("symbol"),
                "exchange": r.get("exchange"),
                "currency": r.get("Currency") or r.get("currency"),
                "sector": r.get("sector",""),
                "industry": r.get("industry",""),
                "change_pct": _format_pct(r.get("Change%")),
                "change_color": _row_change_color(r.get("Change%")),
                "close": r.get("Close"),
                "name": r.get("description") or r.get("description".capitalize(), ""),
                "slug": slugify(str(r.get("symbol"))),
            }
            for _, r in df.iterrows()
        ],
        build_time=datetime.utcnow().isoformat(timespec="seconds")+"Z",
    )
    (out_dir / "index.html").write_text(html, encoding="utf-8")

    # prediction page per symbol
    pred_tmpl = env.get_template("prediction_tomorrow.html")  # your existing detail template
    count = 0
    for _, r in df.iterrows():
        sym = str(r.get("symbol"))
        sym_dir = DIST / slugify(region) / slugify(country) / slugify(r.get("exchange", exchange)) / slugify(sym) / "prediction-tomorrow"
        sym_dir.mkdir(parents=True, exist_ok=True)
        html = pred_tmpl.render(
            region=region,
            country=country,
            exchange=r.get("exchange", exchange),
            symbol=sym,
            name=r.get("description") or "",
            o=r.get("open"),
            h=r.get("high"),
            l=r.get("low"),
            c=r.get("Close"),
            change_pct=_format_pct(r.get("Change%")),
            change_color=_row_change_color(r.get("Change%")),
            prediction_date=target_str,  # <- **shows correct local T/T+1**
            build_time=datetime.utcnow().isoformat(timespec="seconds")+"Z",
        )
        (sym_dir / "index.html").write_text(html, encoding="utf-8")
        count += 1
    return count

def build_home(env):
    # Very small home so root never 404s
    tmpl = env.get_template("home.html")
    html = tmpl.render(build_time=datetime.utcnow().isoformat(timespec="seconds")+"Z")
    (DIST / "index.html").write_text(html, encoding="utf-8")

def main():
    _ensure_base()
    env = _jinja()

    # copy static assets (css/js)
    static_src = ROOT / "static_assets"
    if static_src.exists():
        shutil.copytree(static_src, DIST / "assets")

    # Your regions/countries sources (same as before)
    meta_path = ROOT / "config.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        total = 0
        for m in meta.get("markets", []):
            total += build_country(env, m["region"], m["country"], m.get("exchange",""))
    else:
        # Fallback example: India / NSE
        total = build_country(env, "Asia - Pacific", "India", "NSE")

    build_home(env)
    print(f"Build complete -> {DIST}")
    print(f"[OK] pages: {total}")

if __name__ == "__main__":
    main()
