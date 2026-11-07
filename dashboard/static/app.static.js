/* Static (no-backend) Coles Intelligence dashboard — multi-category, fully dynamic.
   Loads data.json once; every filter scopes both the charts/KPIs and the table,
   computed client-side. */
(function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const fmt$ = (v) => (v == null ? "—" : "$" + Number(v).toFixed(2));
  const fmtPct = (v) => (v == null ? "—" : Number(v).toFixed(0) + "%");

  const RED = "#e4002b", palette = ["#e4002b", "#ff6b81", "#2f6fed", "#0a7a3d",
    "#b7791f", "#8e44ad", "#16a085", "#e67e22", "#3498db", "#7f8c8d",
    "#c0392b", "#f39c12", "#1abc9c", "#9b59b6"];

  const charts = {};
  function drawChart(id, cfg) {
    if (charts[id]) charts[id].destroy();
    const el = document.getElementById(id);
    if (el) charts[id] = new Chart(el, cfg);
  }

  function badgeClass(kind) {
    if (kind === "Half price") return "badge half";
    if (kind === "Multi-buy") return "badge multi";
    if (kind === "Regular price") return "badge regular";
    return "badge special";
  }

  let DATA = null;
  let category = "";
  let page = 0, pageSize = 50;

  // ---- membership-scoped set (used for the sub-category option list) -------
  function scopedByAisle(cat) {
    if (!cat) return DATA.products;
    const m = DATA.memberships || {};
    return DATA.products.filter(p => (m[p.sku_id] || []).indexOf(cat) !== -1);
  }

  // ---- full filter set ----------------------------------------------------
  function filteredProducts() {
    const q = ($("#f-search").value || "").trim().toLowerCase();
    const sub = $("#f-subcategory").value, brand = $("#f-brand").value,
          promo = $("#f-promo").value, special = $("#f-special").checked;
    const m = DATA.memberships || {};

    return DATA.products.filter(r => {
      if (category && (m[r.sku_id] || []).indexOf(category) === -1) return false;
      if (sub && r.subcategory !== sub) return false;
      if (brand && r.brand !== brand) return false;
      if (promo && r.promo_kind !== promo) return false;
      if (special && r.promo_kind === "Regular price") return false;
      if (q) {
        const hay = ((r.display_name || "") + " " + (r.brand || "") + " " + (r.description || "")).toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }

  function filteredRows() {
    const sort = $("#f-sort").value;
    const rows = filteredProducts();
    const cmp = {
      price_asc: (a, b) => (a.price_now ?? Infinity) - (b.price_now ?? Infinity),
      price_desc: (a, b) => (b.price_now ?? -Infinity) - (a.price_now ?? -Infinity),
      discount_desc: (a, b) => (b.discount_percent ?? -1) - (a.discount_percent ?? -1),
      unit_asc: (a, b) => (a.unit_price ?? Infinity) - (b.unit_price ?? Infinity),
      name_asc: (a, b) => String(a.display_name || "").localeCompare(String(b.display_name || "")),
    }[sort] || ((a, b) => 0);
    return rows.slice().sort(cmp);
  }

  // ---- aggregation --------------------------------------------------------
  function buildOverview(prods) {
    const n = prods.length;
    const priced = prods.filter(p => p.price_now != null && p.price_now > 0);
    const avg = priced.length ? priced.reduce((a, p) => a + p.price_now, 0) / priced.length : 0;
    const onSpecial = prods.filter(p => p.promo_kind !== "Regular price").length;
    const disc = prods.filter(p => p.discount_percent != null);
    const avgDisc = disc.length ? disc.reduce((a, p) => a + p.discount_percent, 0) / disc.length : 0;
    const savings = prods.reduce((a, p) => a + (p.save_amount || 0), 0);

    const summary = {
      total_skus: n,
      on_special: onSpecial,
      on_special_pct: n ? Math.round(onSpecial / n * 1000) / 10 : 0,
      avg_price: Math.round(avg * 100) / 100,
      avg_price_nonzero: Math.round(avg * 100) / 100,
      min_price: priced.length ? Math.min(...priced.map(p => p.price_now)) : null,
      max_price: priced.length ? Math.max(...priced.map(p => p.price_now)) : null,
      subcategories: new Set(prods.map(p => p.subcategory).filter(Boolean)).size,
      brands: new Set(prods.map(p => p.brand).filter(Boolean)).size,
      avg_discount_pct: Math.round(avgDisc * 100) / 100,
      total_savings: Math.round(savings * 100) / 100,
      scrape_date: DATA.summary.scrape_date,
    };

    const subBy = {};
    prods.forEach(p => {
      if (!p.subcategory) return;
      (subBy[p.subcategory] = subBy[p.subcategory] || []).push(p);
    });
    const subcategories = Object.entries(subBy).map(([name, ps]) => ({
      name, skus: ps.length,
      avg_price: Math.round(ps.reduce((a, p) => a + (p.price_now || 0), 0) / ps.length * 100) / 100,
      on_special: ps.filter(p => p.promo_kind !== "Regular price").length,
    })).sort((a, b) => b.skus - a.skus);

    const promoBy = {};
    prods.forEach(p => { const k = p.promo_kind || "Regular"; promoBy[k] = (promoBy[k] || 0) + 1; });
    const promo = Object.entries(promoBy).map(([kind, count]) => ({ kind, count })).sort((a, b) => b.count - a.count);

    const brandBy = {};
    prods.forEach(p => {
      if (!p.brand) return;
      (brandBy[p.brand] = brandBy[p.brand] || []).push(p);
    });
    const brands = Object.entries(brandBy)
      .map(([name, ps]) => ({ name, skus: ps.length,
        avg_price: Math.round(ps.reduce((a, p) => a + (p.price_now || 0), 0) / ps.length * 100) / 100,
        on_special: ps.filter(p => p.promo_kind !== "Regular price").length }))
      .sort((a, b) => b.skus - a.skus).slice(0, 12);

    const prices = prods.map(p => p.price_now).filter(v => v != null && v >= 0);
    let histogram = [];
    if (prices.length) {
      const bins = 20, lo = Math.min(...prices), hi = Math.max(...prices);
      const width = (hi - lo) / bins || 1;
      const counts = new Array(bins).fill(0);
      prices.forEach(p => counts[Math.min(Math.floor((p - lo) / width), bins - 1)]++);
      histogram = counts.map((count, i) => ({
        label: `$${Math.round(lo + i * width)}–$${Math.round(lo + (i + 1) * width)}`,
        count,
      }));
    }

    return { summary, subcategories, promo, brands, histogram };
  }

  // ---- rendering ----------------------------------------------------------
  function renderOverview() {
    const d = buildOverview(filteredProducts());
    const s = d.summary;
    $("#meta").textContent = `Snapshot ${s.scrape_date || "—"} · ${s.total_skus.toLocaleString()} SKUs${category ? " · " + category : ""}`;
    $("#subtitle").textContent = `Retail pricing & promotional activity — ${category || "All aisles"}`;

    const scope = [];
    if (category) scope.push(category);
    if ($("#f-subcategory").value) scope.push($("#f-subcategory").value);
    if ($("#f-brand").value) scope.push($("#f-brand").value);
    if ($("#f-promo").value) scope.push($("#f-promo").value);
    if ($("#f-special").checked) scope.push("on special");
    if ($("#f-search").value.trim()) scope.push("“" + $("#f-search").value.trim() + "”");
    $("#charts-note").innerHTML = `Charts reflect <strong>${s.total_skus.toLocaleString()}</strong> selected SKUs` +
      (scope.length ? " · " + scope.join(" · ") : "");

    $("#kpi-skus").textContent = s.total_skus.toLocaleString();
    $("#kpi-special").textContent = fmtPct(s.on_special_pct) + ` (${s.on_special.toLocaleString()})`;
    $("#kpi-avg").textContent = fmt$(s.avg_price_nonzero ?? s.avg_price);
    $("#kpi-subs").textContent = s.subcategories;
    $("#kpi-brands").textContent = s.brands;
    $("#kpi-savings").textContent = fmt$(s.total_savings);

    drawChart("chart-hist", {
      type: "bar",
      data: { labels: d.histogram.map(h => h.label),
              datasets: [{ label: "SKUs", data: d.histogram.map(h => h.count),
                           backgroundColor: RED, borderRadius: 4 }] },
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
                { label: "SKUs", data: subs.map(x => x.skus), backgroundColor: RED, borderRadius: 3 },
                { label: "Avg price ($)", data: subs.map(x => x.avg_price),
                  backgroundColor: "#2f6fed", borderRadius: 3, yAxisID: "y1" }] },
      options: { indexAxis: "y",
                 plugins: { legend: { position: "bottom", labels: { boxWidth: 12 } } },
                 scales: { x: { beginAtZero: true, ticks: { precision: 0 } },
                           y1: { position: "right", grid: { drawOnChartArea: false } } } },
    });

    drawChart("chart-brands", {
      type: "bar",
      data: { labels: d.brands.map(b => b.name),
              datasets: [{ label: "SKUs", data: d.brands.map(b => b.skus),
                           backgroundColor: palette, borderRadius: 4 }] },
      options: { plugins: { legend: { display: false } },
                 scales: { x: { ticks: { maxRotation: 70, minRotation: 45, font: { size: 10 } } },
                           y: { beginAtZero: true, ticks: { precision: 0 } } } },
    });

    // populate option lists (sub-category list depends on the aisle only)
    fill($("#f-category"), DATA.categories.map(c => c.name), "All aisles",
         c => `${c} (${DATA.categories.find(x => x.name === c).skus.toLocaleString()})`);
    fill($("#f-subcategory"), subcategoryOptions());
    fill($("#f-brand"), DATA.filters.brands);
    fill($("#f-promo"), DATA.filters.promos);
  }

  function subcategoryOptions() {
    return category
      ? [...new Set(scopedByAisle(category).map(p => p.subcategory).filter(Boolean))]
      : DATA.filters.subcategories;
  }

  function fill(sel, values, allLabel, labelFn) {
    const current = sel.value;
    sel.innerHTML = `<option value="">${allLabel || sel.dataset.all || "All"}</option>`;
    (values || []).forEach(v => {
      const o = document.createElement("option");
      o.value = v; o.textContent = labelFn ? labelFn(v) : v;
      sel.appendChild(o);
    });
    if ([...sel.options].some(o => o.value === current)) sel.value = current;
  }

  function renderTable() {
    const rows = filteredRows();
    const total = rows.length;
    const slice = rows.slice(page * pageSize, (page + 1) * pageSize);
    const tbody = $("#products tbody");
    tbody.innerHTML = "";
    if (!slice.length) {
      tbody.innerHTML = '<tr><td colspan="10" class="empty">No products match.</td></tr>';
    }
    slice.forEach(r => {
      const tr = document.createElement("tr");
      const was = r.price_was && r.price_was > 0 ? `<span class="was">${fmt$(r.price_was)}</span>` : "—";
      const disc = r.discount_percent ? `<span style="color:#0a7a3d">−${fmtPct(r.discount_percent)}</span>` : "—";
      const unit = r.unit_price ? `${fmt$(r.unit_price)}<small>/${r.unit_of_measure || ""}</small>` : "—";
      const img = r.image_url ? `<img class="prod-img" loading="lazy" src="${escapeHtml(r.image_url)}" alt="">` : "";
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
      tbody.appendChild(tr);
    });

    const start = total ? page * pageSize + 1 : 0;
    const end = Math.min((page + 1) * pageSize, total);
    $("#pager-info").textContent = total ? `${start.toLocaleString()}–${end.toLocaleString()} of ${total.toLocaleString()} SKUs` : "0 SKUs";
    $("#prev").disabled = page === 0;
    $("#next").disabled = end >= total;
  }

  function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, c => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  // ---- events -------------------------------------------------------------
  let debounce;
  function scheduleAll() { page = 0; clearTimeout(debounce); debounce = setTimeout(() => { renderOverview(); renderTable(); }, 200); }
  function scheduleTable() { page = 0; clearTimeout(debounce); debounce = setTimeout(renderTable, 200); }

  $("#f-category").addEventListener("change", () => {
    category = $("#f-category").value;
    $("#f-subcategory").value = "";
    page = 0;
    renderOverview();
    renderTable();
  });
  [["#f-subcategory", "change"], ["#f-brand", "change"], ["#f-promo", "change"]]
    .forEach(([s, e]) => $(s).addEventListener(e, scheduleAll));
  $("#f-special").addEventListener("change", scheduleAll);
  $("#f-search").addEventListener("input", scheduleAll);
  $("#f-sort").addEventListener("change", scheduleTable);
  $("#prev").addEventListener("click", () => { page = Math.max(0, page - 1); renderTable(); });
  $("#next").addEventListener("click", () => { page += 1; renderTable(); });

  // ---- boot ---------------------------------------------------------------
  (async function boot() {
    const res = await fetch("data.json");
    DATA = await res.json();
    renderOverview();
    renderTable();
  })().catch(err => {
    document.getElementById("products").querySelector("tbody").innerHTML =
      `<tr><td colspan="10" class="empty">Failed to load data: ${escapeHtml(err.message)}</td></tr>`;
  });
})();
