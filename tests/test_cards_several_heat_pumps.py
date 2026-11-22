"""Native cards on one Home Assistant with several heat pumps.

One HA can serve several Daikin Cycle ML entries (one heat pump each). A
card without device_id looked every role up on its own, so one card could
show the hot-water state of one heat pump next to the COP of another. Every
role now comes from one device (the first found), or, without the entity
registry, from one entity-id prefix; device_id still picks the heat pump.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_467_performance_card import FILES as PERF
from tests.test_efficiency_native_card import ORDER as EFF

FRONT = Path(__file__).resolve().parent.parent / "custom_components/daikin_cycle_ml/frontend"
DAILY = ["daikin-daily-summary-card.js"]

RUNNER = r"""
const vm = require('vm'); const fs = require('fs');
const D = JSON.parse(fs.readFileSync(0, 'utf8'));
const load = (files) => {
  const win = {};
  const ctx = vm.createContext({ window: win, Intl, Date, Math, JSON, Object, Array, String, Number, Set, Promise,
    parseFloat, isFinite, RegExp, Error, console: { info() {}, debug() {} }, HTMLElement: class {}, CustomEvent: class {},
    document: {}, setInterval: () => 0, clearInterval: () => 0,
    customElements: { _d: {}, get(n) { return this._d[n]; }, define(n, c) { this._d[n] = c; } } });
  for (const f of files) vm.runInContext(fs.readFileSync(f, 'utf8'), ctx, { filename: f });
  return win;
};
const resolvers = {
  efficiency: load(D.eff).DaikinEfficiencyCardParts.data.resolveEntities,
  performance: load(D.perf).DaikinPerformanceCardParts.model.resolveEntities,
  daily: load(D.daily).DaikinDailySummaryCard.resolveEntities,
};
/* three heat pumps; the registry lists hp_specs of the second one first */
const roles = ['hp_specs', 'cycle_state', 'daily_summary_recent', 'thermal_power_live', 'compressor_running', 'dhw_active'];
const houses = [['dev_a', 'a_daikin_cycle_ml'], ['dev_b', 'b_daikin_cycle_ml'], ['dev_c', 'c_daikin_cycle_ml']];
const entities = {}, states = {};
const add = (dev, obj, role) => {
  const pre = ['compressor_running', 'dhw_active'].includes(role) ? 'binary_sensor.' : 'sensor.';
  const id = pre + obj + '_' + role;
  entities[id] = { platform: 'daikin_cycle_ml', translation_key: role, device_id: dev };
  states[id] = { state: '1', attributes: {} };
};
add('dev_b', 'b_daikin_cycle_ml', 'hp_specs');
for (const role of roles) for (const [dev, obj] of houses) if (!(dev === 'dev_b' && role === 'hp_specs')) add(dev, obj, role);
/* without the registry, entity ids interleave across the three prefixes */
const statesOnly = {};
for (const role of roles) for (const [, obj] of [houses[2], houses[0], houses[1]]) {
  const pre = ['compressor_running', 'dhw_active'].includes(role) ? 'binary_sensor.' : 'sensor.';
  statesOnly[pre + obj + '_' + role] = { state: '1', attributes: {} };
}
const out = {};
for (const [name, fn] of Object.entries(resolvers)) {
  out[name] = {
    registry: fn({ states, entities }, {}),
    picked: fn({ states, entities }, { device_id: 'dev_c' }),
    noRegistry: fn({ states: statesOnly, entities: {} }, {}),
  };
}
process.stdout.write(JSON.stringify(out));
"""


def _objects(ids: dict) -> set[str]:
    return {i.split(".", 1)[1].split("_daikin_cycle_ml")[0] for i in ids.values() if i}


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_every_card_shows_one_heat_pump_never_a_mix():
    proc = subprocess.run(["node", "-e", RUNNER], capture_output=True, text=True, timeout=60, check=False,
                          input=json.dumps({"eff": [str(FRONT / f) for f in EFF], "perf": [str(FRONT / f) for f in PERF],
                                            "daily": [str(FRONT / f) for f in DAILY]}))
    assert proc.returncode == 0, proc.stderr
    for card, r in json.loads(proc.stdout).items():
        assert _objects(r["registry"]) == {"b"}, (card, r["registry"])       # the first device found, all roles
        assert _objects(r["picked"]) == {"c"}, (card, r["picked"])           # device_id wins
        assert _objects(r["noRegistry"]) == {"c"}, (card, r["noRegistry"])   # one prefix, sensors and binary sensors
        assert sum(1 for v in r["noRegistry"].values() if v) >= 2, card
