/*
 * Daikin Cycle ML — Efficiency card: entities, history and view model.
 * Part of custom:daikin-efficiency-card (see daikin-efficiency-card.js).
 * Pure functions, no DOM: tested under Node.
 */
(function () {
  "use strict";

  const P = (window.DaikinEfficiencyCardParts = window.DaikinEfficiencyCardParts || {});
  const DOMAIN = "daikin_cycle_ml";
  const LANGS = ["en", "nl", "fr"];

  /* role -> object-id suffixes in en / nl / fr (fallback when the entity
     registry is not available). Checked against translations/*.json by
     tests/test_efficiency_native_card.py. */
  const SUFFIX = {
    thermal_power_live: ["thermal_power_live", "thermisch_vermogen_live", "puissance_thermique_instantanee"],
    hp_specs: ["hp_specs", "wp_specs", "caracteristiques_de_la_pac"],
    cycle_state: ["cycle_state", "cyclus_status", "etat_du_cycle"],
    current_cycle: ["current_cycle", "huidige_cyclus", "cycle_en_cours"],
    heating_curve_advice: ["heating_curve_advice", "stooklijn_advies", "conseil_de_loi_d_eau"],
    cop_curve_recent: ["cop_curve_recent", "courbe_de_cop_recente"],
    cop_today: ["cop_today", "cop_vandaag", "cop_chauffage_du_jour"],
    cop_combined_today: ["cop_combined_today", "cop_gecombineerd_vandaag", "cop_global_du_jour"],
    cop_mean_day: ["cop_mean_day", "cop_gemiddelde_dag", "cop_moyen_du_jour"],
    cop_mean_week: ["cop_mean_week", "cop_gemiddelde_week", "cop_moyen_de_la_semaine"],
    cop_mean_month: ["cop_mean_month", "cop_gemiddelde_maand", "cop_moyen_du_mois"],
    spf_season: ["spf_season", "spf_seizoen", "rendement_saisonnier_spf_saison"],
    cop_normalized_a7w35: ["cop_normalized_a7w35", "cop_genormaliseerd_a7w35", "cop_ramene_a_a7_w35"],
    cop_vs_datasheet_pct: ["cop_vs_datasheet_pct", "cop_par_rapport_a_la_fiche"],
    cop_degradation_status: ["cop_degradation_status", "cop_degradatiestatus", "baisse_du_cop"],
    cop_trend_30d: ["cop_trend_30d", "tendance_du_cop_30_j"],
    runtime_compressor_today: ["runtime_compressor_today", "compressorbedrijfstijd_vandaag", "marche_compresseur_aujourd_hui"],
    runtime_buh_today: ["runtime_buh_today", "buh_bedrijfstijd_vandaag", "marche_appoint_aujourd_hui"],
    compressor_starts_today: ["compressor_starts_today", "compressorstarts_vandaag", "demarrages_compresseur_aujourd_hui"],
    defrost_count_today: ["defrost_count_today", "ontdooiingen_vandaag", "degivrages_aujourd_hui"],
    defrost_duration_today: ["defrost_duration_today", "ontdooiingsduur_vandaag", "duree_de_degivrage_aujourd_hui"],
    duty_cycle_today: ["duty_cycle_today", "duty_cycle_vandaag", "taux_de_marche_aujourd_hui"],
    electrical_energy_total_today: ["electrical_energy_total_today", "elektrische_energie_totaal_vandaag", "electricite_totale_aujourd_hui"],
    cycles_today: ["cycles_today", "cycli_vandaag", "cycles_aujourd_hui"],
    compressor_running: ["compressor_running", "compressor_actief", "compresseur_en_marche"],
    defrost_active: ["defrost_active", "defrost_actief", "degivrage_en_cours"],
    dhw_active: ["dhw_active", "sww_actief", "eau_chaude_en_cours"],
    buh_active: ["buh_active", "buh_actief", "appoint_en_marche"],
    short_cycling_pattern: ["short_cycling_pattern", "kort_cyclisch_patroon", "serie_de_cycles_courts"],
    high_cycle_rate: ["high_cycle_rate", "hoge_cyclusfrequentie", "frequence_de_cycles_elevee"],
  };
  const BINARY = ["compressor_running", "defrost_active", "dhw_active", "buh_active", "short_cycling_pattern", "high_cycle_rate"];
  const REQUIRED_ROLES = ["thermal_power_live", "hp_specs"];
  /* entities whose history feeds the graphs */
  const HISTORY_ROLES = ["thermal_power_live", "compressor_running", "defrost_active", "dhw_active", "buh_active"];
  const RANGES = { "30m": 1800, "3h": 10800, "24h": 86400 };
  const SPANS = Object.assign({ "10m": 600 }, RANGES);

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
    const ha = String((hass && ((hass.locale && hass.locale.language) || hass.language)) || "")
      .toLowerCase().slice(0, 2);
    if (LANGS.includes(ha)) return ha;
    const cl = String((csAttrs && csAttrs.configured_language) || "").toLowerCase();
    return LANGS.includes(cl) ? cl : "en";
  }

  /* role -> entity_id. Registry first (translation_key, any language,
     optional device_id), then the object-id suffix fallback. */
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
          found = ids.find((i) => i.indexOf(DOMAIN) !== -1 && i.endsWith("_" + sfx))
            || ids.find((i) => i.endsWith("_" + sfx)) || null;
          if (found) break;
        }
      }
      out[role] = found;
    }
    return out;
  }

  /* one sample of thermal_power_live (state + attributes) */
  function sampleOf(t, state, a) {
    a = a || {};
    return {
      t, kw: num(state), power: num(a.input_power_w), cop: num(a.input_cop),
      flow: num(a.input_flow_lmin), dt: num(a.input_dt_k), rps: num(a.input_rps),
      lwt: num(a.lwt_c), ret: num(a.return_c), out: num(a.outdoor_c),
      sp: num(a.lw_setpoint_c), room: num(a.room_c), roomSp: num(a.room_setpoint_c),
      liquid: num(a.refrigerant_liquid_c),
    };
  }

  /* history/history_during_period (compressed) -> samples + on/off spans.
     ``hist`` = {entity_id: [{s, a?, lu}]}; times in seconds. */
  function parseHistory(hist, ids) {
    const out = { samples: [], spans: {} };
    if (!hist || typeof hist !== "object") return out;
    const tp = ids.thermal_power_live && hist[ids.thermal_power_live];
    if (Array.isArray(tp)) {
      let lastA = {};
      for (const r of tp) {
        if (!r) continue;
        if (r.a) lastA = r.a;
        const t = num(r.lu !== undefined ? r.lu : r.lc);
        if (t !== null) out.samples.push(sampleOf(t, r.s, lastA));
      }
    }
    for (const role of ["compressor_running", "defrost_active", "dhw_active", "buh_active"]) {
      const rows = ids[role] && hist[ids[role]];
      out.spans[role] = Array.isArray(rows) ? rows.map((r) => ({ t: num(r.lu !== undefined ? r.lu : r.lc), on: on(r.s) }))
        .filter((r) => r.t !== null) : [];
    }
    return out;
  }

  /* on/off change list -> [{from, to}] spans (open span ends at ``now``) */
  function toSpans(changes, now) {
    const spans = [];
    let start = null;
    for (const c of changes || []) {
      if (c.on && start === null) start = c.t;
      if (!c.on && start !== null) { spans.push({ from: start, to: c.t }); start = null; }
    }
    if (start !== null) spans.push({ from: start, to: now });
    return spans;
  }

  /* samples within [now - range, now]; a value holds until the next
     change (recorder semantics), so the last sample before the window
     is carried to its start. Spans clipped to the window. */
  function windowed(buf, now, range) {
    const from = now - (SPANS[range] || RANGES["3h"]);
    const samples = buf.samples.filter((s) => s.t >= from && s.t <= now);
    let prev = null;
    for (const s of buf.samples) { if (s.t < from) prev = s; else break; }
    if (prev && (!samples.length || samples[0].t > from)) samples.unshift(Object.assign({}, prev, { t: from }));
    const spans = {};
    for (const k of Object.keys(buf.spans || {})) {
      spans[k] = toSpans(buf.spans[k], now).filter((s) => s.to >= from)
        .map((s) => ({ from: Math.max(from, s.from), to: Math.min(now, s.to) }));
    }
    return { from, to: now, samples, spans };
  }

  const mean = (xs) => { const v = xs.filter((x) => x !== null && isFinite(x)); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };

  /* time-weighted 10-min mean of a field over the time the compressor
     delivers heat (each value holds until the next sample) */
  function mean10(buf, now, field) {
    const w = windowed(buf, now, "10m");
    let sum = 0, dur = 0;
    w.samples.forEach((s, i) => {
      const end = i + 1 < w.samples.length ? w.samples[i + 1].t : now;
      const v = s[field];
      if (!(s.kw > 0) || v === null || !isFinite(v) || end <= s.t) return;
      sum += v * (end - s.t); dur += end - s.t;
    });
    return dur > 0 ? sum / dur : null;
  }

  /* least squares weighted by n: lwt = a + b * outdoor */
  function fitCurve(pts) {
    let sw = 0, sx = 0, sy = 0, sxx = 0, sxy = 0;
    for (const p of pts) {
      const w = p.n || 1; sw += w; sx += w * p.x; sy += w * p.y; sxx += w * p.x * p.x; sxy += w * p.x * p.y;
    }
    const den = sw * sxx - sx * sx;
    if (pts.length < 2 || !(sw > 0) || Math.abs(den) < 1e-9) return null;
    const b = (sw * sxy - sx * sy) / den;
    return { a: (sy - b * sx) / sw, b, spread: Math.max(...pts.map((p) => p.x)) - Math.min(...pts.map((p) => p.x)) };
  }

  /* heating-curve advice buckets {"0-2": {lwt, cop, n}} -> sorted points */
  function bucketPoints(buckets) {
    const out = [];
    for (const k of Object.keys(buckets || {})) {
      /* keys of bucket_for_outdoor: "-4--2", "0-2", "-10-" (below), "20+" */
      const m = /^(-?\d+)-(-?\d+)$/.exec(k);
      const b = buckets[k] || {};
      const x = m ? (parseFloat(m[1]) + parseFloat(m[2])) / 2 : k === "-10-" ? -11 : k === "20+" ? 21 : null;
      const lwt = num(b.lwt), cop = num(b.cop), n = num(b.n);
      if (x === null || lwt === null) continue;
      out.push({ key: k, x, y: lwt, cop, n: n || 0 });
    }
    return out.sort((a, b) => a.x - b.x);
  }

  /* expected COP from the datasheet points at (outdoor, lwt): per LWT line
     linear in outdoor between two points; outside the points (or with a
     single point, e.g. only A7) the nearest point is scaled with the
     Carnot ratio of the two conditions. Lines are interpolated in LWT. */
  function datasheetCop(points, outdoor, lwt) {
    if (!Array.isArray(points) || outdoor === null || lwt === null) return null;
    const byW = {};
    for (const p of points) {
      const w = num(p.t_lwc), a = num(p.t_out), c = num(p.cop);
      if (w === null || a === null || c === null) continue;
      (byW[w] = byW[w] || []).push({ a, c });
    }
    const atW = (list, w) => {
      list.sort((x, y) => x.a - y.a);
      const lo = list[0], hi = list[list.length - 1];
      if (list.length > 1 && outdoor >= lo.a && outdoor <= hi.a) {
        let i = 0;
        while (i < list.length - 2 && outdoor > list[i + 1].a) i++;
        const p0 = list[i], p1 = list[i + 1];
        return p0.c + (p1.c - p0.c) * (outdoor - p0.a) / (p1.a - p0.a);
      }
      const near = outdoor < lo.a ? lo : hi;
      const c0 = carnot(w, near.a), c1 = carnot(w, outdoor);
      return c0 && c1 ? near.c * (c1 / c0) : near.c;
    };
    const ws = Object.keys(byW).map(Number).sort((a, b) => a - b);
    if (!ws.length) return null;
    let lo = ws[0], hi = ws[ws.length - 1];
    for (const w of ws) { if (w <= lwt) lo = w; if (w >= lwt && hi >= w) hi = w; }
    if (lwt < ws[0]) hi = lo = ws[0];
    if (lwt > ws[ws.length - 1]) hi = lo = ws[ws.length - 1];
    const c0 = atW(byW[lo], lo), c1 = atW(byW[hi], hi);
    const v = lo === hi ? c0 : c0 + (c1 - c0) * (lwt - lo) / (hi - lo);
    return v > 0 ? v : null;
  }

  /* Carnot COP of heating at (condensing ~ LWT + 2 K, evaporating ~ outdoor - 6 K) */
  function carnot(lwt, outdoor) {
    if (lwt === null || outdoor === null) return null;
    const tc = lwt + 2 + 273.15, te = outdoor - 6 + 273.15;
    return tc > te ? tc / (tc - te) : null;
  }

  function buildModel(hass, config, buf, now, range) {
    const ids = resolveEntities(hass, config);
    const st = (role) => (ids[role] && hass.states[ids[role]]) || null;
    const at = (role) => (st(role) && st(role).attributes) || {};
    const val = (role) => num(st(role) && st(role).state);
    const isOn = (role) => !!(st(role) && on(st(role).state));
    const lang = pickLang(hass, config, at("cycle_state"));
    const ok = REQUIRED_ROLES.every((r) => ids[r]);
    const specs = at("hp_specs");
    const tp = st("thermal_power_live");
    const live = sampleOf(now, tp && tp.state, tp && tp.attributes);
    const adv = at("heating_curve_advice");
    const cur = st("current_cycle");
    const mode = cur && ["heating", "dhw", "cooling"].includes(cur.state) ? cur.state : null;
    live.running = isOn("compressor_running") || !!mode;
    live.mode = isOn("dhw_active") ? "dhw" : mode;
    live.defrost = isOn("defrost_active");
    live.buh = isOn("buh_active");
    live.target = num(adv.huidige_setpoint) !== null ? num(adv.huidige_setpoint) : live.sp;
    live.started = num(at("current_cycle").started_at);
    live.source = (tp && tp.attributes && tp.attributes.calculation_source) || null;
    live.lwt10 = mean10(buf, now, "lwt");
    live.cop10 = mean10(buf, now, "cop");
    live.power10 = mean10(buf, now, "power");
    live.kw10 = mean10(buf, now, "kw");
    const elA = at("electrical_energy_total_today");
    const pts = bucketPoints(adv.buckets);
    return {
      ids, ok, lang, now, range,
      model: specs.model ? String(specs.model).toUpperCase() : "",
      meta: [specs.family, num(specs.kw) ? num(specs.kw) + " kW" : "", specs.refrigerant]
        .filter((x) => x && String(x) !== "None").join(" · "),
      specs: {
        lwtMin: num(specs.lwt_min), lwtMax: num(specs.lwt_max), outMin: num(specs.outdoor_min_c),
        outMax: num(specs.outdoor_max_c), nomCop: num(specs.nom_cop), scop35: num(specs.scop_w35),
        scop55: num(specs.scop_w55), buhAbove: num(specs.buh_above_c), defrostBelow: num(specs.defrost_below_c),
        offAbove: num(specs.off_above_c), kw: num(specs.kw), points: Array.isArray(specs.points) ? specs.points : [],
        minFlow: num(config && config.min_flow),
      },
      live,
      win: windowed(buf, now, range), day: windowed(buf, now, "24h"),
      advice: {
        state: (st("heating_curve_advice") && st("heating_curve_advice").state) || "unknown",
        reason: adv.reason || "", step: num(adv.step_c) || 0, delta: num(adv.delta_c), target: num(adv.doel_setpoint),
        setpoint: num(adv.huidige_setpoint), optimal: num(adv.optimale_lwt), lwt: num(adv.huidige_lwt),
        saving: num(adv.besparing_cop_pct), comfort: num(adv.comfort_impact), confidence: num(adv.betrouwbaarheid),
        bucket: adv.bucket || null, samples: num(adv.samples), tracking: num(adv.tracking_error),
        comfortCap: num(adv.comfort_cap), suppressed: adv.suppressed_by || null,
      },
      curve: {
        pts, fit: fitCurve(pts), recentAll: at("cop_curve_recent").points || [],
        recent: (at("cop_curve_recent").points || []).filter((p) => p && p.mode === "heating"),
      },
      today: {
        cop: val("cop_combined_today"), copHeating: val("cop_today"),
        el: num(elA.total_el_kwh), th: num(elA.total_th_kwh),
        modes: ["heating", "dhw", "cooling"].map((k) => ({ k, el: num(elA[k + "_el_kwh"]), th: num(elA[k + "_th_kwh"]) })),
        runtime_s: val("runtime_compressor_today"), buh_s: val("runtime_buh_today"),
        starts: val("compressor_starts_today"), startsHour: num(at("compressor_starts_today").starts_last_hour),
        defrosts: val("defrost_count_today"), defrost_s: val("defrost_duration_today"),
        duty: val("duty_cycle_today"), dutyBand: at("duty_cycle_today").band || null,
        cycles: val("cycles_today"), shortRuns: num(at("cycles_today").short_runs),
        avgRun: num(at("cycles_today").avg_duration_min),
        shortPattern: isOn("short_cycling_pattern"), highRate: isOn("high_cycle_rate"),
      },
      eff: {
        day: val("cop_mean_day"), week: val("cop_mean_week"), month: val("cop_mean_month"),
        byMode: at("cop_mean_week").by_mode || {},
        p10: num(at("cop_mean_week").cop_p10), p90: num(at("cop_mean_week").cop_p90),
        spf: val("spf_season"), spfYtd: num(at("spf_season").spf_ytd), scop365: num(at("spf_season").scop_365d),
        norm: val("cop_normalized_a7w35"), vsSheet: val("cop_vs_datasheet_pct"),
        band: at("cop_vs_datasheet_pct").band || null,
        degr: (st("cop_degradation_status") && st("cop_degradation_status").state) || null,
        degrWeek: num(at("cop_degradation_status").week_pct),
        trend: val("cop_trend_30d"), trendValid: at("cop_trend_30d").valid === true,
      },
    };
  }

  /* live buffer: append the current thermal_power_live state (once per update) */
  function appendLive(buf, hass, ids, now) {
    const id = ids.thermal_power_live, st = id && hass.states[id];
    if (!st) return false;
    const t = Date.parse(st.last_updated || "") / 1000 || now;
    const last = buf.samples[buf.samples.length - 1];
    if (last && last.t >= t) return false;
    buf.samples.push(sampleOf(t, st.state, st.attributes));
    for (const role of ["compressor_running", "defrost_active", "dhw_active", "buh_active"]) {
      const b = ids[role] && hass.states[ids[role]];
      if (!b) continue;
      const list = buf.spans[role] = buf.spans[role] || [];
      const v = on(b.state), prev = list[list.length - 1];
      if (!prev || prev.on !== v) list.push({ t: Date.parse(b.last_changed || "") / 1000 || t, on: v });
    }
    const keep = now - RANGES["24h"] - 600;
    while (buf.samples.length && buf.samples[0].t < keep) buf.samples.shift();
    return true;
  }

  Object.assign(P, {
    data: {
      DOMAIN, LANGS, SUFFIX, BINARY, REQUIRED_ROLES, HISTORY_ROLES, RANGES,
      esc, num, on, mean, pickLang, resolveEntities, sampleOf, parseHistory, toSpans, windowed,
      mean10, fitCurve, bucketPoints, datasheetCop, carnot, buildModel, appendLive,
    },
  });
  if (window.__dcmEffBoot) window.__dcmEffBoot();
})();
