const els = {
  status: document.getElementById("statusPill"),
  refresh: document.getElementById("refreshBtn"),
  previewToggle: document.getElementById("previewToggle"),
  loginPanel: document.getElementById("loginPanel"),
  tokenInput: document.getElementById("tokenInput"),
  saveToken: document.getElementById("saveTokenBtn"),
  changeToken: document.getElementById("changeTokenBtn"),
  barLabel: document.getElementById("barLabel"),
  lastBar: document.getElementById("lastBar"),
  generatedAt: document.getElementById("generatedAt"),
  source: document.getElementById("source"),
  cacheState: document.getElementById("cacheState"),
  warnings: document.getElementById("warnings"),
  eventsBody: document.getElementById("eventsBody"),
  liveMoveSection: document.getElementById("liveMoveSection"),
  liveMoveBody: document.getElementById("liveMoveBody"),
  focusGrid: document.getElementById("focusGrid"),
  pairsBody: document.getElementById("pairsBody"),
  downloadJson: document.getElementById("downloadJsonBtn"),
  downloadCsv: document.getElementById("downloadCsvBtn"),
  downloadMd: document.getElementById("downloadMdBtn"),
};

let scanData = null;
let intraData = null;
let activeFilter = "all";

// Termini italiani per le NOTE del motore (display-only).
const NOTE_IT = {
  fresh: "NUOVO",
  strong: "FORTE",
  watch: "OSSERVA",
  current: "CORRENTE",
  flat: "PIATTO",
};

function token() {
  return localStorage.getItem("fxbr.dashboardToken") || "";
}

function previewOn() {
  return localStorage.getItem("fxbr.previewIntrabar") === "1";
}

function syncAuthUi() {
  const hasToken = Boolean(token());
  els.loginPanel.hidden = hasToken;
  els.changeToken.hidden = !hasToken;
}

function requestToken(message) {
  localStorage.removeItem("fxbr.dashboardToken");
  els.tokenInput.value = "";
  syncAuthUi();
  setStatus("Token richiesto", "idle");
  if (message) showWarning(message);
  window.setTimeout(function () { els.tokenInput.focus(); }, 0);
}

function setStatus(label, mode) {
  els.status.textContent = label;
  els.status.className = "status-pill " + mode;
}

function isLivePayload(data) {
  return Boolean(data && data.is_live === true && data.data_status === "live"
    && String(data.source || "").toLowerCase().indexOf("oanda ") === 0);
}

function setLiveState(isLive, cacheHit) {
  els.cacheState.textContent = isLive ? (cacheHit ? "LIVE OANDA (cache)" : "LIVE OANDA") : "NON LIVE";
  els.cacheState.className = isLive ? "live-ok" : "live-error";
}

function clearOperationalData(message) {
  scanData = null;
  intraData = null;
  els.lastBar.textContent = "-";
  els.generatedAt.textContent = "-";
  els.source.textContent = "-";
  setLiveState(false, false);
  showWarning(message);
  els.eventsBody.innerHTML = '<tr><td colspan="6" class="empty-cell danger">Dati live non disponibili.</td></tr>';
  els.focusGrid.innerHTML = '<div class="empty danger">Dati live non disponibili. Non usare il radar per decidere.</div>';
  els.pairsBody.innerHTML = "";
  els.liveMoveSection.hidden = true;
  els.liveMoveBody.innerHTML = "";
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
  const b = String(bias || "").toLowerCase();
  return b === "long" ? "long" : b === "short" ? "short" : "";
}

function dirLabel(bias) {
  const b = String(bias || "").toUpperCase();
  return (b === "LONG" || b === "SHORT") ? b : "NESSUNO";
}

function noteIt(value) {
  const k = String(value || "").toLowerCase();
  return NOTE_IT[k] || (value || "");
}

function spreadNum(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function fmtSpread(value) {
  return value == null ? "" : Number(value).toFixed(2);
}

function escapeHtml(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
    return {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    }[char];
  });
}

function fetchScan(mode, saved) {
  return fetch("/api/scan?mode=" + mode, {
    headers: { Authorization: "Bearer " + saved },
    cache: "no-store",
  }).then(function (response) {
    if (response.status === 401) return "unauth";
    return response.json().then(function (data) {
      if (!response.ok || !data.ok) {
        throw new Error(data.detail || data.error || "Dati live OANDA non disponibili");
      }
      return data;
    });
  });
}

async function loadScan() {
  const saved = token();
  syncAuthUi();
  els.previewToggle.checked = previewOn();
  if (!saved) {
    setStatus("Token richiesto", "idle");
    return;
  }

  setStatus("Aggiorno", "loading");
  try {
    // Dato OPERATIVO sempre su barra chiusa (no repaint, FR039).
    const closed = await fetchScan("closed", saved);
    if (closed === "unauth") {
      requestToken("Token non valido: inserisci quello corretto.");
      return;
    }
    if (!isLivePayload(closed)) {
      clearOperationalData("Dati non live bloccati: aggiorna piu' tardi.");
      setStatus("Non live", "error");
      return;
    }
    scanData = closed;

    // Anteprima intrabar SOLO se richiesta: seconda chiamata, usata solo per
    // la spia di movimento. Le tabelle operative restano sul closed.
    let intra = null;
    if (previewOn()) {
      try {
        const r = await fetchScan("intrabar", saved);
        if (r && r !== "unauth" && isLivePayload(r)) intra = r;
      } catch (e) {
        intra = null;
      }
    }
    intraData = intra;

    render(closed, intra);
    syncAuthUi();
    setStatus(previewOn() && intra ? "Live + anteprima" : "Live OANDA", "ok");
  } catch (error) {
    setStatus("Non live", "error");
    clearOperationalData(error.message || "Dati live OANDA non disponibili");
  }
}

function render(data, intra) {
  const isForming = data.bar_status === "forming";
  els.barLabel.textContent = isForming ? "H4 in corso, chiude" : "Ultima H4 chiusa";
  els.lastBar.textContent = formatTime(isForming ? data.analyzed_h4_close_utc : data.last_closed_h4_utc);
  els.generatedAt.textContent = formatTime(data.generated_at_utc);
  els.source.textContent = data.source || "-";
  setLiveState(true, Boolean(data.cache && data.cache.hit));

  const warnings = (data.warnings || []).slice();
  if (isForming) {
    warnings.unshift("Attenzione: dato operativo su barra in formazione (atteso solo barra chiusa).");
  }
  renderWarnings(warnings);

  renderEvents(data.events_this_bar || []);
  renderFocus(data.focus || []);
  renderPairs(data.pairs || []);

  if (previewOn() && intra) {
    renderLiveMove(computeLiveMoves(data.pairs || [], intra.pairs || []));
    els.liveMoveSection.hidden = false;
  } else {
    els.liveMoveSection.hidden = true;
    els.liveMoveBody.innerHTML = "";
  }
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

function rowCells(values) {
  return values.map(function (v) { return "<td>" + v + "</td>"; }).join("");
}

function biasCell(bias) {
  return '<span class="cell-bias ' + biasClass(bias) + '">' + escapeHtml(dirLabel(bias)) + "</span>";
}

function renderEvents(rows) {
  if (!rows.length) {
    els.eventsBody.innerHTML = '<tr><td colspan="6" class="empty-cell">Nessun nuovo evento a questa chiusura</td></tr>';
    return;
  }
  els.eventsBody.innerHTML = rows.map(function (r) {
    const tipo = '<span class="tipo tipo-' + escapeHtml(String(r.tipo || "").toLowerCase()) + '">' + escapeHtml(r.tipo) + "</span>";
    const stato = '<span class="state">' + escapeHtml(r.stato) + "</span>";
    const spread = r.spread == null ? "-" : Number(r.spread).toFixed(2);
    return '<tr class="event-row">'
      + "<td><strong>" + escapeHtml(r.pair) + "</strong></td>"
      + "<td>" + biasCell(r.bias) + "</td>"
      + "<td>" + tipo + "</td>"
      + "<td>" + stato + "</td>"
      + "<td>" + escapeHtml(r.score) + "</td>"
      + "<td>" + spread + "</td>"
      + "</tr>";
  }).join("");
}

function computeLiveMoves(closedPairs, intraPairs) {
  const intraByPair = {};
  intraPairs.forEach(function (r) { intraByPair[r.pair] = r; });
  const moves = [];
  closedPairs.forEach(function (c) {
    const i = intraByPair[c.pair];
    if (!i) return;
    const cd = biasClass(c.bias) ? String(c.bias).toUpperCase() : "";
    const id = biasClass(i.bias) ? String(i.bias).toUpperCase() : "";
    const cs = spreadNum(c.spread);
    const is = spreadNum(i.spread);
    let kind = null;
    let weight = 0;
    if (cd && id && cd !== id) {
      kind = "INVERSIONE";
      weight = 1000 + is;
    } else if (id && (is - cs >= 0.5 || (cs < 1.0 && is >= 1.0))) {
      kind = "RAFFORZAMENTO";
      weight = is;
    }
    if (kind) moves.push({ pair: c.pair, closed: c, intra: i, kind: kind, weight: weight });
  });
  moves.sort(function (a, b) { return b.weight - a.weight; });
  return moves.slice(0, 6);
}

function moveCell(row) {
  return '<span class="cell-bias ' + biasClass(row.bias) + '">'
    + escapeHtml(dirLabel(row.bias)) + " " + escapeHtml(fmtSpread(row.spread)) + "</span>";
}

function renderLiveMove(moves) {
  if (!moves.length) {
    els.liveMoveBody.innerHTML = '<tr><td colspan="4" class="empty-cell">Nessun movimento rilevante rispetto alla barra chiusa</td></tr>';
    return;
  }
  els.liveMoveBody.innerHTML = moves.map(function (m) {
    const spia = '<span class="spia ' + (m.kind === "INVERSIONE" ? "spia-inv" : "spia-raf") + '">' + escapeHtml(m.kind) + "</span>";
    return "<tr>"
      + "<td><strong>" + escapeHtml(m.pair) + "</strong></td>"
      + "<td>" + moveCell(m.closed) + "</td>"
      + "<td>" + moveCell(m.intra) + "</td>"
      + "<td>" + spia + "</td>"
      + "</tr>";
  }).join("");
}

function renderFocus(rows) {
  if (!rows.length) {
    els.focusGrid.innerHTML = '<div class="empty">Nessuna coppia da seguire</div>';
    return;
  }
  els.focusGrid.innerHTML = rows.map(function (row) {
    const spread = Number(row.spread || 0).toFixed(2);
    return '<article class="focus-card">'
      + '<div class="focus-top">'
      + '<div class="pair">' + escapeHtml(row.pair) + "</div>"
      + '<span class="badge ' + biasClass(row.bias) + '">' + escapeHtml(dirLabel(row.bias)) + "</span>"
      + "</div>"
      + '<div class="focus-body">'
      + '<div class="focus-row"><span>Tipo</span><strong>' + escapeHtml(row.tipo) + ' <span class="state">' + escapeHtml(row.stato) + "</span></strong></div>"
      + '<div class="focus-row"><span>Score</span><strong>' + escapeHtml(row.score) + "</strong></div>"
      + '<div class="focus-row"><span>Spread</span><strong>' + spread + "</strong></div>"
      + '<div class="strength-row"><span>Forza</span><strong>' + escapeHtml(row.forte) + " / " + escapeHtml(row.debole) + "</strong></div>"
      + '<div><span class="note">' + escapeHtml(noteIt(row.note)) + "</span></div>"
      + "</div>"
      + '<p class="focus-action">Apri TradingView: guarda le linee da rompere e attendi il movimento a campana.</p>'
      + "</article>";
  }).join("");
}

function renderPairs(rows) {
  const focusPairs = {};
  ((scanData && scanData.focus) || []).forEach(function (row) { focusPairs[row.pair] = true; });
  const filtered = rows.filter(function (row) {
    if (activeFilter === "all") return true;
    if (activeFilter === "focus") return Boolean(focusPairs[row.pair]);
    if (activeFilter === "flat") return row.bias === "-";
    return row.bias === activeFilter;
  });

  els.pairsBody.innerHTML = filtered.map(function (row) {
    const spread = row.spread == null ? "-" : Number(row.spread).toFixed(2);
    return "<tr>"
      + "<td><strong>" + escapeHtml(row.pair) + "</strong></td>"
      + "<td>" + biasCell(row.bias) + "</td>"
      + "<td>" + escapeHtml(row.tipo) + "</td>"
      + "<td>" + escapeHtml(row.stato) + "</td>"
      + "<td>" + escapeHtml(row.score) + "</td>"
      + "<td>" + escapeHtml(row.forte) + "</td>"
      + "<td>" + escapeHtml(row.debole) + "</td>"
      + "<td>" + spread + "</td>"
      + "<td>" + escapeHtml(noteIt(row.note)) + "</td>"
      + "</tr>";
  }).join("");
}

function download(name, content, type) {
  const blob = new Blob([content], { type: type });
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
  const quote = function (value) { return '"' + String(value == null ? "" : value).replace(/"/g, '""') + '"'; };
  return [fields.join(",")].concat(rows.map(function (row) {
    return fields.map(function (field) { return quote(row[field]); }).join(",");
  })).join("\n");
}

els.saveToken.addEventListener("click", function () {
  const value = els.tokenInput.value.trim();
  if (!value) return;
  localStorage.setItem("fxbr.dashboardToken", value);
  els.warnings.hidden = true;
  els.warnings.textContent = "";
  loadScan();
});

els.tokenInput.addEventListener("keydown", function (event) {
  if (event.key === "Enter") els.saveToken.click();
});

els.refresh.addEventListener("click", loadScan);

els.changeToken.addEventListener("click", function () {
  requestToken("Token rimosso da questo dispositivo.");
});

els.previewToggle.addEventListener("change", function () {
  localStorage.setItem("fxbr.previewIntrabar", els.previewToggle.checked ? "1" : "0");
  loadScan();
});

document.querySelectorAll(".filter").forEach(function (button) {
  button.addEventListener("click", function () {
    document.querySelectorAll(".filter").forEach(function (item) { item.classList.remove("active"); });
    button.classList.add("active");
    activeFilter = button.dataset.filter;
    renderPairs((scanData && scanData.pairs) || []);
  });
});

els.downloadJson.addEventListener("click", function () {
  if (!scanData) return;
  download("fx-bias-radar-scan.json", JSON.stringify(scanData, null, 2), "application/json");
});

els.downloadCsv.addEventListener("click", function () {
  if (!scanData) return;
  download("fx-bias-radar-pairs.csv", csvFromRows(scanData.pairs || []), "text/csv");
});

els.downloadMd.addEventListener("click", function () {
  if (!scanData) return;
  download("fx-bias-radar-report.md", scanData.markdown || "", "text/markdown");
});

els.tokenInput.value = token();
els.previewToggle.checked = previewOn();
syncAuthUi();
loadScan();
