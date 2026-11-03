"""Reproduction tests for Issue #245: short_off firing on live off-time."""
from types import MethodType
from unittest.mock import MagicMock
from custom_components.daikin_cycle_ml.binary_sensor import _is_short_off
from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator


def test_short_off_uses_completed_gap_not_live_time():
    """Bug #245: alert fired on live off-time instead of the completed gap.

    Scenario: Previous cycle ended with a 15-min gap before it (not short).
    User checks the binary_sensor 2 min into the next off-period.
    Expected: False (15 min > 10 min threshold).
    Bug behavior: True (2 min live gap < 10 min threshold).
    """
    c = MagicMock()
    c.options = {"short_off_threshold_min": 10}
    c.store.last_cycle.return_value = {"mode": "heating", "duration_s": 1200, "off_s": 900}
    c.store.off_time_since_last.return_value = 120

    s = MagicMock()
    s.mode = "heating"

    assert _is_short_off(s, c) is False


def test_short_off_alert_binary_states():
    """Same scenario via coordinator._alert_binary_states (real method bound to mock)."""
    c = MagicMock()
    c.options = {
        "short_off_threshold_min": 10,
        "short_run_threshold_min": 20,
        "pendulum_cycles_per_hour": 4,
        "pendulum_cycles_per_day": 40,
    }
    c._effective_threshold = lambda k, default: c.options.get(k, default)
    c.store.last_cycle.return_value = {"mode": "heating", "duration_s": 1200, "off_s": 900}
    c.store.off_time_since_last.return_value = 120
    c.store.cycles_in_window.return_value = 0
    c.store.cycles_in_window_mode.return_value = 0
    c.store.non_transient_in_window.return_value = 0
    c.store.non_transient_today.return_value = []
    c._alert_binary_states = MethodType(DaikinCycleMLCoordinator._alert_binary_states, c)

    s = MagicMock()
    s.mode = "heating"
    s.anomaly = None

    states = c._alert_binary_states(s)
    assert states["short_off"] is False
