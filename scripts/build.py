#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SGG-1 build.py — LastTradingDay + Logos + Per-stock SEO pages
-------------------------------------------------------------
Input:
  Data/LastTradingDay/<Group>/<country_slug>.csv

Optional logos (any that exist will be used):
  logos/<country_slug>.(png|svg|jpg|webp)
  logos/groups/<group_slug>.(png|svg|jpg|webp)
  logos/stocks/<SYMBOL>.(png|svg|jpg|webp)
  logos_index.json  # optional dict overrides, e.g. {"countries":{"india":"logos/india.svg"}}

Output (dist/):
  index.html
  groups/<group_slug>/index.html
  groups/<group_slug>/<country_slug>/index.html
  stocks/<group_slug>/<country_slug>/<SYMBOL>.html
  sitemap.html
"""

import csv, html, json, os, re, sys, pathlib
from datetime import datetime
from typing import Dict, List, Tuple, Optional

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA_LAST = ROOT / "Data" / "LastTradingDay"
DIST = ROOT / "dist"
LOGOS = ROOT / "logos"
LOGOS_INDEX = ROOT / "logos_index.json"

# ---------- utils ----------
def log(m: str): print(m, flush=True)
def ensure_dir(p: pathlib.Path): p.mkdir(parents=True, exist_ok=True)

_slug_re = re.compile(r"[^a-z0-9]+")
def slugify(s: str) -> str:
    return _slug_re.sub("-", (s or "").strip().lower()).strip("-")

def read_csv_rows(path: pathlib.Path) -> List[Dict[str,str]]:
    rows: List[Dict[str,str]] = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            rows.append({(k or "").strip().lower(): (v or "").strip() for k,v in r.items()})
    return rows

def try_read_json(p: pathlib.Path) -> dict:
    if not p.exists(): return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception as e:
        log(f"[WARN] logos_index.json parse error: {e}")
        return {}

def find_logo_from_index(index: dict, kind: str, key: str) -> Optional[pathlib.Path]:
    try:
        rel = (index.get(kind) or {}).get(key)
        if rel:
            p = ROOT / rel
            return p if p.exists() else None
    except Exception:
        pass
    return None

def find_logo_fallbacks(folder: pathlib.Path, stem: str) -> Optional[pathlib.Path]:
    for ext in ("png","svg","jpg","jpeg","webp"):
        p = folder / f"{stem}.{ext}"
        if p.exists(): return p
    return None

def logo_src_for(group_slug: str, country_slug: Optional[str], symbol: Optional[str], index: dict) -> Optional[str]:
    # 1) explicit index.json wins
    if country_slug:
        p = find_logo_from_index(index, "countries", country_slug)
        if p: return p.relative_to(ROOT).as_posix()
    if symbol:
        p = find_logo_from_index(index, "stocks", symbol.upper())
        if p: return p.relative_to(ROOT).as_posix()
    p = find_logo_from_index(index, "groups", group_slug)
    if p: return p.relative_to(ROOT).as_posix()

    # 2) folder fallbacks
    if symbol:
        p = find_logo_fallbacks(LOGOS / "stocks", symbol.upper())
        if p: return p.relative_to(ROOT).as_posix()
    if country_slug:
        p = find_logo_fallbacks(LOGOS, country_slug)
        if p: return p.relative_to(ROOT).as_posix()
    p = find_logo_fallbacks(LOGOS / "groups", group_slug)
    if p: return p.relative_to(ROOT).as_posix()
    return None

# ---------- load data ----------
# tree[group][country] = {group_name, group_slug, country_slug, country_name, csv_path, rows}
def load_last_trading_day() -> Dict[str, Dict[str, Dict]]:
    tree: Dict[str, Dict[str, Dict]] = {}
    if not DATA_LAST.exists():
        log(f"[WARN] {DATA_LAST} not found")
        return tree

    for group_dir in sorted([d for d in DATA_LAST.iterdir() if d.is_dir()]):
        group_name = group_dir.name
        group_slug = slugify(group_name)
        tree.setdefault(group_slug, {})
        for csv_path in sorted(group_dir.glob("*.csv")):
            country_slug = csv_path.stem
            country_name = country_slug.replace("-", " ").title()
            try:
                rows = read_csv_rows(csv_path)
            except Exception as e:
                log(f"[WARN] read fail {csv_path}: {e}")
                rows = []
            tree[group_slug][country_slug] = {
                "group_name": group_name,
                "group_slug": group_slug,
                "country_slug": country_slug,
                "country_name": country_name,
                "csv_path": csv_path,
                "rows": rows,
            }
    return tree

# ---------- HTML ----------
BASE_CSS = """
:root { --bg:#0b1220; --card:#0f172a; --ink:#e5e7eb; --mut:#93c5fd; --line:#1f2a44; }
*{box-sizing:border-box} body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:0;background:var(--bg);color:var(--ink)}
a{color:var(--mut);text-decoration:none} a:hover{text-decoration:underline}
.wrap{max-width:1200px;margin:0 auto;padding:24px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px;box-shadow:0 10px 30px rgba(0,0,0,.35)}
h1,h2{margin:0 0 12px}
ul.grid{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
.pill{display:block;padding:10px 12px;border:1px solid var(--line);border-radius:12px}
.flex{display:flex;gap:16px;align-items:center}
.logo{width:32px;height:32px;object-fit:contain;background:#fff1;border-radius:8px;padding:4px;border:1px solid #20304d}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
.mut{opacity:.75}
footer{opacity:.7;margin-top:18px;font-size:13px}
"""

def page(title: str, body_html: str, meta_desc: Optional[str]=None) -> str:
    md = meta_desc or title
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(md)}">
<style>{BASE_CSS}</style></head>
<body><div class="wrap">
{body_html}
<footer>Generated {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}</footer>
</div></body></html>"""

PREF_COLS = ["symbol","name","exchange","price","currency","change_percent","change_points","day_high","day_low","sector","industry","tech_rating"]

def columns_for(rows: List[Dict[str,str]]) -> List[str]:
    if not rows: return ["symbol","name"]
    seen, cols = set(), []
    for r in rows[:400]:
        for k in r:
            k = k.lower()
            if k not in seen:
                seen.add(k); cols.append(k)
    cols.sort(key=lambda k: (PREF_COLS.index(k) if k in PREF_COLS else 999, k))
    return cols

# ---------- renderers ----------
def render_index(groups: List[Tuple[str,str]], logo_index: dict) -> str:
    items = []
    for gslug, gname in groups:
        g_logo = logo_src_for(gslug, None, None, logo_index)
        icon = f'<img class="logo" src="/{g_logo}" alt="">' if g_logo else ""
        items.append(f'<li><a class="pill flex" href="groups/{gslug}/index.html">{icon}<span>{html.escape(gname)}</span></a></li>')
    return page("World markets — groups", f'<div class="card"><h1>Groups</h1><ul class="grid">{"".join(items)}</ul></div>')

def render_group(gslug: str, gname: str, countries: List[Tuple[str,str]], logo_index: dict) -> str:
    items = []
    for cslug, cname in countries:
        c_logo = logo_src_for(gslug, cslug, None, logo_index)
        icon = f'<img class="logo" src="/{c_logo}" alt="">' if c_logo else ""
        items.append(f'<li><a class="pill flex" href="./{cslug}/index.html">{icon}<span>{html.escape(cname)}</span></a></li>')
    head_logo = logo_src_for(gslug, None, None, logo_index)
    head = f'<div class="flex"><h1>{html.escape(gname)}</h1>' + (f'<img class="logo" src="/{head_logo}" alt="">' if head_logo else "") + '</div>'
    return page(f"{gname} — countries", f'<div class="card">{head}<ul class="grid">{"".join(items)}</ul></div>')

def render_country(gslug: str, gname: str, cslug: str, cname: str, rows: List[Dict[str,str]], logo_index: dict) -> str:
    cols = columns_for(rows)
    thead = "<tr>" + "".join(f"<th>{html.escape(c)}</th>" for c in cols) + "</tr>"
    trs = []
    for r in rows:
        symbol = (r.get("symbol") or r.get("ticker") or "").strip()
        link = f'stocks/{gslug}/{cslug}/{symbol}.html' if symbol else None
        tds = []
        for c in cols:
            val = r.get(c,"")
            if c == "symbol" and symbol:
                tds.append(f'<td><a href="/{link}">{html.escape(symbol)}</a></td>')
            else:
                tds.append(f'<td>{html.escape(val)}</td>')
        trs.append("<tr>" + "".join(tds) + "</tr>")
    body_table = "\n".join(trs) if trs else '<tr><td class="mut" colspan="99">No rows</td></tr>'
    c_logo = logo_src_for(gslug, cslug, None, logo_index)
    head = f'<div class="flex"><h1>{html.escape(cname)}</h1>' + (f'<img class="logo" src="/{c_logo}" alt="">' if c_logo else "") + f'<span class="mut">{html.escape(gname)}</span></div>'
    html_table = f"""<div class="card">{head}
<div style="overflow:auto">
<table><thead>{thead}</thead><tbody>{body_table}</tbody></table>
</div></div>"""
    return page(f"{cname} — stocks", html_table, meta_desc=f"Browse {cname} stocks, prices, and basic fundamentals.")

def render_stock(gslug: str, gname: str, cslug: str, cname: str, symbol: str, row: Dict[str,str], logo_index: dict) -> str:
    s_logo = logo_src_for(gslug, cslug, symbol, logo_index)
    icon = f'<img class="logo" src="/{s_logo}" alt="">' if s_logo else ""
    title = f"{symbol} price prediction tomorrow | AI analysis"
    h1 = f"{symbol} — {cname} ({gname})"
    # simple key facts block
    facts = []
    for k in ("name","exchange","price","currency","sector","industry","tech_rating","change_percent","change_points","day_high","day_low"):
        v = row.get(k) or row.get(k.lower())
        if v: facts.append(f"<li><strong>{html.escape(k)}:</strong> {html.escape(v)}</li>")
    fact_html = "<ul>" + "".join(facts) + "</ul>" if facts else "<p class='mut'>No key facts available.</p>"
    body = f"""<div class="card">
<div class="flex"><h1>{html.escape(h1)}</h1>{icon}</div>
<p class="mut">SEO stub — replace this section with your model output (signal, confidence, last close, support/resistance).</p>
{fact_html}
</div>"""
    return page(title, body, meta_desc=f"AI prediction and key facts for {symbol} listed in {cname} ({gname}).")

# ---------- main ----------
def main() -> int:
    log("== Build from Data/LastTradingDay with logos & stock pages ==")

    logo_index = try_read_json(LOGOS_INDEX)
    tree = load_last_trading_day()
    ensure_dir(DIST)

    if not tree:
        (DIST / "index.html").write_text(page("No data","<div class='card'><h1>No data</h1></div>"), encoding="utf-8")
        (DIST / "sitemap.html").write_text(page("Sitemap","<div class='card'><h1>Empty</h1></div>"), encoding="utf-8")
        return 0

    # groups (slug, name)
    groups: List[Tuple[str,str]] = []
    for gslug in sorted(tree.keys()):
        any_country = next(iter(tree[gslug].values()))
        groups.append((gslug, any_country["group_name"]))

    # index.html
    (DIST / "index.html").write_text(render_index(groups, logo_index), encoding="utf-8")

    # group & country pages + per-stock SEO pages
    for gslug, gname in groups:
        countries = sorted(
            ((cslug, info["country_name"]) for cslug, info in tree[gslug].items()),
            key=lambda x: x[1].lower()
        )
        gdir = DIST / "groups" / gslug
        ensure_dir(gdir)
        (gdir / "index.html").write_text(render_group(gslug, gname, countries, logo_index), encoding="utf-8")

        for cslug, cname in countries:
            info = tree[gslug][cslug]
            rows = info["rows"]
            # country table
            cdir = gdir / cslug
            ensure_dir(cdir)
            (cdir / "index.html").write_text(render_country(gslug, gname, cslug, cname, rows, logo_index), encoding="utf-8")
            # per-stock pages
            sdir = DIST / "stocks" / gslug / cslug
            ensure_dir(sdir)
            for r in rows:
                sym = (r.get("symbol") or r.get("ticker") or "").strip()
                if not sym: continue
                (sdir / f"{sym}.html").write_text(render_stock(gslug, gname, cslug, cname, sym, r, logo_index), encoding="utf-8")

    # sitemap
    links = ['<li><a class="pill" href="index.html">Home</a></li>']
    for gslug, gname in groups:
        links.append(f'<li><a class="pill" href="groups/{gslug}/index.html">{html.escape(gname)}</a></li>')
        for cslug, info in sorted(tree[gslug].items(), key=lambda kv: kv[1]["country_name"].lower()):
            links.append(f'<li><a class="pill" href="groups/{gslug}/{cslug}/index.html">{html.escape(info["country_name"])} ({html.escape(info["group_name"])})</a></li>')
            # list stock pages too (lightweight)
            for r in info["rows"][:3000]:  # limit to keep sitemap manageable
                sym = (r.get("symbol") or r.get("ticker") or "").strip()
                if sym:
                    links.append(f'<li><a class="pill" href="stocks/{gslug}/{cslug}/{sym}.html">{html.escape(sym)}</a></li>')
    (DIST / "sitemap.html").write_text(page("Sitemap", f"<div class='card'><h1>Sitemap</h1><ul class='grid'>{''.join(links)}</ul></div>"), encoding="utf-8")

    log(f"[OK] Build complete → {DIST / 'index.html'}")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
