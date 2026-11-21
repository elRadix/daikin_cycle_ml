/*
 * Daikin Cycle ML — Efficiency card (native Lovelace card)
 *
 *   type: custom:daikin-efficiency-card
 *
 * Served by the integration itself, no extra frontend cards needed.
 * Live hero (COP, power, heat) and five tabs: Live (setpoint tracker,
 * water, compressor, flow / ΔT and comfort graphs), Today, Efficiency,
 * Curve (heating curve, Carnot, heat balance, defrost, specifications)
 * and Advice. Every graph and tab says whether the current state is
 * good, worth watching or needs action, within the datasheet limits of
 * the configured model. English / Dutch / French, light and dark theme.
 *
 * Files: this one (element, editor, style) + dcm-efficiency-data.js,
 * -assess.js, -charts.js, -verdicts.js, -i18n.js, -render.js. Each
 * file registers itself on window.DaikinEfficiencyCardParts; the
 * element is defined once all parts are loaded (any order).
 *
 * Config (all optional):
 *   device_id:   pick the heat pump when there are several
 *   title:       header title
 *   default_tab: live | today | eff | curve | advice
 *   range:       30m | 3h | 24h (Live graphs)
 *   tabs:        list of tabs to show (default: all)
 *   language:    '' (auto) | en | nl | fr
 *   show_help:   true | false
 *   min_flow:    minimum water flow of your unit in l/min (installation manual)
 *   target_dt:   target ΔT of the installation in K (installer setting; default 5)
 */
(function () {
  "use strict";

  const CARD_VERSION = "1.2.0";
  const TAG = "daikin-efficiency-card";
  const EDITOR_TAG = "daikin-efficiency-card-editor";
  const PARTS = ["data", "assess", "charts", "verdicts", "i18n", "render"];
  const P = (window.DaikinEfficiencyCardParts = window.DaikinEfficiencyCardParts || {});

  const STYLE = `
    :host { display: block; }
    ha-card { overflow: hidden; container-type: inline-size; }
    .head { display: flex; gap: 12px; align-items: center; padding: 14px 16px;
      background: linear-gradient(135deg, rgba(0,151,224,0.16), rgba(0,151,224,0.04));
      border-bottom: 3px solid var(--dcm-accent, #0097E0); }
    .ic { width: 40px; height: 40px; border-radius: 10px; background: var(--dcm-accent, #0097E0);
      display: flex; align-items: center; justify-content: center; font-size: 20px; flex-shrink: 0; }
    .hm { min-width: 0; }
    .ht { font-weight: 800; text-transform: uppercase; letter-spacing: .6px; color: var(--primary-text-color);
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .hs { font-size: .82em; font-weight: 600; color: var(--secondary-text-color); }
    .hero { display: grid; grid-template-columns: 1fr auto; gap: 4px 12px; padding: 12px 16px 8px; color: var(--primary-text-color); }
    .st { display: flex; align-items: center; gap: 6px; font-weight: 700; font-size: .86em; }
    .st .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--disabled-text-color, #9e9e9e); }
    .st.on .dot { background: #43A047; animation: pulse 2s infinite; }
    @keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(67,160,71,.6); } 70% { box-shadow: 0 0 0 8px rgba(67,160,71,0); } 100% { box-shadow: 0 0 0 0 rgba(67,160,71,0); } }
    .big { font-size: 2.4em; font-weight: 800; line-height: 1.1; font-variant-numeric: tabular-nums; }
    .hr { text-align: right; display: flex; flex-direction: column; gap: 4px; align-items: flex-end; }
    .pw { font-size: .95em; font-variant-numeric: tabular-nums; }
    .chip { border-radius: 12px; padding: 3px 10px; font-size: .8em; font-weight: 800; color: #fff; border: 0; font-family: inherit; cursor: pointer; }
    .chip:focus-visible, .go:focus-visible { outline: 2px solid var(--dcm-accent, #0097E0); outline-offset: 2px; }
    .tdot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-left: 4px; vertical-align: middle; }
    .tdot.watch { background: #FB8C00; } .tdot.bad { background: #E53935; }
    .todo { margin-bottom: 12px; } .todo ul { list-style: none; margin: 0; padding: 0; }
    .go { border: 0; background: none; padding: 2px 0; margin-left: 4px; color: var(--dcm-accent, #0097E0); font: inherit; font-weight: 700; cursor: pointer; white-space: nowrap; }
    .chip.good { background: #43A047; } .chip.watch { background: #FB8C00; } .chip.bad { background: #E53935; } .chip.info { background: #1E88E5; }
    .note-s { grid-column: 1 / -1; font-size: .72em; color: var(--secondary-text-color); }
    .tabs { display: grid; grid-template-columns: repeat(5, 1fr); gap: 2px 4px; padding: 6px 8px 0; border-bottom: 1px solid var(--divider-color); }
    .tabs.n4 { grid-template-columns: repeat(4, 1fr); } .tabs.n3 { grid-template-columns: repeat(3, 1fr); }
    .tabs.n2 { grid-template-columns: repeat(2, 1fr); } .tabs.n1 { grid-template-columns: 1fr; }
    @container (max-width: 380px) { .tabs, .tabs.n4 { grid-template-columns: repeat(3, 1fr); } }
    .tab { min-width: 0; overflow-wrap: break-word; hyphens: auto; line-height: 1.15; border: 0; background: none; padding: 8px 4px; cursor: pointer; font: inherit;
      font-size: .84em; font-weight: 700; color: var(--secondary-text-color); border-bottom: 3px solid transparent; border-radius: 8px 8px 0 0; min-height: 40px; }
    .tab.on { color: var(--primary-text-color); border-bottom-color: var(--dcm-accent, #0097E0); background: var(--secondary-background-color); }
    .tab:focus-visible, .win:focus-visible, .more:focus-visible, .hh:focus-visible { outline: 2px solid var(--dcm-accent, #0097E0); }
    .body { padding: 10px 14px 14px; color: var(--primary-text-color); }
    .sect { font-weight: 800; margin: 14px 0 4px; font-size: .92em; }
    .muted { color: var(--secondary-text-color); font-size: .82em; font-weight: 500; }
    .tracker { background: var(--secondary-background-color); border-radius: 12px; padding: 4px 10px 8px; }
    .tracker .sect { margin-top: 6px; }
    .cells { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; }
    .cells .tile { background: var(--card-background-color); }
    .tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); gap: 8px; margin: 8px 0; }
    .tile { background: var(--secondary-background-color); border-radius: 10px; padding: 7px 9px; min-width: 0; }
    .tl { font-size: .7em; font-weight: 700; text-transform: uppercase; letter-spacing: .3px; color: var(--secondary-text-color); overflow-wrap: anywhere; line-height: 1.25; }
    .tv { font-size: 1.2em; font-weight: 800; font-variant-numeric: tabular-nums; }
    .ts { font-size: .72em; color: var(--secondary-text-color); }
    .wins { display: flex; gap: 6px; margin: 12px 0 0; }
    .win { border: 1px solid var(--divider-color); background: none; border-radius: 14px; padding: 4px 12px; cursor: pointer; font: inherit;
      font-size: .82em; font-weight: 700; color: var(--secondary-text-color); min-height: 30px; }
    .win.on { background: var(--dcm-accent, #0097E0); border-color: var(--dcm-accent, #0097E0); color: #fff; }
    .chart { width: 100%; height: auto; display: block; touch-action: pan-y; }
    .chart polyline, .chart line, .chart path { vector-effect: non-scaling-stroke; }
    .chart .grid { stroke: var(--divider-color); stroke-width: 1; }
    .chart .tick { font-size: 8px; fill: var(--secondary-text-color); }
    .chart .rl { font-size: 8px; font-weight: 700; }
    .chart .unit { font-weight: 700; }
    .chart .empty { font-size: 10px; fill: var(--secondary-text-color); }
    .chart .track { fill: var(--secondary-background-color); }
    .chart .callout { fill: var(--card-background-color, #fff); stroke: var(--divider-color); }
    .chart .ct { font-size: 8.5px; fill: var(--primary-text-color); } .chart .ct.b { font-weight: 800; }
    .chart .pt { cursor: pointer; }
    .legend { display: flex; flex-wrap: wrap; gap: 3px 10px; font-size: .74em; color: var(--secondary-text-color); margin: 2px 0 4px; }
    .legend i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 4px; vertical-align: -1px; }
    .vd { display: flex; gap: 8px; align-items: flex-start; border-left: 4px solid; border-radius: 8px; padding: 7px 10px; margin: 6px 0;
      background: var(--secondary-background-color); font-size: .84em; line-height: 1.35; }
    .vd.good { border-color: #43A047; } .vd.watch { border-color: #FB8C00; } .vd.bad { border-color: #E53935; } .vd.info { border-color: #1E88E5; }
    .vi { flex-shrink: 0; }
    .mt { display: grid; gap: 4px; } .mr { display: grid; grid-template-columns: 1fr 1fr 1fr auto; gap: 6px; font-size: .84em; }
    .gauges { display: grid; gap: 6px; margin: 6px 0; }
    .gr { display: grid; grid-template-columns: 7em 1fr 3em; gap: 8px; align-items: center; font-size: .84em; }
    .gr b { text-align: right; font-variant-numeric: tabular-nums; }
    .gauge { position: relative; height: 10px; border-radius: 5px; background: var(--secondary-background-color); overflow: visible; }
    .gauge span { display: block; height: 100%; border-radius: 5px; }
    .gauge .mk { position: absolute; top: -3px; width: 2px; height: 16px; background: var(--primary-text-color); }
    .panels { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 10px 0 4px; }
    .panel { background: var(--secondary-background-color); border-radius: 10px; padding: 7px 9px; min-width: 0; }
    .panel .gauge { margin: 4px 0; background: var(--card-background-color); }
    .specs { border: 1px solid var(--divider-color); border-radius: 10px; padding: 8px 10px; margin: 10px 0; }
    .sg { display: grid; grid-template-columns: auto 1fr; gap: 3px 12px; font-size: .84em; margin-top: 4px; }
    .detail { border: 1px solid var(--divider-color); border-radius: 10px; padding: 6px 10px; margin: 6px 0; font-size: .86em; }
    .adv { border-radius: 12px; padding: 10px 12px; background: var(--secondary-background-color); border-left: 5px solid #1E88E5; }
    .adv.good { border-left-color: #43A047; } .adv.watch { border-left-color: #FB8C00; } .adv.bad { border-left-color: #E53935; }
    .adv .at { font-weight: 700; margin: 4px 0 8px; line-height: 1.35; }
    .note { padding: 9px 12px; border-radius: 10px; background: var(--secondary-background-color); font-size: .84em; margin: 8px 0; line-height: 1.35; }
    .note.warn { border-left: 4px solid #E53935; }
    .more { border: 0; background: none; color: var(--dcm-accent, #0097E0); font: inherit; font-weight: 700; font-size: .86em; cursor: pointer; padding: 8px 0; min-height: 32px; }
    .help { margin-top: 14px; border-top: 1px dashed var(--divider-color); }
    .hh { width: 100%; display: flex; justify-content: space-between; border: 0; background: none; font: inherit; font-weight: 800;
      color: var(--primary-text-color); padding: 10px 0 4px; cursor: pointer; min-height: 36px; }
    .hb { font-size: .84em; color: var(--secondary-text-color); line-height: 1.45; }
    .hb ul { margin: 4px 0 8px; padding-left: 0; list-style: none; } .hb li { margin: 3px 0; color: var(--primary-text-color); }
    .hb p { margin: 6px 0; }
    @container (max-width: 440px) { .cells { grid-template-columns: repeat(2, 1fr); } }
    @container (max-width: 340px) { .cells, .panels { grid-template-columns: repeat(2, 1fr); } .mr { grid-template-columns: 1fr 1fr; } }
  `;

  function define() {
    if (!PARTS.every((k) => P[k]) || customElements.get(TAG)) return;
    const D = P.data;

    class DaikinEfficiencyCard extends HTMLElement {
      static getConfigElement() { return document.createElement(EDITOR_TAG); }

      static getStubConfig() { return { default_tab: "live", range: "3h" }; }

      setConfig(config) {
        if (!config || typeof config !== "object") throw new Error("Invalid configuration");
        if (config.default_tab && !P.render.TABS.includes(config.default_tab)) {
          throw new Error("default_tab must be one of: " + P.render.TABS.join(", "));
        }
        if (config.range && !D.RANGES[config.range]) throw new Error("range must be one of: " + Object.keys(D.RANGES).join(", "));
        this._config = Object.assign({}, config);
        this._ui = { tab: config.default_tab || "live", range: config.range || "3h", adv: false, help: true, bucket: null, historyFailed: false };
        this._buf = this._buf || { samples: [], spans: {} };
        this._sig = null;
        this._draw();
      }

      set hass(hass) {
        this._hass = hass;
        if (this._config && !this._histAsked) this._loadHistory();
        if (this._config && this._ids) D.appendLive(this._buf, hass, this._ids, Date.now() / 1000);
        this._draw();
      }

      get hass() { return this._hass; }

      getCardSize() { return 12; }

      getGridOptions() { return { columns: 12, min_columns: 6, rows: "auto" }; }

      connectedCallback() {
        if (!this._timer) this._timer = setInterval(() => { this._sig = null; this._draw(); }, 30000);
        /* #466: redraw the charts at the new width when the card resizes */
        if (!this._ro && typeof ResizeObserver === "function") {
          this._ro = new ResizeObserver(() => { const w = this._chartWidth(); if (w !== this._w) { this._sig = null; this._draw(); } });
          this._ro.observe(this);
        }
      }

      disconnectedCallback() {
        if (this._timer) { clearInterval(this._timer); this._timer = null; }
        if (this._ro) { this._ro.disconnect(); this._ro = null; }
      }

      _chartWidth() {
        const w = this.getBoundingClientRect ? this.getBoundingClientRect().width : 0;
        return w > 0 ? Math.round((w - 24) / 20) * 20 : 360;   /* 20 px steps: no redraw per pixel */
      }

      async _loadHistory() {
        this._histAsked = true;
        const hass = this._hass;
        this._ids = D.resolveEntities(hass, this._config);
        const ids = D.HISTORY_ROLES.map((r) => this._ids[r]).filter(Boolean);
        if (!ids.length || typeof hass.callWS !== "function") { this._ui.historyFailed = true; return; }
        const now = Date.now();
        try {
          const res = await hass.callWS({
            type: "history/history_during_period", entity_ids: ids,
            start_time: new Date(now - 86400000).toISOString(), end_time: new Date(now).toISOString(),
            minimal_response: false, no_attributes: false, significant_changes_only: false,
          });
          const parsed = D.parseHistory(res, this._ids);
          const live = this._buf.samples.filter((s) => !parsed.samples.length || s.t > parsed.samples[parsed.samples.length - 1].t);
          parsed.samples = parsed.samples.concat(live);
          this._buf = parsed;
        } catch (err) {
          this._ui.historyFailed = true;
          console.debug("daikin-efficiency-card: history unavailable", err);
        }
        this._sig = null;
        this._draw();
      }

      _signature() {
        const ids = this._ids || D.resolveEntities(this._hass, this._config);
        const parts = Object.values(ids).map((id) => {
          const st = id && this._hass.states[id];
          return st ? id + "@" + (st.last_updated || st.state) : "-";
        });
        return parts.join("|") + "#" + JSON.stringify(this._ui) + "#" + this._buf.samples.length
          + "#" + ((this._hass.locale && this._hass.locale.language) || this._hass.language || "");
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
        }
        this._w = this._chartWidth();
        P.charts.setWidth(this._w);
        const m = D.buildModel(this._hass, this._config, this._buf, Date.now() / 1000, this._ui.range);
        m.buf = this._buf;
        const a = P.assess.assess(m);
        const root = this.shadowRoot.getElementById("root");
        root.setAttribute("lang", m.lang);
        root.innerHTML = P.render.render(m, a, this._config, this._ui);
      }

      _onClick(ev) {
        const path = ev.composedPath ? ev.composedPath() : [ev.target];
        for (const el of path) {
          if (!el || !el.getAttribute) continue;
          const act = el.getAttribute("data-act");
          if (!act) continue;
          if (act === "tab") this._ui.tab = el.getAttribute("data-tab");
          else if (act === "todo") this._ui.tab = "advice";
          else if (act === "range") this._ui.range = el.getAttribute("data-range");
          else if (act === "adv") this._ui.adv = !this._ui.adv;
          else if (act === "help") this._ui.help = !this._ui.help;
          else if (act === "bucket") {
            const k = el.getAttribute("data-key");
            this._ui.bucket = this._ui.bucket === k ? null : k;
          } else continue;
          return this._draw();
        }
      }
    }

    const LABELS = {
      device_id: "Heat pump (when you have several)", title: "Title", default_tab: "Tab shown first",
      range: "Live graphs: time range", tabs: "Tabs", language: "Language", show_help: "Show help",
      min_flow: "Minimum flow of your unit (l/min, from the installation manual)",
      target_dt: "Target ΔT of your installation (K, set by your installer; Daikin default 5)",
    };

    class DaikinEfficiencyCardEditor extends HTMLElement {
      setConfig(config) { this._config = Object.assign({}, config); this._render(); }

      set hass(hass) { this._hass = hass; this._render(); }

      _schema() {
        const opt = (v, l) => ({ value: v, label: l });
        const tabs = P.render.TABS.map((k) => opt(k, P.i18n.en["tab_" + k]));
        return [
          { name: "device_id", selector: { device: { integration: D.DOMAIN } } },
          { name: "title", selector: { text: {} } },
          { name: "default_tab", selector: { select: { mode: "dropdown", options: tabs } } },
          { name: "range", selector: { select: { mode: "dropdown", options: Object.keys(D.RANGES).map((r) => opt(r, r)) } } },
          { name: "tabs", selector: { select: { multiple: true, options: tabs } } },
          { name: "language", selector: { select: { mode: "dropdown", options: [opt("", "Auto (Home Assistant)"), opt("en", "English"), opt("nl", "Nederlands"), opt("fr", "Français")] } } },
          { name: "show_help", selector: { boolean: {} } },
          { name: "min_flow", selector: { number: { min: 0, max: 100, step: 0.5, mode: "box", unit_of_measurement: "l/min" } } },
          { name: "target_dt", selector: { number: { min: 2, max: 15, step: 0.5, mode: "box", unit_of_measurement: "K" } } },
        ];
      }

      _render() {
        if (!this._config || !this._hass) return;
        if (!this._form) {
          this._form = document.createElement("ha-form");
          this._form.computeLabel = (s) => LABELS[s.name] || s.name;
          this._form.addEventListener("value-changed", (ev) => {
            const cfg = Object.assign({}, ev.detail.value);
            for (const k of Object.keys(cfg)) {
              if (cfg[k] === "" || cfg[k] === undefined || cfg[k] === null || (Array.isArray(cfg[k]) && !cfg[k].length)) delete cfg[k];
            }
            if (cfg.show_help === true) delete cfg.show_help;
            this._config = cfg;
            this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: cfg }, bubbles: true, composed: true }));
          });
          this.appendChild(this._form);
        }
        this._form.hass = this._hass;
        this._form.schema = this._schema();
        this._form.data = Object.assign({ show_help: true }, this._config);
      }
    }

    customElements.define(TAG, DaikinEfficiencyCard);
    if (!customElements.get(EDITOR_TAG)) customElements.define(EDITOR_TAG, DaikinEfficiencyCardEditor);
    window.DaikinEfficiencyCard = { version: CARD_VERSION, parts: P, Card: DaikinEfficiencyCard };
    if (!window.__dcmEffCardLogged) {
      window.__dcmEffCardLogged = true;
      console.info(`%c DAIKIN-EFFICIENCY-CARD %c ${CARD_VERSION} `,
        "color:#fff;background:#0097E0;font-weight:700", "color:#0097E0;background:#fff;font-weight:700");
    }
  }

  window.customCards = window.customCards || [];
  if (!window.customCards.some((c) => c.type === TAG)) {
    window.customCards.push({
      type: TAG,
      name: "Daikin Cycle ML · Efficiency",
      description: "Live COP, setpoint tracker, water / compressor / flow / comfort graphs, heating curve and advice, with a verdict on every graph.",
      preview: true,
      documentationURL: "https://github.com/elRadix/daikin_cycle_ml/tree/main/dashboard/cards/daikin-efficiency-card",
    });
  }
  window.__dcmEffBoot = define;
  define();
})();
