const els = {
  status: document.getElementById("statusPill"),
  refresh: document.getElementById("refreshBtn"),
  changeToken: document.getElementById("changeTokenBtn"),
  loginPanel: document.getElementById("loginPanel"),
  tokenInput: document.getElementById("tokenInput"),
  saveToken: document.getElementById("saveTokenBtn"),
  generatedAt: document.getElementById("generatedAt"),
  h1Bar: document.getElementById("h1Bar"),
  h4Bar: document.getElementById("h4Bar"),
  dataState: document.getElementById("dataState"),
  warnings: document.getElementById("warnings"),
  rankingH4: document.getElementById("rankingH4"),
  ripreseGrid: document.getElementById("ripreseGrid"),
  rientriGrid: document.getElementById("rientriGrid"),
  canvas: document.getElementById("linesChart"),
};

const CCY_COLOR = {
  EUR: "#6aa7ff", GBP: "#b78bff", AUD: "#60bd7d", NZD: "#28c2b8",
  USD: "#ef6d72", CAD: "#f2b95d", CHF: "#9aa7b4", JPY: "#e36cc0",
};

let chart = null;

function token() { return localStorage.getItem("fxbr.dashboardToken") || ""; }

function syncAuthUi() {
  const has = Boolean(token());
  els.loginPanel.hidden = has;
  els.changeToken.hidden = !has;
}

function setStatus(label, mode) {
  els.status.textContent = label;
  els.status.className = "status-pill " + mode;
}

function requestToken(message) {
  localStorage.removeItem("fxbr.dashboardToken");
  els.tokenInput.value = "";
  syncAuthUi();
  setStatus("Token richiesto", "idle");
  if (message) showWarning(message);
}

function showWarning(message) {
  els.warnings.hidden = false;
  els.warnings.textContent = message;
}

function clearWarning() {
  els.warnings.hidden = true;
  els.warnings.textContent = "";
}

function escapeHtml(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[ch];
  });
}

function fmtDateTime(value) {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return new Intl.DateTimeFormat("it-IT", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
    timeZoneName: "short",
  }).format(d);
}

function fmtHour(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return new Intl.DateTimeFormat("it-IT", { hour: "2-digit", minute: "2-digit" }).format(d);
}

function dirBadge(dir) {
  const cls = dir === "LONG" ? "long" : dir === "SHORT" ? "short" : "";
  return '<span class="badge ' + cls + '">' + escapeHtml(dir) + "</span>";
}

async function load() {
  const saved = token();
  syncAuthUi();
  if (!saved) { setStatus("Token richiesto", "idle"); return; }
  setStatus("Aggiorno", "loading");
  try {
    const res = await fetch("/api/pre_rottura", {
      headers: { Authorization: "Bearer " + saved },
      cache: "no-store",
    });
    if (res.status === 401) { requestToken("Token non valido: inserisci quello corretto."); return; }
    const data = await res.json();
    if (!data.ok) {
      els.dataState.textContent = "Nessun dato";
      showWarning(data.detail || "Pre-Rottura non disponibile.");
      renderLists([], []);
      setStatus("In attesa cron", "idle");
      return;
    }
    clearWarning();
    render(data);
    setStatus("Aggiornato", "ok");
  } catch (err) {
    setStatus("Errore", "error");
    showWarning((err && err.message) || "Errore di rete.");
  }
}

function render(data) {
  els.generatedAt.textContent = fmtDateTime(data.generated_at_utc);
  els.h1Bar.textContent = fmtDateTime(data.h1_last_bar_utc);
  els.h4Bar.textContent = "H4 " + fmtDateTime(data.h4_last_bar_utc);
  els.dataState.textContent = "Aggiornato (orario)";
  const ranking = (data.ranking_h4 || []);
  els.rankingH4.textContent = ranking.length ? ("Forza H4: " + ranking.join(" > ")) : "";
  renderChart(data.lines_h1 || {});
  renderLists(data.riprese || [], data.rientri || []);
}

function renderChart(lines) {
  if (!els.canvas || typeof Chart === "undefined") return;
  const times = (lines.times || []).map(fmtHour);
  const datasets = (lines.currencies || []).map(function (c) {
    const color = CCY_COLOR[c.ccy] || "#888";
    return {
      label: c.ccy,
      data: c.series || [],
      borderColor: color,
      backgroundColor: color,
      borderWidth: 1.6,
      pointRadius: 0,
      tension: 0.25,
      spanGaps: true,
    };
  });
  if (chart) { chart.destroy(); chart = null; }
  chart = new Chart(els.canvas.getContext("2d"), {
    type: "line",
    data: { labels: times, datasets: datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "nearest", intersect: false },
      plugins: { legend: { labels: { color: "#cdd3cd", boxWidth: 12 } } },
      scales: {
        x: { ticks: { color: "#8b948b", maxTicksLimit: 10 }, grid: { color: "rgba(255,255,255,.05)" } },
        y: { ticks: { color: "#8b948b" }, grid: { color: "rgba(255,255,255,.05)" } },
      },
    },
  });
}

function card(row) {
  const stato = row.stato || "";
  const statoCls = stato === "RIPRESA" ? "tipo-resume" : "tipo-rot";
  const extra = stato === "RIENTRO"
    ? ("contro H4 da " + escapeHtml(row.h1_down_run) + " barre H1")
    : "ripartenza fresca";
  return '<article class="focus-card">'
    + '<div class="focus-top"><div class="pair">' + escapeHtml(row.pair) + "</div>" + dirBadge(row.dir) + "</div>"
    + '<div class="focus-body">'
    + '<div class="focus-row"><span>Stato</span><strong><span class="tipo ' + statoCls + '">' + escapeHtml(stato) + "</span></strong></div>"
    + '<div class="focus-row"><span>Forza H4 (gap)</span><strong>' + escapeHtml(row.gap_h4) + "</strong></div>"
    + '<div class="focus-row"><span>Spread H1</span><strong>' + escapeHtml(row.h1_spread) + "</strong></div>"
    + '<div><span class="note">' + extra + "</span></div>"
    + "</div>"
    + '<p class="focus-action">Disegna le linee, metti un alert, entra a rottura o ritest.</p>'
    + "</article>";
}

function renderLists(riprese, rientri) {
  els.ripreseGrid.innerHTML = riprese.length
    ? riprese.map(card).join("")
    : '<div class="empty">Nessuna ripresa a questa ora</div>';
  els.rientriGrid.innerHTML = rientri.length
    ? rientri.map(card).join("")
    : '<div class="empty">Nessun rientro a questa ora</div>';
}

els.saveToken.addEventListener("click", function () {
  const v = els.tokenInput.value.trim();
  if (!v) return;
  localStorage.setItem("fxbr.dashboardToken", v);
  clearWarning();
  load();
});
els.tokenInput.addEventListener("keydown", function (e) { if (e.key === "Enter") els.saveToken.click(); });
els.refresh.addEventListener("click", load);
els.changeToken.addEventListener("click", function () { requestToken("Token rimosso da questo dispositivo."); });

els.tokenInput.value = token();
syncAuthUi();
load();
