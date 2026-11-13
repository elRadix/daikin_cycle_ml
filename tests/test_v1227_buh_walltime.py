"""v1.22.7: BUH wall-time counter (no double-count step1+step2)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    DataSnapshot,
)
from custom_components.daikin_cycle_ml.sensor import (
    _attrs_runtime_buh_today_s,
    _value_runtime_buh_today_s,
)


def _mock_coord():
    """Minimal coordinator with defensive defaults (R808)."""
    coord = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    coord._buh_step1_s = 0.0
    coord._buh_step2_s = 0.0
    coord._buh_total_s = 0.0
    coord._defrost_count_today = 0
    coord._defrost_duration_s = 0.0
    coord._last_defrost_ts = 0.0
    coord._defrost_start_ts = None
    coord._prev_defrost = False
    coord._defrost_prior_s = None
    coord._last_runtime_tick_ts = 0.0
    coord.last_attrs = {}
    coord.entry = None
    coord.store = MagicMock()
    coord.store.cycles_today = MagicMock(return_value=[])
    return coord


# ─── Increment (wall-time) ───

def test_walltime_both_steps_on_no_double_count():
    """Step1+Step2 both ON = 30s wall-time, NOT 60s."""
    c = _mock_coord()
    c._last_runtime_tick_ts = 100.0
    c._tick_buh_and_defrost({"BUH Step1": "ON", "BUH Step2": "ON"}, 130.0)
    assert c._buh_step1_s == pytest.approx(30.0)
    assert c._buh_step2_s == pytest.approx(30.0)
    assert c._buh_total_s == pytest.approx(30.0)  # ← the fix


def test_walltime_step1_only():
    c = _mock_coord()
    c._last_runtime_tick_ts = 100.0
    c._tick_buh_and_defrost({"BUH Step1": "ON", "BUH Step2": "OFF"}, 130.0)
    assert c._buh_step1_s == pytest.approx(30.0)
    assert c._buh_step2_s == 0.0
    assert c._buh_total_s == pytest.approx(30.0)


def test_walltime_step2_only():
    c = _mock_coord()
    c._last_runtime_tick_ts = 100.0
    c._tick_buh_and_defrost({"BUH Step1": "OFF", "BUH Step2": "ON"}, 130.0)
    assert c._buh_step1_s == 0.0
    assert c._buh_step2_s == pytest.approx(30.0)
    assert c._buh_total_s == pytest.approx(30.0)


def test_walltime_none_on():
    c = _mock_coord()
    c._last_runtime_tick_ts = 100.0
    c._tick_buh_and_defrost({"BUH Step1": "OFF", "BUH Step2": "OFF"}, 130.0)
    assert c._buh_total_s == 0.0


# ─── Sensor value (native-first) ───

def test_sensor_value_native_first():
    """v2: native Stats × 60 wins over computed."""
    c = _mock_coord()
    c._buh_total_s = 300.0
    s = DataSnapshot(last_sample_ts=0.0)
    s.attrs = {"Stats: Backup heater today (min)": "42.6"}
    assert _value_runtime_buh_today_s(s, c) == 2556


def test_sensor_value_computed_fallback():
    """v1 (no native): computed wall-time wins."""
    c = _mock_coord()
    c._buh_total_s = 1800.0
    s = DataSnapshot(last_sample_ts=0.0)
    s.attrs = {}
    assert _value_runtime_buh_today_s(s, c) == 1800


def test_sensor_value_invalid_native_fallback():
    """Invalid native ('---') -> computed fallback."""
    c = _mock_coord()
    c._buh_total_s = 1200.0
    s = DataSnapshot(last_sample_ts=0.0)
    s.attrs = {"Stats: Backup heater today (min)": "---"}
    assert _value_runtime_buh_today_s(s, c) == 1200


# ─── Attr output ───

def test_attrs_native_source():
    c = _mock_coord()
    c._buh_step1_s = 2533.0
    c._buh_step2_s = 2903.0
    c._buh_total_s = 2556.0
    s = DataSnapshot(last_sample_ts=0.0)
    s.attrs = {"Stats: Backup heater today (min)": "42.6"}
    attrs = _attrs_runtime_buh_today_s(s, c)
    assert attrs["source"] == "native"
    assert attrs["native_min"] == 42.6
    assert attrs["total_s"] == 2556
    assert attrs["step1_s"] == 2533
    assert attrs["step2_s"] == 2903


def test_attrs_computed_source():
    c = _mock_coord()
    c._buh_step1_s = 1000.0
    c._buh_step2_s = 1200.0
    c._buh_total_s = 1200.0
    s = DataSnapshot(last_sample_ts=0.0)
    s.attrs = {}
    attrs = _attrs_runtime_buh_today_s(s, c)
    assert attrs["source"] == "computed"
    assert attrs["native_min"] is None
    assert attrs["total_s"] == 1200


# ─── Restore migration ───

class _MockDB:
    def __init__(self, store):
        self._store = store

    async def async_get_model_state(self, key):
        return self._store.get(key)

    async def async_set_model_state(self, key, value):
        self._store[key] = value


def test_restore_migrates_legacy_payload():
    """Pre-v1.22.7 payload (no buh_total_s key) -> migrates via max()."""
    c = _mock_coord()
    today = __import__("time").strftime("%Y-%m-%d")
    c.db = _MockDB({
        f"runtime_acc.{today}": {
            "day": today,
            "buh_step1_s": 2533.0,
            "buh_step2_s": 2903.0,
            # NO buh_total_s
        }
    })
    asyncio.run(c._restore_runtime_acc())
    assert c._buh_total_s == pytest.approx(2903.0)  # max(2533, 2903)


# ─── Coverage: _read_float error paths ───

def test_read_native_non_numeric_string():
    """Covers ValueError path in _read_float."""
    from custom_components.daikin_cycle_ml.engine.runtime_source import (
        read_native_buh_minutes,
    )
    assert read_native_buh_minutes({"Stats: Backup heater today (min)": "abc"}) is None


def test_read_native_non_convertible_type():
    """Covers TypeError path in _read_float."""
    from custom_components.daikin_cycle_ml.engine.runtime_source import (
        read_native_buh_minutes,
    )
    assert read_native_buh_minutes({"Stats: Backup heater today (min)": object()}) is None


# ─── defrost_count_today ───

def test_defrost_count_native_first():
    from custom_components.daikin_cycle_ml.engine.runtime_source import (
        defrost_count_today,
    )
    value, src = defrost_count_today({"Stats: Defrosts today": "6"}, 4)
    assert value == 6
    assert src == "native"


def test_defrost_count_computed_fallback():
    from custom_components.daikin_cycle_ml.engine.runtime_source import (
        defrost_count_today,
    )
    value, src = defrost_count_today({}, 4)
    assert value == 4
    assert src == "computed"


def test_defrost_count_invalid_native():
    from custom_components.daikin_cycle_ml.engine.runtime_source import (
        defrost_count_today,
    )
    value, src = defrost_count_today({"Stats: Defrosts today": "---"}, 3)
    assert value == 3
    assert src == "computed"


# ─── compressor_starts_today ───

def test_compressor_starts_native_first():
    from custom_components.daikin_cycle_ml.engine.runtime_source import (
        compressor_starts_today,
    )
    value, src = compressor_starts_today({"Stats: Compressor starts today": "13"}, 5)
    assert value == 13
    assert src == "native"


def test_compressor_starts_computed_fallback():
    from custom_components.daikin_cycle_ml.engine.runtime_source import (
        compressor_starts_today,
    )
    value, src = compressor_starts_today({}, 5)
    assert value == 5
    assert src == "computed"


# ─── Sensor value fns: native-first integration ───

def test_sensor_defrost_count_native():
    from custom_components.daikin_cycle_ml.sensor import _value_defrost_count_today
    c = _mock_coord()
    c._defrost_count_today = 4
    s = DataSnapshot(last_sample_ts=0.0)
    s.attrs = {"Stats: Defrosts today": "6"}
    assert _value_defrost_count_today(s, c) == 6


def test_sensor_compressor_starts_native():
    from custom_components.daikin_cycle_ml.sensor import _value_compressor_starts_today
    c = _mock_coord()
    s = DataSnapshot(last_sample_ts=0.0)
    s.attrs = {"Stats: Compressor starts today": "13"}
    assert _value_compressor_starts_today(s, c) == 13


def test_sensor_compressor_starts_computed():
    from custom_components.daikin_cycle_ml.sensor import _value_compressor_starts_today
    c = _mock_coord()
    c.store.cycles_today = MagicMock(return_value=[{"start_ts": 1.0}, {"start_ts": 2.0}])
    s = DataSnapshot(last_sample_ts=0.0)
    s.attrs = {}
    assert _value_compressor_starts_today(s, c) == 2


# ─── Coverage: _read_float edge cases (v1.22.7) ───

def test_read_float_attrs_not_dict():
    """Coverage for `if not isinstance(attrs, dict): return None`."""
    from unittest.mock import MagicMock
    from custom_components.daikin_cycle_ml.engine.runtime_source import (
        read_native_buh_minutes,
    )
    assert read_native_buh_minutes(MagicMock()) is None


def test_read_float_raw_none():
    """Coverage for `if raw is None: return None`."""
    from custom_components.daikin_cycle_ml.engine.runtime_source import (
        read_native_buh_minutes,
    )
    assert read_native_buh_minutes({"Stats: Backup heater today (min)": None}) is None


# ─── Coverage: sensor safe-guard except paths ───

def test_defrost_count_except_int_conversion():
    """Covers sensor.py except in defrost_count (snap contains non-numeric).

    Uses MagicMock (not real coordinator) because ``runtime_snapshot`` is a
    read-only property on the real class; the mock allows attribute assignment.
    """
    from custom_components.daikin_cycle_ml.sensor import (
        _value_defrost_count_today,
    )
    c = MagicMock()
    c.last_attrs = None
    c.runtime_snapshot = {
        "defrost_count": "not-a-number",
        "buh_step1_s": 0.0,
        "buh_step2_s": 0.0,
    }
    s = DataSnapshot(last_sample_ts=0.0)
    s.attrs = {"Stats: Defrosts today": "3"}  # native wins -> 3
    assert _value_defrost_count_today(s, c) == 3


def test_defrost_count_except_then_computed_zero():
    """Same except path, but no native → falls back to computed=0."""
    from custom_components.daikin_cycle_ml.sensor import (
        _value_defrost_count_today,
    )
    c = MagicMock()
    c.last_attrs = None
    c.runtime_snapshot = {"defrost_count": "bad"}  # int() raises -> except -> 0
    s = DataSnapshot(last_sample_ts=0.0)
    s.attrs = {}  # no native → computed (which is 0)
    assert _value_defrost_count_today(s, c) == 0


def test_compressor_starts_except_cycles_raises():
    """Covers sensor.py except in comp-starts (store.cycles_today raises)."""
    from custom_components.daikin_cycle_ml.sensor import (
        _value_compressor_starts_today,
    )
    c = _mock_coord()
    c.store.cycles_today = MagicMock(side_effect=RuntimeError("db gone"))
    s = DataSnapshot(last_sample_ts=0.0)
    s.attrs = {"Stats: Compressor starts today": "7"}  # native wins
    assert _value_compressor_starts_today(s, c) == 7

