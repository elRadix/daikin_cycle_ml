"""Tests for sensor platform (Batch 5b-1)."""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml import sensor as sensor_mod
from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
from custom_components.daikin_cycle_ml.sensor import (
    SENSOR_DEFS,
    DaikinCycleMLSensor,
)
from custom_components.daikin_cycle_ml.storage.store import CycleStore

EXPECTED_KEYS = {
    "cycle_state", "current_cycle_duration", "current_cycle_mode", "current_dt",
    "current_rps", "last_cycle_duration", "last_cycle_mode", "last_cycle_dt_max",
    "last_cycle_quality", "cycles_today", "cycles_last_hour", "short_runs_today",
    "short_offs_today", "short_cycle_ratio", "avg_cycle_duration_today",
    "avg_off_time_today", "longest_cycle_today", "shortest_cycle_today",
    "avg_quality_today", "good_cycles_today", "bad_cycles_today",
    "good_cycle_ratio", "source_age", "missing_attrs_count",
    "last_sample_age", "coordinator_errors",
    "learned_short_run_min",
    "learned_good_off_min",
    "learned_target_cycles_per_day",
}


def _make_coord(snap: DataSnapshot | None = None, store: CycleStore | None = None):
    coord = MagicMock()
    coord.entry.entry_id = "test_entry"
    coord.entry.data = {"model": "epra12eav3"}
    coord.data = snap if snap is not None else DataSnapshot()
    coord.store = store if store is not None else CycleStore()
    coord.options = {}
    return coord


def _make_sensor(key: str, coord=None):
    spec = next(s for s in SENSOR_DEFS if s["key"] == key)
    coord = coord if coord is not None else _make_coord()
    return DaikinCycleMLSensor(
        coord,
        key=spec["key"],
        name=spec["name"],
        value_fn=spec["value_fn"],
        device_class=spec.get("device_class"),
        state_class=spec.get("state_class"),
        unit=spec.get("unit"),
        icon=spec.get("icon"),
    )


# ---------- structural ----------

def test_sensor_defs_count_is_at_least_26():
    # 12a-3 added 3 learned-threshold sensors (26 -> 29).
    assert len(SENSOR_DEFS) >= 26
    keys = {d["key"] for d in SENSOR_DEFS}
    for k in ("learned_short_run_min", "learned_good_off_min",
              "learned_target_cycles_per_day"):
        assert k in keys

def test_sensor_defs_keys_match_expected():
    assert {s["key"] for s in SENSOR_DEFS} == EXPECTED_KEYS


def test_sensor_defs_keys_unique():
    keys = [s["key"] for s in SENSOR_DEFS]
    assert len(keys) == len(set(keys))


def test_sensor_defs_all_have_name():
    assert all(s.get("name") for s in SENSOR_DEFS)


# ---------- base entity ----------

def test_unique_id_format():
    s = _make_sensor("cycle_state")
    assert s.unique_id == "daikin_cycle_ml_test_entry_cycle_state"


def test_device_info_identifiers():
    s = _make_sensor("cycle_state")
    assert ("daikin_cycle_ml", "test_entry") in s.device_info["identifiers"]


def test_device_info_manufacturer_and_model():
    s = _make_sensor("cycle_state")
    assert s.device_info["manufacturer"] == "Daikin"
    assert s.device_info["model"] == "epra12eav3"


def test_has_entity_name_true():
    s = _make_sensor("cycle_state")
    assert s.has_entity_name is True


def test_available_true_when_data_present():
    s = _make_sensor("cycle_state")
    assert s.available is True


def test_available_false_when_data_none():
    coord = _make_coord()
    coord.data = None
    s = _make_sensor("cycle_state", coord)
    assert s.available is False


def test_native_value_none_when_data_none():
    coord = _make_coord()
    coord.data = None
    s = _make_sensor("cycle_state", coord)
    assert s.native_value is None


# ---------- state / mode ----------

def test_cycle_state_returns_idle():
    s = _make_sensor("cycle_state", _make_coord(DataSnapshot(state="idle")))
    assert s.native_value == "idle"


def test_cycle_state_returns_running():
    s = _make_sensor("cycle_state", _make_coord(DataSnapshot(state="running")))
    assert s.native_value == "running"


def test_current_cycle_mode_returns_snapshot_mode():
    s = _make_sensor("current_cycle_mode", _make_coord(DataSnapshot(mode="Heating")))
    assert s.native_value == "Heating"


# ---------- dT / RPS ----------

def test_current_dt_from_attrs():
    snap = DataSnapshot(attrs={
        "Leaving water temp. after BUH (R2T)": 35.0,
        "Inlet water temp.(R4T)": 30.0,
    })
    s = _make_sensor("current_dt", _make_coord(snap))
    assert s.native_value == 5.0


def test_current_dt_none_when_missing():
    snap = DataSnapshot(attrs={})
    s = _make_sensor("current_dt", _make_coord(snap))
    assert s.native_value is None


def test_current_rps_from_attrs():
    snap = DataSnapshot(attrs={"INV frequency (rps)": 42})
    s = _make_sensor("current_rps", _make_coord(snap))
    assert s.native_value == 42.0


def test_current_rps_none_when_missing():
    s = _make_sensor("current_rps", _make_coord(DataSnapshot(attrs={})))
    assert s.native_value is None


# ---------- current_cycle_duration ----------

def test_current_cycle_duration_zero_when_idle():
    s = _make_sensor("current_cycle_duration", _make_coord(DataSnapshot(state="idle")))
    assert s.native_value == 0


def test_current_cycle_duration_computed_when_running(monkeypatch):
    monkeypatch.setattr(sensor_mod, "_now", lambda: 1000.0)
    snap = DataSnapshot(state="running", cycle_start_ts=940.0)
    s = _make_sensor("current_cycle_duration", _make_coord(snap))
    assert s.native_value == 60.0


# ---------- last cycle from store ----------

def test_last_cycle_duration_from_store():
    store = CycleStore()
    store.add_cycle({"start_ts": 1, "duration_s": 120, "mode": "Heating"})
    s = _make_sensor("last_cycle_duration", _make_coord(store=store))
    assert s.native_value == 120


def test_last_cycle_mode_from_store():
    store = CycleStore()
    store.add_cycle({"start_ts": 1, "duration_s": 120, "mode": "DHW"})
    s = _make_sensor("last_cycle_mode", _make_coord(store=store))
    assert s.native_value == "DHW"


def test_last_cycle_dt_max_from_store():
    store = CycleStore()
    store.add_cycle({"start_ts": 1, "dT_max": 7.5})
    s = _make_sensor("last_cycle_dt_max", _make_coord(store=store))
    assert s.native_value == 7.5


# ---------- counters / ratios ----------

def test_short_runs_today_counter():
    store = CycleStore()
    store.record_short_run()
    store.record_short_run()
    s = _make_sensor("short_runs_today", _make_coord(store=store))
    assert s.native_value == 2


def test_short_cycle_ratio_zero_when_no_cycles():
    s = _make_sensor("short_cycle_ratio")
    assert s.native_value == 0.0


def test_short_cycle_ratio_computed():
    now = time.time()
    store = CycleStore()
    for i in range(4):
        store.add_cycle({"start_ts": now - i, "duration_s": 10})
    store.record_short_run()
    store.record_short_run()
    s = _make_sensor("short_cycle_ratio", _make_coord(store=store))
    assert s.native_value == 50.0


def test_good_cycle_ratio_computed():
    store = CycleStore()
    store.increment("good_cycles_today", 3)
    store.increment("bad_cycles_today", 1)
    s = _make_sensor("good_cycle_ratio", _make_coord(store=store))
    assert s.native_value == 75.0


def test_cycles_last_hour_window():
    now = time.time()
    store = CycleStore()
    store.add_cycle({"start_ts": now - 60, "duration_s": 30})
    store.add_cycle({"start_ts": now - 7200, "duration_s": 30})
    s = _make_sensor("cycles_last_hour", _make_coord(store=store))
    assert s.native_value == 1


# ---------- diagnostic ----------

def test_source_age_uses_last_success_ts(monkeypatch):
    monkeypatch.setattr(sensor_mod, "_now", lambda: 1000.0)
    snap = DataSnapshot(last_success_ts=970.0)
    s = _make_sensor("source_age", _make_coord(snap))
    assert s.native_value == 30.0


def test_last_sample_age_uses_last_sample_ts(monkeypatch):
    monkeypatch.setattr(sensor_mod, "_now", lambda: 1000.0)
    snap = DataSnapshot(last_sample_ts=990.0)
    s = _make_sensor("last_sample_age", _make_coord(snap))
    assert s.native_value == 10.0


def test_missing_attrs_count():
    snap = DataSnapshot(missing_attrs=["a", "b", "c"])
    s = _make_sensor("missing_attrs_count", _make_coord(snap))
    assert s.native_value == 3


def test_coordinator_errors_total():
    snap = DataSnapshot(errors_total=7)
    s = _make_sensor("coordinator_errors", _make_coord(snap))
    assert s.native_value == 7
