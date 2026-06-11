const els = {
  status: document.getElementById("statusPill"),
  refresh: document.getElementById("refreshBtn"),
  loginPanel: document.getElementById("loginPanel"),
  tokenInput: document.getElementById("tokenInput"),
  saveToken: document.getElementById("saveTokenBtn"),
  changeToken: document.getElementById("changeTokenBtn"),
  lastBar: document.getElementById("lastBar"),
  generatedAt: document.getElementById("generatedAt"),
  source: document.getElementById("source"),
  cacheState: document.getElementById("cacheState"),
  warnings: document.getElementById("warnings"),
  focusGrid: document.getElementById("focusGrid"),
  pairsBody: document.getElementById("pairsBody"),
  downloadJson: document.getElementById("downloadJsonBtn"),
  downloadCsv: document.getElementById("downloadCsvBtn"),
  downloadMd: document.getElementById("downloadMdBtn"),
};

let scanData = null;
let activeFilter = "all";

function token() {
  return localStorage.getItem("fxbr.dashboardToken") || "";
}

function syncAuthUi() {
  const hasToken = Boolean(token());
  els.loginPanel.hidden = hasToken;
  els.changeToken.hidden = !hasToken;
}

function requestToken(message = "") {
  localStorage.removeItem("fxbr.dashboardToken");
  els.tokenInput.value = "";
  syncAuthUi();
  setStatus("Token richiesto", "idle");
  if (message) showWarning(message);
  window.setTimeout(() => els.tokenInput.focus(), 0);
}

function setStatus(label, mode) {
  els.status.textContent = label;
  els.status.className = `status-pill ${mode}`;
}

function formatTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("it-IT", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(date);
}

function biasClass(bias) {
  return String(bias || "").toLowerCase() === "long" ? "long"
    : String(bias || "").toLowerCase() === "short" ? "short"
      : "";
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#039;",
  }[char]));
}

async function loadScan() {
  const saved = token();
  syncAuthUi();
  if (!saved) {
    setStatus("Token richiesto", "idle");
    return;
  }

  setStatus("Aggiorno", "loading");
  try {
    const response = await fetch("/api/scan", {
      headers: { Authorization: `Bearer ${saved}` },
      cache: "no-store",
    });
    const data = await response.json();
    if (response.status === 401) {
      requestToken("Token non valido: inserisci quello corretto.");
      return;
    }
    if (!response.ok || !data.ok) {
      throw new Error(data.detail || data.error || "scan non riuscito");
    }
    scanData = data;
    render(data);
    syncAuthUi();
    setStatus("Online", "ok");
  } catch (error) {
    setStatus("Errore", "error");
    showWarning(error.message || "Errore durante lo scan");
  }
}

function render(data) {
  els.lastBar.textContent = formatTime(data.last_closed_h4_utc);
  els.generatedAt.textContent = formatTime(data.generated_at_utc);
  els.source.textContent = data.source || "-";
  els.cacheState.textContent = data.cache && data.cache.hit ? "hit" : "fresh";
  renderWarnings(data.warnings || []);
  renderFocus(data.focus || []);
  renderPairs(data.pairs || []);
}

function renderWarnings(warnings) {
  if (!warnings.length) {
    els.warnings.hidden = true;
    els.warnings.textContent = "";
    return;
  }
  els.warnings.hidden = false;
  els.warnings.innerHTML = warnings.map(escapeHtml).join("<br>");
}

function showWarning(message) {
  els.warnings.hidden = false;
  els.warnings.textContent = message;
}

function renderFocus(rows) {
  if (!rows.length) {
    els.focusGrid.innerHTML = `<div class="empty">${escapeHtml("Nessuna coppia in focus")}</div>`;
    return;
  }
  els.focusGrid.innerHTML = rows.map((row) => `
    <article class="focus-card">
      <div class="focus-top">
        <div class="pair">${escapeHtml(row.pair)}</div>
        <span class="badge ${biasClass(row.bias)}">${escapeHtml(row.bias)}</span>
      </div>
      <div class="focus-body">
        <div class="focus-row"><span>Tipo</span><strong>${escapeHtml(row.tipo)} <span class="state">${escapeHtml(row.stato)}</span></strong></div>
        <div class="focus-row"><span>Score</span><strong>${escapeHtml(row.score)}</strong></div>
        <div class="focus-row"><span>Spread</span><strong>${Number(row.spread || 0).toFixed(2)}</strong></div>
        <div class="strength-row"><span>Forza</span><strong>${escapeHtml(row.forte)} / ${escapeHtml(row.debole)}</strong></div>
        <div><span class="note">${escapeHtml(row.note)}</span></div>
      </div>
      <p class="focus-action">Controlla TradingView, linee manuali e timing ATC.</p>
    </article>
  `).join("");
}

function renderPairs(rows) {
  const focusPairs = new Set((scanData?.focus || []).map((row) => row.pair));
  const filtered = rows.filter((row) => {
    if (activeFilter === "all") return true;
    if (activeFilter === "focus") return focusPairs.has(row.pair);
    if (activeFilter === "flat") return row.bias === "-";
    return row.bias === activeFilter;
  });

  els.pairsBody.innerHTML = filtered.map((row) => `
    <tr>
      <td><strong>${escapeHtml(row.pair)}</strong></td>
      <td><span class="cell-bias ${biasClass(row.bias)}">${escapeHtml(row.bias)}</span></td>
      <td>${escapeHtml(row.tipo)}</td>
      <td>${escapeHtml(row.stato)}</td>
      <td>${escapeHtml(row.score)}</td>
      <td>${escapeHtml(row.forte)}</td>
      <td>${escapeHtml(row.debole)}</td>
      <td>${row.spread == null ? "-" : Number(row.spread).toFixed(2)}</td>
      <td>${escapeHtml(row.note)}</td>
    </tr>
  `).join("");
}

function download(name, content, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function csvFromRows(rows) {
  const fields = ["pair", "bias", "tipo", "stato", "score", "forte", "debole", "spread", "note", "age"];
  const quote = (value) => `"${String(value ?? "").replace(/"/g, '""')}"`;
  return [
    fields.join(","),
    ...rows.map((row) => fields.map((field) => quote(row[field])).join(",")),
  ].join("\n");
}

els.saveToken.addEventListener("click", () => {
  const value = els.tokenInput.value.trim();
  if (!value) return;
  localStorage.setItem("fxbr.dashboardToken", value);
  els.warnings.hidden = true;
  els.warnings.textContent = "";
  loadScan();
});

els.tokenInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") els.saveToken.click();
});

els.refresh.addEventListener("click", loadScan);

els.changeToken.addEventListener("click", () => {
  requestToken("Token rimosso da questo dispositivo.");
});

document.querySelectorAll(".filter").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".filter").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    activeFilter = button.dataset.filter;
    renderPairs(scanData?.pairs || []);
  });
});

els.downloadJson.addEventListener("click", () => {
  if (!scanData) return;
  download("fx-bias-radar-scan.json", JSON.stringify(scanData, null, 2), "application/json");
});

els.downloadCsv.addEventListener("click", () => {
  if (!scanData) return;
  download("fx-bias-radar-pairs.csv", csvFromRows(scanData.pairs || []), "text/csv");
});

els.downloadMd.addEventListener("click", () => {
  if (!scanData) return;
  download("fx-bias-radar-report.md", scanData.markdown || "", "text/markdown");
});

els.tokenInput.value = token();
syncAuthUi();
loadScan();
