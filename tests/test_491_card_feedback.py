"""#491: Tweakers feedback on the Efficiency and Performance cards.

Replays the situations from the report on the cards' own code with the
states of the real integration: advice to raise the curve while the room
is comfortable (22.5 ° for 22 °), liquid − LWT below −3 K, the curve
legend, the compressor at 8 rps under a learned 10.4–62 rps range and the
profile inputs. The advice itself is also fixed at the source
(engine/cop_analyzer.py): the raise is never advised for a warm room.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from html import unescape

import pytest

from custom_components.daikin_cycle_ml.engine.cop_analyzer import CopSample, analyze_stooklijn
from tests.test_467_performance_card import FILES as PERF_FILES
from tests.test_467_performance_card import _run as perf_run
from tests.test_467_performance_card import _with_profile
from tests.test_efficiency_native_card import FRONT, ORDER, _case, _set, _text
from tests.test_efficiency_native_card import _run as eff_run
from tests.test_native_cards_responsive import _playwright

node = pytest.mark.skipif(not shutil.which("node"), reason="node not installed")

UNIT = r"""
const vm = require('vm'); const fs = require('fs');
const D = JSON.parse(fs.readFileSync(0, 'utf8')); const win = {};
const ctx = vm.createContext({ window: win, Intl, Date, Math, JSON, Object, Array, String, Number, parseFloat, isFinite,
  RegExp, Error, console: { info() {}, debug() {} }, HTMLElement: class {}, CustomEvent: class {}, document: {},
  customElements: { _d: {}, get(n) { return this._d[n]; }, define(n, c) { this._d[n] = c; } }, setInterval: () => 0, clearInterval: () => 0 });
for (const f of D.files) vm.runInContext(fs.readFileSync(f, 'utf8'), ctx, { filename: f });
const R = win.DaikinEfficiencyCardParts.render;
process.stdout.write(JSON.stringify([R.liquidRange([]), R.liquidRange([-5.2, 3, null]), R.liquidRange([-1, 12.4])]));
"""


def _raise(case: dict, room: float) -> dict:
    case = _set(case, "heating_curve_advice", "raise_lwt", step_c=2, doel_setpoint=28.0, besparing_cop_pct=0.0, reason="")
    return _set(case, "thermal_power_live", room_c=room, room_setpoint_c=22.0)


@pytest.fixture(scope="module")
def eff() -> dict:
    return eff_run({
        "warm": _raise(_case("nl"), 22.5),                 # the report: comfortable room, raise advised
        "cold": _raise(_case("en"), 20.8),
        "lower_cold": _set(_set(_case("en"), "heating_curve_advice", "lower_lwt", step_c=2, doel_setpoint=24.0,
                                besparing_cop_pct=4.0, reason=""), "thermal_power_live", room_c=20.8, room_setpoint_c=22.0),
        "warm_engine": _set(_case("en"), "heating_curve_advice", "keep", step_c=0, reason="room_warm_enough"),
    })


@node
def test_advice_never_contradicts_the_comfort_reading(eff):
    w = eff["cases"]["warm"]
    assert w["v"]["comfort"] == ["good", "r_ok"] and w["v"]["advice"] == ["good", "ad_room_ok"]
    adv = _text(w["html"]["advice"])
    assert "Verhoog de stooklijn" not in adv and "de kamer is warm genoeg" in adv
    assert "28,0" not in adv                               # the proposed setpoint is not shown either
    assert eff["cases"]["cold"]["v"]["advice"] == ["watch", "ad_raise_room"]
    assert "the room (20.8 °) stays below its setpoint (22 °)" in _text(eff["cases"]["cold"]["html"]["advice"])
    assert eff["cases"]["lower_cold"]["v"]["advice"] == ["good", "ad_floor"]
    assert eff["cases"]["warm_engine"]["v"]["advice"] == ["good", "ad_room_ok"]


@node
def test_curve_legend_shows_every_point_colour_as_a_dot(eff):
    html = eff["cases"]["warm"]["html"]["curve"]
    legend = next(g for g in re.findall(r'<div class="legend">(.*?)</div>', html) if "COP ≥ 5" in g)
    for colour in ("#2E7D32", "#9CCC65", "#FFB300", "var(--secondary-text-color, #8a8a8a)"):
        assert re.search(rf'<i class="dot[^"]*" style="background:{re.escape(colour)}', legend), colour
    assert all(x in unescape(_text(legend)) for x in ("COP ≥ 5", "COP 3,5–5", "COP < 3,5", "Geen COP", "Berekende lijn", "Nu"))


@node
def test_liquid_axis_follows_what_was_measured():
    proc = subprocess.run(["node", "-e", UNIT], capture_output=True, text=True, timeout=60, check=False,
                          input=json.dumps({"files": [str(FRONT / f) for f in ORDER]}))
    assert proc.returncode == 0, proc.stderr
    plain, low, high = json.loads(proc.stdout)
    assert plain == {"lo": -4, "hi": 12}                      # ticks -4 0 4 8 12 (was -2…10 fixed)
    assert low == {"lo": -10, "hi": 10}                       # -5.2 K measured: ticks -10 -5 0 5 10
    assert high == {"lo": -5, "hi": 15}


def _slow(case: dict) -> dict:
    case = _with_profile(case)
    eid = next(k for k, v in case["entities"].items() if v["translation_key"] == "hp_specs")
    specs = case["states"][eid]["attributes"]
    specs.update(rps_min=10.4, rps_max=62, value_sources={**specs.get("value_sources", {}), "rps_min": "learned", "rps_max": "learned"})
    return _set(case, "thermal_power_live", input_rps=8)


@node
def test_compressor_dial_from_zero_and_profile_inputs():
    out = perf_run({"slow": _slow(_case("nl"))}, PERF_FILES)
    r = out["cases"]["slow"]
    assert r["loads"]["compressor"] == pytest.approx(8 / 62 * 100)     # 13 %, was 0 % below the minimum
    html = r["html"] if isinstance(r["html"], str) else json.dumps(r["html"])
    assert html.count('step="any"') >= 6 and 'step="1"' not in html     # 10.4 no longer fails validation
    for ph in ('placeholder="-7"', 'placeholder="35"', 'placeholder="kW"', 'placeholder="COP"'):
        assert ph in html
    assert "Laatste regel: voeg een punt toe uit je datasheet" in _text(html)


def _samples(lwt: float, n: int = 20) -> list[CopSample]:
    return [CopSample(ts=1000.0 + i, outdoor=5.0, lwt=lwt, cop=4.0, mode="heating", data_quality="Good") for i in range(n)]


@pytest.mark.parametrize(("indoor", "rt_sp", "state", "reason"), [
    (22.5, 22.0, "keep", "room_warm_enough"),       # the report: warm room, no raise
    (21.6, 22.0, "keep", "room_warm_enough"),       # within 0.5 K: on setpoint
    (20.8, 22.0, "raise_lwt", ""),                  # cold room: raise
    (21.0, None, "keep", "room_warm_enough"),       # no room setpoint: above the comfort minimum
    (19.5, None, "raise_lwt", ""),                  # below the comfort minimum (20)
])
def test_engine_raises_the_curve_only_for_a_cold_room(indoor, rt_sp, state, reason):
    adv = analyze_stooklijn(_samples(30.0), indoor_avg=indoor, rt_setpoint=rt_sp, setpoint_lwt=26.0, now=1100.0,
                            tracking_lwt=26.0)
    assert (adv.state, adv.reason) == (state, reason)


def test_engine_lowers_the_curve_only_when_the_room_is_not_cold():
    kw = dict(setpoint_lwt=34.0, now=1100.0, tracking_lwt=34.0)
    assert analyze_stooklijn(_samples(30.0), indoor_avg=22.3, rt_setpoint=22.0, **kw).state == "lower_lwt"
    cold = analyze_stooklijn(_samples(30.0), indoor_avg=21.2, rt_setpoint=22.0, **kw)
    assert (cold.state, cold.reason) == ("keep", "comfort_floor_reached")


# ---------- card options: climate_entity (change the curve) + room_entity ----------

CLIMATE = {"entity_id": "climate.altherma_leaving_water_offset", "state": "heat",
           "attributes": {"friendly_name": "Altherma LWT offset", "temperature": 0, "min_temp": -10, "max_temp": 10,
                          "target_temp_step": 1, "current_temperature": 34}}
THERMOSTAT = {"entity_id": "climate.living", "state": "heat",
              "attributes": {"friendly_name": "Living", "current_temperature": 20.6, "temperature": 22}}


def _with_entities(case: dict, *ents: dict, **config) -> dict:
    case["states"] = {**case["states"], **{e["entity_id"]: e for e in ents}}
    return {**case, "config": config}


@pytest.fixture(scope="module")
def opts() -> dict:
    return eff_run({
        # the report's warm room, measured by the card's own room thermostat as cold: raise, apply +2
        "both": _with_entities(_raise(_case("en"), 22.5), CLIMATE, THERMOSTAT,
                               climate_entity=CLIMATE["entity_id"], room_entity=THERMOSTAT["entity_id"]),
        "sensor_room": _with_entities(_raise(_case("en"), 20.8), {"entity_id": "sensor.living_t", "state": "22.4", "attributes": {}},
                                      room_entity="sensor.living_t"),
        "none": _set(_raise(_case("nl"), 22.5), "thermal_power_live", room_c=None),
        "off": _with_entities(_case("en"), {**CLIMATE, "state": "off"}, climate_entity=CLIMATE["entity_id"]),
    })


@node
def test_room_entity_feeds_the_comfort_check(opts):
    both = opts["cases"]["both"]
    assert both["live"]["room"] == 20.6 and both["live"]["roomSp"] == 22       # thermostat: temperature + setpoint
    assert both["v"]["comfort"][1] == "r_cold" and both["v"]["advice"] == ["watch", "ad_raise_room"]
    sr = opts["cases"]["sensor_room"]
    assert sr["live"]["room"] == 22.4 and sr["v"]["advice"] == ["good", "ad_room_ok"]   # sensor: temperature only


@node
def test_climate_entity_changes_the_curve_from_the_advice_tab(opts):
    html = opts["cases"]["both"]["html"]["advice"]
    steps = re.findall(r'data-act="set-lwt" data-v="([-\d.]+)"', html)
    assert steps == ["-1", "1", "2"]                                  # − 1, + 1, apply the advice (+2)
    assert "Apply the advice (+2 °C)" in _text(html) and "Altherma LWT offset" in _text(html)
    assert "card settings" not in _text(html)                         # nothing to ask for
    off = opts["cases"]["off"]["html"]["advice"]
    assert off.count("disabled") == 2 and "The climate entity is off." in _text(off)
    none = _text(opts["cases"]["none"]["html"]["advice"])
    assert "climate_entity" in none and "room_entity" in none         # asked for both, in Dutch
    assert "Voeg je Daikin climate-entiteit" in none and "Voeg een kamersensor of kamerthermostaat" in none


CLICK = r"""
const { chromium } = require('playwright'); const fs = require('fs');
const c = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
  const b = await chromium.launch(); const p = await b.newPage();
  await p.setContent('<html><body><div id="c"></div></body></html>');
  await p.addScriptTag({ content: "customElements.define('ha-card', class extends HTMLElement {});customElements.define('ha-form', class extends HTMLElement {});" });
  for (const f of c.files) await p.addScriptTag({ content: fs.readFileSync(f, 'utf8') });
  const r = await p.evaluate(async (c) => {
    const N = Date.parse(c.now); Date.now = () => N; const calls = [];
    const el = document.createElement('daikin-efficiency-card'); el.setConfig(Object.assign({ default_tab: 'advice' }, c.config));
    document.getElementById('c').appendChild(el);
    el.hass = { states: c.states, entities: c.entities, language: 'en', locale: { language: 'en' }, callWS: async () => ({}),
      callService: async (d, s, data) => calls.push([d, s, data]) };
    await new Promise((r) => setTimeout(r, 100));
    el.shadowRoot.querySelector('.ctl.apply').click();
    return calls;
  }, c);
  process.stdout.write(JSON.stringify(r)); await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
"""


@pytest.mark.skipif(not _playwright(), reason="playwright (node) not installed")
def test_apply_button_calls_climate_set_temperature():
    case = _with_entities(_raise(_case("en"), 22.5), CLIMATE, THERMOSTAT,
                          climate_entity=CLIMATE["entity_id"], room_entity=THERMOSTAT["entity_id"])
    proc = subprocess.run(["node", "-e", CLICK], capture_output=True, text=True, timeout=120, check=False,
                          input=json.dumps({**case, "files": [str(FRONT / f) for f in ORDER]}))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == [["climate", "set_temperature", {"entity_id": CLIMATE["entity_id"], "temperature": 2}]]


@pytest.fixture(scope="module")
def pops() -> dict:
    c = _case("en")
    return eff_run({k: {**c, "ui": {"bucket": k}} for k in ("r0", "now", "2-4", "r999")})


@node
def test_every_curve_dot_has_a_pop_up_with_its_explanation(pops):
    r0 = pops["cases"]["r0"]["html"]["curve"]
    assert len(re.findall(r'data-act="bucket" data-key="r\d+"', r0)) >= 1     # grey dots are tappable
    assert 'data-key="now"' in r0 and "Tap a dot for its explanation." in _text(r0)
    assert "One hour of heating (" in _text(r0) and "The rings are the last 48 hours" in _text(r0)
    now = _text(pops["cases"]["now"]["html"]["curve"])
    assert "Now:" in now and "at a COP of" in now and "Tap ✕ to close" in now
    band = _text(pops["cases"]["2-4"]["html"]["curve"])
    assert "Band 2-4 °C outside" in band or 'class="pop"' not in pops["cases"]["2-4"]["html"]["curve"]
    assert 'class="pop"' not in pops["cases"]["r999"]["html"]["curve"]   # unknown dot: no pop-up
