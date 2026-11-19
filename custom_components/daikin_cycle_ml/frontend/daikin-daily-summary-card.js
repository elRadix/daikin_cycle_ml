/*
 * Daikin Cycle ML — Daily summary card (native Lovelace card)
 *
 *   type: custom:daikin-daily-summary-card
 *
 * Served by the integration itself: no HACS frontend cards needed
 * (no button-card, stack-in-card, card-mod). Loaded automatically on
 * every dashboard once the integration is set up.
 *
 * Tabs: Today (live run, today's numbers, today's alerts), Overview,
 * Quality, Cycles, Duration, Events. Day details on tap. English /
 * Dutch / French. Light and dark theme follow Home Assistant. Entities
 * are found through the entity registry (any language, several heat
 * pumps via device_id).
 *
 * Config (all optional):
 *   device_id:   pick the heat pump when there are several
 *   title:       header title (default: "Daily summary")
 *   default_tab: today | overview | quality | cycles | duration | events
 *   window:      7 | 15 | 30 (days)
 *   tabs:        list of tabs to show (default: all)
 *   language:    '' (auto) | en | nl | fr
 *   show_help:   true | false
 */
(function () {
  "use strict";

  const CARD_VERSION = "1.0.0";
  const TAG = "daikin-daily-summary-card";
  const EDITOR_TAG = "daikin-daily-summary-card-editor";
  const DOMAIN = "daikin_cycle_ml";
  const TABS = ["today", "overview", "quality", "cycles", "duration", "events"];
  const WINDOWS = [7, 15, 30];
  const MODES = ["heating", "dhw", "cooling"];
  const LANGS = ["en", "nl", "fr"];

  /* role -> object-id suffixes in en / nl / fr (fallback when the entity
     registry is not available). Generated from translations/*.json and
     checked by tests/test_daily_summary_native_card.py. */
  const SUFFIX = {
    daily_summary_recent: ["daily_summary_recent", "recent_dagoverzicht", "resume_des_derniers_jours"],
    hp_specs: ["hp_specs", "wp_specs", "caracteristiques_de_la_pac"],
    cycle_state: ["cycle_state", "cyclus_status", "etat_du_cycle"],
    current_cycle: ["current_cycle", "huidige_cyclus", "cycle_en_cours"],
    last_cycle: ["last_cycle", "laatste_cyclus", "dernier_cycle"],
    quality_today: ["quality_today", "kwaliteit_vandaag", "qualite_du_jour"],
    cycles_today: ["cycles_today", "cycli_vandaag", "cycles_aujourd_hui"],
    compressor_starts_today: ["compressor_starts_today", "compressorstarts_vandaag", "demarrages_compresseur_aujourd_hui"],
    runtime_compressor_today: ["runtime_compressor_today", "compressorbedrijfstijd_vandaag", "marche_compresseur_aujourd_hui"],
    cop_combined_today: ["cop_combined_today", "cop_gecombineerd_vandaag", "cop_global_du_jour"],
    alerts_today: ["alerts_today", "alerts_vandaag", "alertes_aujourd_hui"],
    runtime_buh_today: ["runtime_buh_today", "buh_bedrijfstijd_vandaag", "marche_appoint_aujourd_hui"],
    defrost_count_today: ["defrost_count_today", "ontdooiingen_vandaag", "degivrages_aujourd_hui"],
  };
  const REQUIRED_ROLES = ["daily_summary_recent"];

  const C = {
    heating: "#E53935", dhw: "#29B6F6", cooling: "#1E88E5",
    buh: "#FB8C00", defrost: "#42A5F5",
    good: "#43A047", mid: "#FB8C00", low: "#E53935",
    avg: "#8E24AA", info: "#1E88E5", warning: "#FB8C00", critical: "#E53935",
  };
  const MODE_ICON = { heating: "🔥", dhw: "🚿", cooling: "❄️" };
  const ALERTS_SHOWN = 3;

  const I18N = {
    en: {
      title: "Daily summary", subtitle: "Cycles · duration · quality · events",
      tab_today: "Today", tab_overview: "Overview", tab_quality: "Quality",
      tab_cycles: "Cycles", tab_duration: "Duration", tab_events: "Events",
      days: "days", d: "d", heating: "Heating", dhw: "Hot water", cooling: "Cooling",
      running: "Running", idle: "Compressor off", since: "since", run_for: "running for",
      live_score: "Live score", cycles_today: "Cycles today", starts_today: "Starts today",
      runtime_today: "Runtime today", cop_today: "COP today", quality_today: "Quality today",
      buh_today: "Backup heater", defrost_today: "Defrosts",
      alerts_today: "Today's alerts", no_alerts: "No alerts today",
      first_run: "The first cycle is still running. Quality and per-cycle numbers appear when it ends.",
      no_data: "No daily data yet. Numbers appear after the first full day.",
      not_found: "Daikin Cycle ML entities not found. Is the integration set up?",
      quality: "Quality", avg_quality: "Avg quality", cycles: "Cycles", runtime: "Runtime",
      avg_run: "Avg run", longest: "Longest run", best_day: "Best day", worst_day: "Worst day",
      mode_split: "Runtime per mode", trends: "Trends", per_day: "per day",
      good_days: "Good days", mid_days: "Mid days", low_days: "Low days",
      total: "Total", avg_day: "Avg/day", max_day: "Max day",
      buh_min: "Backup heater (min)", defrost_events: "Defrosts", per_cycle: "per cycle",
      quality_chart: "Quality per day", cycles_chart: "Cycles per day",
      duration_chart: "Runtime per day", events_chart: "Events per day",
      good: "Good ≥70", mid: "Mid 40–70", low: "Low <40", avg: "average",
      tap_day: "Tap a day for details", close: "Close",
      day_open: "includes the run still going",
      h_quality: "Quality = average score of the cycles that started that day (0–100). The average counts every cycle once.",
      h_cycles: "A cycle is one continuous compressor run. Many short cycles cost efficiency and wear.",
      h_duration: "Runtime per day split per mode. Runs crossing midnight count on both days.",
      h_events: "Backup-heater minutes and defrosts per day. Few is good.",
      h_today: "Live values of today. The day resets at midnight.",
      sev_info: "info", sev_warning: "warning", sev_critical: "critical",
      ago: "ago", today: "today", yesterday: "yesterday", show_all: "Show all", show_less: "Show less",
    },
    nl: {
      title: "Dagoverzicht", subtitle: "Cycli · duur · kwaliteit · events",
      tab_today: "Vandaag", tab_overview: "Overzicht", tab_quality: "Kwaliteit",
      tab_cycles: "Cycli", tab_duration: "Duur", tab_events: "Events",
      days: "dagen", d: "d", heating: "Verwarming", dhw: "Warm water", cooling: "Koeling",
      running: "In bedrijf", idle: "Compressor uit", since: "sinds", run_for: "draait",
      live_score: "Live score", cycles_today: "Cycli vandaag", starts_today: "Starts vandaag",
      runtime_today: "Bedrijfstijd vandaag", cop_today: "COP vandaag", quality_today: "Kwaliteit vandaag",
      buh_today: "Backup heater", defrost_today: "Ontdooiingen",
      alerts_today: "Meldingen vandaag", no_alerts: "Geen meldingen vandaag",
      first_run: "De eerste cyclus loopt nog. Kwaliteit en cijfers per cyclus verschijnen zodra hij stopt.",
      no_data: "Nog geen dagdata. De cijfers verschijnen na de eerste volledige dag.",
      not_found: "Daikin Cycle ML-entiteiten niet gevonden. Is de integratie ingesteld?",
      quality: "Kwaliteit", avg_quality: "Gem. kwaliteit", cycles: "Cycli", runtime: "Bedrijfstijd",
      avg_run: "Gem. run", longest: "Langste run", best_day: "Beste dag", worst_day: "Slechtste dag",
      mode_split: "Bedrijfstijd per modus", trends: "Trends", per_day: "per dag",
      good_days: "Goede dagen", mid_days: "Matige dagen", low_days: "Slechte dagen",
      total: "Totaal", avg_day: "Gem./dag", max_day: "Max dag",
      buh_min: "Backup heater (min)", defrost_events: "Ontdooiingen", per_cycle: "per cyclus",
      quality_chart: "Kwaliteit per dag", cycles_chart: "Cycli per dag",
      duration_chart: "Bedrijfstijd per dag", events_chart: "Events per dag",
      good: "Goed ≥70", mid: "Matig 40–70", low: "Laag <40", avg: "gemiddelde",
      tap_day: "Tik op een dag voor details", close: "Sluiten",
      day_open: "inclusief de lopende run",
      h_quality: "Kwaliteit = gemiddelde score van de cycli die die dag startten (0–100). Het gemiddelde telt elke cyclus één keer.",
      h_cycles: "Een cyclus is één ononderbroken compressorrun. Veel korte cycli kosten rendement en slijtage.",
      h_duration: "Bedrijfstijd per dag per modus. Runs over middernacht tellen op beide dagen.",
      h_events: "Minuten backup heater en ontdooiingen per dag. Weinig is goed.",
      h_today: "Live waarden van vandaag. De dag begint opnieuw om middernacht.",
      sev_info: "info", sev_warning: "waarschuwing", sev_critical: "kritiek",
      ago: "geleden", today: "vandaag", yesterday: "gisteren", show_all: "Alles tonen", show_less: "Minder tonen",
    },
    fr: {
      title: "Résumé quotidien", subtitle: "Cycles · durée · qualité · événements",
      tab_today: "Aujourd'hui", tab_overview: "Synthèse", tab_quality: "Qualité",
      tab_cycles: "Cycles", tab_duration: "Durée", tab_events: "Événements",
      days: "jours", d: "j", heating: "Chauffage", dhw: "Eau chaude", cooling: "Rafraîchissement",
      running: "En marche", idle: "Compresseur arrêté", since: "depuis", run_for: "en marche depuis",
      live_score: "Score en direct", cycles_today: "Cycles du jour", starts_today: "Démarrages du jour",
      runtime_today: "Marche du jour", cop_today: "COP du jour", quality_today: "Qualité du jour",
      buh_today: "Appoint", defrost_today: "Dégivrages",
      alerts_today: "Alertes du jour", no_alerts: "Aucune alerte aujourd'hui",
      first_run: "Le premier cycle est toujours en cours. La qualité et les chiffres par cycle apparaissent à sa fin.",
      no_data: "Pas encore de données journalières. Elles apparaissent après la première journée complète.",
      not_found: "Entités Daikin Cycle ML introuvables. L'intégration est-elle configurée ?",
      quality: "Qualité", avg_quality: "Qualité moy.", cycles: "Cycles", runtime: "Marche",
      avg_run: "Cycle moy.", longest: "Plus long cycle", best_day: "Meilleur jour", worst_day: "Pire jour",
      mode_split: "Marche par mode", trends: "Tendances", per_day: "par jour",
      good_days: "Bons jours", mid_days: "Jours moyens", low_days: "Jours faibles",
      total: "Total", avg_day: "Moy./jour", max_day: "Jour max",
      buh_min: "Appoint (min)", defrost_events: "Dégivrages", per_cycle: "par cycle",
      quality_chart: "Qualité par jour", cycles_chart: "Cycles par jour",
      duration_chart: "Marche par jour", events_chart: "Événements par jour",
      good: "Bon ≥70", mid: "Moyen 40–70", low: "Faible <40", avg: "moyenne",
      tap_day: "Toucher un jour pour le détail", close: "Fermer",
      day_open: "cycle en cours compris",
      h_quality: "Qualité = score moyen des cycles démarrés ce jour-là (0–100). La moyenne compte chaque cycle une fois.",
      h_cycles: "Un cycle est une marche continue du compresseur. Beaucoup de cycles courts coûtent rendement et usure.",
      h_duration: "Marche par jour et par mode. Un cycle à cheval sur minuit compte sur les deux jours.",
      h_events: "Minutes d'appoint et dégivrages par jour. Peu, c'est bien.",
      h_today: "Valeurs du jour en direct. La journée repart à minuit.",
      sev_info: "info", sev_warning: "avertissement", sev_critical: "critique",
      ago: "plus tôt", today: "aujourd'hui", yesterday: "hier", show_all: "Tout afficher", show_less: "Afficher moins",
    },
  };

  /* ------------------------------------------------------------------ */
  /* pure helpers (exported for tests on window.DaikinDailySummaryCard)  */
  /* ------------------------------------------------------------------ */

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
      let found = null;
      for (const id of Object.keys(ents)) {
        const e = ents[id];
        if (!e || e.platform !== DOMAIN || e.translation_key !== role) continue;
        if (id.indexOf("sensor.") !== 0 || !states[id]) continue;
        if (dev && e.device_id !== dev) continue;
        found = id; break;
      }
      if (!found && !dev) {
        const ids = Object.keys(states).filter((i) => i.indexOf("sensor.") === 0);
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

  /* per-day rows (one per day + mode) -> one object per day */
  function buildDays(attrs) {
    const rows = Array.isArray(attrs && attrs.days) ? attrs.days : [];
    const ev = (attrs && attrs.events_by_day) || {};
    const by = {};
    for (const r of rows) {
      if (!r || !r.day) continue;
      const d = by[r.day] || (by[r.day] = {
        day: r.day, cycles: 0, runs: 0, dur_min: 0, dur_max: 0,
        q_sum: 0, q_w: 0, quality: null, buh: 0, defrost: 0,
        buh_min: null, defrost_events: null,
        modes: { heating: null, dhw: null, cooling: null },
      });
      const cyc = num(r.cycles) || 0;
      const runs = num(r.runs) !== null ? num(r.runs) : cyc;
      const dur = num(r.dur_min) || 0;
      d.cycles += cyc; d.runs += runs; d.dur_min += dur;
      d.dur_max = Math.max(d.dur_max, num(r.dur_max) || 0);
      d.buh += num(r.buh) || 0; d.defrost += num(r.defrost) || 0;
      const q = num(r.quality_avg);
      if (q !== null) { const w = Math.max(1, cyc); d.q_sum += q * w; d.q_w += w; }
      const m = MODES.includes(r.mode) ? r.mode : null;
      if (m) d.modes[m] = { cycles: cyc, runs, dur_min: dur, quality: q, dur_max: num(r.dur_max) || 0 };
    }
    return Object.values(by).map((d) => {
      d.quality = d.q_w > 0 ? d.q_sum / d.q_w : null;
      d.avg_run = d.runs > 0 ? d.dur_min / d.runs : null;
      const e = ev[d.day];
      if (e) {
        d.buh_min = num(e.buh_min);
        d.defrost_events = num(e.defrost_events);
      }
      d.defrosts = Math.max(d.defrost, d.defrost_events || 0);
      return d;
    }).sort((a, b) => (a.day < b.day ? -1 : 1));
  }

  /* period statistics over the window (#436: quality = all cycles) */
  function periodStats(days) {
    const s = {
      days: days.length, cycles: 0, runs: 0, minutes: 0, q_sum: 0, q_w: 0,
      buh_min: 0, buh_days: 0, defrosts: 0, longest: 0,
      mode_min: { heating: 0, dhw: 0, cooling: 0 }, mode_cycles: { heating: 0, dhw: 0, cooling: 0 },
      good: 0, mid: 0, low: 0, best: null, worst: null,
    };
    for (const d of days) {
      s.cycles += d.cycles; s.runs += d.runs; s.minutes += d.dur_min;
      s.q_sum += d.q_sum; s.q_w += d.q_w;
      s.buh_min += d.buh_min || 0;
      if ((d.buh_min || 0) > 0 || d.buh > 0) s.buh_days += 1;
      s.defrosts += d.defrosts; s.longest = Math.max(s.longest, d.dur_max);
      for (const m of MODES) {
        if (d.modes[m]) { s.mode_min[m] += d.modes[m].dur_min; s.mode_cycles[m] += d.modes[m].cycles; }
      }
      if (d.quality !== null) {
        if (d.quality >= 70) s.good++; else if (d.quality >= 40) s.mid++; else s.low++;
        if (!s.best || d.quality > s.best.quality) s.best = d;
        if (!s.worst || d.quality < s.worst.quality) s.worst = d;
      }
    }
    if (s.best && s.worst && s.best.day === s.worst.day) s.worst = null;
    s.quality = s.q_w > 0 ? s.q_sum / s.q_w : null;
    s.avg_run = s.runs > 0 ? s.minutes / s.runs : null;
    s.cycles_per_day = s.days > 0 ? s.cycles / s.days : null;
    return s;
  }

  const qColor = (q) => (q === null || q === undefined ? "var(--secondary-text-color)"
    : q >= 70 ? C.good : q >= 40 ? C.mid : C.low);

  /* ------------------------------------------------------------------ */
  /* formatting                                                          */
  /* ------------------------------------------------------------------ */

  function makeFmt(lang) {
    const nf1 = new Intl.NumberFormat(lang, { maximumFractionDigits: 1, minimumFractionDigits: 1 });
    const nf0 = new Intl.NumberFormat(lang, { maximumFractionDigits: 0 });
    const wd = new Intl.DateTimeFormat(lang, { weekday: "short" });
    const dm = new Intl.DateTimeFormat(lang, { day: "numeric", month: "short" });
    const hm = new Intl.DateTimeFormat(lang, { hour: "2-digit", minute: "2-digit" });
    const date = (day) => { const p = String(day).split("-").map(Number); return new Date(p[0], p[1] - 1, p[2]); };
    return {
      n0: (v) => (v === null || v === undefined || !isFinite(v) ? "—" : nf0.format(v)),
      n1: (v) => (v === null || v === undefined || !isFinite(v) ? "—" : nf1.format(v)),
      pct: (v) => (v === null || v === undefined || !isFinite(v) ? "—" : nf0.format(v) + " %"),
      dur: (min) => {
        if (min === null || min === undefined || !isFinite(min)) return "—";
        if (min < 60) return nf0.format(min) + " min";
        const h = Math.floor(min / 60), m = Math.round(min - h * 60);
        return h + " h" + (m ? " " + String(m).padStart(2, "0") : "");
      },
      hours: (min) => (min === null || !isFinite(min) ? "—" : nf1.format(min / 60) + " h"),
      wd: (day) => wd.format(date(day)),
      dm: (day) => dm.format(date(day)),
      time: (ts) => hm.format(new Date(ts)),
      date,
    };
  }

  /* ------------------------------------------------------------------ */
  /* SVG charts                                                          */
  /* ------------------------------------------------------------------ */

  const W = 360;

  function chartFrame(h, yMax, ticks, fmtTick) {
    const top = 14, bottom = h - 26, left = 30, right = W - 6;
    const y = (v) => bottom - (v / yMax) * (bottom - top);
    let s = "";
    for (const t of ticks) {
      s += `<line x1="${left}" x2="${right}" y1="${y(t)}" y2="${y(t)}" class="grid"/>`
        + `<text x="${left - 4}" y="${y(t) + 3}" class="tick" text-anchor="end">${esc(fmtTick(t))}</text>`;
    }
    return { s, top, bottom, left, right, y };
  }

  function niceMax(v) {
    if (!(v > 0)) return 1;
    const p = Math.pow(10, Math.floor(Math.log10(v)));
    for (const m of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * p >= v) return m * p;
    return 10 * p;
  }

  function xAxis(days, f, fr, sel) {
    const n = days.length, slot = (fr.right - fr.left) / Math.max(1, n);
    const every = n > 16 ? 3 : n > 9 ? 2 : 1;
    let s = "";
    days.forEach((d, i) => {
      if (i % every !== 0 && i !== n - 1) return;
      const x = fr.left + slot * (i + 0.5);
      s += `<text x="${x}" y="${fr.bottom + 11}" class="xl${sel === d.day ? " sel" : ""}" text-anchor="middle">${esc(f.wd(d.day))}</text>`
        + `<text x="${x}" y="${fr.bottom + 21}" class="xs" text-anchor="middle">${esc(f.date(d.day).getDate())}</text>`;
    });
    return { s, slot };
  }

  /* stacked bars: series = [{key, color, get(d)}] */
  function barChart(days, series, opts, f, sel) {
    const h = 170;
    const totals = days.map((d) => series.reduce((a, se) => a + (se.get(d) || 0), 0));
    const yMax = niceMax(Math.max(1, ...totals));
    const fr = chartFrame(h, yMax, [0, yMax / 2, yMax], opts.tick);
    const ax = xAxis(days, f, fr, sel);
    const bw = Math.max(4, Math.min(26, ax.slot * 0.62));
    let bars = "";
    days.forEach((d, i) => {
      const x = fr.left + ax.slot * (i + 0.5) - bw / 2;
      let acc = 0;
      for (const se of series) {
        const v = se.get(d) || 0;
        if (v <= 0) continue;
        const y0 = fr.y(acc), y1 = fr.y(acc + v);
        bars += `<rect x="${x}" y="${y1}" width="${bw}" height="${Math.max(0.5, y0 - y1)}" rx="2" fill="${se.color}"/>`;
        acc += v;
      }
      if (opts.label && totals[i] > 0 && days.length <= 15) {
        bars += `<text x="${x + bw / 2}" y="${fr.y(totals[i]) - 3}" class="val" text-anchor="middle">${esc(opts.label(totals[i]))}</text>`;
      }
      bars += `<rect x="${fr.left + ax.slot * i}" y="${fr.top}" width="${ax.slot}" height="${fr.bottom - fr.top}" class="hit${sel === d.day ? " on" : ""}" data-day="${esc(d.day)}"/>`;
    });
    let avg = "";
    if (opts.avg !== null && opts.avg !== undefined && opts.avg > 0) {
      avg = `<line x1="${fr.left}" x2="${fr.right}" y1="${fr.y(opts.avg)}" y2="${fr.y(opts.avg)}" class="avgline"/>`;
    }
    return `<svg viewBox="0 0 ${W} ${h}" class="chart" role="img">${fr.s}${bars}${avg}${ax.s}</svg>`;
  }

  function qualityChart(days, avg, f, sel) {
    const h = 170;
    const qs = days.map((d) => d.quality).filter((q) => q !== null);
    const lo = qs.length && Math.min(...qs) >= 70 ? 50 : qs.length && Math.min(...qs) >= 40 ? 20 : 0;
    const base = chartFrame(h, 100 - lo, [], String);
    const fr = Object.assign({}, base, { y: (v) => base.y(Math.max(0, v - lo)) });
    fr.s = [lo, 40, 70, 100].filter((t) => t >= lo).map((t) => `<line x1="${fr.left}" x2="${fr.right}" y1="${fr.y(t)}" y2="${fr.y(t)}" class="grid"/>`
      + `<text x="${fr.left - 4}" y="${fr.y(t) + 3}" class="tick" text-anchor="end">${t}</text>`).join("");
    const ax = xAxis(days, f, fr, sel);
    const band = (a, b, col) => `<rect x="${fr.left}" y="${fr.y(b)}" width="${fr.right - fr.left}" height="${fr.y(a) - fr.y(b)}" fill="${col}" opacity="0.08"/>`;
    let s = band(70, 100, C.good) + (lo < 70 ? band(Math.max(lo, 40), 70, C.mid) : "") + (lo < 40 ? band(lo, 40, C.low) : "");
    const pts = [];
    days.forEach((d, i) => { if (d.quality !== null) pts.push({ d, x: fr.left + ax.slot * (i + 0.5), y: fr.y(d.quality) }); });
    if (avg !== null) s += `<line x1="${fr.left}" x2="${fr.right}" y1="${fr.y(avg)}" y2="${fr.y(avg)}" class="avgline"/>`;
    if (pts.length > 1) s += `<polyline points="${pts.map((p) => p.x + "," + p.y).join(" ")}" class="qline"/>`;
    pts.forEach((p, i) => {
      const last = i === pts.length - 1;
      s += `<circle cx="${p.x}" cy="${p.y}" r="${last ? 5 : 4}" fill="var(--card-background-color, #fff)" stroke="${qColor(p.d.quality)}" stroke-width="2.5"/>`;
      if (days.length <= 15) s += `<text x="${p.x}" y="${p.y - 8}" class="val" text-anchor="middle" fill="${qColor(p.d.quality)}">${esc(f.n0(p.d.quality))}</text>`;
    });
    days.forEach((d, i) => {
      s += `<rect x="${fr.left + ax.slot * i}" y="${fr.top}" width="${ax.slot}" height="${fr.bottom - fr.top}" class="hit${sel === d.day ? " on" : ""}" data-day="${esc(d.day)}"/>`;
    });
    return `<svg viewBox="0 0 ${W} ${h}" class="chart" role="img">${fr.s}${s}${ax.s}</svg>`;
  }

  function spark(values, color) {
    const v = values.filter((x) => x !== null && isFinite(x));
    if (v.length < 2) return "";
    const max = Math.max(...v), min = Math.min(0, ...v), w = 100, h = 28;
    const pts = values.map((x, i) => (x === null || !isFinite(x) ? null
      : (i / (values.length - 1)) * w + "," + (h - 2 - ((x - min) / Math.max(1e-9, max - min)) * (h - 4)))).filter(Boolean);
    return `<svg viewBox="0 0 ${w} ${h}" class="spark" preserveAspectRatio="none"><polyline points="${pts.join(" ")}" fill="none" stroke="${color}" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`;
  }

  /* ------------------------------------------------------------------ */
  /* view model + rendering                                              */
  /* ------------------------------------------------------------------ */

  function buildModel(hass, config, now) {
    const ids = resolveEntities(hass, config);
    const st = (role) => (ids[role] && hass.states[ids[role]]) || null;
    const at = (role) => (st(role) && st(role).attributes) || {};
    const lang = pickLang(hass, config, at("cycle_state"));
    const ok = REQUIRED_ROLES.every((r) => ids[r]);
    const allDays = ok ? buildDays(at("daily_summary_recent")) : [];
    const win = WINDOWS.includes(Number(config.window)) ? Number(config.window) : 7;
    const specs = at("hp_specs");
    const cur = st("current_cycle");
    const curA = at("current_cycle");
    const running = !!(cur && cur.state && !["idle", "unknown", "unavailable", "off"].includes(cur.state));
    const alertsA = at("alerts_today");
    return {
      ids, ok, lang, win, allDays, now: now || Date.now(),
      model: specs.model ? String(specs.model).toUpperCase() : "",
      meta: [specs.family, num(specs.kw) ? num(specs.kw) + " kW" : "", specs.refrigerant]
        .filter((x) => x && String(x) !== "None").join(" · "),
      today: {
        running, mode: running ? cur.state : null,
        duration_min: num(curA.duration_min), started_at: num(curA.started_at),
        live_score: num(at("quality_today").live_score),
        quality: num(st("quality_today") && st("quality_today").state),
        cycles: num(st("cycles_today") && st("cycles_today").state),
        starts: num(st("compressor_starts_today") && st("compressor_starts_today").state),
        runtime_s: num(st("runtime_compressor_today") && st("runtime_compressor_today").state),
        cop: num(st("cop_combined_today") && st("cop_combined_today").state),
        buh_s: num(st("runtime_buh_today") && st("runtime_buh_today").state),
        defrosts: num(st("defrost_count_today") && st("defrost_count_today").state),
        last_cycle_known: num(st("last_cycle") && st("last_cycle").state) !== null,
        alerts: Array.isArray(alertsA.alerts) ? alertsA.alerts : [],
      },
    };
  }

  /* title line of an alert message ("🧠 Daikin Cycle ML — ML anomaly detected") */
  function alertTitle(a) {
    const first = String((a && a.message) || "").split("\n")[0];
    const i = first.indexOf("—");
    const t = (i >= 0 ? first.slice(i + 1) : first).trim();
    return t || String((a && a.type) || "").replace(/_/g, " ");
  }

  /* body of an alert message: without the title and separator lines */
  function alertBody(a) {
    return String((a && a.message) || "").split("\n").slice(1)
      .filter((l) => !/^[\s━─=\-_]+$/.test(l)).join("\n").trim();
  }

  function tile(label, value, color, sub) {
    return `<div class="tile"><div class="tl">${esc(label)}</div>`
      + `<div class="tv"${color ? ` style="color:${color}"` : ""}>${esc(value)}</div>`
      + (sub ? `<div class="ts">${esc(sub)}</div>` : "") + `</div>`;
  }

  function legend(items) {
    return `<div class="legend">${items.map((it) => `<span><i style="background:${it.c}"></i>${esc(it.l)}</span>`).join("")}</div>`;
  }

  function dayDetail(d, t, f) {
    if (!d) return "";
    let modes = "";
    for (const m of MODES) {
      const md = d.modes[m];
      if (!md || (md.cycles === 0 && md.dur_min === 0)) continue;
      modes += `<div class="mrow"><span>${MODE_ICON[m]} ${esc(t[m])}</span>`
        + `<span>${esc(f.n0(md.cycles))} × · ${esc(f.dur(md.dur_min))}</span>`
        + `<span style="color:${qColor(md.quality)}">${esc(md.quality === null ? "—" : f.n0(md.quality))}</span></div>`;
    }
    const open = d.runs > d.cycles;
    return `<div class="detail" role="dialog"><div class="dh"><b>${esc(f.wd(d.day))} ${esc(f.dm(d.day))}</b>`
      + `<button class="x" data-act="close" aria-label="${esc(t.close)}">✕</button></div>`
      + `<div class="tiles">`
      + tile(t.quality, d.quality === null ? "—" : f.n0(d.quality), qColor(d.quality))
      + tile(t.cycles, f.n0(d.cycles))
      + tile(t.runtime, f.dur(d.dur_min))
      + tile(t.avg_run, f.dur(d.avg_run), null, open ? t.day_open : "")
      + tile(t.longest, f.dur(d.dur_max))
      + tile(t.buh_min, d.buh_min === null ? f.n0(d.buh) + " ×" : f.n0(d.buh_min), (d.buh_min || d.buh) ? C.buh : null)
      + tile(t.defrost_events, f.n0(d.defrosts), d.defrosts ? C.defrost : null)
      + `</div>${modes ? `<div class="modes">${modes}</div>` : ""}</div>`;
  }

  function renderToday(m, t, f, ui) {
    const td = m.today;
    let s = "";
    const runFor = td.running && td.started_at ? Math.max(0, (m.now / 1000 - td.started_at) / 60) : td.duration_min;
    s += `<div class="banner ${td.running ? "on" : ""}">`
      + `<span class="dot"></span><b>${td.running ? esc(MODE_ICON[td.mode] || "") + " " + esc(t.running) + " · " + esc(t[td.mode] || td.mode) : esc(t.idle)}</b>`
      + (td.running && runFor !== null ? `<span class="muted">${esc(t.run_for)} ${esc(f.dur(runFor))}${td.started_at ? " · " + esc(t.since) + " " + esc(f.time(td.started_at * 1000)) : ""}</span>` : "")
      + (td.running && td.live_score !== null ? `<span class="pill" style="background:${qColor(td.live_score)}">${esc(t.live_score)} ${esc(f.n0(td.live_score))}</span>` : "")
      + `</div>`;
    if (td.running && !td.last_cycle_known && (td.cycles || 0) === 0) s += `<div class="note">ℹ️ ${esc(t.first_run)}</div>`;
    s += `<div class="tiles">`
      + tile(t.cycles_today, f.n0(td.cycles))
      + tile(t.starts_today, f.n0(td.starts))
      + tile(t.runtime_today, td.runtime_s === null ? "—" : f.dur(td.runtime_s / 60))
      + tile(t.cop_today, td.cop === null ? "—" : f.n1(td.cop))
      + tile(t.quality_today, td.quality === null ? "—" : f.n0(td.quality), qColor(td.quality))
      + tile(t.buh_today, td.buh_s === null ? "—" : f.dur(td.buh_s / 60), td.buh_s ? C.buh : null)
      + tile(t.defrost_today, f.n0(td.defrosts), td.defrosts ? C.defrost : null)
      + `</div>`;
    s += `<div class="sect">${esc(t.alerts_today)}${td.alerts.length ? ` · ${td.alerts.length}` : ""}</div>`;
    if (!td.alerts.length) {
      s += `<div class="note ok">✅ ${esc(t.no_alerts)}</div>`;
    } else {
      const shown = ui.allAlerts ? td.alerts : td.alerts.slice(0, ALERTS_SHOWN);
      shown.forEach((a, i) => {
        const sev = String(a.severity || "info");
        const col = C[sev] || C.info;
        const open = ui.alert === i;
        s += `<div class="alert" style="border-left-color:${col}" data-act="alert" data-i="${i}" tabindex="0" role="button" aria-expanded="${open}">`
          + `<div class="ah"><span>${esc(alertTitle(a))}</span><span class="muted">${esc(String(a.time || "").slice(11, 16))}`
          + `${(num(a.count) || 0) > 1 ? " · " + esc(a.count) + "×" : ""} · <b style="color:${col}">${esc(t["sev_" + sev] || sev)}</b></span></div>`
          + (open ? `<pre class="msg">${esc(alertBody(a))}</pre>` : "")
          + `</div>`;
      });
      if (td.alerts.length > ALERTS_SHOWN) {
        s += `<button class="more" data-act="more">${esc(ui.allAlerts ? t.show_less : t.show_all + " (" + td.alerts.length + ")")}</button>`;
      }
    }
    return s;
  }

  function renderOverview(days, ps, m, t, f, ui) {
    let s = `<div class="tiles">`
      + tile(t.avg_quality, ps.quality === null ? "—" : f.n0(ps.quality), qColor(ps.quality))
      + tile(t.cycles, f.n0(ps.cycles), null, f.n1(ps.cycles_per_day) + " " + t.per_day)
      + tile(t.runtime, f.hours(ps.minutes))
      + tile(t.avg_run, f.dur(ps.avg_run))
      + tile(t.buh_min, f.n0(ps.buh_min), ps.buh_min ? C.buh : null)
      + tile(t.defrost_events, f.n0(ps.defrosts), ps.defrosts ? C.defrost : null)
      + `</div>`;
    const tot = MODES.reduce((a, k) => a + ps.mode_min[k], 0);
    if (tot > 0) {
      s += `<div class="sect">${esc(t.mode_split)}</div><div class="split">`
        + MODES.filter((k) => ps.mode_min[k] > 0).map((k) => `<span style="flex:${ps.mode_min[k]};background:${C[k]}" title="${esc(t[k])}"></span>`).join("")
        + `</div>` + legend(MODES.filter((k) => ps.mode_min[k] > 0).map((k) => ({
          c: C[k], l: `${t[k]} ${Math.round((ps.mode_min[k] / tot) * 100)} % · ${ps.mode_cycles[k]}×`,
        })));
    }
    const bw = (lab, d, col) => (d ? `<div class="bw" data-day="${esc(d.day)}" role="button" tabindex="0" style="border-color:${col}">`
      + `<div class="tl" style="color:${col}">${esc(lab)}</div><div><b>${esc(f.wd(d.day))} ${esc(f.dm(d.day))}</b></div>`
      + `<div class="tv" style="color:${qColor(d.quality)}">${esc(f.n0(d.quality))}</div>`
      + `<div class="ts">${esc(f.n0(d.cycles))} × · ${esc(f.hours(d.dur_min))}</div></div>` : "");
    if (ps.best) s += `<div class="bwrow">${bw("🏆 " + t.best_day, ps.best, C.good)}${bw("⚠️ " + t.worst_day, ps.worst, C.low)}</div>`;
    s += `<div class="sect">${esc(t.trends)}</div><div class="sparks">`
      + `<div><span class="tl">${esc(t.quality)}</span>${spark(days.map((d) => d.quality), C.good)}</div>`
      + `<div><span class="tl">${esc(t.cycles)}</span>${spark(days.map((d) => d.cycles), C.heating)}</div>`
      + `<div><span class="tl">${esc(t.runtime)}</span>${spark(days.map((d) => d.dur_min / 60), C.cooling)}</div>`
      + `</div>`;
    return s;
  }

  function renderQuality(days, ps, t, f, ui) {
    return `<div class="sect">${esc(t.quality_chart)} <span class="muted">· ${esc(t.avg)} ${esc(ps.quality === null ? "—" : f.n0(ps.quality))}</span></div>`
      + qualityChart(days, ps.quality, f, ui.day)
      + legend([{ c: C.good, l: t.good }, { c: C.mid, l: t.mid }, { c: C.low, l: t.low }, { c: C.avg, l: t.avg }])
      + `<div class="tiles">`
      + tile(t.avg_quality, ps.quality === null ? "—" : f.n0(ps.quality), qColor(ps.quality))
      + tile(t.good_days, f.n0(ps.good), C.good) + tile(t.mid_days, f.n0(ps.mid), C.mid) + tile(t.low_days, f.n0(ps.low), C.low)
      + `</div>`;
  }

  function renderCycles(days, ps, t, f, ui) {
    const maxDay = days.reduce((a, d) => Math.max(a, d.cycles), 0);
    const present = MODES.filter((k) => ps.mode_cycles[k] > 0);
    return `<div class="sect">${esc(t.cycles_chart)}</div>`
      + barChart(days, MODES.map((k) => ({ key: k, color: C[k], get: (d) => (d.modes[k] ? d.modes[k].cycles : 0) })),
        { tick: (v) => f.n0(v), label: (v) => f.n0(v), avg: ps.cycles_per_day }, f, ui.day)
      + legend(present.map((k) => ({ c: C[k], l: t[k] })).concat([{ c: C.avg, l: t.avg }]))
      + `<div class="tiles">` + tile(t.total, f.n0(ps.cycles)) + tile(t.avg_day, f.n1(ps.cycles_per_day))
      + tile(t.max_day, f.n0(maxDay)) + tile(t.avg_run, f.dur(ps.avg_run)) + `</div>`;
  }

  function renderDuration(days, ps, t, f, ui) {
    const present = MODES.filter((k) => ps.mode_min[k] > 0);
    return `<div class="sect">${esc(t.duration_chart)}</div>`
      + barChart(days, MODES.map((k) => ({ key: k, color: C[k], get: (d) => (d.modes[k] ? d.modes[k].dur_min / 60 : 0) })),
        { tick: (v) => f.n0(v) + "h", label: (v) => f.n1(v), avg: ps.days ? ps.minutes / 60 / ps.days : null }, f, ui.day)
      + legend(present.map((k) => ({ c: C[k], l: t[k] })).concat([{ c: C.avg, l: t.avg }]))
      + `<div class="tiles">` + tile(t.total, f.hours(ps.minutes)) + tile(t.avg_day, f.hours(ps.days ? ps.minutes / ps.days : null))
      + tile(t.avg_run, f.dur(ps.avg_run)) + tile(t.longest, f.dur(ps.longest)) + `</div>`;
  }

  function renderEvents(days, ps, t, f, ui) {
    const perCycle = (x) => (ps.cycles > 0 ? f.n1(x / ps.cycles) : "—");
    return `<div class="sect">${esc(t.events_chart)}</div>`
      + barChart(days, [
        { key: "defrost", color: C.defrost, get: (d) => d.defrosts },
      ], { tick: (v) => f.n0(v), label: (v) => f.n0(v), avg: null }, f, ui.day)
      + legend([{ c: C.defrost, l: t.defrost_events }])
      + barChart(days, [
        { key: "buh", color: C.buh, get: (d) => d.buh_min || 0 },
      ], { tick: (v) => f.n0(v), label: (v) => f.n0(v), avg: null }, f, ui.day)
      + legend([{ c: C.buh, l: t.buh_min }])
      + `<div class="tiles">` + tile(t.defrost_events, f.n0(ps.defrosts), ps.defrosts ? C.defrost : null, perCycle(ps.defrosts) + " " + t.per_cycle)
      + tile(t.buh_min, f.n0(ps.buh_min), ps.buh_min ? C.buh : null, f.n0(ps.buh_days) + " " + t.days) + `</div>`;
  }

  function render(m, config, ui) {
    const t = I18N[m.lang];
    const f = makeFmt(m.lang);
    const title = config.title || t.title;
    const tabs = (Array.isArray(config.tabs) && config.tabs.length ? config.tabs : TABS).filter((x) => TABS.includes(x));
    const tab = tabs.includes(ui.tab) ? ui.tab : tabs[0];
    const head = `<div class="head"><div class="ic">📅</div><div class="hm">`
      + `<div class="ht">${esc(title)}${m.model ? " · " + esc(m.model) : ""}</div>`
      + `<div class="hs">${esc(t.subtitle)}${m.meta ? " · " + esc(m.meta) : ""}</div></div></div>`;
    if (!m.ok) return head + `<div class="body"><div class="note warn">⚠️ ${esc(t.not_found)}</div></div>`;
    const days = m.allDays.slice(-ui.win);
    const ps = periodStats(days);
    const showWin = tab !== "today";
    let s = head + `<div class="tabs n${tabs.length}" role="tablist">`
      + tabs.map((k) => `<button role="tab" class="tab${k === tab ? " on" : ""}" aria-selected="${k === tab}" data-act="tab" data-tab="${k}">${esc(t["tab_" + k])}</button>`).join("")
      + `</div><div class="body">`;
    if (showWin) {
      s += `<div class="wins">` + WINDOWS.map((w) => `<button class="win${w === ui.win ? " on" : ""}" data-act="win" data-win="${w}">${w} ${esc(t.d)}</button>`).join("")
        + `<span class="muted">${days.length ? esc(f.dm(days[0].day)) + " → " + esc(f.dm(days[days.length - 1].day)) : ""}</span></div>`;
    }
    if (tab === "today") s += renderToday(m, t, f, ui);
    else if (!days.length) s += `<div class="note">ℹ️ ${esc(t.no_data)}</div>`;
    else if (tab === "overview") s += renderOverview(days, ps, m, t, f, ui);
    else if (tab === "quality") s += renderQuality(days, ps, t, f, ui);
    else if (tab === "cycles") s += renderCycles(days, ps, t, f, ui);
    else if (tab === "duration") s += renderDuration(days, ps, t, f, ui);
    else if (tab === "events") s += renderEvents(days, ps, t, f, ui);
    if (showWin && days.length) {
      s += dayDetail(days.find((d) => d.day === ui.day), t, f);
      if (!ui.day && tab !== "overview") s += `<div class="hint">👆 ${esc(t.tap_day)}</div>`;
    }
    if (config.show_help !== false && t["h_" + tab]) s += `<div class="help">💡 ${esc(t["h_" + tab])}</div>`;
    return s + `</div>`;
  }

  const STYLE = `
    :host { display: block; }
    ha-card { overflow: hidden; }
    .head { display: flex; gap: 12px; align-items: center; padding: 14px 16px;
      background: linear-gradient(135deg, rgba(0,151,224,0.16), rgba(0,151,224,0.04));
      border-bottom: 3px solid var(--dcm-accent, #0097E0); }
    .ic { width: 40px; height: 40px; border-radius: 10px; background: var(--dcm-accent, #0097E0);
      display: flex; align-items: center; justify-content: center; font-size: 20px; flex-shrink: 0; }
    .hm { min-width: 0; }
    .ht { font-weight: 800; text-transform: uppercase; letter-spacing: .6px; color: var(--primary-text-color);
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .hs { font-size: .82em; font-weight: 600; color: var(--secondary-text-color); }
    ha-card { container-type: inline-size; }
    .tabs { display: grid; grid-template-columns: repeat(6, 1fr); gap: 2px 4px; padding: 8px 8px 0;
      border-bottom: 1px solid var(--divider-color); }
    .tabs.n5 { grid-template-columns: repeat(5, 1fr); } .tabs.n4 { grid-template-columns: repeat(4, 1fr); }
    .tabs.n3 { grid-template-columns: repeat(3, 1fr); } .tabs.n2 { grid-template-columns: repeat(2, 1fr); }
    .tabs.n1 { grid-template-columns: 1fr; }
    @container (max-width: 540px) { .tabs, .tabs.n5, .tabs.n4 { grid-template-columns: repeat(3, 1fr); } }
    .tab { min-width: 0; overflow: hidden; text-overflow: ellipsis; border: 0; background: none; padding: 8px 10px; cursor: pointer; font: inherit;
      font-size: .86em; font-weight: 700; color: var(--secondary-text-color); border-bottom: 3px solid transparent;
      border-radius: 8px 8px 0 0; min-height: 40px; }
    .tab.on { color: var(--primary-text-color); border-bottom-color: var(--dcm-accent, #0097E0);
      background: var(--secondary-background-color); }
    .tab:focus-visible, .win:focus-visible, .alert:focus-visible, .bw:focus-visible { outline: 2px solid var(--dcm-accent, #0097E0); }
    .body { padding: 12px 14px 14px; }
    .wins { display: flex; gap: 6px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
    .win { border: 1px solid var(--divider-color); background: none; border-radius: 14px; padding: 4px 12px;
      cursor: pointer; font: inherit; font-size: .82em; font-weight: 700; color: var(--secondary-text-color); min-height: 30px; }
    .win.on { background: var(--dcm-accent, #0097E0); border-color: var(--dcm-accent, #0097E0); color: #fff; }
    .muted { color: var(--secondary-text-color); font-size: .82em; font-weight: 500; }
    .tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); gap: 8px; margin: 8px 0; }
    .tile { background: var(--secondary-background-color); border-radius: 10px; padding: 8px 10px; min-width: 0; }
    .tl { font-size: .7em; font-weight: 700; text-transform: uppercase; letter-spacing: .3px; color: var(--secondary-text-color);
      overflow-wrap: anywhere; hyphens: auto; line-height: 1.25; }
    .tv { font-size: 1.3em; font-weight: 800; color: var(--primary-text-color); font-variant-numeric: tabular-nums; }
    .ts { font-size: .72em; color: var(--secondary-text-color); }
    .sect { font-weight: 800; margin: 12px 0 4px; color: var(--primary-text-color); font-size: .92em; }
    .chart { width: 100%; height: auto; display: block; touch-action: pan-y; }
    .chart .grid { stroke: var(--divider-color); stroke-width: 1; }
    .chart .tick, .chart .xs { font-size: 8px; fill: var(--secondary-text-color); }
    .chart .xl { font-size: 9px; font-weight: 700; fill: var(--primary-text-color); }
    .chart .xl.sel { fill: var(--dcm-accent, #0097E0); }
    .chart .val { font-size: 8.5px; font-weight: 800; fill: var(--primary-text-color); }
    .chart .avgline { stroke: ${C.avg}; stroke-width: 1.5; stroke-dasharray: 4 3; }
    .chart .qline { fill: none; stroke: var(--dcm-accent, #0097E0); stroke-width: 2.5; stroke-linejoin: round; }
    .chart .hit { fill: transparent; cursor: pointer; }
    .chart .hit.on { fill: var(--dcm-accent, #0097E0); fill-opacity: .1; }
    .legend { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: .78em; color: var(--secondary-text-color); margin: 2px 0 6px; }
    .legend i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 4px; vertical-align: -1px; }
    .split { display: flex; height: 14px; border-radius: 7px; overflow: hidden; gap: 2px; }
    .bwrow { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 8px; }
    .bw { border: 2px solid; border-radius: 10px; padding: 8px 10px; cursor: pointer; color: var(--primary-text-color); }
    .sparks { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
    .sparks > div { background: var(--secondary-background-color); border-radius: 10px; padding: 6px 8px; }
    .spark { width: 100%; height: 28px; display: block; }
    .banner { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; padding: 10px 12px; border-radius: 10px;
      background: var(--secondary-background-color); color: var(--primary-text-color); }
    .banner .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--disabled-text-color, #9e9e9e); }
    .banner.on .dot { background: ${C.good}; box-shadow: 0 0 0 0 ${C.good}; animation: pulse 2s infinite; }
    @keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(67,160,71,.6); } 70% { box-shadow: 0 0 0 8px rgba(67,160,71,0); } 100% { box-shadow: 0 0 0 0 rgba(67,160,71,0); } }
    .pill { color: #fff; border-radius: 10px; padding: 2px 8px; font-size: .8em; font-weight: 800; margin-left: auto; }
    .note { padding: 10px 12px; border-radius: 10px; background: var(--secondary-background-color);
      color: var(--primary-text-color); font-size: .88em; margin: 8px 0; }
    .note.warn { border-left: 4px solid ${C.critical}; }
    .note.ok { border-left: 4px solid ${C.good}; }
    .alert { border-left: 4px solid; background: var(--secondary-background-color); border-radius: 8px;
      padding: 8px 10px; margin: 6px 0; cursor: pointer; color: var(--primary-text-color); }
    .ah { display: flex; justify-content: space-between; gap: 8px; font-weight: 700; font-size: .88em; }
    .msg { white-space: pre-wrap; font-family: var(--code-font-family, monospace); font-size: .78em; margin: 6px 0 0;
      color: var(--secondary-text-color); }
    .detail { margin-top: 10px; border: 1px solid var(--divider-color); border-radius: 12px; padding: 8px 10px;
      background: var(--card-background-color); }
    .dh { display: flex; justify-content: space-between; align-items: center; color: var(--primary-text-color); }
    .x { border: 0; background: none; cursor: pointer; font-size: 1em; color: var(--secondary-text-color); min-width: 32px; min-height: 32px; }
    .modes { border-top: 1px dashed var(--divider-color); padding-top: 6px; }
    .mrow { display: grid; grid-template-columns: 1.4fr 1.4fr .5fr; gap: 6px; font-size: .86em; padding: 2px 0; color: var(--primary-text-color); }
    .mrow span:last-child { text-align: right; font-weight: 800; }
    .more { border: 0; background: none; color: var(--dcm-accent, #0097E0); font: inherit; font-weight: 700;
      font-size: .86em; cursor: pointer; padding: 6px 0; min-height: 32px; }
    .hint, .help { font-size: .78em; color: var(--secondary-text-color); margin-top: 8px; }
  `;

  /* ------------------------------------------------------------------ */
  /* the card                                                            */
  /* ------------------------------------------------------------------ */

  class DaikinDailySummaryCard extends HTMLElement {
    static getConfigElement() { return document.createElement(EDITOR_TAG); }

    static getStubConfig() { return { default_tab: "today", window: 7 }; }

    setConfig(config) {
      if (!config || typeof config !== "object") throw new Error("Invalid configuration");
      if (config.default_tab && !TABS.includes(config.default_tab)) {
        throw new Error("default_tab must be one of: " + TABS.join(", "));
      }
      this._config = Object.assign({}, config);
      const win = Number(config.window);
      this._ui = { tab: config.default_tab || "today", win: WINDOWS.includes(win) ? win : 7, day: null, alert: null, allAlerts: false };
      this._sig = null;
      this._draw();
    }

    set hass(hass) {
      this._hass = hass;
      this._draw();
    }

    get hass() { return this._hass; }

    getCardSize() { return 9; }

    getGridOptions() { return { columns: 12, min_columns: 6, rows: "auto" }; }

    connectedCallback() {
      if (!this._timer) this._timer = setInterval(() => { this._sig = null; this._draw(); }, 60000);
    }

    disconnectedCallback() {
      if (this._timer) { clearInterval(this._timer); this._timer = null; }
    }

    _signature() {
      const ids = resolveEntities(this._hass, this._config);
      const parts = Object.values(ids).map((id) => {
        const st = id && this._hass.states[id];
        return st ? id + "@" + (st.last_updated || st.last_changed || st.state) : "-";
      });
      return parts.join("|") + "#" + JSON.stringify(this._ui) + "#" + ((this._hass.locale && this._hass.locale.language) || this._hass.language || "");
    }

    _draw() {
      if (!this._config || !this._hass) return;
      const sig = this._signature();
      if (sig === this._sig) return;
      this._sig = sig;
      if (!this.shadowRoot) {
        this.attachShadow({ mode: "open" });
        this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card><div id="root"></div></ha-card>`;
        this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
        this.shadowRoot.addEventListener("keydown", (ev) => {
          if ((ev.key === "Enter" || ev.key === " ") && ev.target && ev.target.getAttribute && ev.target.getAttribute("role") === "button") {
            ev.preventDefault(); this._onClick(ev);
          }
        });
      }
      const m = buildModel(this._hass, this._config, Date.now());
      const root = this.shadowRoot.getElementById("root");
    root.setAttribute("lang", m.lang);
    root.innerHTML = render(m, this._config, this._ui);
    }

    _onClick(ev) {
      const path = ev.composedPath ? ev.composedPath() : [ev.target];
      for (const el of path) {
        if (!el || !el.getAttribute) continue;
        const act = el.getAttribute("data-act");
        const day = el.getAttribute("data-day");
        if (act === "tab") { this._ui.tab = el.getAttribute("data-tab"); this._ui.day = null; return this._draw(); }
        if (act === "win") { this._ui.win = Number(el.getAttribute("data-win")); this._ui.day = null; return this._draw(); }
        if (act === "close") { this._ui.day = null; return this._draw(); }
        if (act === "more") { this._ui.allAlerts = !this._ui.allAlerts; return this._draw(); }
        if (act === "alert") {
          const i = Number(el.getAttribute("data-i"));
          this._ui.alert = this._ui.alert === i ? null : i; return this._draw();
        }
        if (day) {
          if (el.classList && el.classList.contains("bw")) { this._ui.tab = "quality"; this._ui.day = day; return this._draw(); }
          this._ui.day = this._ui.day === day ? null : day; return this._draw();
        }
      }
    }
  }

  /* ------------------------------------------------------------------ */
  /* visual editor                                                       */
  /* ------------------------------------------------------------------ */

  const EDITOR_LABELS = {
    device_id: "Heat pump (when you have several)", title: "Title",
    default_tab: "Tab shown first", window: "Days shown", tabs: "Tabs",
    language: "Language", show_help: "Show explanations",
  };

  class DaikinDailySummaryCardEditor extends HTMLElement {
    setConfig(config) { this._config = Object.assign({}, config); this._render(); }

    set hass(hass) { this._hass = hass; this._render(); }

    _schema() {
      const opt = (v, l) => ({ value: v, label: l });
      return [
        { name: "device_id", selector: { device: { integration: DOMAIN } } },
        { name: "title", selector: { text: {} } },
        { name: "default_tab", selector: { select: { mode: "dropdown", options: TABS.map((k) => opt(k, I18N.en["tab_" + k])) } } },
        { name: "window", selector: { select: { mode: "dropdown", options: WINDOWS.map((w) => opt(String(w), w + " days")) } } },
        { name: "tabs", selector: { select: { multiple: true, options: TABS.map((k) => opt(k, I18N.en["tab_" + k])) } } },
        { name: "language", selector: { select: { mode: "dropdown", options: [opt("", "Auto (Home Assistant)"), opt("en", "English"), opt("nl", "Nederlands"), opt("fr", "Français")] } } },
        { name: "show_help", selector: { boolean: {} } },
      ];
    }

    _render() {
      if (!this._config || !this._hass) return;
      if (!this._form) {
        this._form = document.createElement("ha-form");
        this._form.computeLabel = (s) => EDITOR_LABELS[s.name] || s.name;
        this._form.addEventListener("value-changed", (ev) => {
          const cfg = Object.assign({}, ev.detail.value);
          if (cfg.window !== undefined && cfg.window !== "") cfg.window = Number(cfg.window);
          for (const k of Object.keys(cfg)) if (cfg[k] === "" || cfg[k] === undefined) delete cfg[k];
          if (Array.isArray(cfg.tabs) && !cfg.tabs.length) delete cfg.tabs;
          this._config = cfg;
          this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: cfg }, bubbles: true, composed: true }));
        });
        this.appendChild(this._form);
      }
      this._form.hass = this._hass;
      this._form.schema = this._schema();
      const data = Object.assign({ show_help: true }, this._config);
      if (data.window !== undefined) data.window = String(data.window);
      this._form.data = data;
    }
  }

  if (!customElements.get(TAG)) customElements.define(TAG, DaikinDailySummaryCard);
  if (!customElements.get(EDITOR_TAG)) customElements.define(EDITOR_TAG, DaikinDailySummaryCardEditor);

  window.customCards = window.customCards || [];
  if (!window.customCards.some((c) => c.type === TAG)) {
    window.customCards.push({
      type: TAG,
      name: "Daikin Cycle ML · Daily summary",
      description: "Today's run and alerts, quality, cycles, runtime and events per day (no extra cards needed).",
      preview: true,
      documentationURL: "https://github.com/elRadix/daikin_cycle_ml/tree/main/dashboard/cards/daikin-daily-summary-card",
    });
  }

  /* pure helpers for tests and other cards */
  window.DaikinDailySummaryCard = {
    version: CARD_VERSION, SUFFIX, TABS, I18N,
    resolveEntities, buildDays, periodStats, buildModel, render, pickLang, alertTitle, alertBody, esc,
  };

  if (!window.__dcmSummaryCardLogged) {
    window.__dcmSummaryCardLogged = true;
    console.info(`%c DAIKIN-DAILY-SUMMARY-CARD %c ${CARD_VERSION} `,
      "color:#fff;background:#0097E0;font-weight:700", "color:#0097E0;background:#fff;font-weight:700");
  }
})();
