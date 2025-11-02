#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
search_setup.py
- Builds /dist/static/search_index.json (flat list of stocks)
- Writes /dist/static/search.js, which turns the HERO INPUT (#tickerInput) into the GLOBAL SEARCH.
- Does NOT edit /dist/index.html (build.py injects markets grid only).
"""

import csv, json, re
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
    index = []
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
    # NB: this JS removes the 5-char cap and allows multi-word queries (e.g., "tata motors")
    js = r"""
(function(){
  function $(s, r=document){ return r.querySelector(s); }

  function ready(fn){
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn);
    } else { fn(); }
  }

  // simple text normalizer (diacritics-insensitive)
  function norm(s){
    return (s||'')
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g,'')
      .trim();
  }

  ready(function(){
    const input = document.getElementById('tickerInput');
    if (!input) return;

    // ---- remove old UI limits (was 3-5 uppercase ticker) ----
    try { input.maxLength = 64; } catch(_){}
    try { input.setAttribute('maxlength','64'); } catch(_){}
    try { input.classList.remove('uppercase'); } catch(_){}

    const btn   = document.getElementById('predictButton');
    const resBox= document.getElementById('resultsContainer'); // old mock area (we'll keep hidden)
    if (resBox) resBox.style.display = 'none';

    const hostCard = input.closest('.card-bg') || input.parentElement || document.body;

    // Results panel
    const panel = document.createElement('div');
    panel.id = 'rs-results';
    panel.style.marginTop   = '10px';
    panel.style.border      = '1px solid #E2E8F0';
    panel.style.background  = '#FFFFFF';
    panel.style.borderRadius= '12px';
    panel.style.padding     = '8px';
    panel.style.maxHeight   = '360px';
    panel.style.overflow    = 'auto';
    panel.style.display     = 'none';
    panel.style.position    = 'relative';
    panel.style.zIndex      = '5';

    if (resBox && resBox.parentNode === hostCard){
      hostCard.insertBefore(panel, resBox);
    } else {
      hostCard.appendChild(panel);
    }

    const note = document.createElement('div');
    note.style.fontSize = '12px';
    note.style.color    = '#64748B';
    note.style.padding  = '2px 4px';
    note.textContent    = 'Type a symbol (e.g., TATAMOTORS) or a company name (e.g., Tata Motors)';
    panel.appendChild(note);

    let cache = null, timer = null;

    async function ensureIndex(){
      if (cache) return cache;
      // absolute-safe path
      const res = await fetch('/static/search_index.json', {cache:'no-store'});
      cache = await res.json();
      // add precomputed normalized fields for faster matching
      for (let i=0;i<cache.length;i++){
        const it = cache[i];
        it._symbol = norm(it.symbol);
        it._name   = norm(it.name);
      }
      return cache;
    }

    function escapeHtml(s){
      return (s||'').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
    }

    function matchItems(idx, q){
      // token-based: all tokens must be contained in the name (AND),
      // OR the symbol must start with the whole query (for tickers)
      const qn = norm(q);
      const tokens = qn.split(/\s+/).filter(Boolean);
      if (!tokens.length) return [];

      const out = [];
      for (let i=0;i<idx.length;i++){
        const it = idx[i];

        // symbol prefix
        if (it._symbol && it._symbol.startsWith(qn)) {
          out.push(it);
          if (out.length>600) break;
          continue;
        }
        // name tokens AND
        let ok = true;
        for (let t of tokens){
          if (!it._name || it._name.indexOf(t) === -1){ ok=false; break; }
        }
        if (ok){
          out.push(it);
          if (out.length>600) break;
        }
      }
      return out;
    }

    function render(items){
      panel.innerHTML = '';
      panel.appendChild(note);
      if (!items.length){
        note.textContent = 'No matches';
        return;
      }
      note.textContent = items.length + ' match' + (items.length>1?'es':'');
      const frag = document.createDocumentFragment();
      items.slice(0,200).forEach(it=>{
        const a = document.createElement('a');
        a.href = it.url;
        a.style.display       = 'flex';
        a.style.alignItems    = 'center';
        a.style.gap           = '10px';
        a.style.padding       = '8px 10px';
        a.style.border        = '1px solid #E2E8F0';
        a.style.borderRadius  = '10px';
        a.style.marginTop     = '6px';
        a.style.textDecoration= 'none';
        a.style.color         = '#0B111D';
        a.onmouseenter = ()=>{ a.style.borderColor = '#7A3EDC'; };
        a.onmouseleave = ()=>{ a.style.borderColor = '#E2E8F0'; };
        a.innerHTML =
          "<span style='font-weight:700;min-width:84px'>" + escapeHtml(it.symbol||'') + "</span>" +
          "<span style='opacity:.9'>" + escapeHtml(it.name||'') + "</span>" +
          "<span style='margin-left:auto;color:#4D95EE;font-size:12px'>" +
          escapeHtml(it.exchange||'') + " · " + escapeHtml(it.country||'') + "</span>";
        frag.appendChild(a);
      });
      panel.appendChild(frag);
    }

    async function searchNow(){
      const q = (input.value||'').trim();
      if (q.length < 2){
        panel.style.display = 'none';
        if (resBox) resBox.style.display = 'none';
        return;
      }
      const idx = await ensureIndex();
      const out = matchItems(idx, q);
      panel.style.display = 'block';
      if (resBox) resBox.style.display = 'none';
      render(out);
      return out;
    }

    input.addEventListener('input', ()=>{
      clearTimeout(timer);
      timer = setTimeout(searchNow, 120);
    });

    input.addEventListener('focus', async ()=>{
      if (!cache) await ensureIndex().catch(()=>{});
      if ((input.value||'').trim().length >= 2) searchNow();
    });

    input.addEventListener('keydown', async (e)=>{
      if (e.key === 'Enter'){
        const items = await searchNow();
        const first = panel.querySelector('a[href]');
        if (first){
          e.preventDefault();
          location.href = first.href;
        } else if (items && items.length){
          e.preventDefault();
          location.href = items[0].url;
        }
      }
    });

    if (btn){
      btn.addEventListener('click', async (e)=>{
        e.preventDefault();
        const items = await searchNow();
        const first = panel.querySelector('a[href]');
        if (first){ location.href = first.href; }
        else if (items && items.length){ location.href = items[0].url; }
        else { panel.style.display='block'; note.textContent='No matches'; }
      }, {capture:true});
    }

    document.addEventListener('click', (e)=>{
      if (!panel.contains(e.target) && e.target !== input){
        panel.style.display = 'none';
      }
    });
  });
})();
"""
    (STATIC / "search.js").write_text(js, encoding="utf-8")
    print(f"✅ Wrote {(STATIC / 'search.js').relative_to(ROOT)}")

def main():
    STATIC.mkdir(parents=True, exist_ok=True)
    index = build_search_index()
    write_search_index(index)
    write_search_js()
    print("🎉 Search setup complete (hero input powers global search).")

if __name__ == "__main__":
    main()
