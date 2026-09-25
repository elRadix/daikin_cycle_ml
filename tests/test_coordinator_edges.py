"""Tests for coordinator edge branches (Batch 8d)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)
from custom_components.daikin_cycle_ml.ml.features import VECTOR_LEN
from custom_components.daikin_cycle_ml.ml.baseline import Baseline
from custom_components.daikin_cycle_ml.storage.store import CycleStore


def _coord(power_sensor=None):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.power_sensor = power_sensor
    c.options = {}
    c.store = CycleStore()
    c.baseline = Baseline(VECTOR_LEN)
    c.entry = MagicMock()
    c.entry.entry_id = "t"
    c.hass = MagicMock()
    c.hass.states = MagicMock()
    c._last_alert_sent = {}
    c._errors_total = 0
    c.db = None
    return c


def test_read_power_no_sensor_returns_none():
    c = _coord(power_sensor=None)
    assert c._read_power() is None


def test_read_power_state_missing_returns_none():
    c = _coord(power_sensor="sensor.p")
    c.hass.states.get = MagicMock(return_value=None)
    assert c._read_power() is None


def test_read_power_bad_value_returns_none():
    c = _coord(power_sensor="sensor.p")
    state = MagicMock()
    state.state = "abc"
    c.hass.states.get = MagicMock(return_value=state)
    assert c._read_power() is None


def test_read_power_valid_returns_float():
    c = _coord(power_sensor="sensor.p")
    state = MagicMock()
    state.state = "1234.5"
    c.hass.states.get = MagicMock(return_value=state)
    assert c._read_power() == 1234.5


def test_read_power_int_like_works():
    c = _coord(power_sensor="sensor.p")
    state = MagicMock()
    state.state = "500"
    c.hass.states.get = MagicMock(return_value=state)
    assert c._read_power() == 500.0
