"""FEAT-2: thermal_power_live sensor cascade tests."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.daikin_cycle_ml.const import (
    ATTR_FLOW_SENSOR,
    ATTR_INLET_WATER_R4T,
    ATTR_INV_FREQUENCY_RPS,
    ATTR_LEAVING_WATER_AFTER_BUH,
    RPS_KW_FACTOR,
    WATER_DENSITY_KG_L,
    WATER_SPECIFIC_HEAT_KJ_KG_K,
)
from custom_components.daikin_cycle_ml.sensor import (
    _attrs_thermal_power_live,
    _compute_thermal_power_live,
    _value_thermal_power_live,
)


def test_cascade_power_cop() -> None:
    kw, src = _compute_thermal_power_live(
        power_w=800.0, cop=3.5, flow_lmin=None, dt_k=None, rps=None,
    )
    assert kw == pytest.approx(2.8, abs=0.01)
    assert src == "power_cop"


def test_cascade_flow_dt() -> None:
    kw, src = _compute_thermal_power_live(
        power_w=None, cop=None, flow_lmin=15.0, dt_k=5.0, rps=None,
    )
    expected = (15.0 * WATER_DENSITY_KG_L
                * WATER_SPECIFIC_HEAT_KJ_KG_K * 5.0 / 60.0)
    assert kw == pytest.approx(expected, abs=0.01)
    assert src == "flow_dt"


def test_cascade_rps_heuristic() -> None:
    kw, src = _compute_thermal_power_live(
        power_w=None, cop=None, flow_lmin=None, dt_k=None, rps=34.0,
    )
    assert kw == pytest.approx(34.0 * RPS_KW_FACTOR, abs=0.01)
    assert src == "rps_heuristic"


def test_cascade_idle() -> None:
    kw, src = _compute_thermal_power_live(
        power_w=None, cop=None, flow_lmin=None, dt_k=None, rps=None,
    )
    assert kw is None
    assert src == "idle"


def test_cascade_partial_power_no_cop() -> None:
    kw, src = _compute_thermal_power_live(
        power_w=800.0, cop=None, flow_lmin=None, dt_k=None, rps=10.0,
    )
    assert src == "rps_heuristic"
    assert kw == pytest.approx(10.0 * RPS_KW_FACTOR, abs=0.01)


def test_cascade_negative_filtered() -> None:
    kw, src = _compute_thermal_power_live(
        power_w=-100.0, cop=3.5, flow_lmin=None, dt_k=None, rps=None,
    )
    assert kw is None
    assert src == "idle"


def test_value_fn_via_simple_namespace() -> None:
    snap = SimpleNamespace(attrs={
        ATTR_LEAVING_WATER_AFTER_BUH: 35.0,
        ATTR_INLET_WATER_R4T: 30.0,
        ATTR_INV_FREQUENCY_RPS: 20.0,
    }, power_w=500.0, cop=4.0)
    coord = SimpleNamespace(
        _read_power_w=lambda: 500.0,
        _read_cop=lambda: 4.0,
    )
    v = _value_thermal_power_live(snap, coord)
    assert v == pytest.approx(2.0, abs=0.01)


def test_attrs_fn_via_simple_namespace_forward_compat() -> None:
    snap = SimpleNamespace(attrs={
        ATTR_LEAVING_WATER_AFTER_BUH: 35.0,
        ATTR_INLET_WATER_R4T: 30.0,
        ATTR_INV_FREQUENCY_RPS: 20.0,
        ATTR_FLOW_SENSOR: 12.0,
    }, power_w=500.0, cop=4.0)
    coord = SimpleNamespace(
        _read_power_w=lambda: 500.0,
        _read_cop=lambda: 4.0,
    )
    a = _attrs_thermal_power_live(snap, coord)
    assert set(a.keys()) >= {
        "input_power_w", "input_cop", "input_flow_lmin",
        "input_dt_k", "input_rps", "calculation_source",
    }
    assert a["calculation_source"] == "power_cop"
    assert a["input_power_w"] == 500.0
    assert a["input_cop"] == 4.0
    assert a["input_flow_lmin"] == 12.0
    assert a["input_dt_k"] == 5.0
    assert a["input_rps"] == 20.0


# --- FEAT-2: coordinator helper coverage ---

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    _normalize_power_w,
)


class _FakeStates:
    def __init__(self, mapping):
        self._m = mapping

    def get(self, eid):
        return self._m.get(eid)


class _FakeHass:
    def __init__(self, mapping):
        self.states = _FakeStates(mapping)


def _st(value, unit=None):
    attrs = {} if unit is None else {"unit_of_measurement": unit}
    return SimpleNamespace(state=str(value), attributes=attrs)


def test_normalize_power_w_units() -> None:
    assert _normalize_power_w(None, "kW") is None
    assert _normalize_power_w(2.0, "kW") == 2000.0
    assert _normalize_power_w(500.0, "W") == 500.0
    assert _normalize_power_w(500.0, None) == 500.0


def test_read_power_w_kw_normalized() -> None:
    coord = SimpleNamespace(
        power_sensor="sensor.p",
        hass=_FakeHass({"sensor.p": _st(2.5, "kW")}),
    )
    assert DaikinCycleMLCoordinator._read_power_w(coord) == 2500.0


def test_read_power_w_w_unchanged() -> None:
    coord = SimpleNamespace(
        power_sensor="sensor.p",
        hass=_FakeHass({"sensor.p": _st(800.0, "W")}),
    )
    assert DaikinCycleMLCoordinator._read_power_w(coord) == 800.0


def test_read_power_w_no_sensor() -> None:
    coord = SimpleNamespace(power_sensor=None, hass=_FakeHass({}))
    assert DaikinCycleMLCoordinator._read_power_w(coord) is None


def test_read_power_w_missing_state() -> None:
    coord = SimpleNamespace(power_sensor="sensor.p", hass=_FakeHass({}))
    assert DaikinCycleMLCoordinator._read_power_w(coord) is None


def test_read_power_w_invalid() -> None:
    coord = SimpleNamespace(
        power_sensor="sensor.p",
        hass=_FakeHass({"sensor.p": _st("abc")}),
    )
    assert DaikinCycleMLCoordinator._read_power_w(coord) is None


def test_read_cop_ok() -> None:
    coord = SimpleNamespace(
        cop_sensor_entity="sensor.c",
        hass=_FakeHass({"sensor.c": _st(3.5)}),
    )
    assert DaikinCycleMLCoordinator._read_cop(coord) == 3.5


def test_read_cop_no_sensor() -> None:
    coord = SimpleNamespace(cop_sensor_entity=None, hass=_FakeHass({}))
    assert DaikinCycleMLCoordinator._read_cop(coord) is None


def test_read_cop_missing() -> None:
    coord = SimpleNamespace(cop_sensor_entity="sensor.c", hass=_FakeHass({}))
    assert DaikinCycleMLCoordinator._read_cop(coord) is None


def test_read_cop_invalid() -> None:
    coord = SimpleNamespace(
        cop_sensor_entity="sensor.c",
        hass=_FakeHass({"sensor.c": _st("abc")}),
    )
    assert DaikinCycleMLCoordinator._read_cop(coord) is None
