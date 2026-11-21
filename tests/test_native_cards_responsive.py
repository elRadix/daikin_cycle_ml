"""All native cards on phone, tablet and desktop widths.

Chromium mounts each card with the states of the real integration at
360 / 390 (phone), 768 / 1024 (tablet) and 1280 / 1920 (desktop) px and
checks that nothing sticks out of the card (only content inside its own
scroll container, such as a wide table, may), that there are no script
errors, and that every tab renders. Screenshots land in the temp folder
to look at (R402); they are not committed.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from tests.test_daily_summary_native_card import _fixture as daily_fixture
from tests.test_efficiency_native_card import ORDER as EFF_ORDER
from tests.test_efficiency_native_card import _case as eff_case
from tests.test_467_performance_card import FILES as PERF_FILES
from tests.test_467_performance_card import _with_profile

ROOT = Path(__file__).resolve().parent.parent
FRONT = ROOT / "custom_components/daikin_cycle_ml/frontend"
SHOTS = Path(tempfile.gettempdir()) / "dcm-responsive"
WIDTHS = [360, 390, 768, 1024, 1280, 1920]

BROWSER = r"""
const { chromium } = require('playwright'); const fs = require('fs');
const D = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
  const b = await chromium.launch();
  const out = {};
  for (const card of D.cards) {
    for (const w of D.widths) {
      const p = await b.newPage({ viewport: { width: w, height: 900 } });
      const errors = []; p.on('pageerror', (e) => errors.push(e.message));
      await p.setContent('<html><body style="margin:0;font-family:Roboto,Arial"><div id="c" style="padding:8px"></div></body></html>');
      await p.addScriptTag({ content: "customElements.define('ha-card', class extends HTMLElement { connectedCallback(){ this.style.display='block'; } });"
        + "customElements.define('ha-form', class extends HTMLElement {});" });
      for (const f of card.files) await p.addScriptTag({ content: fs.readFileSync(f, 'utf8') });
      const r = await p.evaluate(async (c) => {
        const N = Date.parse(c.now || '2026-11-19T14:00:00+01:00'); Date.now = () => N;
        const el = document.createElement(c.tag); el.style.display = 'block';
        el.setConfig(c.config || {});
        document.getElementById('c').appendChild(el);
        el.hass = { states: c.states, entities: c.entities, language: 'nl', locale: { language: 'nl' },
          callWS: async () => c.history || {}, callService: async () => {} };
        await new Promise((r) => setTimeout(r, 120));
        el.hass = Object.assign({}, el.hass);
        await new Promise((r) => setTimeout(r, 60));
        const R = el.shadowRoot, box = el.getBoundingClientRect(), bad = [];
        const scrolls = (n) => { for (let e = n.parentElement; e; e = e.parentElement) { const o = getComputedStyle(e).overflowX; if (o === 'auto' || o === 'scroll') return true; } return false; };
        const check = (label) => {
          for (const n of R.querySelectorAll('*')) {
            if (['STYLE', 'TITLE', 'DEFS', 'PATTERN'].includes(n.tagName.toUpperCase()) || scrolls(n)) continue;
            const rc = n.getBoundingClientRect();
            if (!rc.width && !rc.height) continue;
            if (rc.right > box.right + 1 || rc.left < box.left - 1) bad.push(label + ':' + (n.className && n.className.baseVal !== undefined ? n.className.baseVal : n.className || n.tagName));
          }
        };
        const tabs = [...R.querySelectorAll('[data-tab]')].map((t) => t.dataset.tab);
        check('first');
        for (const t of tabs) { const b = R.querySelector(`[data-tab="${t}"]`); if (b) { b.click(); await new Promise((r) => setTimeout(r, 20)); check(t); } }
        const prof = R.querySelector('[data-act="prof"]'); if (prof) { prof.click(); check('profile'); }
        return { bad: [...new Set(bad)].slice(0, 12), tabs: tabs.length, page: document.documentElement.scrollWidth - innerWidth };
      }, card);
      if ([390, 1024, 1920].includes(w)) await p.screenshot({ path: `${D.shots}/${card.tag}_${w}.png`, fullPage: true });
      r.errors = errors; out[card.tag + '@' + w] = r;
      await p.close();
    }
  }
  await b.close();
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
"""


def _playwright() -> bool:
    return bool(shutil.which("node")) and subprocess.run(
        ["node", "-e", "require('playwright')"], capture_output=True, check=False).returncode == 0


@pytest.mark.skipif(not _playwright(), reason="playwright (node) not installed")
def test_every_native_card_fits_phone_tablet_and_desktop():
    SHOTS.mkdir(exist_ok=True)
    eff = eff_case("nl")
    cards = [
        {"tag": "daikin-daily-summary-card", "files": [str(FRONT / "daikin-daily-summary-card.js")], **daily_fixture("nl")},
        {"tag": "daikin-efficiency-card", "files": [str(FRONT / f) for f in EFF_ORDER], **eff},
        {"tag": "daikin-performance-card", "files": [str(FRONT / f) for f in PERF_FILES], **_with_profile(eff_case("nl"))},
    ]
    proc = subprocess.run(["node", "-e", BROWSER], capture_output=True, text=True, timeout=600, check=False,
                          input=json.dumps({"cards": cards, "widths": WIDTHS, "shots": str(SHOTS)}))
    assert proc.returncode == 0, proc.stderr
    res = json.loads(proc.stdout)
    assert len(res) == 3 * len(WIDTHS)
    for key, r in res.items():
        assert r["errors"] == [], (key, r["errors"])
        assert r["bad"] == [], (key, r["bad"])          # nothing sticks out of the card
        assert r["page"] <= 0, key                       # the page never scrolls sideways
    assert res["daikin-daily-summary-card@390"]["tabs"] >= 2
    assert res["daikin-efficiency-card@390"]["tabs"] >= 2
