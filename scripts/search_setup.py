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
                if not sym: continue
                name = (r.get("description") or sym).strip()
                exchange = (r.get("exchange") or "").strip()
                if not exchange: continue
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
    js = r"""
(function(){
  // Bind to the HERO input (Ravensight)
  const input = document.getElementById('tickerInput');
  if (!input) return;

  // Create a results panel just under the hero card
  const hostCard = input.closest('.card-bg') || input.parentElement;
  const panel = document.createElement('div');
  panel.id = 'rs-results';
  panel.style.marginTop = '10px';
  panel.style.border = '1px solid #E2E8F0';
  panel.style.background = '#FFFFFF';
  panel.style.borderRadius = '12px';
  panel.style.padding = '8px';
  panel.style.maxHeight = '360px';
  panel.style.overflow = 'auto';
  panel.style.display = 'none';
  hostCard.appendChild(panel);

  const note = document.createElement('div');
  note.style.fontSize = '12px';
  note.style.color = '#64748B';
  note.style.padding = '2px 4px';
  note.textContent = 'Type at least 2 characters';
  panel.appendChild(note);

  let cache = null, timer = null;

  async function ensureIndex(){
    if (cache) return cache;
    const res = await fetch((window.SPP_BASE||'') + '/static/search_index.json', {cache:'no-store'});
    cache = await res.json();
    return cache;
  }

  function escapeHtml(s){
    return (s||'').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
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
      a.style.display = 'flex';
      a.style.alignItems = 'center';
      a.style.gap = '10px';
      a.style.padding = '8px 10px';
      a.style.border = '1px solid #E2E8F0';
      a.style.borderRadius = '10px';
      a.style.marginTop = '6px';
      a.style.textDecoration = 'none';
      a.style.color = '#0B111D';
      a.onmouseenter = ()=>{ a.style.borderColor = '#7A3EDC'; };
      a.onmouseleave = ()=>{ a.style.borderColor = '#E2E8F0'; };
      a.innerHTML = `
        <span style="font-weight:700;min-width:84px">${escapeHtml(it.symbol||'')}</span>
        <span style="opacity:.9">${escapeHtml(it.name||'')}</span>
        <span style="margin-left:auto;color:#4D95EE;font-size:12px">${escapeHtml(it.exchange||'')} · ${escapeHtml(it.country||'')}</span>
      `;
      frag.appendChild(a);
    });
    panel.appendChild(frag);
  }

  async function onInput(){
    const q = input.value.trim();
    if (q.length < 2){
      panel.style.display = 'none';
      return;
    }
    const idx = await ensureIndex();
    const ql = q.toLowerCase();
    const out = [];
    for (let i=0;i<idx.length;i++){
      const it = idx[i];
      if ((it.symbol && it.symbol.toLowerCase().startsWith(ql)) ||
          (it.name && it.name.toLowerCase().includes(ql))) {
        out.push(it);
        if (out.length>500) break;
      }
    }
    panel.style.display = 'block';
    render(out);
  }

  input.addEventListener('input', ()=>{
    clearTimeout(timer);
    timer = setTimeout(onInput, 120);
  });

  input.addEventListener('focus', async ()=>{
    if (!cache) await ensureIndex().catch(()=>{});
    if (input.value.trim().length >= 2) onInput();
  });

  // ENTER navigates to first match if visible
  input.addEventListener('keydown', async (e)=>{
    if (e.key === 'Enter'){
      const links = panel.querySelectorAll('a[href]');
      if (panel.style.display !== 'none' && links.length){
        e.preventDefault();
        location.href = links[0].href;
      }
    }
  });

  // click outside closes the panel
  document.addEventListener('click', (e)=>{
    if (!panel.contains(e.target) && e.target !== input){
      panel.style.display = 'none';
    }
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
