/* Coles Intelligence dashboard client — multi-category, fully dynamic charts.
   Every filter (aisle, sub-category, brand, promo, on-special, search) scopes
   BOTH the charts/KPIs and the product table. */
(function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const fmt$ = (v) => (v == null ? "—" : "$" + Number(v).toFixed(2));
  const fmtPct = (v) => (v == null ? "—" : Number(v).toFixed(0) + "%");
  const els = {
    meta: $("#meta"),
    subtitle: $("#subtitle"),
    kpiSkus: $("#kpi-skus"), kpiSpecial: $("#kpi-special"), kpiAvg: $("#kpi-avg"),
    kpiSubs: $("#kpi-subs"), kpiBrands: $("#kpi-brands"), kpiSavings: $("#kpi-savings"),
    fCat: $("#f-category"), fSub: $("#f-subcategory"), fBrand: $("#f-brand"),
    fPromo: $("#f-promo"), fSpecial: $("#f-special"), fSearch: $("#f-search"),
    fSort: $("#f-sort"), tbody: $("#products tbody"), pagerInfo: $("#pager-info"),
    prev: $("#prev"), next: $("#next"), chartsNote: $("#charts-note"),
  };

  let category = "";   // aisle filter

  const charts = {};
  function drawChart(id, cfg) {
    if (charts[id]) charts[id].destroy();
    const el = document.getElementById(id);
    if (el) charts[id] = new Chart(el, cfg);
  }

  const GREEN = "#78be20", palette = ["#78be20", "#9ccc65", "#2f6fed", "#0a7a3d",
    "#b7791f", "#8e44ad", "#16a085", "#e67e22", "#3498db", "#7f8c8d",
    "#c0392b", "#f39c12", "#1abc9c", "#9b59b6"];

  function badgeClass(kind) {
    if (kind === "Half price") return "badge half";
    if (kind === "Multi-buy") return "badge multi";
    if (kind === "Regular price") return "badge regular";
    return "badge special";
  }

  function currentFilters() {
    const f = {};
    if (category) f.category = category;
    if (els.fSub.value) f.subcategory = els.fSub.value;
    if (els.fBrand.value) f.brand = els.fBrand.value;
    if (els.fPromo.value) f.promo = els.fPromo.value;
    if (els.fSpecial.checked) f.on_special = "1";
    if (els.fSearch.value.trim()) f.search = els.fSearch.value.trim();
    return f;
  }

  function queryString(filters) {
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(filters)) p.set(k, v);
    return p.toString();
  }

  // ---- overview (charts + KPIs, scoped to current filters) ----------------
  async function loadOverview() {
    const q = queryString(currentFilters());
    const res = await fetch("/api/overview?" + q);
    const d = await res.json();
    const s = d.summary;
    els.meta.textContent = `Snapshot ${s.scrape_date || "—"} · ${s.total_skus || 0} SKUs${category ? " · " + category : ""}`;
    els.subtitle.textContent = `Retail pricing & promotional activity — ${category || "All aisles"}`;

    // visible note tying the charts to the current catalogue selection
    const scope = [];
    if (category) scope.push(category);
    if (els.fSub.value) scope.push(els.fSub.value);
    if (els.fBrand.value) scope.push(els.fBrand.value);
    if (els.fPromo.value) scope.push(els.fPromo.value);
    if (els.fSpecial.checked) scope.push("on special");
    if (els.fSearch.value.trim()) scope.push("“" + els.fSearch.value.trim() + "”");
    els.chartsNote.innerHTML = `Charts reflect <strong>${(s.total_skus ?? 0).toLocaleString()}</strong> selected SKUs` +
      (scope.length ? " · " + scope.join(" · ") : "");

    els.kpiSkus.textContent = (s.total_skus ?? 0).toLocaleString();
    els.kpiSpecial.textContent = fmtPct(s.on_special_pct) + ` (${(s.on_special ?? 0).toLocaleString()})`;
    els.kpiAvg.textContent = fmt$(s.avg_price_nonzero ?? s.avg_price);
    els.kpiSubs.textContent = s.subcategories ?? 0;
    els.kpiBrands.textContent = s.brands ?? 0;
    els.kpiSavings.textContent = fmt$(s.total_savings);

    drawChart("chart-hist", {
      type: "bar",
      data: { labels: d.histogram.map(h => h.label),
              datasets: [{ label: "SKUs", data: d.histogram.map(h => h.count),
                           backgroundColor: GREEN, borderRadius: 4 }] },
      options: { plugins: { legend: { display: false } },
                 scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } },
    });

    drawChart("chart-promo", {
      type: "doughnut",
      data: { labels: d.promo.map(p => p.kind),
              datasets: [{ data: d.promo.map(p => p.count), backgroundColor: palette }] },
      options: { plugins: { legend: { position: "bottom", labels: { boxWidth: 12 } } } },
    });

    const subs = d.subcategories.slice(0, 16);
    drawChart("chart-subs", {
      type: "bar",
      data: { labels: subs.map(x => x.name),
              datasets: [
                { label: "SKUs", data: subs.map(x => x.skus), backgroundColor: GREEN, borderRadius: 3 },
                { label: "Avg price ($)", data: subs.map(x => x.avg_price),
                  backgroundColor: "#2f6fed", borderRadius: 3, yAxisID: "y1" }] },
      options: { indexAxis: "y",
                 plugins: { legend: { position: "bottom", labels: { boxWidth: 12 } } },
                 scales: { x: { beginAtZero: true, ticks: { precision: 0 } },
                           y1: { position: "right", grid: { drawOnChartArea: false } } } },
    });

    const brands = d.brands.slice(0, 12);
    drawChart("chart-brands", {
      type: "bar",
      data: { labels: brands.map(b => b.name),
              datasets: [{ label: "SKUs", data: brands.map(b => b.skus),
                           backgroundColor: palette, borderRadius: 4 }] },
      options: { plugins: { legend: { display: false } },
                 scales: { x: { ticks: { maxRotation: 70, minRotation: 45, font: { size: 10 } } },
                           y: { beginAtZero: true, ticks: { precision: 0 } } } },
    });

    // global option lists (aisle / brand / promo) — sub-category is handled separately
    fillAisles(d.categories);
    fill(els.fBrand, d.filters.brands);
    fill(els.fPromo, d.filters.promos);
  }

  function fillAisles(cats) {
    const current = els.fCat.value;
    els.fCat.innerHTML = '<option value="">All aisles</option>';
    (cats || []).forEach(c => {
      const o = document.createElement("option");
      o.value = c.name;
      o.textContent = `${c.name} (${c.skus.toLocaleString()})`;
      els.fCat.appendChild(o);
    });
    if ([...els.fCat.options].some(o => o.value === current)) els.fCat.value = current;
  }

  // sub-category options depend on the selected aisle only
  async function updateSubcategoryOptions() {
    const q = category ? "?category=" + encodeURIComponent(category) : "";
    const res = await fetch("/api/overview" + q);
    const d = await res.json();
    const list = category
      ? [...new Set((d.subcategories || []).map(x => x.name))]
      : (d.filters.subcategories || []);
    fill(els.fSub, list);
  }

  function fill(sel, values) {
    const current = sel.value;
    sel.innerHTML = '<option value="">' + (sel.dataset.all || "All") + "</option>";
    (values || []).forEach(v => {
      const o = document.createElement("option");
      o.value = v; o.textContent = v;
      sel.appendChild(o);
    });
    if ([...sel.options].some(o => o.value === current)) sel.value = current;
  }

  // ---- products -----------------------------------------------------------
  let page = 0, pageSize = 50;

  async function loadProducts() {
    const f = currentFilters();
    f.limit = String(pageSize);
    f.offset = String(page * pageSize);
    f.sort = els.fSort.value;

    const res = await fetch("/api/products?" + queryString(f));
    const d = await res.json();
    const total = d.total;

    els.tbody.innerHTML = "";
    if (!d.rows.length) {
      els.tbody.innerHTML = '<tr><td colspan="10" class="empty">No products match.</td></tr>';
    }
    d.rows.forEach(r => {
      const tr = document.createElement("tr");
      const was = r.price_was && r.price_was > 0 ? `<span class="was">${fmt$(r.price_was)}</span>` : "—";
      const disc = r.discount_percent ? `<span style="color:#0a7a3d">−${fmtPct(r.discount_percent)}</span>` : "—";
      const unit = r.unit_price ? `${fmt$(r.unit_price)}<small>/${r.unit_of_measure || ""}</small>` : "—";
      const img = r.image_url
        ? `<img class="prod-img" loading="lazy" src="${escapeHtml(r.image_url)}" alt="">`
        : "";
      const name = r.product_url
        ? `<a href="${escapeHtml(r.product_url)}" target="_blank" rel="noopener">${escapeHtml(r.display_name)}</a>`
        : escapeHtml(r.display_name);
      tr.innerHTML = `
        <td class="prod">${img}${name}</td>
        <td>${escapeHtml(r.category || "—")}</td>
        <td>${escapeHtml(r.brand || "—")}</td>
        <td>${escapeHtml(r.subcategory || "—")}</td>
        <td class="num now">${fmt$(r.price_now)}</td>
        <td class="num">${was}</td>
        <td class="num">${disc}</td>
        <td class="num">${unit}</td>
        <td><span class="${badgeClass(r.promo_kind)}">${escapeHtml(r.promo_kind || "Regular")}</span></td>
        <td class="${r.available ? "avail" : "avail no"}">${r.available ? r.availability_type || "In stock" : "Unavailable"}</td>`;
      els.tbody.appendChild(tr);
    });

    const start = total ? page * pageSize + 1 : 0;
    const end = Math.min((page + 1) * pageSize, total);
    els.pagerInfo.textContent = total ? `${start.toLocaleString()}–${end.toLocaleString()} of ${total.toLocaleString()} SKUs` : "0 SKUs";
    els.prev.disabled = page === 0;
    els.next.disabled = end >= total;
  }

  function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, c => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  // ---- events -------------------------------------------------------------
  let debounce;
  function reloadAll() {
    page = 0;
    clearTimeout(debounce);
    debounce = setTimeout(() => { loadOverview(); loadProducts(); }, 200);
  }
  function reloadProducts() {
    page = 0;
    clearTimeout(debounce);
    debounce = setTimeout(loadProducts, 200);
  }

  els.fCat.addEventListener("change", () => {
    category = els.fCat.value;
    els.fSub.value = "";
    page = 0;
    updateSubcategoryOptions();
    loadOverview();
    loadProducts();
  });
  [els.fSub, els.fBrand, els.fPromo].forEach(el => el.addEventListener("change", reloadAll));
  els.fSpecial.addEventListener("change", reloadAll);
  els.fSearch.addEventListener("input", reloadAll);
  els.fSort.addEventListener("change", reloadProducts);
  els.prev.addEventListener("click", () => { page = Math.max(0, page - 1); loadProducts(); });
  els.next.addEventListener("click", () => { page += 1; loadProducts(); });

  // ---- boot ---------------------------------------------------------------
  (async function boot() {
    await loadOverview();
    await updateSubcategoryOptions();
    await loadProducts();
  })().catch(err => {
    els.tbody.innerHTML = `<tr><td colspan="10" class="empty">Failed to load data: ${escapeHtml(err.message)}</td></tr>`;
  });
})();
