#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Inject a Top-5 predictions table into every prediction-tomorrow page, ranked by the
'Last 7-Day Accuracy' for the same (Region, Country, Exchange).

Assumptions about the built HTML (already true in your site):
- Each page has the line:  Region: X · Country: Y · Exchange: Z
- Each page shows:        Last 7-Day Accuracy: 85.71% (6/7)
- The Top Predictions card exists and contains:
     <tbody id="top5-rows"> ... </tbody>
- File layout: dist/.../<symbol>/prediction-tomorrow/index.html
"""

import os
import re
from pathlib import Path
from html import escape

DIST = Path("dist")

# Robust patterns (whitespace-insensitive, tolerant of spans etc.)
RE_META = re.compile(
    r"Region:\s*(?P<region>[^<·]+?)\s*·\s*Country:\s*(?P<country>[^<·]+?)\s*·\s*Exchange:\s*(?P<exch>[^<\n\r]+?)\s*<",
    flags=re.IGNORECASE | re.DOTALL,
)

RE_ACCURACY = re.compile(
    r"Last\s*7[-\s]?Day\s*Accuracy[:\s]*[^0-9]*(?P<pct>\d{1,3}(?:\.\d+)?)%",
    flags=re.IGNORECASE | re.DOTALL,
)

# For writing rows into the existing <tbody id="top5-rows">…</tbody>
RE_TBODY = re.compile(
    r'(<tbody[^>]*id=["\']top5-rows["\'][^>]*>)(.*?)(</tbody>)',
    flags=re.IGNORECASE | re.DOTALL,
)

# Get the symbol from path: .../<symbol>/prediction-tomorrow/index.html
RE_SYMBOL = re.compile(r"/([^/]+)/prediction-tomorrow/index\.html$", re.IGNORECASE)


def norm_key(x: str) -> str:
    return " ".join(x.strip().split()).lower()


def extract_symbol(html_path: Path) -> str:
    m = RE_SYMBOL.search(str(html_path).replace("\\", "/"))
    if m:
        return m.group(1)
    # fallback to directory name
    return html_path.parent.parent.name


def scan_pages():
    """Scan all prediction pages and collect meta + accuracy"""
    records = []  # dict per page: {path, sym, region, country, exch, acc_pct}

    for html_path in DIST.rglob("prediction-tomorrow/index.html"):
        try:
            html = html_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        # Region/Country/Exchange
        mm = RE_META.search(html)
        if not mm:
            # try a looser fallback without the trailing '<'
            mm2 = re.search(
                r"Region:\s*([^<·]+?)\s*·\s*Country:\s*([^<·]+?)\s*·\s*Exchange:\s*([^\n\r<]+)",
                html, re.IGNORECASE | re.DOTALL
            )
            if mm2:
                region, country, exch = mm2.group(1), mm2.group(2), mm2.group(3)
            else:
                continue
        else:
            region = mm.group("region")
            country = mm.group("country")
            exch = mm.group("exch")

        # Last-7 accuracy
        ma = RE_ACCURACY.search(html)
        if not ma:
            # if a page has no last-7 yet, skip (keeps table empty until it exists)
            continue
        try:
            acc = float(ma.group("pct"))
        except Exception:
            continue

        sym = extract_symbol(html_path)
        records.append(
            dict(
                path=html_path,
                symbol=sym,
                region=region.strip(),
                country=country.strip(),
                exch=exch.strip(),
                acc_pct=acc,
            )
        )
    return records


def group_by_exchange(records):
    by_ex = {}  # key: (region,country,exch) normalized -> list of recs
    for r in records:
        key = (norm_key(r["region"]), norm_key(r["country"]), norm_key(r["exch"]))
        by_ex.setdefault(key, []).append(r)
    # sort each list by accuracy desc
    for k in by_ex:
        by_ex[k].sort(key=lambda x: (-x["acc_pct"], x["symbol"]))
    return by_ex


def build_rows(top_list, current_symbol):
    """Create HTML rows for the top-5, excluding current symbol when possible."""
    rows = []
    count = 0

    # Prefer excluding the current page's symbol, but keep going if list is short.
    for rec in top_list:
        sym = rec["symbol"]
        if count >= 5:
            break
        if sym == current_symbol and len(top_list) > 5:
            continue
        rows.append(
            f"<tr><td>{escape(sym.upper())}</td>"
            f"<td class=\"text-right\">{rec['acc_pct']:.2f}%</td></tr>"
        )
        count += 1

    if not rows:
        rows = ['<tr><td colspan="2">No data yet</td></tr>']
    return "\n".join(rows)


def inject_rows(html, rows_html):
    """Replace inner of <tbody id="top5-rows">…</tbody>"""
    def repl(m):
        return f"{m.group(1)}\n{rows_html}\n{m.group(3)}"
    new_html, n = RE_TBODY.subn(repl, html, count=1)
    return new_html, n


def main():
    recs = scan_pages()
    if not recs:
        print("[warn] No pages with Last 7-Day Accuracy found. Nothing injected.")
        return

    by_ex = group_by_exchange(recs)

    injected = 0
    for r in recs:
        key = (norm_key(r["region"]), norm_key(r["country"]), norm_key(r["exch"]))
        leaderboard = by_ex.get(key, [])
        if not leaderboard:
            continue

        rows_html = build_rows(leaderboard, current_symbol=r["symbol"])

        try:
            html = r["path"].read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        new_html, n = inject_rows(html, rows_html)
        if n == 0:
            # No anchor? skip silently.
            continue

        try:
            r["path"].write_text(new_html, encoding="utf-8")
            injected += 1
        except Exception:
            pass

    print(f"[OK] Top-5 injected into {injected} pages")


if __name__ == "__main__":
    main()
     
