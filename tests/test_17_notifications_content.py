"""Batch 17a: notification content consistency."""
import re

from custom_components.daikin_cycle_ml.engine.notification_engine import (
    BINARY_ALERT_MAP,
    evaluate_alerts,
)


def _opts():
    return {
        "notify_emoji_enabled": True,
        "quiet_hours_enabled": False,
        "alert_aggregation_minutes": 0,
        "persistent_enabled": True,
    }


def _first_msg(bkey, ctx):
    alerts = evaluate_alerts(
        {bkey: True}, _opts(), now=1000.0, context=ctx
    )
    assert len(alerts) == 1
    return alerts[0].message


def test_pendulum_hourly_real_numbers():
    ctx = {
        "pendulum": {
            "cph": 6, "target_cph": 4,
            "cycles_today": 42, "target_cpd": 40,
            "advice": "",
        }
    }
    msg = _first_msg("pendulum_hourly", ctx)
    assert "Pendulum hourly" in msg
    assert "6" in msg and "4" in msg
    assert "?" not in msg
    assert "{" not in msg


def test_pendulum_daily_real_numbers():
    ctx = {
        "pendulum": {
            "cph": 1, "target_cph": 4,
            "cycles_today": 42, "target_cpd": 40,
            "advice": "",
        }
    }
    msg = _first_msg("pendulum_daily", ctx)
    assert "42" in msg
    assert "{" not in msg


def test_short_run_with_advice():
    advice = "\n\U0001F4A1 Consider wider setpoint delta"
    ctx = {
        "short_run": {
            "duration_min": 12, "threshold_min": 20,
            "advice": advice,
        }
    }
    msg = _first_msg("short_run", ctx)
    assert "12" in msg and "20" in msg
    assert "Consider wider setpoint delta" in msg


def test_short_run_without_advice():
    ctx = {
        "short_run": {
            "duration_min": 12, "threshold_min": 20, "advice": "",
        }
    }
    msg = _first_msg("short_run", ctx)
    assert not msg.endswith("\n")


def test_ml_anomaly_format():
    ctx = {
        "ml_anomaly": {
            "mode": "Heating", "z_max": 3.8,
            "top_dim": "duration_s", "advice": "",
        }
    }
    msg = _first_msg("ml_anomaly", ctx)
    assert "Heating" in msg
    assert "3.8" in msg
    assert "duration_s" in msg


def test_setpoint_osc_format():
    ctx = {
        "setpoint_osc": {
            "osc_count": 5, "window_min": 60, "advice": "",
        }
    }
    msg = _first_msg("setpoint_osc", ctx)
    assert "5" in msg and "60" in msg


def test_multiline_all_templates():
    """Every alert renders at least 2 lines (headline + detail)."""
    for bkey in BINARY_ALERT_MAP:
        atype = BINARY_ALERT_MAP[bkey][0]
        ctx = {
            atype: {
                "cph": 1, "target_cph": 2,
                "cycles_today": 3, "target_cpd": 4,
                "duration_min": 5, "threshold_min": 6,
                "off_min": 7,
                "mode": "H", "z_max": 1.0, "top_dim": "x",
                "osc_count": 8, "window_min": 9,
                "advice": "",
            }
        }
        msg = _first_msg(bkey, ctx)
        # strip leading emoji + space
        body = re.sub(r"^[^\s]+\s+", "", msg, count=1)
        assert "{" not in body, "placeholder in " + bkey + ": " + body
        assert "}" not in body, "placeholder in " + bkey + ": " + body


def test_no_question_mark_left():
    """Regression: cph/cycles_today no longer render as ?."""
    for bkey in BINARY_ALERT_MAP:
        atype = BINARY_ALERT_MAP[bkey][0]
        ctx = {
            atype: {
                "cph": 1, "target_cph": 2,
                "cycles_today": 3, "target_cpd": 4,
                "duration_min": 5, "threshold_min": 6,
                "off_min": 7,
                "mode": "H", "z_max": 1.0, "top_dim": "x",
                "osc_count": 8, "window_min": 9,
                "advice": "",
            }
        }
        msg = _first_msg(bkey, ctx)
        assert "?" not in msg, bkey + ": " + msg

def test_stooklijn_format_lower():
    from custom_components.daikin_cycle_ml.engine.notification_engine import (
        build_stooklijn_message,
    )
    msg = build_stooklijn_message({
        "state": "verlaag_lwt_2c",
        "besparing_cop_pct": 8.0,
        "comfort_impact": 0.5,
        "betrouwbaarheid": 0.87,
        "samples": 14,
    })
    assert "Stooklijn" in msg
    assert "Lower LWT" in msg
    assert "8% COP" in msg
    assert "0.5C" in msg
    assert "87% confidence" in msg
    assert "14 samples" in msg
    assert "{" not in msg


def test_stooklijn_format_unknown_state():
    from custom_components.daikin_cycle_ml.engine.notification_engine import (
        build_stooklijn_message,
    )
    msg = build_stooklijn_message({"state": "behoud"})
    assert "Keep current LWT" in msg


def test_stooklijn_empty_cache():
    from custom_components.daikin_cycle_ml.engine.notification_engine import (
        build_stooklijn_message,
    )
    msg = build_stooklijn_message({})
    assert "Insufficient data" in msg


def test_cop_low_format():
    from custom_components.daikin_cycle_ml.engine.notification_engine import (
        build_cop_low_message,
    )
    msg = build_cop_low_message(2.31, 5)
    assert "Day COP low" in msg
    assert "2.31" in msg
    assert "threshold 2.5" in msg
    assert "5 samples" in msg
