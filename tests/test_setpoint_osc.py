"""Batch 21 tests: setpoint oscillation tracker + alert state."""
from __future__ import annotations

import time
from collections import deque

from custom_components.daikin_cycle_ml.const import ATTR_LW_SETPOINT
from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)


def _bare_coordinator(options=None):
    """Coordinator via __new__ (R52-safe: class attrs exist)."""
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = options or {}
    c._setpoint_history = None
    c._last_setpoint = None
    return c


def test_track_setpoint_ignores_missing_attr():
    c = _bare_coordinator()
    assert c._track_setpoint({}) == 0


def test_track_setpoint_first_seen_no_entry():
    c = _bare_coordinator()
    assert c._track_setpoint({ATTR_LW_SETPOINT: 35.0}) == 0
    assert c._last_setpoint == 35.0


def test_track_setpoint_below_min_delta_ignored():
    c = _bare_coordinator()
    c._track_setpoint({ATTR_LW_SETPOINT: 35.0})
    assert c._track_setpoint({ATTR_LW_SETPOINT: 35.2}) == 0


def test_track_setpoint_at_min_delta_counts():
    c = _bare_coordinator()
    c._track_setpoint({ATTR_LW_SETPOINT: 35.0})
    assert c._track_setpoint({ATTR_LW_SETPOINT: 34.5}) == 1


def test_track_setpoint_custom_min_delta():
    c = _bare_coordinator(options={"setpoint_osc_min_delta": 0.1})
    c._track_setpoint({ATTR_LW_SETPOINT: 35.0})
    assert c._track_setpoint({ATTR_LW_SETPOINT: 34.9}) == 1


def test_track_setpoint_window_eviction():
    c = _bare_coordinator(options={"setpoint_osc_window_min": 1})
    c._setpoint_history = deque()
    now = time.time()
    c._setpoint_history.append((now - 120, 33.0))
    c._last_setpoint = 34.0
    n = c._track_setpoint({ATTR_LW_SETPOINT: 34.0})
    assert n == 0


def test_track_setpoint_window_disabled_safe():
    c = _bare_coordinator(options={"setpoint_osc_window_min": 0})
    c._track_setpoint({ATTR_LW_SETPOINT: 35.0})
    c._track_setpoint({ATTR_LW_SETPOINT: 34.0})
    assert len(c._setpoint_history) >= 1


def test_track_setpoint_bad_value_safe():
    c = _bare_coordinator()
    assert c._track_setpoint({ATTR_LW_SETPOINT: "garbage"}) == 0


def test_track_setpoint_bad_option_safe():
    c = _bare_coordinator(options={
        "setpoint_osc_window_min": "not-a-number",
        "setpoint_osc_min_delta": "not-a-number",
    })
    assert c._track_setpoint({ATTR_LW_SETPOINT: 35.0}) == 0


def test_compute_oscillating_below_threshold():
    c = _bare_coordinator(options={"setpoint_oscillation_threshold": 5})
    now = time.time()
    c._setpoint_history = deque([(now, 35.0), (now, 34.0)])
    assert c._compute_setpoint_oscillating() is False


def test_compute_oscillating_at_threshold():
    c = _bare_coordinator(options={"setpoint_oscillation_threshold": 3})
    now = time.time()
    c._setpoint_history = deque([(now, x) for x in (35.0, 34.5, 35.0)])
    assert c._compute_setpoint_oscillating() is True


def test_compute_oscillating_default_threshold():
    c = _bare_coordinator()
    c._setpoint_history = None
    assert c._compute_setpoint_oscillating() is False


def test_compute_oscillating_zero_threshold_falls_back():
    c = _bare_coordinator(options={"setpoint_oscillation_threshold": 0})
    now = time.time()
    c._setpoint_history = deque([(now, x) for x in range(10)])
    assert c._compute_setpoint_oscillating() is True


def test_compute_oscillating_bad_option_safe():
    c = _bare_coordinator(options={"setpoint_oscillation_threshold": "bad"})
    c._setpoint_history = deque()
    assert c._compute_setpoint_oscillating() is False
