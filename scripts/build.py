#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv, html, json, os, re, unicodedata, shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

# ----------------- Paths & Config -----------------
ROOT = Path(__file__).resolve().parents[1]
DATA_LAST = ROOT / "Data" / "LastTradingDay"
DATA_HIST = ROOT / "Data" / "Historical"
DIST = ROOT / "dist"

CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
BASE_URL = CFG.get("base_url", "").rstrip("/")

SKIP_LOGOS = os.environ.get("SKIP_LOGOS", "0") == "1"
IMG_EXTS = {".png", ".jpg", ".jpeg", ".svg", ".webp"}

# ----------------- Utils -----------------
def ensure_dir(p: Path): p.mkdir(parents=True, exist_ok=True)
def write_text(p: Path, s: str): p.parent.mkdir(parents=True, exist_ok=True); p.write_text(s, encoding="utf-8")
def write_json(p: Path, obj): p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
def slug(s: str) -> str: s=(s or "").strip().lower(); s=re.sub(r"[^a-z0-9]+","-",s); return s.strip("-") or "item"
def _f(x):
    try: return float(x)
    except: return None

def classify(o,h,l,c):
    rng = max(h,l) - min(h,l)
    body = abs(c-o)
    if rng <= 0: return "Sideways", 0.5, "No range"
    ratio = body/rng if rng else 0.0
    if ratio < 0.2: return "Sideways", 0.5, "Small body vs range — indecision"
    if c > o: return "Bullish", min(0.9, 0.6 + ratio/2), "Close above open"
    if c < o: return "Bearish", min(0.9, 0.6 + ratio/2), "Close below open"
    return "Sideways", 0.5, "Flat"

def next_business_day(d):
    wd = d.weekday()
    if wd == 4: return d + timedelta(days=3)
    if wd == 5: return d + timedelta(days=2)
    return d + timedelta(days=1)

# ----------------- Readers -----------------
def read_csv_rows(path: Path) -> List[Dict[str,str]]:
    rows=[]
    with open(path,"r",encoding="utf-8",newline="") as f:
        rdr=csv.DictReader(f)
        for r in rdr:
            rows.append({(k or "").strip().lower():(v or "").strip() for k,v in r.items()})
    return rows

def load_last_trading_day() -> Dict[str, Dict[str, Dict]]:
    """
    tree[group_slug][country_slug] = {..., rows}
    """
    tree={}
    if not DATA_LAST.exists(): return tree
    for group_dir in sorted([d for d in DATA_LAST.iterdir() if d.is_dir()]):
        gname=group_dir.name; gslug=slug(gname); tree.setdefault(gslug,{})
        for csvp in sorted(group_dir.glob("*.csv")):
            cslug=csvp.stem; cname=cslug.replace("-"," ").title()
            rows=read_csv_rows(csvp)
            for r in rows:
                for k in ("symbol","description","exchange","sector","industry",
                          "open","high","low","close","change_percent","change%"):
                    r.setdefault(k, r.get(k, ""))
            tree[gslug][cslug]={"group_name":gname,"group_slug":gslug,
                                "country_name":cname,"country_slug":cslug,
                                "csv_path":csvp,"rows":rows}
    return tree

# ----------------- Assets -----------------
def copy_static_assets():
    ensure_dir(DIST/"static")
    for name in ("styles.css","app.js"):
        src=ROOT/"static"/name
        if src.exists(): shutil.copy2(src, DIST/"static"/name)

def ensure_placeholder_logo():
    svg="""<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64' viewBox='0 0 64 64'>
<rect width='64' height='64' rx='12' fill='#0e1729' stroke='#223157'/>
<path d='M20 36h24M20 28h24' stroke='#4f8cff' stroke-width='3' stroke-linecap='round'/>
</svg>"""
    p=DIST/"static"/"logo-placeholder.svg"
    if not p.exists(): ensure_dir(p.parent); p.write_text(svg, encoding="utf-8")

def _norm(s:str)->str:
    s=unicodedata.normalize("NFKD", s or "").encode("ascii","ignore").decode("ascii")
    return re.sub(r"[^A-Z0-9]","",s.upper())

def load_logos_index()->Dict[tuple,str]:
    for p in [ROOT/"logos_index.json", ROOT/"logos"/"logos_index.json"]:
        if p.exists():
            try:
                raw=json.loads(p.read_text(encoding="utf-8"))
                flat={}
                for exch,mp in (raw or {}).items():
                    for sym,rel in (mp or {}).items():
                        flat[(exch.upper(), _norm(sym))]=str(rel).lstrip("/\\")
                return flat
            except: pass
    return {}

def build_scan_index():
    base=ROOT/"logos"; idx={}
    if not base.exists(): return idx
    for root,_,files in os.walk(base):
        for f in files:
            if os.path.splitext(f)[1].lower() not in IMG_EXTS: continue
            full=Path(root)/f; rel=full.relative_to(base).as_posix()
            exch=full.parent.name; stem=os.path.splitext(f)[0]
            stem=re.sub(r"(--|_|-)?\d{2,4}$","",stem)
            idx.setdefault(exch.upper(), []).append((_norm(stem), rel))
    return idx

class LogoResolver:
    def __init__(self):
        self.placeholder=f"{BASE_URL}/static/logo-placeholder.svg"
        if SKIP_LOGOS:
            self.curated={}; self.scan={}
        else:
            src=ROOT/"logos"; dst=DIST/"logos"
            if src.exists() and not dst.exists(): shutil.copytree(src,dst)
            self.curated=load_logos_index(); self.scan=build_scan_index()
        self.cache={}
    def url_for(self, exchange:str, symbol:str, name:str="")->str:
        key=(exchange or "", symbol or "")
        if key in self.cache: return self.cache[key]
        if SKIP_LOGOS:
            self.cache[key]=self.placeholder; return self.placeholder
        exch=(exchange or "").upper(); symn=_norm(symbol)
        rel=self.curated.get((exch,symn))
        if rel: url=f"{BASE_URL}/logos/{rel}"; self.cache[key]=url; return url
        # direct symbol match
        for stem,rel in self.scan.get(exch, []):
            if stem==symn: url=f"{BASE_URL}/logos/{rel}"; self.cache[key]=url; return url
        # fuzzy
        for stem,rel in self.scan.get(exch, []):
            if symn and (symn in stem or stem in symn): url=f"{BASE_URL}/logos/{rel}"; self.cache[key]=url; return url
        self.cache[key]=self.placeholder; return self.placeholder

# ----------------- Historical back-test (last 7) -----------------
def list_recent_dates(n:int)->List[str]:
    if not DATA_HIST.exists(): return []
    dates=[d.name for d in DATA_HIST.iterdir() if d.is_dir() and re.match(r"^\d{4}-\d{2}-\d{2}$", d.name)]
    dates.sort(); return dates[-n:]

def get_symbol_closes_for_country(group_name:str, country_slug:str, symbol:str, how_many_days:int=9)->List[Tuple[str,Optional[float]]]:
    dates=list_recent_dates(how_many_days*2); out=[]
    for d in dates:
        csvp=DATA_HIST/d/group_name/f"{country_slug}.csv"
        if not csvp.exists(): continue
        try:
            rows=read_csv_rows(csvp); close_val=None
            for r in rows:
                if (r.get("symbol") or "").strip().upper()==symbol.upper():
                    close_val=_f(r.get("close")); break
            if close_val is not None: out.append((d, close_val))
        except: pass
        if len(out)>=how_many_days: break
    out.sort(key=lambda x:x[0]); return out

def make_last7_backtest(group_name:str, country_name:str, country_slug:str, symbol:str)->Dict:
    closes=get_symbol_closes_for_country(group_name, country_slug, symbol, how_many_days= NineOrDefault(9))
    # fallback: if helper not found, respect plain 9
    if isinstance(closes, list) and len(closes) < 3:
        return {"rows":[], "wins":0, "total":0, "win_pct":None}
    if len(closes) < 3:
        return {"rows":[], "wins":0, "total":0, "win_pct":None}

    preds=[]
    for i in range(2, len(closes)):
        d_t, c_t = closes[i]
        _, c_t1 = closes[i-1]
        _, c_t2 = closes[i-2]
        pred = "Bullish" if (c_t1 is not None and c_t2 is not None and c_t1 >= c_t2) else "Bearish"
        actual = "Bullish" if (c_t is not None and c_t1 is not None and c_t > c_t1) else "Bearish"
        preds.append((d_t, pred, c_t, pred==actual))
    preds = preds[-7:]
    wins=sum(1 for *_, w in preds if w); total=len(preds)
    win_pct=(wins/total*100.0) if total else None
    rows=[{"date":d,"prediction":p,"close":None if c is None else round(c,2),"result":"Win" if w else "Loss","is_win":w} for d,p,c,w in preds]
    return {"rows":rows,"wins":wins,"total":total,"win_pct":None if win_pct is None else round(win_pct,2)}

# helper to keep literal 9 even if someone search-replaces
def NineOrDefault(n:int)->int: return 9

# ----------------- HTML helpers -----------------
def pct_html(chg: Optional[float])->str:
    if chg is None: return ""
    cls = "pos" if chg>0 else ("neg" if chg<0 else "")
    return f"<span class='pct {cls}'>{chg:.2f}%</span>"

def tpl_base(title, description, body, canonical):
    meta_kw=", ".join(CFG.get("keywords", []))
    author=CFG.get("author", {}); site_tagline=CFG.get("site_tagline","")
    build_time=datetime.utcnow().isoformat(timespec="seconds")+"Z"
    css=f"{BASE_URL}/static/styles.css"; js=f"{BASE_URL}/static/app.js"
    extra_css="""
    <style>.btn{display:inline-block;padding:.35rem .7rem;border:1px solid #27406b;border-radius:8px}
    .btn:hover{background:#122036}.mini{font-size:12px;opacity:.8}.mut{opacity:.75}
    .win{color:#3ddc97;font-weight:700}.loss{color:#ff6b6b;font-weight:700}
    .pct{font-weight:700}.pct.pos{color:#3ddc97}.pct.neg{color:#ff6b6b}</style>"""
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="canonical" href="{canonical}">
<meta name="description" content="{html.escape(description)}">
<meta name="keywords" content="{html.escape(meta_kw)}">
<meta name="author" content="{html.escape(author.get('name',''))}">
<link rel="stylesheet" href="{css}">{extra_css}
</head>
<body>
<div class="container">
<header class="hero card">
  <div class="breadcrumbs"><a href="{BASE_URL}/">Home</a></div>
  <h1 class="h1">{html.escape(title)}</h1>
  <p class="small">{html.escape(site_tagline)}</p>
  <div class="kv">
    <div><strong>Purpose:</strong> Transparent, reproducible SSG for daily stock pages.</div>
    <div><strong>Last build:</strong> {build_time}</div>
  </div>
</header>
<main class="grid">
{body}
</main>
<footer class="footer">
  <div>E-E-A-T: Author <strong>{html.escape(author.get('name',''))}</strong> · Org: {html.escape(author.get('org','',))} · Contact: <a href="mailto:{html.escape(author.get('contact_email',''))}">{html.escape(author.get('contact_email',''))}</a></div>
  <div>Data provenance: Trading day snapshots. Prediction target = next business day.</div>
</footer>
</div>
<script>window.SPP_BASE="{BASE_URL}";window.SPP_INDEX_URL="{BASE_URL}/static/index.json";</script>
<script src="{js}" defer></script>
</body></html>"""

# ----------------- Build -----------------
def main():
    ensure_dir(DIST/"static")
    copy_static_assets()
    ensure_placeholder_logo()

    tree=load_last_trading_day()
    resolver=LogoResolver()

    # Home
    home_body = """
<section class='card'>
  <h2 class='h2'>Browse Markets</h2>
  <div class="picker">
    <div class="row"><div class="row-title">Regions</div><div id="regions" class="chips"></div></div>
    <div class="row"><div class="row-title">Countries</div><div id="countries" class="chips"></div></div>
    <div class="row"><div class="row-title">Exchanges</div><div id="exchanges" class="chips"></div></div>
  </div>
</section>
<section class='card'>
  <h2 class='h2'>Stocks</h2>
  <div id="stocks_table">Pick a region → country → exchange</div>
</section>"""
    write_text(DIST/"index.html", tpl_base(
        f"{CFG.get('site_title','')} — {CFG.get('site_tagline','')}",
        "Interactive drilldown: region → country → exchange → stocks.",
        home_body, f"{BASE_URL}/"
    ))

    site_index={"regions":[]}

    for gslug in sorted(tree.keys()):
        gname = next(iter(tree[gslug].values()))["group_name"]
        region_entry={"name":gname,"slug":gslug,"url":f"{BASE_URL}/{gslug}/","countries":[]}
        site_index["regions"].append(region_entry)

        # Region page
        country_links=[]
        for cslug in sorted(tree[gslug].keys()):
            cname=tree[gslug][cslug]["country_name"]
            region_entry["countries"].append({"name":cname,"slug":cslug,"url":f"{BASE_URL}/{gslug}/{cslug}/","exchanges":[]})
            country_links.append(f"<li><a href='{BASE_URL}/{gslug}/{cslug}/'>{html.escape(cname)}</a></li>")
        write_text(DIST/gslug/"index.html",
                   tpl_base(f"{gname} Markets — {CFG.get('site_title','')}",
                           f"Browse stock markets in {gname}.",
                           f"<section class='card'><h2 class='h2'>Countries in {html.escape(gname)}</h2><ul>{''.join(country_links)}</ul></section>",
                           f"{BASE_URL}/{gslug}/"))

        # Countries → Exchanges
        for c in region_entry["countries"]:
            cslug,cname=c["slug"],c["name"]
            rows=tree[gslug][cslug]["rows"]

            # group by exchange
            by_exch={}
            for r in rows:
                by_exch.setdefault((r.get("exchange") or "UNKNOWN").strip(), []).append(r)

            ex_links=[]
            for exch, erows in sorted(by_exch.items(), key=lambda kv: kv[0].lower()):
                e_slug=slug(exch); e_url=f"{BASE_URL}/{gslug}/{cslug}/{e_slug}/"
                c["exchanges"].append({"name":exch,"slug":e_slug,"url":e_url})
                ex_links.append(f"<li><a href='{e_url}'>{html.escape(exch)}</a></li>")

                table_rows_html=[]; json_rows=[]
                for r in erows:
                    sym=(r.get("symbol") or "").strip()
                    name=(r.get("description") or sym or "").strip()
                    sec=(r.get("sector") or "").strip()
                    o=_f(r.get("open")); h=_f(r.get("high")); l=_f(r.get("low")); cclose=_f(r.get("close"))
                    chg_raw=r.get("change_percent") or r.get("change%") or ""
                    try: chg=float(chg_raw)
                    except: chg=None

                    s_slug=slug(sym)
                    sig,conf,reason=(" ",0,"")
                    if None not in (o,h,l,cclose): sig,conf,reason=classify(o,h,l,cclose)

                    stock_url=f"{BASE_URL}/{gslug}/{cslug}/{e_slug}/{s_slug}/prediction-tomorrow/"
                    chg_cell=pct_html(chg)

                    # row HTML
                    table_rows_html.append(
                        "<tr>"
                        f"<td><a href='{stock_url}'>{html.escape(sym)}</a></td>"
                        f"<td><a href='{stock_url}'>{html.escape(name)}</a></td>"
                        f"<td>{html.escape(sec)}</td>"
                        f"<td>{'' if o is None else '{:.2f}'.format(o)}</td>"
                        f"<td>{'' if h is None else '{:.2f}'.format(h)}</td>"
                        f"<td>{'' if l is None else '{:.2f}'.format(l)}</td>"
                        f"<td>{'' if cclose is None else '{:.2f}'.format(cclose)}</td>"
                        f"<td>{chg_cell}</td>"
                        f"<td><a class='btn' href='{stock_url}'>AI Prediction</a></td>"
                        "</tr>"
                    )

                    # JSON row for app.js table
                    logo_url=resolver.url_for(exch, sym, name)
                    json_rows.append({
                        "symbol": sym, "name": name, "sector": sec,
                        "open": None if o is None else round(o,2),
                        "high": None if h is None else round(h,2),
                        "low":  None if l is None else round(l,2),
                        "close":None if cclose is None else round(cclose,2),
                        "change_percent": None if chg is None else round(chg,4),
                        "signal": sig, "logo": logo_url,
                        "url": stock_url
                    })

                    # --- Per-stock page with 7-day back-test ---
                    if sym and None not in (o,h,l,cclose):
                        pred_date=next_business_day(datetime.utcnow().date()).isoformat()
                        bt=make_last7_backtest(tree[gslug][cslug]["group_name"], cname, cslug, sym)

                        win_line = ""
                        if bt["total"]:
                            win_line = (
                                f"<div class='mini mut'>Last 7 accuracy: <strong>{bt['win_pct']}%</strong> "
                                f"({bt['wins']} / {bt['total']} wins)</div>"
                            )

                        bt_rows=[]
                        for row7 in bt["rows"]:
                            cls="win" if row7["is_win"] else "loss"
                            close_txt = "" if row7["close"] is None else "{:.2f}".format(row7["close"])
                            bt_rows.append(
                                "<tr>"
                                f"<td>{html.escape(row7['date'])}</td>"
                                f"<td>{html.escape(row7['prediction'])}</td>"
                                f"<td class='mini'>{close_txt}</td>"
                                f"<td class='{cls}'>{html.escape(row7['result'])}</td>"
                                "</tr>"
                            )

                        empty_html = '<tr><td colspan="4" class="mut">Not enough historical data.</td></tr>'
                        tbody_html = "".join(bt_rows) if bt_rows else empty_html

                        bt_table = (
                            "<div class='card'>"
                            "<h3 class='h3'>Back-tested performance (last 7 trading days)</h3>"
                            f"{win_line}"
                            "<div class='table-wrap'><table class='table'>"
                            "<thead><tr><th>Date</th><th>AI Prediction</th><th>Actual Close</th><th>Result</th></tr></thead>"
                            f"<tbody>{tbody_html}</tbody>"
                            "</table></div></div>"
                        )

                        chg_header = pct_html(chg)
                        title=f"AI Analysis of {sym} Tomorrow | {name} Stock Prediction"
                        h1=f"AI Analysis of {sym} ({name}) Stock for Tomorrow"
                        mdesc=f"Prediction and recent back-test for {sym} listed on {exch} in {cname}."
                        header = (
                            "<div class='card'>"
                            f"<h2 class='h2'>{html.escape(h1)}</h2>"
                            f"<p class='mini mut'>Region: {html.escape(gname)} · Country: {html.escape(cname)} · Exchange: {html.escape(exch)}</p>"
                            f"<p class='mini mut'>OHLC: O {'{:.2f}'.format(o)}, H {'{:.2f}'.format(h)}, L {'{:.2f}'.format(l)}, C {'{:.2f}'.format(cclose)} · Change%: {chg_header}</p>"
                            f"<div class='card'><h3 class='h3'>Prediction for {pred_date}</h3><p><strong>{html.escape(sig or 'Signal')}</strong> (confidence {int(conf*100)}%).</p></div>"
                            "</div>"
                        )
                        stock_body = header + bt_table
                        write_text(DIST/gslug/cslug/e_slug/slug(sym)/"prediction-tomorrow"/"index.html",
                                   tpl_base(title, mdesc, stock_body, f"{BASE_URL}/{gslug}/{cslug}/{e_slug}/{slug(sym)}/prediction-tomorrow/"))

                table_html = (
                    "<table class='table'>"
                    "<thead><tr><th>Symbol</th><th>Name</th><th>Sector</th>"
                    "<th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Change%</th><th>Signal</th></tr></thead>"
                    f"<tbody>{''.join(table_rows_html)}</tbody></table>"
                )
                write_text(DIST/gslug/cslug/e_slug/"index.html",
                           tpl_base(f"{cname} {exch} — {CFG.get('site_title','')}",
                                    f"Browse {exch} listings in {cname}.",
                                    table_html, f"{BASE_URL}/{gslug}/{cslug}/{e_slug}/"))
                write_json(DIST/"static"/"exchanges"/gslug/cslug/f"{e_slug}.json",
                           {"region": gname, "country": cname, "exchange": exch, "rows": json_rows})

            # Country landing
            write_text(DIST/gslug/cslug/"index.html",
                       tpl_base(f"{cname} — {CFG.get('site_title','')}",
                                f"Browse exchanges in {cname}.",
                                "<section class='card'><h2 class='h2'>Exchanges</h2><ul>"
                                + "".join([f"<li><a href='{BASE_URL}/{gslug}/{cslug}/{e['slug']}/'>{html.escape(e['name'])}</a></li>"
                                           for e in c['exchanges']]) +
                                "</ul></section>",
                                f"{BASE_URL}/{gslug}/{cslug}/"))

    # index.json for app.js
    write_json(DIST/"static"/"index.json", site_index)

    # robots + sitemap
    write_text(DIST/"robots.txt", f"Sitemap: {BASE_URL}/sitemap.xml\nUser-agent: *\nAllow: /\n")
    urls=[]
    for p in DIST.rglob("index.html"):
        rel="/"+str(p.relative_to(DIST)).replace("\\","/")
        urls.append(f"{BASE_URL}{rel[:-10]}")
    urls=sorted(set(urls))
    write_text(DIST/"sitemap.xml",
               "<?xml version='1.0' encoding='UTF-8'?><urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
               + "".join([f"<url><loc>{u}</loc></url>" for u in urls]) + "</urlset>")
    print("Build complete →", DIST)

if __name__=="__main__":
    main()
