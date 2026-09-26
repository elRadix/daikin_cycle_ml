"""Tests for binary_sensor platform (Batch 5b-2)."""
from __future__ import annotations

import time
from unittest.mock import MagicMock

from custom_components.daikin_cycle_ml import binary_sensor as bs_mod
from custom_components.daikin_cycle_ml.binary_sensor import (
    BINARY_SENSOR_DEFS,
    DaikinCycleMLBinarySensor,
)
from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
from custom_components.daikin_cycle_ml.storage.store import CycleStore

EXPECTED_KEYS = {
    "compressor_running", "pendulum_hourly", "pendulum_daily", "short_run",
    "short_off", "defrost_active", "buh_step1_active", "buh_step2_active",
    "dhw_active", "heating_active", "cooling_active", "source_stale",
    "missing_attrs", "setpoint_oscillating", "dhw_pendulum", "high_cycle_rate",
}


def _make_coord(snap=None, store=None, options=None):
    coord = MagicMock()
    coord.entry.entry_id = "test_entry"
    coord.entry.data = {"model": "epra12eav3"}
    coord.data = snap if snap is not None else DataSnapshot()
    coord.store = store if store is not None else CycleStore()
    coord.options = options if options is not None else {}
    return coord


def _make_bs(key: str, coord=None):
    spec = next(s for s in BINARY_SENSOR_DEFS if s["key"] == key)
    coord = coord if coord is not None else _make_coord()
    return DaikinCycleMLBinarySensor(
        coord, key=spec["key"], name=spec["name"],
        state_fn=spec["state_fn"],
        device_class=spec.get("device_class"),
        icon=spec.get("icon"),
    )


# ---------- structural ----------

def test_binary_sensor_defs_count_is_16():
    assert len(BINARY_SENSOR_DEFS) == 16


def test_binary_sensor_defs_keys_match_expected():
    assert {s["key"] for s in BINARY_SENSOR_DEFS} == EXPECTED_KEYS


def test_binary_sensor_defs_keys_unique():
    keys = [s["key"] for s in BINARY_SENSOR_DEFS]
    assert len(keys) == len(set(keys))


def test_binary_sensor_defs_all_have_name():
    assert all(s.get("name") for s in BINARY_SENSOR_DEFS)


# ---------- base entity ----------

def test_unique_id_format():
    bs = _make_bs("compressor_running")
    assert bs.unique_id == "daikin_cycle_ml_test_entry_compressor_running"


def test_device_info_identifiers():
    bs = _make_bs("compressor_running")
    assert ("daikin_cycle_ml", "test_entry") in bs.device_info["identifiers"]


def test_device_info_model_from_entry():
    bs = _make_bs("compressor_running")
    assert bs.device_info["model"] == "epra12eav3"


def test_available_true_when_data_present():
    assert _make_bs("compressor_running").available is True


def test_available_false_when_data_none():
    coord = _make_coord()
    coord.data = None
    assert _make_bs("compressor_running", coord).available is False


def test_is_on_false_when_data_none():
    coord = _make_coord()
    coord.data = None
    assert _make_bs("compressor_running", coord).is_on is False


# ---------- compressor / mode ----------

def test_compressor_running_on():
    snap = DataSnapshot(state="running")
    assert _make_bs("compressor_running", _make_coord(snap)).is_on is True


def test_compressor_running_off_when_idle():
    snap = DataSnapshot(state="idle")
    assert _make_bs("compressor_running", _make_coord(snap)).is_on is False


def test_heating_active_on():
    snap = DataSnapshot(mode="Heating")
    assert _make_bs("heating_active", _make_coord(snap)).is_on is True


def test_cooling_active_on():
    snap = DataSnapshot(mode="Cooling")
    assert _make_bs("cooling_active", _make_coord(snap)).is_on is True


# ---------- attr-driven ----------

def test_defrost_active_on_from_attr():
    snap = DataSnapshot(attrs={"Defrost Operation": "ON"})
    assert _make_bs("defrost_active", _make_coord(snap)).is_on is True


def test_buh_step1_on_from_attr():
    snap = DataSnapshot(attrs={"BUH Step1": "ON"})
    assert _make_bs("buh_step1_active", _make_coord(snap)).is_on is True


def test_buh_step2_off_when_missing():
    snap = DataSnapshot(attrs={})
    assert _make_bs("buh_step2_active", _make_coord(snap)).is_on is False


def test_dhw_active_via_iu_mode():
    snap = DataSnapshot(attrs={"I/U operation mode": "DHW"})
    assert _make_bs("dhw_active", _make_coord(snap)).is_on is True


def test_dhw_active_via_3way_valve():
    snap = DataSnapshot(attrs={"3way valve(On:DHW_Off:Space)": "ON"})
    assert _make_bs("dhw_active", _make_coord(snap)).is_on is True


# ---------- diagnostics ----------

def test_source_stale_on_when_old(monkeypatch):
    monkeypatch.setattr(bs_mod, "_now", lambda: 10000.0)
    snap = DataSnapshot(last_success_ts=9000.0)
    assert _make_bs("source_stale", _make_coord(snap)).is_on is True


def test_source_stale_off_when_fresh(monkeypatch):
    monkeypatch.setattr(bs_mod, "_now", lambda: 10000.0)
    snap = DataSnapshot(last_success_ts=9999.0)
    assert _make_bs("source_stale", _make_coord(snap)).is_on is False


def test_missing_attrs_on_when_list_non_empty():
    snap = DataSnapshot(missing_attrs=["x"])
    assert _make_bs("missing_attrs", _make_coord(snap)).is_on is True


def test_missing_attrs_off_when_empty():
    snap = DataSnapshot(missing_attrs=[])
    assert _make_bs("missing_attrs", _make_coord(snap)).is_on is False


def test_setpoint_oscillating_follows_coordinator():
    """Batch 21b: stub removed; state now delegates to coordinator."""
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
    )
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = {}
    c._setpoint_history = None
    c._last_setpoint = None
    assert c._compute_setpoint_oscillating() is False

def test_pendulum_hourly_on_when_threshold_hit(monkeypatch):
    monkeypatch.setattr(bs_mod, "_now", lambda: 10000.0)
    store = CycleStore()
    for i in range(4):
        store.add_cycle({"start_ts": 9990 - i, "duration_s": 10})
    coord = _make_coord(store=store, options={"pendulum_cycles_per_hour": 4})
    assert _make_bs("pendulum_hourly", coord).is_on is True


def test_pendulum_hourly_off_below_threshold(monkeypatch):
    monkeypatch.setattr(bs_mod, "_now", lambda: 10000.0)
    store = CycleStore()
    store.add_cycle({"start_ts": 9990, "duration_s": 10})
    coord = _make_coord(store=store, options={"pendulum_cycles_per_hour": 4})
    assert _make_bs("pendulum_hourly", coord).is_on is False


def test_short_run_on_when_last_cycle_short():
    store = CycleStore()
    store.add_cycle({"start_ts": 100, "duration_s": 300})
    coord = _make_coord(store=store, options={"short_run_threshold_min": 20})
    assert _make_bs("short_run", coord).is_on is True


def test_short_run_off_when_long_cycle():
    store = CycleStore()
    store.add_cycle({"start_ts": 100, "duration_s": 3600})
    coord = _make_coord(store=store, options={"short_run_threshold_min": 20})
    assert _make_bs("short_run", coord).is_on is False


def test_short_off_on_when_recent(monkeypatch):
    monkeypatch.setattr(bs_mod, "_now", lambda: 1000.0)
    store = CycleStore()
    store.add_cycle({"start_ts": 900, "end_ts": 990, "duration_s": 90})
    coord = _make_coord(store=store, options={"short_off_threshold_min": 5})
    assert _make_bs("short_off", coord).is_on is True


def test_short_off_off_when_long(monkeypatch):
    monkeypatch.setattr(bs_mod, "_now", lambda: 1000.0)
    store = CycleStore()
    store.add_cycle({"start_ts": 100, "end_ts": 600, "duration_s": 500})
    coord = _make_coord(store=store, options={"short_off_threshold_min": 5})
    assert _make_bs("short_off", coord).is_on is False


def test_dhw_pendulum_on(monkeypatch):
    monkeypatch.setattr(bs_mod, "_now", lambda: 10000.0)
    store = CycleStore()
    for i in range(3):
        store.add_cycle({"start_ts": 9990 - i, "mode": "DHW", "duration_s": 60})
    coord = _make_coord(store=store, options={"dhw_pendulum_cycles_per_hour": 3})
    assert _make_bs("dhw_pendulum", coord).is_on is True


def test_high_cycle_rate_on(monkeypatch):
    monkeypatch.setattr(bs_mod, "_now", lambda: 10000.0)
    store = CycleStore()
    for i in range(7):
        store.add_cycle({"start_ts": 9990 - i, "duration_s": 30})
    coord = _make_coord(store=store, options={"pendulum_cycles_per_hour": 4})
    assert _make_bs("high_cycle_rate", coord).is_on is True


def test_high_cycle_rate_off(monkeypatch):
    monkeypatch.setattr(bs_mod, "_now", lambda: 10000.0)
    store = CycleStore()
    store.add_cycle({"start_ts": 9990, "duration_s": 30})
    coord = _make_coord(store=store, options={"pendulum_cycles_per_hour": 4})
    assert _make_bs("high_cycle_rate", coord).is_on is False
