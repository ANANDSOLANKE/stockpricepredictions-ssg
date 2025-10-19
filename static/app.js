// static/app.js
(function () {
  const BASE = (window.SPP_BASE || "").replace(/\/+$/, "");
  const INDEX_URL = window.SPP_INDEX_URL || (BASE + "/static/index.json");

  // DOM
  const $tableWrap  = document.getElementById("stocks_table");
  const $pickerHost = document.getElementById("markets_picker");

  // State
  let SITE = null;
  let sel = { region: null, country: null, exchange: null };

  // helpers
  function a(tag, attrs = {}, children = []) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "class") el.className = v;
      else if (k === "html") el.innerHTML = v;
      else el.setAttribute(k, v);
    }
    (Array.isArray(children) ? children : [children])
      .filter(Boolean)
      .forEach(ch =>
        el.appendChild(typeof ch === "string" ? document.createTextNode(ch) : ch)
      );
    return el;
  }
  function clear(el){ while (el && el.firstChild) el.removeChild(el.firstChild); }

  async function fetchJSON(url) {
    const res = await fetch(url, { cache: "no-cache" });
    if (!res.ok) throw new Error(`${res.status} ${url}`);
    return await res.json();
  }

  // ----- UI: Picker rows (Regions / Countries / Exchanges) -------------------
  function chip(text, isActive, onClick) {
    const el = a("button", { class: "chip", type: "button" }, text);
    if (isActive) el.classList.add("active");
    el.onclick = onClick;
    return el;
  }

  function makeRow(label, chipsEl) {
    return a("div", { class: "row" }, [
      a("div", { class: "row-title" }, label),
      a("div", { class: "chips" }, chipsEl)
    ]);
  }

  function renderPicker() {
    clear($pickerHost);
    if (!SITE) return;

    // Regions
    const regionChips = SITE.regions.map(r =>
      chip(r.name, sel.region && sel.region.slug === r.slug, () => {
        sel.region = r;
        // default: first country + first exchange
        sel.country = (r.countries && r.countries[0]) || null;
        sel.exchange = sel.country && sel.country.exchanges ? sel.country.exchanges[0] : null;
        renderPicker();
        loadCurrentExchange();
      })
    );

    // Countries (depends on region)
    const countryChips = (sel.region ? sel.region.countries : []).map(c =>
      chip(c.name, sel.country && sel.country.slug === c.slug, () => {
        sel.country = c;
        sel.exchange = (c.exchanges && c.exchanges[0]) || null;
        renderPicker();
        loadCurrentExchange();
      })
    );

    // Exchanges (depends on country)
    const exchangeChips = (sel.country ? sel.country.exchanges : []).map(e =>
      chip(e.name, sel.exchange && sel.exchange.slug === e.slug, () => {
        sel.exchange = e;
        renderPicker();
        loadCurrentExchange();
      })
    );

    $pickerHost.appendChild(makeRow("REGIONS", regionChips));
    $pickerHost.appendChild(makeRow("COUNTRIES", countryChips));
    $pickerHost.appendChild(makeRow("EXCHANGES", exchangeChips));
  }

  // ----- Load exchange data and render table --------------------------------
  function formatNum(x) {
    if (x === null || x === undefined || x === "") return "";
    const n = Number(x);
    if (!isFinite(n)) return "";
    return n.toFixed(2);
  }
  function pctSpan(val) {
    if (val === null || val === undefined || val === "") return document.createTextNode("");
    const n = Number(val);
    if (!isFinite(n)) return document.createTextNode("");
    const cls = n > 0 ? "pct pos" : n < 0 ? "pct neg" : "pct";
    return a("span", { class: cls }, n.toFixed(2) + "%");
  }

  async function loadCurrentExchange() {
    clear($tableWrap);

    if (!sel.exchange || !sel.region || !sel.country) {
      $tableWrap.textContent = "Pick a region → country → exchange";
      return;
    }

    const url = `${BASE}/static/exchanges/${sel.region.slug}/${sel.country.slug}/${sel.exchange.slug}.json`;
    try {
      const data = await fetchJSON(url);
      renderTable(data);
    } catch (e) {
      $tableWrap.textContent = `Failed to load ${url}`;
    }
  }

  function renderTable(data) {
    clear($tableWrap);

    const table = a("table", { class: "table" });
    const thead = a("thead");
    const trh = a("tr");
    ["Symbol","Name","Sector","Open","High","Low","Close","Change%","Signal"]
      .forEach(h => trh.appendChild(a("th", {}, h)));
    thead.appendChild(trh);

    const tbody = a("tbody");
    (data.rows || []).forEach(row => {
      const tr = a("tr");

      const sym = row.symbol || "";
      const name = row.name || sym;
      const sector = row.sector || "";
      const url = row.url || "#";
      const logo = row.logo || "";

      tr.appendChild(a("td", {}, a("a", { href: url }, sym)));

      const nameCell = a("td");
      const link = a("a", { href: url, class: "name-with-logo" });
      if (logo) {
        link.appendChild(a("img", { src: logo, alt: "", class: "logo-ico", loading: "lazy" }));
      }
      link.appendChild(document.createTextNode(name));
      nameCell.appendChild(link);
      tr.appendChild(nameCell);

      tr.appendChild(a("td", {}, sector));
      tr.appendChild(a("td", {}, formatNum(row.open)));
      tr.appendChild(a("td", {}, formatNum(row.high)));
      tr.appendChild(a("td", {}, formatNum(row.low)));
      tr.appendChild(a("td", {}, formatNum(row.close)));
      tr.appendChild(a("td", {}, pctSpan(row.change_percent)));
      tr.appendChild(a("td", {}, a("a", { href: url, class: "btn" }, "AI Prediction")));

      tbody.appendChild(tr);
    });

    table.appendChild(thead);
    table.appendChild(tbody);
    $tableWrap.appendChild(a("div", { class: "table-wrap" }, table));
  }

  // ----- boot ---------------------------------------------------------------
  (async function init() {
    try {
      SITE = await fetchJSON(INDEX_URL);
      // defaults: first region → first country → first exchange
      if (SITE.regions && SITE.regions.length) {
        sel.region = SITE.regions[0] || null;
        sel.country = sel.region && sel.region.countries ? sel.region.countries[0] : null;
        sel.exchange = sel.country && sel.country.exchanges ? sel.country.exchanges[0] : null;
      }
      renderPicker();
      loadCurrentExchange();
    } catch {
      $tableWrap.textContent = "Failed to load site index.";
    }
  })();
})();
