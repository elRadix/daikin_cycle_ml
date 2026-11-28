/*
 * Daikin Cycle ML — Reports card (native Lovelace card, #508).
 *
 *   type: custom:daikin-reports-card
 *
 * Week, month, year and heating-season reports per mode: COP, energy,
 * temperatures, flow, cycling, backup heater, defrost, alerts and ML
 * anomalies, compared with the previous period or the same period a year
 * earlier (energy per degree day, COP at the same outdoor temperature),
 * with a verdict per metric. The reports are stored by the integration for
 * good and read through the service daikin_cycle_ml.get_report.
 *
 * Options (all optional):
 *   device_id:   heat pump device (when you have several)
 *   title:       card title
 *   period_type: week | month | year | season (default month)
 *   mode:        all | heating | dhw | cooling (default all)
 *   compare:     previous | last_year | none (default previous)
 *   default_tab: overview | energy | temps | cycling | events | compare
 *   language:    '' (auto) | en | nl | fr
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

  /* DCM-DIAG:BEGIN (same block in every native card; tests/test_card_diagnostics_export.py)
   * Diagnostics for a bug report straight from the card: the same file as
   * Home Assistant's "Download diagnostics", without the list of every other
   * custom integration Home Assistant adds (custom_components,
   * integration_manifest, setup_times). Download, or copy to paste. */
  const DCM_DIAG_T = {
    en: { label: "Diagnostics for a bug report", save: "Download", copy: "Copy", busy: "Collecting…",
      saved: "Saved: daikin_cycle_ml_diagnostics.json", copied: "Copied: paste it into your issue",
      no_entry: "No Daikin Cycle ML entry found for this card.", failed: "Not available: {msg}" },
    nl: { label: "Diagnose voor een foutmelding", save: "Downloaden", copy: "Kopiëren", busy: "Verzamelen…",
      saved: "Opgeslagen: daikin_cycle_ml_diagnostics.json", copied: "Gekopieerd: plak het in je issue",
      no_entry: "Geen Daikin Cycle ML-installatie gevonden voor deze kaart.", failed: "Niet beschikbaar: {msg}" },
    fr: { label: "Diagnostic pour un rapport de bug", save: "Télécharger", copy: "Copier", busy: "Collecte…",
      saved: "Enregistré : daikin_cycle_ml_diagnostics.json", copied: "Copié : collez-le dans votre issue",
      no_entry: "Aucune installation Daikin Cycle ML trouvée pour cette carte.", failed: "Indisponible : {msg}" },
  };
  const DCM_DIAG_DROP = ["custom_components", "integration_manifest", "setup_times"];
  function dcmDiagEntry(hass, ids) {
    for (const id of Object.values(ids || {})) {
      const e = id && hass && hass.entities && hass.entities[id];
      const d = e && e.device_id && hass.devices && hass.devices[e.device_id];
      if (d && Array.isArray(d.config_entries) && d.config_entries.length) return d.config_entries[0];
    }
    return null;
  }
  function dcmDiagText(raw) {
    const out = Object.assign({}, raw);
    for (const k of DCM_DIAG_DROP) delete out[k];
    return JSON.stringify(out, null, 2);
  }
  async function dcmDiagRun(hass, entryId, how) {
    const text = dcmDiagText(await hass.callApi("GET", "diagnostics/config_entry/" + entryId));
    if (how === "copy") { await navigator.clipboard.writeText(text); return "copied"; }
    const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url; a.download = "daikin_cycle_ml_diagnostics.json";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return "saved";
  }
  function dcmDiagHtml(t, msg) {
    const b = "font:inherit;font-size:12px;min-height:32px;padding:4px 12px;border-radius:8px;cursor:pointer;"
      + "border:1px solid var(--divider-color,#ccc);background:var(--card-background-color,#fff);color:var(--primary-text-color)";
    const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    return `<div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:8px 16px 12px;font-size:12px;color:var(--secondary-text-color)">`
      + `<span>${esc(t.label)}</span><span style="display:flex;gap:8px">`
      + `<button type="button" data-diag="save" style="${b}">${esc(t.save)}</button>`
      + `<button type="button" data-diag="copy" style="${b}">${esc(t.copy)}</button></span>`
      + (msg ? `<span role="status">${esc(msg)}</span>` : "") + `</div>`;
  }
  /* mounts the row in box; info() -> { lang, ids }; returns the redraw */
  function dcmDiag(card, box, info) {
    let msg = "";
    const tr = () => DCM_DIAG_T[info().lang] || DCM_DIAG_T.en;
    const draw = () => dcmPatch(box, dcmDiagHtml(tr(), msg));
    box.addEventListener("click", async (ev) => {
      const path = ev.composedPath ? ev.composedPath() : [ev.target];
      const btn = path.find((n) => n && n.getAttribute && n.getAttribute("data-diag"));
      if (!btn) return;
      const t = tr(), entry = dcmDiagEntry(card._hass, info().ids);
      if (!entry) { msg = t.no_entry; draw(); return; }
      msg = t.busy; draw();
      try {
        msg = t[await dcmDiagRun(card._hass, entry, btn.getAttribute("data-diag"))];
      } catch (err) {
        msg = t.failed.replace("{msg}", (err && (err.message || (err.body && err.body.message))) || String(err));
      }
      draw();
    });
    return draw;
  }
  /* DCM-DIAG:END */

  const CARD_VERSION = "1.0.0";
  const TAG = "daikin-reports-card";
  const EDITOR_TAG = "daikin-reports-card-editor";
  const PARTS = ["model", "i18n", "render"];
  const P = (window.DaikinReportsCardParts = window.DaikinReportsCardParts || {});
  const REFRESH_MS = 15 * 60 * 1000;   /* the current period grows: reload now and then */

  const STYLE = `
    :host { display: block; }
    ha-card { overflow: hidden; container-type: inline-size; }
    .head { display: flex; gap: 12px; align-items: center; padding: 14px 16px;
      background: linear-gradient(135deg, rgba(0,151,224,0.16), rgba(0,151,224,0.04)); border-bottom: 3px solid var(--dcm-accent, #0097E0); }
    .ic { width: 40px; height: 40px; border-radius: 10px; background: var(--dcm-accent, #0097E0); display: flex; align-items: center;
      justify-content: center; font-size: 20px; flex-shrink: 0; }
    .hm { min-width: 0; flex: 1; }
    .ht { font-weight: 800; text-transform: uppercase; letter-spacing: .6px; color: var(--primary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .hs { font-size: .82em; font-weight: 600; color: var(--secondary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .badge { border-radius: 12px; padding: 3px 10px; font-weight: 800; color: #10151a; white-space: nowrap; }
    .body { padding: 10px 14px 14px; color: var(--primary-text-color); display: grid; gap: 10px; min-width: 0; }
    .ctls { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
    .ctl { display: grid; gap: 3px; min-width: 0; }
    .ctl > span { font-size: .72em; font-weight: 700; color: var(--secondary-text-color); text-transform: uppercase; letter-spacing: .05em; }
    select { width: 100%; min-width: 0; min-height: 36px; font: inherit; font-size: .9em; padding: 4px 6px; border-radius: 8px;
      border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); }
    .stp { display: flex; gap: 4px; min-width: 0; }
    .nav { min-width: 32px; min-height: 36px; border-radius: 8px; border: 1px solid var(--divider-color); background: var(--card-background-color);
      color: var(--primary-text-color); font: inherit; font-weight: 800; cursor: pointer; }
    .nav[disabled] { opacity: .35; cursor: default; }
    .tabs { display: flex; gap: 4px; overflow-x: auto; scrollbar-width: none; border-bottom: 1px solid var(--divider-color); }
    .tabs::-webkit-scrollbar { display: none; }
    .tab { border: 0; background: none; font: inherit; font-size: .86em; font-weight: 700; padding: 8px 10px; min-height: 36px; cursor: pointer;
      color: var(--secondary-text-color); border-bottom: 3px solid transparent; white-space: nowrap; }
    .tab.on { color: var(--primary-text-color); border-bottom-color: var(--dcm-accent, #0097E0); }
    .tab:focus-visible, .nav:focus-visible, select:focus-visible { outline: 2px solid var(--dcm-accent, #0097E0); outline-offset: 1px; }
    .panel { display: grid; gap: 10px; min-width: 0; }
    .tiles { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
    .tile { background: var(--secondary-background-color); border-radius: 12px; padding: 8px 10px; min-width: 0; }
    .tk { font-size: .72em; font-weight: 700; color: var(--secondary-text-color); text-transform: uppercase; letter-spacing: .05em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .tv { font-size: 1.35em; font-weight: 800; font-variant-numeric: tabular-nums; }
    .tv small { font-size: .55em; font-weight: 700; color: var(--secondary-text-color); }
    .chg { display: inline-block; font-size: .76em; font-weight: 800; border-radius: 999px; padding: 1px 7px; font-variant-numeric: tabular-nums; white-space: nowrap; }
    .chg.g { background: rgba(67,160,71,.2); color: #2E7D32; } .chg.b { background: rgba(229,57,53,.18); color: #C62828; }
    .chg.n { background: rgba(142,142,147,.2); color: var(--secondary-text-color); }
    .vds { display: grid; gap: 6px; }
    .vd { display: grid; grid-template-columns: auto 1fr auto; gap: 8px; align-items: center; border-radius: 8px; padding: 6px 10px;
      background: var(--secondary-background-color); font-size: .88em; }
    .pill { font-weight: 800; color: #10151a; border-radius: 999px; padding: 1px 8px; font-size: .82em; white-space: nowrap; }
    .vv { font-weight: 700; font-variant-numeric: tabular-nums; white-space: nowrap; }
    .note { padding: 9px 12px; border-radius: 10px; background: var(--secondary-background-color); font-size: .86em; line-height: 1.35; }
    .note.err { border-left: 4px solid #E53935; }
    .muted { color: var(--secondary-text-color); font-size: .82em; }
    h4 { margin: 4px 0 0; font-size: .82em; text-transform: uppercase; letter-spacing: .05em; color: var(--secondary-text-color); }
    .kvs { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 6px 12px; }
    .kv { display: flex; justify-content: space-between; gap: 8px; border-bottom: 1px solid var(--divider-color); padding: 4px 0; font-size: .9em; min-width: 0; }
    .kv b { font-variant-numeric: tabular-nums; white-space: nowrap; }
    .tw { overflow-x: auto; }
    table { border-collapse: collapse; width: 100%; font-size: .86em; color: inherit; }
    th, td { text-align: left; padding: 4px 6px; border-bottom: 1px solid var(--divider-color); }
    th { font-size: .78em; color: var(--secondary-text-color); font-weight: 700; }
    td.r { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
    .chart { width: 100%; max-width: 560px; height: auto; max-height: 220px; display: block; margin: 0 auto; }
    .chart .ax { fill: var(--secondary-text-color); font-size: 9px; }
    .chart rect.hi { fill: var(--dcm-accent, #0097E0); }
    .lg { justify-content: center; display: flex; gap: 12px; flex-wrap: wrap; font-size: .76em; color: var(--secondary-text-color); }
    .lg i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 4px; vertical-align: -1px; }
    .chk { margin: 0; padding-left: 18px; font-size: .86em; }
    @container (max-width: 520px) {
      .ctls { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
  `;

  function define() {
    if (!PARTS.every((k) => P[k]) || customElements.get(TAG)) return;
    const M = P.model, R = P.render;

    class DaikinReportsCard extends HTMLElement {
      static getConfigElement() { return document.createElement(EDITOR_TAG); }

      static getStubConfig() { return { period_type: "month" }; }

      setConfig(config) {
        if (!config || typeof config !== "object") throw new Error("Invalid configuration");
        for (const [k, list] of [["period_type", M.TYPES], ["mode", M.MODES], ["compare", M.AGAINST], ["default_tab", M.TABS]]) {
          if (config[k] && !list.includes(config[k])) throw new Error(k + " must be one of: " + list.join(", "));
        }
        this._config = Object.assign({}, config);
        this._ui = {};
        this._resp = null;
        this._reqKey = null;
        this._draw();
      }

      set hass(hass) { this._hass = hass; this._maybeFetch(); this._draw(); }

      get hass() { return this._hass; }

      getCardSize() { return 9; }

      getGridOptions() { return { columns: 12, min_columns: 6, rows: "auto" }; }

      connectedCallback() {
        this._timer = setInterval(() => { this._reqKey = null; this._maybeFetch(); }, REFRESH_MS);
      }

      disconnectedCallback() { clearInterval(this._timer); }

      _maybeFetch() {
        if (!this._config || !this._hass) return;
        const ids = M.resolveEntities(this._hass, this._config);
        if (!ids.last_month_report) return;
        const entryId = M.entryOf(this._hass, ids);
        const data = M.request(entryId, this._config, this._ui);
        /* a new nightly build changes the sensor: reload then too */
        const st = this._hass.states[ids.last_month_report];
        const key = JSON.stringify(data) + "@" + ((st && st.last_updated) || "");
        if (key === this._reqKey) return;
        this._reqKey = key;
        this._fetch(data, key);
      }

      async _fetch(data, key) {
        this._ui.loading = true; this._ui.error = "";
        this._draw(true);
        try {
          const res = await this._hass.callWS({ type: "call_service", domain: M.DOMAIN, service: "get_report",
            service_data: data, return_response: true });
          if (key !== this._reqKey) return;            /* a newer request is on its way */
          this._resp = (res && res.response) || res || {};
          if (!this._ui.key && this._resp.key) this._ui.key = this._resp.key;
        } catch (err) {
          if (key !== this._reqKey) return;
          this._ui.error = (err && (err.message || (err.body && err.body.message))) || String(err);
        }
        this._ui.loading = false;
        this._draw(true);
      }

      _draw(force) {
        if (!this._config || !this._hass) return;
        if (!this.shadowRoot) {
          this.attachShadow({ mode: "open" });
          this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card><div id="root"></div></ha-card>`;
          const diagBox = document.createElement("div");
          this.shadowRoot.querySelector("ha-card").appendChild(diagBox);
          this._diagDraw = dcmDiag(this, diagBox, () => this._diagInfo || { lang: "en", ids: {} });
          this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
          this.shadowRoot.addEventListener("change", (ev) => this._onChange(ev));
        }
        const lang = (this._hass.locale && this._hass.locale.language) || this._hass.language || "";
        const sig = JSON.stringify(this._ui) + "#" + lang + "#" + (this._resp ? this._resp.key + this._resp.mode + this._resp.against : "-");
        if (!force && sig === this._sig) return;
        this._sig = sig;
        this._m = M.buildModel(this._hass, this._config, this._ui, this._resp);
        const root = this.shadowRoot.getElementById("root");
        root.setAttribute("lang", this._m.lang);
        dcmPatch(root, R.render(this._m, this._config));
        /* a patched <select> keeps its old choice: follow the selected option */
        for (const sel of root.querySelectorAll("select[data-ctl]")) {
          const opt = sel.querySelector("option[selected]");
          if (opt && sel.value !== opt.value) sel.value = opt.value;
        }
        this._diagInfo = { lang: this._m.lang, ids: this._m.ids };
        this._diagDraw();
      }

      _set(patch) {
        Object.assign(this._ui, patch);
        this._maybeFetch();
        this._draw(true);
      }

      _onClick(ev) {
        const path = ev.composedPath ? ev.composedPath() : [ev.target];
        for (const el of path) {
          if (!el || !el.getAttribute) continue;
          const tab = el.getAttribute("data-tab");
          if (tab) {
            this._set({ tab });
            /* phones: the tab row scrolls; keep the chosen tab in view */
            const on = this.shadowRoot.querySelector(".tab.on");
            if (on && on.scrollIntoView) on.scrollIntoView({ block: "nearest", inline: "nearest" });
            return;
          }
          const act = el.getAttribute("data-act");
          if ((act === "prev" || act === "next") && this._m) {
            const k = act === "prev" ? this._m.prevKey : this._m.nextKey;
            if (k) this._set({ key: k });
            return;
          }
        }
      }

      _onChange(ev) {
        const el = ev.target;
        const ctl = el && el.getAttribute && el.getAttribute("data-ctl");
        if (!ctl) return;
        /* another period type or mode: start at its newest period */
        if (ctl === "type") this._set({ type: el.value, key: null });
        else if (ctl === "key") this._set({ key: el.value });
        else this._set({ [ctl]: el.value });
      }
    }

    const LABELS = {
      device_id: "Heat pump (when you have several)", title: "Title", language: "Language",
      period_type: "Period", mode: "Mode", compare: "Compare with", default_tab: "Tab",
    };

    class DaikinReportsCardEditor extends HTMLElement {
      setConfig(config) { this._config = Object.assign({}, config); this._render(); }

      set hass(hass) { this._hass = hass; this._render(); }

      _schema() {
        const T = P.i18n.en, opt = (v, l) => ({ value: v, label: l });
        const sel = (list, labels) => ({ select: { mode: "dropdown", options: list.map((v) => opt(v, labels[v])) } });
        return [
          { name: "device_id", selector: { device: { integration: M.DOMAIN } } },
          { name: "title", selector: { text: {} } },
          { name: "period_type", selector: sel(M.TYPES, T.types) },
          { name: "mode", selector: sel(M.MODES, T.modes) },
          { name: "compare", selector: sel(M.AGAINST, T.against) },
          { name: "default_tab", selector: sel(M.TABS, T.tabs) },
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

    customElements.define(TAG, DaikinReportsCard);
    if (!customElements.get(EDITOR_TAG)) customElements.define(EDITOR_TAG, DaikinReportsCardEditor);
    window.DaikinReportsCard = { version: CARD_VERSION, parts: P, Card: DaikinReportsCard };
    if (!window.__dcmReportsCardLogged) {
      window.__dcmReportsCardLogged = true;
      console.info(`%c DAIKIN-REPORTS-CARD %c ${CARD_VERSION} `,
        "color:#fff;background:#0097E0;font-weight:700", "color:#0097E0;background:#fff;font-weight:700");
    }
  }

  window.customCards = window.customCards || [];
  if (!window.customCards.some((c) => c.type === TAG)) {
    window.customCards.push({
      type: TAG,
      name: "Daikin Cycle ML · Reports",
      description: "Week, month, year and heating-season reports: COP, energy, temperatures, cycling and events, compared with the previous period or last year.",
      preview: true,
      documentationURL: "https://github.com/elRadix/daikin_cycle_ml/tree/main/dashboard/cards/daikin-reports-card",
    });
  }
  window.__dcmReportsBoot = define;
  define();
})();
