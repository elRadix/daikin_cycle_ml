"""Performance card: saving the model profile names the config entry.

With three Daikin Cycle ML entries set up, every save from the card failed
("3 Daikin Cycle ML integrations are set up: choose one with entry_id"):
the card called set_model_profile without entry_id. It now passes the entry
of the heat pump it shows (entity -> device -> config entry).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_467_performance_card import FILES

FRONT = Path(__file__).resolve().parent.parent / "custom_components/daikin_cycle_ml/frontend"

RUNNER = r"""
const vm = require('vm'); const fs = require('fs');
const D = JSON.parse(fs.readFileSync(0, 'utf8')); const win = {};
const ctx = vm.createContext({ window: win, Intl, Date, Math, JSON, Object, Array, String, Number, Set, Promise,
  parseFloat, isFinite, RegExp, Error, console: { info() {} }, HTMLElement: class {}, CustomEvent: class {}, document: {},
  customElements: { _d: {}, get(n) { return this._d[n]; }, define(n, c) { this._d[n] = c; } } });
for (const f of D.files) vm.runInContext(fs.readFileSync(f, 'utf8'), ctx, { filename: f });
const M = win.DaikinPerformanceCardParts.model, Card = ctx.customElements._d['daikin-performance-card'];
const hass = (devices) => ({ states: { 'sensor.daikin_cycle_ml_hp_specs': { state: 'epra12eav3', attributes: {} } },
  entities: { 'sensor.daikin_cycle_ml_hp_specs': { platform: 'daikin_cycle_ml', translation_key: 'hp_specs', device_id: 'dev1' } },
  devices, language: 'en' });
(async () => {
  const out = {
    entry: M.entryOf(hass({ dev1: { config_entries: ['entry_b'] } }), 'sensor.daikin_cycle_ml_hp_specs'),
    noDevice: M.entryOf(hass({}), 'sensor.daikin_cycle_ml_hp_specs'),
    noEntity: M.entryOf(hass({}), null),
    calls: [],
  };
  for (const entryId of ['entry_b', null]) {
    const el = new Card();
    el._ui = { msg: '' }; el._draw = () => {};
    el._m = { lang: 'en', entryId };
    el._hass = { callService: async (d, s, data) => out.calls.push([d, s, data]) };
    await el._save({ fields: { rps_min: 8 } });
  }
  process.stdout.write(JSON.stringify(out));
})();
"""


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_save_names_the_entry_of_the_shown_heat_pump():
    proc = subprocess.run(["node", "-e", RUNNER], capture_output=True, text=True, timeout=60, check=False,
                          input=json.dumps({"files": [str(FRONT / f) for f in FILES]}))
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["entry"] == "entry_b" and out["noDevice"] is None and out["noEntity"] is None
    assert out["calls"] == [
        ["daikin_cycle_ml", "set_model_profile", {"entry_id": "entry_b", "fields": {"rps_min": 8}}],
        ["daikin_cycle_ml", "set_model_profile", {"fields": {"rps_min": 8}}],   # one entry: no id needed
    ]
