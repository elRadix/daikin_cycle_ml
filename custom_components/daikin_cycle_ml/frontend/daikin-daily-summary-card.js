class DaikinDailySummaryCard extends HTMLElement {
 setConfig(config) {
 this.config = config;
 this.activeTab = config.default_tab || 'overview';
 this._initialized = false;
 this._hass = null;
 }

 set hass(hass) {
 this._hass = hass;
 if (!this._initialized) {
 this.attachShadow({ mode: 'open' });
 this._renderShell();
 this._initialized = true;
 }
 this._updateContent();
 }

 getCardSize() { return 8; }

 _getState(entityId, fallback = '—') {
 if (!this._hass || !this._hass.states[entityId]) return fallback;
 const state = this._hass.states[entityId].state;
 return (state === 'unavailable' || state === 'unknown') ? fallback : state;
 }

 _getAttr(entityId, attr, fallback = '—') {
 if (!this._hass || !this._hass.states[entityId]) return fallback;
 const val = this._hass.states[entityId].attributes[attr];
 return val !== undefined ? val : fallback;
 }

 _renderShell() {
 const tabs = ['overview', 'quality', 'cycles', 'duration', 'events'];
 const tabLabels = {
 overview: 'Overview', quality: 'Quality', cycles: 'Cycles',
 duration: 'Duration', events: 'Events'
 };

 this.shadowRoot.innerHTML = `
 <style>
 :host { display: block; }
 ha-card { padding: 16px; border-radius: 12px; font-family: var(--paper-font-body1_-_font-family); }
 .tabs { display: flex; gap: 8px; border-bottom: 1px solid var(--divider-color); margin-bottom: 16px; overflow-x: auto; }
 .tab { padding: 8px 12px; cursor: pointer; border-radius: 8px 8px 0 0; color: var(--secondary-text-color); font-weight: 500; white-space: nowrap; }
 .tab.active { background: var(--primary-background-color); color: var(--primary-text-color); border-bottom: 2px solid var(--primary-color); }
 .content { padding: 8px; min-height: 200px; }
 .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
 .metric { background: var(--secondary-background-color); padding: 12px; border-radius: 8px; }
 .metric-title { font-size: 0.85em; color: var(--secondary-text-color); text-transform: uppercase; letter-spacing: 0.5px; }
 .metric-value { font-size: 1.4em; font-weight: bold; margin-top: 4px; }
 .status-list { display: flex; flex-direction: column; gap: 8px; }
 .status-item { display: flex; justify-content: space-between; padding: 8px; background: var(--secondary-background-color); border-radius: 6px; }
 .status-on { color: var(--success-color); font-weight: bold; }
 .status-off { color: var(--disabled-text-color); }
 </style>
 <ha-card>
 <div class="tabs">
 ${tabs.map(t => `<div class="tab ${t === this.activeTab ? 'active' : ''}" data-tab="${t}">${tabLabels[t]}</div>`).join('')}
 </div>
 <div class="content" id="content"></div>
 </ha-card>
 `;

 this.shadowRoot.querySelectorAll('.tab').forEach(el => {
 el.addEventListener('click', (e) => {
 this.activeTab = e.currentTarget.dataset.tab;
 this.shadowRoot.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
 e.currentTarget.classList.add('active');
 this._updateContent();
 });
 });
 }

 _updateContent() {
 if (!this._initialized || !this._hass) return;
 const content = this.shadowRoot.getElementById('content');
 if (!content) return;

 let html = '';
 switch (this.activeTab) {
 case 'overview':
 html = `
 <div class="grid">
 <div class="metric"><div class="metric-title">COP Today</div><div class="metric-value">${this._getState('sensor.daikin_cycle_ml_cop_today')}</div></div>
 <div class="metric"><div class="metric-title">Cycles Today</div><div class="metric-value">${this._getState('sensor.daikin_cycle_ml_cycles_today')}</div></div>
 <div class="metric"><div class="metric-title">Thermal Power</div><div class="metric-value">${this._getState('sensor.daikin_cycle_ml_thermal_power_live')} kW</div></div>
 <div class="metric"><div class="metric-title">Quality Score</div><div class="metric-value">${this._getState('sensor.daikin_cycle_ml_quality_today')}</div></div>
 </div>`;
 break;
 case 'quality':
 html = `
 <div class="grid">
 <div class="metric"><div class="metric-title">COP vs Datasheet</div><div class="metric-value">${this._getState('sensor.daikin_cycle_ml_cop_vs_datasheet_pct')}%</div></div>
 <div class="metric"><div class="metric-title">COP Trend 30d</div><div class="metric-value">${this._getState('sensor.daikin_cycle_ml_cop_trend_30d')}</div></div>
 <div class="metric"><div class="metric-title">SPF YTD</div><div class="metric-value">${this._getState('sensor.daikin_cycle_ml_spf_ytd')}</div></div>
 <div class="metric"><div class="metric-title">SCOP Running</div><div class="metric-value">${this._getState('sensor.daikin_cycle_ml_scop_running_365d')}</div></div>
 </div>`;
 break;
 case 'cycles':
 html = `
 <div class="grid">
 <div class="metric"><div class="metric-title">Cycle State</div><div class="metric-value">${this._getState('sensor.daikin_cycle_ml_cycle_state')}</div></div>
 <div class="metric"><div class="metric-title">Short Runs</div><div class="metric-value">${this._getState('sensor.daikin_cycle_ml_short_run')}</div></div>
 <div class="metric"><div class="metric-title">Pendulum (Daily)</div><div class="metric-value">${this._getState('sensor.daikin_cycle_ml_pendulum_daily')}</div></div>
 <div class="metric"><div class="metric-title">Last Cycle Duration</div><div class="metric-value">${this._getAttr('sensor.daikin_cycle_ml_last_cycle', 'duration_min', '—')} min</div></div>
 </div>`;
 break;
 case 'duration':
 html = `
 <div class="grid">
 <div class="metric"><div class="metric-title">Heating Energy Today</div><div class="metric-value">${this._getState('sensor.daikin_cycle_ml_thermal_energy_heating_today')} kWh</div></div>
 <div class="metric"><div class="metric-title">Compressor Runtime</div><div class="metric-value">${this._getAttr('sensor.daikin_cycle_ml_current_cycle', 'runtime_min', '—')} min</div></div>
 <div class="metric"><div class="metric-title">High Cycle Rate</div><div class="metric-value">${this._getState('sensor.daikin_cycle_ml_high_cycle_rate')}</div></div>
 <div class="metric"><div class="metric-title">Daily Summary</div><div class="metric-value">${this._getState('sensor.daikin_cycle_ml_daily_summary_recent')}</div></div>
 </div>`;
 break;
 case 'events':
 const status = (id, label) => {
 const val = this._getState(id, 'off');
 const isOn = val.toLowerCase() === 'on' || val === 'True' || val === '1';
 return `<div class="status-item"><span>${label}</span><span class="${isOn ? 'status-on' : 'status-off'}">${val.toUpperCase()}</span></div>`;
 };
 html = `
 <div class="status-list">
 ${status('sensor.daikin_cycle_ml_heating_active', 'Heating')}
 ${status('sensor.daikin_cycle_ml_dhw_active', 'DHW')}
 ${status('sensor.daikin_cycle_ml_defrost_active', 'Defrost')}
 ${status('sensor.daikin_cycle_ml_buh_active', 'Backup Heater')}
 ${status('sensor.daikin_cycle_ml_compressor_running', 'Compressor')}
 </div>`;
 break;
 }
 content.innerHTML = html;
 }
}
customElements.define('daikin-daily-summary-card', DaikinDailySummaryCard);
