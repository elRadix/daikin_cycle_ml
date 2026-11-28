"""#488: a sensor update must not rebuild the native cards.

Every redraw replaced the whole card (root.innerHTML), so on a phone the
page jumped back to the top on every update, a table scrolled sideways
went back to its start, the tapped tab lost the focus and a number being
typed in the Performance card was wiped. The cards now patch only the
nodes that changed (dcmPatch, the same block in every card file).

Chromium mounts each card with the states of the real integration, opens
the advanced view, scrolls, types, then sends an update in which every
entity changed (new last_updated) and checks that the nodes, the scroll
position, the focus and the typed value survive, and that the patched
card equals a card drawn from scratch with the same states.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from tests.test_467_performance_card import FILES as PERF_FILES
from tests.test_467_performance_card import _with_profile
from tests.test_daily_summary_native_card import _fixture as daily_fixture
from tests.test_efficiency_native_card import ORDER as EFF_ORDER
from tests.test_efficiency_native_card import _case as eff_case
from tests.test_native_cards_responsive import _playwright

ROOT = Path(__file__).resolve().parent.parent
FRONT = ROOT / "custom_components/daikin_cycle_ml/frontend"
CARDS = ["daikin-daily-summary-card.js", "daikin-efficiency-card.js", "daikin-performance-card.js", "daikin-reports-card.js"]
BLOCK = re.compile(r"  /\* DCM-PATCH:BEGIN.*?/\* DCM-PATCH:END \*/\n", re.S)

BROWSER = r"""
const { chromium } = require('playwright'); const fs = require('fs');
const D = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
  const b = await chromium.launch(); const out = {};
  for (const c of D.cards) {
    const p = await b.newPage({ viewport: { width: 390, height: 700 } });
    const errors = []; p.on('pageerror', (e) => errors.push(e.message));
    /* a scroller without scroll anchoring, as on iOS Safari */
    await p.setContent('<html><body style="margin:0"><div id="s" style="height:700px;overflow:auto;overflow-anchor:none">'
      + '<div id="c"></div><div id="f"></div><div style="height:1500px"></div></div></body></html>');
    await p.addScriptTag({ content: "customElements.define('ha-card', class extends HTMLElement { connectedCallback(){ this.style.display='block'; } });"
      + "customElements.define('ha-form', class extends HTMLElement {});" });
    for (const f of c.files) await p.addScriptTag({ content: fs.readFileSync(f, 'utf8') });
    out[c.tag] = await p.evaluate(async (c) => {
      const N = Date.parse(c.now || '2026-11-19T14:00:00+01:00'); Date.now = () => N;
      const wait = (ms) => new Promise((r) => setTimeout(r, ms));
      const hass = (states) => ({ states, entities: c.entities, language: 'nl', locale: { language: 'nl' },
        callWS: async () => c.history || {}, callService: async () => {} });
      const mount = async (host, states) => {
        const el = document.createElement(c.tag); el.style.display = 'block'; el.setConfig(c.config || {});
        document.getElementById(host).appendChild(el); el.hass = hass(states); await wait(150); return el;
      };
      const el = await mount('c', c.states), R = el.shadowRoot;
      const adv = R.querySelector('[data-act="adv"]'); if (adv) adv.click();
      const prof = R.querySelector('[data-act="prof"]'); if (prof) prof.click();
      const tab = R.querySelector('[data-tab]'); if (tab) tab.focus();
      const typed = R.getElementById('new-t'); if (typed) typed.value = '-7';
      const s = document.getElementById('s'); s.scrollTop = 400;
      const first = R.querySelector('#root > *'), nodes = R.querySelectorAll('#root *').length;
      const st = {}; for (const [k, v] of Object.entries(c.states)) st[k] = Object.assign({}, v, { last_updated: 'u' + k });
      el.hass = hass(st); await wait(50);
      const fresh = await mount('f', st);
      for (const [sel, a] of [['[data-act="adv"]', adv], ['[data-act="prof"]', prof], ['[data-tab]', tab]]) {
        if (a) { const t = fresh.shadowRoot.querySelector(sel); if (t) t.click(); }
      }
      await wait(50);
      const html = (r) => r.getElementById('root').innerHTML;
      return {
        kept: first === R.querySelector('#root > *'), nodes: nodes > 20,
        scroll: s.scrollTop, focus: !tab || R.activeElement === tab,
        typed: typed ? R.getElementById('new-t').value : null,
        same: html(R) === html(fresh.shadowRoot),
      };
    }, c);
    out[c.tag].errors = errors; await p.close();
  }
  await b.close(); process.stdout.write(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
"""


def test_every_native_card_carries_the_same_patch_block():
    blocks = [BLOCK.findall((FRONT / f).read_text(encoding="utf-8")) for f in CARDS]
    assert all(len(b) == 1 for b in blocks)
    assert len({b[0] for b in blocks}) == 1
    for f in CARDS:
        src = (FRONT / f).read_text(encoding="utf-8")
        assert "root.innerHTML" not in src and src.count("dcmPatch(root, ") == 2, f      # the block + the draw


@pytest.mark.skipif(not _playwright(), reason="playwright (node) not installed")
def test_update_keeps_nodes_scroll_focus_and_typed_value():
    cards = [
        {"tag": "daikin-daily-summary-card", "files": [str(FRONT / "daikin-daily-summary-card.js")], **daily_fixture("nl")},
        {"tag": "daikin-efficiency-card", "files": [str(FRONT / f) for f in EFF_ORDER], **eff_case("nl")},
        {"tag": "daikin-performance-card", "files": [str(FRONT / f) for f in PERF_FILES], **_with_profile(eff_case("nl"))},
    ]
    proc = subprocess.run(["node", "-e", BROWSER], capture_output=True, text=True, timeout=300, check=False,
                          input=json.dumps({"cards": cards}))
    assert proc.returncode == 0, proc.stderr
    res = json.loads(proc.stdout)
    for tag, r in res.items():
        assert r["errors"] == [], (tag, r["errors"])
        assert r["kept"] and r["nodes"], tag           # the card was patched, not rebuilt
        assert r["scroll"] == 400, tag                 # the page stays where it was
        assert r["focus"], tag                         # the tapped tab keeps the focus
        assert r["same"], tag                          # and shows what a fresh card shows
    assert res["daikin-performance-card"]["typed"] == "-7"   # a number being typed survives
