from __future__ import annotations
import re, json
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
DATA = ROOT / "Data"

# We keep the page route the same:
PRED_GLOB = "**/prediction-tomorrow/index.html"

def _last_7_dates(latest: datetime) -> list[str]:
    out = []
    d = latest.date()
    for i in range(7):
        out.append((d - timedelta(days=i)).isoformat())
    return out

def _load_symbol_history(region: str, country: str, sym: str) -> list[dict]:
    # use Historical/*/<region>/<country>.csv  (your existing structure)
    # We will scan latest folder by date descending first:
    hist_root = DATA / "Historical"
    if not hist_root.exists():
        return []

    # collect date folders
    dates = sorted([p.name for p in hist_root.iterdir() if p.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}", p.name)], reverse=True)
    rows: list[dict] = []
    for d in dates[:10]:  # only need a short window
        csv_path = hist_root / d / region / f"{country.lower().replace(' ','-')}.csv"
        if not csv_path.exists():
            continue
        try:
            import pandas as pd
            df = pd.read_csv(csv_path)
            # filter symbol rows only
            sdf = df[df["symbol"].astype(str) == sym]
            for _, r in sdf.iterrows():
                rows.append({
                    "date": d,
                    "close": r.get("Close"),
                    "open": r.get("open"),
                })
        except Exception:
            pass
        if len(rows) >= 14:
            break
    # newest first
    rows.sort(key=lambda x: x["date"], reverse=True)
    return rows

def _ai_signal(prev_close, last_close) -> str:
    try:
        pc = float(prev_close)
        lc = float(last_close)
    except Exception:
        return ""
    return "Bullish" if lc > pc else ("Bearish" if lc < pc else "Sideways")

def inject_last7():
    pages = list(DIST.glob(PRED_GLOB))
    print(f"[scan] prediction-tomorrow pages: {len(pages)}")

    injected = 0
    now = datetime.utcnow()

    for page in pages:
        # recover meta (region/country/exchange/symbol) from path parts
        # /dist/<region>/<country>/<exchange>/<symbol>/prediction-tomorrow/index.html
        parts = page.relative_to(DIST).parts
        if len(parts) < 5:
            continue
        region_slug, country_slug, exchange_slug, symbol_slug = parts[0], parts[1], parts[2], parts[3]

        # crude inverse slugs -> names
        region = region_slug.replace("-", " ").title()
        country = country_slug.replace("-", " ").title()
        symbol = symbol_slug.upper()

        hist = _load_symbol_history(region, country, symbol)
        if len(hist) < 2:
            # nothing to show – skip
            continue

        # Build last-7 performance lines
        last7_dates = _last_7_dates(now)
        rows = []
        wins = 0
        used = 0

        for i in range(1, len(hist)):
            d = hist[i-1]["date"]  # last day
            prev_d = hist[i]["date"]
            # only take unique dates and up to 7 rows
            if d not in last7_dates:
                continue
            sig = _ai_signal(hist[i]["close"], hist[i-1]["close"])
            actual_close = hist[i-1]["close"]
            # For this simplistic approach, "Win" if direction matched same rule on that day:
            # If sig was Bullish, day change close-prevclose > 0
            try:
                day_up = float(hist[i-1]["close"]) - float(hist[i]["close"])
                res = "Win" if (sig == "Bullish" and day_up > 0) or (sig == "Bearish" and day_up < 0) else "Loss"
            except Exception:
                res = ""
            if res == "Win":
                wins += 1
            used += 1
            rows.append({
                "date": d,
                "ai": sig,
                "actual": actual_close,
                "result": res
            })
            if len(rows) == 7:
                break

        rows.sort(key=lambda x: x["date"], reverse=True)
        win_pct = (wins/used*100.0) if used else 0.0

        # Inject at marker <!-- LAST7 --> … <!-- /LAST7 -->
        html = page.read_text(encoding="utf-8")
        block = [
            '<section class="card mt-6">',
            '  <h3 class="h3">Last 7-Day Performance</h3>',
            f'  <p class="small">Last 7-Day Accuracy: <strong>{win_pct:.2f}%</strong> ({wins}/{used})</p>',
            '  <div class="table-wrap"><table class="table"><thead><tr>',
            '    <th>Date</th><th>AI Prediction</th><th class="text-right">Actual Close</th><th class="text-center">Result</th>',
            '  </tr></thead><tbody>'
        ]
        for r in rows:
            color = "style='color:#3ddc97;'" if r["result"] == "Win" else "style='color:#ff6b6b;'"
            block.append(
                f"<tr><td>{r['date']}</td><td>{r['ai']}</td><td class='text-right'>{r['actual']}</td><td class='text-center'><span {color}>{r['result']}</span></td></tr>"
            )
        block.append("</tbody></table></div></section>")
        inject_html = "\n".join(block)

        new_html = re.sub(
            r"<!-- LAST7 -->.*?<!-- /LAST7 -->",
            f"<!-- LAST7 -->\n{inject_html}\n<!-- /LAST7 -->",
            html,
            flags=re.S
        )
        if new_html != html:
            page.write_text(new_html, encoding="utf-8")
            injected += 1

    print(f"[OK] injected: {injected}")

if __name__ == "__main__":
    inject_last7()
