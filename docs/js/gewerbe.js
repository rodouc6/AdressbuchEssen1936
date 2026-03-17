/* gewerbe.js – Gewerbeatlas: Explorativer Kartenzugang zu Gewerbe (Kat. III) */

(function () {
  "use strict";

  // ── Hamburger-Menü ──────────────────────────────────────────────────────
  document.querySelector(".nav-toggle")?.addEventListener("click", function () {
    document.querySelector(".nav-links")?.classList.toggle("open");
  });

  // ── State ──────────────────────────────────────────────────────────────

  let kategorien = [];
  let allFeatures = [];
  let activeKategorie = null;
  let activeBranche = null;
  let popup = null;
  let historicalLayerVisible = true;
  let searchTimer = null;

  // ── Karte initialisieren ───────────────────────────────────────────────

  const map = new maplibregl.Map({
    container: "gewerbe-map",
    style: "https://tiles.openfreemap.org/styles/liberty",
    center: [7.0177, 51.4556],
    zoom: 12,
    minZoom: 9,
    maxZoom: 18,
  });

  map.addControl(new maplibregl.NavigationControl(), "top-right");
  map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");

  // ── Historischer Stadtplan (ArcGIS) ────────────────────────────────────

  const ARCGIS_EXPORT =
    "https://geo.essen.de/arcgis/rest/services/historischerverein/Stadtplan_1935/MapServer/export";

  function arcGISUrl(bounds, w, h) {
    const p = new URLSearchParams({
      bbox: `${bounds.getWest()},${bounds.getSouth()},${bounds.getEast()},${bounds.getNorth()}`,
      bboxSR: "4326", imageSR: "4326",
      size: `${Math.round(w)},${Math.round(h)}`,
      format: "png32", transparent: "true", f: "image",
    });
    return `${ARCGIS_EXPORT}?${p}`;
  }

  function boundsToCoords(b) {
    return [
      [b.getWest(), b.getNorth()],
      [b.getEast(), b.getNorth()],
      [b.getEast(), b.getSouth()],
      [b.getWest(), b.getSouth()],
    ];
  }

  function addHistoricalLayer() {
    const bounds = map.getBounds();
    const canvas = map.getCanvas();
    map.addSource("stadtplan-1935", {
      type: "image",
      url: arcGISUrl(bounds, canvas.width, canvas.height),
      coordinates: boundsToCoords(bounds),
    });
    map.addLayer({
      id: "stadtplan-1935-layer",
      type: "raster",
      source: "stadtplan-1935",
      paint: { "raster-opacity": 0.7, "raster-fade-duration": 200 },
    });
    setTimeout(() => map.on("moveend", refreshHistoricalLayer), 2000);
  }

  let _refreshTimer = null;
  function refreshHistoricalLayer() {
    clearTimeout(_refreshTimer);
    _refreshTimer = setTimeout(() => {
      if (!historicalLayerVisible) return;
      const src = map.getSource("stadtplan-1935");
      if (!src) return;
      const bounds = map.getBounds();
      const canvas = map.getCanvas();
      try {
        src.updateImage({
          url: arcGISUrl(bounds, canvas.width, canvas.height),
          coordinates: boundsToCoords(bounds),
        });
      } catch { /* ignore */ }
    }, 200);
  }

  // ── HTML-Escape ────────────────────────────────────────────────────────

  function esc(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // ── Daten laden ────────────────────────────────────────────────────────

  async function loadData() {
    const [geojsonResp, katResp] = await Promise.all([
      fetch("data/gewerbe.geojson"),
      fetch("data/gewerbe_kategorien.json"),
    ]);
    if (!geojsonResp.ok || !katResp.ok) throw new Error("Fehler beim Laden");
    const geojson = await geojsonResp.json();
    const katData = await katResp.json();
    return { geojson, kategorien: katData.kategorien };
  }

  // ── Farb-Lookup ────────────────────────────────────────────────────────

  let katFarbeMap = {};   // kategorie-id → farbe
  let katLabelMap = {};   // kategorie-id → label

  function buildKatMaps() {
    for (const k of kategorien) {
      katFarbeMap[k.id] = k.farbe;
      katLabelMap[k.id] = k.label;
    }
  }

  // ── Chips rendern (Desktop) ────────────────────────────────────────────

  function renderChips() {
    const container = document.getElementById("gewerbe-chips");
    container.innerHTML = "";

    // "Alle" chip
    const allChip = document.createElement("button");
    allChip.className = "gewerbe-chip" + (activeKategorie === null ? " active" : "");
    allChip.style.setProperty("--chip-color", "var(--primary)");
    allChip.innerHTML = `<span class="gewerbe-chip-label">Alle</span>`;
    allChip.addEventListener("click", () => selectKategorie(null));
    container.appendChild(allChip);

    for (const k of kategorien) {
      const chip = document.createElement("button");
      chip.className = "gewerbe-chip" + (activeKategorie === k.id ? " active" : "");
      chip.style.setProperty("--chip-color", k.farbe);
      chip.innerHTML = `<span class="gewerbe-chip-icon">${k.icon}</span>` +
        `<span class="gewerbe-chip-label">${esc(k.label)}</span>` +
        `<span class="gewerbe-chip-count">${k.gesamt.toLocaleString("de-DE")}</span>`;
      chip.addEventListener("click", () => selectKategorie(k.id));
      container.appendChild(chip);
    }
  }

  // ── Subchips (Einzel-Branchen einer Kategorie) ─────────────────────────

  function renderSubchips() {
    const container = document.getElementById("gewerbe-subchips");
    container.innerHTML = "";

    if (!activeKategorie) {
      container.classList.remove("visible");
      return;
    }
    container.classList.add("visible");

    const kat = kategorien.find(k => k.id === activeKategorie);
    if (!kat) return;

    // "Alle [Kategorie]" subchip
    const allSub = document.createElement("button");
    allSub.className = "gewerbe-subchip" + (activeBranche === null ? " active" : "");
    allSub.textContent = `Alle ${kat.label}`;
    allSub.addEventListener("click", () => selectBranche(null));
    container.appendChild(allSub);

    for (const b of kat.branchen.slice(0, 30)) {
      const sub = document.createElement("button");
      sub.className = "gewerbe-subchip" + (activeBranche === b.name ? " active" : "");
      sub.textContent = `${b.name} (${b.anzahl})`;
      sub.addEventListener("click", () => selectBranche(b.name));
      container.appendChild(sub);
    }
  }

  // ── Mobile Bottom Sheet Grid ──────────────────────────────────────────

  function renderSheetGrid() {
    const grid = document.getElementById("gewerbe-sheet-grid");
    grid.innerHTML = "";
    for (const k of kategorien) {
      const card = document.createElement("button");
      card.className = "gewerbe-sheet-card" + (activeKategorie === k.id ? " active" : "");
      card.style.setProperty("--card-color", k.farbe);
      card.innerHTML = `<span class="sheet-card-icon">${k.icon}</span>` +
        `<span class="sheet-card-label">${esc(k.label)}</span>` +
        `<span class="sheet-card-count">${k.gesamt.toLocaleString("de-DE")}</span>`;
      card.addEventListener("click", () => {
        selectKategorie(activeKategorie === k.id ? null : k.id);
        collapseSheet();
      });
      grid.appendChild(card);
    }
  }

  // ── Sheet expand/collapse ──────────────────────────────────────────────

  function collapseSheet() {
    document.getElementById("gewerbe-sheet").classList.remove("expanded");
  }

  function setupSheet() {
    const sheet = document.getElementById("gewerbe-sheet");
    const handle = sheet.querySelector(".gewerbe-sheet-handle");
    handle.addEventListener("click", () => {
      sheet.classList.toggle("expanded");
    });
  }

  // ── Selektion ──────────────────────────────────────────────────────────

  function selectKategorie(id) {
    if (activeKategorie === id) {
      // Toggle off
      activeKategorie = null;
      activeBranche = null;
    } else {
      activeKategorie = id;
      activeBranche = null;
    }
    renderChips();
    renderSubchips();
    renderSheetGrid();
    updateLegend();
    updateMapFilter();
  }

  function selectBranche(name) {
    if (activeBranche === name) {
      activeBranche = null;
    } else {
      activeBranche = name;
    }
    renderSubchips();
    updateMapFilter();
  }

  // ── Suche ──────────────────────────────────────────────────────────────

  function setupSearch() {
    const input = document.getElementById("gewerbe-search");
    input.addEventListener("input", () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => doSearch(input.value.trim()), 200);
    });
  }

  function doSearch(query) {
    if (!query) {
      // Reset: zeige alle Chips
      renderChips();
      activeKategorie = null;
      activeBranche = null;
      renderSubchips();
      renderSheetGrid();
      updateLegend();
      updateMapFilter();
      return;
    }

    const q = query.toLowerCase();

    // Finde passende Branchen und markiere deren Kategorie
    const matches = [];
    for (const k of kategorien) {
      for (const b of k.branchen) {
        if (b.name.toLowerCase().includes(q)) {
          matches.push({ branche: b.name, kategorie: k.id, anzahl: b.anzahl });
        }
      }
    }

    if (matches.length === 0) {
      // Keine Treffer – keine Filterung
      return;
    }

    // Wähle die Kategorie mit den meisten Treffern
    const katCounts = {};
    for (const m of matches) {
      katCounts[m.kategorie] = (katCounts[m.kategorie] || 0) + m.anzahl;
    }
    const bestKat = Object.entries(katCounts).sort((a, b) => b[1] - a[1])[0][0];

    // Wenn genau eine Branche → wähle sie direkt
    if (matches.length === 1) {
      activeKategorie = matches[0].kategorie;
      activeBranche = matches[0].branche;
    } else {
      activeKategorie = bestKat;
      activeBranche = null;
    }
    renderChips();
    renderSubchips();
    renderSheetGrid();
    updateLegend();
    updateMapFilter();
  }

  // ── Karten-Layer ──────────────────────────────────────────────────────

  function addGewerbeLayer(geojson) {
    map.addSource("gewerbe", {
      type: "geojson",
      data: geojson,
    });

    // Build color match expression
    const colorExpr = buildColorExpression();

    // Heatmap layer for low zoom
    map.addLayer({
      id: "gewerbe-heat",
      type: "heatmap",
      source: "gewerbe",
      maxzoom: 13,
      paint: {
        "heatmap-weight": ["interpolate", ["linear"], ["get", "anzahl"], 0, 0, 20, 1],
        "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 9, 0.3, 13, 1],
        "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 9, 8, 13, 20],
        "heatmap-opacity": ["interpolate", ["linear"], ["zoom"], 11, 0.7, 13, 0],
        "heatmap-color": [
          "interpolate", ["linear"], ["heatmap-density"],
          0, "rgba(0,0,0,0)", 0.2, "#ffffb2", 0.4, "#fd8d3c",
          0.6, "#f03b20", 0.8, "#bd0026", 1, "#800026",
        ],
      },
    });

    // Circle layer
    map.addLayer({
      id: "gewerbe-circles",
      type: "circle",
      source: "gewerbe",
      minzoom: 10,
      paint: {
        "circle-color": colorExpr,
        "circle-radius": [
          "interpolate", ["linear"], ["zoom"],
          10, 2, 13, 4, 16, 7, 18, 10,
        ],
        "circle-opacity": [
          "interpolate", ["linear"], ["zoom"],
          10, 0.6, 13, 0.8, 16, 0.9,
        ],
        "circle-stroke-width": 0.5,
        "circle-stroke-color": "rgba(255,255,255,0.6)",
      },
    });
  }

  function buildColorExpression() {
    // Default: color by first gewerbe's kategorie
    // We use a match expression on a computed property – but since GeoJSON source
    // doesn't support computed props, we need to set a top-level property.
    // We'll use feature-state or just use a fixed default and filter.
    // Simplest: use default multi-color based on first gewerbe kategorie
    // This requires the geojson to have a top-level "kategorie" field.
    // Since we don't, we'll build the expression from the JSON.

    // Actually, for simplicity, let's compute dominant kategorie per feature
    // during load and store as a property.
    // But we already generated the geojson. Let's compute it client-side.

    // For now, use a fallback approach: all points get a single color when
    // filtered, or multi-color when showing all.
    return activeKategorie
      ? (katFarbeMap[activeKategorie] || "#9ca3af")
      : "#d97706";  // default orange
  }

  // ── Feature-Kategorien vorab berechnen ─────────────────────────────────

  function enrichFeatures(geojson) {
    // Add dominant kategorie to each feature for coloring
    for (const feat of geojson.features) {
      const gewerbe = feat.properties.gewerbe;
      if (!gewerbe || gewerbe.length === 0) continue;

      // Count categories
      const catCount = {};
      for (const g of gewerbe) {
        catCount[g.kategorie] = (catCount[g.kategorie] || 0) + 1;
      }
      // Pick dominant
      let maxCat = "sonstiges", maxN = 0;
      for (const [cat, n] of Object.entries(catCount)) {
        if (n > maxN) { maxCat = cat; maxN = n; }
      }
      feat.properties.hauptkategorie = maxCat;

      // Also store category set for filtering
      feat.properties.kategorien = Object.keys(catCount);
    }
    return geojson;
  }

  // ── Filter & Update ────────────────────────────────────────────────────

  function updateMapFilter() {
    if (!map.getSource("gewerbe")) return;

    if (!activeKategorie && !activeBranche) {
      // Show all – update source with all features, color by dominant category
      map.getSource("gewerbe").setData({
        type: "FeatureCollection",
        features: allFeatures,
      });
      updateCircleColor();
      return;
    }

    // Filter features
    const filtered = [];
    for (const feat of allFeatures) {
      const gewerbe = feat.properties.gewerbe;
      let match = false;

      for (const g of gewerbe) {
        if (activeKategorie && g.kategorie !== activeKategorie) continue;
        if (activeBranche && g.branche !== activeBranche) continue;
        match = true;
        break;
      }

      if (match) {
        // Create a filtered copy with only matching gewerbe entries
        const filteredGewerbe = gewerbe.filter(g => {
          if (activeKategorie && g.kategorie !== activeKategorie) return false;
          if (activeBranche && g.branche !== activeBranche) return false;
          return true;
        });
        filtered.push({
          ...feat,
          properties: {
            ...feat.properties,
            anzahl: filteredGewerbe.length,
            gewerbe_filtered: filteredGewerbe,
          },
        });
      }
    }

    map.getSource("gewerbe").setData({
      type: "FeatureCollection",
      features: filtered,
    });
    updateCircleColor();
  }

  function updateCircleColor() {
    if (!map.getLayer("gewerbe-circles")) return;

    if (activeKategorie) {
      // Single color
      map.setPaintProperty("gewerbe-circles", "circle-color",
        katFarbeMap[activeKategorie] || "#9ca3af");
    } else {
      // Multi-color based on dominant category
      const matchExpr = ["match", ["get", "hauptkategorie"]];
      for (const k of kategorien) {
        matchExpr.push(k.id, k.farbe);
      }
      matchExpr.push("#9ca3af"); // fallback
      map.setPaintProperty("gewerbe-circles", "circle-color", matchExpr);
    }

    // Also update heatmap color to match
    if (activeKategorie && map.getLayer("gewerbe-heat")) {
      const farbe = katFarbeMap[activeKategorie] || "#d97706";
      map.setPaintProperty("gewerbe-heat", "heatmap-color", [
        "interpolate", ["linear"], ["heatmap-density"],
        0, "rgba(0,0,0,0)", 0.3, farbe + "40", 0.6, farbe + "99", 1, farbe,
      ]);
    } else if (map.getLayer("gewerbe-heat")) {
      map.setPaintProperty("gewerbe-heat", "heatmap-color", [
        "interpolate", ["linear"], ["heatmap-density"],
        0, "rgba(0,0,0,0)", 0.2, "#ffffb2", 0.4, "#fd8d3c",
        0.6, "#f03b20", 0.8, "#bd0026", 1, "#800026",
      ]);
    }
  }

  // ── Legende ────────────────────────────────────────────────────────────

  function updateLegend() {
    const content = document.getElementById("gewerbe-legend-content");
    if (activeKategorie) {
      const kat = kategorien.find(k => k.id === activeKategorie);
      if (!kat) return;
      content.innerHTML = `
        <div class="legend-row">
          <div class="legend-dot" style="background:${kat.farbe}"></div>
          ${kat.icon} ${esc(kat.label)} (${kat.gesamt.toLocaleString("de-DE")})
        </div>`;
    } else {
      // Show top categories
      let html = "";
      for (const k of kategorien.slice(0, 8)) {
        html += `<div class="legend-row">
          <div class="legend-dot" style="background:${k.farbe}"></div>
          ${k.icon} ${esc(k.label)}
        </div>`;
      }
      content.innerHTML = html;
    }
  }

  // ── Popup ──────────────────────────────────────────────────────────────

  function setupPopup() {
    map.on("click", "gewerbe-circles", (e) => {
      if (!e.features || e.features.length === 0) return;
      const feat = e.features[0];
      const props = feat.properties;

      // Parse gewerbe JSON (MapLibre stringifies nested objects)
      let gewerbe = [];
      try {
        const gList = props.gewerbe_filtered || props.gewerbe;
        gewerbe = typeof gList === "string" ? JSON.parse(gList) : gList;
      } catch { gewerbe = []; }

      const adresse = props.adresse || "Unbekannt";

      let html = `<div class="popup-header" style="background:${
        activeKategorie ? (katFarbeMap[activeKategorie] || "var(--primary)") : "var(--primary)"
      }">
        <div class="popup-adresse">${esc(adresse)}</div>
        <div class="popup-count">${gewerbe.length} Gewerbe</div>
      </div>
      <div class="popup-personen">`;

      for (const g of gewerbe) {
        const katFarbe = katFarbeMap[g.kategorie] || "#9ca3af";
        html += `<div class="person-card" style="border-left-color:${katFarbe}">`;
        if (g.firmenname) {
          html += `<div class="person-firma">${esc(g.firmenname)}</div>`;
        }
        if (g.branche) {
          html += `<div class="person-branche">${esc(g.branche)}</div>`;
        }
        if (g.nachname || g.vorname) {
          html += `<div class="person-detail">${esc(g.vorname)} ${esc(g.nachname)}</div>`;
        }
        html += `</div>`;
      }

      html += `</div>`;

      if (popup) popup.remove();
      popup = new maplibregl.Popup({ maxWidth: "320px", closeButton: true })
        .setLngLat(e.lngLat)
        .setHTML(html)
        .addTo(map);
    });

    map.on("mouseenter", "gewerbe-circles", () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", "gewerbe-circles", () => {
      map.getCanvas().style.cursor = "";
    });
  }

  // ── Stadtplan-Toggle ───────────────────────────────────────────────────

  function setupLayerControls() {
    document.getElementById("toggle-stadtplan").addEventListener("change", (e) => {
      historicalLayerVisible = e.target.checked;
      document.getElementById("opacity-row").style.display = historicalLayerVisible ? "" : "none";
      if (map.getLayer("stadtplan-1935-layer")) {
        map.setLayoutProperty("stadtplan-1935-layer", "visibility",
          historicalLayerVisible ? "visible" : "none");
      }
    });

    document.getElementById("opacity-stadtplan").addEventListener("input", (e) => {
      const val = parseInt(e.target.value, 10);
      document.getElementById("opacity-value").textContent = val + "%";
      if (map.getLayer("stadtplan-1935-layer")) {
        map.setPaintProperty("stadtplan-1935-layer", "raster-opacity", val / 100);
      }
    });
  }

  // ── UI-Toggle ────────────────────────────────────────────────────────

  function setupUIToggle() {
    const btn = document.getElementById("gewerbe-ui-toggle");
    const iconVisible = document.getElementById("toggle-icon-visible");
    const iconHidden = document.getElementById("toggle-icon-hidden");
    if (!btn) return;

    btn.addEventListener("click", () => {
      const hidden = document.body.classList.toggle("gewerbe-ui-hidden");
      iconVisible.style.display = hidden ? "none" : "";
      iconHidden.style.display = hidden ? "" : "none";
    });
  }

  // ── Initialisierung ────────────────────────────────────────────────────

  map.on("load", async () => {
    try {
      addHistoricalLayer();

      const { geojson, kategorien: kats } = await loadData();
      kategorien = kats;
      buildKatMaps();

      const enriched = enrichFeatures(geojson);
      allFeatures = enriched.features;

      addGewerbeLayer(enriched);
      renderChips();
      renderSubchips();
      renderSheetGrid();
      updateLegend();
      updateCircleColor();
      setupPopup();
      setupSearch();
      setupLayerControls();
      setupSheet();
      setupUIToggle();

      document.getElementById("loading").style.display = "none";
    } catch (err) {
      document.getElementById("loading").innerHTML =
        `<div style="color:red">Fehler beim Laden:<br>${err.message}</div>`;
      console.error(err);
    }
  });

})();
