/* PREWAKE — cronologia operativa degli ultimi 20 giorni.
   Usa lo snapshot read-only esistente: nessuna modifica a motore, workflow o email. */
(function () {
  "use strict";

  var DAYS_MS = 20 * 24 * 60 * 60 * 1000;
  var payload = null;
  var historyRows = [];
  var windowStart = null;
  var windowEnd = null;

  var els = {
    list: document.getElementById("list"),
    status: document.getElementById("status"),
    tokenInput: document.getElementById("tokenInput"),
    saveToken: document.getElementById("saveToken"),
    callCount: document.getElementById("callCount"),
    period: document.getElementById("period"),
    fPair: document.getElementById("fPair"),
    fDir: document.getElementById("fDir"),
    fType: document.getElementById("fType")
  };

  function token() {
    return localStorage.getItem("fxbr.dashboardToken") || "";
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
    });
  }

  function validDate(value) {
    var date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  function barClose(barOpenUtc) {
    var date = validDate(barOpenUtc);
    if (!date) return null;
    return new Date(date.getTime() + 60 * 60 * 1000);
  }

  function formatRome(date, withYear) {
    if (!date) return "—";
    var options = {
      timeZone: "Europe/Rome",
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit"
    };
    if (withYear) options.year = "numeric";
    return date.toLocaleString("it-IT", options);
  }

  function eventLabel(type) {
    var labels = {
      NEW_WAKE: "NUOVA CHIAMATA",
      REAWAKENING: "RISVEGLIO"
    };
    return labels[type] || String(type || "CHIAMATA").replace(/_/g, " ");
  }

  function emailLabel(status) {
    var value = String(status || "").toUpperCase();
    if (value === "SENT") return { text: "Email inviata", style: "ok" };
    if (value === "PENDING" || value === "RETRY") return { text: "Email in attesa", style: "wait" };
    if (value === "FAILED" || value === "ERROR") return { text: "Email non inviata", style: "error" };
    return { text: "Stato email non disponibile", style: "wait" };
  }

  function periodAnchor(data) {
    return validDate(data.last_complete_h1_utc) || validDate(data.generated_at_utc) || new Date();
  }

  function buildHistory(data) {
    windowEnd = periodAnchor(data);
    windowStart = new Date(windowEnd.getTime() - DAYS_MS);
    historyRows = (data.events || []).filter(function (event) {
      var opened = validDate(event.bar_time_utc);
      return event.is_prospective === true && event.is_backfill !== true && opened &&
        opened >= windowStart && opened <= windowEnd;
    }).sort(function (left, right) {
      var timeDiff = new Date(right.bar_time_utc).getTime() - new Date(left.bar_time_utc).getTime();
      return timeDiff || String(left.pair || "").localeCompare(String(right.pair || ""));
    });
  }

  function card(event) {
    var direction = event.direction === "LONG" ? "LONG" : "SHORT";
    var email = emailLabel(event.email_status);
    var close = barClose(event.bar_time_utc);
    return '<article class="ph-card">' +
      '<div class="ph-card-top"><div>' +
      '<div class="ph-pair">' + escapeHtml(event.pair) + '</div>' +
      '<div class="ph-pressure">Pressione sperimentale: ' + direction + '</div>' +
      '</div><div class="ph-event">' + escapeHtml(eventLabel(event.event_type)) + '</div></div>' +
      '<div class="ph-meta"><div><span>Chiusura H1 · ora di Roma</span>' +
      '<strong><time datetime="' + escapeHtml(close ? close.toISOString() : "") + '">' + escapeHtml(formatRome(close, true)) + '</time></strong></div>' +
      '<div><span>Notifica</span><strong class="ph-email ' + email.style + '">' + escapeHtml(email.text) + '</strong></div></div>' +
      '</article>';
  }

  function fillOptions() {
    var pairs = {};
    var types = {};
    historyRows.forEach(function (event) {
      pairs[event.pair] = true;
      types[event.event_type] = true;
    });
    els.fPair.innerHTML = '<option value="">tutte le coppie</option>';
    els.fType.innerHTML = '<option value="">tutti i tipi di chiamata</option>';
    Object.keys(pairs).sort().forEach(function (value) {
      els.fPair.insertAdjacentHTML("beforeend", '<option value="' + escapeHtml(value) + '">' + escapeHtml(value) + '</option>');
    });
    Object.keys(types).sort().forEach(function (value) {
      els.fType.insertAdjacentHTML("beforeend", '<option value="' + escapeHtml(value) + '">' + escapeHtml(eventLabel(value)) + '</option>');
    });
  }

  function render() {
    var pair = els.fPair.value;
    var direction = els.fDir.value;
    var type = els.fType.value;
    var filtered = historyRows.filter(function (event) {
      return (!pair || event.pair === pair) &&
        (!direction || event.direction === direction) &&
        (!type || event.event_type === type);
    });

    els.callCount.textContent = String(filtered.length);
    els.period.textContent = formatRome(windowStart, false) + " — " + formatRome(windowEnd, false);
    els.list.innerHTML = filtered.length
      ? filtered.map(card).join("")
      : '<div class="ph-empty">Nessuna chiamata PREWAKE prospettica negli ultimi 20 giorni per questi filtri.</div>';
  }

  function renderStatus() {
    var events = payload.events || [];
    var oldest = events.reduce(function (result, event) {
      var date = validDate(event.bar_time_utc);
      return date && (!result || date < result) ? date : result;
    }, null);
    var possiblyLimited = events.length >= 200 && oldest && oldest > windowStart;
    els.status.className = "ph-status" + (possiblyLimited ? " warning" : "");
    els.status.textContent = possiblyLimited
      ? "Attenzione: la fonte ha raggiunto il limite di 200 eventi; il periodo potrebbe non essere completo."
      : "Aggiornato all’ultima H1 completa: " + formatRome(windowEnd, true) + ". Orari mostrati in Europe/Rome.";
  }

  function load() {
    var saved = token();
    if (!saved) {
      els.status.textContent = "Inserisci il dashboard token per vedere le chiamate.";
      return;
    }
    els.status.textContent = "Caricamento chiamate…";
    fetch("/api/prewake", {
      headers: { Authorization: "Bearer " + saved },
      cache: "no-store"
    }).then(function (response) {
      if (response.status === 401) throw new Error("token non valido");
      if (!response.ok) throw new Error("servizio temporaneamente non disponibile");
      return response.json();
    }).then(function (data) {
      if (data.ok === false) throw new Error(data.detail || data.error || "dati PREWAKE non disponibili");
      payload = data;
      buildHistory(data);
      fillOptions();
      render();
      renderStatus();
    }).catch(function (error) {
      els.list.innerHTML = '<div class="ph-empty">Impossibile caricare le chiamate.</div>';
      els.status.className = "ph-status warning";
      els.status.textContent = "Errore: " + error.message;
    });
  }

  els.saveToken.addEventListener("click", function () {
    var value = els.tokenInput.value.trim();
    if (value) {
      localStorage.setItem("fxbr.dashboardToken", value);
      load();
    }
  });
  els.tokenInput.addEventListener("keydown", function (event) {
    if (event.key === "Enter") els.saveToken.click();
  });
  [els.fPair, els.fDir, els.fType].forEach(function (element) {
    element.addEventListener("change", render);
  });

  els.tokenInput.value = token();
  load();
})();
