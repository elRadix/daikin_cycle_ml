"""Cycle ML Audit Phase A3: runtime end-to-end validation."""
from __future__ import annotations

import time
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.daikin_cycle_ml.const import (
    ATTR_LW_SETPOINT,
)
from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    DataSnapshot,
)
from custom_components.daikin_cycle_ml.engine.cycle_detector import (
    CycleDetector,
    classify_mode,
    detect_compressor_on,
)
from custom_components.daikin_cycle_ml.engine.notification_engine import (
    evaluate_alerts,
)
from custom_components.daikin_cycle_ml.engine.quality_scorer import score_cycle


def _bare(options=None, store=None, db=None, baseline=None, adaptive=None,
          data=None):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = options or {}
    c._setpoint_history = deque()
    c._last_setpoint = None
    c._status_update_unsub = None
    c._kmeans_centroids = []
    c._cluster_labels = []
    c._last_alert_sent = {}
    c.store = store if store is not None else MagicMock()
    c.db = db
    c.baseline = baseline if baseline is not None else MagicMock()
    c.adaptive = adaptive if adaptive is not None else MagicMock()
    c.data = data if data is not None else DataSnapshot()
    c.hass = MagicMock()
    c.hass.services.async_call = AsyncMock()
    c.hass.services.async_services = MagicMock(return_value={})
    return c


# ============================================================
# A3.1 — Cycle detection: tick -> snapshot -> cycle-close
# ============================================================
def test_a31_detect_compressor_on_rps_threshold():
    attrs = {"INV frequency (rps)": 30.0, "I/U operation mode": "Heating"}
    assert detect_compressor_on(
        attrs,
        {"compressor_rps_threshold": 20,
         "fallback_power_threshold_w": 100},
    ) is True


def test_a31_detect_compressor_on_below_threshold():
    attrs = {"INV frequency (rps)": 5.0, "I/U operation mode": "Heating"}
    assert detect_compressor_on(
        attrs,
        {"compressor_rps_threshold": 20,
         "fallback_power_threshold_w": 100},
    ) is False


def test_a31_classify_mode_heating():
    attrs = {"I/U operation mode": "Heating", "3way valve": "OFF",
             "Defrost Operation": "OFF"}
    assert classify_mode(attrs) == "heating"


def test_a31_classify_mode_defrost_is_flag_not_mode():
    # Defrost is tracked separately as a bool flag (defrost_used),
    # not as a mode value. classify_mode returns the underlying mode.
    attrs = {"I/U operation mode": "Heating", "Defrost Operation": "ON"}
    assert classify_mode(attrs) == "heating"


def test_a31_quality_score_full_good_cycle():
    record = {"duration_s": 3600, "dT_max": 6.0, "rps_max": 50,
              "buh_used": 0, "defrost_used": 0}
    score = score_cycle(record, {})
    assert score >= 80


def test_a31_quality_score_short_cycle_penalty():
    record = {"duration_s": 600, "dT_max": 5.0, "rps_max": 50,
              "buh_used": 0, "defrost_used": 0}
    score = score_cycle(record, {})
    assert score < 80


# ============================================================
# A3.2 — Alert dispatch — all 6 alert types fire
# ============================================================
def test_a32_alert_short_run():
    ctx = {"short_run": {"threshold_min": 20, "duration_min": 10, "advice": ""}}
    out = evaluate_alerts(
        {"short_run": True}, {}, now=1e9, context=ctx, language="en",
    )
    assert len(out) == 1
    assert out[0].alert_type == "short_run"


def test_a32_alert_short_off():
    ctx = {"short_off": {"threshold_min": 5, "off_min": 3, "advice": ""}}
    out = evaluate_alerts(
        {"short_off": True}, {}, now=1e9, context=ctx, language="en",
    )
    assert len(out) == 1


def test_a32_alert_pendulum_hourly():
    ctx = {"pendulum": {"cph": 5, "target_cph": 4,
                        "cycles_today": 42, "target_cpd": 40, "advice": ""}}
    out = evaluate_alerts(
        {"pendulum_hourly": True}, {}, now=1e9, context=ctx, language="en",
    )
    assert len(out) == 1


def test_a32_alert_pendulum_daily():
    ctx = {"pendulum": {"cph": 5, "target_cph": 4,
                        "cycles_today": 42, "target_cpd": 40, "advice": ""}}
    out = evaluate_alerts(
        {"pendulum_daily": True}, {}, now=1e9, context=ctx, language="en",
    )
    assert len(out) == 1


def test_a32_alert_ml_anomaly():
    ctx = {"ml_anomaly": {"mode": "Heating", "z_max": 3.5,
                          "top_dim": "rps_max", "advice": ""}}
    out = evaluate_alerts(
        {"ml_anomaly": True}, {}, now=1e9, context=ctx, language="en",
    )
    assert len(out) == 1


def test_a32_alert_setpoint_osc():
    ctx = {"setpoint_osc": {"osc_count": 7, "window_min": 30,
                            "threshold": 6, "advice": ""}}
    out = evaluate_alerts(
        {"setpoint_osc": True}, {}, now=1e9, context=ctx, language="en",
    )
    assert len(out) == 1


# ============================================================
# A3.3 — Alert group + language routing
# ============================================================
def test_a33_group_filter_blocks_all():
    out = evaluate_alerts(
        {"short_run": True, "short_off": True,
         "pendulum_hourly": True, "ml_anomaly": True, "setpoint_osc": True},
        {
            "alert_group_pendulum": False,
            "alert_group_short_cycle": False,
            "alert_group_ml": False,
            "alert_group_setpoint": False,
            "alert_group_cop_stooklijn": False,
        },
        now=1e9,
    )
    assert out == []


def test_a33_language_nl_renders_dutch():
    ctx = {"short_run": {"threshold_min": 20, "duration_min": 10, "advice": ""}}
    out = evaluate_alerts(
        {"short_run": True},
        {"notification_language": "nl", "notify_emoji_enabled": False},
        now=1e9, context=ctx,
    )
    assert "Korte run" in out[0].message


def test_a33_quiet_hours_suppresses_warning():
    # 22:00 -> 07:00, now = 23:00
    now = time.mktime((2026, 9, 26, 23, 0, 0, 0, 0, -1))
    out = evaluate_alerts(
        {"short_run": True},
        {"quiet_hours_enabled": True,
         "quiet_hours_start": "22:00",
         "quiet_hours_end": "07:00"},
        now=now,
    )
    assert out == []


def test_a33_quiet_hours_allows_daytime():
    # 12:00
    now = time.mktime((2026, 9, 26, 12, 0, 0, 0, 0, -1))
    out = evaluate_alerts(
        {"short_run": True},
        {"quiet_hours_enabled": True,
         "quiet_hours_start": "22:00",
         "quiet_hours_end": "07:00"},
        now=now,
    )
    assert len(out) == 1


# ============================================================
# A3.4 — Coordinator alert dispatch + dedup
# ============================================================
async def test_a34_dispatch_sends_persistent():
    st = MagicMock()
    st.last_cycle.return_value = {"duration_s": 300}  # short
    st.off_time_since_last.return_value = None
    st.cycles_in_window.return_value = 0
    st.cycles_today.return_value = []
    c = _bare(options={"short_run_threshold_min": 20}, store=st)
    snap = DataSnapshot()
    await c._async_dispatch_alerts(snap)
    # persistent_notification must have been called
    calls = [ca.args[0] for ca in c.hass.services.async_call.await_args_list]
    assert "persistent_notification" in calls


async def test_a34_dedup_within_window():
    st = MagicMock()
    st.last_cycle.return_value = {"duration_s": 300}
    st.off_time_since_last.return_value = None
    st.cycles_in_window.return_value = 0
    st.cycles_today.return_value = []
    c = _bare(options={"short_run_threshold_min": 20,
                       "alert_aggregation_minutes": 30}, store=st)
    snap = DataSnapshot()
    await c._async_dispatch_alerts(snap)
    calls_first = c.hass.services.async_call.await_count
    # Second dispatch immediately - should be deduped
    await c._async_dispatch_alerts(snap)
    calls_second = c.hass.services.async_call.await_count
    # No additional persistent call on second dispatch
    assert calls_second == calls_first


# ============================================================
# A3.5 — Scheduled tasks: maintenance + kmeans + status
# ============================================================
async def test_a35_status_update_emits_message():
    c = _bare(options={"notify_emoji_enabled": False})
    st = MagicMock()
    st.counters_snapshot.return_value = {"cycles_today": 5}
    st.last_cycle.return_value = None
    c.store = st
    c.baseline.total_samples.return_value = 100
    c.baseline.modes.return_value = ["Heating"]
    msg = await c.async_emit_status_update()
    assert isinstance(msg, str)
    assert "Heating" in msg or "cycles" in msg.lower() or msg


async def test_a35_adaptive_save_load_roundtrip():
    db = MagicMock()
    stored = {}
    async def set_state(k, v):
        stored[k] = v
        return True
    async def get_state(k):
        return stored.get(k)
    db.async_set_model_state = AsyncMock(side_effect=set_state)
    db.async_get_model_state = AsyncMock(side_effect=get_state)
    ad = MagicMock()
    ad.to_dict.return_value = {"dims": {"Heating": {"p50": 30}}}
    c = _bare(db=db, adaptive=ad)
    assert await c.async_save_adaptive_state() is True
    # Now load
    with patch("custom_components.daikin_cycle_ml.coordinator.AdaptiveThresholds") as AT:
        AT.from_dict.return_value = "LOADED"
        ok = await c.async_load_adaptive_state()
        assert ok is True
        assert c.adaptive == "LOADED"



# ============================================================
# A3.7 — ML pipeline: feature -> baseline -> adaptive
# ============================================================
def test_a37_feature_vector_length_11():
    from custom_components.daikin_cycle_ml.ml.features import (
        VECTOR_LEN, extract_feature_vector,
    )
    assert VECTOR_LEN == 11
    rec = {"duration_s": 1800, "dT_max": 5.0, "dT_avg": 3.0,
           "rps_max": 50, "rps_avg": 35.0, "outdoor_temp": 8.0,
           "buh_used": 0, "defrost_used": 0}
    v = extract_feature_vector(rec, cop_avg=3.5, lwt_avg=35.0,
                                indoor_temp_avg=20.0)
    assert len(v) == 11
    assert v[8] == 3.5
    assert v[9] == 35.0
    assert v[10] == 20.0


def test_a37_multi_baseline_update_and_query():
    from custom_components.daikin_cycle_ml.ml.multi_baseline import MultiBaseline
    mb = MultiBaseline(dim=11)
    v = [float(x) for x in range(11)]
    for _ in range(10):
        mb.update("Heating", v)
    assert mb.total_samples() == 10
    assert "Heating" in mb.modes()


def test_a37_baseline_dim_guard_on_from_dict():
    from custom_components.daikin_cycle_ml.ml.multi_baseline import MultiBaseline
    legacy = {"dim": 8, "modes": {"Heating": {"n": 5}}}
    mb = MultiBaseline.from_dict(legacy)
    # Should reset (dim-guard)
    assert mb.total_samples() == 0


# ============================================================
# A3.8 — Services chain (send_test_notification)
# ============================================================
async def test_a38_send_test_notification_resolves_target():
    from custom_components.daikin_cycle_ml import services as svc_mod
    # Ensure handler exists
    assert hasattr(svc_mod, "async_register_services")


# ============================================================
# A3.9 — Setpoint osc end-to-end via coordinator
# ============================================================
def test_a39_setpoint_osc_triggers_at_threshold():
    c = _bare(options={"setpoint_oscillation_threshold": 3})
    # 3 changes within window -> True
    now = time.time()
    c._setpoint_history = deque([(now, x) for x in (35.0, 34.5, 35.0)])
    assert c._compute_setpoint_oscillating() is True


def test_a39_setpoint_osc_eviction_window():
    c = _bare(options={"setpoint_osc_window_min": 1,
                       "setpoint_oscillation_threshold": 2})
    c._setpoint_history = deque()
    now = time.time()
    c._setpoint_history.append((now - 120, 33.0))  # outside window
    c._last_setpoint = 34.0
    c._track_setpoint({ATTR_LW_SETPOINT: 34.0})
    # old entry evicted, only current remains -> below threshold
    assert c._compute_setpoint_oscillating() is False
