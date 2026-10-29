"""Tests for electrical power cascade (v1.14.0, R507)."""
import pytest
from unittest.mock import MagicMock
from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
from custom_components.daikin_cycle_ml.const import (
    V2_STATS_KEY, INV_PRIMARY_CURRENT_KEY, BUH_STEP1_KEY, BUH_STEP2_KEY,
)


def _coord(options=None, power_sensor=None, cop_sensor=None):
    c = object.__new__(DaikinCycleMLCoordinator)
    c.options = options or {}
    c.power_sensor = power_sensor
    c.cop_sensor_entity = cop_sensor
    c.hass = MagicMock()
    c.hass.states.get = MagicMock(return_value=None)
    c.data = None
    c._last_v2_stats_ts = 0.0
    return c


def _state(value):
    s = MagicMock()
    s.state = str(value)
    return s


def test_power_from_meter_returns_float():
    c = _coord(power_sensor="sensor.pm")
    c.hass.states.get = MagicMock(return_value=_state("573.55"))
    assert c._power_from_meter() == pytest.approx(573.55)


def test_power_from_meter_none_when_not_configured():
    c = _coord(power_sensor=None)
    assert c._power_from_meter() is None


def test_power_from_meter_none_on_invalid():
    c = _coord(power_sensor="sensor.pm")
    c.hass.states.get = MagicMock(return_value=_state("unavailable"))
    assert c._power_from_meter() is None


def test_power_from_v2_stats_returns_watts():
    c = _coord()
    assert c._power_from_v2_stats(1000.0, {V2_STATS_KEY: 0.55}) == pytest.approx(550.0)


def test_power_from_v2_stats_none_when_not_active():
    c = _coord()
    assert c._power_from_v2_stats(1000.0, {"foo": 1.0}) is None


def test_power_from_v2_stats_hysteresis_no_key():
    c = _coord()
    c._last_v2_stats_ts = 1000.0
    assert c._power_from_v2_stats(1100.0, {"foo": 1.0}) is None


def test_power_from_inverter_1phase():
    c = _coord(options={})
    assert c._power_from_inverter({INV_PRIMARY_CURRENT_KEY: 1.8}) == pytest.approx(514.0)


def test_power_from_inverter_3phase():
    c = _coord(options={"supply_phases": "3"})
    assert c._power_from_inverter({INV_PRIMARY_CURRENT_KEY: 1.8}) == pytest.approx(1342.0)


def test_power_from_inverter_buh_step1():
    c = _coord(options={"buh_step1_kw": 3.0})
    attrs = {INV_PRIMARY_CURRENT_KEY: 1.8, BUH_STEP1_KEY: "ON"}
    assert c._power_from_inverter(attrs) == pytest.approx(3514.0)


def test_power_from_inverter_buh_step1_and_step2():
    c = _coord(options={"buh_step1_kw": 3.0, "buh_step2_kw": 6.0})
    attrs = {INV_PRIMARY_CURRENT_KEY: 1.8, BUH_STEP1_KEY: "ON", BUH_STEP2_KEY: "ON"}
    assert c._power_from_inverter(attrs) == pytest.approx(9514.0)


def test_cascade_prefers_power_meter():
    c = _coord(power_sensor="sensor.pm")
    c.hass.states.get = MagicMock(return_value=_state("800.0"))
    attrs = {V2_STATS_KEY: 0.55, INV_PRIMARY_CURRENT_KEY: 1.8}
    pw, src = c._compute_electrical_power(1000.0, attrs)
    assert pw == pytest.approx(800.0)
    assert src == "power_meter"


def test_cascade_prefers_v2_over_inverter():
    c = _coord(power_sensor=None)
    attrs = {V2_STATS_KEY: 0.55, INV_PRIMARY_CURRENT_KEY: 1.8}
    pw, src = c._compute_electrical_power(1000.0, attrs)
    assert pw == pytest.approx(550.0)
    assert src == "espaltherma_v2_stats"


def test_cascade_falls_to_inverter():
    c = _coord(power_sensor=None)
    pw, src = c._compute_electrical_power(1000.0, {INV_PRIMARY_CURRENT_KEY: 1.8})
    assert pw == pytest.approx(514.0)
    assert src == "inverter_estimated_v1"


def test_cascade_none_when_all_missing():
    c = _coord(power_sensor=None)
    pw, src = c._compute_electrical_power(1000.0, {})
    assert pw is None
    assert src == "none"


def test_detect_v2_stats_empty_attrs():
    c = _coord()
    assert c._detect_v2_stats({}) is False
    assert c._detect_v2_stats(None) is False


def test_power_from_meter_invalid_state():
    c = _coord(power_sensor="sensor.pm")
    c.hass.states.get = MagicMock(return_value=_state("not_a_number"))
    assert c._power_from_meter() is None


def test_power_from_v2_stats_invalid_value():
    c = _coord()
    assert c._power_from_v2_stats(1000.0, {V2_STATS_KEY: "not_a_number"}) is None


def test_power_from_inverter_invalid_current():
    c = _coord()
    assert c._power_from_inverter({INV_PRIMARY_CURRENT_KEY: "not_a_number"}) is None
