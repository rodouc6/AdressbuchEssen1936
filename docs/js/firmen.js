/* firmen.js – Durchsuchbares Firmenverzeichnis */

(function () {
  "use strict";

  const PER_PAGE = 100;
  let allData = [];
  let filtered = [];
  let sortCol = "firmenname";
  let sortAsc = true;
  let currentPage = 1;

  function escHtml(s) {
    if (!s) return "";
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function preprocess(data) {
    for (const d of data) {
      d._search = [d.firmenname, d.branche, d.nachname, d.vorname, d.adresse]
        .filter(Boolean).join(" ").toLowerCase();
    }
  }

  function doSearch(query) {
    const q = query.trim().toLowerCase();
    if (q.length < 1) {
      filtered = allData;
    } else {
      filtered = allData.filter(d => d._search.includes(q));
    }
    currentPage = 1;
    doSort();
  }

  function doSort() {
    filtered.sort((a, b) => {
      const va = (a[sortCol] || "").toLowerCase();
      const vb = (b[sortCol] || "").toLowerCase();
      if (va < vb) return sortAsc ? -1 : 1;
      if (va > vb) return sortAsc ? 1 : -1;
      return 0;
    });
    render();
  }

  function render() {
    const tbody = document.getElementById("db-tbody");
    const countEl = document.getElementById("db-count");
    const totalPages = Math.max(1, Math.ceil(filtered.length / PER_PAGE));
    if (currentPage > totalPages) currentPage = totalPages;

    countEl.textContent = filtered.length.toLocaleString("de-DE") + " Einträge";

    const start = (currentPage - 1) * PER_PAGE;
    const slice = filtered.slice(start, start + PER_PAGE);

    const rows = slice.map(d => `<tr>
      <td>${escHtml(d.firmenname)}</td>
      <td>${escHtml(d.branche)}</td>
      <td>${escHtml(d.nachname)}${d.vorname ? ", " + escHtml(d.vorname) : ""}</td>
      <td>${escHtml(d.adresse)}</td>
      <td>${escHtml(d.seite)}</td>
    </tr>`).join("");

    tbody.innerHTML = rows;
    renderPagination(totalPages);
    updateSortArrows();
  }

  function renderPagination(totalPages) {
    const container = document.getElementById("db-pagination");
    if (totalPages <= 1) { container.innerHTML = ""; return; }

    const btns = [];
    btns.push(`<button ${currentPage === 1 ? "disabled" : ""} data-page="${currentPage - 1}">&laquo;</button>`);

    const range = paginationRange(currentPage, totalPages);
    for (const p of range) {
      if (p === "...") {
        btns.push(`<span style="padding:0 0.3rem">…</span>`);
      } else {
        btns.push(`<button class="${p === currentPage ? "active" : ""}" data-page="${p}">${p}</button>`);
      }
    }

    btns.push(`<button ${currentPage === totalPages ? "disabled" : ""} data-page="${currentPage + 1}">&raquo;</button>`);
    container.innerHTML = btns.join("");

    container.querySelectorAll("button[data-page]").forEach(btn => {
      btn.addEventListener("click", () => {
        currentPage = parseInt(btn.dataset.page, 10);
        render();
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
    });
  }

  function paginationRange(current, total) {
    const delta = 2;
    const range = [];
    for (let i = 1; i <= total; i++) {
      if (i === 1 || i === total || (i >= current - delta && i <= current + delta)) {
        range.push(i);
      }
    }
    const result = [];
    let prev = 0;
    for (const i of range) {
      if (prev && i - prev > 1) result.push("...");
      result.push(i);
      prev = i;
    }
    return result;
  }

  function updateSortArrows() {
    document.querySelectorAll(".db-table th").forEach(th => {
      const col = th.dataset.col;
      th.classList.toggle("sorted", col === sortCol);
      const arrow = th.querySelector(".sort-arrow");
      if (col === sortCol) {
        arrow.textContent = sortAsc ? "\u25B2" : "\u25BC";
      } else {
        arrow.textContent = "\u25B2";
      }
    });
  }

  // Init
  fetch("data/firmen.json")
    .then(r => r.json())
    .then(data => {
      allData = data;
      preprocess(allData);
      filtered = allData;
      doSort();

      document.getElementById("db-loading").style.display = "none";
      document.getElementById("db-content").style.display = "";

      document.getElementById("db-search").addEventListener("input", e => {
        doSearch(e.target.value);
      });

      document.querySelectorAll(".db-table th[data-col]").forEach(th => {
        th.addEventListener("click", () => {
          const col = th.dataset.col;
          if (sortCol === col) {
            sortAsc = !sortAsc;
          } else {
            sortCol = col;
            sortAsc = true;
          }
          doSort();
        });
      });
    })
    .catch(err => {
      document.getElementById("db-loading").innerHTML =
        `<div style="color:red">Fehler beim Laden: ${err.message}</div>`;
    });

})();
