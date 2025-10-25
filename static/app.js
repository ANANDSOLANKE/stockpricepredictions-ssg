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
    if (!elRegions) return; // not on picker page
    clear(elRegions); clear(elCountries); clear(elExchanges);
    if (elStocksTable) elStocksTable.textContent = "Pick a region → country → exchange";
    (index.regions || []).forEach((r) => {
      elRegions.appendChild(
        chip(r.name, () => renderCountries(r))
      );
    });
  }

  function renderCountries(region) {
    clear(elCountries); clear(elExchanges);
    if (elStocksTable) elStocksTable.textContent = "Pick a country → exchange";
    (region.countries || []).forEach((c) => {
      elCountries.appendChild(
        chip(c.name, () => renderExchanges(region, c))
      );
    });
    elCountries.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  async function renderExchanges(region, country) {
    clear(elExchanges);
    if (elStocksTable) elStocksTable.textContent = "Pick an exchange to load stocks";
    (country.exchanges || []).forEach((e) => {
      elExchanges.appendChild(
        chip(e.name, () => loadExchangeTable(region, country, e))
      );
    });
    elExchanges.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  async function loadExchangeTable(region, country, exch) {
    if (!elStocksTable) return;
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

  // Boot (picker/list pages)
  (async () => {
    try {
      if (!elRegions) return; // if we're not on the picker page, skip boot
      const resp = await fetch(INDEX_URL, { cache: "no-store" });
      const index = await resp.json();
      renderRegions(index);
    } catch (e) {
      console.error(e);
    }
  })();

  /* =====================================================
     vExt3 — Prediction page patch (client-side)
     Only runs on /prediction-tomorrow/ pages.
     ===================================================== */
  (function predictionPatch(){
    if (!/\/prediction-tomorrow\/?$/.test(location.pathname)) return;

    // 1) Find the old OHLC pills inside the hero and parse values
    const ohlcEl = document.querySelector('.ohlc');
    const header = document.querySelector('.header') || document.querySelector('.stock-header') || document.querySelector('.card.header');

    function parseOhlc(text){
      if (!text) return null;
      const t = text.replace(/\s+/g,' ').trim();
      // O <num> H <num> L <num> C <num> [Change% <num>]
      const m = t.match(/O\s*([\d.,]+).*?H\s*([\d.,]+).*?L\s*([\d.,]+).*?C\s*([\d.,]+)(?:.*?Change%[:\s]*([-+]?\d+(?:\.\d+)?))?/i);
      return m ? { open:m[1], high:m[2], low:m[3], close:m[4], change: m[5] || null } : null;
    }

    const ohlc = ohlcEl ? parseOhlc(ohlcEl.textContent) : null;

    // 2) Inject price strip under the stock title (once)
    if (header && ohlc && !header.querySelector('.spp-stat-strip')) {
      const strip = document.createElement('div');
      strip.className = 'spp-stat-strip';

      // Try to read a date if the page provides it as a data attribute
      const dateAttr = document.querySelector('[data-ohlc-date]')?.getAttribute('data-ohlc-date');
      const parts = [];
      if (dateAttr) parts.push(`<span><strong>Date:</strong> ${dateAttr}</span><span class="dot">•</span>`);
      parts.push(`<span><strong>Open:</strong> ${ohlc.open}</span><span class="dot">•</span>`);
      parts.push(`<span><strong>High:</strong> ${ohlc.high}</span><span class="dot">•</span>`);
      parts.push(`<span><strong>Low:</strong> ${ohlc.low}</span><span class="dot">•</span>`);
      parts.push(`<span><strong>Close:</strong> ${ohlc.close}</span>`);
      if (ohlc.change != null) parts.push(`<span class="dot">•</span><span><strong>% Change:</strong> ${ohlc.change}%</span>`);

      strip.innerHTML = parts.join('');
      header.appendChild(strip);
    }

    // 3) Ensure the old pills are hidden (CSS also hides them)
    if (ohlcEl) ohlcEl.style.display = 'none';

    // 4) Add animated ▲/▼ arrow in the big signal line
    const sigEl = document.querySelector('.signal');
    if (sigEl && !sigEl.querySelector('.spp-arrow')) {
      const txt = sigEl.textContent.trim().toLowerCase();
      const up = txt.includes('bullish');
      const arrow = document.createElement('span');
      arrow.className = 'spp-arrow ' + (up ? 'up' : 'down');
      arrow.textContent = up ? '▲' : '▼';
      sigEl.prepend(arrow);
    }

    // 5) Optional: change the chip text to "Stock prediction for <date>" if a date is available
    const chip = document.querySelector('.chip');
    const predDate = document.querySelector('[data-pred-date]')?.getAttribute('data-pred-date');
    if (chip && predDate) chip.textContent = `Stock prediction for ${predDate}`;
  })();

})();
