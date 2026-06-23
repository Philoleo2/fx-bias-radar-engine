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
  allineateGrid: document.getElementById("allineateGrid"),
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

function showWarning(message) { els.warnings.hidden = false; els.warnings.textContent = message; }
function clearWarning() { els.warnings.hidden = true; els.warnings.textContent = ""; }

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
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", timeZoneName: "short",
  }).format(d);
}

function shiftHours(value, hours) {
  if (!value) return value;
  const t = Date.parse(value);
  if (Number.isNaN(t)) return value;
  return new Date(t + hours * 3600000).toISOString();
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
      headers: { Authorization: "Bearer " + saved }, cache: "no-store",
    });
    if (res.status === 401) { requestToken("Token non valido: inserisci quello corretto."); return; }
    const data = await res.json();
    if (!data.ok) {
      els.dataState.textContent = "Nessun dato";
      showWarning(data.detail || "Pre-Rottura non disponibile.");
      renderAllineate([]);
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
  els.h1Bar.textContent = fmtDateTime(shiftHours(data.h1_last_bar_utc, 1));
  els.h4Bar.textContent = "H4 " + fmtDateTime(shiftHours(data.h4_last_bar_utc, 4));
  els.dataState.textContent = "Aggiornato (orario)";
  const ranking = (data.ranking_h4 || []);
  els.rankingH4.textContent = ranking.length ? ("Forza H4: " + ranking.join(" > ")) : "";
  renderChart(data.lines_h1 || {});
  renderAllineate(data.allineate || []);
}

function renderChart(lines) {
  if (!els.canvas || typeof Chart === "undefined") return;
  const times = (lines.times || []).map(function (t) { return fmtHour(shiftHours(t, 1)); });
  const datasets = (lines.currencies || []).map(function (c) {
    const color = CCY_COLOR[c.ccy] || "#888";
    return {
      label: c.ccy, data: c.series || [], borderColor: color, backgroundColor: color,
      borderWidth: 1.6, pointRadius: 0, tension: 0.25, spanGaps: true,
    };
  });
  if (chart) { chart.destroy(); chart = null; }
  chart = new Chart(els.canvas.getContext("2d"), {
    type: "line",
    data: { labels: times, datasets: datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: "nearest", intersect: false },
      plugins: { legend: { labels: { color: "#cdd3cd", boxWidth: 12 } } },
      scales: {
        x: { ticks: { color: "#8b948b", maxTicksLimit: 10 }, grid: { color: "rgba(255,255,255,.05)" } },
        y: { ticks: { color: "#8b948b" }, grid: { color: "rgba(255,255,255,.05)" } },
      },
    },
  });
}

function alignedCard(row) {
  const isLong = String(row.dir).toUpperCase() === "LONG";
  const col = isLong ? "var(--green)" : "var(--red)";
  const arr = isLong ? "su ↑" : "giù ↓";
  const phrase = '<span style="color:' + col + '; font-weight:600;">Rottura H1 ' + arr
    + "</span>, allineata a daily+weekly " + escapeHtml(String(row.dir).toUpperCase());
  const detail = "Daily E weekly in compressione attiva nella stessa direzione: il segnale piu' selettivo.";
  return '<article class="focus-card">'
    + '<div class="focus-top"><div class="pair">' + escapeHtml(row.pair) + "</div>"
    + dirBadge(String(row.dir).toUpperCase()) + "</div>"
    + '<div class="focus-body">'
    + '<div style="font-size:15px; line-height:1.6; margin:4px 0 10px;">' + phrase + "</div>"
    + '<div class="note">' + detail + "</div>"
    + "</div>"
    + '<p class="focus-action">Incrocia con la tua linea: entra a rottura o ritest.</p>'
    + "</article>";
}

function renderAllineate(allineate) {
  if (!els.allineateGrid) return;
  els.allineateGrid.innerHTML = (allineate && allineate.length)
    ? allineate.map(alignedCard).join("")
    : '<div class="empty">Nessuna rottura allineata a daily + weekly a questa ora</div>';
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

// Auto-aggiornamento ogni 5 minuti.
setInterval(load, 300000);
