/* statistik.js – Chart.js Diagramme für Adressbuch Essen 1936 */

(function () {
  "use strict";

  const PALETTE = [
    "#1a3a5c", "#2a5a8c", "#3b82f6", "#60a5fa",
    "#22c55e", "#4ade80", "#f97316", "#fb923c",
    "#ef4444", "#f87171", "#a855f7", "#c084fc",
    "#14b8a6", "#2dd4bf", "#eab308", "#facc15",
    "#64748b", "#94a3b8", "#1d4ed8", "#6366f1",
  ];

  function makeColor(i) {
    return PALETTE[i % PALETTE.length];
  }

  function horizontalBarChart(canvasId, labels, values, label) {
    const ctx = document.getElementById(canvasId).getContext("2d");
    new Chart(ctx, {
      type: "bar",
      data: {
        labels,
        datasets: [{
          label,
          data: values,
          backgroundColor: labels.map((_, i) => makeColor(i)),
          borderWidth: 0,
          borderRadius: 3,
        }],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => ` ${ctx.parsed.x.toLocaleString("de-DE")} Einträge`,
            },
          },
        },
        scales: {
          x: {
            grid: { color: "rgba(0,0,0,0.06)" },
            ticks: { font: { size: 11 } },
          },
          y: {
            ticks: { font: { size: 12 } },
          },
        },
      },
    });
  }

  function verticalBarChart(canvasId, labels, values, label) {
    const ctx = document.getElementById(canvasId).getContext("2d");
    new Chart(ctx, {
      type: "bar",
      data: {
        labels,
        datasets: [{
          label,
          data: values,
          backgroundColor: labels.map((_, i) => makeColor(i)),
          borderWidth: 0,
          borderRadius: 3,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => ` ${ctx.parsed.y.toLocaleString("de-DE")} Einträge`,
            },
          },
        },
        scales: {
          x: {
            ticks: {
              font: { size: 10 },
              maxRotation: 45,
              minRotation: 30,
            },
          },
          y: {
            grid: { color: "rgba(0,0,0,0.06)" },
            ticks: {
              font: { size: 11 },
              callback: v => v.toLocaleString("de-DE"),
            },
          },
        },
      },
    });
  }

  fetch("data/statistiken.json")
    .then(r => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    })
    .then(data => {
      document.getElementById("loading-stats").style.display = "none";
      document.getElementById("charts-container").style.display = "block";

      // Top Berufe
      const topBerufe = data.top_berufe || [];
      horizontalBarChart(
        "chart-berufe",
        topBerufe.map(([name]) => name),
        topBerufe.map(([, n]) => n),
        "Anzahl"
      );

      // Top Nachnamen
      const topNachnamen = data.top_nachnamen || [];
      horizontalBarChart(
        "chart-nachnamen",
        topNachnamen.map(([name]) => name),
        topNachnamen.map(([, n]) => n),
        "Anzahl"
      );

      // Stadtteile – Top 25, vertikales Balkendiagramm
      const stadtteile = (data.stadtteile || []).slice(0, 25);
      verticalBarChart(
        "chart-stadtteile",
        stadtteile.map(([name]) => name),
        stadtteile.map(([, n]) => n),
        "Einträge"
      );
    })
    .catch(err => {
      document.getElementById("loading-stats").innerHTML =
        `<div style="color:red">Fehler beim Laden: ${err.message}<br>
        Bitte Website über einen HTTP-Server aufrufen (z.B. python3 -m http.server 8000)</div>`;
    });

})();
