# scripts/build_last7.py
# Build/inject "Last 7-Day Performance" blocks into prediction pages.
# - Reads Data/Historical to compute 7 most-recent *target* trading days
# - Deduplicates by target date (newest source wins)
# - Injects HTML into dist/**/prediction-tomorrow/index.html
#
# Assumptions:
#   URL path looks like: dist/<groups or region root>/<region>/<country>/<exchange>/<symbol>/prediction-tomorrow/index.html
#   Historical files live at   Data/Historical/YYYY-MM-DD/<Region>/<country>.csv
#   CSV has at least columns: symbol, Close (case-insensitive OK). Some files also have 'Change%' etc.
#
# Safe to run repeatedly; will replace the existing LAST7 block if found.

from __future__ import annotations
import re
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
import csv

ROOT = Path(__file__).resolve().parents[1]   # repo root
DIST = ROOT / "dist"
DATA = ROOT / "Data" / "Historical"

# ---------- utilities ----------

def _norm(s: str) -> str:
    return (s or "").strip().lower()

def _title_keep_hyphen(s: str) -> str:
    # "asia-pacific" -> "Asia - Pacific" folder name; leave already-titled alone
    if " - " in s:
        return s
    s = s.replace("-", " - ")
    return " ".join([w.capitalize() for w in s.split()])

def next_bday(d: date) -> date:
    nd = d + timedelta(days=1)
    while nd.weekday() >= 5:  # 5=Sat, 6=Sun
        nd += timedelta(days=1)
    return nd

def prev_bday(d: date) -> date:
    pd = d - timedelta(days=1)
    while pd.weekday() >= 5:
        pd -= timedelta(days=1)
    return pd

def list_hist_dates(limit:int=30) -> list[date]:
    # read available YYYY-MM-DD folders (sorted newest->oldest)
    dates = []
    if DATA.exists():
        for p in DATA.iterdir():
            if p.is_dir():
                try:
                    dates.append(datetime.strptime(p.name, "%Y-%m-%d").date())
                except ValueError:
                    pass
    dates.sort(reverse=True)
    return dates[:limit]

def read_country_csv(d: date, region: str, country: str) -> list[dict]:
    # Region folder uses "Asia - Pacific" style; file is lowercase country (e.g., india.csv)
    region_folder = _title_keep_hyphen(region)
    f = DATA / d.strftime("%Y-%m-%d") / region_folder / f"{_norm(country)}.csv"
    if not f.exists():
        return []
    rows = []
    with f.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            # normalize keys to match regardless of case
            nr = {k.strip(): v for k, v in r.items()}
            rows.append(nr)
    return rows

def get_close(rows:list[dict], symbol:str) -> float | None:
    sym = _norm(symbol)
    for r in rows:
        if _norm(r.get("symbol","")) == sym:
            # allow different header cases
            for k in ("Close", "close", "C", "c", "Close "):
                if k in r and str(r[k]).strip() != "":
                    try:
                        return float(str(r[k]).replace(",",""))
                    except ValueError:
                        return None
    return None

def bullish_from_pair(prev_close:float, today_close:float) -> str:
    return "Bullish" if (today_close is not None and prev_close is not None and today_close > prev_close) else "Bearish"

# ---------- build last-7 rows for one symbol ----------

def build_last7_for_symbol(region:str, country:str, exchange:str, symbol:str) -> tuple[list[dict], float]:
    """
    Returns (rows, accuracy)
    rows: list of dicts -> {"date": YYYY-MM-DD target, "pred": Bullish/Bearish, "actual": Bullish/Bearish, "result": Win/Loss, "src_date": YYYY-MM-DD }
    """
    hist_days = list_hist_dates(limit=40)  # plenty to recover 7 unique targets
    if not hist_days:
        return [], 0.0

    rows_accum: list[dict] = []

    # Build a small cache of (date -> df rows) for this country to avoid re-reading
    cache: dict[date, list[dict]] = {}

    def country_rows(d:date) -> list[dict]:
        if d not in cache:
            cache[d] = read_country_csv(d, region, country)
        return cache[d]

    # Iterate newest->older source days; compute target and actual
    for src in hist_days:
        prev_src = prev_bday(src)
        tgt = next_bday(src)

        # We need prev_src close (to compute predicted signal), and tgt close + its prev close for actual
        rows_src_prev = country_rows(prev_src)
        rows_src_tgt  = country_rows(tgt)
        rows_tgt_prev = country_rows(prev_bday(tgt))

        if not rows_src_prev or not rows_tgt_prev or not rows_src_tgt:
            continue

        prev_close = get_close(rows_src_prev, symbol)
        today_close = get_close(country_rows(src), symbol)  # the close that produced the signal

        tgt_close = get_close(rows_src_tgt, symbol)
        tgt_prev_close = get_close(rows_tgt_prev, symbol)

        if prev_close is None or today_close is None or tgt_close is None or tgt_prev_close is None:
            continue

        pred = bullish_from_pair(prev_close, today_close)
        actual = bullish_from_pair(tgt_prev_close, tgt_close)
        result = "Win" if pred == actual else "Loss"

        rows_accum.append({
            "date": tgt.isoformat(),     # target day for the prediction
            "pred": pred,
            "actual": actual,
            "result": result,
            "src_date": src.isoformat()
        })

        # stop early if we already have a lot (we'll dedup next)
        if len(rows_accum) >= 20:
            break

    # --- De-duplicate by target date (keep newest source day) ---
    by_date: dict[str, dict] = {}
    for r in rows_accum:
        k = r["date"]
        if k not in by_date or r["src_date"] > by_date[k]["src_date"]:
            by_date[k] = r

    rows = sorted(by_date.values(), key=lambda x: x["date"], reverse=True)[:7]

    wins = sum(1 for r in rows if r["result"] == "Win")
    acc = round(100.0 * wins / len(rows), 2) if rows else 0.0
    return rows, acc

# ---------- HTML injection ----------

START_MARKS = (
    r"<!--\s*LAST7:START\s*-->",    # your older marker variant (upper)
    r"<!--\s*last7:start\s*-->",    # lower variant
)
END_MARKS = (
    r"<!--\s*LAST7:END\s*-->",
    r"<!--\s*last7:end\s*-->",
)

def render_block(rows:list[dict], acc:float) -> str:
    # Simple, style-neutral. Your CSS already styles .card/.table etc.
    # The colors use classes that are in your stylesheet.
    stat = f"{acc:.2f}% ({sum(1 for r in rows if r['result']=='Win')} / {len(rows) or 1} Wins)"
    def res_cls(r): return "text-green" if r["result"]=="Win" else "text-red"

    # use light utility classes you already have in styles.css
    tb_rows = "\n".join(
        f"""<tr>
<td>{r['date']}</td>
<td>{r['pred']}</td>
<td class="text-right">{r['actual']}</td>
<td class="text-center {'text-success' if r['result']=='Win' else 'text-danger'}"><strong>{r['result']}</strong></td>
</tr>"""
        for r in rows
    )

    return f"""<!-- LAST7:START -->
<div class="card mb-8" id="last7">
  <h2 class="h2">Last 7-Day Performance</h2>
  <div class="mb-3 small">Last 7-Day Accuracy: <strong class="{'text-success' if acc>=50 else 'text-danger'}">{stat}</strong></div>
  <div class="table-wrap">
    <table class="table performance-table">
      <thead>
        <tr>
          <th>Date</th>
          <th>AI Prediction</th>
          <th class="text-right">Actual</th>
          <th class="text-center">Result</th>
        </tr>
      </thead>
      <tbody>
        {tb_rows}
      </tbody>
    </table>
  </div>
</div>
<!-- LAST7:END -->"""

def inject_block(html:str, block:str) -> str:
    # Replace existing block between markers; otherwise append before </body>
    start_pat = "(" + "|".join(START_MARKS) + ")"
    end_pat   = "(" + "|".join(END_MARKS) + ")"

    start_re = re.compile(start_pat, flags=re.IGNORECASE)
    end_re   = re.compile(end_pat,   flags=re.IGNORECASE)

    s = start_re.search(html)
    e = end_re.search(html) if s else None
    if s and e:
        return html[:s.start()] + block + html[e.end():]

    # try single marker pair in any order
    if s:
        # remove from start marker to end of file and append block
        return html[:s.start()] + block + "\n</body>" if "</body>" not in html.lower() else html[:s.start()] + block + html[html.lower().rfind("</body>"):]
    if e:
        head = html[:html.lower().rfind("</body>")] if "</body>" in html.lower() else html
        return head + block + "</body>"

    # No markers: append before </body>
    idx = html.lower().rfind("</body>")
    if idx != -1:
        return html[:idx] + block + html[idx:]
    return html + block

# ---------- Page scanning & wiring ----------

def parse_page_parts(page_path:Path) -> tuple[str,str,str,str] | None:
    """
    From dist/.../<region>/<country>/<exchange>/<symbol>/prediction-tomorrow/index.html
    return (region, country, exchange, symbol) all lower-case for lookup,
    while region is mapped back to folder title via _title_keep_hyphen when needed
    """
    parts = [p for p in page_path.parts]
    # try to find ".../<region>/<country>/<exchange>/<symbol>/prediction-tomorrow/index.html"
    # Find "prediction-tomorrow" in parts and step back 4
    try:
        i = parts.index("prediction-tomorrow")
    except ValueError:
        # sometimes it's a directory named 'prediction-tomorrow' then index.html filename
        try:
            i = parts.index("prediction-tomorrow", 0, len(parts)-1)
        except ValueError:
            return None
    if i < 4:
        return None
    symbol = parts[i-1]
    exchange = parts[i-2]
    country = parts[i-3]
    region = parts[i-4]
    return (region, country, exchange, symbol)

def write_text(p:Path, text:str):
    p.write_text(text, encoding="utf-8", newline="\n")

def main():
    if not DIST.exists():
        print("[skip] no dist directory")
        return

    # Scan pages
    pages = list(DIST.glob("**/prediction-tomorrow/index.html"))
    count_scanned = len(pages)
    count_injected = 0

    for page in pages:
        parsed = parse_page_parts(page.relative_to(DIST))
        if not parsed:
            continue
        region, country, exchange, symbol = parsed
        rows, acc = build_last7_for_symbol(region, country, exchange, symbol)
        if not rows:
            continue

        html = page.read_text(encoding="utf-8", errors="ignore")
        block = render_block(rows, acc)
        new_html = inject_block(html, block)
        if new_html != html:
            write_text(page, new_html)
            count_injected += 1

    print(f"[scan] prediction-tomorrow pages: {count_scanned}")
    print(f"[OK] injected: {count_injected}")

if __name__ == "__main__":
    main()
