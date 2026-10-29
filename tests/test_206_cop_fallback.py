"""Tests for internal COP fallback (v1.14.0, R507)."""
import pytest
from unittest.mock import MagicMock
from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
from custom_components.daikin_cycle_ml.const import V2_STATS_KEY


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


BASE_ATTRS = {
    "Leaving water temp. before BUH (R1T)": 30.5,
    "Inlet water temp.(R4T)": 27.5,
    "Flow sensor (l/min)": 17.4,
    "INV frequency (rps)": 22,
    "INV primary current (A)": 1.8,
}


def test_cop_from_sensor_when_present():
    c = _coord(cop_sensor="sensor.cop")
    c.hass.states.get = MagicMock(return_value=_state("5.5"))
    cop, src = c._read_cop_effective(1000.0, BASE_ATTRS)
    assert cop == pytest.approx(5.5)
    assert src == "cop_sensor"


def test_cop_computed_from_flow_dt_inverter():
    c = _coord(power_sensor=None, cop_sensor=None)
    cop, src = c._read_cop_effective(1000.0, BASE_ATTRS)
    assert cop is not None
    assert 6.0 < cop < 8.0
    assert src == "computed_inverter_estimated_v1"


def test_cop_none_when_no_power():
    c = _coord(power_sensor=None, cop_sensor=None)
    cop, src = c._read_cop_effective(1000.0, {"foo": 1.0})
    assert cop is None
    assert src == "no_power"


def test_cop_none_when_no_dt():
    c = _coord(power_sensor=None, cop_sensor=None)
    attrs = {"INV primary current (A)": 1.8}
    cop, src = c._read_cop_effective(1000.0, attrs)
    assert cop is None
    assert src == "no_dt"


def test_cop_out_of_range_returns_none():
    c = _coord(power_sensor=None, cop_sensor=None)
    attrs = {
        V2_STATS_KEY: 0.05,
        "Leaving water temp. before BUH (R1T)": 30.0,
        "Inlet water temp.(R4T)": 25.0,
        "Flow sensor (l/min)": 10.0,
        "INV frequency (rps)": 22,
    }
    cop, src = c._read_cop_effective(1000.0, attrs)
    assert cop is None
    assert src == "cop_out_of_range"


def test_data_snapshot_fields_present():
    from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
    s = DataSnapshot()
    assert hasattr(s, "cop_source")
    assert s.cop_source == "none"
    assert hasattr(s, "electrical_power_w")
    assert s.electrical_power_w is None
    assert hasattr(s, "electrical_power_source")
    assert s.electrical_power_source == "none"


def test_cop_effective_no_attrs_returns_none():
    c = _coord(cop_sensor=None, power_sensor=None)
    cop, src = c._read_cop_effective(1000.0, None)
    assert cop is None
    assert src == "none"
    cop, src = c._read_cop_effective(1000.0, {})
    assert cop is None
    assert src == "none"


def test_cop_effective_invalid_flow():
    c = _coord(cop_sensor=None, power_sensor=None)
    attrs = dict(BASE_ATTRS)
    attrs["Flow sensor (l/min)"] = "invalid"
    cop, src = c._read_cop_effective(1000.0, attrs)
    assert cop is not None
    assert src.startswith("computed_")


def test_cop_effective_invalid_rps():
    c = _coord(cop_sensor=None, power_sensor=None)
    attrs = dict(BASE_ATTRS)
    attrs["INV frequency (rps)"] = "invalid"
    cop, src = c._read_cop_effective(1000.0, attrs)
    assert cop is not None


def test_cop_effective_mode_from_data():
    c = _coord(cop_sensor=None, power_sensor=None)
    class _D:
        mode = "dhw"
    c.data = _D()
    cop, src = c._read_cop_effective(1000.0, BASE_ATTRS)
    assert src.startswith("computed_")
