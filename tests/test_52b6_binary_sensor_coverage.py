"""Batch 52b6: extra coverage for binary_sensor.py."""

from unittest.mock import MagicMock

from custom_components.daikin_cycle_ml import binary_sensor as bs


def test_pendulum_hourly_propagates_store_error():
    """v1.19.6 (R580): store errors must propagate, not be swallowed.

    Pre-v1.19.6 the function wrapped the DHW count in try/except and
    defaulted dhw_n=0, which INFLATED the alert count when the query
    failed (10 - 0 = 10 >= 4 -> False positive). FIX A removed the
    fallback (R580); the store error now propagates to the caller.
    """
    import pytest

    c = MagicMock()
    c.options = {"pendulum_cycles_per_hour": 4}
    c.store = MagicMock()
    c.store.cycles_in_window_mode = MagicMock(side_effect=RuntimeError("boom"))
    s = MagicMock()
    with pytest.raises(RuntimeError, match="boom"):
        bs._is_pendulum_hourly(s, c)


def test_binary_sensor_is_on_snap_none():
    """Cover lijn 179: snap None -> False."""
    coord = MagicMock()
    sensor = bs.DaikinCycleMLBinarySensor(coord, "test", "Test", lambda s, c: True)
    sensor.snapshot = MagicMock(return_value=None)
    assert sensor.is_on is False


def test_binary_sensor_attrs_snap_none():
    """Cover lijn 192: snap None -> None."""
    coord = MagicMock()
    sensor = bs.DaikinCycleMLBinarySensor(
        coord, "test", "Test", lambda s, c: True, attr_fn=lambda s, c: {"x": 1}
    )
    sensor.snapshot = MagicMock(return_value=None)
    assert sensor.extra_state_attributes is None


def test_binary_sensor_attrs_fn_raises():
    """Cover lijn 195-197."""
    coord = MagicMock()
    sensor = bs.DaikinCycleMLBinarySensor(
        coord, "test", "Test", lambda s, c: True, attr_fn=lambda s, c: 1 / 0
    )
    sensor.snapshot = MagicMock(return_value=MagicMock())
    assert sensor.extra_state_attributes is None
