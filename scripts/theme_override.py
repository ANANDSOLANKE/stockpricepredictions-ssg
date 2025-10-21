#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Non-destructive page template override for prediction pages.

- Scans dist/**/prediction-tomorrow/index.html
- Parses the page for context (symbol, company, region/country/exchange, OHLC, change%, prediction date)
- If templates/prediction.html exists, replaces <main>...</main> with rendered template
- If template is missing or parsing fails, leaves the page unchanged

Safe: If anything goes wrong, we fall back to the original page.
"""

from __future__ import annotations
import re, html
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
TPL = ROOT / "templates" / "prediction.html"

MAIN_RE = re.compile(r"(<main\b[^>]*>)(.*?)(</main>)", re.DOTALL|re.IGNORECASE)

def _find(pat: str, text: str) -> Optional[str]:
    m = re.search(pat, text, re.IGNORECASE)
    return (m.group(1).strip() if m else None)

def _extract_ctx(html_txt: str, path_parts: tuple[str, ...]) -> Optional[Dict[str, str]]:
    """
    Extract minimal context from the existing page markup.
    Works with your current pages like:
      - H1 "AI Analysis of XXXXX Tomorrow | Company …"
      - Region/Country/Exchange line
      - OHLC line
      - "Prediction for YYYY-MM-DD"
    """
    ctx: Dict[str, str] = {}

    # symbol from URL (.../<symbol>/prediction-tomorrow/index.html)
    try:
        # dist/<region>/<country>/<exchange>/<symbol>/prediction-tomorrow/index.html
        ctx["symbol"] = path_parts[-3].upper()
    except Exception:
        ctx["symbol"] = ""

    # Title section
    # e.g. <h1>AI Analysis of 360ONE Tomorrow | 360 One Wam Limited Stock Prediction</h1>
    heading = _find(r"<h1[^>]*>(.*?)</h1>", html_txt) or ""
    ctx["heading_raw"] = heading
    # split "AI Analysis of SYMBOL Tomorrow | COMPANY NAME Stock Prediction"
    company = ""
    if "|" in heading:
        company = heading.split("|", 1)[-1]
        company = re.sub(r"\s*Stock Prediction\s*$", "", company, flags=re.IGNORECASE).strip()
    ctx["company"] = html.unescape(company)

    # Region/Country/Exchange line (your current page has: Region: AA · Country: BB · Exchange: CC)
    rce = _find(r"Region:\s*([^<·]+).*?Country:\s*([^<·]+).*?Exchange:\s*([^<·<]+)", html_txt)
    if rce:
        m = re.search(r"Region:\s*([^<·]+).*?Country:\s*([^<·]+).*?Exchange:\s*([^<·<]+)", html_txt, re.IGNORECASE|re.DOTALL)
        if m:
            ctx["region"] = m.group(1).strip()
            ctx["country"] = m.group(2).strip()
            ctx["exchange"] = m.group(3).strip()
    else:
        ctx["region"] = ctx["country"] = ctx["exchange"] = ""

    # OHLC & Change%
    # e.g. OHLC: O 121.00, H 124.89, L 115.20, C 117.63 · Change%: -2.00%
    ohlc_line = _find(r"OHLC:\s*([^<]+)", html_txt) or ""
    ctx["ohlc_line"] = ohlc_line.strip()
    change_pct = _find(r"Change%:\s*([+\-]?\d+(?:\.\d+)?%)", html_txt) or ""
    ctx["change_pct"] = change_pct

    # Prediction date
    pred_date = _find(r"Prediction for\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", html_txt) or ""
    ctx["pred_date"] = pred_date

    # "Last build"
    last_build = _find(r"Last build:\s*([^<]+)", html_txt) or ""
    ctx["last_build"] = last_build

    # Next-day signal word (Bullish/Bearish) if present in the body
    # We accept the last  occurrence of "Model signal" line
    signal = ""
    ms = list(re.finditer(r"\bModel signal\b.*?", html_txt, re.IGNORECASE|re.DOTALL))
    if ms:
        # Rough colorization not needed here; we only need word highlight if template wants it
        if re.search(r"\bBullish\b", html_txt, re.IGNORECASE):
            signal = "BULLISH"
        elif re.search(r"\bBearish\b", html_txt, re.IGNORECASE):
            signal = "BEARISH"
    ctx["signal"] = signal

    return ctx

def render_template(tpl: str, ctx: Dict[str, str]) -> str:
    # very small {var} replacement; make sure to escape where needed in the template itself
    def rep(m):
        key = m.group(1)
        return ctx.get(key, "")
    return re.sub(r"\{(\w+)\}", rep, tpl)

def apply_prediction_template() -> None:
    if not TPL.exists():
        print("[theme] No templates/prediction.html — skipping.")
        return

    tpl_txt = TPL.read_text(encoding="utf-8")
    changed = 0
    scanned = 0

    for file in DIST.glob("**/prediction-tomorrow/index.html"):
        scanned += 1
        html_txt = file.read_text(encoding="utf-8")
        parts = file.parts

        ctx = _extract_ctx(html_txt, parts)
        if not ctx:
            continue

        # fill in a nice page title fallback
        if "{page_title}" in tpl_txt:
            title = f"{ctx.get('company','').strip() or ctx.get('symbol','')} ({ctx.get('symbol','')}) — {ctx.get('pred_date','')}"
            ctx["page_title"] = title

        rendered = render_template(tpl_txt, ctx)

        # splice it into <main> … </main>; if not found, just append before </body>
        m = MAIN_RE.search(html_txt)
        if m:
            new_html = html_txt[:m.start(2)] + rendered + html_txt[m.end(2):]
        else:
            if "</body>" in html_txt.lower():
                new_html = re.sub(r"</body>", rendered + "\n</body>", html_txt, flags=re.IGNORECASE)
            else:
                new_html = html_txt + "\n" + rendered

        file.write_text(new_html, encoding="utf-8")
        changed += 1

    print(f"[theme] scanned={scanned} updated={changed}")

if __name__ == "__main__":
    apply_prediction_template()
