"""v1.22.4-B: coordinator instrumentation + 5 new diagnostics sections."""
from __future__ import annotations

import time
from collections import deque
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.diagnostics import (
    _coordinator_timing,
    _detector_transitions,
    _repairs_snapshot,
    _runtime_extended,
    _sampling_snapshot,
)


# ---------- bare coordinator (__new__ bypass — R808) ----------
@pytest.fixture
def coord_bare():
    """Coordinator with only attributes the new methods touch.

    Uses __new__ bypass (R808) to avoid pulling in CycleDetector,
    CycleStore, MultiBaseline, AdaptiveThresholds and the
    DataUpdateCoordinator super().__init__ chain — none of which
    the new methods depend on.
    """
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
    )
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c._tick_count = 0
    c._tick_durations_ms = deque(maxlen=200)
    c._last_tick_duration_ms = 0.0
    c._tick_duration_max_ms = 0.0
    c._tick_timestamps = deque(maxlen=3000)
    c._gap_count_24h = 0
    c._largest_gap_s = 0.0
    c._last_gap_s = None
    c._duplicate_ts_count = 0
    c._non_numeric_attrs = []
    c._null_attrs_last_tick = []
    c._samples_last_24h = 0
    c._samples_expected_24h = 2880
    c._last_exception = None
    c._last_exception_ts = None
    c._last_exception_traceback = None
    c._uptime_start_monotonic = 0.0
    c._transitions = deque(maxlen=100)
    c._last_mode_change_ts = 0.0
    c._last_observed_mode = ""
    c.update_interval = timedelta(seconds=30)
    c.data = MagicMock()
    c.data.attrs = {}
    return c


# ---------- sampling ----------
def test_sampling_empty():
    c = MagicMock()
    c._samples_last_24h = 0
    c._samples_expected_24h = 2880
    c._gap_count_24h = 0
    c._largest_gap_s = 0.0
    c._last_gap_s = None
    c._duplicate_ts_count = 0
    c._non_numeric_attrs = []
    c._null_attrs_last_tick = []
    out = _sampling_snapshot(c)
    assert out["gap_count_24h"] == 0
    assert out["non_numeric_attrs"] == []
    assert out["null_attrs_last_tick"] == []


def test_sampling_populated():
    c = MagicMock()
    c._samples_last_24h = 2870
    c._samples_expected_24h = 2880
    c._gap_count_24h = 3
    c._largest_gap_s = 61.5
    c._last_gap_s = 30.2
    c._duplicate_ts_count = 1
    c._non_numeric_attrs = ["weird"]
    c._null_attrs_last_tick = ["flag"]
    out = _sampling_snapshot(c)
    assert out["samples_last_24h"] == 2870
    assert out["gap_count_24h"] == 3
    assert out["largest_gap_s"] == 61.5
    assert out["non_numeric_attrs"] == ["weird"]


# ---------- timing ----------
def test_timing_no_durations():
    c = MagicMock()
    c._tick_count = 42
    c._last_tick_duration_ms = 18.5
    c._tick_duration_max_ms = 410.0
    c._tick_durations_ms = deque(maxlen=200)
    c._uptime_start_monotonic = 0.0
    out = _coordinator_timing(c)
    assert out["tick_count"] == 42
    assert out["tick_duration_ms_last"] == 18.5
    assert out["tick_duration_ms_max"] == 410.0
    assert "tick_duration_ms_p50" not in out


def test_timing_with_durations():
    c = MagicMock()
    c._tick_count = 100
    c._tick_durations_ms = deque([10.0, 20.0, 30.0, 40.0, 50.0], maxlen=200)
    c._last_tick_duration_ms = 50.0
    c._tick_duration_max_ms = 50.0
    c._uptime_start_monotonic = 0.0
    out = _coordinator_timing(c)
    assert out["tick_duration_ms_p50"] == 30.0
    assert "tick_duration_ms_p95" in out


def test_timing_uptime():
    c = MagicMock()
    c._tick_count = 1
    c._tick_durations_ms = deque(maxlen=200)
    c._last_tick_duration_ms = 5.0
    c._tick_duration_max_ms = 5.0
    c._uptime_start_monotonic = time.monotonic() - 3600
    out = _coordinator_timing(c)
    assert out["uptime_s"] is not None
    assert out["uptime_s"] > 3000


# ---------- transitions ----------
def test_transitions_empty():
    c = MagicMock()
    c._transitions = deque(maxlen=100)
    assert _detector_transitions(c) == []


def test_transitions_populated():
    c = MagicMock()
    c._transitions = deque(
        [
            {"ts": 100.0, "from": "IDLE", "to": "RUNNING"},
            {"ts": 200.0, "from": "RUNNING", "to": "IDLE"},
        ],
        maxlen=100,
    )
    out = _detector_transitions(c)
    assert len(out) == 2
    assert out[1]["to"] == "IDLE"


# ---------- repairs ----------
def test_repairs_no_coordinator_issues(hass):
    out = _repairs_snapshot(hass)
    assert out["active"] == []
    assert out["count"] == 0


# ---------- runtime extended ----------
def test_runtime_extended_minimal():
    c = MagicMock()
    c._uptime_start_monotonic = 0.0
    c._last_exception = None
    c._last_exception_ts = None
    c._last_exception_traceback = None
    out = _runtime_extended(c)
    assert out["last_exception"] is None
    assert out["last_exception_ts"] is None
    assert "log_level" in out


def test_runtime_extended_with_exception():
    c = MagicMock()
    c._uptime_start_monotonic = 0.0
    c._last_exception = "ValueError: boom"
    c._last_exception_ts = 123.0
    c._last_exception_traceback = "trace"
    out = _runtime_extended(c)
    assert out["last_exception"] == "ValueError: boom"
    assert out["last_exception_ts"] == 123.0
    assert out["last_exception_traceback"] == "trace"


# ---------- _record_tick_health ----------
def test_record_tick_health_first_tick(coord_bare):
    coord_bare.data.attrs = {"R1T": 6.8, "flag": True, "nullattr": None}
    coord_bare._record_tick_health()
    assert coord_bare._samples_last_24h == 1
    assert coord_bare._last_gap_s is None
    assert coord_bare._null_attrs_last_tick == ["nullattr"]
    assert coord_bare._non_numeric_attrs == []


def test_record_tick_health_normal_gap(coord_bare):
    coord_bare._tick_timestamps.append(time.time() - 30)
    coord_bare._record_tick_health()
    assert coord_bare._gap_count_24h == 0
    assert coord_bare._duplicate_ts_count == 0


def test_record_tick_health_large_gap(coord_bare):
    coord_bare._tick_timestamps.append(time.time() - 60)
    coord_bare._record_tick_health()
    assert coord_bare._gap_count_24h == 1
    assert coord_bare._largest_gap_s >= 59


def test_record_tick_health_duplicate_ts(coord_bare):
    coord_bare._tick_timestamps.append(time.time() - 5)
    coord_bare._record_tick_health()
    assert coord_bare._duplicate_ts_count == 1


def test_record_tick_health_non_numeric_attrs(coord_bare):
    coord_bare.data.attrs = {"str_attr": "hello", "num": 5.0}
    coord_bare._record_tick_health()
    assert "str_attr" in coord_bare._non_numeric_attrs


def test_record_tick_health_prune_24h(coord_bare):
    coord_bare._tick_timestamps.append(time.time() - 90000)
    coord_bare._record_tick_health()
    assert coord_bare._samples_last_24h == 1


def test_record_tick_health_no_update_interval(coord_bare):
    coord_bare.update_interval = None
    coord_bare._tick_timestamps.append(time.time() - 30)
    coord_bare._record_tick_health()  # must not crash


# ---------- _record_exception ----------
def test_record_exception(coord_bare):
    try:
        raise ValueError("boom")
    except ValueError as exc:
        coord_bare._record_exception(exc)
    assert coord_bare._last_exception == "ValueError: boom"
    assert coord_bare._last_exception_ts is not None
    assert "ValueError: boom" in coord_bare._last_exception_traceback


# ---------- _async_update_data wrapper ----------
@pytest.mark.asyncio
async def test_instrument_tick_success(coord_bare):
    """_instrument_tick wrapper: normal flow."""
    from custom_components.daikin_cycle_ml.coordinator import _instrument_tick
    @_instrument_tick
    async def stub(self):
        return MagicMock()
    coord_bare._record_tick_health = MagicMock()
    result = await stub(coord_bare)
    assert coord_bare._tick_count == 1
    assert coord_bare._record_tick_health.called
    assert coord_bare._last_tick_duration_ms >= 0
    assert result is not None


@pytest.mark.asyncio
async def test_instrument_tick_exception(coord_bare):
    """_instrument_tick wrapper: inner raises -> recorded -> re-raised."""
    from custom_components.daikin_cycle_ml.coordinator import _instrument_tick
    @_instrument_tick
    async def stub(self):
        raise ValueError("boom")
    coord_bare._record_tick_health = MagicMock()
    with pytest.raises(ValueError, match="boom"):
        await stub(coord_bare)
    assert coord_bare._tick_count == 1
    assert coord_bare._last_exception == "ValueError: boom"


@pytest.mark.asyncio
async def test_instrument_tick_record_tick_health_exception(coord_bare):
    """_instrument_tick wrapper: _record_tick_health raises -> swallowed."""
    from custom_components.daikin_cycle_ml.coordinator import _instrument_tick
    @_instrument_tick
    async def stub(self):
        return MagicMock()
    coord_bare._record_tick_health = MagicMock(side_effect=RuntimeError("boom"))
    result = await stub(coord_bare)
    assert result is not None


# ---------- _track_mode_transition (transition append coverage) ----------
def test_track_mode_first_observed(coord_bare):
    """Empty _last_observed_mode -> append with from='unknown'."""
    snap = MagicMock()
    snap.mode = "heating"
    coord_bare._track_mode_transition(snap, 100.0)
    assert len(coord_bare._transitions) == 1
    assert coord_bare._transitions[0]["from"] == "unknown"
    assert coord_bare._transitions[0]["to"] == "heating"
    assert coord_bare._transitions[0]["ts"] == 100.0
    assert coord_bare._last_mode_change_ts == 100.0
    assert coord_bare._last_observed_mode == "heating"


def test_track_mode_same_mode_no_append(coord_bare):
    """Same mode -> no append (covers False branch of the if)."""
    snap = MagicMock()
    snap.mode = "heating"
    coord_bare._track_mode_transition(snap, 100.0)
    coord_bare._track_mode_transition(snap, 200.0)
    assert len(coord_bare._transitions) == 1


def test_track_mode_different_mode_appends(coord_bare):
    """heating -> dhw -> 2 transitions logged."""
    s1 = MagicMock(); s1.mode = "heating"
    coord_bare._track_mode_transition(s1, 100.0)
    s2 = MagicMock(); s2.mode = "dhw"
    coord_bare._track_mode_transition(s2, 200.0)
    assert len(coord_bare._transitions) == 2
    assert coord_bare._transitions[1]["from"] == "heating"
    assert coord_bare._transitions[1]["to"] == "dhw"


def test_track_mode_unknown_skipped(coord_bare):
    """mode='unknown' -> early return, no append."""
    snap = MagicMock(); snap.mode = "unknown"
    coord_bare._track_mode_transition(snap, 100.0)
    assert len(coord_bare._transitions) == 0


def test_track_mode_none_skipped(coord_bare):
    """mode=None -> early return."""
    snap = MagicMock(); snap.mode = None
    coord_bare._track_mode_transition(snap, 100.0)
    assert len(coord_bare._transitions) == 0


def test_track_mode_non_string_skipped(coord_bare):
    """mode=42 -> isinstance(str) False -> early return."""
    snap = MagicMock(); snap.mode = 42
    coord_bare._track_mode_transition(snap, 100.0)
    assert len(coord_bare._transitions) == 0


def test_track_mode_empty_string_skipped(coord_bare):
    """mode='' -> early return."""
    snap = MagicMock(); snap.mode = ""
    coord_bare._track_mode_transition(snap, 100.0)
    assert len(coord_bare._transitions) == 0
