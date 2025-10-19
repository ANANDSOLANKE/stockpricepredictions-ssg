// static/app.js (robust base detection + compact labeled picker)
(function () {
  // --- Robust base detection (works on GitHub Pages subpaths) ---
  function detectRootFromScript() {
    // Find this script tag's src
    var scripts = document.getElementsByTagName('script');
    var me = scripts[scripts.length - 1];
    var src = (me && me.src) || '';
    // e.g. https://domain/path/static/app.js?v=123 -> static dir
    var staticUrl = src.replace(/\/app\.js(?:\?.*)?$/, '/');
    // Remove trailing "static/"
    var root = staticUrl.replace(/static\/?$/, '');
    // Ensure trailing slash
    if (!/\/$/.test(root)) root += '/';
    return root;
  }

  var ROOT = (window.SPP_BASE && String(window.SPP_BASE)) || detectRootFromScript();
  var INDEX_URL = (window.SPP_INDEX_URL && String(window.SPP_INDEX_URL)) || (ROOT + 'static/index.json');

  // --- DOM helpers ---
  function a(tag, attrs, children) {
    var el = document.createElement(tag);
    attrs = attrs || {};
    Object.keys(attrs).forEach(function (k) {
      if (k === 'class') el.className = attrs[k];
      else if (k === 'html') el.innerHTML = attrs[k];
      else el.setAttribute(k, attrs[k]);
    });
    (Array.isArray(children) ? children : (children != null ? [children] : []))
      .forEach(function (ch) { el.appendChild(typeof ch === 'string' ? document.createTextNode(ch) : ch); });
    return el;
  }
  function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); }

  // --- small utils ---
  function formatNum(x) {
    if (x === null || x === undefined || x === '') return '';
    var n = Number(x); if (!isFinite(n)) return ''; return n.toFixed(2);
  }
  function pctSpan(val) {
    if (val === null || val === undefined || val === '') return document.createTextNode('');
    var n = Number(val); if (!isFinite(n)) return document.createTextNode('');
    var cls = n > 0 ? 'pct pos' : n < 0 ? 'pct neg' : 'pct';
    return a('span', { class: cls }, n.toFixed(2) + '%');
  }
  function chip(text, active, onclick) {
    var c = a('button', { class: 'chip', type: 'button' }, text);
    if (active) c.classList.add('active');
    c.addEventListener('click', onclick);
    return c;
  }

  // --- data fetch ---
  function fetchJSON(url) {
    return fetch(url, { cache: 'no-cache' }).then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status + ' for ' + url);
      return res.json();
    });
  }

  // --- state ---
  var SITE = null;
  var sel = { region: null, country: null, exchange: null };

  // --- rendering the compact labeled picker ---
  var $picker = document.getElementById('markets_picker');
  var $tableWrap = document.getElementById('stocks_table');

  function section(title, items) {
    var row = a('div', { class: 'row' });
    var left = a('div', { class: 'row-title' }, title.toUpperCase());
    var right = a('div', { class: 'chips' });
    items.forEach(function (el) { right.appendChild(el); });
    row.appendChild(left);
    row.appendChild(right);
    return row;
  }

  function renderPicker() {
    clear($picker);
    if (!SITE) return;

    var regionChips = SITE.regions.map(function (r) {
      return chip(r.name, sel.region && sel.region.slug === r.slug, function () {
        sel.region = r; sel.country = null; sel.exchange = null;
        renderPicker(); renderTable(null);
      });
    });

    var countryChips = (sel.region ? sel.region.countries : []).map(function (c) {
      return chip(c.name, sel.country && sel.country.slug === c.slug, function () {
        sel.country = c; sel.exchange = null;
        renderPicker(); renderTable(null);
      });
    });

    var exchangeChips = (sel.country ? sel.country.exchanges : []).map(function (e) {
      return chip(e.name, sel.exchange && sel.exchange.slug === e.slug, function () {
        sel.exchange = e;
        loadAndRenderExchange(sel.region.slug, sel.country.slug, sel.exchange.slug);
      });
    });

    $picker.appendChild(section('Regions', regionChips));
    $picker.appendChild(section('Countries', countryChips));
    $picker.appendChild(section('Exchanges', exchangeChips));
  }

  function renderTable(data, err) {
    clear($tableWrap);
    if (err) { $tableWrap.textContent = err; return; }
    if (!data) { return; }

    var table = a('table', { class: 'table' });
    var thead = a('thead');
    var trh = a('tr');
    ['Symbol','Name','Sector','Open','High','Low','Close','Change%','Signal']
      .forEach(function (h) { trh.appendChild(a('th', {}, h)); });
    thead.appendChild(trh);

    var tbody = a('tbody');
    (data.rows || []).forEach(function (row) {
      var tr = a('tr');
      var sym = row.symbol || '';
      var name = row.name || sym;
      var sector = row.sector || '';
      var url = row.url || '#';
      var logo = row.logo || '';

      tr.appendChild(a('td', {}, a('a', { href: url }, sym)));

      var nameCell = a('td');
      var link = a('a', { href: url, class: 'name-with-logo' });
      if (logo) link.appendChild(a('img', { src: logo, alt: '', class: 'logo-ico', loading: 'lazy' }));
      link.appendChild(document.createTextNode(name));
      nameCell.appendChild(link);
      tr.appendChild(nameCell);

      tr.appendChild(a('td', {}, sector));
      tr.appendChild(a('td', {}, formatNum(row.open)));
      tr.appendChild(a('td', {}, formatNum(row.high)));
      tr.appendChild(a('td', {}, formatNum(row.low)));
      tr.appendChild(a('td', {}, formatNum(row.close)));
      tr.appendChild(a('td', {}, pctSpan(row.change_percent)));
      tr.appendChild(a('td', {}, a('a', { href: url, class: 'btn' }, 'AI Prediction')));
      tbody.appendChild(tr);
    });

    table.appendChild(thead);
    table.appendChild(tbody);
    $tableWrap.appendChild(a('div', { class: 'table-wrap' }, table));
  }

  function loadAndRenderExchange(rslug, cslug, eslug) {
    var url = ROOT + 'static/exchanges/' + rslug + '/' + cslug + '/' + eslug + '.json';
    fetchJSON(url).then(function (data) {
      renderTable(data);
    }).catch(function () {
      renderTable(null, 'Failed to load ' + url);
    });
  }

  // --- init ---
  (function init() {
    fetchJSON(INDEX_URL).then(function (site) {
      SITE = site;
      // choose first by default
      if (SITE.regions && SITE.regions.length) {
        sel.region = SITE.regions[0];
        if (sel.region.countries && sel.region.countries.length) {
          sel.country = sel.region.countries[0];
          if (sel.country.exchanges && sel.country.exchanges.length) {
            sel.exchange = sel.country.exchanges[0];
            loadAndRenderExchange(sel.region.slug, sel.country.slug, sel.exchange.slug);
          }
        }
      }
      renderPicker();
    }).catch(function () {
      clear($picker);
      $tableWrap.textContent = 'Failed to load site index.';
    });
  })();
})();
