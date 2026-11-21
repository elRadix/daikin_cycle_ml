/*
 * Daikin Cycle ML — Efficiency card: HTML of the hero, the tabs and help.
 * Part of custom:daikin-efficiency-card (see daikin-efficiency-card.js).
 * Pure string builders: tested under Node, no DOM.
 */
(function () {
  "use strict";

  const P = (window.DaikinEfficiencyCardParts = window.DaikinEfficiencyCardParts || {});
  const TABS = ["live", "today", "eff", "curve", "advice"];
  const LVL_ICON = { good: "✅", watch: "⚠️", bad: "⛔", info: "ℹ️" };
  const SIGNED = { cop_ok: 1, td_ok: 1, sh_ok: 1, sh_below: 1, sh_low: 1 };

  function makeFmt(lang) {
    const nf = (d) => new Intl.NumberFormat(lang, { minimumFractionDigits: d, maximumFractionDigits: d });
    const f0 = nf(0), f1 = nf(1), f2 = nf(2);
    const hm = new Intl.DateTimeFormat(lang, { hour: "2-digit", minute: "2-digit" });
    const ok = (v) => v !== null && v !== undefined && isFinite(v);
    return {
      n0: (v) => (ok(v) ? f0.format(v) : "—"), n1: (v) => (ok(v) ? f1.format(v) : "—"), n2: (v) => (ok(v) ? f2.format(v) : "—"),
      time: (ms) => hm.format(new Date(ms)),
      dur: (s) => { if (!ok(s)) return "—"; const m = Math.round(s / 60); return m < 60 ? m + " min" : Math.floor(m / 60) + " h " + String(m % 60).padStart(2, "0"); },
      fill(tpl, p, signed) {
        return String(tpl || "").replace(/\{(\w+)\}/g, (_, k) => {
          const v = p ? p[k] : undefined;
          if (v === null || v === undefined) return "—";
          if (typeof v !== "number") return String(v);
          /* 1 decimal unless the value has two (datasheet COPs such as 4.92) */
          const s = Number.isInteger(v) ? f0.format(v) : Math.abs(Math.round(v * 10) / 10 - v) < 1e-9 ? f1.format(v) : f2.format(v);
          return signed && k === "pct" && v > 0 ? "+" + s : s;
        });
      },
    };
  }

  function verdict(a, key, V, t, f) {
    const x = a[key];
    if (!x) return "";
    return `<div class="vd ${x.lvl}" data-vd="${key}" data-k="${x.k}"><span class="vi" role="img" aria-label="${P.data.esc(t["lvl_" + x.lvl])}" title="${P.data.esc(t["lvl_" + x.lvl])}">${LVL_ICON[x.lvl]}</span>`
      + `<span>${P.data.esc(f.fill(V[x.k] || V.none, x.p, SIGNED[x.k]))}</span></div>`;
  }

  const tile = (label, value, sub, color) => `<div class="tile"><div class="tl">${P.data.esc(label)}</div>`
    + `<div class="tv"${color ? ` style="color:${color}"` : ""}>${P.data.esc(value)}</div>${sub ? `<div class="ts">${P.data.esc(sub)}</div>` : ""}</div>`;

  const legend = (items) => `<div class="legend">${items.map((i) => `<span><i style="background:${i.c}${i.dash ? ";height:2px" : ""}"></i>${P.data.esc(i.l)}</span>`).join("")}</div>`;

  const sect = (title, extra) => `<div class="sect">${P.data.esc(title)}${extra ? ` <span class="muted">${P.data.esc(extra)}</span>` : ""}</div>`;

  function hero(m, a, t, f) {
    const L = m.live, C = P.charts.C, esc = P.data.esc;
    const mode = L.defrost ? t.defrost : L.buh ? t.buh : L.mode ? t[L.mode] : null;
    const cop = L.cop10 !== null ? L.cop10 : L.cop;
    return `<div class="hero"><div class="hl"><div class="st ${L.running ? "on" : ""}"><span class="dot"></span>`
      + `${esc(L.running ? t.running + (mode ? " · " + mode : "") : t.idle)}</div>`
      + `<div class="big">${esc(L.running ? f.n1(cop) : "—")}</div><div class="muted">${esc(t.cop10)}</div></div>`
      + `<div class="hr"><div class="pw"><b>${esc(f.n0(L.power10 !== null ? L.power10 : L.power))} W</b> <span class="muted">${esc(t.elec)}</span></div>`
      + `<div class="pw">→ <b style="color:${C.lwt}">${esc(f.n2(L.kw10 !== null ? L.kw10 : L.kw))} kW</b> <span class="muted">${esc(t.heat_out)}</span></div>`
      + `<div class="chip ${a.overall.lvl}">${LVL_ICON[a.overall.lvl]} ${esc(t["lvl_" + a.overall.lvl])}</div></div>`
      + `<div class="note-s">${esc(t.heat_note)}</div></div>`;
  }

  function renderLive(m, a, V, t, f, ui, cfg) {
    const L = m.live, C = P.charts.C, esc = P.data.esc, LIM = P.assess.LIMITS;
    const gap = L.lwt10 !== null && L.target !== null ? L.lwt10 - L.target : null;
    let s = `<div class="tracker"><div class="sect">${esc(t.tracker)}</div><div class="cells">`
      + tile(t.target, f.n1(L.target) + " °") + tile(t.mean10, f.n1(L.lwt10 !== null ? L.lwt10 : L.lwt) + " °")
      + tile(t.gap, gap === null ? "—" : (gap > 0 ? "+" : "") + f.n1(gap) + " K", null, gap === null ? null : Math.abs(gap) <= LIM.track_ok_k ? C.good : Math.abs(gap) <= LIM.track_bad_k ? C.watch : C.bad)
      + tile(t.speed, f.n0(L.rps) + " rps") + `</div>` + verdict(a, "tracker", V, t, f) + `</div>`;
    s += `<div class="wins">` + Object.keys(P.data.RANGES).map((r) => `<button class="win${r === ui.range ? " on" : ""}" data-act="range" data-range="${r}">${esc(r)}</button>`).join("") + `</div>`;
    if (ui.historyFailed) s += `<div class="note">ℹ️ ${esc(t.history_off)}</div>`;
    const w = m.win, bands = [{ role: "defrost_active", color: C.defrost }, { role: "dhw_active", color: C.dhw }, { role: "buh_active", color: C.buh }];
    const tm = (ms) => f.time(ms);
    s += sect(t.ch_water) + P.charts.lineChart(w, {
      title: t.ch_water, bands, empty: t.no_history, yL: { pad: 6, step: 2, unit: "°C" },
      refBands: [{ get: (p) => p.sp, k: LIM.track_ok_k, color: C.target }],
      series: [{ get: (p) => p.sp, color: C.target, dash: "5 3", width: 1.5 }, { get: (p) => p.ret, color: C.ret }, { get: (p) => p.lwt, color: C.lwt }],
    }, tm) + legend([{ c: C.lwt, l: t.lwt }, { c: C.ret, l: t.ret }, { c: C.target, l: t.setpoint + " ±1 K" }, { c: C.defrost, l: t.defrost }, { c: C.dhw, l: t.dhw }, { c: C.buh, l: t.buh }])
      + verdict(a, "water", V, t, f);
    s += sect(t.ch_compressor) + P.charts.lineChart(w, {
      title: t.ch_compressor, bands, markers: "compressor_running", empty: t.no_history,
      yL: { fixed: { lo: 0, hi: Math.max(60, ...w.samples.map((p) => p.rps || 0)) }, unit: t.rps }, yR: { pad: 500, step: 500, unit: "W" },
      series: [{ get: (p) => p.power, color: C.power, axis: "r", width: 1.5 }, { get: (p) => p.rps, color: C.rps }],
    }, tm) + legend([{ c: C.rps, l: t.rps }, { c: C.power, l: t.power }, { c: C.good, l: "▲ " + t.start }, { c: C.bad, l: "▲ " + t.stop }])
      + verdict(a, "compressor", V, t, f);
    const DT = P.assess.dtLimits(m.specs);
    s += sect(t.ch_hydraulics) + P.charts.lineChart(w, {
      title: t.ch_hydraulics, bands, empty: t.no_history, yL: { fixed: { lo: 0, hi: Math.max(25, ...w.samples.map((p) => p.flow || 0)) }, unit: "l/min" }, yR: { fixed: { lo: 0, hi: Math.max(12, Math.ceil((DT.high + 2) / 4) * 4) }, unit: "ΔT K" },
      refs: [{ y: m.specs.minFlow, color: C.bad, label: t.min_flow }, { y: DT.design, axis: "r", color: C.dt, label: t.design_dt.replace("{dt}", (DT.design % 1 === 0 ? f.n0(DT.design) : f.n1(DT.design))) }],
      series: [{ get: (p) => p.dt, color: C.dt, axis: "r", width: 1.5 }, { get: (p) => p.flow, color: C.flow }],
    }, tm) + legend([{ c: C.flow, l: t.flow + " (←)" }, { c: C.dt, l: t.dt + " (→)" }, { c: C.dt, l: "- - " + t.design_dt.replace("{dt}", (DT.design % 1 === 0 ? f.n0(DT.design) : f.n1(DT.design))) }].concat(m.specs.minFlow !== null ? [{ c: C.bad, l: "- - " + t.min_flow }] : []))
      + verdict(a, "hydraulics", V, t, f);
    s += sect(t.ch_comfort) + P.charts.lineChart(m.day, {
      title: t.ch_comfort, empty: t.no_history, yL: { pad: 4, step: 2, unit: "°C" }, yR: { pad: 6, step: 2, unit: "°C" },
      series: [{ get: (p) => p.out, color: C.out, axis: "r", width: 1.5 }, { get: (p) => p.roomSp, color: C.roomSp, dash: "5 3", width: 1.5 }, { get: (p) => p.room, color: C.room }],
    }, tm) + legend([{ c: C.room, l: t.room }, { c: C.roomSp, l: t.room_sp }, { c: C.out, l: t.outdoor + " (→)" }])
      + verdict(a, "comfort", V, t, f) + verdict(a, "cop", V, t, f);
    s += `<button class="more" data-act="adv">${esc(ui.adv ? t.adv_hide : t.adv_show)}</button>`;
    if (ui.adv) {
      s += sect(t.ch_liquid) + P.charts.lineChart(w, {
        title: t.ch_liquid, bands, empty: t.no_history, yL: { fixed: { lo: -2, hi: 10 } },
        refs: [{ y: LIM.liquid_watch_k, color: C.watch, label: LIM.liquid_watch_k + " K" }],
        series: [{ get: (p) => (p.liquid !== null && p.lwt !== null && p.kw > 0 ? p.liquid - p.lwt : null), color: C.liquid }],
      }, tm) + verdict(a, "liquid", V, t, f);
    }
    return s;
  }

  function renderToday(m, a, V, t, f) {
    const T = m.today, C = P.charts.C;
    let s = `<div class="tiles">` + tile(t.cop_today, f.n2(T.cop)) + tile(t.el_today, f.n1(T.el) + " kWh")
      + tile(t.th_today, f.n1(T.th) + " kWh") + tile(t.runtime, f.dur(T.runtime_s)) + tile(t.starts, f.n0(T.starts))
      + tile(t.cycles, f.n0(T.cycles), T.avgRun !== null ? t.avg_run + " " + f.n0(T.avgRun) + " min" : "")
      + tile(t.defrosts, f.n0(T.defrosts), T.defrost_s ? f.dur(T.defrost_s) : "", T.defrosts ? C.defrost : null)
      + tile(t.buh_min, f.dur(T.buh_s), "", T.buh_s ? C.buh : null) + tile(t.duty, f.n0(T.duty) + " %") + `</div>`;
    s += verdict(a, "todayCop", V, t, f);
    const rows = T.modes.filter((x) => (x.el || 0) > 0 || (x.th || 0) > 0);
    if (rows.length) {
      s += sect(t.by_mode) + `<div class="mt">` + rows.map((x) => `<div class="mr"><span>${P.data.esc(t[x.k])}</span><span>${P.data.esc(f.n1(x.el))} kWh ${P.data.esc(t.elec)}</span>`
        + `<span>${P.data.esc(f.n1(x.th))} kWh ${P.data.esc(t.heat_out)}</span><b>COP ${P.data.esc(f.n2(x.el > 0 ? x.th / x.el : null))}</b></div>`).join("") + `</div>`;
    }
    s += sect(t.cop_hourly) + P.charts.copBars(m.curve.recentAll, m.now, t, (ms) => f.time(ms))
      + legend([{ c: C.lwt, l: t.heating }, { c: C.dhw, l: t.dhw }]);
    return s + verdict(a, "cycles", V, t, f) + verdict(a, "events", V, t, f);
  }

  function renderEff(m, a, V, t, f) {
    const E = m.eff, S = m.specs, C = P.charts.C, max = Math.max(7, (S.nomCop || 0) + 1, E.week || 0);
    const row = (lab, val) => `<div class="gr"><span>${P.data.esc(lab)}</span>${P.charts.gauge(val, max, C.cop, S.nomCop)}<b>${P.data.esc(f.n2(val))}</b></div>`;
    let s = sect("COP", t.p10p90 + " " + f.n2(E.p10) + "–" + f.n2(E.p90) + " (" + t.week.toLowerCase() + ")")
      + `<div class="gauges">${row(t.day, E.day)}${row(t.week, E.week)}${row(t.month, E.month)}</div>`;
    const bm = E.byMode || {};
    const modes = ["heating", "dhw", "cooling"].filter((k) => bm[k] && P.data.num(bm[k].cop_mean) !== null);
    if (modes.length) s += `<div class="tiles">` + modes.map((k) => tile(t[k] + " · " + t.week, f.n2(P.data.num(bm[k].cop_mean)), f.n0(P.data.num(bm[k].n_hours)) + " h")).join("") + `</div>`;
    s += sect(t.vs_sheet) + `<div class="tiles">` + tile(t.norm, f.n2(E.norm), t.nominal + " " + f.n2(S.nomCop))
      + tile(t.vs_sheet, E.vsSheet === null ? "—" : (E.vsSheet > 0 ? "+" : "") + f.n1(E.vsSheet) + " %") + `</div>` + verdict(a, "sheet", V, t, f);
    s += sect(t.spf) + `<div class="gauges">` + `<div class="gr"><span>${P.data.esc(t.spf)}</span>${P.charts.gauge(E.spf, max, C.cop, S.scop35)}<b>${P.data.esc(f.n2(E.spf))}</b></div>`
      + `<div class="gr"><span>${P.data.esc(t.scop35)}</span>${P.charts.gauge(S.scop35, max, "var(--secondary-text-color)")}<b>${P.data.esc(f.n2(S.scop35))}</b></div>`
      + `<div class="gr"><span>${P.data.esc(t.scop55)}</span>${P.charts.gauge(S.scop55, max, "var(--secondary-text-color)")}<b>${P.data.esc(f.n2(S.scop55))}</b></div></div>`
      + `<div class="tiles">` + tile(t.spf_ytd, f.n2(E.spfYtd)) + tile(t.scop365, f.n2(E.scop365)) + `</div>` + verdict(a, "spf", V, t, f);
    s += sect(t.degradation) + `<div class="tiles">` + tile(t.week, E.degrWeek === null ? "—" : f.n1(E.degrWeek) + " %")
      + tile(t.trend30, E.trend === null ? "—" : f.n1(E.trend) + " %") + `</div>` + verdict(a, "trend", V, t, f);
    return s;
  }

  function renderCurve(m, a, V, t, f, ui) {
    const S = m.specs, Cv = m.curve, C = P.charts.C, esc = P.data.esc, L = m.live;
    let s = sect(t.curve_title) + P.charts.curveChart(m, ui.bucket, t, f)
      + legend([{ c: C.cop, l: t.measured }, { c: C.buh, l: t.fitted }, { c: C.out, l: t.now }, { c: "var(--secondary-text-color)", l: t.recent_pts }, { c: C.defrost, l: t.defrost_zone }]);
    const b = Cv.pts.find((p) => p.key === ui.bucket);
    if (b) s += `<div class="detail"><b>${esc(t.bucket_detail)} ${esc(b.key)} °</b> · ${esc(f.n1(b.y))} ° · COP ${esc(f.n2(b.cop))} · ${esc(b.n)} ${esc(t.samples)}</div>`;
    s += verdict(a, "curveFit", V, t, f) + verdict(a, "curveLive", V, t, f);
    s += sect(t.strip24) + P.charts.strip24(m.day, t, (ms) => f.time(ms));
    const cop = L.cop10 !== null ? L.cop10 : L.cop, car = P.data.carnot(L.lwt, L.out);
    const eta = cop !== null && car ? cop / car : null;
    const demand = L.flow !== null && L.dt !== null ? (L.flow / 60) * 4.186 * L.dt : null;
    const supply = L.power !== null && L.cop !== null ? (L.power * L.cop) / 1000 : null;
    const T = m.today, share = T.runtime_s > 0 && T.defrost_s !== null ? (T.defrost_s / T.runtime_s) * 100 : null;
    s += `<div class="panels"><div class="panel"><div class="tl">${esc(t.carnot)}</div><div class="tv">${esc(eta === null ? "—" : f.n0(eta * 100) + " %")}</div>`
      + P.charts.gauge(eta === null ? null : eta * 100, 100, "#8E2463") + `<div class="ts">max COP ${esc(f.n1(car))}</div></div>`
      + `<div class="panel"><div class="tl">${esc(t.balance)}</div><div class="tv">${esc(demand !== null && supply !== null ? (demand - supply >= 0 ? "+" : "") + f.n2(demand - supply) + " kW" : "—")}</div>`
      + `<div class="ts">${esc(t.demand)} ${esc(f.n2(demand))} · ${esc(t.supply)} ${esc(f.n2(supply))} kW</div></div>`
      + `<div class="panel"><div class="tl">${esc(t.defrost_impact)}</div><div class="tv">${esc(f.n0(T.defrosts))} ×</div>`
      + `<div class="ts">${esc(f.dur(T.defrost_s))}${share !== null ? " · " + esc(f.n0(share)) + " %" : ""}</div></div></div>`;
    s += verdict(a, "carnot", V, t, f) + verdict(a, "balance", V, t, f) + verdict(a, "events", V, t, f);
    const fit = Cv.fit, n = Cv.pts.reduce((x, p) => x + (p.n || 0), 0);
    const rng = (lo, hi) => (lo === null || hi === null ? "—" : f.n0(lo) + " … " + f.n0(hi) + " °C");
    s += `<div class="specs"><div class="tl">${esc(t.specs_box)} · ${esc(m.model)}</div><div class="sg">`
      + `<span>${esc(t.spec_lwt)}</span><b>${esc(rng(S.lwtMin, S.lwtMax))}</b><span>${esc(t.spec_out)}</span><b>${esc(rng(S.outMin, S.outMax))}</b>`
      + `<span>${esc(t.spec_cop)}</span><b>${esc(f.n2(S.nomCop))}</b><span>${esc(t.spec_defrost)}</span><b>${esc(f.n0(S.defrostBelow))} °C</b>`
      + `<span>${esc(t.spec_buh)}</span><b>${esc(f.n0(S.buhAbove))} °C</b><span>${esc(t.spec_off)}</span><b>${esc(f.n0(S.offAbove))} °C</b>`
      + `<span>${esc(t.formula)}</span><b>${esc(fit ? "LWT = " + f.n1(fit.a) + (fit.b < 0 ? " − " : " + ") + f.n2(Math.abs(fit.b)) + " × T_out" : "—")}</b>`
      + `<span>${esc(t.samples)}</span><b>${esc(f.n0(n))} · ${esc(Cv.pts.length)} ${esc(t.bands)}</b></div></div>`;
    s += `<div class="tiles">` + tile(t.tile_now, f.n1(L.lwt) + " °") + tile(t.tile_best, f.n1(m.advice.optimal) + " °")
      + tile(t.tile_save, f.n1(m.advice.saving) + " %") + tile(t.tile_trend, m.eff.trend === null ? "—" : f.n1(m.eff.trend) + " %") + `</div>`;
    return s;
  }

  function renderAdvice(m, a, V, t, f) {
    const A = m.advice, x = a.advice, esc = P.data.esc, L = m.live;
    let s = `<div class="adv ${x.lvl}"><div class="tl">${esc(t.advice_title)}</div><div class="at">${esc(f.fill(V[x.k], x.p))}</div>`
      + `<div class="cells">` + tile(t.setpoint_now, f.n1(A.setpoint) + " °") + tile(t.setpoint_new, f.n1(A.target !== null ? A.target : A.setpoint) + " °")
      + tile(t.saving, f.n1(A.saving) + " %") + tile(t.confidence, f.n0(A.confidence === null ? null : A.confidence * 100) + " %") + `</div>`
      + P.charts.gauge(A.confidence === null ? null : A.confidence * 100, 100, P.charts.C.info) + `</div>`;
    s += sect(t.comfort_guard, L.room !== null ? f.n1(L.room) + " °" + (L.roomSp !== null ? " / " + f.n1(L.roomSp) + " °" : "") : "")
      + verdict(a, "comfort", V, t, f) + sect(t.tracker) + verdict(a, "tracker", V, t, f);
    return s + `<div class="note">🔁 ${esc(t.when_change)}</div><div class="note">🛠️ ${esc(t.how_change)}</div>`;
  }

  function helpVals(m) {
    const S = m.specs, LIM = P.assess.LIMITS, DT = P.assess.dtLimits(S);
    return {
      trk: LIM.track_ok_k, trkBad: LIM.track_bad_k, model: m.model || "heat pump", lwtMin: S.lwtMin, lwtMax: S.lwtMax,
      buh: S.buhAbove, starts: LIM.starts_watch_h, dtDesign: DT.design, dtLow: DT.low, dtHigh: DT.high,
      room: LIM.room_ok_k, copOk: Math.round(LIM.cop_ok_ratio * 100), defrost: S.defrostBelow, defWatch: LIM.defrost_watch_pct,
      nom: S.nomCop, scop35: S.scop35, scop55: S.scop55, off: S.offAbove, caOk: Math.round(LIM.carnot_ok * 100), caHigh: 70,
    };
  }

  function renderHelp(m, a, V, t, f, tab, open) {
    const esc = P.data.esc, keys = a.tabs[tab] || [];
    const now = keys.map((k) => a[k]).filter(Boolean).map((x) => `<li class="${x.lvl}">${LVL_ICON[x.lvl]} ${esc(f.fill(V[x.k] || V.none, x.p, SIGNED[x.k]))}</li>`).join("");
    return `<div class="help"><button class="hh" data-act="help" aria-expanded="${open}">💡 ${esc(t.help_title)} <span>${open ? "▾" : "▸"}</span></button>`
      + (open ? `<div class="hb"><div class="tl">${esc(t.help_now)}</div><ul>${now}</ul>`
        + (t["h_" + tab] || []).map((p) => `<p>${esc(f.fill(p, helpVals(m)))}</p>`).join("") + `</div>` : "") + `</div>`;
  }

  function render(m, a, config, ui) {
    const lang = P.i18n[m.lang] ? m.lang : "en";
    const t = P.i18n[lang], V = P.verdicts[lang], f = makeFmt(lang), esc = P.data.esc;
    const tabs = (Array.isArray(config.tabs) && config.tabs.length ? config.tabs : TABS).filter((x) => TABS.includes(x));
    const tab = tabs.includes(ui.tab) ? ui.tab : tabs[0];
    const head = `<div class="head"><div class="ic">📈</div><div class="hm"><div class="ht">${esc(config.title || t.title)}${m.model ? " · " + esc(m.model) : ""}</div>`
      + `<div class="hs">${esc(t.subtitle)}${m.meta ? " · " + esc(m.meta) : ""}</div></div></div>`;
    if (!m.ok) return head + `<div class="body"><div class="note warn">⚠️ ${esc(t.not_found)}</div></div>`;
    let s = head + hero(m, a, t, f) + `<div class="tabs n${tabs.length}" role="tablist">`
      + tabs.map((k) => `<button role="tab" class="tab${k === tab ? " on" : ""}" aria-selected="${k === tab}" data-act="tab" data-tab="${k}">${esc(t["tab_" + k])}</button>`).join("")
      + `</div><div class="body">`;
    if (tab === "live") s += renderLive(m, a, V, t, f, ui, config);
    else if (tab === "today") s += renderToday(m, a, V, t, f);
    else if (tab === "eff") s += renderEff(m, a, V, t, f);
    else if (tab === "curve") s += renderCurve(m, a, V, t, f, ui);
    else if (tab === "advice") s += renderAdvice(m, a, V, t, f);
    if (config.show_help !== false) s += renderHelp(m, a, V, t, f, tab, ui.help !== false);
    return s + `</div>`;
  }

  Object.assign(P, { render: { TABS, makeFmt, render, renderHelp, helpVals } });
  if (window.__dcmEffBoot) window.__dcmEffBoot();
})();
