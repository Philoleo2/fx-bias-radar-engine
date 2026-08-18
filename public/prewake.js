/* PREWAKE — minimal mobile-first view.
   Deliberately NOT a research dashboard (SS43): pair, direction, event, time,
   FX Bias present/absent, optional dual-leg badge. No coefficients, no PCA,
   no regression diagnostics. */
(function () {
  "use strict";

  var els = {
    list: document.getElementById("list"),
    status: document.getElementById("status"),
    tokenInput: document.getElementById("tokenInput"),
    saveToken: document.getElementById("saveToken"),
    fDate: document.getElementById("fDate"),
    fPair: document.getElementById("fPair"),
    fDir: document.getElementById("fDir"),
    fType: document.getElementById("fType"),
    fSample: document.getElementById("fSample"),
    fFx: document.getElementById("fFx")
  };

  var payload = null;

  function token() { return localStorage.getItem("fxbr.dashboardToken") || ""; }

  function romeClose(barOpenUtc) {
    // The alert refers to the H1 CLOSE, one hour after the bar open.
    var d = new Date(barOpenUtc);
    d.setUTCHours(d.getUTCHours() + 1);
    return d.toLocaleString("it-IT", {
      timeZone: "Europe/Rome", day: "2-digit", month: "2-digit",
      hour: "2-digit", minute: "2-digit"
    });
  }

  function hhmm(barOpenUtc) {
    var d = new Date(barOpenUtc);
    d.setUTCHours(d.getUTCHours() + 1);
    return d.toLocaleTimeString("it-IT", { timeZone: "Europe/Rome", hour: "2-digit", minute: "2-digit" });
  }

  function card(e) {
    var side = e.direction === "LONG" ? "pw-long" : "pw-short";
    var badges = "";
    if (e.dual_leg) badges += '<span class="pw-badge dual">DUAL LEG</span>';
    if (e.is_backfill) badges += '<span class="pw-badge backfill">BACKFILL</span>';
    if (e.same_bar_raw_breakout) badges += '<span class="pw-badge samebar">SAME BAR</span>';

    var link = e.fx_bias_link;
    var meta;
    if (link && link.fx_bias_time) {
      meta = "PREWAKE " + hhmm(e.bar_time_utc) +
             "<br>FX BIAS " + hhmm(link.fx_bias_time) +
             "<br>Lead: " + Math.round(link.lead_hours) + " H1";
    } else {
      meta = romeClose(e.bar_time_utc) +
             "<br>FX Bias: " + (e.fx_bias_same ? "sì" : "—");
    }
    return '<div class="pw-card">' + badges +
      '<div class="pw-pair">' + e.pair + "</div>" +
      '<div class="pw-dir ' + side + '">' + e.direction + " DA OSSERVARE</div>" +
      '<div class="pw-meta">' + meta + "</div></div>";
  }

  function apply() {
    if (!payload) return;
    var rows = (payload.events || []).slice();
    var d = els.fDate.value, p = els.fPair.value, dir = els.fDir.value;
    var ty = els.fType.value, sa = els.fSample.value, fx = els.fFx.value;
    rows = rows.filter(function (e) {
      if (d && e.bar_time_utc.slice(0, 10) !== d) return false;
      if (p && e.pair !== p) return false;
      if (dir && e.direction !== dir) return false;
      if (ty && e.event_type !== ty) return false;
      if (sa === "prospective" && !e.is_prospective) return false;
      if (sa === "backfill" && !e.is_backfill) return false;
      var hasFx = Boolean(e.fx_bias_link && e.fx_bias_link.fx_bias_time);
      if (fx === "yes" && !hasFx) return false;
      if (fx === "no" && hasFx) return false;
      return true;
    });
    els.list.innerHTML = rows.length
      ? rows.map(card).join("")
      : '<div class="pw-empty">Nessun evento per questi filtri.</div>';
  }

  function fillOptions() {
    var pairs = {}, types = {};
    (payload.events || []).forEach(function (e) { pairs[e.pair] = 1; types[e.event_type] = 1; });
    Object.keys(pairs).sort().forEach(function (v) {
      els.fPair.insertAdjacentHTML("beforeend", '<option value="' + v + '">' + v + "</option>");
    });
    Object.keys(types).sort().forEach(function (v) {
      els.fType.insertAdjacentHTML("beforeend", '<option value="' + v + '">' + v + "</option>");
    });
  }

  function status() {
    var fp = payload.model_fingerprint || "";
    els.status.innerHTML =
      "<strong>" + (payload.model_name || "PAIR_PREWAKE_V1") + "</strong><br>" +
      "Status: " + (payload.status || "ACTIVE") + "<br>" +
      "Model fingerprint:<br><code>" + fp.slice(0, 12) + "…</code><br>" +
      "Threshold: <code>" + payload.threshold + "</code><br>" +
      "Prospective start: " + (payload.prospective_start_at || "non ancora abilitato") + "<br>" +
      "Ultima H1 completa: " + (payload.last_complete_h1_utc || "—") + " UTC<br>" +
      "Tuning: " + (payload.tuning || "FROZEN");
  }

  function load() {
    var saved = token();
    if (!saved) { els.status.textContent = "Inserisci il dashboard token."; return; }
    fetch("/api/prewake", { headers: { Authorization: "Bearer " + saved }, cache: "no-store" })
      .then(function (r) {
        if (r.status === 401) throw new Error("token non valido");
        return r.json();
      })
      .then(function (data) {
        payload = data;
        fillOptions();
        status();
        apply();
      })
      .catch(function (err) { els.status.textContent = "Errore: " + err.message; });
  }

  els.saveToken.addEventListener("click", function () {
    var v = els.tokenInput.value.trim();
    if (v) { localStorage.setItem("fxbr.dashboardToken", v); load(); }
  });
  els.tokenInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") els.saveToken.click();
  });
  [els.fDate, els.fPair, els.fDir, els.fType, els.fSample, els.fFx].forEach(function (el) {
    el.addEventListener("change", apply);
  });

  els.tokenInput.value = token();
  load();
})();
