/* Drilldown with logos + fallback, search & sort */
(function () {
  const $ = (sel) => document.querySelector(sel);
  const regionsEl    = $("#regions");
  const countriesEl  = $("#countries");
  const exchangesEl  = $("#exchanges");
  const tableMountEl = $("#stocks_table");

  const BASE = (window.SPP_BASE || "").replace(/\/$/, "");
  const INDEX_URL = window.SPP_INDEX_URL;
  const PLACEHOLDER = `${BASE}/static/logo-placeholder.svg`;

  const el = (tag, cls, html) => { const n = document.createElement(tag); if (cls) n.className = cls; if (html!=null) n.innerHTML = html; return n; };
  const chip = (label, onClick, url) => { const a = el("a","chip",label); a.href=url||"javascript:void(0)"; if(onClick){a.addEventListener("click",e=>{e.preventDefault(); onClick(a);});} return a; };
  const match = (row, q) => (row.symbol + " " + row.name + " " + (row.sector||"")).toLowerCase().includes(q);

  let state = { regions:[], selectedRegion:null, selectedCountry:null, selectedExchange:null, rows:[], sort:{key:"symbol", dir:1}, filter:"" };

  function setActive(container, a){ [...container.querySelectorAll(".chip")].forEach(x=>x.classList.remove("active")); if(a) a.classList.add("active"); }

  function renderRegions(){
    regionsEl.innerHTML="";
    state.regions.forEach(r=>{
      regionsEl.appendChild(chip(r.name,(a)=>{ state.selectedRegion=r; state.selectedCountry=null; state.selectedExchange=null; setActive(regionsEl,a); renderCountries(); exchangesEl.innerHTML=""; tableMountEl.innerHTML="Pick an exchange."; }, r.url));
    });
  }
  function renderCountries(){
    countriesEl.innerHTML="";
    const region=state.selectedRegion; if(!region) return;
    (region.countries||[]).forEach(c=>{
      countriesEl.appendChild(chip(c.name,(a)=>{ state.selectedCountry=c; state.selectedExchange=null; setActive(countriesEl,a); renderExchanges(); tableMountEl.innerHTML="Pick an exchange."; }, c.url));
    });
  }
  function renderExchanges(){
    exchangesEl.innerHTML="";
    const c=state.selectedCountry; if(!c) return;
    (c.exchanges||[]).forEach(ex=>{
      exchangesEl.appendChild(chip(ex.name,(a)=>{ state.selectedExchange=ex; setActive(exchangesEl,a); loadExchangeJSON(state.selectedRegion.slug, c.slug, ex.slug); }, ex.url));
    });
  }

  function renderToolbar(){
    const bar=el("div","toolbar");
    const input=el("input","input"); input.type="search"; input.placeholder="Search symbols, names, sectors…"; input.value=state.filter;
    input.addEventListener("input",()=>{ state.filter=input.value.trim().toLowerCase(); renderTable(); });
    const sel=el("select","select");
    ["symbol","name","sector","open","high","low","close","signal"].forEach(k=>{ const o=el("option",null,k.toUpperCase()); o.value=k; if(k===state.sort.key) o.selected=true; sel.appendChild(o); });
    sel.addEventListener("change",()=>{ state.sort.key=sel.value; renderTable(); });
    bar.appendChild(input); bar.appendChild(sel); return bar;
  }

  function renderTable(){
    tableMountEl.innerHTML="";
    tableMountEl.appendChild(renderToolbar());
    let rows=state.rows;
    if(state.filter) rows=rows.filter(r=>match(r,state.filter));
    const {key,dir}=state.sort;
    rows=rows.slice().sort((a,b)=>{ const va=a[key], vb=b[key]; if(va==null&&vb!=null) return -1*dir; if(vb==null&&va!=null) return 1*dir; if(typeof va==="number"&&typeof vb==="number") return (va-vb)*dir; return String(va).localeCompare(String(vb))*dir; });

    const wrap=el("div","table-wrap"); const tbl=el("table","table");
    const head=el("thead"); head.innerHTML=`<tr>
      <th data-k="symbol">Symbol</th><th data-k="name">Name</th><th data-k="sector">Sector</th>
      <th data-k="open">Open</th><th data-k="high">High</th><th data-k="low">Low</th><th data-k="close">Close</th><th data-k="signal">Signal</th>
    </tr>`;
    head.querySelectorAll("th").forEach(th=>{
      th.addEventListener("click",()=>{ const k=th.getAttribute("data-k"); if(state.sort.key===k) state.sort.dir*=-1; else {state.sort.key=k; state.sort.dir=1;} renderTable(); });
    });
    tbl.appendChild(head);

    const body=el("tbody");
    rows.forEach(r=>{
      const tr=el("tr");
      const logo = r.logo || PLACEHOLDER;
      tr.innerHTML =
        `<td>
           <a href="${r.url}">
             <img src="${logo}" alt="${r.symbol}" style="height:20px;width:20px;object-fit:contain;margin-right:6px;vertical-align:middle;"
                  onerror="this.onerror=null;this.src='${PLACEHOLDER}';">
             ${r.symbol}
           </a>
         </td>
         <td><a href="${r.url}">${r.name}</a></td>
         <td>${r.sector||""}</td>
         <td>${r.open ?? ""}</td>
         <td>${r.high ?? ""}</td>
         <td>${r.low ?? ""}</td>
         <td>${r.close ?? ""}</td>
         <td><span class="badge ${String(r.signal||'').toLowerCase()}">${r.signal||""}</span></td>`;
      body.appendChild(tr);
    });
    tbl.appendChild(body); wrap.appendChild(tbl); tableMountEl.appendChild(wrap);
  }

  function loadExchangeJSON(r,c,e){
    const url = `${BASE}/static/exchanges/${r}/${c}/${e}.json`;
    fetch(url).then(r=>r.json()).then(data=>{ state.rows=data.rows||[]; state.filter=""; state.sort={key:"symbol",dir:1}; renderTable(); })
      .catch(()=>{ tableMountEl.innerHTML="Could not load stocks for this exchange."; });
  }

  // Boot
  fetch(INDEX_URL).then(r=>r.json()).then(data=>{
    state.regions=data.regions||[]; renderRegions();

    // light geo default
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone||"";
    const hints=[
      {re:/^Asia\/Kolkata/, region:"Asia - Pacific", country:"India"},
      {re:/^Australia\//, region:"Asia - Pacific", country:"Australia"},
      {re:/^Asia\/(Tokyo|Seoul)/, region:"Asia - Pacific", country:"Japan"},
      {re:/^Europe\//, region:"Europe", country:"United Kingdom"},
      {re:/^America\/(New|Los|Chicago|Toronto)/, region:"North America", country:"USA"},
    ];
    const hit=hints.find(h=>h.re.test(tz));
    if(hit){
      const region=state.regions.find(r=>r.name===hit.region);
      if(region){ state.selectedRegion=region; renderCountries();
        const c=(region.countries||[]).find(x=>x.name.toLowerCase()===hit.country.toLowerCase());
        if(c){ state.selectedCountry=c; renderExchanges(); }
      }
    }
  }).catch(()=>{ regionsEl.innerHTML="Could not load regions."; });
})();
