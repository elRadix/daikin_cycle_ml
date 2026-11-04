"""v1.19.7 G1: behavioral dispatch tests for alerts lacking them."""
from __future__ import annotations

import time

from custom_components.daikin_cycle_ml.engine.notification_engine import (
    BINARY_ALERT_MAP,
    evaluate_alerts,
)

_BASE_OPTS = {"quiet_hours_enabled": False, "alert_aggregation_minutes": 0}


def _dispatch(states, context=None):
    return evaluate_alerts(states, _BASE_OPTS, time.time(), context=context or {})


def test_high_cycle_rate_dispatches_when_true():
    specs = _dispatch(
        {"high_cycle_rate": True},
        context={"high_cycle_rate": {
            "cph": 12, "target_cph": 4, "multiplier": "1.5", "advice": "advice",
        }},
    )
    assert "high_cycle_rate" in [s.alert_type for s in specs]


def test_high_cycle_rate_silent_when_false():
    specs = _dispatch({"high_cycle_rate": False})
    assert "high_cycle_rate" not in [s.alert_type for s in specs]


def test_cop_vs_datasheet_low_dispatches_when_true():
    specs = _dispatch(
        {"cop_vs_datasheet_low": True},
        context={"cop_vs_datasheet_low": {
            "pct_diff": "-15.2", "cop_expected": "4.20", "advice": "advice",
        }},
    )
    assert "cop_vs_datasheet_low" in [s.alert_type for s in specs]


def test_cop_vs_datasheet_low_silent_when_false():
    specs = _dispatch({"cop_vs_datasheet_low": False})
    assert "cop_vs_datasheet_low" not in [s.alert_type for s in specs]


def test_short_cycling_pattern_dispatches_with_context():
    specs = _dispatch(
        {"short_cycling_pattern": True},
        context={"short_cycling_pattern": {
            "min_cycles": 3, "window_min": 60, "threshold_min": 20,
            "mode": "heating", "outdoor": "8.0", "advice": "advice",
        }},
    )
    assert "short_cycling_pattern" in [s.alert_type for s in specs]


def test_short_cycling_pattern_silent_when_false():
    specs = _dispatch({"short_cycling_pattern": False})
    assert "short_cycling_pattern" not in [s.alert_type for s in specs]


def test_new_alerts_have_no_unfilled_placeholders():
    """Rendered messages must not leak literal {key} when context is complete."""
    cases = [
        ("high_cycle_rate", {"cph": 12, "target_cph": 4, "multiplier": "1.5", "advice": "advice"}),
        ("cop_vs_datasheet_low", {"pct_diff": "-15.2", "cop_expected": "4.20", "advice": "advice"}),
        ("short_cycling_pattern", {"min_cycles": 3, "window_min": 60, "threshold_min": 20,
                                    "mode": "heating", "outdoor": "8.0", "advice": "advice"}),
    ]
    for alert_type, ctx in cases:
        specs = _dispatch({alert_type: True}, context={alert_type: ctx})
        match = [s for s in specs if s.alert_type == alert_type]
        assert match, f"{alert_type} did not dispatch"
        msg = match[0].message
        assert "{" not in msg, f"{alert_type} literal: {msg!r}"


def test_all_three_new_types_are_in_binary_alert_map():
    for t in ("high_cycle_rate", "cop_vs_datasheet_low", "short_cycling_pattern"):
        assert t in BINARY_ALERT_MAP
