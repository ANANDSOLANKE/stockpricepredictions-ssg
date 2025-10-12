#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Inject a 7-day backtest table into each prediction-tomorrow page.

Uses Historical CSV data (symbol + description) to reconstruct
the last 7 trading days and compare predicted vs. actual movement.
"""

from __future__ import annotations
import csv, html, re, time
from pathlib import Path
from typing import Dict, List, Tuple, Optional

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
DATA_HIST = ROOT / "Data" / "Historical"

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

time.sleep(2)

def _f(x):
    try: return float(x)
    except Exception: return None

def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")

def list_recent_dates(n: int = 40) -> List[str]:
    if not DATA_HIST.exists(): return []
    dates = [d.name for d in DATA_HIST.iterdir() if d.is_dir() and re.match(r"^\d{4}-\d{2}-\d{2}$", d.name)]
    dates.sort()
    return dates[-n:]

_hist_cache: Dict[Tuple[str, str], Dict[str, List[Tuple[str, float]]]] = {}
_slugmap_cache: Dict[Tuple[str, str], Dict[str, str]] = {}

# --- CSV reader -------------------------------------------------------
def read_country_hist(date_folder: str, group_dir: str, country_slug: str):
    p = DATA_HIST / date_folder / group_dir / f"{country_slug}.csv"
    if not p.exists(): return []
    rows = []
    with open(p, "r", encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            sym = (r.get("symbol") or "").strip().upper()
            desc = (r.get("description") or "").strip()
            close = r.get("Close") or r.get("close")
            if not sym or not close: continue
            rows.append((sym, _f(close), desc))
    return rows

# --- Build cache ------------------------------------------------------
def get_country_history(group_dir: str, country_slug: str, days: int = 16):
    key = (group_dir, country_slug)
    if key in _hist_cache: return _hist_cache[key]

    hist: Dict[str, List[Tuple[str, float]]] = {}
    smap: Dict[str, str] = {}

    def add_slugs(symbol: str, desc: str):
        variants = [
            symbol,
            re.sub(r"(\.|\-|_)?eq$", "", symbol),
            re.sub(r"\.[a-z]{1,4}$", "", symbol),
            desc,
            desc.replace("Limited","").replace("Ltd","").strip()
        ]
        for v in variants:
            v = slugify(v)
            if not v: continue
            smap.setdefault(v, symbol)
            smap.setdefault(v.replace("-", ""), symbol)

    for d in list_recent_dates(days * 3):
        for sym, close, desc in read_country_hist(d, group_dir, country_slug):
            if close is None: continue
            hist.setdefault(sym, []).append((d, close))
            add_slugs(sym, desc)

    for s, arr in hist.items():
        hist[s] = sorted(arr)[-days:]
    _hist_cache[key] = hist
    _slugmap_cache[key] = smap
    return hist

# --- Resolve symbol ---------------------------------------------------
def resolve_symbol(group_dir: str, country_slug: str, sym_slug: str, name_slug: Optional[str]):
    key = (group_dir, country_slug)
    if key not in _slugmap_cache:
        _ = get_country_history(group_dir, country_slug)
    smap = _slugmap_cache.get(key, {})
    if not smap: return None

    candidates = [sym_slug]
    if name_slug: candidates.append(name_slug)
    for c in candidates:
        base = slugify(c)
        if base in smap: return smap[base]
        base = base.replace("-", "")
        if base in smap: return smap[base]
        for k, v in smap.items():
            if base in k or k in base: return v
    return None

# --- AI logic ----------------------------------------------------------
def predict_from(p1: float, p2: float):
    if p1 is None or p2 is None: return None
    return "Bullish" if p1 > p2 else "Bearish"

def actual_move(today: float, prev: float):
    if today is None or prev is None: return None
    return "Bullish" if today > prev else "Bearish"

def backtest(series: List[Tuple[str, float]]):
    if len(series) < 3: return []
    out = []
    for i in range(2, len(series)):
        d, c = series[i]
        _, p1 = series[i-1]; _, p2 = series[i-2]
        pred = predict_from(p1, p2)
        act = actual_move(c, p1)
        if pred and act: out.append((d, pred, act, pred == act))
    return out[-7:]

# --- HTML helpers -----------------------------------------------------
def build_html(rows):
    wins = sum(1 for *_, w in rows if w)
    total = len(rows)
    winpct = round((wins/total)*100,2) if total else 0
    trs = []
    for d,p,a,w in rows:
        color = "#3ddc97" if w else "#ff6b6b"
        trs.append(f"<tr><td>{d}</td><td>{p}</td><td>{a}</td><td style='color:{color};font-weight:700'>{'Win' if w else 'Loss'}</td></tr>")
    summary = f"<div style='margin:10px 0;padding:10px;border:1px solid #244;border-radius:12px;background:#0f172a;display:flex;justify-content:space-between'><span>Last 7-Day Accuracy:</span><b style='color:#3ddc97'>{winpct}% ({wins}/{total})</b></div>"
    return f"<div class='card'><h3 class='h3'>Last 7-Day Performance</h3>{summary}<div class='table-wrap'><table class='table'><thead><tr><th>Date</th><th>AI Prediction</th><th>Actual</th><th>Result</th></tr></thead><tbody>{''.join(trs)}</tbody></table></div></div>"

def inject_html(page, snippet):
    if "Last 7-Day Performance" in page: return page
    if "</main>" in page: return page.replace("</main>", snippet + "\n</main>")
    if "</body>" in page: return page.replace("</body>", snippet + "\n</body>")
    return page + snippet

def get_company_from_html(txt):
    m = re.search(r"\(([^)]+)\)", txt)
    return m.group(1).strip() if m else None

# --- Main --------------------------------------------------------------
def main():
    found = updated = skip_map = 0
    for file in DIST.glob("**/prediction-tomorrow/index.html"):
        found += 1
        parts = file.parts
        try:
            group = parts[-6].lower()
            country = parts[-5].lower()
            sym = parts[-3].lower()
        except Exception:
            continue
        group_dir = GROUP_DIR_BY_SLUG.get(group) or slug_to_title_dir(group)
        txt = file.read_text(encoding="utf-8")
        comp = get_company_from_html(txt)
        name_slug = slugify(comp) if comp else None
        hist = get_country_history(group_dir, country, 16)
        real_sym = resolve_symbol(group_dir, country, sym, name_slug)
        if not real_sym or real_sym not in hist:
            skip_map += 1
            continue
        series = hist[real_sym]
        rows = backtest(series)
        if not rows: continue
        file.write_text(inject_html(txt, build_html(rows)), encoding="utf-8")
        updated += 1
    print(f"[scan] {found} pages | [OK] injected {updated} | [skip-map] {skip_map}")

if __name__ == "__main__":
    main()
