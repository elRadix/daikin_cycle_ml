"""Tests for notification_engine (Batch 6b-3a)."""
from __future__ import annotations

import time

from custom_components.daikin_cycle_ml.engine.notification_engine import (
    AlertSpec,
    BINARY_ALERT_MAP,
    DEFAULT_AGG_MIN,
    SEV_CRITICAL,
    SEV_WARNING,
    _in_quiet_hours,
    _parse_hhmm,
    evaluate_alerts,
)


def _ts(y, mo, d, h, mi):
    return time.mktime((y, mo, d, h, mi, 0, 0, 0, -1))


# ---------- parsing ----------

def test_parse_hhmm_valid():
    assert _parse_hhmm("22:00", "07:00") == (22, 0)
    assert _parse_hhmm("07:30", "22:00") == (7, 30)


def test_parse_hhmm_invalid_falls_back():
    assert _parse_hhmm("garbage", "07:00") == (7, 0)
    assert _parse_hhmm(None, "22:00") == (22, 0)


# ---------- quiet hours ----------

def test_in_quiet_hours_same_day():
    # 01:00-05:00 window, at 03:00
    assert _in_quiet_hours(_ts(2026, 1, 1, 3, 0), (1, 0), (5, 0)) is True


def test_in_quiet_hours_same_day_outside():
    assert _in_quiet_hours(_ts(2026, 1, 1, 6, 0), (1, 0), (5, 0)) is False


def test_in_quiet_hours_overnight_evening():
    # 22:00-07:00, at 23:30
    assert _in_quiet_hours(_ts(2026, 1, 1, 23, 30), (22, 0), (7, 0)) is True


def test_in_quiet_hours_overnight_morning():
    # 22:00-07:00, at 06:30
    assert _in_quiet_hours(_ts(2026, 1, 1, 6, 30), (22, 0), (7, 0)) is True


def test_in_quiet_hours_overnight_midday():
    assert _in_quiet_hours(_ts(2026, 1, 1, 12, 0), (22, 0), (7, 0)) is False


def test_in_quiet_hours_equal_bounds_never_quiet():
    assert _in_quiet_hours(_ts(2026, 1, 1, 12, 0), (5, 0), (5, 0)) is False


# ---------- evaluate: basic ----------

def test_no_trigger_returns_empty():
    assert evaluate_alerts({}, {}, now=1e9) == []


def test_all_false_returns_empty():
    states = {k: False for k in BINARY_ALERT_MAP}
    assert evaluate_alerts(states, {}, now=1e9) == []


def test_single_pendulum_hourly():
    out = evaluate_alerts({"pendulum_hourly": True}, {}, now=1e9)
    assert len(out) == 1
    assert isinstance(out[0], AlertSpec)
    assert out[0].alert_type == "pendulum"
    assert out[0].severity == SEV_WARNING
    assert out[0].notif_id.startswith("daikin_cycle_ml_")


def test_short_run_single_alert():
    out = evaluate_alerts({"short_run": True}, {}, now=1e9)
    assert len(out) == 1
    assert out[0].alert_type == "short_run"


def test_short_off_single_alert():
    out = evaluate_alerts({"short_off": True}, {}, now=1e9)
    assert len(out) == 1
    assert out[0].alert_type == "short_off"


def test_two_triggers_same_type_deduped():
    # both pendulum triggers -> single alert
    out = evaluate_alerts(
        {"pendulum_hourly": True, "pendulum_daily": True}, {}, now=1e9
    )
    assert len(out) == 1
    assert out[0].alert_type == "pendulum"


def test_multiple_distinct_types_emitted():
    out = evaluate_alerts(
        {"pendulum_hourly": True, "short_run": True, "short_off": True},
        {}, now=1e9,
    )
    types = sorted(a.alert_type for a in out)
    assert types == ["pendulum", "short_off", "short_run"]


def test_result_is_list_of_alert_specs():
    out = evaluate_alerts({"short_run": True}, {}, now=1e9)
    assert all(isinstance(a, AlertSpec) for a in out)


# ---------- aggregation ----------

def test_aggregation_suppresses_within_window():
    now = 1e9
    last = {"short_run": now - 60.0}  # 1min ago, agg window default 30min
    out = evaluate_alerts({"short_run": True}, {}, now=now, last_sent=last)
    assert out == []


def test_aggregation_allows_after_window():
    now = 1e9
    last = {"short_run": now - (DEFAULT_AGG_MIN + 1) * 60.0}
    out = evaluate_alerts({"short_run": True}, {}, now=now, last_sent=last)
    assert len(out) == 1


def test_aggregation_custom_window():
    now = 1e9
    last = {"short_run": now - 120.0}  # 2min ago
    opts = {"alert_aggregation_minutes": 1}  # 1 min window -> allow
    out = evaluate_alerts({"short_run": True}, opts, now=now, last_sent=last)
    assert len(out) == 1


def test_aggregation_different_types_independent():
    now = 1e9
    last = {"short_run": now - 60.0}
    out = evaluate_alerts(
        {"short_run": True, "short_off": True}, {}, now=now, last_sent=last
    )
    types = {a.alert_type for a in out}
    assert types == {"short_off"}


# ---------- quiet hours ----------

def test_quiet_hours_suppresses_warning():
    now = _ts(2026, 1, 1, 3, 0)  # 03:00
    opts = {
        "quiet_hours_enabled": True,
        "quiet_hours_start": "22:00",
        "quiet_hours_end": "07:00",
    }
    out = evaluate_alerts({"short_run": True}, opts, now=now)
    assert out == []


def test_quiet_hours_outside_window_allows():
    now = _ts(2026, 1, 1, 12, 0)
    opts = {
        "quiet_hours_enabled": True,
        "quiet_hours_start": "22:00",
        "quiet_hours_end": "07:00",
    }
    out = evaluate_alerts({"short_run": True}, opts, now=now)
    assert len(out) == 1


def test_quiet_hours_disabled_allows_all():
    now = _ts(2026, 1, 1, 3, 0)
    opts = {"quiet_hours_enabled": False}
    out = evaluate_alerts({"short_run": True}, opts, now=now)
    assert len(out) == 1


# ---------- persistent flag ----------

def test_persistent_default_on():
    out = evaluate_alerts({"short_run": True}, {}, now=1e9)
    assert out[0].persistent is True


def test_persistent_disabled_via_options():
    out = evaluate_alerts(
        {"short_run": True}, {"persistent_enabled": False}, now=1e9
    )
    assert out[0].persistent is False


# ---------- BINARY_ALERT_MAP sanity ----------

def test_map_covers_core_trigger_keys():
    keys = set(BINARY_ALERT_MAP)
    # Original 4 triggers must always be present.
    assert {"pendulum_hourly", "pendulum_daily",
            "short_run", "short_off"} <= keys
    # 12c added ML anomaly + setpoint oscillation triggers.
    assert {"ml_anomaly", "setpoint_osc"} <= keys


def test_map_contains_both_severities_defined():
    severities = {spec[1] for spec in BINARY_ALERT_MAP.values()}
    assert SEV_WARNING in severities
    assert SEV_CRITICAL not in severities  # only warning by default
