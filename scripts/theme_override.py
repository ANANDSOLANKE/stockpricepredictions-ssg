# scripts/theme_override.py
# Injects: (1) meta strip below company header with Date + O/H/L/C + %,
# (2) modernized banner line: "AI Prediction: {Company} for {Date}" with ▲/▼ and green/red.
# Safe and idempotent: leaves a marker so we don't double-apply.

import os
import re
import datetime

DIST_ROOT = "dist"
PRED_DIR = "prediction-tomorrow"

STAMP = f"<!-- v2-theme applied {datetime.datetime.utcnow().isoformat()}Z -->"

CSS = r"""
/* --- v2 theme (meta strip + banner) --- */
.spp-meta-wrap{margin-top:6px;margin-bottom:10px}
.spp-meta{
  display:inline-flex; gap:10px; flex-wrap:wrap;
  font-size:13px; line-height:1.3;
  background:rgba(255,255,255,0.06);
  padding:8px 12px; border-radius:10px;
  border:1px solid rgba(255,255,255,0.08);
}
.spp-meta strong{opacity:.95}
.spp-meta .dim{opacity:.75}

.spp-banner{
  margin:18px 0 22px 0; border-radius:14px; padding:22px 22px 18px 22px;
  color:#fff; position:relative; overflow:hidden;
  box-shadow:0 10px 30px rgba(0,0,0,.18);
}
.spp-banner--bull{ background:linear-gradient(180deg,#0FA968 0%,#0b8d58 100%); }
.spp-banner--bear{ background:linear-gradient(180deg,#E74C3C 0%,#c83f31 100%); }

.spp-banner .line{display:flex; align-items:center; gap:12px; flex-wrap:wrap}
.spp-banner .badge{
  display:inline-flex; align-items:center; gap:8px;
  font-size:28px; font-weight:800; letter-spacing:.01em
}
.spp-banner .title{ font-size:18px; opacity:.95; font-weight:700; letter-spacing:.02em }
.spp-banner .arrow{ font-size:28px; line-height:1 }
.spp-banner .pill{
  padding:4px 10px; border-radius:999px; background:rgba(255,255,255,.12);
  font-weight:700; font-size:12px; letter-spacing:.04em
}
"""

# ---------- helpers to read values already on the page ----------

def _strip_html(txt: str) -> str:
    return re.sub(r"<[^>]+>", "", txt or "").strip()

def _get_company(html: str) -> str:
    # H1 contains "AI Analysis of XXX Tomorrow | ..."
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, flags=re.I|re.S)
    if not m: return "Stock"
    text = _strip_html(m.group(1))
    n = re.search(r"AI Analysis of (.+?) Tomorrow", text, flags=re.I)
    return n.group(1).strip() if n else text

def _get_prediction_date(html: str) -> str:
    m = re.search(r"Prediction for\s+([0-9]{4}-[0-9]{2}-[0-9]{2})", html, flags=re.I)
    return m.group(1) if m else "—"

def _get_ohlc_and_pct(html: str):
    # OHLC line in your pages: "OHLC: O 19.10, H 19.22, L 18.96, C 19.07 ... Change%: -0.10%"
    o=h=l=c=pct = "—"
    m = re.search(r"OHLC:\s*O\s*([0-9.\-]+).*?H\s*([0-9.\-]+).*?L\s*([0-9.\-]+).*?C\s*([0-9.\-]+)", html, flags=re.I|re.S)
    if m:
        o,h,l,c = m.group(1), m.group(2), m.group(3), m.group(4)
    k = re.search(r"Change%[:\s]*([+\-]?[0-9.]+%)", html, flags=re.I)
    if k: pct = k.group(1)
    return o,h,l,c,pct

def _infer_signal(html: str) -> str:
    # Try first row in 7-day table's AI Prediction column
    m = re.search(r"<table[^>]*>.*?<thead.*?</thead>.*?<tbody[^>]*>(.*?)</tbody>", html, flags=re.I|re.S)
    if m:
        body = m.group(1)
        r = re.search(r"<tr[^>]*>.*?<td[^>]*>.*?</td>.*?<td[^>]*>(Bullish|Bearish)</td>", body, flags=re.I|re.S)
        if r: return r.group(1).title()
    return "—"

# ---------- injectors ----------

def ensure_css(html: str) -> str:
    if "/* --- v2 theme (meta strip + banner) --- */" in html:
        return html
    style = f"<style>{CSS}</style>"
    if "</head>" in html:
        return re.sub(r"</head>", style + "\n</head>", html, count=1, flags=re.I)
    return style + "\n" + html

def inject_meta_strip(html: str, date: str, o: str, h: str, l: str, c: str, pct: str) -> str:
    # put this right after the H1 block (below the big page title area)
    block = f"""
<div class="spp-meta-wrap">
  <div class="spp-meta">
    <span class="dim">{date}</span>
    <span>•</span>
    <span><strong>O</strong> {o}</span>
    <span><strong>H</strong> {h}</span>
    <span><strong>L</strong> {l}</span>
    <span><strong>C</strong> {c}</span>
    <span>•</span>
    <span><strong>Change%</strong> {pct}</span>
  </div>
</div>
""".strip()

    # Insert after the first H1 close or the header container
    out = re.sub(r"(</h1>)", r"\1\n" + block, html, count=1, flags=re.I)
    if out != html: return out
    # Fallback: before the first h2
    out = re.sub(r"(<h2[^>]*>)", block + r"\1", html, count=1, flags=re.I)
    return out

def inject_banner(html: str, company: str, pdate: str, signal: str) -> str:
    # Build our banner; pick green/red + arrow
    is_bull = (signal.lower() == "bullish")
    banner_cls = "spp-banner spp-banner--bull" if is_bull else "spp-banner spp-banner--bear"
    arrow = "▲" if is_bull else "▼"
    title = f"AI Prediction: {company} for {pdate}"

    banner = f"""
<div class="{banner_cls}">
  <div class="line">
    <span class="badge"><span class="arrow">{arrow}</span> {signal if signal!='—' else ''}</span>
    <span class="pill">NEXT-DAY SIGNAL</span>
  </div>
  <div class="title">{title}</div>
</div>
""".strip()

    # Replace the old small banner block if we can find it,
    # otherwise inject before the "Last 7-Day Performance" section.
    # Try to locate any previous injected block by our classes:
    if "spp-banner" in html:
        html = re.sub(r"<div class=\"spp-banner[^\n]+?</div>\s*", "", html, flags=re.I|re.S)

    anchor = re.search(r"(Last\s*7[ -]Day\s*Performance)", html, flags=re.I)
    if anchor:
        return re.sub(anchor.re, banner + r"\n\1", html, count=1)
    return re.sub(r"(<h2[^>]*>)", banner + r"\1", html, count=1, flags=re.I)

# ---------- main patch ----------

def process(path: str) -> bool:
    try:
        src = open(path, "r", encoding="utf-8").read()
    except Exception:
        return False

    if STAMP in src:
        return False

    company = _get_company(src)
    pdate   = _get_prediction_date(src)
    o,h,l,c,pct = _get_ohlc_and_pct(src)
    signal  = _infer_signal(src)

    html = ensure_css(src)
    html = inject_meta_strip(html, pdate, o, h, l, c, pct)
    html = inject_banner(html, company, pdate, signal)

    # Remove any old OHLC pill that sat inside previous green card (avoids duplicate)
    html = re.sub(r"<div class=\"spp-v2-ohlc\".*?</div>", "", html, flags=re.I|re.S)

    html += "\n" + STAMP
    try:
        open(path, "w", encoding="utf-8").write(html)
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
    print(f"[theme_override] patched={patched}")

if __name__ == "__main__":
    main()
