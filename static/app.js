   /* Minimal drilldown UI with smart default based on browser time zone */
(function () {
  const $ = (sel) => document.querySelector(sel);
  const regionsEl = $("#regions");
  const countriesEl = $("#countries");
  const exchangesEl = $("#exchanges");
  const tableEl = $("#stocks_table");

  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  // very simple mapping → default region/country guess
  const tzDefaults = [
    { match: /^Asia\/Kolkata/, region: "Asia - Pacific", country: "India" },
    { match: /^Australia\//, region: "Asia - Pacific", country: "Australia" },
    { match: /^Asia\/(Tokyo|Seoul)/, region: "Asia - Pacific", country: "Japan" },
    { match: /^Europe\//, region: "Europe", country: "United Kingdom" },
    { match: /^America\/(New|Los|Chicago|Toronto)/, region: "North America", country: "USA" },
  ];

  const humanToSlug = (name) => name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

  function chip(label, onClick, url) {
    const a = document.createElement("a");
    a.className = "chip";
    a.textContent = label;
    a.href = url || "javascript:void(0)";
    if (onClick) a.addEventListener("click", (e) => { e.preventDefault(); onClick(); });
    return a;
  }

  function renderTable(rows) {
    if (!rows || !rows.length) {
      tableEl.innerHTML = "No stocks found for this exchange.";
      return;
    }
    const head = `
      <thead><tr>
        <th>Symbol</th><th>Name</th><th>Sector</th>
        <th>Open</th><th>High</th><th>Low</th><th>Close</th><th>Signal</th>
      </tr></thead>`;
    const body = rows.map(r => `
      <tr>
        <td><a href="${r.url}">${r.symbol}</a></td>
        <td><a href="${r.url}">${r.name}</a></td>
        <td>${r.sector || ""}</td>
        <td>${r.open ?? ""}</td>
        <td>${r.high ?? ""}</td>
        <td>${r.low ?? ""}</td>
        <td>${r.close ?? ""}</td>
        <td>${r.signal || ""}</td>
      </tr>`).join("");
    tableEl.innerHTML = `<table class="table">${head}<tbody>${body}</tbody></table>`;
  }

  function loadExchangeJSON(regionSlug, countrySlug, exchSlug) {
    const url = `${location.origin}${location.pathname.replace(/\/$/, '')}/static/exchanges/${regionSlug}/${countrySlug}/${exchSlug}.json`;
    fetch(url).then(r => r.json()).then(data => {
      renderTable(data.rows || []);
    }).catch(() => {
      tableEl.innerHTML = "Could not load stocks for this exchange.";
    });
  }

  function renderExchanges(region, country) {
    exchangesEl.innerHTML = "";
    tableEl.innerHTML = "Pick an exchange.";
    (country.exchanges || []).forEach(ex => {
      const rSlug = humanToSlug(region.name);
      const cSlug = country.slug;
      const eSlug = ex.slug;
      exchangesEl.appendChild(chip(ex.name, () => {
        loadExchangeJSON(rSlug, cSlug, eSlug);
      }, ex.url));
    });
  }

  function renderCountries(region, all) {
    countriesEl.innerHTML = "";
    exchangesEl.innerHTML = "";
    tableEl.innerHTML = "Pick a country.";
    (region.countries || []).forEach(c => {
      const link = c.url;
      countriesEl.appendChild(chip(c.name, () => {
        renderExchanges(region, c);
      }, link));
    });

    // Preselect default country within selected region, if time zone implies it
    const tzHit = tzDefaults.find(x => x.match.test(tz));
    if (tzHit && tzHit.region === region.name) {
      const c = (region.countries || []).find(x => x.name.toLowerCase() === (tzHit.country || "").toLowerCase());
      if (c) renderExchanges(region, c);
    }
  }

  function renderRegions(all) {
    regionsEl.innerHTML = "";
    (all.regions || []).forEach(r => {
      regionsEl.appendChild(chip(r.name, () => renderCountries(r, all), r.url));
    });

    // Smart default region selection
    const tzHit = tzDefaults.find(x => x.match.test(tz));
    if (tzHit) {
      const r = (all.regions || []).find(x => x.name === tzHit.region);
      if (r) renderCountries(r, all);
    }
  }

  // boot
  fetch(window.SPP_INDEX_URL).then(r => r.json()).then(data => {
    renderRegions(data);
  }).catch(() => {
    regionsEl.innerHTML = "Could not load regions.";
  });
})();
