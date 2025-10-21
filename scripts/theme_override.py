# scripts/theme_override.py
from __future__ import annotations
import re
from pathlib import Path
from html import escape

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
TPL = ROOT / "templates" / "prediction_v2.html"

# ---------- small helpers ----------

def _read(p: Path) -> str:
    return p.read_text("utf-8", errors="ignore")

def _write(p: Path, s: str) -> None:
    p.write_text(s, encoding="utf-8")

def _first(rx: str, s: str, flags=re.I|re.S) -> str | None:
    m = re.search(rx, s, flags)
    return m.group(1).strip() if m else None

def _extract_last7(html: str) -> list[tuple[str,str,str,str]]:
    """
    Very tolerant extraction of the 7-day table from current page.
    Returns list of (date, ai_pred, actual, resultText) where resultText is 'Win'/'Loss'/''.
    """
    rows = []
    # Try to locate the "Last 7-Day" table rows by TRs containing four TDs
    for m in re.finditer(r"<tr[^>]*>\s*(<td.*?</td>)\s*(<td.*?</td>)\s*(<td.*?</td>)\s*(<td.*?</td>)\s*</tr>", html, re.I|re.S):
        tds = [re.sub(r"<.*?>", "", x, flags=re.S).strip() for x in m.groups()]
        if len(tds) == 4:
            date, ai, actual, result = tds
            # Heuristic: date like 2025-10-14
            if re.match(r"\d{4}-\d{2}-\d{2}", date):
                rows.append((date, ai, actual, result))
    return rows[:7]

def _rows_html(rows: list[tuple[str,str,str,str]]) -> str:
    out = []
    for d, ai, act, result in rows:
        cls = "result-win" if result.lower().startswith("win") else ("result-loss" if result.lower().startswith("loss") else "")
        badge = f'<span class="{cls}">{escape(result)}</span>' if cls else escape(result)
        out.append(
            "<tr>"
            f"<td>{escape(d)}</td>"
            f"<td>{escape(ai)}</td>"
            f"<td>{escape(act)}</td>"
            f"<td>{badge}</td>"
            "</tr>"
        )
    return "\n".join(out) if out else '<tr><td colspan="4" style="color:#94a3b8">Not enough history.</td></tr>'

def _signal_class(sig: str) -> str:
    s = (sig or "").strip().lower()
    if s.startswith("bear"): return "signal signal--bear"
    return "signal signal--bull"

# ---------- main renderer ----------

def render_prediction_v2(orig_html: str) -> str | None:
    """Build the new page HTML. Returns None if we couldn't parse enough."""
    # Company + symbol from H1 title line:  "AI Analysis of NAME Tomorrow | NAME Stock Prediction"
    company = _first(r"AI Analysis of\s+(.*?)\s+Tomorrow", orig_html) or _first(r"<h1[^>]*>(.*?)</h1>", orig_html)
    if not company:
        return None

    symbol = _first(r"Exchange:\s*([A-Z]+)\s*</span>.*?>([A-Z0-9\.-]+)<", orig_html)  # sometimes there is symbol near exchange
    # Try simpler: it often appears in the page slug (we don't have it here), so symbol stays None gracefully

    # Region/Country/Exchange line
    region  = _first(r"Region:\s*([^·<]+)", orig_html) or ""
    country = _first(r"Country:\s*([^·<]+)", orig_html) or ""
    exchg   = _first(r"Exchange:\s*([^·<]+)", orig_html) or _first(r"Exchange:\s*([A-Z]+)", orig_html) or ""

    # Last build
    last_build = _first(r"Last build:\s*([0-9T:\-]+Z?)", orig_html) or ""

    # Prediction date & signal
    pred_date = _first(r"Prediction for\s*([0-9\-]+)", orig_html) or ""
    signal    = _first(r"Model signal[^<]*based.*?</div>", orig_html)  # not present textually -> fallback
    # On your page the main "signal" is not explicit text; we infer from change% sign if missing
    change_pct = _first(r"Change%:\s*([+\-]?\d+(?:\.\d+)?%)", orig_html) or ""
    if not signal:
        try:
            val = float(change_pct.replace("%",""))
            signal = "Bullish" if val >= 0 else "Bearish"
        except Exception:
            signal = "Bullish"

    # OHLC
    o = _first(r"OHLC:\s*O\s*([0-9\.,]+)", orig_html) or ""
    h = _first(r"OHLC:[^H]*H\s*([0-9\.,]+)", orig_html) or ""
    l = _first(r"OHLC:[^L]*L\s*([0-9\.,]+)", orig_html) or ""
    c = _first(r"OHLC:[^C]*C\s*([0-9\.,]+)", orig_html) or ""

    # 7-day accuracy headline
    acc_pct = _first(r"Last 7-Day Accuracy:\s*([0-9\.]+%.*?\))", orig_html) or ""
    acc_note = f"Last 7-Day Accuracy: {acc_pct}" if acc_pct else "Last 7-Day Accuracy unavailable"

    # Extract last 7 rows
    rows = _extract_last7(orig_html)
    rows_html = _rows_html(rows)

    # Long text placeholders
    methodology = ("We analyze price & volume factors (momentum, RSI, MACD, etc.) "
                   "and key support/resistance levels via our deep learning model.")
    disclaimer = ("This is <b>not</b> financial advice. For informational purposes only. "
                  "Trading carries inherent risk.")
    long_text = (f"{company} appears in a sector monitored by our model; the analysis leverages "
                 "the latest close data to assess the next-day directional probability.")

    tpl = _read(TPL)
    html = tpl.format(
        page_title=f"{company} — Next-day AI Signal",
        company_name=escape(company),
        symbol=escape(symbol or ""),
        region=escape(region), country=escape(country), exchange=escape(exchg),
        last_build=escape(last_build),
        pred_date=escape(pred_date),
        signal_upper=escape(signal.upper()),
        signal_class=_signal_class(signal),
        ohlc_open=escape(o), ohlc_high=escape(h), ohlc_low=escape(l), ohlc_close=escape(c),
        change_pct=escape(change_pct),
        accuracy_pct=escape(acc_pct or "—"),
        accuracy_note=escape(acc_note),
        methodology=methodology,
        disclaimer=disclaimer,
        last7_rows=rows_html,
        long_text=long_text
    )
    return html

def apply_prediction_template():
    if not DIST.exists() or not TPL.exists():
        print("[v2-ui] dist or template missing; skipping.")
        return
    targets = list(DIST.glob("**/prediction-tomorrow/index.html"))
    if not targets:
        print("[v2-ui] No prediction-tomorrow pages found; nothing to do.")
        return

    changed = 0
    for idx_html in targets:
        try:
            orig = _read(idx_html)
            new_html = render_prediction_v2(orig)
            if not new_html:
                continue
            # backup original once
            bkp = idx_html.with_suffix(".legacy.html")
            if not bkp.exists():
                _write(bkp, orig)
            _write(idx_html, new_html)
            changed += 1
        except Exception as e:
            print(f"[v2-ui] Failed {idx_html}: {e}")
    print(f"[v2-ui] Re-skinned {changed} prediction pages.")
