"""Batch 52b6: extra coverage for sensor.py."""
from unittest.mock import MagicMock

from custom_components.daikin_cycle_ml import sensor as s_mod


def test_ratio_denom_zero():
    """Cover lijn 74-75: denom <= 0 -> None."""
    assert s_mod._ratio(5, 0) is None
    assert s_mod._ratio(5, -1) is None


def test_ratio_type_error():
    """Cover lijn 74-75: exception path."""
    assert s_mod._ratio("bad", 10) is None


def test_attrs_current_cycle_running_with_start():
    """Cover lijn 123."""
    s = MagicMock()
    s.state = "running"
    s.cycle_start_ts = 100.0
    s.attrs = {}
    c = MagicMock()
    out = s_mod._attrs_current_cycle(s, c)
    assert "duration_min" in out
    assert out["duration_min"] is not None


def test_attrs_learned_adaptive_raises():
    """Cover lijn 201-202, 205-206."""
    s = MagicMock()
    s.mode = "heating"
    c = MagicMock()
    c.adaptive = MagicMock()
    c.adaptive.learn_good_off_min = MagicMock(side_effect=RuntimeError("a"))
    c.adaptive.learn_target_cycles_per_day = MagicMock(
        side_effect=RuntimeError("b"))
    c.options = {}
    out = s_mod._attrs_learned(s, c)
    assert out["good_off_min"] is None
    assert out["target_cycles_per_day"] is None
