/* schichten.js – Schichtenkarte: Gebäudepolygone nach sozialer Schicht */

(function () {
  "use strict";

  // ── Farben ────────────────────────────────────────────────────────────────

  const COLORS = {
    arm:      "#b91c1c",
    mittel:   "#d4a847",
    reich:    "#1e3a5f",
    gemischt: "#6b7c45",
    none:     "#cccccc",
  };

  // ── PMTiles-Protokoll registrieren ──────────────────────────────────────

  const protocol = new pmtiles.Protocol();
  maplibregl.addProtocol("pmtiles", protocol.tile);

  // ── Karte initialisieren ──────────────────────────────────────────────────

  const map = new maplibregl.Map({
    container: "schichten-map",
    style: "https://tiles.openfreemap.org/styles/liberty",
    center: [7.0177, 51.4556],
    zoom: 12,
    minZoom: 9,
    maxZoom: 18,
  });

  map.addControl(new maplibregl.NavigationControl(), "top-right");
  map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");

  let popup = null;
  let historicalLayerVisible = true;

  // ── Historischer Stadtplan (ArcGIS) ───────────────────────────────────────

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

  // ── Hilfsfunktionen ────────────────────────────────────────────────────────

  function escHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // ── Gebäude-Layer (PMTiles) ─────────────────────────────────────────────

  function addGebaeudeLayers() {
    map.addSource("gebaeude-schichten", {
      type: "vector",
      url: "pmtiles://data/gebaeude_schichten.pmtiles",
    });

    // Gebäude-Fill
    map.addLayer({
      id: "gebaeude-fill",
      type: "fill",
      source: "gebaeude-schichten",
      "source-layer": "gebaeude",
      paint: {
        "fill-color": [
          "match", ["get", "schicht"],
          "arm",      COLORS.arm,
          "mittel",   COLORS.mittel,
          "reich",    COLORS.reich,
          "gemischt", COLORS.gemischt,
          COLORS.none,
        ],
        "fill-opacity": 0.7,
      },
    });

    // Gebäude-Outline (nur bei hohem Zoom)
    map.addLayer({
      id: "gebaeude-outline",
      type: "line",
      source: "gebaeude-schichten",
      "source-layer": "gebaeude",
      minzoom: 14,
      paint: {
        "line-color": "#999",
        "line-width": 0.5,
        "line-opacity": 0.5,
      },
    });
  }

  // ── Popup ─────────────────────────────────────────────────────────────────

  function showPopup(feature, lngLat) {
    if (popup) popup.remove();
    const p = feature.properties;

    const schichtLabel = {
      arm: "Arm (Arbeiterklasse)",
      mittel: "Mittel (Facharbeiter/Angestellte)",
      reich: "Reich (Akademiker/Selbstständige)",
      gemischt: "Gemischt",
    }[p.schicht] || "Nicht zugeordnet";

    const color = COLORS[p.schicht] || COLORS.none;

    let html;
    if (p.strasse) {
      html = `
        <div class="popup-header" style="background:${color}">
          <div class="popup-adresse">${escHtml(p.strasse)}</div>
          <div class="popup-count">${schichtLabel} · Score ${p.score}</div>
        </div>`;
    } else {
      html = `
        <div class="popup-header" style="background:${color}">
          <div class="popup-adresse">Nicht zugeordnet</div>
          <div class="popup-count">Keine klassifizierte Straße in der Nähe</div>
        </div>`;
    }

    popup = new maplibregl.Popup({ maxWidth: "300px", closeButton: true })
      .setLngLat(lngLat)
      .setHTML(html)
      .addTo(map);
  }

  // ── Events ────────────────────────────────────────────────────────────────

  let hoveredId = null;

  function setupEvents() {
    // Hover
    map.on("mousemove", "gebaeude-fill", e => {
      map.getCanvas().style.cursor = "pointer";
    });

    map.on("mouseleave", "gebaeude-fill", () => {
      map.getCanvas().style.cursor = "";
    });

    // Click
    map.on("click", "gebaeude-fill", e => {
      if (e.features && e.features.length > 0) {
        showPopup(e.features[0], e.lngLat);
      }
    });

    // Stadtplan-Toggle
    document.getElementById("toggle-stadtplan").addEventListener("change", e => {
      historicalLayerVisible = e.target.checked;
      document.getElementById("opacity-row").style.display = historicalLayerVisible ? "" : "none";
      if (map.getLayer("stadtplan-1935-layer")) {
        map.setLayoutProperty("stadtplan-1935-layer", "visibility",
          historicalLayerVisible ? "visible" : "none");
      }
    });

    document.getElementById("opacity-stadtplan").addEventListener("input", e => {
      const val = parseInt(e.target.value, 10);
      document.getElementById("opacity-value").textContent = val + "%";
      if (map.getLayer("stadtplan-1935-layer")) {
        map.setPaintProperty("stadtplan-1935-layer", "raster-opacity", val / 100);
      }
    });
  }

  // ── Initialisierung ───────────────────────────────────────────────────────

  map.on("load", () => {
    try {
      addHistoricalLayer();
      addGebaeudeLayers();
      setupEvents();
      document.getElementById("loading").style.display = "none";
    } catch (err) {
      document.getElementById("loading").innerHTML =
        `<div style="color:red">Fehler beim Laden:<br>${err.message}</div>`;
      console.error(err);
    }
  });

})();
