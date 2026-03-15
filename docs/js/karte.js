/* karte.js – MapLibre GL JS Kartenlogik für Adressbuch Essen 1936 */

(function () {
  "use strict";

  // ── Karte initialisieren ──────────────────────────────────────────────────

  const map = new maplibregl.Map({
    container: "map",
    style: "https://tiles.openfreemap.org/styles/liberty",
    center: [7.0177, 51.4556],
    zoom: 11,
    minZoom: 9,
    maxZoom: 18,
  });

  map.addControl(new maplibregl.NavigationControl(), "top-right");
  map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");

  // ── Berufsgruppen-Konfiguration ───────────────────────────────────────────

  // OhdAB-Kategorien B 0–B 9 (id = Kurzbezeichnung, muss mit GeoJSON-Werten übereinstimmen)
  const BERUFSGRUPPEN = [
    { id: "Rohstoffgewinnung",        label: "Rohstoffgewinnung",        farbe: "#78716c" },
    { id: "Unternehmensorganisation", label: "Unternehmensorganisation", farbe: "#7c3aed" },
    { id: "Verkehr",                  label: "Verkehr",                  farbe: "#0891b2" },
    { id: "Kaufm. Dienstleistungen",  label: "Kaufm. Dienstleistungen",  farbe: "#d97706" },
    { id: "Gesundheit",               label: "Gesundheit",               farbe: "#0f766e" },
    { id: "Bau",                      label: "Bau",                      farbe: "#ea580c" },
    { id: "Geisteswiss. & Kunst",     label: "Geisteswiss. & Kunst",     farbe: "#9333ea" },
    { id: "Land- & Forstwirtschaft",  label: "Land- & Forstwirtschaft",  farbe: "#16a34a" },
    { id: "Naturwissenschaft",        label: "Naturwissenschaft",        farbe: "#2563eb" },
    { id: "Militär",                  label: "Militär",                  farbe: "#4d7c0f" },
    { id: "sonstige",                 label: "Sonstiges",                farbe: "#9ca3af" },
  ];

  // ── Zustand ───────────────────────────────────────────────────────────────

  let allFeatures = [];
  let currentFilteredFeatures = [];  // aktuell sichtbar (nach Sidebar-Filtern)
  let searchIndex = [];
  let searchActive = false;
  let searchDebounceTimer = null;

  let activeFilter = {
    stadtteile: [],
    nurAkademiker: false,
    sektionen: ["I", "III"],
    berufsgruppen: [],
    bergbauFilter: null,  // null | "narrow" | "broad"
  };

  let popup = null;
  let historicalLayerVisible = true;

  // ── Paint-Expressions ─────────────────────────────────────────────────────

  const CIRCLE_COLOR = "#1d4ed8";

  const circleRadius = [
    "interpolate", ["linear"], ["get", "anzahl"],
    1, 3, 5, 4, 20, 5, 50, 6.5, 100, 8,
  ];

  const circleOpacity = [
    "interpolate", ["linear"], ["get", "anzahl"],
    1, 0.25, 5, 0.45, 20, 0.7, 50, 0.87, 100, 0.97,
  ];

  const heatmapWeight = [
    "interpolate", ["linear"], ["get", "anzahl"],
    0, 0, 100, 1,
  ];

  // ── Historischer Stadtplan (ArcGIS dynamic export) ────────────────────────

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
    // moveend erst nach 2s registrieren, damit das initiale Bild
    // nicht durch sofortige ResizeObserver-Events abgebrochen wird
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
      } catch { /* vorheriges Bild noch am Laden – ignorieren */ }
    }, 200);
  }

  // ── Daten laden ───────────────────────────────────────────────────────────

  async function loadData() {
    const resp = await fetch("data/essen1936.geojson");
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
  }

  // ── Suchindex ─────────────────────────────────────────────────────────────

  function buildSearchIndex(features) {
    const idx = [];
    for (let i = 0; i < features.length; i++) {
      const feat = features[i];
      const props = feat.properties;
      const adresse = props.adresse || "";

      // Adress-Eintrag
      idx.push({
        type: "adresse",
        searchText: adresse.toLowerCase(),
        label: adresse,
        detail: `${props.anzahl} Person${props.anzahl !== 1 ? "en" : ""}`,
        feature: feat,
      });

      // Personen-Einträge
      const personen = typeof props.personen === "string"
        ? JSON.parse(props.personen)
        : (props.personen || []);

      for (const p of personen) {
        const name = [p.nachname, p.vorname].filter(Boolean).join(" ");
        if (!name) continue;
        idx.push({
          type: "person",
          searchText: name.toLowerCase(),
          label: p.nachname + (p.vorname ? ", " + p.vorname : ""),
          detail: [p.beruf, adresse].filter(Boolean).join(" · "),
          feature: feat,
        });
      }
    }
    return idx;
  }

  // ── Suche ausführen ───────────────────────────────────────────────────────

  const MAX_PERSON_HITS = 300;

  function performSearch(query) {
    const q = query.trim().toLowerCase();
    if (q.length < 2) return null;

    const filteredSet = new Set(currentFilteredFeatures);
    const adresseHits = [];
    const personHits = [];
    const seenPersonKeys = new Set();
    const matchedFeatures = new Set();

    for (const entry of searchIndex) {
      if (!entry.searchText.includes(q)) continue;
      if (!filteredSet.has(entry.feature)) continue;

      matchedFeatures.add(entry.feature);

      if (entry.type === "adresse") {
        adresseHits.push(entry);
      } else if (entry.type === "person") {
        const key = entry.label + "|" + entry.feature.properties.adresse;
        if (!seenPersonKeys.has(key)) {
          seenPersonKeys.add(key);
          personHits.push(entry);
        }
      }
    }

    return {
      adresseHits,
      personHits,
      total: matchedFeatures.size,
      matchedFeatures: [...matchedFeatures],
    };
  }

  // ── Treffer im Text hervorheben ───────────────────────────────────────────

  function highlightText(text, query) {
    const idx = text.toLowerCase().indexOf(query.toLowerCase());
    if (idx === -1) return `<span class="dr-muted">${escHtml(text)}</span>`;
    return (
      `<span class="dr-muted">${escHtml(text.slice(0, idx))}</span>` +
      `<strong>${escHtml(text.slice(idx, idx + query.length))}</strong>` +
      `<span class="dr-muted">${escHtml(text.slice(idx + query.length))}</span>`
    );
  }

  // ── Ergebnisliste (Sidebar-Panel) ────────────────────────────────────────

  function showResultsPanel(results, query) {
    document.getElementById("sidebar-filters").style.display = "none";
    const panel = document.getElementById("sidebar-results");
    panel.style.display = "flex";

    const countEl = document.getElementById("results-count");
    const list    = document.getElementById("results-list");

    if (!results || (results.adresseHits.length === 0 && results.personHits.length === 0)) {
      countEl.textContent = "Keine Treffer";
      list.innerHTML = `<div class="results-empty">Keine Treffer für „${escHtml(query)}"</div>`;
      return;
    }

    const totalPersons = results.personHits.length;
    const shown = Math.min(totalPersons, MAX_PERSON_HITS);
    countEl.textContent = `${results.total.toLocaleString("de-DE")} Treffer`;

    // Sprung-Buttons aufbauen
    const jumps = document.getElementById("results-jumps");
    jumps.innerHTML = "";
    const resultsList = document.getElementById("results-list");
    if (results.adresseHits.length > 0) {
      const btn = document.createElement("button");
      btn.className = "jump-btn";
      btn.textContent = `Straßen (${results.adresseHits.length})`;
      btn.addEventListener("click", () => {
        resultsList.scrollTo({ top: 0, behavior: "smooth" });
      });
      jumps.appendChild(btn);
    }
    if (totalPersons > 0) {
      const btn = document.createElement("button");
      btn.className = "jump-btn";
      btn.textContent = `Personen (${totalPersons.toLocaleString("de-DE")})`;
      btn.addEventListener("click", () => {
        const el = document.getElementById("jump-personen");
        if (el) resultsList.scrollTo({ top: el.offsetTop, behavior: "smooth" });
      });
      jumps.appendChild(btn);
    }

    const parts = [];

    if (results.adresseHits.length > 0) {
      parts.push(`<div class="results-group-label" id="jump-adressen">Straßen</div>`);
      for (const h of results.adresseHits) {
        parts.push(`
          <div class="result-item" data-adresse="${escHtml(h.feature.properties.adresse)}">
            <div class="result-label">${highlightText(h.label, query)}</div>
            <div class="result-detail">${escHtml(h.detail)}</div>
          </div>`);
      }
    }

    if (totalPersons > 0) {
      parts.push(`<div class="results-group-label" id="jump-personen">Personen</div>`);
      for (const h of results.personHits.slice(0, MAX_PERSON_HITS)) {
        parts.push(`
          <div class="result-item" data-adresse="${escHtml(h.feature.properties.adresse)}">
            <div class="result-label">${highlightText(h.label, query)}</div>
            <div class="result-detail">${escHtml(h.detail)}</div>
          </div>`);
      }
      if (totalPersons > MAX_PERSON_HITS) {
        parts.push(`<div class="results-more">Erste ${MAX_PERSON_HITS} von ${totalPersons.toLocaleString("de-DE")} – Suche verfeinern</div>`);
      }
    }

    list.innerHTML = parts.join("");

    list.querySelectorAll(".result-item").forEach(el => {
      el.addEventListener("click",       () => selectResult(el.dataset.adresse));
      el.addEventListener("mouseenter",  () => highlightFeature(el.dataset.adresse));
      el.addEventListener("mouseleave",  () => clearHighlight());
    });
  }

  function hideResultsPanel() {
    document.getElementById("sidebar-results").style.display = "none";
    document.getElementById("sidebar-filters").style.display = "";
    clearHighlight();
  }

  // ── Ergebnis auswählen ────────────────────────────────────────────────────

  function selectResult(adresse) {
    const feat = currentFilteredFeatures.find(
      f => f.properties.adresse === adresse
    );
    if (!feat) return;

    const coords = feat.geometry.coordinates;
    map.flyTo({ center: coords, zoom: Math.max(map.getZoom(), 16) });
    map.once("moveend", () => showPopup(feat, { lng: coords[0], lat: coords[1] }));
  }

  // ── Hover-Highlight ───────────────────────────────────────────────────────

  function highlightFeature(adresse) {
    const feat = currentFilteredFeatures.find(f => f.properties.adresse === adresse);
    const src = map.getSource("adressen-highlight");
    if (src) src.setData({ type: "FeatureCollection", features: feat ? [feat] : [] });
  }

  function clearHighlight() {
    const src = map.getSource("adressen-highlight");
    if (src) src.setData({ type: "FeatureCollection", features: [] });
  }

  // ── Such-Dimm-Effekt ──────────────────────────────────────────────────────

  function activateSearchDim(matchedFeatures) {
    searchActive = true;

    // Hintergrund: alle gefilterten Features abgedunkelt
    const bgSrc = map.getSource("adressen-bg");
    if (bgSrc) {
      bgSrc.setData({ type: "FeatureCollection", features: currentFilteredFeatures });
    }
    if (map.getLayer("adressen-circle-dim")) {
      map.setLayoutProperty("adressen-circle-dim", "visibility", "visible");
    }

    // Heatmap ausblenden (verwirrend im Such-Modus)
    if (map.getLayer("adressen-heat")) {
      map.setLayoutProperty("adressen-heat", "visibility", "none");
    }

    // Vordergrund: nur Treffer, normal sichtbar
    const src = map.getSource("adressen");
    if (src) {
      src.setData({ type: "FeatureCollection", features: matchedFeatures });
    }
  }

  function clearSearchDim() {
    searchActive = false;

    if (map.getLayer("adressen-circle-dim")) {
      map.setLayoutProperty("adressen-circle-dim", "visibility", "none");
    }
    if (map.getLayer("adressen-heat")) {
      map.setLayoutProperty("adressen-heat", "visibility", "visible");
    }

    // Hauptquelle auf gefilterte Features zurücksetzen
    const src = map.getSource("adressen");
    if (src) {
      src.setData({ type: "FeatureCollection", features: currentFilteredFeatures });
    }
  }

  // ── Filter ────────────────────────────────────────────────────────────────

  function buildMaplibreFilter() {
    const conditions = ["all"];

    if (activeFilter.stadtteile.length > 0) {
      const orConds = ["any"];
      for (const st of activeFilter.stadtteile) {
        orConds.push(["in", st, ["get", "stadtteile"]]);
      }
      conditions.push(orConds);
    }

    // Akademiker-Filter wird jetzt personenbezogen in applyFilters() gelöst

    return conditions.length > 1 ? conditions : null;
  }

  function parsePersn(p) {
    return typeof p === "string" ? JSON.parse(p) : p;
  }

  /** Prüft ob eine Person die aktiven Personenfilter erfüllt. */
  function personMatches(p) {
    const g = activeFilter.berufsgruppen;
    if (g.length > 0 && !g.includes(p.berufsgruppe)) return false;
    if (activeFilter.nurAkademiker && !p.akademiker) return false;
    if (activeFilter.bergbauFilter === "narrow") {
      if (p.bergbau_typ !== "b" && p.bergbau_typ !== "s") return false;
    } else if (activeFilter.bergbauFilter === "broad") {
      if (!p.bergbau_typ) return false;
    }
    return true;
  }

  function applyFilters() {
    const aktiveSektionen = activeFilter.sektionen;
    const hatPersonenfilter = activeFilter.berufsgruppen.length > 0 || activeFilter.nurAkademiker || activeFilter.bergbauFilter;

    currentFilteredFeatures = [];

    for (const f of allFeatures) {
      const props = f.properties;

      if (aktiveSektionen.length > 0) {
        const sektionen = props.sektionen || [];
        if (!aktiveSektionen.some(s => sektionen.includes(s))) continue;
      }

      if (hatPersonenfilter) {
        const personen = parsePersn(props.personen);
        const matchCount = personen.filter(personMatches).length;
        if (matchCount === 0) continue;

        currentFilteredFeatures.push({
          type: f.type,
          geometry: f.geometry,
          properties: { ...props, anzahl: matchCount },
        });
        continue;
      }

      currentFilteredFeatures.push(f);
    }

    if (searchActive) {
      // Such-Modus: nur Treffer in gefilterten Features neu berechnen
      const query = document.getElementById("search-input").value;
      const results = performSearch(query);
      if (results) {
        activateSearchDim(results.matchedFeatures);
      } else {
        clearSearchDim();
      }
    } else {
      const src = map.getSource("adressen");
      if (src) src.setData({ type: "FeatureCollection", features: currentFilteredFeatures });
    }

    const mlFilter = buildMaplibreFilter();
    ["adressen-heat", "adressen-circle", "adressen-circle-dim"].forEach(id => {
      if (map.getLayer(id)) map.setFilter(id, mlFilter);
    });
  }

  // ── Berufsgruppen-Checkboxes befüllen ─────────────────────────────────────

  function bgSlug(id) {
    return id.replace(/[^a-zA-Z0-9]/g, "-");
  }

  function populateBerufsgruppFilter() {
    const container = document.getElementById("filter-berufsgruppen");
    for (const bg of BERUFSGRUPPEN) {
      const slug = bgSlug(bg.id);
      const row = document.createElement("label");
      row.className = "bg-item";
      row.htmlFor = `bg-${slug}`;
      row.innerHTML = `
        <input type="checkbox" id="bg-${slug}" value="${bg.id}">
        <span class="bg-dot" style="background:${bg.farbe}"></span>
        <span class="bg-label">${bg.label}</span>`;
      container.appendChild(row);
    }
  }

  // ── Stadtteile befüllen ───────────────────────────────────────────────────

  function populateStadtteilFilter(features) {
    const set = new Set();
    features.forEach(f => (f.properties.stadtteile || []).forEach(s => set.add(s)));
    const sel = document.getElementById("filter-stadtteil");
    [...set].sort().forEach(st => {
      const opt = document.createElement("option");
      opt.value = st;
      opt.textContent = st;
      sel.appendChild(opt);
    });
  }

  // ── Layer hinzufügen ──────────────────────────────────────────────────────

  function addLayers() {
    // Hauptquelle
    map.addSource("adressen", {
      type: "geojson",
      data: { type: "FeatureCollection", features: currentFilteredFeatures },
    });

    // Hintergrundquelle (für Dimm-Effekt)
    map.addSource("adressen-bg", {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });

    // Heatmap
    map.addLayer({
      id: "adressen-heat",
      type: "heatmap",
      source: "adressen",
      maxzoom: 12,
      paint: {
        "heatmap-weight": heatmapWeight,
        "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 9, 0.3, 12, 1],
        "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 9, 8, 12, 20],
        "heatmap-color": [
          "interpolate", ["linear"], ["heatmap-density"],
          0, "rgba(33,102,172,0)", 0.2, "rgb(103,169,207)",
          0.4, "rgb(209,229,240)", 0.6, "rgb(253,219,199)",
          0.8, "rgb(239,138,98)", 1, "rgb(178,24,43)",
        ],
        "heatmap-opacity": ["interpolate", ["linear"], ["zoom"], 10, 1, 12, 0],
      },
    });

    // Dim-Layer (Hintergrund bei Suche) – standardmäßig unsichtbar
    map.addLayer({
      id: "adressen-circle-dim",
      type: "circle",
      source: "adressen-bg",
      minzoom: 11,
      layout: { visibility: "none" },
      paint: {
        "circle-color": CIRCLE_COLOR,
        "circle-radius": circleRadius,
        "circle-opacity": 0.08,
        "circle-stroke-width": 0,
      },
    });

    // Highlight-Quelle (Hover aus Ergebnisliste)
    map.addSource("adressen-highlight", {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });

    map.addLayer({
      id: "adressen-highlight-layer",
      type: "circle",
      source: "adressen-highlight",
      paint: {
        "circle-color": CIRCLE_COLOR,
        "circle-radius": ["interpolate", ["linear"], ["get", "anzahl"], 1, 7, 50, 13],
        "circle-opacity": 0.9,
        "circle-stroke-width": 2,
        "circle-stroke-color": "white",
      },
    });

    // Haupt-Circle-Layer
    map.addLayer({
      id: "adressen-circle",
      type: "circle",
      source: "adressen",
      minzoom: 11,
      paint: {
        "circle-color": CIRCLE_COLOR,
        "circle-radius": circleRadius,
        "circle-stroke-width": 0,
        "circle-opacity": circleOpacity,
      },
    });
  }

  // ── Popup ─────────────────────────────────────────────────────────────────

  function showPopup(feature, lngLat) {
    if (popup) popup.remove();
    const props = feature.properties;
    const personen = typeof props.personen === "string"
      ? JSON.parse(props.personen)
      : props.personen;

    const dimSektionI = activeFilter.sektionen.length > 0 && !activeFilter.sektionen.includes("I");
    const hatPersonenfilter = activeFilter.berufsgruppen.length > 0 || activeFilter.nurAkademiker || activeFilter.bergbauFilter;

    // Sortierung: matchende Personen zuerst, dann nach Sektion/Seite
    const sorted = [...personen].sort((a, b) => {
      if (hatPersonenfilter) {
        const aMatch = personMatches(a) ? 0 : 1;
        const bMatch = personMatches(b) ? 0 : 1;
        if (aMatch !== bMatch) return aMatch - bMatch;
      }
      const sA = (a.seite || "Z").split("-")[0];
      const sB = (b.seite || "Z").split("-")[0];
      if (sA !== sB) return sA < sB ? -1 : 1;
      return (parseInt((a.seite || "").split("-")[1]) || 0)
           - (parseInt((b.seite || "").split("-")[1]) || 0);
    });

    const matchCount = hatPersonenfilter
      ? personen.filter(personMatches).length
      : personen.length;

    const cards = sorted.map(p => {
      const sektion = p.seite ? p.seite.split("-")[0] : "";
      const dimSektion = dimSektionI && sektion === "I";
      const dimPerson = hatPersonenfilter && !personMatches(p);
      const dim = dimSektion || dimPerson;
      return `
        <div class="person-card${dim ? " person-card--dim" : ""}">
          <div class="person-name">${escHtml(p.nachname)}${p.vorname ? ", " + escHtml(p.vorname) : ""}</div>
          <div class="person-detail">${p.beruf ? escHtml(p.beruf) + " · " : ""}Seite ${escHtml(p.seite)}</div>
        </div>`;
    }).join("");

    const countLabel = hatPersonenfilter
      ? `${matchCount} von ${personen.length} Person${personen.length !== 1 ? "en" : ""}`
      : `${personen.length} Person${personen.length !== 1 ? "en" : ""}`;

    popup = new maplibregl.Popup({ maxWidth: "340px", closeButton: true })
      .setLngLat(lngLat)
      .setHTML(`
        <div class="popup-header">
          <div class="popup-adresse">${escHtml(props.adresse)}</div>
          <div class="popup-count">${countLabel}</div>
        </div>
        <div class="popup-personen">${cards}</div>`)
      .addTo(map);
  }

  function escHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // ── Tooltip ───────────────────────────────────────────────────────────────

  let tooltip = null;

  function createTooltip() {
    tooltip = document.createElement("div");
    tooltip.style.cssText = `
      position:absolute; pointer-events:none; z-index:100;
      background:rgba(26,58,92,0.9); color:white;
      padding:4px 8px; border-radius:4px; font-size:12px;
      white-space:nowrap; display:none;`;
    document.getElementById("map").appendChild(tooltip);
  }

  // ── Zechen-Layer ─────────────────────────────────────────────────────────

  let zechenLoaded = false;

  async function loadZechenLayer() {
    try {
      const resp = await fetch("data/zechen.geojson");
      if (!resp.ok) return;
      const geojson = await resp.json();

      map.addSource("zechen", { type: "geojson", data: geojson });

      // Schlägel-und-Eisen-Icon laden
      const img = await map.loadImage("img/schlaegel-eisen.png");
      map.addImage("schlaegel-eisen", img.data);

      map.addLayer({
        id: "zechen-symbol",
        type: "symbol",
        source: "zechen",
        layout: {
          "icon-image": "schlaegel-eisen",
          "icon-size": 0.5,
          "icon-allow-overlap": true,
          visibility: "none",
        },
      });

      // Klick → Popup
      map.on("click", "zechen-symbol", e => {
        const props = e.features[0].properties;
        new maplibregl.Popup({ maxWidth: "260px" })
          .setLngLat(e.lngLat)
          .setHTML(`
            <div class="popup-header">
              <div class="popup-adresse">${escHtml(props.name)}</div>
              <div class="popup-count">${escHtml(props.betriebszeit)}</div>
            </div>`)
          .addTo(map);
      });

      map.on("mouseenter", "zechen-symbol", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "zechen-symbol", () => {
        map.getCanvas().style.cursor = "";
      });

      zechenLoaded = true;
    } catch (err) {
      console.warn("Zechen-Layer konnte nicht geladen werden:", err);
    }
  }

  function toggleZechenLayer() {
    if (!zechenLoaded) return;
    const vis = activeFilter.bergbauFilter ? "visible" : "none";
    map.setLayoutProperty("zechen-symbol", "visibility", vis);
    const legendEl = document.getElementById("legend-zeche");
    if (legendEl) legendEl.style.display = activeFilter.bergbauFilter ? "" : "none";
  }

  // ── Events ────────────────────────────────────────────────────────────────

  function setupEvents() {
    createTooltip();

    // Hover
    map.on("mousemove", "adressen-circle", e => {
      map.getCanvas().style.cursor = "pointer";
      const p = e.features[0].properties;
      tooltip.style.display = "block";
      tooltip.style.left = (e.originalEvent.offsetX + 12) + "px";
      tooltip.style.top  = (e.originalEvent.offsetY - 10) + "px";
      tooltip.textContent = `${p.adresse} · ${p.anzahl} Person${p.anzahl !== 1 ? "en" : ""}`;
    });
    map.on("mouseleave", "adressen-circle", () => {
      map.getCanvas().style.cursor = "";
      tooltip.style.display = "none";
    });

    // Klick → Popup
    map.on("click", "adressen-circle", e => showPopup(e.features[0], e.lngLat));

    // ── Suche ────────────────────────────────────────────────────────────────

    const searchInput = document.getElementById("search-input");
    const searchClear = document.getElementById("search-clear");

    searchInput.addEventListener("input", e => {
      const q = e.target.value;
      searchClear.style.display = q ? "block" : "none";

      clearTimeout(searchDebounceTimer);

      if (q.trim().length < 2) {
        hideResultsPanel();
        if (searchActive) clearSearchDim();
        return;
      }

      searchDebounceTimer = setTimeout(() => {
        const results = performSearch(q);
        showResultsPanel(results, q);
        if (results && results.matchedFeatures.length > 0) {
          activateSearchDim(results.matchedFeatures);
        } else {
          clearSearchDim();
        }
      }, 200);
    });

    searchInput.addEventListener("focus", e => {
      if (e.target.value.trim().length >= 2) {
        const results = performSearch(e.target.value);
        showResultsPanel(results, e.target.value);
      }
    });

    searchInput.addEventListener("keydown", e => {
      if (e.key === "Escape") {
        searchInput.value = "";
        searchClear.style.display = "none";
        hideResultsPanel();
        clearSearchDim();
      }
    });

    searchClear.addEventListener("click", () => {
      searchInput.value = "";
      searchClear.style.display = "none";
      hideResultsPanel();
      clearSearchDim();
      searchInput.focus();
    });

    document.getElementById("btn-back-filter").addEventListener("click", () => {
      searchInput.value = "";
      searchClear.style.display = "none";
      hideResultsPanel();
      clearSearchDim();
    });

    // ── Sidebar-Filter ────────────────────────────────────────────────────

    document.getElementById("filter-stadtteil").addEventListener("change", e => {
      activeFilter.stadtteile = [...e.target.selectedOptions].map(o => o.value);
      applyFilters();
    });

    document.getElementById("filter-akademiker").addEventListener("change", e => {
      activeFilter.nurAkademiker = e.target.checked;
      applyFilters();
    });

    ["I", "II", "III"].forEach(kat => {
      document.getElementById(`kat-${kat}`).addEventListener("change", () => {
        activeFilter.sektionen = ["I", "II", "III"].filter(
          k => document.getElementById(`kat-${k}`).checked
        );
        applyFilters();
      });
    });

    // Berufsgruppen-Checkboxes
    document.getElementById("filter-berufsgruppen").addEventListener("change", () => {
      activeFilter.berufsgruppen = BERUFSGRUPPEN
        .filter(bg => document.getElementById(`bg-${bgSlug(bg.id)}`).checked)
        .map(bg => bg.id);
      applyFilters();
    });

    // Bergbau-Filter (gegenseitig exklusiv)
    document.getElementById("filter-bergbau-narrow").addEventListener("change", e => {
      if (e.target.checked) {
        document.getElementById("filter-bergbau-broad").checked = false;
        activeFilter.bergbauFilter = "narrow";
      } else {
        activeFilter.bergbauFilter = null;
      }
      toggleZechenLayer();
      applyFilters();
    });

    document.getElementById("filter-bergbau-broad").addEventListener("change", e => {
      if (e.target.checked) {
        document.getElementById("filter-bergbau-narrow").checked = false;
        activeFilter.bergbauFilter = "broad";
      } else {
        activeFilter.bergbauFilter = null;
      }
      toggleZechenLayer();
      applyFilters();
    });

    document.getElementById("btn-reset").addEventListener("click", () => {
      activeFilter = { stadtteile: [], nurAkademiker: false, sektionen: ["I", "III"], berufsgruppen: [], bergbauFilter: null };
      document.getElementById("filter-stadtteil").selectedIndex = -1;
      document.getElementById("filter-akademiker").checked = false;
      document.getElementById("filter-bergbau-narrow").checked = false;
      document.getElementById("filter-bergbau-broad").checked = false;
      toggleZechenLayer();
      document.getElementById("kat-I").checked = true;
      document.getElementById("kat-II").checked = false;
      document.getElementById("kat-III").checked = true;
      BERUFSGRUPPEN.forEach(bg => {
        document.getElementById(`bg-${bgSlug(bg.id)}`).checked = false;
      });
      searchInput.value = "";
      searchClear.style.display = "none";
      hideResultsPanel();
      clearSearchDim();
      applyFilters();
    });

    // ── Info-Tooltip positionieren (fixed, schwebt über Karte) ──────────

    const infoBtn = document.querySelector(".info-btn");
    const infoTip = document.querySelector(".info-tooltip");
    if (infoBtn && infoTip) {
      const show = () => {
        const r = infoBtn.getBoundingClientRect();
        infoTip.style.left = (r.right + 8) + "px";
        infoTip.style.top = r.top + "px";
        infoTip.style.display = "block";
      };
      const hide = () => { infoTip.style.display = "none"; };
      infoBtn.addEventListener("mouseenter", show);
      infoBtn.addEventListener("mouseleave", hide);
      infoBtn.addEventListener("focus", show);
      infoBtn.addEventListener("blur", hide);
    }

    // ── Stadtplan 1935 ────────────────────────────────────────────────────

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

  map.on("load", async () => {
    try {
      const geojson = await loadData();
      allFeatures = geojson.features;
      currentFilteredFeatures = allFeatures;

      addHistoricalLayer();
      addLayers();
      loadZechenLayer();
      populateStadtteilFilter(allFeatures);
      populateBerufsgruppFilter();
      setupEvents();

      searchIndex = buildSearchIndex(allFeatures);

      document.getElementById("loading").style.display = "none";
    } catch (err) {
      document.getElementById("loading").innerHTML =
        `<div style="color:red">Fehler beim Laden der Daten:<br>${err.message}</div>`;
      console.error(err);
    }
  });

})();
