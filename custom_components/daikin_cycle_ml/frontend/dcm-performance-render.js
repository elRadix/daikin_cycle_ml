/*
 * Daikin Cycle ML — Performance card: texts and HTML.
 * Part of custom:daikin-performance-card (see daikin-performance-card.js).
 * Pure string builders: tested under Node, no DOM.
 */
(function () {
  "use strict";

  const P = (window.DaikinPerformanceCardParts = window.DaikinPerformanceCardParts || {});
  const C = { good: "#3ccf7a", watch: "#ffb020", bad: "#ff4d4d", info: "#4fc3f7" };

  const I18N = {
    en: {
      title: "Performance", sub: "Load · compressor · COP against spec", thermal: "Capacity used", electrical: "Electrical power",
      compressor: "Compressor", cop_spec: "COP vs rating point", spec: "rating", outdoor: "Outdoor", water: "Leaving water", heat: "Heat out",
      static: "Static load", of_nominal: "of nominal", headroom: "RESERVE", little: "LITTLE RESERVE", none: "AT ITS LIMIT",
      room: "About {kw} kW more heat available from the heat pump at {out} °C / {lwt} °C (estimate).",
      room_none: "Add the max heat for this condition in the model profile to see the kW left.",
      miss_hc: "Max heat unknown · add it in the model profile", miss_el: "Needs max heat and spec COP", miss_f: "Speed range not known yet",
      nearest: "Nearest point: {from} · add a point closer to {out} °C / {lwt} °C",
      v_idle: "The compressor is off. The dials show the next run.", v_defrost: "Defrosting: the loads return when heating resumes.",
      v_no_limits: "No limits known for this model yet. Add max heat points or the compressor range in the model profile.",
      v_at_limit: "At its limit: the compressor is at full speed and the water stays more than 2 K below its target. A lower water temperature (heating curve) gives back capacity and COP.",
      v_at_limit_buh: "At its limit and the backup heater is on. A lower water temperature (heating curve) gives back capacity and COP.",
      v_near_limit: "Working hard: close to the estimated maximum at this outdoor and water temperature.",
      v_ok_efficient: "Room to spare and at or above the rated COP: the efficient part of the curve.",
      v_ok: "Running with room to spare.",
      profile: "Model profile", profile_hint: "From the model chosen in setup. Fill in what is missing or adjust a value: your value is used by the whole integration.",
      p_out: "Outdoor °C", p_water: "Water °C", p_hmax: "Max heat kW", p_cop: "Spec COP", p_src: "Source", add: "Add point",
      rps_min: "Compressor minimum", rps_max: "Compressor maximum", learned_from: "learned from {n} runs",
      learned_hmax: "Learned from your runs at full speed", from_samples: "from {n} samples",
      src: { datasheet: "Datasheet", learned: "Learned", manual: "Manual", estimate: "Estimate" }, missing: "Missing", reset: "Remove my value",
      saved: "Saved: used by the whole integration.", error: "Not saved: {msg}", not_found: "Daikin Cycle ML entities not found.",
      room_seen: "It delivers more than the estimate here: the maximum is at least {kw} kW.",
      est_max: "Estimate from Daikin's maximum ({kw} kW at A7/W35), lower in frost",
      est_nominal: "Estimate from the nominal {kw} kW, lower in frost · adjust it in the model profile",
      seen: "Delivers more than the estimate: maximum raised to what it does now",
      f_seen: "Maximum = highest speed seen so far",
      el_est: "Estimate (max heat ÷ COP)",
      v_buh_on: "The backup heater is on while the heat pump still has reserve. The Daikin controller decides this (equilibrium temperature, delay after start, defrost or emergency mode): check those settings.",
      states: { heating: "Heating", dhw: "Hot water", off: "Off" },
    },
    nl: {
      title: "Prestatie", sub: "Belasting · compressor · COP t.o.v. spec", thermal: "Benut vermogen", electrical: "Elektrisch vermogen",
      compressor: "Compressor", cop_spec: "COP t.o.v. meetpunt", spec: "meetpunt", outdoor: "Buiten", water: "Aanvoer", heat: "Warmte",
      static: "Statische last", of_nominal: "van nominaal", headroom: "RESERVE", little: "WEINIG RESERVE", none: "OP ZIJN GRENS",
      room: "Nog ongeveer {kw} kW warmte beschikbaar uit de warmtepomp bij {out} °C / {lwt} °C (schatting).",
      room_none: "Vul het maximale vermogen voor deze situatie in het modelprofiel in om de resterende kW te zien.",
      miss_hc: "Max. vermogen onbekend · vul het in het modelprofiel in", miss_el: "Vraagt max. vermogen en spec-COP", miss_f: "Toerenbereik nog niet bekend",
      nearest: "Dichtstbijzijnd punt: {from} · voeg een punt dichter bij {out} °C / {lwt} °C toe",
      v_idle: "De compressor staat uit. De meters tonen de volgende run.", v_defrost: "Ontdooien: de lasten komen terug als het verwarmen hervat.",
      v_no_limits: "Nog geen grenzen bekend voor dit model. Vul maximaal-vermogenpunten of het compressorbereik in het modelprofiel in.",
      v_at_limit: "Op zijn grens: de compressor draait op vol toerental en het water blijft meer dan 2 K onder het doel. Een lagere watertemperatuur (stooklijn) geeft vermogen en COP terug.",
      v_at_limit_buh: "Op zijn grens en de backup-heater staat aan. Een lagere watertemperatuur (stooklijn) geeft vermogen en COP terug.",
      v_near_limit: "Werkt hard: dicht bij het geschatte maximum bij deze buiten- en watertemperatuur.",
      v_ok_efficient: "Ruim binnen de grens en op of boven de nominale COP: het zuinige deel van de curve.",
      v_ok: "Draait ruim binnen de grens.",
      profile: "Modelprofiel", profile_hint: "Uit het model van de installatie. Vul aan wat ontbreekt of pas een waarde aan: je waarde wordt door de hele integratie gebruikt.",
      p_out: "Buiten °C", p_water: "Water °C", p_hmax: "Max. vermogen kW", p_cop: "Spec-COP", p_src: "Bron", add: "Punt toevoegen",
      rps_min: "Compressor minimum", rps_max: "Compressor maximum", learned_from: "geleerd uit {n} runs",
      learned_hmax: "Geleerd uit je runs op vol toerental", from_samples: "uit {n} metingen",
      src: { datasheet: "Datasheet", learned: "Geleerd", manual: "Handmatig", estimate: "Schatting" }, missing: "Ontbreekt", reset: "Mijn waarde wissen",
      saved: "Opgeslagen: de hele integratie gebruikt het.", error: "Niet opgeslagen: {msg}", not_found: "Daikin Cycle ML-entiteiten niet gevonden.",
      room_seen: "Hij levert hier meer dan de schatting: het maximum is minstens {kw} kW.",
      est_max: "Schatting uit het Daikin-maximum ({kw} kW bij A7/W35), lager bij vorst",
      est_nominal: "Schatting uit het nominale vermogen {kw} kW, lager bij vorst · aan te passen in het modelprofiel",
      seen: "Levert meer dan de schatting: maximum verhoogd tot wat hij nu doet",
      f_seen: "Maximum = hoogste toerental tot nu toe",
      el_est: "Schatting (max. warmte ÷ COP)",
      v_buh_on: "De backup-heater staat aan terwijl de warmtepomp nog reserve heeft. Dat beslist de Daikin-regeling (evenwichtstemperatuur, vertraging na de start, ontdooien of noodbedrijf): controleer die instellingen.",
      states: { heating: "Verwarmen", dhw: "Warm water", off: "Uit" },
    },
    fr: {
      title: "Performance", sub: "Charge · compresseur · COP par rapport à la fiche", thermal: "Puissance utilisée", electrical: "Puissance électrique",
      compressor: "Compresseur", cop_spec: "COP / point de mesure", spec: "point", outdoor: "Extérieur", water: "Départ", heat: "Chaleur",
      static: "Charge statique", of_nominal: "du nominal", headroom: "RÉSERVE", little: "PEU DE RÉSERVE", none: "À SA LIMITE",
      room: "Encore environ {kw} kW de chaleur disponibles de la pompe à chaleur à {out} °C / {lwt} °C (estimation).",
      room_none: "Ajoutez la puissance max. pour cette condition dans le profil du modèle pour voir les kW restants.",
      miss_hc: "Puissance max. inconnue · ajoutez-la dans le profil du modèle", miss_el: "Demande la puissance max. et le COP de la fiche", miss_f: "Plage de vitesse pas encore connue",
      nearest: "Point le plus proche : {from} · ajoutez un point plus proche de {out} °C / {lwt} °C",
      v_idle: "Le compresseur est à l'arrêt. Les cadrans montrent le prochain cycle.", v_defrost: "Dégivrage : les charges reviennent à la reprise du chauffage.",
      v_no_limits: "Aucune limite connue pour ce modèle. Ajoutez des points de puissance max. ou la plage du compresseur dans le profil du modèle.",
      v_at_limit: "À sa limite : le compresseur est à pleine vitesse et l'eau reste plus de 2 K sous sa cible. Une eau moins chaude (loi d'eau) rend de la puissance et du COP.",
      v_at_limit_buh: "À sa limite et l'appoint électrique est en marche. Une eau moins chaude (loi d'eau) rend de la puissance et du COP.",
      v_near_limit: "Travaille dur : proche du maximum estimé à cette température extérieure et d'eau.",
      v_ok_efficient: "De la réserve et un COP égal ou supérieur au nominal : la partie efficace de la courbe.",
      v_ok: "Fonctionne avec de la réserve.",
      profile: "Profil du modèle", profile_hint: "Issu du modèle choisi à l'installation. Complétez ce qui manque ou ajustez une valeur : elle est utilisée par toute l'intégration.",
      p_out: "Extérieur °C", p_water: "Eau °C", p_hmax: "Puissance max. kW", p_cop: "COP fiche", p_src: "Source", add: "Ajouter un point",
      rps_min: "Compresseur minimum", rps_max: "Compresseur maximum", learned_from: "appris sur {n} cycles",
      learned_hmax: "Appris de vos cycles à pleine vitesse", from_samples: "sur {n} mesures",
      src: { datasheet: "Fiche", learned: "Appris", manual: "Manuel", estimate: "Estimation" }, missing: "Manquant", reset: "Effacer ma valeur",
      saved: "Enregistré : utilisé par toute l'intégration.", error: "Non enregistré : {msg}", not_found: "Entités Daikin Cycle ML introuvables.",
      room_seen: "Elle fournit ici plus que l'estimation : le maximum est d'au moins {kw} kW.",
      est_max: "Estimation à partir du maximum Daikin ({kw} kW à A7/W35), plus bas par gel",
      est_nominal: "Estimation à partir des {kw} kW nominaux, plus bas par gel · modifiable dans le profil du modèle",
      seen: "Fournit plus que l'estimation : maximum relevé à ce qu'elle fait maintenant",
      f_seen: "Maximum = vitesse la plus haute vue jusqu'ici",
      el_est: "Estimation (chaleur max. ÷ COP)",
      v_buh_on: "L'appoint électrique est en marche alors que la pompe à chaleur a encore de la réserve. C'est la régulation Daikin qui décide (température d'équilibre, délai après le démarrage, dégivrage ou mode secours) : vérifiez ces réglages.",
      states: { heating: "Chauffage", dhw: "Eau chaude", off: "Arrêt" },
    },
  };

  function makeFmt(lang) {
    const loc = lang === "nl" ? "nl-NL" : lang === "fr" ? "fr-FR" : "en-GB";
    const nf = (d) => (v) => (v === null || v === undefined || !isFinite(v) ? "—"
      : Number(v).toLocaleString(loc, { minimumFractionDigits: d, maximumFractionDigits: d }));
    return { n0: nf(0), n1: nf(1), n2: nf(2), fill: (tpl, p) => String(tpl).replace(/\{(\w+)\}/g, (_, k) => (p[k] === undefined || p[k] === null ? "—" : p[k])) };
  }

  /* 240° dial, 0-100 %, amber from WATCH, red from BAD */
  function dial(p, title, sub, big, note) {
    const M = P.model, cx = 100, cy = 100, R = 82, a0 = 150, span = 240, has = p !== null && isFinite(p);
    const ang = (v) => (a0 + (Math.max(0, Math.min(100, v)) / 100) * span) * Math.PI / 180;
    const pt = (v, r) => [cx + r * Math.cos(ang(v)), cy + r * Math.sin(ang(v))];
    const arc = (v0, v1, r) => {
      const [x0, y0] = pt(v0, r), [x1, y1] = pt(v1, r), large = (v1 - v0) * span / 100 > 180 ? 1 : 0;
      return `M${x0.toFixed(1)} ${y0.toFixed(1)} A${r} ${r} 0 ${large} 1 ${x1.toFixed(1)} ${y1.toFixed(1)}`;
    };
    let s = `<path d="${arc(0, 100, R)}" fill="none" stroke="#1d2731" stroke-width="10" stroke-linecap="round"/>`
      + `<path d="${arc(M.WATCH, M.BAD, R)}" fill="none" stroke="${C.watch}" stroke-width="10" opacity=".85"/>`
      + `<path d="${arc(M.BAD, 100, R)}" fill="none" stroke="${C.bad}" stroke-width="10" stroke-linecap="round"/>`;
    if (has) s += `<path d="${arc(0, Math.max(0.5, Math.min(100, p)), R)}" fill="none" stroke="${C[M.zone(p)]}" stroke-width="4" stroke-linecap="round"/>`;
    for (let v = 0; v <= 100; v += 5) {
      const major = v % 10 === 0, [x0, y0] = pt(v, R - 9), [x1, y1] = pt(v, R - (major ? 18 : 13));
      s += `<line x1="${x0.toFixed(1)}" y1="${y0.toFixed(1)}" x2="${x1.toFixed(1)}" y2="${y1.toFixed(1)}" class="tk" stroke-width="${major ? 1.6 : 0.8}"/>`;
      if (major && (big || v % 20 === 0)) {
        const [lx, ly] = pt(v, R - 28);
        s += `<text x="${lx.toFixed(1)}" y="${(ly + 3).toFixed(1)}" class="tkl" text-anchor="middle">${v}</text>`;
      }
    }
    const deg = a0 + ((has ? Math.max(0, Math.min(104, p)) : 0) / 100) * span;
    s += `<g class="needle" style="transform-origin:${cx}px ${cy}px;transform:rotate(${deg.toFixed(1)}deg)"><path d="M${cx - 8} ${cy - 2.2} L${cx + R - 14} ${cy} L${cx - 8} ${cy + 2.2}z" fill="${has ? C.bad : "#56626e"}"/></g>`
      + `<circle cx="${cx}" cy="${cy}" r="7" fill="#2a3540" stroke="#0b0f13" stroke-width="2"/>`
      + `<text x="${cx}" y="${cy + 38}" class="val" text-anchor="middle" font-size="${big ? 30 : 26}">${has ? Math.round(p) : "—"}${has ? '<tspan class="unit" dx="2">%</tspan>' : ""}</text>`;
    const esc = M.esc;
    return `<div class="dial${big ? " main" : ""}"><svg viewBox="0 0 200 160" role="img" aria-label="${esc(title)} ${has ? Math.round(p) + " %" : "—"}">${s}</svg>`
      + `<div class="cap">${esc(title)}</div><div class="sub">${esc(sub)}</div>${note ? `<div class="miss">${esc(note)}</div>` : ""}</div>`;
  }

  function srcChip(t, src) {
    return src ? `<span class="srcchip ${src}">${P.model.esc(t.src[src] || src)}</span>` : `<span class="srcchip missing">${P.model.esc(t.missing)}</span>`;
  }

  function profile(m, t, f, ui) {
    const esc = P.model.esc, num = P.model.num, L = m.limits;
    const rpsRow = (k) => {
      const v = num(L[k === "rps_min" ? "fmin" : "fmax"]), src = m.sources[k] || null;
      const note = src === "learned" && m.learned.runs ? " · " + f.fill(t.learned_from, { n: m.learned.runs }) : "";
      return `<div class="pf"><label for="pf-${k}">${esc(t[k])}</label><div class="pin"><input id="pf-${k}" type="number" step="1" min="1" max="200" inputmode="decimal" data-field="${k}" value="${v === null ? "" : v}"><span>rps</span></div>`
        + `<div class="pmeta">${srcChip(t, src)}<span class="muted">${esc(note)}</span>${src === "manual" ? `<button type="button" class="lnk" data-act="clear-field" data-k="${k}">${esc(t.reset)}</button>` : ""}</div></div>`;
    };
    const rows = m.points.map((p) => {
      const src = p.src || {}, key = `${p.t_out}|${p.t_lwc}`;
      const cell = (c, step) => `<input type="number" step="${step}" data-pt="${esc(key)}" data-c="${c}" aria-label="${esc(t["p_" + c])} ${esc(p.label || "")}" class="${num(p[c]) === null ? "empty" : ""}" value="${num(p[c]) === null ? "" : p[c]}">`;
      const manual = src.hmax === "manual" || src.cop === "manual";
      return `<tr><td>${f.n0(num(p.t_out))}</td><td>${f.n0(num(p.t_lwc))}</td><td>${cell("hmax", 0.1)}</td><td>${cell("cop", 0.01)}</td>`
        + `<td>${srcChip(t, src.hmax || src.cop || null)}${src.hmax === "learned" && num(p.hmax_n) ? ` <span class="muted">${esc(f.fill(t.from_samples, { n: f.n0(num(p.hmax_n)) }))}</span>` : ""}${manual ? ` <button type="button" class="lnk" data-act="clear-point" data-pt="${esc(key)}">${esc(t.reset)}</button>` : ""}</td></tr>`;
    }).join("");
    return `<div class="prof"><div class="hint">${esc(t.profile_hint)}</div><div class="pgrid">${rpsRow("rps_min")}${rpsRow("rps_max")}</div>`
      + `<div class="tw"><table><thead><tr><th>${esc(t.p_out)}</th><th>${esc(t.p_water)}</th><th>${esc(t.p_hmax)}</th><th>${esc(t.p_cop)}</th><th>${esc(t.p_src)}</th></tr></thead><tbody>${rows}`
      + `<tr class="new"><td><input type="number" step="1" id="new-t" aria-label="${esc(t.p_out)}"></td><td><input type="number" step="1" id="new-w" aria-label="${esc(t.p_water)}"></td>`
      + `<td><input type="number" step="0.1" id="new-hc" aria-label="${esc(t.p_hmax)}"></td><td><input type="number" step="0.01" id="new-cop" aria-label="${esc(t.p_cop)}"></td>`
      + `<td><button type="button" class="btn" data-act="add-point">${esc(t.add)}</button></td></tr></tbody></table></div>`
      + (ui.msg ? `<div class="pmsg ${ui.msgErr ? "err" : ""}">${esc(ui.msg)}</div>` : "") + `</div>`;
  }

  function render(m, cfg, ui) {
    const M = P.model, esc = M.esc, t = I18N[m.lang] || I18N.en, f = makeFmt(m.lang), L = m.limits, l = m.live;
    const head = `<div class="head"><div class="ic">🏁</div><div class="hm"><div class="ht">${esc((cfg && cfg.title) || t.title)}${m.model ? " · " + esc(m.model) : ""}</div>`
      + `<div class="hs">${esc(t.sub)}${m.meta ? " · " + esc(m.meta) : ""}</div></div>${m.ok ? `<span class="badge" style="background:${C[m.lvl]}">${esc(t["v_" + m.key] ? (m.lvl === "good" ? "✓" : m.lvl === "watch" ? "⚠" : m.lvl === "bad" ? "⛔" : "ℹ") : "")}</span>` : ""}</div>`;
    if (!m.ok) return head + `<div class="body"><div class="note">${esc(t.not_found)}</div></div>`;
    const cond = { out: f.n0(l.outdoor), lwt: f.n0(l.lwt) };
    const sub = {
      thermal: L.thMax !== null ? `${f.n1(l.heat)} / ${f.n1(L.thMax)} kW` : `${f.n1(l.heat)} kW`,
      electrical: L.elMax !== null ? `${f.n2(l.power === null ? null : l.power / 1000)} / ${f.n2(L.elMax)} kW` : `${f.n2(l.power === null ? null : l.power / 1000)} kW`,
      compressor: L.fmin !== null && L.fmax !== null ? `${f.n0(l.rps)} rps · ${f.n0(L.fmin)}–${f.n0(L.fmax)}` : `${f.n0(l.rps)} rps`,
    };
    const note = {
      thermal: L.thMax === null ? t.miss_hc : L.thSeen ? t.seen : L.thLearned ? t.learned_hmax
        : L.thEstimate ? f.fill(L.basis === "max" ? t.est_max : t.est_nominal, { kw: L.basis === "max" ? f.n2(L.anchor) : f.n0(L.anchor) })
          : !L.thExact ? f.fill(t.nearest, { from: L.thFrom.join(", "), out: cond.out, lwt: cond.lwt }) : "",
      electrical: L.elMax === null ? t.miss_el : L.elEst ? t.el_est : "",
      compressor: L.fmin === null || L.fmax === null ? t.miss_f : L.fSeen ? t.f_seen : "",
    };
    const order = m.primary === "thermal" ? ["compressor", "thermal", "electrical"]
      : m.primary === "electrical" ? ["thermal", "electrical", "compressor"] : ["thermal", "compressor", "electrical"];
    const dials = order.map((k, i) => dial(m.loads[k], t[k], sub[k], i === 1, note[k])).join("");
    const copW = m.copPct === null ? 0 : Math.max(0, Math.min(100, m.copPct - 50));
    const hz = m.atLimit ? "bad" : m.loads.thermal !== null && m.loads.thermal >= M.WATCH ? "watch" : "good";
    const room = L.thSeen ? f.fill(t.room_seen, { kw: f.n1(L.thMax) })
      : m.headroom !== null ? f.fill(t.room, { kw: f.n1(m.headroom), out: cond.out, lwt: cond.lwt }) : t.room_none;
    const cluster = `<div class="cluster"><div class="dials">${dials}</div><div class="strip">`
      + `<div class="boost"><div class="row"><span class="k">${esc(t.cop_spec)}</span><span class="n">${f.n2(l.cop)} · ${m.copPct === null ? "—" : f.n0(m.copPct) + " %"}</span></div>`
      + `<div class="bar"><i style="width:${copW.toFixed(1)}%"></i><b></b></div><div class="scale"><span>50 %</span><span>${esc(t.spec)} ${f.n2(L.copSpec)}</span><span>150 %</span></div></div>`
      + `<div class="cond"><div><div class="k">${esc(t.outdoor)}</div><div class="v">${cond.out} °C</div></div><div><div class="k">${esc(t.water)}</div><div class="v">${cond.lwt} °C</div></div>`
      + `<div><div class="k">${esc(t.heat)}</div><div class="v">${f.n1(l.heat)} kW</div></div><div><div class="k">${esc(t.static)}</div><div class="v">${m.staticLoad === null ? "—" : f.n0(m.staticLoad) + " % " + esc(t.of_nominal)}</div></div></div></div>`
      + `<div class="room"><span class="pill" style="background:${C[hz]}">${esc(hz === "bad" ? t.none : hz === "watch" ? t.little : t.headroom)}</span><span>${esc(room)}</span></div></div>`;
    const verdict = `<div class="vd ${m.lvl}"><span>${m.lvl === "good" ? "✅" : m.lvl === "watch" ? "⚠️" : m.lvl === "bad" ? "⛔" : "ℹ️"}</span><span>${esc(t["v_" + m.key])}</span></div>`;
    const prof = `<button type="button" class="more" data-act="prof" aria-expanded="${ui.prof ? "true" : "false"}">${ui.prof ? "▾" : "▸"} ${esc(t.profile)}</button>` + (ui.prof ? profile(m, t, f, ui) : "");
    return head + `<div class="body">${cluster}${verdict}${prof}</div>`;
  }

  Object.assign(P, { render: { I18N, C, makeFmt, dial, render } });
  if (window.__dcmPerfBoot) window.__dcmPerfBoot();
})();
