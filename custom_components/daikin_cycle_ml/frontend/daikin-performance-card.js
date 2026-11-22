/*
 * Daikin Cycle ML — Performance card (native Lovelace card, #467).
 *
 *   type: custom:daikin-performance-card
 *
 * A car-style cluster: thermal load, compressor speed and electrical load
 * against the limits of the model chosen in setup at the current outdoor
 * and water temperature, COP against the datasheet, and the headroom left
 * before the backup heater. The limits come from sensor hp_specs (the
 * model's datasheet with the user's model profile merged in). The model
 * profile can be filled in or adjusted on the card; it is saved in the
 * integration (service set_model_profile) and used everywhere.
 *
 * Options (all optional):
 *   device_id:    heat pump device (when you have several)
 *   title:        card title
 *   primary_load: compressor | thermal | electrical (the big dial)
 *   language:     '' (auto) | en | nl | fr
 */
(function () {
  "use strict";

  /* DCM-PATCH:BEGIN (same block in every native card; tests/test_488_card_patch.py)
   * #488: a redraw updates the nodes that changed instead of replacing the
   * whole card (innerHTML). Replacing it made the page jump to the top on
   * some browsers (iOS Safari has no scroll anchoring), reset scrolled
   * tables, dropped the focus and wiped a number being typed. */
  function dcmPatch(root, html) {
    const tpl = document.createElement("template");
    tpl.innerHTML = html;
    dcmSync(root, tpl.content);
  }
  function dcmSync(live, next) {
    const a = Array.from(live.childNodes), b = Array.from(next.childNodes);
    b.forEach((y, i) => {
      const x = a[i];
      if (!x) { live.appendChild(y); return; }
      if (x.nodeType !== y.nodeType || x.nodeName !== y.nodeName) { live.replaceChild(y, x); return; }
      if (x.nodeType !== 1) { if (x.nodeValue !== y.nodeValue) x.nodeValue = y.nodeValue; return; }
      /* an input keeps what is typed in it until its stored value changes */
      const val = x.nodeName === "INPUT" && x.getAttribute("value") !== y.getAttribute("value");
      for (const at of Array.from(x.attributes)) if (!y.hasAttribute(at.name)) x.removeAttribute(at.name);
      for (const at of Array.from(y.attributes)) if (x.getAttribute(at.name) !== at.value) x.setAttribute(at.name, at.value);
      if (val) x.value = y.getAttribute("value") || "";
      dcmSync(x, y);
    });
    for (let i = a.length - 1; i >= b.length; i--) live.removeChild(a[i]);
  }
  /* DCM-PATCH:END */

  const CARD_VERSION = "1.2.2";
  const TAG = "daikin-performance-card";
  const EDITOR_TAG = "daikin-performance-card-editor";
  const PARTS = ["model", "render"];
  const P = (window.DaikinPerformanceCardParts = window.DaikinPerformanceCardParts || {});

  const STYLE = `
    :host { display: block; }
    ha-card { overflow: hidden; container-type: inline-size; }
    .head { display: flex; gap: 12px; align-items: center; padding: 14px 16px;
      background: linear-gradient(135deg, rgba(0,151,224,0.16), rgba(0,151,224,0.04)); border-bottom: 3px solid var(--dcm-accent, #0097E0); }
    .ic { width: 40px; height: 40px; border-radius: 10px; background: var(--dcm-accent, #0097E0); display: flex; align-items: center;
      justify-content: center; font-size: 20px; flex-shrink: 0; }
    .hm { min-width: 0; flex: 1; }
    .ht { font-weight: 800; text-transform: uppercase; letter-spacing: .6px; color: var(--primary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .hs { font-size: .82em; font-weight: 600; color: var(--secondary-text-color); }
    .badge { border-radius: 12px; padding: 3px 10px; font-weight: 800; color: #10151a; }
    .body { padding: 10px 14px 14px; color: var(--primary-text-color); display: grid; gap: 10px; }
    .cluster { background: radial-gradient(120% 90% at 50% 0%, #151c24, #0c1116); border-radius: 16px; padding: 12px 10px;
      color: #e8eef4; border: 1px solid #26313c; }
    .dials { display: grid; grid-template-columns: 1fr 1.4fr 1fr; align-items: end; gap: 4px; max-width: 720px; margin: 0 auto; }
    .dial svg { width: 100%; height: auto; display: block; overflow: visible; }
    .dial .tk { stroke: #8392a1; } .dial .tkl { fill: #8392a1; font-size: 9px; }
    .dial .val { fill: #e8eef4; font-weight: 800; font-variant-numeric: tabular-nums; } .dial .unit { fill: #8392a1; font-size: 10px; }
    .dial .cap { text-align: center; font-size: .72em; letter-spacing: .1em; text-transform: uppercase; color: #8392a1; font-weight: 700; margin-top: -4px; }
    .dial .sub { text-align: center; font-size: .74em; color: #b9c4cf; font-variant-numeric: tabular-nums; }
    .dial .miss { text-align: center; font-size: .7em; color: #ffb020; margin-top: 2px; line-height: 1.25; }
    .needle { transition: transform .9s cubic-bezier(.2,.9,.25,1.15); }
    @media (prefers-reduced-motion: reduce) { .needle { transition: none; } }
    .strip { display: grid; grid-template-columns: 1.2fr 1fr; gap: 8px; margin: 10px auto 0; max-width: 720px; }
    .boost, .cond { background: #151c24; border: 1px solid #26313c; border-radius: 12px; padding: 8px 10px; min-width: 0; }
    .boost .row { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; }
    .k { font-size: .68em; letter-spacing: .08em; text-transform: uppercase; color: #8392a1; font-weight: 700; }
    .boost .n { font-weight: 800; font-variant-numeric: tabular-nums; }
    .bar { position: relative; height: 10px; border-radius: 6px; background: #0a0e12; margin-top: 6px; overflow: hidden; }
    .bar i { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 6px; background: linear-gradient(90deg, #1e6fa3, #4fc3f7); }
    .bar b { position: absolute; left: 50%; top: -3px; bottom: -3px; width: 2px; background: #e8eef4; }
    .scale { display: flex; justify-content: space-between; font-size: .66em; color: #8392a1; margin-top: 3px; }
    .cond { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 10px; }
    .cond .v { font-weight: 700; font-variant-numeric: tabular-nums; }
    .room { display: flex; gap: 10px; align-items: center; font-size: .82em; color: #b9c4cf; margin: 10px auto 0; max-width: 720px; flex-wrap: wrap; }
    .pill { font-weight: 800; color: #10151a; border-radius: 999px; padding: 2px 9px; font-size: .86em; letter-spacing: .04em; }
    .vd { display: flex; gap: 8px; align-items: flex-start; border-left: 4px solid #1E88E5; border-radius: 8px; padding: 8px 10px;
      background: var(--secondary-background-color); font-size: .9em; line-height: 1.35; }
    .vd.good { border-left-color: #43A047; } .vd.watch { border-left-color: #FB8C00; } .vd.bad { border-left-color: #E53935; }
    .note { padding: 9px 12px; border-radius: 10px; background: var(--secondary-background-color); font-size: .84em; }
    .more { border: 0; background: none; color: var(--dcm-accent, #0097E0); font: inherit; font-weight: 700; font-size: .9em; cursor: pointer; padding: 6px 0; text-align: left; min-height: 32px; }
    .more:focus-visible, .lnk:focus-visible, .btn:focus-visible, input:focus-visible { outline: 2px solid var(--dcm-accent, #0097E0); outline-offset: 1px; }
    .prof { display: grid; gap: 8px; }
    .hint, .muted { color: var(--secondary-text-color); font-size: .82em; }
    .pgrid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 8px; }
    .pf { background: var(--secondary-background-color); border-radius: 10px; padding: 8px 10px; display: grid; gap: 4px; min-width: 0; }
    .pf label { font-size: .74em; font-weight: 700; color: var(--secondary-text-color); }
    .pin { display: flex; gap: 6px; align-items: center; }
    input { width: 100%; min-width: 0; font: inherit; padding: 5px 7px; border-radius: 8px; border: 1px solid var(--divider-color);
      background: var(--card-background-color); color: var(--primary-text-color); font-variant-numeric: tabular-nums; }
    input.empty { border-style: dashed; border-color: #E53935; }
    .pmeta { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; font-size: .76em; }
    .srcchip { border-radius: 999px; padding: 1px 8px; font-weight: 700; font-size: .78em; white-space: nowrap; }
    .srcchip.datasheet { background: rgba(0,151,224,.18); } .srcchip.learned { background: rgba(67,160,71,.22); }
    .srcchip.manual { background: rgba(251,140,0,.28); } .srcchip.estimate { background: rgba(142,142,147,.24); } .srcchip.missing { background: rgba(229,57,53,.2); }
    .lnk { border: 0; background: none; color: var(--dcm-accent, #0097E0); font: inherit; cursor: pointer; padding: 0; font-size: .95em; }
    .tw { overflow-x: auto; }
    table { border-collapse: collapse; width: 100%; font-size: .85em; }
    th, td { text-align: left; padding: 4px 6px; border-bottom: 1px solid var(--divider-color); vertical-align: middle; }
    th { font-size: .78em; color: var(--secondary-text-color); font-weight: 700; }
    td input { width: 5em; padding: 4px 6px; -moz-appearance: textfield; appearance: textfield; }
    td input::-webkit-outer-spin-button, td input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
    @container (max-width: 420px) { th, td { padding: 4px 3px; } td input { width: 4.4em; } table { font-size: .82em; } }
    .btn { font: inherit; font-weight: 700; font-size: .86em; padding: 5px 10px; border-radius: 8px; border: 0; background: var(--dcm-accent, #0097E0); color: #fff; cursor: pointer; white-space: nowrap; }
    .pmsg { font-size: .84em; color: #43A047; } .pmsg.err { color: #E53935; }
    @container (max-width: 520px) {
      .dials { grid-template-columns: 1fr 1fr; }
      .dial.main { grid-column: 1 / -1; order: -1; max-width: 300px; margin: 0 auto; width: 100%; }
      .strip { grid-template-columns: 1fr; }
    }
  `;

  function define() {
    if (!PARTS.every((k) => P[k]) || customElements.get(TAG)) return;
    const M = P.model, R = P.render;

    class DaikinPerformanceCard extends HTMLElement {
      static getConfigElement() { return document.createElement(EDITOR_TAG); }

      static getStubConfig() { return { primary_load: "compressor" }; }

      setConfig(config) {
        if (!config || typeof config !== "object") throw new Error("Invalid configuration");
        if (config.primary_load && !M.LOADS.includes(config.primary_load)) {
          throw new Error("primary_load must be one of: " + M.LOADS.join(", "));
        }
        this._config = Object.assign({}, config);
        this._ui = this._ui || { prof: false, msg: "", msgErr: false };
        this._sig = null;
        this._draw();
      }

      set hass(hass) { this._hass = hass; this._draw(); }

      get hass() { return this._hass; }

      getCardSize() { return 8; }

      getGridOptions() { return { columns: 12, min_columns: 6, rows: "auto" }; }

      _signature() {
        const ids = M.resolveEntities(this._hass, this._config);
        return Object.values(ids).map((id) => {
          const st = id && this._hass.states[id];
          return st ? id + "@" + (st.last_updated || st.state) : "-";
        }).join("|") + "#" + JSON.stringify(this._ui) + "#" + ((this._hass.locale && this._hass.locale.language) || this._hass.language || "");
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
          this.shadowRoot.addEventListener("change", (ev) => this._onChange(ev));
        }
        this._m = M.buildModel(this._hass, this._config);
        const root = this.shadowRoot.getElementById("root");
        root.setAttribute("lang", this._m.lang);
        dcmPatch(root, R.render(this._m, this._config, this._ui));
      }

      async _save(data) {
        const t = R.I18N[this._m.lang] || R.I18N.en;
        try {
          /* several Daikin Cycle ML entries: name the one shown */
          await this._hass.callService(M.DOMAIN, "set_model_profile", this._m.entryId ? Object.assign({ entry_id: this._m.entryId }, data) : data);
          this._ui.msg = t.saved; this._ui.msgErr = false;
        } catch (err) {
          this._ui.msg = R.makeFmt(this._m.lang).fill(t.error, { msg: (err && err.message) || String(err) });
          this._ui.msgErr = true;
        }
        this._sig = null;
        this._draw();
      }

      _point(key) {
        const [t_out, t_lwc] = String(key).split("|").map(Number);
        return { t_out, t_lwc };
      }

      _onClick(ev) {
        const path = ev.composedPath ? ev.composedPath() : [ev.target];
        for (const el of path) {
          if (!el || !el.getAttribute) continue;
          const act = el.getAttribute("data-act");
          if (!act) continue;
          if (act === "prof") { this._ui.prof = !this._ui.prof; this._ui.msg = ""; this._sig = null; this._draw(); return; }
          if (act === "clear-field") { this._save({ fields: { [el.getAttribute("data-k")]: null } }); return; }
          if (act === "clear-point") {
            this._save({ points: [Object.assign(this._point(el.getAttribute("data-pt")), { hmax: null, cop: null })] });
            return;
          }
          if (act === "add-point") {
            const q = (id) => { const v = M.num(this.shadowRoot.getElementById(id).value); return v; };
            const p = { t_out: q("new-t"), t_lwc: q("new-w") };
            if (p.t_out === null || p.t_lwc === null) return;
            if (q("new-hc") !== null) p.hmax = q("new-hc");
            if (q("new-cop") !== null) p.cop = q("new-cop");
            if (p.hmax === undefined && p.cop === undefined) return;
            this._save({ points: [p] }).then(() => {
              if (!this._ui.msgErr) for (const id of ["new-t", "new-w", "new-hc", "new-cop"]) this.shadowRoot.getElementById(id).value = "";
            });
            return;
          }
        }
      }

      _onChange(ev) {
        const el = ev.target;
        if (!el || !el.getAttribute) return;
        const v = M.num(el.value);
        const field = el.getAttribute("data-field");
        if (field) { this._save({ fields: { [field]: v } }); return; }
        const pt = el.getAttribute("data-pt");
        if (pt) this._save({ points: [Object.assign(this._point(pt), { [el.getAttribute("data-c")]: v })] });
      }
    }

    const LABELS = {
      device_id: "Heat pump (when you have several)", title: "Title", language: "Language",
      primary_load: "Big dial",
    };

    class DaikinPerformanceCardEditor extends HTMLElement {
      setConfig(config) { this._config = Object.assign({}, config); this._render(); }

      set hass(hass) { this._hass = hass; this._render(); }

      _schema() {
        const opt = (v, l) => ({ value: v, label: l });
        return [
          { name: "device_id", selector: { device: { integration: M.DOMAIN } } },
          { name: "title", selector: { text: {} } },
          { name: "primary_load", selector: { select: { mode: "dropdown", options: [opt("compressor", "Compressor"), opt("thermal", "Thermal load"), opt("electrical", "Electrical load")] } } },
          { name: "language", selector: { select: { mode: "dropdown", options: [opt("", "Auto (Home Assistant)"), opt("en", "English"), opt("nl", "Nederlands"), opt("fr", "Français")] } } },
        ];
      }

      _render() {
        if (!this._config || !this._hass) return;
        if (!this._form) {
          this._form = document.createElement("ha-form");
          this._form.computeLabel = (s) => LABELS[s.name] || s.name;
          this._form.addEventListener("value-changed", (ev) => {
            const cfg = Object.assign({}, ev.detail.value);
            for (const k of Object.keys(cfg)) if (cfg[k] === "" || cfg[k] === undefined || cfg[k] === null) delete cfg[k];
            this._config = cfg;
            this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: cfg }, bubbles: true, composed: true }));
          });
          this.appendChild(this._form);
        }
        this._form.hass = this._hass;
        this._form.schema = this._schema();
        this._form.data = Object.assign({}, this._config);
      }
    }

    customElements.define(TAG, DaikinPerformanceCard);
    if (!customElements.get(EDITOR_TAG)) customElements.define(EDITOR_TAG, DaikinPerformanceCardEditor);
    window.DaikinPerformanceCard = { version: CARD_VERSION, parts: P, Card: DaikinPerformanceCard };
    if (!window.__dcmPerfCardLogged) {
      window.__dcmPerfCardLogged = true;
      console.info(`%c DAIKIN-PERFORMANCE-CARD %c ${CARD_VERSION} `,
        "color:#fff;background:#0097E0;font-weight:700", "color:#0097E0;background:#fff;font-weight:700");
    }
  }

  window.customCards = window.customCards || [];
  if (!window.customCards.some((c) => c.type === TAG)) {
    window.customCards.push({
      type: TAG,
      name: "Daikin Cycle ML · Performance",
      description: "Thermal load, compressor speed and electrical load against the limits of your model, COP against the datasheet and the headroom before the backup heater.",
      preview: true,
      documentationURL: "https://github.com/elRadix/daikin_cycle_ml/tree/main/dashboard/cards/daikin-performance-card",
    });
  }
  window.__dcmPerfBoot = define;
  define();
})();
