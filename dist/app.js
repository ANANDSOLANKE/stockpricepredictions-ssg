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
  const buildV = window.__BUILD_V__ || Date.now(); // cache-buster to avoid stale logos

  (data.rows || []).forEach(row => {
    const tr = a("tr");
    const sym = (row.symbol || "").toUpperCase();
    const name = row.name || sym;
    const sector = row.sector || "";
    const url = row.url || "#";
    const group = (row.group || row.region || "global").toLowerCase();
    const country = (row.country || "").toLowerCase().replace(/\s+/g, "-");
    const exchange = (row.exchange || "").toLowerCase().replace(/\s+/g, "-");

    // --- Logo paths ---
    // 1️⃣ Prefer new ticker-based logos built by build_logos.py
    const tickerLogo = `${BASE}/logos/_ticker/${group}/${country}/${exchange}/${sym}.png?v=${buildV}`;
    // 2️⃣ Fallback to existing company-slug logo
    const fallbackLogo = row.logo || `${BASE}/logos/${country}/${exchange}/${(row.slug || row.name || "").toLowerCase().replace(/\s+/g, "-")}--600.png?v=${buildV}`;
    // 3️⃣ Final placeholder (generic)
    const placeholderLogo = `${BASE}/logos/placeholder.png?v=${buildV}`;

    tr.appendChild(a("td", {}, a("a", { href: url }, sym)));

    const nameCell = a("td");
    const link = a("a", { href: url, class: "name-with-logo" });

    // <img> with graceful onerror fallback chain
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
