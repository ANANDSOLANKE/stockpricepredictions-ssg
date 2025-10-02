#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SGG-1 build.py — LastTradingDay version
---------------------------------------
Reads data from:
  Data/LastTradingDay/<Group>/<slug>.csv

Emits static site to:
  dist/
    index.html                     (Groups)
    groups/<group_slug>/index.html (Countries in that Group)
    groups/<group_slug>/<slug>/index.html (Stocks table for that country)
    sitemap.html

Notes
- Safe if files/folders are missing.
- Displays any CSV columns it finds; prefers a friendly order when available.
- Group/country names are taken from folder/file names (no hardcoded lists).
- Old dated folders like Data/03.09.2025 are ignored.
"""

import csv
import html
import os
import pathlib
import re
import sys
from datetime import datetime
from typing import Dict, List, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA_LAST = ROOT / "Data" / "LastTradingDay"
DIST = ROOT / "dist"

# ---------- utils ----------

def log(msg: str) -> None:
    print(msg, flush=True)

def ensure_dir(p: pathlib.Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

_slug_cleanup_re = re.compile(r"[^a-z0-9]+")
def slugify(s: str) -> str:
    s = s.strip().lower()
    s = _slug_cleanup_re.sub("-", s)
    return s.strip("-")

def read_csv_rows(path: pathlib.Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            rdr = csv.DictReader(f)
            for r in rdr:
                # normalize keys to lower-case
                rows.append({(k or "").strip().lower(): (v or "").strip() for k, v in r.items()})
    except FileNotFoundError:
        log(f"[WARN] Missing CSV: {path}")
    except Exception as e:
        log(f"[WARN] Failed reading {path}: {e}")
    return rows

# ---------- load data structure ----------
# tree[group][country_slug] -> {'group':str, 'country_slug':str, 'country_name':str, 'csv_path':Path, 'rows':[...]}
def load_last_trading_day() -> Dict[str, Dict[str, Dict]]:
    tree: Dict[str, Dict[str, Dict]] = {}

    if not DATA_LAST.exists():
        log(f"[WARN] {DATA_LAST.as_posix()} not found. No pages will be generated.")
        return tree

    for group_dir in sorted(p for p in DATA_LAST.iterdir() if p.is_dir()):
        group_name = group_dir.name
        gslug = slugify(group_name)
        tree.setdefault(gslug, {})
        # find all .csv files inside the group
        for csv_path in sorted(group_dir.glob("*.csv")):
            country_slug = csv_path.stem  # filename without .csv
            country_name = country_slug.replace("-", " ").title()
            rows = read_csv_rows(csv_path)
            tree[gslug][country_slug] = {
                "group": group_name,
                "group_slug": gslug,
                "country_slug": country_slug,
                "country_name": country_name,
                "csv_path": csv_path,
                "rows": rows,
            }
    return tree

# ---------- HTML helpers ----------

BASE_CSS = """
  :root { --bg:#0b1220; --card:#0f172a; --ink:#e5e7eb; --mut:#93c5fd; --line:#1f2a44; }
  *{box-sizing:border-box} body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:0;background:var(--bg);color:var(--ink)}
  a{color:var(--mut);text-decoration:none} a:hover{text-decoration:underline}
  .wrap{max-width:1200px;margin:0 auto;padding:24px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px;box-shadow:0 10px 30px rgba(0,0,0,.35)}
  h1,h2{margin:0 0 12px}
  ul.grid{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
  .pill{display:block;padding:10px 12px;border:1px solid var(--line);border-radius:12px}
  table{width:100%;border-collapse:collapse;font-size:14px}
  th,td{padding:8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
  .mut{opacity:.75}
  footer{opacity:.7;margin-top:18px;font-size:13px}
"""

def page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(title)}">
<style>{BASE_CSS}</style>
</head>
<body>
<div class="wrap">
{body}
<footer>Generated {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")} — LastTradingDay source</footer>
</div>
</body></html>"""

# ---------- rendering ----------

PREFERRED_COL_ORDER = [
    "symbol","name","exchange","price","currency",
    "change_percent","change_points","day_high","day_low",
    "sector","industry","tech_rating"
]

def make_group_index(groups: List[Tuple[str,str]]) -> str:
    items = "\n".join(
        f'<li><a class="pill" href="groups/{gslug}/index.html">{html.escape(gname)}</a></li>'
        for gslug, gname in groups
    )
    return page(
        "World markets — groups",
        f'<div class="card"><h1>Groups</h1><ul class="grid">{items}</ul></div>'
    )

def make_country_index(group_slug: str, group_name: str, countries: List[Tuple[str,str]]) -> str:
    items = "\n".join(
        f'<li><a class="pill" href="./{cslug}/index.html">{html.escape(cname)}</a></li>'
        for cslug, cname in countries
    )
    return page(
        f"{group_name} — countries",
        f'<div class="card"><h1>{html.escape(group_name)}</h1><ul class="grid">{items}</ul></div>'
    )

def make_stock_table(group_name: str, country_name: str, rows: List[Dict[str,str]]) -> str:
    # Gather columns present across rows; prefer friendly order
    cols: List[str] = []
    seen = set()
    for r in rows[:200]:  # sample
        for k in r.keys():
            k = k.lower()
            if k not in seen:
                seen.add(k)
                cols.append(k)
    # sort by preference
    def sort_key(k): 
        return (PREFERRED_COL_ORDER.index(k) if k in PREFERRED_COL_ORDER else 999, k)
    cols = sorted(cols, key=sort_key)
    if not cols:
        cols = ["symbol","name"]  # fallback

    # Build table
    thead = "<tr>" + "".join(f"<th>{html.escape(c)}</th>" for c in cols) + "</tr>"
    trs = []
    for r in rows:
        tds = "".join(f"<td>{html.escape(r.get(c,'') or '')}</td>" for c in cols)
        trs.append(f"<tr>{tds}</tr>")
    tbody = "\n".join(trs) if trs else '<tr><td class="mut" colspan="99">No rows</td></tr>'

    return page(
        f"{country_name} — stocks",
        f"""<div class="card">
<h1>{html.escape(country_name)}</h1>
<p class="mut">{html.escape(group_name)}</p>
<div style="overflow:auto"><table>
<thead>{thead}</thead>
<tbody>{tbody}</tbody>
</table></div>
</div>"""
    )

def make_sitemap(groups: List[Tuple[str,str]], tree: Dict[str, Dict[str, Dict]]) -> str:
    links = ['<li><a class="pill" href="index.html">Home</a></li>']
    for gslug, gname in groups:
        links.append(f'<li><a class="pill" href="groups/{gslug}/index.html">{html.escape(gname)}</a></li>')
        for cslug, info in sorted(tree[gslug].items(), key=lambda kv: kv[1]["country_name"].lower()):
            links.append(f'<li><a class="pill" href="groups/{gslug}/{cslug}/index.html">{html.escape(info["country_name"])} ({html.escape(info["group"])})</a></li>')
    return page("Sitemap", f'<div class="card"><h1>Sitemap</h1><ul class="grid">{"".join(links)}</ul></div>')

# ---------- main ----------

def main() -> int:
    log("== Build from Data/LastTradingDay ==")

    tree = load_last_trading_day()
    ensure_dir(DIST)

    if not tree:
        # generate a small placeholder
        log("[INFO] No LastTradingDay data found. Writing placeholder site.")
        body = '<div class="card"><h1>No data yet</h1><p>Put CSVs into <code>Data/LastTradingDay/&lt;Group&gt;/&lt;slug&gt;.csv</code>.</p></div>'
        (DIST / "index.html").write_text(page("No data", body), encoding="utf-8")
        (DIST / "sitemap.html").write_text(page("Sitemap","<div class='card'><h1>Empty</h1></div>"), encoding="utf-8")
        return 0

    # groups list
    groups_ordered: List[Tuple[str,str]] = []
    for gslug in sorted(tree.keys()):
        # any country entry contains the group_name
        any_country = next(iter(tree[gslug].values()))
        groups_ordered.append((gslug, any_country["group"]))

    # index.html
    (DIST / "index.html").write_text(make_group_index(groups_ordered), encoding="utf-8")

    # per-group pages
    for gslug, gname in groups_ordered:
        countries = sorted(
            ((cslug, info["country_name"]) for cslug, info in tree[gslug].items()),
            key=lambda x: x[1].lower()
        )
        gdir = DIST / "groups" / gslug
        ensure_dir(gdir)
        (gdir / "index.html").write_text(make_country_index(gslug, gname, countries), encoding="utf-8")

        # per-country pages
        for cslug, _cname in countries:
            info = tree[gslug][cslug]
            rows = info["rows"]
            html_page = make_stock_table(info["group"], info["country_name"], rows)
            cdir = gdir / cslug
            ensure_dir(cdir)
            (cdir / "index.html").write_text(html_page, encoding="utf-8")

    # sitemap.html
    (DIST / "sitemap.html").write_text(make_sitemap(groups_ordered, tree), encoding="utf-8")

    log(f"[OK] Build complete → {DIST.as_posix()}/index.html")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
