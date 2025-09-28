/* Interactive homepage: Regions → Countries → Exchanges → Stocks */
const regionsDiv = document.getElementById("regions");
const countriesSection = document.getElementById("countries-section");
const countriesDiv = document.getElementById("countries");
const exchangesSection = document.getElementById("exchanges-section");
const exchangesDiv = document.getElementById("exchanges");
const stocksSection = document.getElementById("stocks-section");
const stocksDiv = document.getElementById("stocks");

// --- Robust BASE: use injected BASE_URL if present, else compute from current location (works for custom domain and GitHub subpath) ---
const RUNTIME_BASE =
  (typeof window.BASE_URL === "string" && window.BASE_URL.trim().length
    ? window.BASE_URL
    : (location.origin + (location.pathname.endsWith("/") ? location.pathname.slice(0, -1) : location.pathname))
  ).replace(/\/$/, "");

// helper classes
const clsBtn = "px-4 py-2 rounded-xl shadow bg-gradient-to-r from-indigo-600 to-blue-600 hover:from-indigo-500 hover:to-blue-500 transition";
const clsBtnGhost = "px-4 py-2 rounded-xl bg-gray-800 hover:bg-gray-700 transition";
const activeStyle = "ring-2 ring-white/60";

let SITE = null;

const slug = (s) => (s || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
function clearActive(parent) { [...parent.querySelectorAll("button")].forEach(b => b.classList.remove(activeStyle)); }
function button(txt, onClick, solid=true) { const b=document.createElement("button"); b.className=solid?clsBtn:clsBtnGhost; b.textContent=txt; b.onclick=()=>onClick(b); return b; }
function fmt(x){ return (x===null || x===undefined || isNaN(x)) ? "" : Number(x).toFixed(2); }

async function loadSite() {
  // ← KEY LINE: always fetch relative to RUNTIME_BASE
  const res = await fetch(`${RUNTIME_BASE}/data/index.json`, {cache: "no-store"});
  const j = await res.json();
  SITE = j.data;
  renderRegions();
  await autoSelectByLocation().catch(()=>{});
  // Fallback defaults
  if (!document.querySelector("#countries-section:not(.hidden)")) {
    const r = (window.DEFAULTS?.region) || Object.keys(SITE)[0];
    selectRegionSlug(r);
    const c = (window.DEFAULTS?.country) || Object.keys(SITE[r].countries)[0];
    selectCountrySlug(r, c);
    const e = Object.keys(SITE[r].countries[c].exchanges)[0];
    selectExchangeSlug(r, c, e);
  }
}

function renderRegions() {
  regionsDiv.innerHTML = "";
  Object.entries(SITE).forEach(([rslug, rdata]) => {
    regionsDiv.appendChild(button(rdata.display, (btn)=>{
      clearActive(regionsDiv); btn.classList.add(activeStyle);
      selectRegionSlug(rslug);
    }));
  });
}

function selectRegionSlug(rslug) {
  countriesSection.classList.remove("hidden");
  countriesDiv.innerHTML = "";
  Object.entries(SITE[rslug].countries).forEach(([cslug, cdata])=>{
    countriesDiv.appendChild(button(cdata.display, (btn)=>{
      clearActive(countriesDiv); btn.classList.add(activeStyle);
      selectCountrySlug(rslug, cslug);
    }, false));
  });
}

function selectCountrySlug(rslug, cslug) {
  exchangesSection.classList.remove("hidden");
  exchangesDiv.innerHTML = "";
  const exchs = SITE[rslug].countries[cslug].exchanges;
  Object.entries(exchs).forEach(([eslug, edata])=>{
    exchangesDiv.appendChild(button(edata.display, (btn)=>{
      clearActive(exchangesDiv); btn.classList.add(activeStyle);
      selectExchangeSlug(rslug, cslug, eslug);
    }, false));
  });
}

function selectExchangeSlug(rslug, cslug, eslug) {
  stocksSection.classList.remove("hidden");
  const rows = SITE[rslug].countries[cslug].exchanges[eslug].stocks || [];
  stocksDiv.innerHTML = rows.map(s => `
    <tr>
      <td><a class="text-blue-400 hover:underline" href="${s.url}">${s.symbol}</a></td>
      <td><a class="text-blue-400 hover:underline" href="${s.url}">${s.name}</a></td>
      <td>${s.sector || ""}</td>
      <td>${fmt(s.open)}</td>
      <td>${fmt(s.high)}</td>
      <td>${fmt(s.low)}</td>
      <td>${fmt(s.close)}</td>
      <td>${s.signal || ""}</td>
    </tr>
  `).join("");
}

/* Light geolocation; safe fallback if blocked */
async function autoSelectByLocation(){
  try{
    const r = await fetch("https://ipapi.co/json/", {cache:"no-store"}).then(r=>r.json());
    const cslug = slug(r.country_name || "");
    if(!cslug) return;
    for (const [rslug, rdata] of Object.entries(SITE)) {
      if (rdata.countries[cslug]) {
        const exchs = Object.keys(rdata.countries[cslug].exchanges);
        if (exchs.length) {
          selectRegionSlug(rslug);
          selectCountrySlug(rslug, cslug);
          selectExchangeSlug(rslug, cslug, exchs[0]);
        }
        break;
      }
    }
  } catch(e) { /* ignore */ }
}

window.addEventListener("DOMContentLoaded", loadSite);
