// static/app.js
(function () {
  const BASE = (window.SPP_BASE || "").replace(/\/+$/, "");
  const INDEX_URL = window.SPP_INDEX_URL || (BASE + "/static/index.json");

  // Mount points already in your HTML
  const $regions = document.getElementById("regions");
  const $countries = document.getElementById("countries");
  const $exchanges = document.getElementById("exchanges");
  const $tableWrap = document.getElementById("stocks_table");

  let SITE = null;
  let sel = { region: null, country: null, exchange: null };

  // ---------- small DOM helpers ----------
  function a(tag, attrs = {}, children = []) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") el.className = v;
      else if (k === "html") el.innerHTML = v;
      else el.setAttribute(k, v);
    }
    (Array.isArray(children) ? children : [children])
      .filter(Boolean)
      .forEach(ch => el.appendChild(typeof ch === "string" ? document.createTextNode(ch) : ch));
    return el;
  }
  function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); }

  // A single chip
  function chip(text, active, onclick) {
    const c = a("button", {
      class: "chip" + (active ? " active" : ""),
      type: "button",
      "aria-pressed": active ? "true" : "false"
    }, text);
    c.onclick = onclick;
    return c;
  }

  // A labeled row: title + chip grid
  function renderRow($host, title, items, isActive, onPick) {
    clear($host);
    const row = a("div", { class: "row" });
    row.appendChild(a("div", { class: "row-title" }, title));
    const chips = a("div", { class: "chips" });
    items.forEach(item => {
      chips.appendChild(chip(
        item.name,
        isActive(item),
        () => onPick(item)
      ));
    });
    row.appendChild(chips);
    $host.appendChild(row);
  }

  // ---------- networking ----------
  async function fetchJSON(url) {
    const res = await fetch(url, { cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
    return await res.json();
  }

  // ---------- renderers ----------
  function renderRegions() {
    renderRow(
      $regions,
      "Regions",
      SITE?.regions || [],
      (r) => sel.region && sel.region.slug === r.slug,
      (r) => { sel.region = r; sel.country = null; sel.exchange = null; renderCountries(); renderExchanges(); renderTable(null); }
    );
  }

  function renderCountries() {
    const items = sel.region?.countries || [];
    renderRow(
      $countries,
      "Countries",
      items,
      (c) => sel.country && sel.country.slug === c.slug,
      (c) => { sel.country = c; sel.exchange = null; renderExchanges(); renderTable(null); }
    );
  }

  function renderExchanges() {
    const items = sel.country?.exchanges || [];
    renderRow(
      $exchanges,
      "Exchanges",
      items,
      (e) => sel.exchange && sel.exchange.slug === e.slug,
      async (e) => {
        sel.exchange = e;
        await loadAndRenderExchange(sel.region.slug, sel.country.slug, sel.exchange.slug);
      }
    );
  }

  async function loadAndRenderExchange(rslug, cslug, eslug) {
    const url = `${BASE}/static/exchanges/${rslug}/${cslug}/${eslug}.json`;
    try {
      const data = await fetchJSON(url);
      renderTable(data);
    } catch {
      renderTable(null, `Failed to load ${url}`);
    }
  }

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

  function renderTable(data, errMsg) {
    clear($tableWrap);
    if (errMsg) { $tableWrap.textContent = errMsg; return; }
    if (!data) { $tableWrap.textContent = "Pick a region → country → exchange"; return; }

    const table = a("table", { class: "table" });
    const thead = a("thead");
    const trh = a("tr");
    ["Symbol","Name","Sector","Open","High","Low","Close","Change%","Signal"]
      .forEach(h => trh.appendChild(a("th", {}, h)));
    thead.appendChild(trh);

    const tbody = a("tbody");
    const buildV = window.__BUILD_V__ || Date.now(); // cache-buster for logos

    (data.rows || []).forEach(row => {
      const tr = a("tr");
      const sym = (row.symbol || "").toUpperCase();
      const name = row.name || sym;
      const sector = row.sector || "";
      const url = row.url || "#";

      const group = (row.group || row.region || "global").toLowerCase();
      const country = (row.country || "").toLowerCase().replace(/\s+/g, "-");
      const exchange = (row.exchange || "").toLowerCase().replace(/\s+/g, "-");

      // Prefer ticker-based logo created by the logo sync; fallback to legacy; then placeholder
      const tickerLogo = `${BASE}/logos/_ticker/${group}/${country}/${exchange}/${sym}.png?v=${buildV}`;
      const fallbackLogo = row.logo || `${BASE}/logos/${country}/${exchange}/${(row.slug || row.name || "").toLowerCase().replace(/\s+/g, "-")}--600.png?v=${buildV}`;
      const placeholderLogo = `${BASE}/logos/placeholder.png?v=${buildV}`;

      tr.appendChild(a("td", {}, a("a", { href: url }, sym)));

      const nameCell = a("td");
      const link = a("a", { href: url, class: "name-with-logo" });
      const img = a("img", {
        src: tickerLogo,
        alt: "",
        class: "logo-ico",
        loading: "lazy",
        onerror: `this.onerror=null;this.src='${fallbackLogo}';this.onerror=function(){this.onerror=null;this.src='${placeholderLogo}';}`
      });
      link.appendChild(img);
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

  // ---------- init ----------
  (async function init() {
    try {
      SITE = await fetchJSON(INDEX_URL);
      renderRegions();
      if (SITE.regions?.length) {
        sel.region = SITE.regions[0]; renderCountries();
        if (sel.region.countries?.length) {
          sel.country = sel.region.countries[0]; renderExchanges();
          if (sel.country.exchanges?.length) {
            sel.exchange = sel.country.exchanges[0];
            await loadAndRenderExchange(sel.region.slug, sel.country.slug, sel.exchange.slug);
          }
        }
      }
    } catch {
      $tableWrap.textContent = "Failed to load site index.";
    }
  })();
})();
