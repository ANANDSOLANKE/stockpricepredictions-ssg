// static/app.js
(() => {
  const $ = (sel) => document.querySelector(sel);
  const BASE = window.SPP_BASE || "";
  const INDEX_URL = window.SPP_INDEX_URL || (BASE + "/static/index.json");

  const elRegions = $("#regions");
  const elCountries = $("#countries");
  const elExchanges = $("#exchanges");
  const elStocksTable = $("#stocks_table");

  // Utility
  const clear = (el) => (el.innerHTML = "");
  const chip = (text, onClick) => {
    const a = document.createElement("button");
    a.className = "chip";
    a.type = "button";
    a.textContent = text;
    a.addEventListener("click", onClick);
    return a;
  };

  // Render functions (ONLY populate the three containers; do not add titles)
  function renderRegions(index) {
    clear(elRegions); clear(elCountries); clear(elExchanges);
    elStocksTable.textContent = "Pick a region → country → exchange";
    (index.regions || []).forEach((r) => {
      elRegions.appendChild(
        chip(r.name, () => renderCountries(r))
      );
    });
  }

  function renderCountries(region) {
    clear(elCountries); clear(elExchanges);
    elStocksTable.textContent = "Pick a country → exchange";
    (region.countries || []).forEach((c) => {
      elCountries.appendChild(
        chip(c.name, () => renderExchanges(region, c))
      );
    });
    // Scroll into view on mobile
    elCountries.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  async function renderExchanges(region, country) {
    clear(elExchanges);
    elStocksTable.textContent = "Pick an exchange to load stocks";
    (country.exchanges || []).forEach((e) => {
      elExchanges.appendChild(
        chip(e.name, () => loadExchangeTable(region, country, e))
      );
    });
    elExchanges.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  async function loadExchangeTable(region, country, exch) {
    // /static/exchanges/<region>/<country>/<exchange>.json
    const url = `${BASE}/static/exchanges/${region.slug}/${country.slug}/${exch.slug}.json`;
    elStocksTable.textContent = "Loading…";

    try {
      const resp = await fetch(url, { cache: "no-store" });
      const data = await resp.json();

      const rows = data.rows || [];
      if (!rows.length) {
        elStocksTable.textContent = "No listings found.";
        return;
      }

      const table = document.createElement("table");
      table.className = "table";
      table.innerHTML = `
        <thead>
          <tr>
            <th>Logo</th>
            <th>Symbol</th>
            <th>Name</th>
            <th>Sector</th>
            <th>Open</th>
            <th>High</th>
            <th>Low</th>
            <th>Close</th>
            <th>Change%</th>
            <th>Signal</th>
          </tr>
        </thead>
        <tbody></tbody>
      `;
      const tb = table.querySelector("tbody");

      rows.forEach((r) => {
        const tr = document.createElement("tr");
        const pct =
          typeof r.change_percent === "number"
            ? r.change_percent.toFixed(2)
            : "";
        const pctClass =
          typeof r.change_percent === "number"
            ? (r.change_percent > 0 ? "pos" : (r.change_percent < 0 ? "neg" : ""))
            : "";

        tr.innerHTML = `
          <td><img src="${r.logo}" alt="" class="logo"></td>
          <td><a href="${r.url}">${r.symbol || ""}</a></td>
          <td><a href="${r.url}">${r.name || ""}</a></td>
          <td>${r.sector || ""}</td>
          <td>${r.open ?? ""}</td>
          <td>${r.high ?? ""}</td>
          <td>${r.low ?? ""}</td>
          <td>${r.close ?? ""}</td>
          <td><span class="pct ${pctClass}">${pct ? pct + "%" : ""}</span></td>
          <td><a class="btn" href="${r.url}">AI Prediction</a></td>
        `;
        tb.appendChild(tr);
      });

      elStocksTable.innerHTML = "";
      elStocksTable.appendChild(table);
      elStocksTable.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (e) {
      console.error(e);
      elStocksTable.textContent = "Failed to load data.";
    }
  }

  // Boot
  (async () => {
    try {
      const resp = await fetch(INDEX_URL, { cache: "no-store" });
      const index = await resp.json();
      renderRegions(index);
    } catch (e) {
      console.error(e);
    }
  })();
})();
