#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
search_setup.py
- Generates /dist/static/search_index.json from Data/LastTradingDay
- Injects a search bar + client-side search JS into /dist/index.html

Run AFTER your normal build.py.
"""

import csv, json, os, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_LAST = ROOT / "Data" / "LastTradingDay"
DIST = ROOT / "dist"
STATIC = DIST / "static"

CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
BASE_URL = (CONFIG.get("base_url", "") or "").rstrip("/")

def slug(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "item"

def read_csv_rows(p: Path):
    out = []
    with open(p, "r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            row = { (k or "").strip().lower(): (v or "").strip() for k, v in row.items() }
            out.append(row)
    return out

def build_search_index():
    """Scan Data/LastTradingDay and produce a flat index of stocks for search."""
    index = []  # [{symbol, name, exchange, country, region, url}]
    if not DATA_LAST.exists():
        return index

    for region_dir in sorted(d for d in DATA_LAST.iterdir() if d.is_dir()):
        region_name = region_dir.name
        region_slug = slug(region_name)

        for csvp in sorted(region_dir.glob("*.csv")):
            country_raw = csvp.stem
            country_name = country_raw.replace("-", " ").title()
            country_slug = slug(country_raw)

            rows = read_csv_rows(csvp)
            for r in rows:
                sym = (r.get("symbol") or "").strip()
                if not sym:
                    continue
                name = (r.get("description") or sym).strip()
                exchange = (r.get("exchange") or "").strip()
                if not exchange:
                    continue
                ex_slug = slug(exchange)
                sym_slug = slug(sym)

                url = f"{BASE_URL}/{region_slug}/{country_slug}/{ex_slug}/{sym_slug}/prediction-tomorrow/"
                index.append({
                    "symbol": sym,
                    "name": name,
                    "exchange": exchange,
                    "country": country_name,
                    "region": region_name,
                    "url": url
                })
    return index

def write_search_index(index):
    STATIC.mkdir(parents=True, exist_ok=True)
    outp = STATIC / "search_index.json"
    outp.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    print(f"✅ Wrote {outp.relative_to(ROOT)} ({len(index)} entries)")

def write_search_js():
    """
    Write /dist/static/search.js — lightweight client-side search
    - Lazy loads JSON on first use
    - Filters by symbol or name (case-insensitive)
    """
    js = r"""
(function(){
  const $ = (s, r=document)=>r.querySelector(s);
  const $$ = (s, r=document)=>Array.from(r.querySelectorAll(s));

  const root = document.getElementById('global-search');
  if (!root) return;

  const input = document.createElement('input');
  input.type = 'search';
  input.placeholder = 'Search stock by symbol or name…';
  input.autocomplete = 'off';
  input.className = 'gs-input';

  const results = document.createElement('div');
  results.className = 'gs-results';

  const note = document.createElement('div');
  note.className = 'gs-note';
  note.textContent = 'Type at least 2 characters';

  const style = document.createElement('style');
  style.textContent = `
    .gs-wrap{margin:16px 0 8px;padding:12px;background:#111a25;border:1px solid #22395f;border-radius:10px}
    .gs-input{width:100%;padding:10px 12px;border-radius:8px;border:1px solid #2b4a70;background:#0d1117;color:#fff;font-size:14px;outline:none}
    .gs-input:focus{border-color:#4f7bff;box-shadow:0 0 0 2px #4f7bff33}
    .gs-results{margin-top:8px;max-height:360px;overflow:auto}
    .gs-item{display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:8px;border:1px solid #243c62;background:#0f1522;margin-top:6px;text-decoration:none;color:#fff}
    .gs-item:hover{background:#203553}
    .gs-sym{font-weight:700;min-width:84px}
    .gs-name{opacity:.9}
    .gs-meta{margin-left:auto;color:#7fb1ff;font-size:12px}
    .gs-note{color:#9fb3ce;font-size:12px;margin-top:8px}
  `;
  document.head.appendChild(style);

  const wrap = document.createElement('div');
  wrap.className = 'gs-wrap';
  wrap.appendChild(input);
  wrap.appendChild(results);
  wrap.appendChild(note);
  root.appendChild(wrap);

  let cache = null; // lazy-loaded
  let timer = null;

  async function ensureIndex(){
    if (cache) return cache;
    const res = await fetch((window.SPP_BASE||'') + '/static/search_index.json', {cache:'no-store'});
    cache = await res.json();
    return cache;
  }

  function render(items){
    results.innerHTML = '';
    if (!items.length){
      note.textContent = 'No matches';
      return;
    }
    note.textContent = items.length + ' match' + (items.length>1?'es':'');
    const frag = document.createDocumentFragment();
    items.slice(0,200).forEach(it=>{
      const a = document.createElement('a');
      a.className = 'gs-item';
      a.href = it.url;
      a.innerHTML = `
        <span class="gs-sym">${escapeHtml(it.symbol||'')}</span>
        <span class="gs-name">${escapeHtml(it.name||'')}</span>
        <span class="gs-meta">${escapeHtml(it.exchange||'')} · ${escapeHtml(it.country||'')}</span>
      `;
      frag.appendChild(a);
    });
    results.appendChild(frag);
  }

  function escapeHtml(s){
    return (s||'').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  }

  async function onInput(){
    const q = input.value.trim();
    if (q.length < 2){
      results.innerHTML = '';
      note.textContent = 'Type at least 2 characters';
      return;
    }
    const idx = await ensureIndex();
    const ql = q.toLowerCase();
    const out = [];
    for (let i=0;i<idx.length;i++){
      const it = idx[i];
      // match by symbol startswith or name contains
      if ((it.symbol && it.symbol.toLowerCase().startsWith(ql)) ||
          (it.name && it.name.toLowerCase().includes(ql))) {
        out.push(it);
        if (out.length>500) break; // hard cap to keep UI snappy
      }
    }
    render(out);
  }

  // debounce
  input.addEventListener('input', ()=>{
    clearTimeout(timer);
    timer = setTimeout(onInput, 120);
  });

  // load index lazily on first focus, so it’s instant afterward
  input.addEventListener('focus', ()=>{ if (!cache) ensureIndex().catch(()=>{}); });

})();
"""
    (STATIC / "search.js").write_text(js, encoding="utf-8")
    print(f"✅ Wrote {(STATIC / 'search.js').relative_to(ROOT)}")

def inject_search_into_landing():
    """Injects a search container + script into dist/index.html."""
    idx_html = DIST / "index.html"
    if not idx_html.exists():
        print("⚠️ dist/index.html not found. Run your main build.py first.")
        return

    html = idx_html.read_text(encoding="utf-8")

    # 1) Insert container just after <main class="grid">
    marker = "<main class=\"grid\">"
    block = (
        marker
        + "\n"
        + "<section class=\"region\" id=\"global-search\">\n"
        + "  <h2 style=\"color:#00b7ff;margin:0 0 10px\">Search</h2>\n"
        + "  <!-- Search UI will be injected here by /static/search.js -->\n"
        + "</section>\n"
    )
    if marker in html and "id=\"global-search\"" not in html:
        html = html.replace(marker, block, 1)
        print("✅ Inserted search container into dist/index.html")
    else:
        print("ℹ️ Search container already present (or marker not found).")

    # 2) Ensure <script src=".../static/search.js" defer> before </body>
    script_tag = f"<script src=\"{BASE_URL}/static/search.js\" defer></script>"
    if script_tag not in html:
        html = html.replace("</body>", script_tag + "\n</body>")
        print("✅ Added search.js script tag to dist/index.html")
    else:
        print("ℹ️ search.js script already referenced.")

    idx_html.write_text(html, encoding="utf-8")

def main():
    STATIC.mkdir(parents=True, exist_ok=True)
    index = build_search_index()
    write_search_index(index)
    write_search_js()
    inject_search_into_landing()
    print("🎉 Search setup complete.")

if __name__ == "__main__":
    main()
