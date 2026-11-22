/*
 * Daikin Cycle ML — Efficiency card: SVG charts.
 * Part of custom:daikin-efficiency-card (see daikin-efficiency-card.js).
 * Pure string builders: tested under Node, no DOM.
 */
(function () {
  "use strict";

  const P = (window.DaikinEfficiencyCardParts = window.DaikinEfficiencyCardParts || {});
  /* #466: charts are drawn at the card's own width (setWidth), so text and
     lines keep their size on a wide desktop card instead of being scaled up
     from a 360-unit drawing. 360 under Node and before the first layout. */
  let W = 360;
  function setWidth(px) {
    const w = Math.round(Number(px));
    W = isFinite(w) && w > 0 ? Math.max(300, Math.min(1400, w)) : 360;
    return W;
  }
  const C = {
    lwt: "#E53935", ret: "#FB8C00", target: "#8E24AA", rps: "#1E88E5", power: "#43A047",
    flow: "#0097A7", dt: "#F4511E", room: "#E53935", roomSp: "#8E24AA", out: "#1E88E5",
    liquid: "#6D4C41", cop: "#2E7D32", defrost: "#42A5F5", dhw: "#29B6F6", buh: "#FB8C00",
    good: "#43A047", watch: "#FB8C00", bad: "#E53935", info: "#1E88E5",
  };

  const esc = (s) => P.data.esc(s);
  const fin = (x) => x !== null && x !== undefined && isFinite(x);

  function niceRange(vals, padMin, step) {
    const v = vals.filter(fin);
    if (!v.length) return null;
    let lo = Math.min(...v), hi = Math.max(...v);
    if (hi - lo < padMin) { const c = (lo + hi) / 2; lo = c - padMin / 2; hi = c + padMin / 2; }
    lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
    return { lo, hi };
  }

  function timeTicks(from, to, fmtTime) {
    const span = to - from, step = span <= 2400 ? 600 : span <= 12000 ? 3600 : 6 * 3600;
    const out = [];
    for (let t = Math.ceil(from / step) * step; t <= to; t += step) out.push({ t, label: fmtTime(t * 1000) });
    return out;
  }

  /* line chart over time: series [{get, color, axis, dash, label}] */
  /* colour of a measured heating-curve point by its COP (legend: curveLegend) */
  const PT = { hi: "#2E7D32", mid: "#9CCC65", lo: "#FFB300", none: "var(--secondary-text-color, #8a8a8a)" };
  const RING = "#5C6BC0";      /* last 48 h: hourly heating points (rings) */
  const ptColor = (cop) => (!fin(cop) ? PT.none : cop >= 5 ? PT.hi : cop >= 3.5 ? PT.mid : PT.lo);

  function lineChart(win0, opts, fmtTime) {
    /* #466: a little taller on wide cards; units above the axes; when the
       history starts inside the window, the time axis starts there too */
    const units = !!((opts.yL && opts.yL.unit) || (opts.yR && opts.yR.unit));
    const h = Math.round((opts.height || 150) * Math.min(1.6, Math.max(1, W / 360)));
    const top = units ? 18 : 10, bottom = h - 18, left = 30, right = W - (opts.yR ? 30 : 6);
    const first = win0.samples.length ? win0.samples[0].t : null;
    const win = first !== null && first - win0.from > 0.05 * (win0.to - win0.from) && first < win0.to - 60
      ? Object.assign({}, win0, { from: first }) : win0;
    const x = (t) => left + ((t - win.from) / Math.max(1, win.to - win.from)) * (right - left);
    const ranges = {};
    for (const ax of ["l", "r"]) {
      const cfg = ax === "l" ? opts.yL : opts.yR;
      if (!cfg) continue;
      const vals = [];
      for (const se of opts.series) if ((se.axis || "l") === ax) for (const s of win.samples) vals.push(se.get(s));
      for (const r of opts.refs || []) if ((r.axis || "l") === ax) vals.push(r.y);
      const st = cfg.step || 1, nr = niceRange(vals, cfg.pad || 2, st);
      let r = cfg.fixed || (nr ? { lo: nr.lo - st, hi: nr.hi + st } : { lo: 0, hi: 1 });
      if (!cfg.fixed && nr) {
        /* one step of margin so lines and the ±1 K band never touch the frame,
           never below 0 for positive data, 4 equal whole-step intervals */
        if (Math.min(...vals.filter(fin)) >= 0) r.lo = Math.max(0, r.lo);
        while (Math.round((r.hi - r.lo) / st) % 4) r.hi += st;
      }
      ranges[ax] = r;
    }
    const y = (v, ax) => { const r = ranges[ax || "l"]; return bottom - ((v - r.lo) / Math.max(1e-9, r.hi - r.lo)) * (bottom - top); };
    let s = "";
    /* mode bands */
    for (const b of opts.bands || []) {
      for (const sp of (win.spans[b.role] || [])) {
        const x0 = x(sp.from), x1 = Math.max(x0 + 1.5, x(sp.to));
        s += `<rect x="${x0.toFixed(1)}" y="${top}" width="${(x1 - x0).toFixed(1)}" height="${bottom - top}" fill="${b.color}" opacity="0.16"/>`;
      }
    }
    /* grid + ticks */
    const rl = ranges.l;
    const ticks = 4;
    for (let i = 0; i <= ticks; i++) {
      const v = rl.lo + ((rl.hi - rl.lo) * i) / ticks, yy = y(v, "l");
      s += `<line x1="${left}" x2="${right}" y1="${yy.toFixed(1)}" y2="${yy.toFixed(1)}" class="grid"/>`
        + `<text x="${left - 3}" y="${(yy + 3).toFixed(1)}" class="tick" text-anchor="end">${esc(opts.yL.fmt ? opts.yL.fmt(v) : Math.round(v))}</text>`;
      if (ranges.r) {
        const vr = ranges.r.lo + ((ranges.r.hi - ranges.r.lo) * i) / ticks;
        s += `<text x="${right + 3}" y="${(yy + 3).toFixed(1)}" class="tick" text-anchor="start">${esc(opts.yR.fmt ? opts.yR.fmt(vr) : Math.round(vr))}</text>`;
      }
    }
    if (opts.yL && opts.yL.unit) s += `<text x="${left - 3}" y="9" class="tick unit" text-anchor="end">${esc(opts.yL.unit)}</text>`;
    if (opts.yR && opts.yR.unit) s += `<text x="${right + 3}" y="9" class="tick unit" text-anchor="start">${esc(opts.yR.unit)}</text>`;
    for (const tk of timeTicks(win.from, win.to, fmtTime)) {
      const xx = x(tk.t), anc = xx > right - 18 ? "end" : xx < left + 18 ? "start" : "middle";
      s += `<text x="${xx.toFixed(1)}" y="${h - 5}" class="tick" text-anchor="${anc}">${esc(tk.label)}</text>`;
    }
    /* reference band (±k around a line) and reference lines */
    for (const r of opts.refBands || []) {
      win.samples.forEach((p, i) => {
        const v = r.get(p);
        if (!fin(v)) return;
        const x0 = x(p.t), x1 = x(i + 1 < win.samples.length ? win.samples[i + 1].t : win.to);
        if (x1 <= x0) return;
        s += `<rect x="${x0.toFixed(1)}" y="${y(v + r.k, r.axis).toFixed(1)}" width="${(x1 - x0).toFixed(1)}" height="${(y(v - r.k, r.axis) - y(v + r.k, r.axis)).toFixed(1)}" fill="${r.color}" opacity="0.12"/>`;
      });
    }
    for (const r of opts.refs || []) {
      if (!fin(r.y)) continue;
      const yy = y(r.y, r.axis);
      if (yy < top - 0.5 || yy > bottom + 0.5) continue;
      s += `<line x1="${left}" x2="${right}" y1="${yy.toFixed(1)}" y2="${yy.toFixed(1)}" stroke="${r.color}" stroke-width="1.2" stroke-dasharray="5 3"/>`
        + (r.label ? `<text x="${right - 2}" y="${(yy - 3).toFixed(1)}" class="rl" text-anchor="end" fill="${r.color}">${esc(r.label)}</text>` : "");
    }
    /* series: a value holds until the next sample (step line); the
       line breaks where the value is unknown */
    for (const se of opts.series) {
      let seg = [];
      const flush = () => {
        if (seg.length > 1) s += `<polyline points="${seg.join(" ")}" fill="none" stroke="${se.color}" stroke-width="${se.width || 2}"${se.dash ? ` stroke-dasharray="${se.dash}"` : ""} stroke-linejoin="round"/>`;
        seg = [];
      };
      win.samples.forEach((p, i) => {
        const v = se.get(p);
        if (!fin(v)) { flush(); return; }
        const end = i + 1 < win.samples.length ? win.samples[i + 1].t : win.to;
        const yy = y(v, se.axis).toFixed(1);
        seg.push(`${x(p.t).toFixed(1)},${yy}`, `${x(end).toFixed(1)},${yy}`);
      });
      flush();
    }
    /* start / stop markers */
    for (const sp of (opts.markers && win.spans[opts.markers]) || []) {
      if (sp.from > win.from) s += `<path d="M${x(sp.from).toFixed(1)} ${bottom} l-3.5 6 h7z" fill="${C.good}"><title>start</title></path>`;
      if (sp.to < win.to) s += `<path d="M${x(sp.to).toFixed(1)} ${bottom} l-3.5 6 h7z" fill="${C.bad}"><title>stop</title></path>`;
    }
    if (!win.samples.length) s += `<text x="${(left + right) / 2}" y="${(top + bottom) / 2}" class="empty" text-anchor="middle">${esc(opts.empty || "")}</text>`;
    return `<svg viewBox="0 0 ${W} ${h}" class="chart" role="img" aria-label="${esc(opts.title || "")}">${s}</svg>`;
  }

  /* heating curve: outdoor (x) vs LWT (y) */
  function curveChart(m, sel, t, f, pop) {
    const at = {};      /* centre of every tappable dot, for the pop-up */
    const S = m.specs, Cv = m.curve, L = m.live;
    const h = 260, top = 10, bottom = h - 22, left = 30, right = W - 6;
    const xLo = -15, xHi = 20, yLo = 15, yHi = Math.max(60, (S.lwtMax || 55) + 5);
    const x = (o) => left + ((o - xLo) / (xHi - xLo)) * (right - left);
    const y = (v) => bottom - ((v - yLo) / (yHi - yLo)) * (bottom - top);
    const clampX = (o) => Math.max(xLo, Math.min(xHi, o));
    let s = `<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="${C.defrost}" stroke-width="2" opacity="0.35"/></pattern></defs>`;
    if (S.defrostBelow !== null) {
      s += `<rect x="${left}" y="${top}" width="${(x(clampX(S.defrostBelow)) - left).toFixed(1)}" height="${bottom - top}" fill="url(#hatch)"/>`
        + `<text x="${left + 4}" y="${top + 10}" class="rl" fill="${C.defrost}">${esc(t.defrost_zone)} &lt; ${esc(S.defrostBelow)}°</text>`;
    }
    if (S.offAbove !== null && S.offAbove < xHi) {
      s += `<rect x="${x(S.offAbove).toFixed(1)}" y="${top}" width="${(right - x(S.offAbove)).toFixed(1)}" height="${bottom - top}" fill="var(--secondary-text-color)" opacity="0.08"/>`;
    }
    for (let v = 20; v <= yHi; v += 10) {
      s += `<line x1="${left}" x2="${right}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" class="grid"/><text x="${left - 3}" y="${(y(v) + 3).toFixed(1)}" class="tick" text-anchor="end">${v}°</text>`;
    }
    for (let o = -15; o <= 20; o += 5) s += `<text x="${x(o).toFixed(1)}" y="${bottom + 11}" class="tick" text-anchor="middle">${o}</text>`;
    s += `<text x="${(left + right) / 2}" y="${h - 1}" class="tick" text-anchor="middle">${esc(t.outdoor_axis)}</text>`;
    const lim = [[S.lwtMax, C.bad, t.lim_max], [S.buhAbove, C.buh, t.lim_buh], [S.lwtMin, C.out, t.lim_min]];
    for (const [v, col, lab] of lim) {
      if (!fin(v) || v < yLo || v > yHi) continue;
      s += `<line x1="${left}" x2="${right}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" stroke="${col}" stroke-width="1.2" stroke-dasharray="5 3"/>`
        + `<text x="${right - 2}" y="${(y(v) - 3).toFixed(1)}" class="rl" text-anchor="end" fill="${col}">${esc(lab)} ${esc(v)}°</text>`;
    }
    /* recent hourly points (48 h, heating) */
    /* every dot has a pop-up: a wider invisible ring makes the small grey
       ones easy to tap; the explanation is drawn under the chart */
    Cv.recent.forEach((p, i) => {
      const o = P.data.num(p.outdoor_mean), l = P.data.num(p.lwt_mean);
      if (o === null || l === null) return;
      /* hollow rings (one per hour of heating), newest darkest: never
         mistaken for the filled band averages or a band without COP */
      const cx = x(clampX(o)).toFixed(1), cy = y(l).toFixed(1), on = sel === "r" + i;
      at["r" + i] = [+cx, +cy];
      const age = Cv.recent.length > 1 ? i / (Cv.recent.length - 1) : 1;
      s += `<circle cx="${cx}" cy="${cy}" r="${on ? 5 : 3.5}" fill="none" stroke="${on ? "#AD1457" : RING}" stroke-width="${on ? 2.5 : 1.5}" opacity="${on ? 1 : (0.3 + 0.7 * age).toFixed(2)}"/>`
        + `<circle cx="${cx}" cy="${cy}" r="7" fill="transparent" data-act="bucket" data-key="r${i}" class="pt"><title>${esc(f.n1(o))}° → ${esc(f.n1(l))}°</title></circle>`;
    });
    if (Cv.fit) {
      const a = Cv.fit.a, b = Cv.fit.b;
      s += `<line x1="${x(xLo)}" y1="${y(a + b * xLo).toFixed(1)}" x2="${x(xHi)}" y2="${y(a + b * xHi).toFixed(1)}" stroke="${C.buh}" stroke-width="2" stroke-dasharray="6 4"/>`;
    }
    if (Cv.pts.length > 1) s += `<polyline points="${Cv.pts.map((p) => `${x(clampX(p.x)).toFixed(1)},${y(p.y).toFixed(1)}`).join(" ")}" fill="none" stroke="${C.cop}" stroke-width="1.5" opacity="0.6"/>`;
    Cv.pts.forEach((p) => {
      const on = sel === p.key;
      const col = ptColor(p.cop);
      at[p.key] = [x(clampX(p.x)), y(p.y)];
      s += `<circle cx="${x(clampX(p.x)).toFixed(1)}" cy="${y(p.y).toFixed(1)}" r="${on ? 8 : 6}" fill="${col}" stroke="${on ? "#AD1457" : "var(--card-background-color, #fff)"}" stroke-width="2" data-act="bucket" data-key="${esc(p.key)}" class="pt"><title>${esc(p.key)}°: ${esc(f.n1(p.y))}° · COP ${esc(f.n2(p.cop))} · n ${esc(p.n)}</title></circle>`;
    });
    if (fin(L.out) && fin(L.lwt)) {
      const lx = x(clampX(L.out)), ly = y(L.lwt);
      const flip = lx > right - 110;
      at.now = [lx, ly];
      s += `<circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="${sel === "now" ? 8 : 6}" fill="${C.out}" stroke="${sel === "now" ? "#AD1457" : "#fff"}" stroke-width="2" data-act="bucket" data-key="now" class="pt"/>`
        + (sel === "now" && pop ? "" : `<rect x="${(flip ? lx - 104 : lx + 8).toFixed(1)}" y="${(ly - 34).toFixed(1)}" width="96" height="26" rx="5" class="callout"/>`
        + `<text x="${(flip ? lx - 98 : lx + 14).toFixed(1)}" y="${(ly - 23).toFixed(1)}" class="ct">${esc(t.now)} · ${esc(f.n1(L.out))}° ${esc(t.out_short)}</text>`
        + `<text x="${(flip ? lx - 98 : lx + 14).toFixed(1)}" y="${(ly - 12).toFixed(1)}" class="ct b">${esc(f.n1(L.lwt))}° · ${esc(f.n2(L.kw))} kW</text>`);
    }
    const svg = `<svg viewBox="0 0 ${W} ${h}" class="chart" role="img" aria-label="${esc(t.curve_title)}">${s}</svg>`;
    const p = pop && at[sel];
    if (!p) return svg;
    /* the pop-up sits in the chart next to its dot, on the side with room */
    const lx = (p[0] / W) * 100, ty = (p[1] / h) * 100;
    const pos = (W < 520 ? "left:4%;right:4%" : lx > 50 ? `right:${(100 - lx + 2).toFixed(1)}%` : `left:${(lx + 2).toFixed(1)}%`)
      + (ty > 45 ? `;bottom:${(100 - ty + 4).toFixed(1)}%` : `;top:${(ty + 4).toFixed(1)}%`);
    return `<div class="cwrap">${svg}<div class="pop" style="${pos}" data-act="bucket" data-key="${esc(sel)}" role="tooltip">${esc(pop)}<span class="px">✕</span></div></div>`;
  }

  /* 24 h strip with backup-heater and defrost spans */
  function strip24(win, t, fmtTime) {
    const h = 40, left = 30, right = W - 6;
    const x = (tt) => left + ((tt - win.from) / Math.max(1, win.to - win.from)) * (right - left);
    let s = "";
    const rows = [["buh_active", C.buh, t.buh_short, 6], ["defrost_active", C.defrost, t.def_short, 20]];
    for (const [role, col, lab, yy] of rows) {
      s += `<text x="${left - 3}" y="${yy + 8}" class="tick" text-anchor="end">${esc(lab)}</text><rect x="${left}" y="${yy}" width="${right - left}" height="10" rx="3" class="track"/>`;
      for (const sp of win.spans[role] || []) {
        const x0 = x(sp.from);
        s += `<rect x="${x0.toFixed(1)}" y="${yy}" width="${Math.max(2, x(sp.to) - x0).toFixed(1)}" height="10" rx="2" fill="${col}"/>`;
      }
    }
    for (const tk of timeTicks(win.from, win.to, fmtTime)) s += `<text x="${x(tk.t).toFixed(1)}" y="${h - 1}" class="tick" text-anchor="middle">${esc(tk.label)}</text>`;
    return `<svg viewBox="0 0 ${W} ${h}" class="chart" role="img">${s}</svg>`;
  }

  /* hourly COP bars (cop_curve_recent points, last 24 h) */
  function copBars(points, now, t, fmtTime) {
    const h = 120, top = 8, bottom = h - 16, left = 30, right = W - 6, from = now - 86400;
    const pts = (points || []).filter((p) => P.data.num(p.ts) >= from && P.data.num(p.cop_mean) !== null);
    const max = Math.max(6, ...pts.map((p) => P.data.num(p.cop_mean)));
    const x = (tt) => left + ((tt - from) / 86400) * (right - left);
    const y = (v) => bottom - (v / max) * (bottom - top);
    const bw = ((right - left) / 24) * 0.7;
    let s = "";
    for (let v = 0; v <= max; v += 2) s += `<line x1="${left}" x2="${right}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" class="grid"/><text x="${left - 3}" y="${(y(v) + 3).toFixed(1)}" class="tick" text-anchor="end">${v}</text>`;
    for (const p of pts) {
      const c = P.data.num(p.cop_mean), xx = x(P.data.num(p.ts));
      const dhw = p.mode === "dhw", bx = dhw ? xx + bw * 0.45 : xx, bww = dhw ? bw * 0.55 : bw;
      s += `<rect x="${bx.toFixed(1)}" y="${y(c).toFixed(1)}" width="${bww.toFixed(1)}" height="${(bottom - y(c)).toFixed(1)}" rx="1.5" fill="${p.mode === "dhw" ? C.dhw : C.lwt}"><title>${esc(fmtTime(P.data.num(p.ts) * 1000))} · COP ${esc(c.toFixed(2))}</title></rect>`;
    }
    for (const tk of timeTicks(from, now, fmtTime)) s += `<text x="${x(tk.t).toFixed(1)}" y="${h - 3}" class="tick" text-anchor="middle">${esc(tk.label)}</text>`;
    if (!pts.length) s += `<text x="${(left + right) / 2}" y="${h / 2}" class="empty" text-anchor="middle">${esc(t.no_history)}</text>`;
    return `<svg viewBox="0 0 ${W} ${h}" class="chart" role="img">${s}</svg>`;
  }

  /* horizontal bar 0..max with a marker */
  function gauge(value, max, color, mark) {
    const pct = fin(value) && max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
    const mk = fin(mark) && max > 0 ? `<i class="mk" style="left:${Math.max(0, Math.min(100, (mark / max) * 100)).toFixed(1)}%"></i>` : "";
    return `<div class="gauge"><span style="width:${pct.toFixed(1)}%;background:${color}"></span>${mk}</div>`;
  }

  Object.assign(P, { charts: { get W() { return W; }, setWidth, C, PT, RING, ptColor, lineChart, curveChart, strip24, copBars, gauge, niceRange, timeTicks } });
  if (window.__dcmEffBoot) window.__dcmEffBoot();
})();
