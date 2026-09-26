"""Batch 22c tests: per-group alert filtering."""
from __future__ import annotations

from custom_components.daikin_cycle_ml.engine.notification_engine import (
    evaluate_alerts,
)


def test_default_all_groups_on():
    out = evaluate_alerts(
        {"short_run": True, "short_off": True},
        {},
        now=1e9,
    )
    types = {a.alert_type for a in out}
    assert "short_run" in types
    assert "short_off" in types


def test_group_short_cycle_disabled():
    out = evaluate_alerts(
        {"short_run": True, "short_off": True},
        {"alert_group_short_cycle": False},
        now=1e9,
    )
    assert out == []


def test_group_pendulum_disabled():
    out = evaluate_alerts(
        {"pendulum_hourly": True},
        {"alert_group_pendulum": False},
        now=1e9,
    )
    assert out == []


def test_group_ml_disabled():
    out = evaluate_alerts(
        {"ml_anomaly": True},
        {"alert_group_ml": False},
        now=1e9,
    )
    assert out == []


def test_group_setpoint_disabled():
    out = evaluate_alerts(
        {"setpoint_osc": True},
        {"alert_group_setpoint": False},
        now=1e9,
    )
    assert out == []


def test_partial_disable_keeps_other_groups():
    out = evaluate_alerts(
        {"short_run": True, "pendulum_hourly": True},
        {"alert_group_short_cycle": False},
        now=1e9,
    )
    types = {a.alert_type for a in out}
    assert "short_run" not in types
    assert "pendulum" in types


def test_group_enabled_explicitly_still_fires():
    out = evaluate_alerts(
        {"short_run": True},
        {"alert_group_short_cycle": True},
        now=1e9,
    )
    assert len(out) == 1


def test_group_disable_before_dedup_check():
    """Disabled group should not consume dedup window."""
    last = {"short_run": 1e9 - 60}  # 1 min ago
    out = evaluate_alerts(
        {"short_run": True},
        {"alert_group_short_cycle": False},
        now=1e9,
        last_sent=last,
    )
    assert out == []
