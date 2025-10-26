# scripts/theme_override.py
# Inject a modern summary header + colored prediction banner into each
# prediction page in dist/**/prediction-tomorrow/index.html.

import os
import re
import datetime

DIST_ROOT = "dist"
PRED_DIR_NAME = "prediction-tomorrow"

VERSION = "v2.2"
STAMP = f"<!-- spp-theme {VERSION} {datetime.datetime.utcnow().isoformat()}Z -->"

CSS_BLOCK = r"""
/* ===== SPP v2 theme (header + banner) ===== */
.spp-v2-wrap{margin:18px 0 22px}
.spp-v2-header{margin-bottom:10px}
.spp-v2-company{font-size:22px;font-weight:800;letter-spacing:.01em;color:#EAF3FF}
.spp-v2-meta{margin-top:6px;display:flex;flex-wrap:wrap;gap:10px;font-size:13px;opacity:.9;color:#CFE5FF}
.spp-v2-meta .dot{opacity:.5}

/* banner colors */
.spp-v2-card{border-radius:14px;padding:22px 22px 18px 22px;color:#fff;
  box-shadow:0 8px 28px rgba(0,0,0,.15), inset 0 0 0 1px rgba(255,255,255,.06)}
.spp-v2-card.bullish{background:linear-gradient(180deg,#0EA76B 0%,#0A8F5C 100%)}
.spp-v2-card.bearish{background:linear-gradient(180deg,#E65B60 0%,#C13E45 100%)}
.spp-v2-card.neutral{background:linear-gradient(180deg,#586274 0%,#454F61 100%)}

/* banner content */
.spp-v2-banner-title{font-weight:700;letter-spacing:.02em;font-size:16px;opacity:.95}
.spp-v2-signal{font-size:44px;line-height:1.05;font-weight:900;letter-spacing:.01em;margin-top:10px}
"""

CARD_TEMPLATE = """{stamp}
<div class="spp-v2-wrap">
  <div class="spp-v2-header">
    <div class="spp-v2-company">{company}</div>
    <div class="spp-v2-meta">
      <span>Date: {pdate}</span><span class="dot">•</span>
      <span>O {o}</span><span class="dot">•</span>
      <span>H {h}</span><span class="dot">•</span>
      <span>L {l}</span><span class="dot">•</span>
      <span>C {c}</span><span class="dot">•</span>
      <span>Change% {chg}</span>
    </div>
  </div>

  <div class="spp-v2-card {sigcls}">
    <div class="spp-v2-banner-title">AI Prediction: {company} for {pdate}</div>
    <div class="spp-v2-signal">{signal}</div>
  </div>
</div>
"""

# ---------- Utilities ----------

def _read(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"[read] {path}: {e}")
        return None

def _write(path: str, text: str) -> bool:
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return True
    except Exception as e:
        print(f"[write] {path}: {e}")
        return False

def _ensure_css(html: str) -> str:
    if "/* ===== SPP v2 theme (header + banner) ===== */" in html:
        return html
    tag = f"<style>{CSS_BLOCK}</style>"
    # Prefer <head>, otherwise inject at top of document
    if re.search(r"</head>", html, flags=re.I):
        return re.sub(r"</head>", tag + "\n</head>", html, count=1, flags=re.I)
    return tag + "\n" + html

def _strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s)

# ---------- Extractors ----------

def extract_company(html: str) -> str:
    # From H1: "AI Analysis of XYZ Tomorrow | ABC Stock Prediction"
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    if m:
        text = _strip_tags(m.group(1)).strip()
        n = re.search(r"AI Analysis of (.+?) Tomorrow", text, re.I)
        if n:
            return n.group(1).strip()
        return text
    # fallback <title>
    t = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if t:
        return _strip_tags(t.group(1)).strip()
    return "Stock"

def extract_prediction_date(html: str) -> str:
    m = re.search(r"Prediction for\s+(\d{4}-\d{2}-\d{2})", html, re.I)
    if m: return m.group(1)
    # fallback pattern inside top area
    m = re.search(r"for\s+(\d{4}-\d{2}-\d{2})", html, re.I)
    return m.group(1) if m else "—"

def get_ohlc_and_change(html: str):
    o = h = l = c = chg = "—"
    # tolerant OHLC
    mo = re.search(
        r"OHLC:\s*O\s*([0-9.,\-]+).*?H\s*([0-9.,\-]+).*?L\s*([0-9.,\-]+).*?C\s*([0-9.,\-]+)",
        html, re.I | re.S
    )
    if mo:
        o, h, l, c = [g.strip().replace(",", "") for g in mo.groups()]
    # tolerant Change%
    patterns = [
        r"Change%\s*:\s*([+\-]?\s*\d+(?:[.,]\d+)?)\s*%",
        r"Change%\s*[–\-•\.\u00b7]\s*([+\-]?\s*\d+(?:[.,]\d+)?)\s*%",
        r"Change%\s+([+\-]?\s*\d+(?:[.,]\d+)?)\s*%",
        r"OHLC.{0,300}?([+\-]?\s*\d+(?:[.,]\d+)?)\s*%",
    ]
    for patt in patterns:
        k = re.search(patt, html, re.I | re.S)
        if k:
            chg = k.group(1).replace(" ", "").replace(",", ".") + "%"
            break
    return o, h, l, c, chg

def derive_signal(html: str) -> str:
    # Try table first-row "AI Prediction" cell
    m = re.search(r"<tbody[^>]*>(.*?)</tbody>", html, re.I | re.S)
    if m:
        body = m.group(1)
        r = re.search(r"<tr[^>]*>.*?<td[^>]*>.*?</td>.*?<td[^>]*>(Bullish|Bearish)</td>",
                      body, re.I | re.S)
        if r:
            return r.group(1).title()
    # fallback: look for a big word near top
    r = re.search(r"\b(Bullish|Bearish)\b", html, re.I)
    if r:
        return r.group(1).title()
    return "—"

# ---------- Injection ----------

def build_card(company, pdate, o, h, l, c, chg, signal) -> str:
    s = (signal or "").lower()
    sigcls = "bullish" if s == "bullish" else "bearish" if s == "bearish" else "neutral"
    return CARD_TEMPLATE.format(
        stamp=STAMP, company=company, pdate=pdate,
        o=o, h=h, l=l, c=c, chg=chg,
        signal=signal, sigcls=sigcls,
    )

def inject_card(html: str) -> str:
    # Skip if already injected
    if f"spp-theme {VERSION}" in html:
        return html

    company = extract_company(html)
    pdate   = extract_prediction_date(html)
    o, h, l, c, chg = get_ohlc_and_change(html)
    signal  = derive_signal(html)

    card = build_card(company, pdate, o, h, l, c, chg, signal)

    # Prefer to insert BEFORE “Last 7-Day Performance”
    target = re.search(r"(Last\s*7[–\-]?\s*Day\s*Performance)", html, re.I)
    if target:
        return re.sub(target.re, card + r" \1", html, count=1)

    # Else after first H2, else after first H1
    if re.search(r"<h2[^>]*>", html, re.I):
        return re.sub(r"(<h2[^>]*>)", r"\1" + card, html, count=1, flags=re.I)
    if re.search(r"</h1>", html, re.I):
        return re.sub(r"(</h1>)", r"\1" + card, html, count=1, flags=re.I)

    # Fallback: prepend to body
    return card + html

# ---------- Main ----------

def process_file(path: str) -> bool:
    html = _read(path)
    if html is None:
        return False
    new_html = _ensure_css(html)
    new_html = inject_card(new_html)
    if new_html != html:
        if _write(path, new_html):
            print(f"[patched] {path}")
            return True
    return False

def main():
    patched = 0
    for root, _, files in os.walk(DIST_ROOT):
        if os.path.basename(root) != PRED_DIR_NAME:
            continue
        for fn in files:
            if fn.lower() == "index.html":
                if process_file(os.path.join(root, fn)):
                    patched += 1
    print(f"[theme_override] {VERSION} patched={patched}")

if __name__ == "__main__":
    main()
