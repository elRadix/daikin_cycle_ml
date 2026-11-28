/*
 * Daikin Cycle ML — Reports card: entities, the service request and the
 * view model of one period report. Part of custom:daikin-reports-card (see
 * daikin-reports-card.js). Pure functions, no DOM: tested under Node.
 *
 * The report comes from the service daikin_cycle_ml.get_report (#508):
 * the period's figures, the comparison with the previous period or the
 * same period last year (deltas, weather-matched COP, verdicts), the trend,
 * the last periods and the days of the period. Nothing is read from large
 * state attributes (R401).
 */
(function () {
  "use strict";

  const P = (window.DaikinReportsCardParts = window.DaikinReportsCardParts || {});
  const DOMAIN = "daikin_cycle_ml";
  const LANGS = ["en", "nl", "fr"];
  const TYPES = ["week", "month", "year", "season"];
  const MODES = ["all", "heating", "dhw", "cooling"];
  const AGAINST = ["previous", "last_year", "none"];
  const TABS = ["overview", "energy", "temps", "cycling", "events", "compare"];
  const HISTORY = 12;
  const POINTS = ["quality_mean", "buh_share_pct"];
  const SUFFIX = {
    last_month_report: ["last_month_report", "rapport_vorige_maand", "rapport_du_mois_dernier"],
    hp_specs: ["hp_specs", "wp_specs", "caracteristiques_de_la_pac"],
    cycle_state: ["cycle_state", "cyclus_status", "etat_du_cycle"],
  };
  /* tiles of the overview: metric, unit, decimals */
  const TILES = [["cop", "", 2], ["el_kwh", "kwh", 0], ["th_kwh", "kwh", 0], ["runtime_h", "h", 0],
    ["cycles", "", 0], ["quality_mean", "", 0]];
  /* rows of the Compare tab (metric, unit, decimals) */
  const ROWS = [["cop", "", 2], ["cop_matched", "", 2], ["el_kwh", "kwh", 1], ["th_kwh", "kwh", 1], ["el_per_dd", "kwh", 3],
    ["runtime_h", "h", 1], ["cycles", "", 0], ["run_mean_min", "min", 0], ["starts_per_h", "", 2], ["quality_mean", "", 0],
    ["lwt_mean", "°C", 1], ["return_mean", "°C", 1], ["dt_mean", "K", 1], ["flow_mean", "l/min", 1], ["outdoor_mean", "°C", 1],
    ["dd", "", 0], ["buh_min", "min", 0], ["buh_share_pct", "%", 1], ["defrost_count", "", 0], ["alerts_total", "", 0],
    ["ml_anomalies", "", 0]];

  const esc = (s) => String(s === undefined || s === null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  const num = (v) => {
    if (v === null || v === undefined || v === "" || typeof v === "boolean") return null;
    const x = typeof v === "number" ? v : parseFloat(String(v));
    return isFinite(x) ? x : null;
  };

  function pickLang(hass, config, csAttrs) {
    const ov = String((config && config.language) || "").toLowerCase();
    if (LANGS.includes(ov)) return ov;
    const ha = String((hass && ((hass.locale && hass.locale.language) || hass.language)) || "").toLowerCase().slice(0, 2);
    if (LANGS.includes(ha)) return ha;
    const cl = String((csAttrs && csAttrs.configured_language) || "").toLowerCase();
    return LANGS.includes(cl) ? cl : "en";
  }

  /* role -> entity_id: registry (translation_key, optional device) first,
     then the object-id suffix in en / nl / fr; one device, never a mix. */
  function resolveEntities(hass, config) {
    const out = {};
    const states = (hass && hass.states) || {};
    const ents = (hass && hass.entities) || {};
    let dev = config && config.device_id;
    if (!dev) {
      const first = Object.keys(ents).find((id) => ents[id] && ents[id].platform === DOMAIN && ents[id].device_id && states[id]);
      dev = first ? ents[first].device_id : null;
    }
    let prefix = null;
    for (const role of Object.keys(SUFFIX)) {
      let found = null;
      for (const id of Object.keys(ents)) {
        const e = ents[id];
        if (!e || e.platform !== DOMAIN || e.translation_key !== role || id.indexOf("sensor.") !== 0 || !states[id]) continue;
        if (dev && e.device_id !== dev) continue;
        found = id; break;
      }
      if (!found && !dev) {
        const ids = Object.keys(states).filter((i) => i.indexOf("sensor.") === 0);
        for (const sfx of SUFFIX[role]) {
          found = (prefix && ids.find((i) => i === "sensor." + prefix + "_" + sfx))
            || (prefix ? null : ids.find((i) => i.indexOf(DOMAIN) !== -1 && i.endsWith("_" + sfx)) || ids.find((i) => i.endsWith("_" + sfx))) || null;
          if (found) { if (!prefix) prefix = found.slice(7, found.length - sfx.length - 1); break; }
        }
      }
      out[role] = found;
    }
    return out;
  }

  function entryOf(hass, ids) {
    for (const id of Object.values(ids || {})) {
      const e = id && hass && hass.entities && hass.entities[id];
      const d = e && e.device_id && hass.devices && hass.devices[e.device_id];
      if (d && Array.isArray(d.config_entries) && d.config_entries.length) return d.config_entries[0];
    }
    return null;
  }

  /* the UI state with the card's defaults filled in */
  function uiState(config, ui) {
    const c = config || {}, u = ui || {};
    const pick = (v, list, d) => (list.includes(v) ? v : d);
    return {
      type: pick(u.type || c.period_type, TYPES, "month"),
      mode: pick(u.mode || c.mode, MODES, "all"),
      against: pick(u.against || c.compare, AGAINST, "previous"),
      tab: pick(u.tab || c.default_tab, TABS, "overview"),
      key: u.key || null,
    };
  }

  /* service data for get_report */
  function request(entryId, config, ui) {
    const s = uiState(config, ui);
    const data = { period_type: s.type, mode: s.mode, compare: s.against, history: HISTORY, include_days: true };
    if (s.key) data.period = s.key;
    if (entryId) data.entry_id = entryId;
    return data;
  }

  function fill(tpl, vars) {
    return String(tpl).replace(/\{(\w+)\}/g, (m, k) => (vars && vars[k] !== undefined ? vars[k] : m));
  }

  /* human period name: "Week 48 · 2026", "November 2026", "2026", "2026/27" */
  function periodLabel(type, key, lang, T) {
    if (!key) return "";
    if (type === "week") {
      const [y, w] = String(key).split("-W");
      return fill(T.week_n, { n: Number(w) }) + " · " + y;
    }
    if (type === "month") {
      const [y, m] = String(key).split("-").map(Number);
      try {
        const s = new Intl.DateTimeFormat(lang, { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(Date.UTC(y, m - 1, 15)));
        return s.charAt(0).toUpperCase() + s.slice(1);
      } catch (e) { return key; }
    }
    return String(key);
  }

  function step(available, key, dir) {
    /* available is newest first: "earlier" moves down the list */
    const i = (available || []).indexOf(key);
    if (i < 0) return null;
    const j = dir < 0 ? i + 1 : i - 1;
    return j >= 0 && j < available.length ? available[j] : null;
  }

  function buildModel(hass, config, ui, resp) {
    const ids = resolveEntities(hass, config);
    const st = (role) => (ids[role] && hass.states[ids[role]]) || null;
    const at = (role) => (st(role) && st(role).attributes) || {};
    const lang = pickLang(hass, config, at("cycle_state"));
    const T = (P.i18n && (P.i18n[lang] || P.i18n.en)) || {};
    const s = uiState(config, ui);
    const specs = at("hp_specs");
    const m = {
      lang, T, ids, ui: s, ok: !!ids.last_month_report, entryId: entryOf(hass, ids),
      model: specs.model ? String(specs.model).toUpperCase() : "",
      loading: !!(ui && ui.loading), error: (ui && ui.error) || "", resp: resp || null,
      tabs: TABS, types: TYPES, modes: MODES, againsts: AGAINST,
    };
    const r = resp || {};
    m.available = Array.isArray(r.available) ? r.available : [];
    m.key = r.key || s.key || null;
    m.found = !!r.found;
    /* label from the response's own type: a slow reply to an older request
       never shows a month key as a week */
    m.ptype = r.period_type || s.type;
    m.label = periodLabel(m.ptype, m.key, lang, T);
    m.prevKey = step(m.available, m.key, -1);
    m.nextKey = step(m.available, m.key, 1);
    if (!m.found) return m;
    const data = r.data || {}, der = r.derived || {}, cmp = r.compare || {}, metrics = cmp.metrics || {};
    const val = (k) => (num(der[k]) !== null ? num(der[k]) : num(data[k]));
    m.data = data;
    m.finalised = !!r.finalised;
    m.partial = !!cmp.partial && !!(r.reference && r.reference.found);
    m.coverage = { n: num(data.n_days_recorded) || 0, d: num(data.n_days) || 0 };
    m.refKey = r.reference && r.reference.key;
    m.refFound = !!(r.reference && r.reference.found);
    m.refLabel = periodLabel(m.ptype, m.refKey, lang, T);
    m.verdicts = cmp.verdicts || {};
    m.overall = m.refFound ? (m.verdicts.overall || null) : null;
    const d = (k) => metrics[k] || {};
    m.tiles = TILES.map(([k, unit, dec]) => ({
      k, unit, dec, value: val(k), ref: num(d(k).ref), delta: num(d(k).delta), pct: num(d(k).delta_pct),
    }));
    m.rows = ROWS.map(([k, unit, dec]) => ({
      k, unit, dec, value: k === "cop_matched" ? num(d(k).cur) : val(k), ref: num(d(k).ref),
      delta: num(d(k).delta), pct: num(d(k).delta_pct), better: P.better ? P.better[k] : undefined,
    })).filter((row) => row.value !== null || row.ref !== null);
    /* the COP verdict is judged on the weather-matched COP when there is one */
    const judgedOn = (k) => (k === "cop" && metrics.cop_matched ? "cop_matched" : k);
    m.judged = Object.keys(m.verdicts).filter((k) => k !== "overall")
      .map((k) => ({ k, v: m.verdicts[k], delta: num(d(judgedOn(k)).delta),
        /* quality and the backup-heater share are judged in points, not % */
        pct: POINTS.includes(k) ? null : num(d(judgedOn(k)).delta_pct) }));
    m.trend = r.trend || {};
    m.history = Array.isArray(r.history) ? r.history : [];
    m.days = Array.isArray(r.days) ? r.days : [];
    m.byMode = r.by_mode || {};
    m.scheme = r.scheme || "";
    m.alerts = Object.entries(data.alerts || {}).sort((a, b) => b[1] - a[1]);
    m.checks = Object.entries(data.checks || {}).sort((a, b) => b[1] - a[1]);
    m.temps = { mean: num(data.outdoor_mean), min: num(data.outdoor_min), max: num(data.outdoor_max),
      lwt: num(data.lwt_mean), ret: num(data.return_mean), dt: num(data.dt_mean), flow: num(data.flow_mean), dd: num(der.dd) };
    return m;
  }

  /* higher is better (true), lower is better (false), neutral (null): the
     colour of a change; same table as engine/report_compare.METRICS */
  P.better = {
    cop: true, cop_matched: true, el_per_dd: false, run_mean_min: true, starts_per_h: false, quality_mean: true,
    buh_min: false, buh_share_pct: false, alerts_total: false, ml_anomalies: false,
  };

  Object.assign(P, { model: { DOMAIN, LANGS, TYPES, MODES, AGAINST, TABS, HISTORY, SUFFIX, TILES, ROWS,
    esc, num, fill, pickLang, resolveEntities, entryOf, uiState, request, periodLabel, step, buildModel } });
  if (window.__dcmReportsBoot) window.__dcmReportsBoot();
})();
