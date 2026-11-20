"""#435: the configured power meter is used first, in watts.

A kW meter is converted; an energy meter (kWh / device_class energy) is
not a power reading and is skipped (once logged) so the cascade falls back
to the ESPAltherma estimate instead of reading 3200 kWh as 3200 W.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
from custom_components.daikin_cycle_ml.diagnostics import _power_meter


def _coord(state=None):
    c = object.__new__(DaikinCycleMLCoordinator)
    c.options = {}
    c.power_sensor = "sensor.meter"
    c.buh_power_sensor = None
    c.hass = MagicMock()
    c.hass.states.get = MagicMock(return_value=state)
    c._last_v2_stats_ts = 0.0
    return c


def _st(value, unit=None, device_class=None):
    attrs = {}
    if unit:
        attrs["unit_of_measurement"] = unit
    if device_class:
        attrs["device_class"] = device_class
    return SimpleNamespace(state=str(value), attributes=attrs)


def test_watts_used_as_is():
    c = _coord(_st(877.9, "W", "power"))
    assert c._power_from_meter() == pytest.approx(877.9)
    assert c.power_meter_status == {"used": True, "unit": "W", "reason": None}
    assert c._compute_electrical_power(0.0, {})[1] == "power_meter"


def test_kilowatts_converted():
    c = _coord(_st(0.85, "kW", "power"))
    assert c._power_from_meter() == pytest.approx(850.0)


@pytest.mark.parametrize("unit, dc", [("kWh", None), ("Wh", "energy"), (None, "energy")])
def test_energy_meter_skipped_and_logged_once(unit, dc, caplog):
    c = _coord(_st(3200.0, unit, dc))
    with caplog.at_level(logging.WARNING):
        assert c._power_from_meter() is None
        assert c._power_from_meter() is None
    assert sum("energy sensor" in r.message for r in caplog.records) == 1
    assert c.power_meter_status["reason"] == "energy_sensor"
    pw, src = c._compute_electrical_power(0.0, {"Stats: Electrical input estimated (kW)": 0.9})
    assert (pw, src) == (pytest.approx(900.0), "espaltherma_v2_stats")


@pytest.mark.parametrize("state, reason", [
    (None, "unavailable"),
    (_st("unavailable"), "unavailable"),
    (_st("abc", "W"), "not_numeric"),
    (_st(0, "W"), "zero"),
])
def test_skip_reasons(state, reason):
    c = _coord(state)
    assert c._power_from_meter() is None
    assert c.power_meter_status["reason"] == reason


def test_not_configured_and_not_read_yet():
    c = _coord()
    assert c.power_meter_status["reason"] == "not_read_yet"
    c.power_sensor = None
    assert c._power_from_meter() is None
    assert c.power_meter_status == {"used": False, "unit": None, "reason": "not_configured"}


def test_diagnostics_section():
    c = _coord(_st(500, "W"))
    c._power_from_meter()
    assert _power_meter(c)["used"] is True
    assert _power_meter(MagicMock()) is None
