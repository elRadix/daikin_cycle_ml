"""Diagnostics export from the native cards.

Home Assistant's "Download diagnostics" file also lists every other custom
integration of the install (custom_components, integration_manifest,
setup_times): hundreds of lines on an install with many integrations. Each
native card now has a row "Diagnostics for a bug report: Download / Copy"
that fetches the same file through Home Assistant's API, for the entry of the
heat pump it shows, and drops those three blocks.
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

FRONT = Path(__file__).resolve().parent.parent / "custom_components/daikin_cycle_ml/frontend"
CARDS = ["daikin-daily-summary-card.js", "daikin-efficiency-card.js", "daikin-performance-card.js", "daikin-reports-card.js"]
BLOCK = re.compile(r"  /\* DCM-DIAG:BEGIN.*?/\* DCM-DIAG:END \*/\n", re.S)

BROWSER = r"""
const { chromium } = require('playwright'); const fs = require('fs');
const D = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
  const b = await chromium.launch(); const out = {};
  for (const c of D.cards) {
    const p = await b.newPage({ viewport: { width: 480, height: 900 } });
    const errors = []; p.on('pageerror', (e) => errors.push(e.message));
    await p.setContent('<html><body><div id="c"></div></body></html>');
    await p.addScriptTag({ content: "customElements.define('ha-card', class extends HTMLElement {});customElements.define('ha-form', class extends HTMLElement {});" });
    for (const f of c.files) await p.addScriptTag({ content: fs.readFileSync(f, 'utf8') });
    out[c.tag] = await p.evaluate(async (c) => {
      const N = Date.parse(c.now || '2026-11-19T14:00:00+01:00'); Date.now = () => N;
      const wait = (ms) => new Promise((r) => setTimeout(r, ms));
      const res = { api: [], copied: null, saved: null, name: null };
      Object.defineProperty(navigator, 'clipboard', { value: { writeText: async (t) => { res.copied = t; } }, configurable: true });
      URL.createObjectURL = (blob) => { res.blob = blob; return 'blob:x'; };
      HTMLAnchorElement.prototype.click = function () { res.name = this.download; };
      const raw = { home_assistant: { version: '2026.11.2' }, custom_components: { a: {}, b: {} }, integration_manifest: { domain: 'daikin_cycle_ml' },
        setup_times: { x: 1 }, data: { source: { attributes: {} } } };
      const entities = {}; for (const [id, e] of Object.entries(c.entities || {})) entities[id] = Object.assign({}, e, { device_id: 'dev1' });
      const el = document.createElement(c.tag); el.setConfig(c.config || {});
      document.getElementById('c').appendChild(el);
      el.hass = { states: c.states, entities, devices: { dev1: { config_entries: ['entry_9'] } }, language: 'nl', locale: { language: 'nl' },
        callWS: async () => c.history || {}, callService: async () => {},
        callApi: async (method, path) => { res.api.push([method, path]); return raw; } };
      await wait(150);
      const R = el.shadowRoot, btn = (k) => R.querySelector(`[data-diag="${k}"]`);
      res.label = btn('save') ? btn('save').parentElement.parentElement.textContent : null;
      btn('copy').click(); await wait(50);
      res.msgCopy = R.querySelector('[role="status"]').textContent;
      btn('save').click(); await wait(50);
      res.saved = res.blob ? await res.blob.text() : null;
      res.msgSave = R.querySelector('[role="status"]').textContent;
      el.hass = Object.assign({}, el.hass, { callApi: async () => { throw new Error('401 Unauthorized'); } });
      await wait(30); btn('copy').click(); await wait(50);
      res.msgFail = R.querySelector('[role="status"]').textContent;
      el.hass = Object.assign({}, el.hass, { devices: {} });
      await wait(30); btn('save').click(); await wait(50);
      res.msgNoEntry = R.querySelector('[role="status"]').textContent;
      return res;
    }, c);
    out[c.tag].errors = errors; await p.close();
  }
  await b.close(); process.stdout.write(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
"""


def test_every_native_card_carries_the_same_export_block():
    blocks = [BLOCK.findall((FRONT / f).read_text(encoding="utf-8")) for f in CARDS]
    assert all(len(b) == 1 for b in blocks) and len({b[0] for b in blocks}) == 1


@pytest.mark.skipif(not _playwright(), reason="playwright (node) not installed")
def test_download_and_copy_without_the_list_of_other_integrations():
    cards = [
        {"tag": "daikin-daily-summary-card", "files": [str(FRONT / "daikin-daily-summary-card.js")], **daily_fixture("nl")},
        {"tag": "daikin-efficiency-card", "files": [str(FRONT / f) for f in EFF_ORDER], **eff_case("nl")},
        {"tag": "daikin-performance-card", "files": [str(FRONT / f) for f in PERF_FILES], **_with_profile(eff_case("nl"))},
    ]
    proc = subprocess.run(["node", "-e", BROWSER], capture_output=True, text=True, timeout=300, check=False,
                          input=json.dumps({"cards": cards}))
    assert proc.returncode == 0, proc.stderr
    for tag, r in json.loads(proc.stdout).items():
        assert r["errors"] == [], (tag, r["errors"])
        assert "Diagnose voor een foutmelding" in r["label"], tag
        assert r["api"][:2] == [["GET", "diagnostics/config_entry/entry_9"]] * 2, (tag, r["api"])
        for text in (r["copied"], r["saved"]):
            doc = json.loads(text)
            assert set(doc) == {"home_assistant", "data"}, tag          # the three HA blocks are gone
        assert r["name"] == "daikin_cycle_ml_diagnostics.json", tag
        assert r["msgCopy"].startswith("Gekopieerd") and r["msgSave"].startswith("Opgeslagen"), tag
        assert r["msgFail"] == "Niet beschikbaar: 401 Unauthorized", tag
        assert r["msgNoEntry"].startswith("Geen Daikin Cycle ML-installatie"), tag
