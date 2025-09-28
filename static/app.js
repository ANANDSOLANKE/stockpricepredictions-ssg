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

let SITE = null;

// Button styles
const clsBtn =
  "px-4 py-2 rounded-xl shadow bg-gradient-to-r from-indigo-600 to-blue-600 hover:from-indigo-500 hover:to-blue-500 text-white transition";
const clsBtnGhost =
  "px-4 py-2 rounded-xl bg-gray-800 hover:bg-gray-700 text-white transition";
const activeStyle = "ring-2 ring-white/60";

// Helpers
const slug = (s) =>
  (s || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
function clearActive(parent) {
  [...parent.querySelectorAll("button")].forEach((b) =>
    b.classList.remove(activeStyle)
  );
}
function button(txt, onClick, solid = true) {
  const b = document.createElement("button");
  b.className = solid ? clsBtn : clsBtnGhost;
  b.textContent = txt;
  b.onclick = () => onClick(b);
  return b;
}
function fmt(x) {
  return x == null || isNaN(x) ? "" : Number(x).toFixed(2);
}

// Load site JSON
async function loadSite() {
  const res = await fetch(`${RUNTIME_BASE}/data/index.json`, {
    cache: "no-store",
  });
  const j = await res.json();
  SITE = j.data;

  renderRegions();

  // Try auto-select by location
  await autoSelectByLocation().catch(() => {});

  // Fallback default selection
  if (!document.querySelector("#countries-section:not(.hidden)")) {
    const r = "asia-pacific"; // default region
    selectRegionSlug(r);
    const c = "india"; // default country
    selectCountrySlug(r, c);
    const e = Object.keys(SITE[r].countries[c].exchanges)[0];
    selectExchangeSlug(r, c, e);
  }
}

// Render Regions
function renderRegions() {
  regionsDiv.innerHTML = "";
  for (const r of Object.keys(SITE)) {
    regionsDiv.appendChild(
      button(SITE[r].label, (b) => {
        clearActive(regionsDiv);
        b.classList.add(activeStyle);
        selectRegionSlug(r);
      })
    );
  }
}

// Region → Countries
function selectRegionSlug(regionSlug) {
  const region = SITE[regionSlug];
  countriesDiv.innerHTML = "";
  countriesSection.classList.remove("hidden");
  for (const c of Object.keys(region.countries)) {
    countriesDiv.appendChild(
      button(region.countries[c].label, (b) => {
        clearActive(countriesDiv);
        b.classList.add(activeStyle);
        selectCountrySlug(regionSlug, c);
      }, false)
    );
  }
}

// Country → Exchanges
function selectCountrySlug(regionSlug, countrySlug) {
  const country = SITE[regionSlug].countries[countrySlug];
  exchangesDiv.innerHTML = "";
  exchangesSection.classList.remove("hidden");
  for (const e of Object.keys(country.exchanges)) {
    exchangesDiv.appendChild(
      button(country.exchanges[e].label, (b) => {
        clearActive(exchangesDiv);
        b.classList.add(activeStyle);
        selectExchangeSlug(regionSlug, countrySlug, e);
      })
    );
  }
}

// Exchange → Stocks
function selectExchangeSlug(regionSlug, countrySlug, exchangeSlug) {
  const exchange =
    SITE[regionSlug].countries[countrySlug].exchanges[exchangeSlug];
  stocksDiv.innerHTML = "";
  stocksSection.classList.remove("hidden");

  const tbl = document.createElement("table");
  tbl.className =
    "min-w-full border border-gray-700 divide-y divide-gray-700 text-sm";
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

  for (const s of exchange.stocks) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="px-2 py-1 font-mono">${s.symbol}</td>
      <td class="px-2 py-1">${s.description}</td>
      <td class="px-2 py-1">${s.sector || ""}</td>
      <td class="px-2 py-1">${fmt(s.open)}</td>
      <td class="px-2 py-1">${fmt(s.high)}</td>
      <td class="px-2 py-1">${fmt(s.low)}</td>
      <td class="px-2 py-1">${fmt(s.close)}</td>
      <td class="px-2 py-1">${s.signal || ""}</td>
    `;
    tbody.appendChild(tr);
  }

  stocksDiv.appendChild(tbl);
}

// Try to auto-select region/country by IP (very basic)
async function autoSelectByLocation() {
  try {
    const res = await fetch("https://ipapi.co/json/");
    const j = await res.json();
    if (j && j.country_name && j.country_name.toLowerCase() === "india") {
      selectRegionSlug("asia-pacific");
      selectCountrySlug("asia-pacific", "india");
      const e = Object.keys(
        SITE["asia-pacific"].countries["india"].exchanges
      )[0];
      selectExchangeSlug("asia-pacific", "india", e);
    }
  } catch (e) {
    console.warn("Location detection failed", e);
  }
}

// Start
loadSite().catch((e) => {
  console.error("Failed to load site:", e);
});
