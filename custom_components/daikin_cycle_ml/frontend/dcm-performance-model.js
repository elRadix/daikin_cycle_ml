/*
 * Daikin Cycle ML — Performance card: entities, limits and loads.
 * Part of custom:daikin-performance-card (see daikin-performance-card.js).
 * Pure functions, no DOM: tested under Node.
 *
 * The limits come from the model chosen in setup (sensor hp_specs), with
 * the user's model profile merged in by the integration (#467): every
 * datasheet point may carry hmax (maximum heat kW, from the user or the capacity tables;
 * not the datasheet hc, which is the rating-point capacity) and cop, each with its source
 * in point.src; rps_min / rps_max come from the profile or are learned.
 */
(function () {
  "use strict";

  const P = (window.DaikinPerformanceCardParts = window.DaikinPerformanceCardParts || {});
  const DOMAIN = "daikin_cycle_ml";
  const LANGS = ["en", "nl", "fr"];
  const SUFFIX = {
    thermal_power_live: ["thermal_power_live", "thermisch_vermogen_live", "puissance_thermique_instantanee"],
    hp_specs: ["hp_specs", "wp_specs", "caracteristiques_de_la_pac"],
    cycle_state: ["cycle_state", "cyclus_status", "etat_du_cycle"],
    compressor_running: ["compressor_running", "compressor_actief", "compresseur_en_marche"],
    defrost_active: ["defrost_active", "defrost_actief", "degivrage_en_cours"],
    dhw_active: ["dhw_active", "sww_actief", "eau_chaude_en_cours"],
    buh_active: ["buh_active", "buh_actief", "appoint_en_marche"],
  };
  const BINARY = ["compressor_running", "defrost_active", "dhw_active", "buh_active"];
  const REQUIRED_ROLES = ["thermal_power_live", "hp_specs"];
  const LOADS = ["thermal", "compressor", "electrical"];
  const WATCH = 85, BAD = 95;
  const NEAR_K = 3;   /* within 3 K of a known point counts as known (no "add a point" note) */

  const esc = (s) => String(s === undefined || s === null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  const num = (v) => {
    if (v === null || v === undefined || v === "" || typeof v === "boolean") return null;
    const s = String(v);
    if (s === "unknown" || s === "unavailable" || s === "None") return null;
    const x = parseFloat(s);
    return isFinite(x) ? x : null;
  };
  const on = (v) => ["on", "true", "1", "yes"].includes(String(v).toLowerCase());

  function pickLang(hass, config, csAttrs) {
    const ov = String((config && config.language) || "").toLowerCase();
    if (LANGS.includes(ov)) return ov;
    const ha = String((hass && ((hass.locale && hass.locale.language) || hass.language)) || "").toLowerCase().slice(0, 2);
    if (LANGS.includes(ha)) return ha;
    const cl = String((csAttrs && csAttrs.configured_language) || "").toLowerCase();
    return LANGS.includes(cl) ? cl : "en";
  }

  /* role -> entity_id: registry (translation_key, optional device) first,
     then the object-id suffix in en / nl / fr. */
  function resolveEntities(hass, config) {
    const out = {};
    const states = (hass && hass.states) || {};
    const ents = (hass && hass.entities) || {};
    const dev = config && config.device_id;
    for (const role of Object.keys(SUFFIX)) {
      const pre = BINARY.includes(role) ? "binary_sensor." : "sensor.";
      let found = null;
      for (const id of Object.keys(ents)) {
        const e = ents[id];
        if (!e || e.platform !== DOMAIN || e.translation_key !== role) continue;
        if (id.indexOf(pre) !== 0 || !states[id]) continue;
        if (dev && e.device_id !== dev) continue;
        found = id; break;
      }
      if (!found && !dev) {
        const ids = Object.keys(states).filter((i) => i.indexOf(pre) === 0);
        for (const sfx of SUFFIX[role]) {
          found = ids.find((i) => i.indexOf(DOMAIN) !== -1 && i.endsWith("_" + sfx)) || ids.find((i) => i.endsWith("_" + sfx)) || null;
          if (found) break;
        }
      }
      out[role] = found;
    }
    return out;
  }

  function carnot(lwt, outdoor) {
    if (lwt === null || outdoor === null) return null;
    const tc = lwt + 2 + 273.15, te = outdoor - 6 + 273.15;
    return tc > te ? tc / (tc - te) : null;
  }

  /* value of `key` at (outdoor, lwt): linear along outdoor per water
     temperature, then along water temperature. Outside the points the
     nearest is used (COP scaled by the Carnot ratio; max heat held).
     exact = inside the known points (or within NEAR_K of one) in both directions. */
  function atCondition(points, key, outdoor, lwt) {
    if (!Array.isArray(points) || outdoor === null || lwt === null) return null;
    const byW = {}, used = new Set();
    let manual = false;
    for (const p of points) {
      const w = num(p.t_lwc), a = num(p.t_out), v = num(p[key]);
      if (w === null || a === null || v === null) continue;
      (byW[w] = byW[w] || []).push({ a, v, label: p.label || `A${a}/W${w}`, m: !!(p.src && p.src[key] === "manual") });
    }
    const ws = Object.keys(byW).map(Number).sort((x, y) => x - y);
    if (!ws.length) return null;
    let exact = true;
    const along = (w) => {
      const list = byW[w].sort((x, y) => x.a - y.a);
      const lo = list[0], hi = list[list.length - 1];
      if (list.length > 1 && outdoor >= lo.a && outdoor <= hi.a) {
        let i = 0;
        while (i < list.length - 2 && outdoor > list[i + 1].a) i++;
        const p0 = list[i], p1 = list[i + 1];
        [p0, p1].forEach((p) => { used.add(p.label); manual = manual || p.m; });
        return p0.v + (p1.v - p0.v) * (outdoor - p0.a) / (p1.a - p0.a);
      }
      const near = outdoor < lo.a ? lo : hi;
      used.add(near.label); manual = manual || near.m;
      if (Math.abs(near.a - outdoor) > NEAR_K) exact = false;
      if (key !== "cop") return near.v;
      const c0 = carnot(w, near.a), c1 = carnot(w, outdoor);
      return c0 && c1 ? near.v * (c1 / c0) : near.v;
    };
    let value;
    if (lwt <= ws[0] || lwt >= ws[ws.length - 1] || ws.length === 1) {
      const w = lwt <= ws[0] ? ws[0] : ws[ws.length - 1];
      if (Math.abs(w - lwt) > NEAR_K) exact = false;
      value = along(w);
      if (key === "cop" && Math.abs(w - lwt) > 0.5) {
        const c0 = carnot(w, outdoor), c1 = carnot(lwt, outdoor);
        if (c0 && c1) value *= c1 / c0;
      }
    } else {
      let i = 0;
      while (i < ws.length - 2 && lwt > ws[i + 1]) i++;
      const v0 = along(ws[i]), v1 = along(ws[i + 1]);
      value = v0 + (v1 - v0) * (lwt - ws[i]) / (ws[i + 1] - ws[i]);
    }
    return { value, exact, from: [...used], manual };
  }

  function limits(specs, outdoor, lwt) {
    const pts = Array.isArray(specs.points) ? specs.points : [];
    const vs = specs.value_sources || {};
    const hc = atCondition(pts, "hmax", outdoor, lwt);
    const cop = atCondition(pts, "cop", outdoor, lwt);
    const thMax = hc ? hc.value : null, copSpec = cop ? cop.value : null;
    const fmin = num(specs.rps_min), fmax = num(specs.rps_max);
    return {
      thMax, thExact: hc ? hc.exact : false, thFrom: hc ? hc.from : [], thManual: hc ? hc.manual : false,
      copSpec, elMax: thMax && copSpec ? thMax / copSpec : null,
      fmin, fmax, fSrc: vs.rps_max || vs.rps_min || null,
      kw: num(specs.kw),
    };
  }

  const zone = (p) => (p === null ? "info" : p >= BAD ? "bad" : p >= WATCH ? "watch" : "good");

  function buildModel(hass, config) {
    const ids = resolveEntities(hass, config);
    const st = (role) => (ids[role] && hass.states[ids[role]]) || null;
    const at = (role) => (st(role) && st(role).attributes) || {};
    const isOn = (role) => !!(st(role) && on(st(role).state));
    const lang = pickLang(hass, config, at("cycle_state"));
    const ok = REQUIRED_ROLES.every((r) => ids[r]);
    const specs = at("hp_specs");
    const tp = st("thermal_power_live"), a = (tp && tp.attributes) || {};
    const live = {
      heat: num(tp && tp.state), power: num(a.input_power_w), cop: num(a.input_cop), rps: num(a.input_rps),
      lwt: num(a.lwt_c), outdoor: num(a.outdoor_c),
      running: isOn("compressor_running"), defrost: isOn("defrost_active"), dhw: isOn("dhw_active"), buh: isOn("buh_active"),
    };
    const L = limits(specs, live.outdoor, live.lwt);
    const pct = (x, max) => (x !== null && max ? (x / max) * 100 : null);
    const loads = {
      thermal: pct(live.heat, L.thMax),
      electrical: live.power !== null && L.elMax ? (live.power / 1000 / L.elMax) * 100 : null,
      compressor: live.rps !== null && L.fmin !== null && L.fmax !== null && L.fmax > L.fmin
        ? Math.max(0, ((live.rps - L.fmin) / (L.fmax - L.fmin)) * 100) : null,
    };
    const staticLoad = pct(live.heat, L.kw);
    const copPct = live.cop !== null && L.copSpec ? (live.cop / L.copSpec) * 100 : null;
    const headroom = L.thMax !== null && live.heat !== null ? Math.max(0, L.thMax - live.heat) : null;
    const worst = Math.max(loads.thermal === null ? -1 : loads.thermal, loads.compressor === null ? -1 : loads.compressor);
    let lvl, key;
    if (!live.running) { lvl = "info"; key = "idle"; }
    else if (live.defrost) { lvl = "info"; key = "defrost"; }
    else if (worst < 0) { lvl = "info"; key = "no_limits"; }
    else if (worst >= BAD) { lvl = "bad"; key = live.buh ? "at_limit_buh" : "at_limit"; }
    else if (worst >= WATCH) { lvl = "watch"; key = "near_limit"; }
    else { lvl = "good"; key = copPct !== null && copPct >= 100 ? "ok_efficient" : "ok"; }
    return {
      ids, ok, lang, live, limits: L, loads, staticLoad, copPct, headroom, lvl, key,
      model: specs.model ? String(specs.model).toUpperCase() : "",
      meta: [specs.family, num(specs.kw) ? num(specs.kw) + " kW" : "", specs.refrigerant].filter((x) => x && String(x) !== "None").join(" · "),
      points: (Array.isArray(specs.points) ? specs.points : []).filter((p) => num(p.t_out) !== null && num(p.t_lwc) !== null),
      sources: specs.value_sources || {}, learned: specs.rps_learned || {},
      primary: LOADS.includes(config && config.primary_load) ? config.primary_load : "compressor",
    };
  }

  Object.assign(P, { model: { DOMAIN, SUFFIX, LOADS, WATCH, BAD, esc, num, on, pickLang, resolveEntities, carnot, atCondition, limits, zone, buildModel } });
  if (window.__dcmPerfBoot) window.__dcmPerfBoot();
})();
