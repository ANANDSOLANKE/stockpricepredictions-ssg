# scripts/theme_override.py
# Inject a green next-day summary card into each prediction page
# Safe: reads values already rendered on the page and inserts one styled block.

import os
import re
import datetime

DIST_ROOT = "dist"
PRED_DIR = "prediction-tomorrow"

MARK = f"<!-- v2-theme card injected {datetime.datetime.utcnow().isoformat()}Z -->"

CSS_BLOCK = r"""
/* v2 theme summary card */
.spp-v2-wrap{margin:18px 0 22px 0}
.spp-v2-card{
  background:linear-gradient(180deg,#0EA76B 0%,#0A8F5C 100%);
  color:#E9FFF5; border-radius:14px; padding:22px 22px 18px 22px;
  box-shadow:0 8px 28px rgba(14,167,107,0.15), inset 0 0 0 1px rgba(255,255,255,0.08)
}
.spp-v2-kv{display:flex;gap:18px;align-items:flex-end;flex-wrap:wrap}
.spp-v2-t{font-weight:700;letter-spacing:.02em}
.spp-v2-title{font-size:18px;opacity:.95}
.spp-v2-date{font-size:14px;opacity:.8}
.spp-v2-signal{font-size:44px;line-height:1.05;font-weight:800;letter-spacing:.01em}
.spp-v2-ohlc{
  margin-top:14px;display:inline-flex;gap:10px;flex-wrap:wrap;
  font-size:13px; background:rgba(255,255,255,0.09); padding:8px 10px; border-radius:10px
}
.spp-v2-pill{padding:4px 8px;border-radius:999px;background:#063F2E;color:#9FF2CF;font-weight:700;font-size:12px}
.spp-v2-note{margin-top:8px;font-size:12px;opacity:.8}
"""

CARD_TEMPLATE = """{mark}
<div class="spp-v2-wrap">
  <div class="spp-v2-card">
    <div class="spp-v2-kv">
      <div class="spp-v2-t spp-v2-title">{company}</div>
      <div class="spp-v2-t spp-v2-date">{pdate}</div>
      <span class="spp-v2-pill">NEXT-DAY SIGNAL</span>
    </div>
    <div class="spp-v2-signal">{signal}</div>
    <div class="spp-v2-ohlc">
      <span>OHLC:</span>
      <span>O {o}</span>
      <span>H {h}</span>
      <span>L {l}</span>
      <span>C {c}</span>
      <span>• Change%: {chg}</span>
    </div>
    <div class="spp-v2-note">Based on yesterday’s OHLC and our day-action model.</div>
  </div>
</div>
"""

def _ensure_css(html: str) -> str:
    if "/* v2 theme summary card */" in html:
        return html
    # inject before </head> if possible, else at top
    style_tag = f"<style>{CSS_BLOCK}</style>"
    if "</head>" in html:
        return re.sub(r"</head>", style_tag + "\n</head>", html, count=1, flags=re.IGNORECASE)
    return style_tag + "\n" + html

def _extract_company(html: str) -> str:
    # From the big H1: "AI Analysis of XXX Tomorrow | ABC Stock Prediction"
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.IGNORECASE|re.DOTALL)
    if m:
        # Pull the part after the first "of " and before " Tomorrow"
        text = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        n = re.search(r"AI Analysis of (.+?) Tomorrow", text, flags=re.IGNORECASE)
        if n:
            return n.group(1).strip()
        return text
    return "Stock Prediction"

def _extract_prediction_date(html: str) -> str:
    m = re.search(r"Prediction for\s+([0-9]{4}-[0-9]{2}-[0-9]{2})", html, flags=re.IGNORECASE)
    return m.group(1) if m else "—"

def _extract_ohlc(html: str):
    # Example line: OHLC: O 19.10, H 19.22, L 18.96, C 19.07 · Change%: -0.10%
    o=h=l=c=chg="—"
    m = re.search(r"OHLC:\s*O\s*([0-9.\-]+).*?H\s*([0-9.\-]+).*?L\s*([0-9.\-]+).*?C\s*([0-9.\-]+)", html, flags=re.IGNORECASE|re.DOTALL)
    if m:
        o,h,l,c = m.group(1), m.group(2), m.group(3), m.group(4)
    k = re.search(r"Change%:\s*([+\-]?[0-9.]+%)", html, flags=re.IGNORECASE)
    if not k:
        # also render previous pattern with dot mid
        k = re.search(r"Change%[:\s]*([+\-]?[0-9.]+%)", html, flags=re.IGNORECASE)
    if k:
        chg = k.group(1)
    return o,h,l,c,chg

def _derive_signal(html: str) -> str:
    # Lean on your existing wording: "Model signal based on..." followed by prior day's action.
    # We'll infer signal as text already on page if present, else default "—".
    # Many of your pages don't explicitly print "Bullish/Bearish" at the top,
    # so we keep the card neutral if we can't infer.
    # We do this: try to read first row of the 7-day table "AI Prediction" cell text.
    m = re.search(r"<table[^>]*>.*?<thead.*?</thead>.*?<tbody[^>]*>(.*?)</tbody>", html, flags=re.IGNORECASE|re.DOTALL)
    if m:
        body = m.group(1)
        r = re.search(r"<tr[^>]*>.*?<td[^>]*>.*?</td>.*?<td[^>]*>(Bullish|Bearish)</td>", body, flags=re.IGNORECASE|re.DOTALL)
        if r:
            return r.group(1).title()
    # fallback: neutral dash
    return "—"

def _inject_card(html: str) -> str:
    company = _extract_company(html)
    pdate   = _extract_prediction_date(html)
    o,h,l,c,chg = _extract_ohlc(html)
    signal  = _derive_signal(html)

    card = CARD_TEMPLATE.format(
        mark=MARK, company=company, pdate=pdate,
        o=o, h=h, l=l, c=c, chg=chg, signal=signal
    )

    # Place card just before "Last 7-Day Performance" block if present,
    # otherwise after the first secondary header.
    target = re.search(r"(Last\s*7[--]Day\s*Performance)", html, flags=re.IGNORECASE)
    if target:
        return re.sub(target.re, card + r" \1", html, count=1)
    # fallback: inject after first <h2>
    return re.sub(r"(<h2[^>]*>)", r"\1" + card, html, count=1, flags=re.IGNORECASE)

def process(path: str) -> bool:
    try:
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
    except Exception as e:
        print("read fail:", path, e)
        return False

    if MARK in html:
        return False

    html = _ensure_css(html)
    html = _inject_card(html)

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        print("patched:", path)
        return True
    except Exception as e:
        print("write fail:", path, e)
        return False

def main():
    patched = 0
    for root, _, files in os.walk(DIST_ROOT):
        if os.path.basename(root) != PRED_DIR:
            continue
        for fn in files:
            if fn.lower() == "index.html":
                if process(os.path.join(root, fn)):
                    patched += 1
    print(f"theme_override: patched={patched}")

if __name__ == "__main__":
    main()
