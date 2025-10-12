#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
import csv, html, re, time
from pathlib import Path
from typing import Dict, List, Tuple, Optional

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
DATA_HIST = ROOT / "Data" / "Historical"
DATA_LAST = ROOT / "Data" / "LastTradingDay"

GROUP_DIR_BY_SLUG = {
    "asia-pacific": "Asia - Pacific",
    "europe": "Europe",
    "middle-east-africa": "Middle East - Africa",
    "mexico-south-america": "Mexico - South America",
    "north-america": "North America",
    "global-indices": "Global Indices",
}
def slug_to_title_dir(slug: str) -> str:
    parts = [p for p in re.split(r"[^a-z0-9]+", slug.lower()) if p]
    return " ".join(w.capitalize() for w in parts)

time.sleep(2)  # let build.py finish writing

def _f(x):
    try: return float(x)
    except: return None

def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "item"

def list_recent_dates(n: int = 40) -> List[str]:
    if not DATA_HIST.exists(): return []
    dates = [d.name for d in DATA_HIST.iterdir()
             if d.is_dir() and re.match(r"^\d{4}-\d{2}-\d{2}$", d.name)]
    dates.sort()
    return dates[-n:]

# ---------- historical readers + caches ----------
_hist_cache: Dict[Tuple[str, str], Dict[str, List[Tuple[str, float]]]] = {}
_hist_slug_map_cache: Dict[Tuple[str, str], Dict[str, str]] = {}
_slug_cache_last: Dict[Tuple[str, str], Dict[str, str]] = {}

def read_country_hist_csv(date_folder: str, group_dir: str, country_slug: str) -> List[Tuple[str, Optional[float]]]:
    p = DATA_HIST / date_folder / group_dir / f"{country_slug}.csv"
    if not p.exists(): return []
    out = []
    with open(p, "r", encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            sym = (r.get("symbol") or "").strip().upper()
            close = _f(r.get("close"))
            if sym:
                out.append((sym, close))
    return out

def get_country_history(group_dir: str, country_slug: str, how_many_days: int = 16) -> Dict[str, List[Tuple[str, float]]]:
    key = (group_dir, country_slug)
    if key in _hist_cache:
        return _hist_cache[key]

    dates = list_recent_dates(how_many_days * 3)
    hist: Dict[str, List[Tuple[str, float]]] = {}
    for d in dates:
        for sym, close in read_country_hist_csv(d, group_dir, country_slug):
            if close is None:
                continue
            hist.setdefault(sym, []).append((d, float(close)))

    # sort & trim; also build slug map of historical symbols
    slug_map: Dict[str, str] = {}
    for s in list(hist.keys()):
        series = sorted(hist[s], key=lambda x: x[0])
        hist[s] = series[-(how_many_days+5):]
        slug_map[slugify(s)] = s

    _hist_cache[key] = hist
    _hist_slug_map_cache[key] = slug_map
    return hist

def hist_symbol_from_slug(group_dir: str, country_slug: str, sym_slug: str) -> Optional[str]:
    key = (group_dir, country_slug)
    if key not in _hist_slug_map_cache:
        _ = get_country_history(group_dir, country_slug)
    slug_map = _hist_slug_map_cache.get(key, {})
    if sym_slug in slug_map:
        return slug_map[sym_slug]
    # try relaxed variants (strip common suffixes)
    candidates = {
        sym_slug,
        re.sub(r"(\.|\-|_|\/)?eq$", "", sym_slug),
        re.sub(r"\.[a-z]{1,4}$", "", sym_slug),  # .ns, .ax, .to, etc.
    }
    for c in candidates:
        if c in slug_map:
            return slug_map[c]
    return None

def build_symbol_slug_map_last(group_dir: str, country_slug: str) -> Dict[str, str]:
    p = DATA_LAST / group_dir / f"{country_slug}.csv"
    mp: Dict[str, str] = {}
    if p.exists():
        with open(p, "r", encoding="utf-8", newline="") as f:
            rdr = csv.DictReader(f)
            for r in rdr:
                sym = (r.get("symbol") or "").strip().upper()
                if sym:
                    mp[slugify(sym)] = sym
    return mp

def last_symbol_from_slug(group_dir: str, country_slug: str, sym_slug: str) -> Optional[str]:
    key = (group_dir, country_slug)
    if key not in _slug_cache_last:
        _slug_cache_last[key] = build_symbol_slug_map_last(group_dir, country_slug)
    mp = _slug_cache_last[key]
    if sym_slug in mp:
        return mp[sym_slug]
    # relaxed variants
    candidates = {
        sym_slug,
        re.sub(r"(\.|\-|_|\/)?eq$", "", sym_slug),
        re.sub(r"\.[a-z]{1,4}$", "", sym_slug),
    }
    for c in candidates:
        if c in mp:
            return mp[c]
    return None

# ---------- backtest ----------
def predict_from(prev_close: float, prev2_close: float) -> Optional[str]:
    if prev_close is None or prev2_close is None:
        return None
    return "Bullish" if prev_close > prev2_close else "Bearish"

def actual_move(today_close: float, prev_close: float) -> Optional[str]:
    if today_close is None or prev_close is None:
        return None
    return "Bullish" if today_close > prev_close else "Bearish"

def backtest_last7(series: List[Tuple[str, float]]) -> List[Tuple[str, str, str, bool]]:
    if len(series) < 3: return []
    rows: List[Tuple[str, str, str, bool]] = []
    for i in range(2, len(series)):
        d_t, c_t = series[i]
        _, c_t1 = series[i-1]
        _, c_t2 = series[i-2]
        pred = predict_from(c_t1, c_t2)
        act  = actual_move(c_t, c_t1)
        if pred and act:
            rows.append((d_t, pred, act, pred == act))
    return rows[-7:]

# ---------- HTML ----------
def build_table_html(rows: List[Tuple[str, str, str, bool]]) -> str:
    wins = sum(1 for *_, w in rows if w)
    total = len(rows)
    win_pct = round((wins / total) * 100, 2) if total else 0.0
    body = []
    for d, pred, act, win in rows:
        color = "#3ddc97" if win else "#ff6b6b"
        body.append(
            "<tr>"
            f"<td>{html.escape(d)}</td>"
            f"<td>{html.escape(pred)}</td>"
            f"<td>{html.escape(act)}</td>"
            f"<td style='color:{color};font-weight:700'>{'Win' if win else 'Loss'}</td>"
            "</tr>"
        )
    summary = (
        "<div class='mb-6 p-4' style='background:#0f172a;border:1px solid #244;"
        "border-radius:12px;display:flex;gap:12px;align-items:center;justify-content:space-between;'>"
        "<span class='small' style='opacity:.85'>Last 7 Trading Days Accuracy:</span>"
        f"<div><span style='color:#3ddc97;font-weight:800;font-size:24px'>{win_pct}%</span>"
        f"<span class='small' style='margin-left:8px;opacity:.8'>({wins} / {total} Wins)</span></div>"
        "</div>"
    )
    return (
        "<div class='card'>"
        "<h3 class='h3'>Last 7-Day Performance</h3>"
        f"{summary}"
        "<div class='table-wrap'><table class='table'>"
        "<thead><tr><th>Date</th><th>AI Prediction</th><th>Actual</th><th>Result</th></tr></thead>"
        f"<tbody>{''.join(body) if body else '<tr><td colspan=4>No data</td></tr>'}</tbody>"
        "</table></div></div>"
    )

def inject_into_html(html_txt: str, snippet: str) -> str:
    if "</main>" in html_txt:
        return html_txt.replace("</main>", snippet + "\n</main>")
    if "</body>" in html_txt:
        return html_txt.replace("</body>", snippet + "\n</body>")
    return html_txt + snippet

# ---------- main ----------
def main():
    found = 0
    updated = 0
    skip_group = skip_hist = skip_short = skip_map = 0

    for index_html in DIST.glob("**/prediction-tomorrow/index.html"):
        found += 1
        parts = index_html.parts
        try:
            group_slug   = parts[-6].lower()
            country_slug = parts[-5].lower()
            symbol_slug  = parts[-3].lower()
        except Exception:
            skip_group += 1
            continue

        group_dir = GROUP_DIR_BY_SLUG.get(group_slug) or slug_to_title_dir(group_slug)

        txt = index_html.read_text(encoding="utf-8")
        if "Last 7-Day Performance" in txt:
            continue

        # 1) Try resolve via LastTradingDay mapping
        symbol = last_symbol_from_slug(group_dir, country_slug, symbol_slug)
        # 2) If not, try resolve via Historical slug map
        if not symbol:
            symbol = hist_symbol_from_slug(group_dir, country_slug, symbol_slug)
        if not symbol:
            skip_map += 1
            continue

        hist = get_country_history(group_dir, country_slug, how_many_days=16)
        series = hist.get(symbol)
        if not series:
            # final fallback: look up by slug in historical
            sym2 = hist_symbol_from_slug(group_dir, country_slug, symbol_slug)
            if sym2:
                series = hist.get(sym2)
        if not series:
            skip_hist += 1
            continue

        if len(series) < 3:
            skip_short += 1
            continue

        rows = backtest_last7(series)
        if not rows:
            skip_short += 1
            continue

        index_html.write_text(inject_into_html(txt, build_table_html(rows)), encoding="utf-8")
        updated += 1

    print(f"[scan] prediction-tomorrow pages: {found}")
    print(f"[skip] parse/group: {skip_group}  map-miss: {skip_map}  no-history: {skip_hist}  short: {skip_short}")
    print(f"[OK] injected: {updated}")

if __name__ == "__main__":
    main()
