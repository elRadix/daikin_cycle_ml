"""Batch 22b tests: alert i18n language selection + rendering."""
from __future__ import annotations

from custom_components.daikin_cycle_ml.engine.notification_engine import (
    ALERT_TEMPLATES,
    ALERT_TEMPLATES_EN,
    ALERT_TEMPLATES_NL,
    BINARY_ALERT_MAP,
    evaluate_alerts,
)


def test_templates_have_en_nl():
    assert "en" in ALERT_TEMPLATES
    assert "nl" in ALERT_TEMPLATES
    assert set(ALERT_TEMPLATES_EN.keys()) == set(ALERT_TEMPLATES_NL.keys())


def test_template_keys_match_binary_alert_map():
    for key in BINARY_ALERT_MAP:
        assert key in ALERT_TEMPLATES_EN
        assert key in ALERT_TEMPLATES_NL


def test_evaluate_alerts_default_en():
    out = evaluate_alerts({"short_run": True}, {}, now=1e9)
    assert len(out) == 1
    assert out[0].alert_type == "short_run"


def test_evaluate_alerts_explicit_language_param():
    out_en = evaluate_alerts({"short_run": True}, {}, now=1e9, language="en")
    out_nl = evaluate_alerts({"short_run": True}, {}, now=1e9, language="nl")
    assert len(out_en) == 1 and len(out_nl) == 1


def test_evaluate_alerts_language_from_options():
    out = evaluate_alerts(
        {"short_run": True},
        {"notification_language": "nl"},
        now=1e9,
    )
    assert len(out) == 1


def test_evaluate_alerts_unknown_lang_falls_back_en():
    out = evaluate_alerts(
        {"short_run": True},
        {"notification_language": "xx"},
        now=1e9,
    )
    assert len(out) == 1


def test_language_param_overrides_option():
    out = evaluate_alerts(
        {"short_run": True},
        {"notification_language": "en"},
        now=1e9,
        language="nl",
    )
    assert len(out) == 1


def test_context_renders_en():
    ctx = {"short_run": {"threshold_min": 20, "duration_min": 10, "advice": ""}}
    out = evaluate_alerts(
        {"short_run": True},
        {"notify_emoji_enabled": False},
        now=1e9,
        context=ctx,
        language="en",
    )
    msg = out[0].message
    assert "Short run" in msg
    assert "10 min" in msg
    assert "{duration_min}" not in msg


def test_context_renders_nl():
    ctx = {"short_run": {"threshold_min": 20, "duration_min": 10, "advice": ""}}
    out = evaluate_alerts(
        {"short_run": True},
        {"notify_emoji_enabled": False},
        now=1e9,
        context=ctx,
        language="nl",
    )
    msg = out[0].message
    assert "Korte run" in msg
    assert "10 min" in msg
    assert "{duration_min}" not in msg


def test_setpoint_osc_renders_threshold():
    ctx = {"setpoint_osc": {
        "osc_count": 7, "window_min": 30, "threshold": 6, "advice": "",
    }}
    out = evaluate_alerts(
        {"setpoint_osc": True},
        {"notify_emoji_enabled": False},
        now=1e9,
        context=ctx,
        language="en",
    )
    msg = out[0].message
    assert "7" in msg
    assert "30" in msg
    assert "6" in msg
    assert "{threshold}" not in msg


def test_pendulum_hourly_renders_cph():
    ctx = {"pendulum": {
        "cph": 5, "target_cph": 4,
        "cycles_today": 42, "target_cpd": 40,
        "advice": "",
    }}
    out = evaluate_alerts(
        {"pendulum_hourly": True},
        {"notify_emoji_enabled": False},
        now=1e9,
        context=ctx,
        language="en",
    )
    msg = out[0].message
    assert "5" in msg
    assert "hourly" in msg.lower()
