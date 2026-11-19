class DaikinDailySummaryCard extends HTMLElement {
  setConfig(config) {
    this.config = config;
    this.activeTab = config.default_tab || 'overview';
  }

  set hass(hass) {
    this._hass = hass;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: 'open' });
      this.render();
    }
  }

  getCardSize() { return 8; }

  render() {
    const tabs = ['overview', 'quality', 'cycles', 'duration', 'events'];
    const tabLabels = {
      overview: 'Overview', quality: 'Quality', cycles: 'Cycles',
      duration: 'Duration', events: 'Events'
    };

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        ha-card { padding: 16px; border-radius: 12px; font-family: var(--paper-font-body1_-_font-family); }
        .tabs { display: flex; gap: 8px; border-bottom: 1px solid var(--divider-color); margin-bottom: 16px; }
        .tab { padding: 8px 12px; cursor: pointer; border-radius: 8px 8px 0 0; color: var(--secondary-text-color); font-weight: 500; }
        .tab.active { background: var(--primary-background-color); color: var(--primary-text-color); border-bottom: 2px solid var(--primary-color); }
        .content { padding: 8px; min-height: 200px; }
      </style>
      <ha-card>
        <div class="tabs">
          ${tabs.map(t => `<div class="tab ${t === this.activeTab ? 'active' : ''}" data-tab="${t}">${tabLabels[t]}</div>`).join('')}
        </div>
        <div class="content">
          <p>Tab content for <strong>${this.activeTab}</strong> will go here.</p>
          <p style="color: var(--secondary-text-color); font-size: 0.9em;">Entities loaded: ${Object.keys(this._hass?.states || {}).length}</p>
        </div>
      </ha-card>
    `;

    this.shadowRoot.querySelectorAll('.tab').forEach(el => {
      el.addEventListener('click', (e) => {
        this.activeTab = e.target.dataset.tab;
        this.render();
      });
    });
  }
}
customElements.define('daikin-daily-summary-card', DaikinDailySummaryCard);
