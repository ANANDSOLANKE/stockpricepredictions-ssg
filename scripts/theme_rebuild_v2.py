# scripts/theme_rebuild_v2.py
# Rebuild the top hero area to match the provided mock:
# - Full company name in a top header
# - Right chip with "Close | %Change"
# - "AI Prediction: {Company} for {Date}" big title
# - Color-coded signal banner (green bull / red bear) with ▲/▼ arrow
# - OHLC pill row exactly like the screenshot

import os, re, datetime
from html import escape

DIST_ROOT = "dist"
PRED_DIR  = "prediction-tomorrow"

MARK = f"<!-- v2 rebuild applied {datetime.datetime.utcnow().isoformat()}Z -->"

CSS = r"""
/* ===== v2 rebuild ===== */
.v2-wrap  { margin: 18px 0 26px 0; }
.v2-hdr   {
  background:#ffffff; border-radius:12px; padding:16px 20px;
  box-shadow: 0 2px 22px rgba(0,0,0,.06);
  display:flex; align-items:center; justify-content:space-between; gap:12px;
}
.v2-name  { font-size:22px; font-weight:800; color:#19212A; letter-spacing:.01em }
.v2-sub   { font-size:11px; opacity:.72; margin-top:4px }
.v2-price {
  min-width: 178px; text-align:right;
  font-weight:800; font-size:22px; color:#146C43;
}
.v2-chg   { display:block; font-size:12px; font-weight:700; margin-top:2px }

.v2-hero {
  border-radius:14px; color:#fff; padding:24px 26px 18px 26px;
  margin-top:12px;
  box-shadow: 0 14px 36px rgba(0,0,0,.08);
}
.v2-hero.bull {
  background: linear-gradient(180deg, #10B981 0%, #0EA76B 100%);
}
.v2-hero.bear {
  background: linear-gradient(180deg, #EF4444 0%, #DC2626 100%);
}
.v2-title { font-size:26px; font-weight:800; letter-spacing:.01em; opacity:.96 }
.v2-kicker{ margin-top:10px; font-size:12px; font-weight:900; letter-spacing:.15em; opacity:.9 }
.v2-signal{
  margin-top:12px; font-size:66px; line-height:1.02; font-weight:900; letter-spacing:.02em;
  text-shadow: 0 1px 0 rgba(0,0,0,.06);
}
.v2-signal .arrow { font-size:.7em; margin-left:.18em; vertical-align:baseline; }

.v2-ohlc {
  margin:16px auto 6px auto;
  display:inline-flex; gap:14px; flex-wrap:wrap;
  font-size:14px; color:#0F172A;
  background:#fff; padding:10px 16px; border-radius:12px;
  box-shadow: inset 0 0 0 1px rgba(0,0,0,.06);
}
.v2-ohlc b{ color:#111827 }
.v2-note { margin-top:6px; font-size:12px; opacity:.9 }
"""

TEMPLATE = """{mark}
<div class="v2-wrap">
  <div class="v2-hdr">
    <div>
      <div class="v2-name">{company}</div>
      <div class="v2-sub">{ex_line}</div>
    </div>
    <div class="v2-price" style="color:{price_color}">
      {close}
      <span class="v2-chg" style="color:{chg_color}">{chg}</span>
    </div>
  </div>

  <div class="v2-hero {colour}">
    <div class="v2-title">AI Prediction: {company} for {pdate}</div>
    <div class="v2-kicker">NEXT-DAY SIGNAL</div>
    <div class="v2-signal">{signal} <span class="arrow">{arrow}</span></div>

    <div class="v2-ohlc">
      <span><b>OHLC:</b></span>
      <span>O {o}</span>
      <span>|</span>
      <span>H {h}</span>
      <span>|</span>
      <span>L {l}</span>
      <span>|</span>
      <span>C {c}</span>
    </div>
    <div class="v2-note">Based on yesterday’s OHLC data and our proprietary model.</div>
  </div>
</div>
"""

def inject_css(doc:str)->str:
    if "/* ===== v2 rebuild ===== */" in doc: return doc
    block = f"<style>{CSS}</style>"
    return re.sub(r"</head>", block+"\n</head>", doc, count=1, flags=re.IGNORECASE) if "</head>" in doc else block+"\n"+doc

def extract_h1_company(doc:str)->str:
    m = re.search(r"<h1[^>]*>(.*?)</h1>", doc, flags=re.I|re.S)
    if not m: return "Stock Prediction"
    plain = re.sub(r"<[^>]+>","",m.group(1)).strip()
    n = re.search(r"AI Analysis of (.+?) Tomorrow", plain, flags=re.I)
    return (n.group(1) if n else plain).strip()

def extract_prediction_date(doc:str)->str:
    m = re.search(r"Prediction for\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", doc, flags=re.I)
    return m.group(1) if m else "—"

def extract_ohlc_and_change(doc:str):
    # OHLC: O 19.10, H 19.22, L 18.96, C 19.07 · Change%: -0.10%
    o=h=l=c="—"
    chg="—"
    mm = re.search(r"OHLC:\s*O\s*([0-9.,\-]+).*?H\s*([0-9.,\-]+).*?L\s*([0-9.,\-]+).*?C\s*([0-9.,\-]+)", doc, flags=re.I|re.S)
    if mm: o,h,l,c = mm.group(1),mm.group(2),mm.group(3),mm.group(4)
    mc = re.search(r"Change%[:\s]*([+\-]?[0-9.]+%)", doc, flags=re.I)
    if mc: chg = mc.group(1)
    return o,h,l,c,chg

def extract_exchange_line(doc:str)->str:
    # From the meta block near the top
    # "Region: X · Country: Y · Exchange: Z"
    m = re.search(r"Region:\s*([^<]+?)\s*·\s*Country:\s*([^<]+?)\s*·\s*Exchange:\s*([^<]+)", doc, flags=re.I)
    if not m: return ""
    return f"{m.group(3).strip()} | {m.group(2).strip()}"

def infer_signal(doc:str)->str:
    # First row of last7 table "AI Prediction" column
    m = re.search(r"<tbody[^>]*>(.*?)</tbody>", doc, flags=re.I|re.S)
    if not m: return "—"
    body = m.group(1)
    r = re.search(r"<tr[^>]*>.*?<td[^>]*>.*?</td>.*?<td[^>]*>(Bullish|Bearish)</td>", body, flags=re.I|re.S)
    return r.group(1).title() if r else "—"

def color_for_change(chg:str)->str:
    if chg.startswith("-"): return "#B91C1C"   # red
    if chg.startswith("+"): return "#0E9F6E"   # green
    return "#334155"                           # neutral

def build_block(doc:str)->str:
    company = escape(extract_h1_company(doc))
    pdate   = extract_prediction_date(doc)
    o,h,l,c,chg = extract_ohlc_and_change(doc)
    ex_line = escape(extract_exchange_line(doc))
    signal  = infer_signal(doc)

    # Colour & arrow
    if signal.lower()=="bullish":
        colour, arrow = "bull", "▲"
    elif signal.lower()=="bearish":
        colour, arrow = "bear", "▼"
    else:
        colour, arrow = "bull", "•"  # neutral fallback

    price_color = "#146C43" if not chg.startswith("-") else "#B91C1C"
    chg_color   = color_for_change(chg)

    block = TEMPLATE.format(
        mark=MARK,
        company=company, pdate=pdate,
        ex_line=ex_line,
        close=c if c else "—",
        chg=chg if chg else "—",
        price_color=price_color, chg_color=chg_color,
        colour=colour, signal=signal, arrow=arrow,
        o=o, h=h, l=l, c=c
    )
    return block

def insert_block(doc:str, block:str)->str:
    # Put the whole rebuilt header just under the main "Home" box
    # Find first <section or first H1 and place block right after.
    # 1) after the opening container that holds your top box:
    anchor = re.search(r"(</header>|</nav>|<main[^>]*>)", doc, flags=re.I)
    if anchor:
        pos = anchor.end()
        return doc[:pos] + "\n" + block + "\n" + doc[pos:]
    # 2) else insert before the existing H1
    return re.sub(r"(<h1[^>]*>)", block + r"\1", doc, count=1, flags=re.I)

def strip_previous(doc:str)->str:
    # Make it idempotent
    if MARK in doc: return doc
    return doc

def process(path:str)->bool:
    try:
        html = open(path, "r", encoding="utf-8").read()
    except Exception as e:
        print("read fail:", path, e); return False

    if MARK in html:
        return False

    html2 = inject_css(html)
    block = build_block(html2)
    html2 = insert_block(html2, block)

    try:
        open(path, "w", encoding="utf-8").write(html2)
        print("patched:", path)
        return True
    except Exception as e:
        print("write fail:", path, e); return False

def main():
    patched = 0
    for root,_,files in os.walk(DIST_ROOT):
        if os.path.basename(root) != PRED_DIR: continue
        for fn in files:
            if fn.lower()=="index.html":
                if process(os.path.join(root,fn)): patched += 1
    print(f"[v2-rebuild] patched={patched}")

if __name__=="__main__":
    main()
