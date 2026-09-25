"""Tests for 12c: dynamic notifications + emoji + status builder."""
from __future__ import annotations

from custom_components.daikin_cycle_ml.const import (
    ALERT_TYPE_EMOJI,
    SEVERITY_EMOJI,
)
from custom_components.daikin_cycle_ml.engine.notification_engine import (
    BINARY_ALERT_MAP,
    build_status_message,
    evaluate_alerts,
)


def test_severity_emoji_map_complete():
    for k in ("critical", "warning", "watch", "info", "ok", "status"):
        assert k in SEVERITY_EMOJI
        assert SEVERITY_EMOJI[k]


def test_alert_type_emoji_map_covers_core():
    for k in ("pendulum", "short_run", "short_off", "ml_anomaly", "setpoint_osc"):
        assert k in ALERT_TYPE_EMOJI
        assert ALERT_TYPE_EMOJI[k]


def test_dynamic_message_uses_context():
    ctx = {"short_run": {"duration_min": 8, "threshold_min": 20}}
    out = evaluate_alerts({"short_run": True}, {}, now=1e9, context=ctx)
    assert len(out) == 1
    assert "8" in out[0].message
    assert "20" in out[0].message


def test_emoji_prefix_present_by_default():
    out = evaluate_alerts({"short_run": True}, {}, now=1e9)
    assert out[0].message.startswith(ALERT_TYPE_EMOJI["short_run"])


def test_emoji_disabled_via_option():
    out = evaluate_alerts(
        {"short_run": True}, {"notify_emoji_enabled": False}, now=1e9
    )
    assert not out[0].message.startswith(ALERT_TYPE_EMOJI["short_run"])


def test_emoji_disabled_via_kwarg():
    out = evaluate_alerts(
        {"short_run": True}, {}, now=1e9, emoji_enabled=False
    )
    assert not out[0].message.startswith(ALERT_TYPE_EMOJI["short_run"])


def test_no_context_leaves_placeholder():
    out = evaluate_alerts({"short_run": True}, {}, now=1e9)
    assert "{duration_min}" in out[0].message


def test_ml_anomaly_mapped():
    out = evaluate_alerts({"ml_anomaly": True}, {}, now=1e9)
    assert out[0].alert_type == "ml_anomaly"
    assert out[0].notif_id == "daikin_cycle_ml_ml_anomaly"


def test_setpoint_osc_mapped():
    out = evaluate_alerts({"setpoint_osc": True}, {}, now=1e9)
    assert out[0].alert_type == "setpoint_osc"


def test_binary_alert_map_extended():
    for k in ("pendulum_hourly", "pendulum_daily", "short_run",
              "short_off", "ml_anomaly", "setpoint_osc"):
        assert k in BINARY_ALERT_MAP


def test_build_status_message_basic():
    snap = {
        "mode": "heating",
        "state": "running",
        "cycles_today": 12,
        "target_cpd": 8,
        "last_cycle_ago_min": 35,
        "quality_last": 72,
        "anomaly_severity": "normal",
        "baseline_samples": 142,
        "baseline_modes": ["heating", "dhw"],
    }
    msg = build_status_message(snap)
    assert "heating" in msg
    assert "12" in msg and "8" in msg
    assert "35" in msg and "72" in msg
    assert "142" in msg
    assert msg.startswith(SEVERITY_EMOJI["status"])


def test_build_status_message_no_emoji():
    snap = {"mode": "dhw", "state": "idle"}
    msg = build_status_message(snap, emoji_enabled=False)
    assert not msg.startswith(SEVERITY_EMOJI["status"])
    assert "dhw" in msg


def test_build_status_message_minimal():
    msg = build_status_message({})
    assert "unknown" in msg
    assert "idle" in msg

