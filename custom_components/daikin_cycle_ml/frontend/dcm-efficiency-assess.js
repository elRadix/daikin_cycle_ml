/*
 * Daikin Cycle ML — Efficiency card: assessment of the current state.
 * Part of custom:daikin-efficiency-card (see daikin-efficiency-card.js).
 *
 * Every graph and tab gets a verdict {lvl, k, p}: lvl = good | watch |
 * bad | info, k = text key (I18N.v[k]), p = values for the text. The
 * limits come from the datasheet of the configured model (hp_specs) and
 * the rules below (LIMITS, also shown in the help section).
 */
(function () {
  "use strict";

  const P = (window.DaikinEfficiencyCardParts = window.DaikinEfficiencyCardParts || {});

  const LIMITS = {
    track_ok_k: 1.0,        /* 10-min mean within ±1 K of the target */
    track_bad_k: 2.0,       /* more than 2 K off = not following the curve */
    settle_min: 10,         /* first 10 min of a run: still heating up */
    dt_low_k: 3.0,          /* defaults for a 5 K target; see dtLimits() */
    dt_high_k: 8.0,
    dt_design_k: 5.0,       /* Daikin default design ΔT for space heating */
    starts_watch_h: 3,      /* starts in the last hour */
    starts_bad_h: 4,
    room_ok_k: 0.5,
    room_bad_k: 1.0,
    cop_ok_ratio: 0.9,      /* measured COP >= 90 % of the datasheet */
    cop_bad_ratio: 0.75,
    cop_suspect_ratio: 1.4, /* far above the datasheet: check the meter */
    liquid_watch_k: 6.0,    /* R3T (liquid) − LWT */
    carnot_low: 0.30,
    carnot_ok: 0.40,
    carnot_high: 0.80,
    balance_ok_pct: 15,
    balance_bad_pct: 30,
    defrost_watch_pct: 10,  /* share of compressor time */
    defrost_bad_pct: 20,
    spf_ok_ratio: 0.9,      /* season SPF vs SCOP W35 of the datasheet */
    curve_dev_k: 1.5,       /* live LWT vs fitted curve */
    curve_spread_k: 4,      /* outdoor spread needed to judge the slope */
    curve_flat_kk: 0.1,     /* |slope| below 0.1 K per K = flat (fixed water temperature) */
    design_out_c: -10,      /* outdoor used to check the curve end */
    avg_run_watch_min: 30,
  };

  const v = (lvl, k, p) => ({ lvl, k, p: p || {} });
  const r1 = (x) => (x === null || x === undefined ? null : Math.round(x * 10) / 10);
  const RANK = { bad: 3, watch: 2, good: 1, info: 0 };
  const worst = (list) => list.filter(Boolean).reduce((a, b) => (RANK[b.lvl] > RANK[a.lvl] ? b : a), v("info", "none"));

  function heatingSteady(L, now) {
    return L.running && L.mode === "heating" && !L.defrost
      && !(L.started && now - L.started < LIMITS.settle_min * 60);
  }

  function tracker(m) {
    const L = m.live, S = m.specs;
    if (!L.running) {
      if (L.out !== null && S.offAbove !== null && L.out >= S.offAbove) return v("info", "trk_off_warm", { out: r1(L.out), off: S.offAbove });
      return v("info", "trk_off");
    }
    if (L.defrost) return v("info", "trk_defrost");
    if (L.mode === "dhw") return v("info", "trk_dhw");
    if (L.mode === "cooling") return v("info", "trk_cooling");
    if (L.started && m.now - L.started < LIMITS.settle_min * 60) {
      return v("info", "trk_settling", { min: Math.round((m.now - L.started) / 60) });
    }
    const lwt = L.lwt10 !== null ? L.lwt10 : L.lwt;
    if (L.target === null || lwt === null) return v("info", "trk_no_target");
    const gap = lwt - L.target, a = Math.abs(gap);
    const p = { gap: r1(gap), abs: r1(a), lwt: r1(lwt), target: r1(L.target), rps: L.rps };
    if (L.buh) return v("watch", "trk_buh", p);
    if (a <= LIMITS.track_ok_k) return v("good", "trk_on", p);
    if (a <= LIMITS.track_bad_k) return v("watch", gap > 0 ? "trk_above" : "trk_below", p);
    return v("bad", gap > 0 ? "trk_far_above" : "trk_far_below", p);
  }

  /* #466: the installer sets the target ΔT (card option target_dt, default
     5 K). Low = 60 % of it (much water for little heat), high = 3 K above. */
  function dtLimits(S) {
    const design = S && S.dtTarget ? S.dtTarget : LIMITS.dt_design_k;
    return { design, low: Math.round(design * 6) / 10, high: design + 3 };
  }

  function water(m) {
    const L = m.live, S = m.specs;
    if (L.lwt === null) return v("info", "w_no_data");
    const DT = dtLimits(S);
    const p = { lwt: r1(L.lwt), ret: r1(L.ret), dt: r1(L.dt), max: S.lwtMax, min: S.lwtMin, buh: S.buhAbove,
      target: DT.design, low: DT.low, high: DT.high };
    if (S.lwtMax !== null && L.lwt > S.lwtMax) return v("bad", "w_over_max", p);
    if (!L.running) return v("info", "w_idle", p);
    if (L.defrost) return v("info", "w_defrost", p);
    if (L.mode === "dhw") return v("info", "w_dhw", p);
    if (S.buhAbove !== null && L.lwt > S.buhAbove) return v("watch", "w_buh_zone", p);
    if (L.dt === null) return v("info", "w_no_dt", p);
    if (L.dt < DT.low) return v("watch", "w_dt_low", p);
    if (L.dt > DT.high) return v("watch", "w_dt_high", p);
    return v("good", "w_ok", p);
  }

  function compressor(m) {
    const L = m.live, T = m.today;
    const n = T.startsHour;
    const p = { n: n === null ? 0 : n, rps: L.rps, avg: T.avgRun === null ? null : Math.round(T.avgRun), power: L.power === null ? null : Math.round(L.power) };
    if (T.shortPattern || T.highRate || (n !== null && n >= LIMITS.starts_bad_h)) return v("bad", "c_short", p);
    if (n !== null && n >= LIMITS.starts_watch_h) return v("watch", "c_starts", p);
    if (!L.running) return v("info", "c_off", p);
    if (L.defrost) return v("info", "c_defrost", p);
    return v("good", "c_ok", p);
  }

  function hydraulics(m) {
    const L = m.live, S = m.specs;
    const DT = dtLimits(S);
    const design = L.kw !== null && L.kw > 0 ? (L.kw / (4.186 * DT.design)) * 60 : null;
    const p = { flow: r1(L.flow), min: S.minFlow, design: r1(design), dt: r1(L.dt), target: DT.design };
    if (!L.running) return v("info", "h_idle", p);
    if (L.flow === null) return v("info", "h_no_sensor", p);
    if (L.flow <= 0) return v("bad", "h_no_flow", p);
    if (S.minFlow !== null && L.flow < S.minFlow) return v("bad", "h_below_min", p);
    if (L.mode === "heating" && L.dt !== null && L.dt > DT.high) return v("watch", "h_low", p);
    if (L.mode === "heating" && L.dt !== null && L.dt < DT.low) return v("watch", "h_high", p);
    return v("good", "h_ok", p);
  }

  function comfort(m) {
    const L = m.live;
    if (L.room === null) return v("info", "r_none", { out: r1(L.out) });
    if (L.roomSp === null) return v("info", "r_no_sp", { room: r1(L.room), out: r1(L.out) });
    const d = L.room - L.roomSp;
    const p = { room: r1(L.room), sp: r1(L.roomSp), d: r1(d), abs: r1(Math.abs(d)), out: r1(L.out) };
    if (d <= -LIMITS.room_bad_k) return v("bad", "r_cold", p);
    if (d < -LIMITS.room_ok_k) return v("watch", "r_cool", p);
    if (d > LIMITS.room_bad_k) return v("watch", "r_warm", p);
    return v("good", "r_ok", p);
  }

  function copLive(m) {
    const L = m.live, S = m.specs;
    if (!L.running || L.mode !== "heating") return v("info", "cop_idle");
    if (L.defrost) return v("info", "cop_defrost");
    const cop = L.cop10 !== null ? L.cop10 : L.cop;
    if (cop === null) return v("info", "cop_none");
    const exp = P.data.datasheetCop(S.points, L.out, L.lwt);
    const p = { cop: r1(cop), exp: r1(exp), out: r1(L.out), lwt: r1(L.lwt) };
    if (exp === null) return v("info", "cop_no_sheet", p);
    const ratio = cop / exp;
    p.pct = Math.round((ratio - 1) * 100);
    if (ratio > LIMITS.cop_suspect_ratio) return v("watch", "cop_suspect", p);
    if (ratio >= LIMITS.cop_ok_ratio) return v("good", "cop_ok", p);
    p.pct = Math.abs(p.pct);
    if (ratio >= LIMITS.cop_bad_ratio) return v("watch", "cop_below", p);
    return v("bad", "cop_low", p);
  }

  function liquid(m) {
    const L = m.live;
    if (!heatingSteady(L, m.now) || L.liquid === null || L.lwt === null) return v("info", "liq_none");
    const d = L.liquid - L.lwt;
    const p = { d: r1(d), abs: r1(Math.abs(d)), liq: r1(L.liquid), lwt: r1(L.lwt) };
    /* Tweakers: "−3 K above" read wrong; below the leaving water is normal */
    return d > LIMITS.liquid_watch_k ? v("watch", "liq_high", p) : v("good", d < 0 ? "liq_below" : "liq_ok", p);
  }

  function todayCop(m) {
    const T = m.today, S = m.specs, w = m.day.samples.filter((s) => s.kw > 0);
    if (T.cop === null) return v("info", "td_none");
    const out = P.data.mean(w.map((s) => s.out)), lwt = P.data.mean(w.map((s) => s.lwt));
    const exp = P.data.datasheetCop(S.points, out, lwt);
    const p = { cop: r1(T.cop), exp: r1(exp), out: r1(out), lwt: r1(lwt) };
    if (exp === null) return v("info", "td_no_sheet", p);
    const ratio = T.cop / exp;
    p.pct = Math.round((ratio - 1) * 100);
    if (ratio >= LIMITS.cop_ok_ratio) return v("good", "td_ok", p);
    p.pct = Math.abs(p.pct);
    if (ratio >= LIMITS.cop_bad_ratio) return v("watch", "td_below", p);
    return v("bad", "td_low", p);
  }

  function events(m) {
    const T = m.today, S = m.specs;
    const share = T.runtime_s > 0 && T.defrost_s !== null ? (T.defrost_s / T.runtime_s) * 100 : null;
    const p = { n: T.defrosts || 0, pct: share === null ? null : Math.round(share), buh: T.buh_s === null ? 0 : Math.round(T.buh_s / 60), below: S.defrostBelow };
    /* no data for today at all (sensors unknown, or none found): no verdict */
    if (T.defrosts === null && T.defrost_s === null && T.buh_s === null && T.runtime_s === null) return v("info", "ev_none", p);
    if (share !== null && share > LIMITS.defrost_bad_pct) return v("bad", "ev_defrost_bad", p);
    if (p.buh > 0) return v("watch", "ev_buh", p);
    if (share !== null && share > LIMITS.defrost_watch_pct) return v("watch", "ev_defrost_watch", p);
    return v("good", p.n ? "ev_ok_defrost" : "ev_ok", p);
  }

  function cycles(m) {
    const T = m.today;
    const p = { n: T.cycles || 0, short: T.shortRuns || 0, avg: T.avgRun === null ? null : Math.round(T.avgRun), starts: T.starts || 0 };
    if (T.shortPattern || T.highRate) return v("bad", "cy_short", p);
    if (T.avgRun !== null && T.cycles > 1 && T.avgRun < LIMITS.avg_run_watch_min) return v("watch", "cy_avg_short", p);
    if (!T.cycles) return v("info", "cy_none", p);
    return v("good", "cy_ok", p);
  }

  function sheet(m) {
    const E = m.eff;
    const p = { pct: r1(E.vsSheet), norm: r1(E.norm), nom: m.specs.nomCop };
    if (E.vsSheet === null) return v("info", "sh_none", p);
    if (E.band === "on_spec") return v("good", "sh_ok", p);
    if (E.band === "below_spec") return v("watch", "sh_below", p);
    return v("bad", "sh_low", p);
  }

  function spf(m) {
    const E = m.eff, S = m.specs;
    const p = { spf: r1(E.spf), scop: S.scop35, scop55: S.scop55 };
    if (E.spf === null || S.scop35 === null) return v("info", "spf_none", p);
    if (E.spf >= S.scop35 * LIMITS.spf_ok_ratio) return v("good", "spf_ok", p);
    if (S.scop55 !== null && E.spf >= S.scop55) return v("watch", "spf_mid", p);
    return v("bad", "spf_low", p);
  }

  function trend(m) {
    const E = m.eff;
    const p = { week: r1(E.degrWeek), trend: r1(E.trend) };
    if (E.degr === "critical") return v("bad", "tr_critical", p);
    if (E.degr === "warning") return v("watch", "tr_warning", p);
    if (!E.trendValid) return v("info", "tr_wait", p);
    return v("good", "tr_ok", p);
  }

  function curveFit(m) {
    const C = m.curve, S = m.specs, f = C.fit;
    const p = { n: C.pts.length, a: f ? r1(f.a) : null, b: f ? Math.round(-f.b * 100) / 100 : null, buh: S.buhAbove, max: S.lwtMax, t: LIMITS.design_out_c };
    if (!f || f.spread < LIMITS.curve_spread_k) return v("info", "cv_learning", p);
    if (Math.abs(f.b) < LIMITS.curve_flat_kk) return v("info", "cv_flat", p);
    if (f.b >= 0) return v("watch", "cv_rising", p);
    const end = f.a + f.b * LIMITS.design_out_c;
    p.end = r1(end);
    if (S.lwtMax !== null && end > S.lwtMax) return v("bad", "cv_over_max", p);
    if (S.buhAbove !== null && end > S.buhAbove) return v("watch", "cv_buh", p);
    return v("good", "cv_ok", p);
  }

  function curveLive(m) {
    const L = m.live, f = m.curve.fit;
    if (!f || !heatingSteady(L, m.now) || L.lwt === null || L.out === null) return v("info", "cl_none");
    const exp = f.a + f.b * L.out, d = L.lwt - exp;
    const p = { d: r1(d), abs: r1(Math.abs(d)), exp: r1(exp), lwt: r1(L.lwt), out: r1(L.out) };
    if (Math.abs(d) <= LIMITS.curve_dev_k) return v("good", "cl_ok", p);
    return v("watch", d > 0 ? "cl_above" : "cl_below", p);
  }

  function carnotV(m) {
    const L = m.live;
    const cop = L.cop10 !== null ? L.cop10 : L.cop;
    const c = P.data.carnot(L.lwt, L.out);
    if (!heatingSteady(L, m.now) || cop === null || c === null) return v("info", "ca_none");
    const eta = cop / c;
    const p = { pct: Math.round(eta * 100), max: r1(c), cop: r1(cop) };
    if (eta > LIMITS.carnot_high) return v("watch", "ca_high", p);
    if (eta >= LIMITS.carnot_ok) return v("good", "ca_ok", p);
    if (eta >= LIMITS.carnot_low) return v("watch", "ca_mid", p);
    return v("bad", "ca_low", p);
  }

  function balance(m) {
    const L = m.live;
    if (!heatingSteady(L, m.now) || L.flow === null || L.dt === null || L.power === null || L.cop === null) return v("info", "ba_none");
    const demand = (L.flow / 60) * 4.186 * L.dt, supply = (L.power * L.cop) / 1000;
    const pct = (Math.abs(demand - supply) / Math.max(demand, supply, 0.01)) * 100;
    const p = { demand: r1(demand), supply: r1(supply), pct: Math.round(pct) };
    if (pct <= LIMITS.balance_ok_pct) return v("good", "ba_ok", p);
    if (pct <= LIMITS.balance_bad_pct) return v("watch", "ba_watch", p);
    return v("bad", "ba_bad", p);
  }

  function advice(m) {
    const A = m.advice;
    const p = { step: A.step, saving: r1(A.saving), target: r1(A.target), sp: r1(A.setpoint), opt: r1(A.optimal), n: A.samples || 0, bucket: A.bucket };
    if (A.suppressed === "dhw_active") return v("info", "ad_dhw", p);
    if (A.suppressed === "buh_active") return v("info", "ad_buh", p);
    /* never against the live comfort reading: no warmer curve for a room
       that is warm enough, no cooler curve for a room that is cold */
    const L = m.live, d = L.room !== null && L.roomSp !== null ? L.room - L.roomSp : null;
    Object.assign(p, { room: r1(L.room), rsp: r1(L.roomSp) });
    if (A.state === "lower_lwt" && d !== null && d < -LIMITS.room_ok_k) return v("good", "ad_floor", p);
    if (A.state === "raise_lwt" && d !== null && d >= -LIMITS.room_ok_k) return v("good", "ad_room_ok", p);
    if (A.state === "lower_lwt") return v("watch", "ad_lower", p);
    if (A.state === "raise_lwt") return v("watch", d === null ? "ad_raise" : "ad_raise_room", p);
    if (A.state === "keep") {
      const map = {
        within_deadband: ["good", "ad_keep_ok"], no_indoor_sensor: ["info", "ad_no_room"],
        unit_tracking_behind: ["watch", "ad_tracking"], comfort_floor_reached: ["good", "ad_floor"],
        comfort_ceiling_reached: ["good", "ad_ceiling"], low_confidence: ["info", "ad_low_conf"],
        insufficient_samples: ["info", "ad_few"], room_warm_enough: ["good", "ad_room_ok"],
      };
      const e = map[A.reason] || ["good", "ad_keep_ok"];
      return v(e[0], e[1], p);
    }
    return v("info", "ad_no_data", p);
  }

  /* all verdicts, grouped per tab */
  function assess(m) {
    const a = {
      tracker: tracker(m), water: water(m), compressor: compressor(m), hydraulics: hydraulics(m),
      comfort: comfort(m), cop: copLive(m), liquid: liquid(m),
      todayCop: todayCop(m), events: events(m), cycles: cycles(m),
      sheet: sheet(m), spf: spf(m), trend: trend(m),
      curveFit: curveFit(m), curveLive: curveLive(m), carnot: carnotV(m), balance: balance(m),
      advice: advice(m),
    };
    a.tabs = {
      live: ["tracker", "water", "compressor", "hydraulics", "comfort", "cop"],
      today: ["todayCop", "cycles", "events"],
      eff: ["sheet", "spf", "trend"],
      curve: ["curveFit", "curveLive", "carnot", "balance", "events"],
      advice: ["advice", "comfort", "tracker"],
    };
    /* one list of what needs attention (watch / bad) over every tab, each
       check once, at the first tab that shows it: the header badge, the
       tab dots and the Advice tab's to-do list all read it */
    const seen = new Set();
    a.actions = [];
    for (const tab of ["live", "today", "eff", "curve", "advice"]) {
      for (const key of a.tabs[tab]) {
        const x = a[key];
        if (seen.has(key) || !x || (x.lvl !== "bad" && x.lvl !== "watch")) continue;
        seen.add(key);
        a.actions.push(Object.assign({ key, tab }, x));
      }
    }
    a.actions.sort((x, y) => RANK[y.lvl] - RANK[x.lvl]);
    a.tabLvl = {};
    for (const tab of Object.keys(a.tabs)) a.tabLvl[tab] = worst(a.tabs[tab].map((k) => a[k])).lvl;
    a.overall = a.actions.length ? a.actions[0] : worst(Object.keys(a.tabs).flatMap((t) => a.tabs[t]).map((k) => a[k]));
    return a;
  }

  Object.assign(P, { assess: { LIMITS, RANK, assess, worst, heatingSteady, dtLimits } });
  if (window.__dcmEffBoot) window.__dcmEffBoot();
})();
