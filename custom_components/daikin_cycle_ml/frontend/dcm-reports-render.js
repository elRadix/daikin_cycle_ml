/*
 * Daikin Cycle ML — Reports card: HTML of the controls, tabs, tiles,
 * tables and charts. Part of custom:daikin-reports-card. Pure functions on
 * the view model of dcm-reports-model.js: tested under Node.
 */
(function () {
  "use strict";

  const P = (window.DaikinReportsCardParts = window.DaikinReportsCardParts || {});
  const COL = { good: "#43A047", watch: "#FB8C00", act: "#E53935", incomplete: "#8E8E93", line: "#0097E0", bar: "#7FB8DA", alt: "#FB8C00" };

  function fmt(lang) {
    const cache = {};
    return (v, dec) => {
      if (v === null || v === undefined || !isFinite(v)) return "—";
      const k = String(dec);
      cache[k] = cache[k] || new Intl.NumberFormat(lang, { minimumFractionDigits: dec, maximumFractionDigits: dec });
      return cache[k].format(v);
    };
  }

  function unitOf(T, u) { return u === "kwh" ? T.kwh : u === "h" ? T.h : u === "min" ? T.min : u; }

  /* change chip: +3.2 % in green / red by what is better; grey when neutral */
  function chip(m, row, f) {
    if (row.delta === null && row.pct === null) return "";
    const better = P.better[row.k];
    const up = (row.pct !== null ? row.pct : row.delta) > 0;
    const zero = (row.pct !== null ? Math.abs(row.pct) < 0.5 : Math.abs(row.delta) < 1e-9);
    const cls = zero || better === undefined || better === null ? "n" : (up === better ? "g" : "b");
    const txt = row.pct !== null ? (row.pct > 0 ? "+" : "") + f(row.pct, 1) + " %" : (row.delta > 0 ? "+" : "") + f(row.delta, row.dec);
    return `<span class="chg ${cls}">${P.model.esc(txt)}</span>`;
  }

  function select(name, label, value, opts) {
    const E = P.model.esc;
    return `<label class="ctl"><span>${E(label)}</span><select data-ctl="${name}" aria-label="${E(label)}">`
      + opts.map(([v, l]) => `<option value="${E(v)}"${v === value ? " selected" : ""}>${E(l)}</option>`).join("")
      + `</select></label>`;
  }

  function controls(m) {
    const T = m.T, E = P.model.esc, u = m.ui;
    const periods = m.available.map((k) => [k, P.model.periodLabel(m.ptype || u.type, k, m.lang, T)]);
    if (m.key && !m.available.includes(m.key)) periods.unshift([m.key, m.label]);
    return `<div class="ctls">`
      + select("type", T.lbl_type, u.type, m.types.map((t) => [t, T.types[t]]))
      + `<div class="ctl per"><span>${E(T.lbl_period)}</span><div class="stp">`
      + `<button type="button" class="nav" data-act="prev" aria-label="${E(T.prev)}"${m.prevKey ? "" : " disabled"}>‹</button>`
      + `<select data-ctl="key" aria-label="${E(T.lbl_period)}">${periods.map(([v, l]) => `<option value="${E(v)}"${v === m.key ? " selected" : ""}>${E(l)}</option>`).join("")}</select>`
      + `<button type="button" class="nav" data-act="next" aria-label="${E(T.next)}"${m.nextKey ? "" : " disabled"}>›</button></div></div>`
      + select("mode", T.lbl_mode, u.mode, m.modes.map((x) => [x, T.modes[x]]))
      + select("against", T.lbl_compare, u.against, m.againsts.map((x) => [x, T.against[x]]))
      + `</div>`;
  }

  function tabs(m) {
    const E = P.model.esc;
    return `<div class="tabs" role="tablist">` + m.tabs.map((t) => `<button type="button" role="tab" data-tab="${t}" aria-selected="${t === m.ui.tab}" class="tab${t === m.ui.tab ? " on" : ""}">${E(m.T.tabs[t])}</button>`).join("") + `</div>`;
  }

  /* ---------- charts (inline SVG, no library) ---------- */

  function bars(values, labels, opts) {
    const E = P.model.esc;
    const w = 320, h = 120, pad = 18;
    const vals = values.map((v) => (v === null || v === undefined || !isFinite(v) ? null : v));
    const max = Math.max(0, ...vals.filter((v) => v !== null)) || 1;
    const n = Math.max(1, vals.length), bw = (w - pad) / n;
    const f = opts.f;
    let svg = `<svg viewBox="0 0 ${w} ${h + 16}" role="img" aria-label="${E(opts.title)}" class="chart">`;
    vals.forEach((v, i) => {
      if (v === null) return;
      const bh = Math.max(1, (v / max) * (h - pad));
      const x = pad + i * bw + bw * 0.15;
      svg += `<rect x="${x.toFixed(1)}" y="${(h - bh).toFixed(1)}" width="${(bw * 0.7).toFixed(1)}" height="${bh.toFixed(1)}" rx="2" fill="${opts.color || COL.bar}"${i === opts.hi ? ' class="hi"' : ""}><title>${E(labels[i])}: ${E(f(v, opts.dec))}</title></rect>`;
    });
    if (opts.line) {
      const lv = opts.line.map((v) => (v === null || v === undefined || !isFinite(v) ? null : v));
      const lmax = Math.max(...lv.filter((v) => v !== null), 0) || 1;
      const lmin = Math.min(...lv.filter((v) => v !== null), lmax);
      const span = lmax - lmin || 1;
      const pts = lv.map((v, i) => (v === null ? null : [pad + i * bw + bw / 2, h - pad / 2 - ((v - lmin) / span) * (h - pad * 1.5)]));
      let d = "";
      pts.forEach((p) => { if (p) d += (d ? " L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1); });
      if (d) svg += `<path d="${d}" fill="none" stroke="${COL.line}" stroke-width="2"/>`;
      pts.forEach((p, i) => { if (p) svg += `<circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="2.6" fill="${COL.line}"><title>${E(labels[i])}: ${E(f(lv[i], 2))}</title></circle>`; });
    }
    const first = labels[0] || "", last = labels[labels.length - 1] || "";
    svg += `<text x="${pad}" y="${h + 12}" class="ax">${E(first)}</text><text x="${w}" y="${h + 12}" text-anchor="end" class="ax">${E(last)}</text>`;
    svg += `<text x="0" y="10" class="ax">${E(f(max, opts.dec))}</text></svg>`;
    return svg;
  }

  function lines(series, labels, opts) {
    const E = P.model.esc;
    const w = 320, h = 120, pad = 22;
    const all = [].concat(...series.map((s) => s.values)).filter((v) => v !== null && v !== undefined && isFinite(v));
    if (!all.length) return "";
    const max = Math.max(...all), min = Math.min(...all), span = max - min || 1;
    const n = Math.max(1, labels.length - 1);
    const xy = (i, v) => [pad + (i / n) * (w - pad), 8 + (1 - (v - min) / span) * (h - 16)];
    let svg = `<svg viewBox="0 0 ${w} ${h + 16}" role="img" aria-label="${E(opts.title)}" class="chart">`;
    for (const s of series) {
      let d = "";
      s.values.forEach((v, i) => {
        if (v === null || v === undefined || !isFinite(v)) return;
        const [x, y] = xy(i, v); d += (d ? " L" : "M") + x.toFixed(1) + " " + y.toFixed(1);
      });
      if (d) svg += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="2"><title>${E(s.name)}</title></path>`;
    }
    svg += `<text x="0" y="12" class="ax">${E(opts.f(max, 0))}</text><text x="0" y="${h}" class="ax">${E(opts.f(min, 0))}</text>`;
    svg += `<text x="${pad}" y="${h + 12}" class="ax">${E(labels[0] || "")}</text><text x="${w}" y="${h + 12}" text-anchor="end" class="ax">${E(labels[labels.length - 1] || "")}</text></svg>`;
    return svg + `<div class="lg">${series.map((s) => `<span><i style="background:${s.color}"></i>${E(s.name)}</span>`).join("")}</div>`;
  }

  /* ---------- panels ---------- */

  function tile(m, t, f) {
    const E = P.model.esc;
    return `<div class="tile"><div class="tk">${E(m.T.m[t.k])}</div><div class="tv">${E(f(t.value, t.dec))}`
      + (t.unit ? ` <small>${E(unitOf(m.T, t.unit))}</small>` : "") + `</div>${chip(m, t, f)}</div>`;
  }

  function verdictList(m, f) {
    const E = P.model.esc, T = m.T;
    if (!m.refFound) return `<div class="note">${E(P.model.fill(T.no_ref, { p: m.refLabel || "—" }))}</div>`;
    return `<div class="vds">` + m.judged.map((j) => `<div class="vd ${j.v}"><span class="pill" style="background:${COL[j.v]}">${E(T.verdict[j.v])}</span>`
      + `<span>${E(T.v_text[j.k] || j.k)}</span><span class="vv">${j.pct !== null ? E((j.pct > 0 ? "+" : "") + f(j.pct, 1) + " %") : j.delta !== null ? E((j.delta > 0 ? "+" : "") + f(j.delta, 1)) : ""}</span></div>`).join("") + `</div>`;
  }

  function overview(m, f) {
    const T = m.T, E = P.model.esc;
    let h = `<div class="tiles">${m.tiles.map((t) => tile(m, t, f)).join("")}</div>`;
    if (m.refFound) h += `<div class="muted">${E(P.model.fill(T.vs, { p: m.refLabel }))}</div>`;
    return h + verdictList(m, f);
  }

  function hist(m, key) { return m.history.map((x) => x[key]); }
  function histLabels(m) { return m.history.map((x) => P.model.periodLabel(m.ptype, x.key, m.lang, m.T)); }
  function dayLabels(m) { return m.days.map((d) => String(d.day).slice(5)); }

  function energy(m, f) {
    const T = m.T, E = P.model.esc;
    let h = "";
    const modes = Object.entries(m.byMode);
    if (modes.length) {
      h += `<h4>${E(T.by_mode)}</h4><div class="tw"><table><tr><th></th><th>${E(T.m.el_kwh)}</th><th>${E(T.m.th_kwh)}</th><th>${E(T.m.cop)}</th><th>${E(T.m.runtime_h)}</th></tr>`
        + modes.map(([k, v]) => `<tr><td>${E(T.modes[k] || k)}</td><td>${E(f(v.el_kwh, 1))}</td><td>${E(f(v.th_kwh, 1))}</td><td>${E(f(v.cop, 2))}</td><td>${E(f(v.runtime_h, 1))}</td></tr>`).join("")
        + `</table></div>`;
    }
    if (m.history.length) {
      h += `<h4>${E(P.model.fill(T.history, { n: m.history.length }))}</h4>`
        + bars(hist(m, "el_kwh"), histLabels(m), { title: T.energy_chart, f, dec: 0, line: hist(m, "cop"), hi: m.history.length - 1 })
        + `<div class="lg"><span><i style="background:${COL.bar}"></i>${E(T.energy_chart)}</span><span><i style="background:${COL.line}"></i>${E(T.cop_chart)}</span></div>`;
    }
    if (m.days.length) {
      h += `<h4>${E(T.per_day)}</h4>` + bars(m.days.map((d) => d.el_kwh), dayLabels(m), { title: T.energy_chart, f, dec: 1, line: m.days.map((d) => d.cop) });
    }
    const cop = m.trend.cop;
    if (cop) h += `<div class="muted">${E(T.trend)} ${E(T.m.cop)}: ${E(T["t_" + cop.direction])}</div>`;
    if (m.checks.length) {
      h += `<h4>${E(T.checks)}</h4><ul class="chk">${m.checks.map(([k, n]) => `<li>${E(T.ch[k] || k)}: ${E(P.model.fill(T.days, { n }))}</li>`).join("")}</ul>`;
    }
    return h;
  }

  function temps(m, f) {
    const T = m.T, E = P.model.esc, t = m.temps;
    const kv = (k, v, u) => `<div class="kv"><span>${E(T.m[k])}</span><b>${E(f(v, 1))}${u ? " " + E(u) : ""}</b></div>`;
    let h = `<div class="kvs">${kv("outdoor_mean", t.mean, "°C")}${kv("outdoor_min", t.min, "°C")}${kv("outdoor_max", t.max, "°C")}`
      + `${kv("lwt_mean", t.lwt, "°C")}${kv("return_mean", t.ret, "°C")}${kv("dt_mean", t.dt, "K")}${kv("flow_mean", t.flow, "l/min")}${kv("dd", t.dd, "")}</div>`;
    if (m.scheme) h += `<div class="muted">${E(P.model.fill(T.scheme, { s: m.scheme }))}</div>`;
    if (m.days.length) {
      h += `<h4>${E(T.per_day)}</h4>` + lines([
        { name: T.m.outdoor_mean, color: COL.line, values: m.days.map((d) => d.outdoor_mean !== undefined ? d.outdoor_mean : d.outdoor_run_mean) },
        { name: T.m.lwt_mean, color: COL.alt, values: m.days.map((d) => d.lwt_mean) },
      ], dayLabels(m), { title: T.temp_chart, f });
    } else if (m.history.length) {
      h += lines([{ name: T.m.outdoor_mean, color: COL.line, values: hist(m, "outdoor_mean") },
        { name: T.m.lwt_mean, color: COL.alt, values: hist(m, "lwt_mean") }], histLabels(m), { title: T.temp_chart, f });
    }
    return h;
  }

  function cycling(m, f) {
    const T = m.T, E = P.model.esc, d = m.data;
    const kv = (k, v, dec, u) => `<div class="kv"><span>${E(T.m[k])}</span><b>${E(f(v, dec))}${u ? " " + E(u) : ""}</b></div>`;
    const der = (m.resp && m.resp.derived) || {};
    let h = `<div class="kvs">${kv("cycles", d.cycles, 0)}${kv("runs", d.runs, 0)}${kv("run_mean_min", d.run_mean_min, 0, T.min)}`
      + `${kv("starts_per_h", der.starts_per_h, 2)}${kv("runtime_h", d.runtime_h, 1, T.h)}${kv("quality_mean", d.quality_mean, 0)}${kv("rps_mean", d.rps_mean, 0, "rps")}</div>`;
    if (m.days.length) h += `<h4>${E(T.per_day)}</h4>` + bars(m.days.map((x) => x.cycles), dayLabels(m), { title: T.cycles_chart, f, dec: 0 });
    const tr = m.trend.starts_per_h;
    if (tr) h += `<div class="muted">${E(T.trend)} ${E(T.m.starts_per_h)}: ${E(T["t_" + tr.direction])}</div>`;
    return h;
  }

  function events(m, f) {
    const T = m.T, E = P.model.esc, d = m.data, der = (m.resp && m.resp.derived) || {};
    const kv = (k, v, dec, u) => `<div class="kv"><span>${E(T.m[k])}</span><b>${E(f(v, dec))}${u ? " " + E(u) : ""}</b></div>`;
    let h = `<div class="kvs">${kv("buh_min", d.buh_min, 0, T.min)}${kv("buh_share_pct", der.buh_share_pct, 1, "%")}`
      + `${kv("defrost_count", d.defrost_count, 0)}${kv("defrost_min", d.defrost_min, 0, T.min)}${kv("ml_anomalies", d.ml_anomalies, 0)}${kv("alerts_total", der.alerts_total, 0)}</div>`;
    h += `<h4>${E(T.alerts_by_type)}</h4>`;
    h += m.alerts.length
      ? `<div class="tw"><table>${m.alerts.map(([k, n]) => `<tr><td>${E(k)}</td><td class="r">${E(n)}</td></tr>`).join("")}</table></div>`
      : `<div class="muted">${E(T.no_alerts)}</div>`;
    return h;
  }

  function compare(m, f) {
    const T = m.T, E = P.model.esc;
    let h = `<div class="tw"><table class="cmp"><tr><th>${E(T.metric)}</th><th>${E(m.label)}</th><th>${E(m.refFound ? m.refLabel : T.ref_p)}</th><th>${E(T.change)}</th></tr>`
      + m.rows.map((r) => `<tr><td>${E(T.m[r.k] || r.k)}</td><td class="r">${E(f(r.value, r.dec))}</td><td class="r">${E(f(r.ref, r.dec))}</td><td class="r">${chip(m, r, f)}</td></tr>`).join("")
      + `</table></div>`;
    if (m.history.length > 1) {
      h += `<h4>${E(P.model.fill(T.history, { n: m.history.length }))}</h4>`
        + bars(hist(m, "el_per_dd"), histLabels(m), { title: T.m.el_per_dd, f, dec: 2, line: hist(m, "cop"), hi: m.history.length - 1 })
        + `<div class="lg"><span><i style="background:${COL.bar}"></i>${E(T.m.el_per_dd)}</span><span><i style="background:${COL.line}"></i>${E(T.cop_chart)}</span></div>`;
    }
    return h;
  }

  const PANELS = { overview, energy, temps, cycling, events, compare };

  function render(m, config) {
    const T = m.T, E = P.model.esc, f = fmt(m.lang);
    const title = (config && config.title) || T.title || "Reports";
    const badge = m.overall ? `<span class="badge" style="background:${COL[m.overall]}">${E(T.verdict[m.overall])}</span>` : "";
    let h = `<div class="head"><div class="ic">📊</div><div class="hm"><div class="ht">${E(title)}</div>`
      + `<div class="hs">${E([m.model, m.label].filter(Boolean).join(" · "))}</div></div>${badge}</div>`;
    if (!m.ok) return h + `<div class="body"><div class="note">${E(T.no_entity)}</div></div>`;
    h += `<div class="body">` + controls(m);
    if (m.error) return h + `<div class="note err">${E(P.model.fill(T.error, { msg: m.error }))}</div></div>`;
    if (!m.resp) return h + `<div class="note">${E(T.loading)}</div></div>`;
    if (!m.found) return h + `<div class="note">${E(m.available.length ? T.not_found : T.none)}</div></div>`;
    h += tabs(m);
    if (m.loading) h += `<div class="muted" role="status">${E(T.loading)}</div>`;
    if (!m.finalised) h += `<div class="note">${E(T.open)}</div>`;
    if (m.partial) h += `<div class="note">${E(P.model.fill(T.partial, m.coverage))}</div>`;
    h += `<div class="panel" role="tabpanel">${PANELS[m.ui.tab](m, f)}</div>`;
    return h + `</div>`;
  }

  P.render = { render, fmt, bars, lines, COL };
  if (window.__dcmReportsBoot) window.__dcmReportsBoot();
})();
