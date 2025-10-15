// static/app.js
(function () {
  const BASE = (window.SPP_BASE || "").replace(/\/+$/, "");
  const INDEX_URL = window.SPP_INDEX_URL || (BASE + "/static/index.json");

  const $regions = document.getElementById("regions");
  const $countries = document.getElementById("countries");
  const $exchanges = document.getElementById("exchanges");
  const $tableWrap = document.getElementById("stocks_table");

  let SITE = null;
  let sel = { region: null, country: null, exchange: null };

  function a(tag, attrs = {}, children = []) {
    const el = document.createElement(tag);
    Object.entries(attrs).forEach(([k, v]) => {
      if (k === "class") el.className = v;
      else if (k === "html") el.innerHTML = v;
      else el.setAttribute(k, v);
    });
    (Array.isArray(children) ? children : [children])
      .filter(Boolean)
      .forEach(ch => el.appendChild(typeof ch === "string" ? document.createTextNode(ch) : ch));
    return el;
  }

  async function fetchJSON(url) {
    const res = await fetch(url, { cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
    return await res.json();
  }

  function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); }

  function chip(text, active, onclick) {
    const c = a("div", { class: "chip" }, text);
    if (active) c.classList.add("active");
    c.onclick = onclick;
    return c;
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

  function renderRegions() {
    clear($regions);
    SITE.regions.forEach(r => {
      $regions.appendChild(chip(r.name, sel.region && sel.region.slug === r.slug, () => {
        sel.region = r; sel.country = null; sel.exchange = null;
        renderCountries(); renderExchanges(); renderTable(null);
      }));
    });
  }

  function renderCountries() {
    clear($countries);
    if (!sel.region) return;
    sel.region.countries.forEach(c => {
      $countries.appendChild(chip(c.name, sel.country && sel.country.slug === c.slug, () => {
        sel.country = c; sel.exchange = null;
        renderExchanges(); renderTable(null);
      }));
    });
  }

  function renderExchanges() {
    clear($exchanges);
    if (!sel.country) return;
    sel.country.exchanges.forEach(e => {
      $exchanges.appendChild(chip(e.name, sel.exchange && sel.exchange.slug === e.slug, async () => {
        sel.exchange = e;
        await loadAndRenderExchange(sel.region.slug, sel.country.slug, sel.exchange.slug);
      }));
    });
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

  (async function init() {
    try {
      SITE = await fetchJSON(INDEX_URL);
      renderRegions();
      if (SITE.regions && SITE.regions.length) {
        sel.region = SITE.regions[0]; renderCountries();
        if (sel.region.countries && sel.region.countries.length) {
          sel.country = sel.region.countries[0]; renderExchanges();
          if (sel.country.exchanges && sel.country.exchanges.length) {
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
