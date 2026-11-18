"""Optional backup-heater power sensor (prod-1: BUH on its own circuit).

prod-1 measures the compressor with sensor.warmtepomp_power and the
backup heater with sensor.weerstand_power. With only the compressor
meter, BUH heat (ESPAltherma heat uses R2T after the BUH) was counted
but its electricity was not, so COP read high while the BUH ran.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
from custom_components.daikin_cycle_ml.sensor import (
    _attrs_electrical_power_estimated,
)

MAIN = "sensor.warmtepomp_power"
BUH = "sensor.weerstand_power"


def _state(value: Any, unit: str | None = "W") -> SimpleNamespace:
    return SimpleNamespace(state=value, attributes={"unit_of_measurement": unit})


def _coord(states: dict[str, Any], buh: str | None = BUH) -> DaikinCycleMLCoordinator:
    c = object.__new__(DaikinCycleMLCoordinator)
    c.hass = MagicMock()
    c.hass.states.get = lambda eid: states.get(eid)
    c.power_sensor = MAIN
    c.buh_power_sensor = buh
    c._last_buh_meter_w = None
    return c


def test_buh_meter_added_to_power_meter():
    c = _coord({MAIN: _state("435.47"), BUH: _state("3000")})
    assert c._power_from_meter() == pytest.approx(3435.47)
    assert c._last_buh_meter_w == 3000.0


def test_buh_meter_in_kw_is_normalised():
    c = _coord({MAIN: _state("435"), BUH: _state("3.0", "kW")})
    assert c._power_from_meter() == pytest.approx(3435.0)


@pytest.mark.parametrize(
    "buh_state",
    [None, _state("unavailable"), _state("unknown"), _state("abc"),
     _state("-5"), _state("inf"), _state("0")],
)
def test_buh_meter_invalid_or_idle_leaves_main(buh_state):
    states = {MAIN: _state("435")}
    if buh_state is not None:
        states[BUH] = buh_state
    c = _coord(states)
    assert c._power_from_meter() == 435.0


def test_no_buh_sensor_configured():
    c = _coord({MAIN: _state("435"), BUH: _state("3000")}, buh=None)
    assert c._power_from_meter() == 435.0
    assert c._last_buh_meter_w is None


def test_main_meter_missing_ignores_buh():
    c = _coord({BUH: _state("3000")})
    assert c._power_from_meter() is None


def test_main_meter_zero_ignores_buh():
    c = _coord({MAIN: _state("0"), BUH: _state("3000")})
    assert c._power_from_meter() is None


def test_compressor_detection_power_excludes_buh():
    # _read_power_w feeds the compressor fallback detector: BUH must not
    # make an idle compressor look "on".
    c = _coord({MAIN: _state("20"), BUH: _state("3000")})
    c.hass.states.get = lambda eid: {MAIN: _state("20"), BUH: _state("3000")}.get(eid)
    assert c._read_power_w() == 20.0


def test_electrical_power_source_includes_buh():
    c = _coord({MAIN: _state("435"), BUH: _state("3000")})
    pw, src = c._compute_electrical_power(0.0, {})
    assert (pw, src) == (pytest.approx(3435.0), "power_meter")


def test_cop_lower_while_buh_runs():
    # heat 2.6 kW from the HP + 1.0 kW from the BUH (ESPAltherma heat
    # output includes BUH heat via R2T); compressor meter 900 W.
    attrs = {"Stats: Heat output (kW)": 3.6}
    without = _coord({MAIN: _state("900")}, buh=None)
    with_buh = _coord({MAIN: _state("900"), BUH: _state("1000")})
    for c in (without, with_buh):
        c.cop_sensor_entity = None
        c.data = None
    cop_without, _ = without._read_cop_effective(0.0, attrs)
    cop_with, _ = with_buh._read_cop_effective(0.0, attrs)
    assert cop_without == pytest.approx(4.0, rel=1e-3)   # looks fine, is wrong
    assert cop_with == pytest.approx(3.6 / 1.9, rel=1e-3)  # 1.89: real


def test_sensor_attributes_expose_buh_meter():
    c = _coord({MAIN: _state("435"), BUH: _state("3000")})
    c.options = {"buh_power_sensor_entity": BUH}
    c._power_from_meter()
    s = SimpleNamespace(attrs={}, electrical_power_source="power_meter")
    attrs = _attrs_electrical_power_estimated(s, c)  # type: ignore[arg-type]
    assert attrs["buh_power_sensor"] == BUH
    assert attrs["buh_meter_w"] == 3000.0


async def test_options_device_step_offers_buh_sensor(monkeypatch):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.daikin_cycle_ml.config_flow import (
        DaikinCycleMLOptionsFlow,
    )
    from custom_components.daikin_cycle_ml.const import DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN, data={"model": "epra12eav3"},
        options={"buh_power_sensor_entity": BUH}, version=1,
    )
    # pin config_entry: other suites patch how OptionsFlow resolves it
    monkeypatch.setattr(
        DaikinCycleMLOptionsFlow, "config_entry", property(lambda self: entry),
    )
    flow = DaikinCycleMLOptionsFlow()
    flow.hass = MagicMock()
    flow.hass.config_entries.async_get_entry = MagicMock(return_value=entry)
    flow.hass.config_entries.async_get_known_entry = MagicMock(return_value=entry)
    flow.hass.config_entries.async_update_entry = MagicMock()
    flow.handler = entry.entry_id
    flow.context = {"entry_id": entry.entry_id}
    r = await flow.async_step_device()
    sensors = next(
        v.schema for k, v in r["data_schema"].schema.items()
        if str(getattr(k, "schema", k)) == "sensors"
    )
    keys = {str(getattr(k, "schema", k)): k for k in sensors.schema}
    assert "buh_power_sensor_entity" in keys
    assert keys["buh_power_sensor_entity"].description == {"suggested_value": BUH}

    # saving the sensors step without the key clears it (#244 contract)
    out = await flow.async_step_device({"sensors": {"power_sensor_entity": MAIN}})
    assert out["type"] == "create_entry"
    assert out["data"]["buh_power_sensor_entity"] is None
    assert out["data"]["power_sensor_entity"] == MAIN


def test_translations_have_label():
    import json
    from pathlib import Path

    base = Path(__file__).resolve().parent.parent / "custom_components/daikin_cycle_ml"
    for f in ("strings.json", "translations/en.json", "translations/nl.json",
              "translations/fr.json"):
        d = json.loads((base / f).read_text(encoding="utf-8"))
        sec = d["options"]["step"]["device"]["sections"]["sensors"]
        assert sec["data"]["buh_power_sensor_entity"]
        assert sec["data_description"]["buh_power_sensor_entity"]
