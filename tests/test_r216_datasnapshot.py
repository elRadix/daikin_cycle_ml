"""R216: DataSnapshot contract for entity consumption."""
from __future__ import annotations

from types import SimpleNamespace

from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
from custom_components.daikin_cycle_ml.binary_sensor import BINARY_SENSOR_DEFS
from custom_components.daikin_cycle_ml.sensor import (
    _attrs_thermal_power_live,
    _value_thermal_power_live,
)


def test_datasnapshot_has_r216_fields_with_defaults() -> None:
    s = DataSnapshot()
    assert s.power_w is None
    assert s.cop is None
    assert s.setpoint_oscillating is False


def test_datasnapshot_accepts_explicit_values() -> None:
    s = DataSnapshot(power_w=500.0, cop=4.0, setpoint_oscillating=True)
    assert s.power_w == 500.0
    assert s.cop == 4.0
    assert s.setpoint_oscillating is True


def test_sensor_reads_snapshot_not_coordinator() -> None:
    snap = SimpleNamespace(
        attrs={}, power_w=800.0, cop=4.0,
    )
    coord = SimpleNamespace()  # geen _read_power_w nodig
    assert _value_thermal_power_live(snap, coord) == 3.2


def test_binary_sensor_setpoint_oscillating_reads_snapshot() -> None:
    entry = next(
        e for e in BINARY_SENSOR_DEFS if e["key"] == "setpoint_oscillating"
    )
    fn = entry["state_fn"]
    assert fn(SimpleNamespace(setpoint_oscillating=True), SimpleNamespace()) is True
    assert fn(SimpleNamespace(setpoint_oscillating=False), SimpleNamespace()) is False
