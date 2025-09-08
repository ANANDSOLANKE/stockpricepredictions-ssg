#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, re, json, shutil, datetime
from pathlib import Path
import pandas as pd

# ---------- Paths & Config ----------
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "Data"
DIST = ROOT / "dist"

CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
BASE_URL = CFG.get("base_url", "").rstrip("/")  # e.g. https://anandsolanke.github.io/stockpricepredictions-ssg

# ---------- Helpers ----------
def find_latest_date_folder():
    """Find latest Data/DD.MM.YYYY folder."""
    if not DATA_DIR.exists():
        raise SystemExit("Missing Data/ directory at repo root.")
    candidates = []
    for p in DATA_DIR.iterdir():
        if p.is_dir() and re.match(r"^\d{2}\.\d{2}\.\d{4}$", p.name):
            d = datetime.datetime.strptime(p.name, "%d.%m.%Y").date()
            candidates.append((d, p))
    if not candidates:
        raise SystemExit("No dated folder like DD.MM.YYYY inside Data/.")
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1], candidates[0][0]

def next_business_day(d: datetime.date):
    wd = d.weekday()
    if wd == 4:  # Fri
        return d + datetime.timedelta(days=3)
    if wd == 5:  # Sat
        return d + datetime.timedelta(days=2)
    return d + datetime.timedelta(days=1)

def classify(o,h,l,c):
    """Simple candle heuristic → (signal, confidence, reason)."""
    rng = max(h,l) - min(h,l)
    body = abs(c-o)
    if rng <= 0: return "Sideways", 0.5, "No range"
    ratio = body/rng
    if ratio < 0.2: return "Sideways", 0.5, "Small body vs range — indecision"
    if c > o: return "Bullish", min(0.9, 0.6 + ratio/2), "Close above open"
    if c < o: return "Bearish", min(0.9, 0.6 + ratio/2), "Close below open"
    return "Sideways", 0.5, "Flat"

def read_csv_safe(p: Path):
    df = pd.read_csv(p, low_memory=False)
    cols = {c: c.strip().lower() for c in df.columns}
    df = df.rename(columns=cols)
    for c in ["symbol","description","exchange","sector","industry","open","high","low","close"]:
        if c not in df.columns:
            df[c] = "" if c not in ["open","high","low","close"] else None
    return df

def slug(s: str):
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "stock"

def write_html(path: Path, html: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")

def tpl_base(title, description, body, canonical):
    """Minimal HTML template (no Jinja)."""
    meta_kw = ", ".join(CFG.get("keywords", []))
    author = CFG.get("author", {})
    site_title = CFG.get("site_title", "")
    site_tagline = CFG.get("site_tagline", "")
    build_time = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    css = f"{BASE_URL}/static/styles.css"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<link rel="canonical" href="{canonical}">
<meta name="description" content="{description}">
<meta name="keywords" content="{meta_kw}">
<meta name="author" content="{author.get('name','')}">
<link rel="stylesheet" href="{css}">
</head>
<body>
<div class="container">
<header class="hero card">
  <div class="breadcrumbs"><a href="{BASE_URL}/index.html">Home</a></div>
  <h1 class="h1">{title}</h1>
  <p class="small">{site_tagline}</p>
  <div class="kv">
    <div><strong>Purpose:</strong> Transparent, reproducible SSG for daily stock pages.</div>
    <div><strong>Last build:</strong> {build_time}</div>
  </div>
</header>
<main class="grid">
{body}
</main>
<footer class="footer">
  <div>E-E-A-T: Author <strong>{author.get('name','')}</strong> · Org: {author.get('org','')} · Contact: <a href="mailto:{author.get('contact_email','')}">{author.get('contact_email','')}</a></div>
  <div>Data provenance: Uploaded CSVs (OHLC). Session date = exchange local date. Prediction = next business day (holidays not applied).</div>
</footer>
</div>
</body>
</html>"""

# ---------- Build ----------
def main():
    date_dir, date_obj = find_latest_date_folder()

    # reset dist
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "static").mkdir(parents=True, exist_ok=True)

    # copy CSS (fallback if missing)
    css_src = ROOT / "static" / "styles.css"
    if css_src.exists():
        shutil.copy2(css_src, DIST / "static" / "styles.css")
    else:
        (DIST / "static" / "styles.css").write_text(
            "body{font-family:system-ui;background:#0b1220;color:#e8f0fe;margin:0}"
            " .container{max-width:1100px;margin:0 auto;padding:24px}"
            " .card{background:#111a2b;border-radius:16px;padding:16px}"
            " .h1{font-size:28px} .h2{font-size:22px} .h3{font-size:18px}"
            " .grid{display:grid;gap:16px}"
            " .table{width:100%;border-collapse:collapse}"
            " .table td,.table th{border-bottom:1px solid #1f2a44;padding:8px}"
            " .small{color:#9fb3c8}",
            encoding="utf-8"
        )

    # Home: list regions discovered
    regions = [p for p in date_dir.iterdir() if p.is_dir()]
    regions.sort(key=lambda x: x.name.lower())

    home_body = ["<section class='card'><h2 class='h2'>Browse Regions</h2><ul>"]
    for r in regions:
        r_slug = slug(r.name)
        home_body.append(f"<li><a href='{BASE_URL}/{r_slug}/index.html'>{r.name}</a></li>")
    home_body.append("</ul></section>")
    write_html(
        DIST / "index.html",
        tpl_base(
            f"{CFG.get('site_title','')} — {CFG.get('site_tagline','')}",
            "Daily static stock prediction pages built from your uploaded CSVs.",
            "\n".join(home_body),
            f"{BASE_URL}/"
        )
    )

    # Region → Countries → Stocks
    for region in regions:
        r_slug = slug(region.name)

        # Collect countries (CSV files directly under region folder)
        country_links = []
        for csv in sorted([p for p in region.glob("*.csv")], key=lambda x: x.name.lower()):
            country_name = csv.stem.replace("-", " ").title()
            c_slug = slug(country_name)
            country_links.append((country_name, c_slug))

            df = read_csv_safe(csv)
            rows_html = []

            for _, row in df.iterrows():
                # read row values
                try:
                    o = float(row["open"]); h = float(row["high"]); l = float(row["low"]); c = float(row["close"])
                except Exception:
                    o = h = l = c = None

                sig, conf, reason = ("", 0, "")
                if None not in (o, h, l, c):
                    sig, conf, reason = classify(o, h, l, c)

                sym = str(row["symbol"]).strip()
                name = str(row["description"]).strip() or sym
                exch = str(row["exchange"]).strip()
                sec  = str(row["sector"]).strip()
                ind  = str(row["industry"]).strip()
                s_slug = slug(name or sym)

                # Per-stock page (only if we have OHLC)
                if None not in (o, h, l, c):
                    pred = next_business_day(date_obj)
                    body = f"""
<article class="card">
  <h2 class="h2">{name} ({sym})</h2>
  <p class="small">Region: {region.name} · Country: {country_name} · Exchange: {exch}</p>
  <p class="small">Session Date: {date_obj.isoformat()} · OHLC: O {o}, H {h}, L {l}, C {c}</p>
  <div class="card">
    <h3 class="h3">Prediction for {pred.isoformat()}</h3>
    <p><strong>{sig}</strong> — {reason} (confidence {int(conf*100)}%).</p>
  </div>
</article>"""
                    write_html(
                        DIST / r_slug / c_slug / s_slug / "index.html",
                        tpl_base(
                            f"{name} prediction tomorrow — {CFG.get('site_title','')}",
                            f"{name} ({sym}) next-day prediction and OHLC snapshot.",
                            body,
                            f"{BASE_URL}/{r_slug}/{c_slug}/{s_slug}/"
                        )
                    )

                # Row in country table (links must use BASE_URL)
                rows_html.append(
                    (
                        f"<tr>"
                        f"<td><a href='{BASE_URL}/{r_slug}/{c_slug}/{s_slug}/index.html'>{sym}</a></td>"
                        f"<td><a href='{BASE_URL}/{r_slug}/{c_slug}/{s_slug}/index.html'>{name}</a></td>"
                        f"<td>{exch}</td><td>{sec}</td><td>{ind}</td>"
                        f"<td>{'' if c is None else f'{c:.2f}'}</td><td>{sig}</td>"
                        f"</tr>"
                    )
                )

            # Country index page
            table = (
                "<table class='table'>"
                "<thead><tr><th>Symbol</th><th>Name</th><th>Exchange</th><th>Sector</th>"
                "<th>Industry</th><th>Close</th><th>Signal</th></tr></thead>"
                "<tbody>" + "\n".join(rows_html) + "</tbody></table>"
            )
            body = f"<section class='card'><h2 class='h2'>{country_name} — Stocks</h2>{table}</section>"
            write_html(
                DIST / r_slug / c_slug / "index.html",
                tpl_base(
                    f"{country_name} stocks — {CFG.get('site_title','')}",
                    f"Browse stocks listed in {country_name}.",
                    body,
                    f"{BASE_URL}/{r_slug}/{c_slug}/"
                )
            )

        # Region index page (links must use BASE_URL)
        lis = "".join(
            [f"<li><a href='{BASE_URL}/{r_slug}/{c_slug}/index.html'>{cn}</a></li>"
             for (cn, c_slug) in country_links]
        )
        body = f"<section class='card'><h2 class='h2'>Countries in {region.name}</h2><ul>{lis}</ul></section>"
        write_html(
            DIST / r_slug / "index.html",
            tpl_base(
                f"{region.name} Markets — {CFG.get('site_title','')}",
                f"Browse stock markets in {region.name}.",
                body,
                f"{BASE_URL}/{r_slug}/"
            )
        )

    # robots.txt + sitemap.xml
    (DIST / "robots.txt").write_text(
        f"Sitemap: {BASE_URL}/sitemap.xml\nUser-agent: *\nAllow: /\n",
        encoding="utf-8"
    )

    urls = []
    for p in DIST.rglob("index.html"):
        rel = "/" + str(p.relative_to(DIST)).replace("\\", "/")
        urls.append(f"{BASE_URL}{rel[:-10]}")  # drop 'index.html'
    sm = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
        + "".join([f"<url><loc>{u}</loc></url>" for u in urls])
        + "</urlset>"
    )
    (DIST / "sitemap.xml").write_text(sm, encoding="utf-8")

    print("Build complete →", DIST)

if __name__ == "__main__":
    main()
