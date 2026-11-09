"""Regression test for v1.22.1 setpoint oscillation guard."""
from collections import deque

from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator


def _make_coord(state: str) -> DaikinCycleMLCoordinator:
    coord = object.__new__(DaikinCycleMLCoordinator)
    coord.options = {"setpoint_oscillation_threshold": 3}
    coord._setpoint_history = deque([(0, 35.0), (1, 35.5), (2, 35.0), (3, 35.5)])
    coord.detector = type("Detector", (), {"state": state})()
    return coord


def test_setpoint_oscillating_idle_clears_history() -> None:
    """Alert must not fire when compressor is idle, and history must be cleared."""
    coord = _make_coord("idle")
    result = coord._compute_setpoint_oscillating()

    assert result is False
    assert len(coord._setpoint_history) == 0


def test_setpoint_oscillating_heating_still_works() -> None:
    """Normal heating behavior must remain intact (direction reversal triggers)."""
    coord = _make_coord("heating")
    result = coord._compute_setpoint_oscillating()

    assert result is True
    assert len(coord._setpoint_history) == 4


def test_setpoint_oscillating_no_detector() -> None:
    """Ensure missing detector (partial mock) does not crash."""
    coord = _make_coord("heating")
    del coord.detector  # Remove to simulate uninitialized
    # Should fall back to evaluating history (True in this case)
    assert coord._compute_setpoint_oscillating() is True


def test_setpoint_oscillating_idle_empty_history() -> None:
    """Ensure idle state with empty history returns False safely."""
    coord = _make_coord("idle")
    coord._setpoint_history.clear()
    assert coord._compute_setpoint_oscillating() is False
