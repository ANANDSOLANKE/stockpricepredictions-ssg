/* Interactive homepage: Regions → Countries → Exchanges → Stocks */
const regionsDiv = document.getElementById("regions");
const countriesSection = document.getElementById("countries-section");
const countriesDiv = document.getElementById("countries");
const exchangesSection = document.getElementById("exchanges-section");
const exchangesDiv = document.getElementById("exchanges");
const stocksSection = document.getElementById("stocks-section");
const stocksDiv = document.getElementById("stocks");

// Robust base path (works on custom domain or GitHub subpath)
const RUNTIME_BASE =
  (typeof window.BASE_URL === "string" && window.BASE_URL.trim().length
    ? window.BASE_URL
    : (location.origin + (location.pathname.endsWith("/") ? location.pathname.slice(0, -1) : location.pathname))
  ).replace(/\/$/, "");

// Small helpers
const text = (v) => (v ?? "").toString();
const getLabel = (obj) => text(obj?.label ?? obj?.display ?? "");
const fmt = (x) => (x == null || isNaN(x) ? "" : Number(x).toFixed(2));
const slug = (s) => text(s).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

// Button styles
const clsBtn = "px-4 py-2 rounded-xl shadow bg-gradient-to-r from-indigo-600 to-blue-600 hover:from-indigo-500 hover:to-blue-500 text-white transition";
const clsBtnGhost = "px-4 py-2 rounded-xl bg-gray-800 hover:bg-gray-700 text-white transition";
const activeStyle = "ring-2 ring-white/60";

function clearActive(parent) { [...parent.querySelectorAll("button")].forEach(b => b.classList.remove(activeStyle)); }
function button(txt, onClick, solid = true) {
  const b = document.createElement("button");
  b.className = solid ? clsBtn : clsBtnGhost;
  b.textContent = txt || "(unnamed)";
  b.onclick = () => onClick(b);
  return b;
}

let SITE = null; // structure: { regionSlug: { display/label, countries: { countrySlug: { display/label, exchanges: { exchSlug: { display/label, stocks: [...] }}}}}}

// Load site JSON
async function loadSite() {
  const url = `${RUNTIME_BASE}/data/index.json`;
  console.log("[app] fetching", url);
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    console.error("[app] failed to fetch data/index.json:", res.status, res.statusText);
    return;
  }
  const j = await res.json();
  if (!j || !j.data) {
    console.error("[app] malformed JSON (missing .data)");
    return;
  }
  SITE = j.data;

  renderRegions();

  // Try auto-select by IP (best effort)
  try { await autoSelectByLocation(); } catch (_) {}

  // Fallback defaults if nothing selected yet
  if (!document.querySelector("#countries-section:not(.hidden)")) {
    const r = Object.keys(SITE)[0];
    if (!r) return;
    selectRegionSlug(r);
    const c = Object.keys(SITE[r].countries || {})[0];
    if (!c) return;
    selectCountrySlug(r, c);
    const e = Object.keys(SITE[r].countries[c].exchanges || {})[0];
    if (!e) return;
    selectExchangeSlug(r, c, e);
  }
}

// Regions → buttons
function renderRegions() {
  regionsDiv.innerHTML = "";
  const regions = Object.entries(SITE);
  if (!regions.length) {
    regionsDiv.innerHTML = `<div class="text-red-300">No regions found in data/index.json</div>`;
    return;
  }
  for (const [rslug, rdata] of regions) {
    regionsDiv.appendChild(
      button(getLabel(rdata) || rslug, (btn) => {
        clearActive(regionsDiv);
        btn.classList.add(activeStyle);
        selectRegionSlug(rslug);
      })
    );
  }
}

// Region → Countries
function selectRegionSlug(regionSlug) {
  const region = SITE[regionSlug];
  countriesDiv.innerHTML = "";
  countriesSection.classList.remove("hidden");

  const countries = Object.entries(region.countries || {});
  if (!countries.length) {
    countriesDiv.innerHTML = `<div class="text-yellow-300">No countries for ${getLabel(region) || regionSlug}</div>`;
    return;
  }

  for (const [cslug, cdata] of countries) {
    countriesDiv.appendChild(
      button(getLabel(cdata) || cslug, (btn) => {
        clearActive(countriesDiv);
        btn.classList.add(activeStyle);
        selectCountrySlug(regionSlug, cslug);
      }, false)
    );
  }
}

// Country → Exchanges
function selectCountrySlug(regionSlug, countrySlug) {
  const country = SITE[regionSlug].countries[countrySlug];
  exchangesDiv.innerHTML = "";
  exchangesSection.classList.remove("hidden");

  const exchs = Object.entries(country.exchanges || {});
  if (!exchs.length) {
    exchangesDiv.innerHTML = `<div class="text-yellow-300">No exchanges for ${getLabel(country) || countrySlug}</div>`;
    return;
  }

  for (const [eslug, edata] of exchs) {
    exchangesDiv.appendChild(
      button(getLabel(edata) || eslug, (btn) => {
        clearActive(exchangesDiv);
        btn.classList.add(activeStyle);
        selectExchangeSlug(regionSlug, countrySlug, eslug);
      })
    );
  }
}

// Exchange → Stocks table
function selectExchangeSlug(regionSlug, countrySlug, exchangeSlug) {
  const exchange = SITE[regionSlug].countries[countrySlug].exchanges[exchangeSlug];
  stocksDiv.innerHTML = "";
  stocksSection.classList.remove("hidden");

  const rows = exchange.stocks || [];
  if (!rows.length) {
    stocksDiv.innerHTML = `<div class="text-yellow-300">No stocks in ${getLabel(exchange) || exchangeSlug}</div>`;
    return;
  }

  const tbl = document.createElement("table");
  tbl.className = "min-w-full border border-gray-700 divide-y divide-gray-700 text-sm";
  tbl.innerHTML = `
    <thead class="bg-gray-900">
      <tr>
        <th class="px-2 py-1">Symbol</th>
        <th class="px-2 py-1">Name</th>
        <th class="px-2 py-1">Sector</th>
        <th class="px-2 py-1">Open</th>
        <th class="px-2 py-1">High</th>
        <th class="px-2 py-1">Low</th>
        <th class="px-2 py-1">Close</th>
        <th class="px-2 py-1">Signal</th>
      </tr>
    </thead>
    <tbody class="divide-y divide-gray-800"></tbody>
  `;
  const tbody = tbl.querySelector("tbody");

  for (const s of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="px-2 py-1 font-mono">${text(s.symbol)}</td>
      <td class="px-2 py-1">${text(s.name || s.description)}</td>
      <td class="px-2 py-1">${text(s.sector)}</td>
      <td class="px-2 py-1">${fmt(s.open)}</td>
      <td class="px-2 py-1">${fmt(s.high)}</td>
      <td class="px-2 py-1">${fmt(s.low)}</td>
      <td class="px-2 py-1">${fmt(s.close)}</td>
      <td class="px-2 py-1">${text(s.signal)}</td>
    `;
    tbody.appendChild(tr);
  }

  stocksDiv.appendChild(tbl);
}

// Simple geo default (India → Asia-Pacific/India/<first exchange>)
async function autoSelectByLocation() {
  try {
    const r = await fetch("https://ipapi.co/json/", { cache: "no-store" }).then(r => r.json());
    const cname = text(r.country_name).toLowerCase();
    if (!cname) return;
    // find the region that has a matching country slug
    for (const [rslug, rdata] of Object.entries(SITE)) {
      for (const cslug of Object.keys(rdata.countries || {})) {
        if (cslug === slug(cname)) {
          const exchs = Object.keys(rdata.countries[cslug].exchanges || {});
          if (exchs.length) {
            selectRegionSlug(rslug);
            selectCountrySlug(rslug, cslug);
            selectExchangeSlug(rslug, cslug, exchs[0]);
          }
          return;
        }
      }
    }
  } catch (e) {
    console.warn("Geo lookup failed", e);
  }
}

loadSite().catch(err => {
  console.error("Failed to initialize app:", err);
});
