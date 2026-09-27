"""Batch 52e-2: coverage-fill for coordinator.py (91 missing lines).

All coordinator except/fallback branches. Follows existing test style
(coordinator.__new__ + asyncio.run) for consistency.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    DataSnapshot,
)
from custom_components.daikin_cycle_ml.ml.adaptive_thresholds import (
    AdaptiveThresholds,
)
from custom_components.daikin_cycle_ml.ml.features import VECTOR_LEN
from custom_components.daikin_cycle_ml.ml.multi_baseline import (
    MultiBaseline,
)

class _RaisingDetector:
    """Detector whose .state property raises (line 394-395 coverage)."""

    @property
    def state(self):
        raise RuntimeError("boom")


def _mk(options=None, data=None):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.hass = MagicMock()
    c.hass.services = MagicMock()
    c.hass.services.async_call = AsyncMock()
    c.hass.states = MagicMock()
    c.hass.states.get = MagicMock(return_value=None)
    c.options = dict(options or {})
    c.entry = MagicMock()
    c.entry.entry_id = "test"
    if data is not None:
        c.data = data
    else:
        c.data = MagicMock()
        c.data.state = "idle"
        c.data.mode = "heating"
        c.data.attributes = {}
        c.data.anomaly = None
        c.data.advice = []
        c.data.last_record = None
    c.store = MagicMock()
    c.store.last_cycle = MagicMock(return_value=None)
    c.store.cycles_in_window = MagicMock(return_value=0)
    c.store.cycles_today = MagicMock(return_value=[])
    c.store.counters_snapshot = MagicMock(return_value={})
    c.store.off_time_since_last = MagicMock(return_value=None)
    c.detector = MagicMock()
    c.detector.state = "idle"
    c.db = MagicMock()
    c._last_alert_sent = {}
    c._setpoint_history = deque()
    c._last_setpoint = None
    c._cop_today_value = None
    c._cop_today_samples = None
    c._cop_today_cache = {}
    c._stooklijn_cache = {}
    c._stooklijn_cache_ts = 0.0
    c._last_cop_sample_ts = 0.0
    c._baseline_save_unsub = None
    c._kmeans_unsub = None
    c._stooklijn_unsub = None
    c._maintenance_unsub = None
    c._status_update_unsub = None
    c._kmeans_centroids = []
    c._cluster_labels = {}
    c._cycle_lwt_sum = 0.0
    c._cycle_lwt_count = 0
    c._cycle_indoor_sum = 0.0
    c._cycle_indoor_count = 0
    c._notify_fail_streak = 0
    c._notify_fail_target = ""
    c._db_integrity_ok = True
    c._migration_error = None
    c._errors_total = 0
    c.source_entity = "sensor.x"
    c.cop_sensor_entity = "sensor.cop"
    c.power_sensor = None
    c.indoor_temp_entity = None
    c.baseline = MultiBaseline(VECTOR_LEN)
    c.adaptive = AdaptiveThresholds(min_samples=20)
    return c


# ---------- A. setup_persistence migration branch (241-246) ----------

def test_setup_baseline_persistence_migration_saves():
    c = _mk()
    fake = {"some": "data"}
    mb = MagicMock()
    mb._migrated_from_dim = 11
    mb.dim = 12
    mb.modes.return_value = ["heating"]
    mb.total_samples.return_value = 3
    mb.to_dict.return_value = {"dim": 12}
    c.db.async_get_model_state = AsyncMock(return_value=fake)
    c.db.async_set_model_state = AsyncMock(return_value=True)
    c.db.async_ensure_cluster_column = AsyncMock()
    with patch.object(MultiBaseline, "from_dict", return_value=mb), \
         patch.object(c, "async_load_adaptive_state",
                      new=AsyncMock(return_value=True)), \
         patch.object(c, "_load_kmeans_state",
                      new=AsyncMock(return_value=False)), \
         patch("custom_components.daikin_cycle_ml.coordinator.async_track_time_interval",
               return_value=MagicMock()):
        asyncio.run(c.async_setup_baseline_persistence())
    assert c.baseline is mb
    c.db.async_set_model_state.assert_awaited()


def test_setup_baseline_persistence_restore_exception():
    c = _mk()
    c.db.async_get_model_state = AsyncMock(side_effect=RuntimeError("boom"))
    c.db.async_ensure_cluster_column = AsyncMock()
    with patch.object(c, "async_load_adaptive_state",
                      new=AsyncMock(return_value=True)), \
         patch.object(c, "_load_kmeans_state",
                      new=AsyncMock(return_value=False)), \
         patch("custom_components.daikin_cycle_ml.coordinator.async_track_time_interval",
               return_value=MagicMock()):
        asyncio.run(c.async_setup_baseline_persistence())


# ---------- A2. _accumulate_cycle_samples (394-395) ----------

def test_accumulate_cycle_samples_detector_raises():
    c = _mk()
    c.detector = _RaisingDetector()
    c._accumulate_cycle_samples({"lwt": 30.0})


def test_accumulate_cycle_samples_active_with_lwt_and_indoor():
    c = _mk()
    c.detector.state = "active"
    c.indoor_temp_entity = "sensor.indoor"
    st = MagicMock()
    st.state = "21.5"
    c.hass.states.get = MagicMock(return_value=st)
    c._accumulate_cycle_samples({"lwt": 30.0})
    assert c._cycle_lwt_count == 1
    assert c._cycle_indoor_count == 1


def test_accumulate_cycle_samples_indoor_invalid():
    c = _mk()
    c.detector.state = "active"
    c.indoor_temp_entity = "sensor.indoor"
    st = MagicMock()
    st.state = "not-a-number"
    c.hass.states.get = MagicMock(return_value=st)
    c._accumulate_cycle_samples({"lwt": 30.0})


# ---------- A3. _collect_cycle_averages indoor (426) ----------

def test_collect_cycle_averages_indoor_count():
    c = _mk()
    c._cycle_indoor_sum = 42.0
    c._cycle_indoor_count = 2
    cop, lwt, indoor = asyncio.run(c._collect_cycle_averages({}))
    assert indoor == 21.0


# ---------- A4. _process_new_cycle cluster assign (500-501) ----------

def test_process_new_cycle_cluster_assign_fails():
    c = _mk()
    c.db.async_insert_cycle = AsyncMock(return_value=42)
    c.db.async_insert_features = AsyncMock(return_value=None)
    c.db.async_update_cycle_cluster = AsyncMock(return_value=None)
    c._assign_cluster = MagicMock(side_effect=RuntimeError("boom"))
    snap = DataSnapshot(last_sample_ts=time.time())
    snap.mode = "heating"
    asyncio.run(c._process_new_cycle({}, snap))


def test_process_new_cycle_ml_pipeline_exception():
    c = _mk()
    c.db = None
    c.adaptive.observe_cycle = MagicMock(side_effect=RuntimeError("boom"))
    snap = DataSnapshot(last_sample_ts=time.time())
    snap.mode = "heating"
    asyncio.run(c._process_new_cycle({}, snap))


# ---------- B. _refresh_cop_today (528-529, 534-535, 552-553) ----------

def test_refresh_cop_today_empty_rows():
    c = _mk()
    c.db.async_fetch_cop_samples = AsyncMock(return_value=[])
    asyncio.run(c._refresh_cop_today(time.time()))
    assert c._cop_today_cache == {}


def test_refresh_cop_today_no_todays():
    c = _mk()
    old_ts = time.time() - 86400 * 5
    c.db.async_fetch_cop_samples = AsyncMock(return_value=[
        {"ts": old_ts, "cop": 3.0},
    ])
    asyncio.run(c._refresh_cop_today(time.time()))
    assert c._cop_today_cache == {}


def test_refresh_cop_today_week_fetch_fails():
    c = _mk()
    now = time.time()
    async def _fetch(days=1):
        if days == 1:
            return [{"ts": now, "cop": 3.0}]
        raise RuntimeError("boom")
    c.db.async_fetch_cop_samples = AsyncMock(side_effect=_fetch)
    asyncio.run(c._refresh_cop_today(now))
    assert c._cop_today_cache.get("cop") == 3.0


def test_refresh_cop_today_outer_except():
    c = _mk()
    now = time.time()
    c.db.async_fetch_cop_samples = AsyncMock(return_value=[
        {"ts": "not-a-ts", "cop": "not-a-cop"},
        {"ts": now, "cop": -1.0},
    ])
    asyncio.run(c._refresh_cop_today(now))


# ---------- B2. _maybe_refresh_stooklijn (566-634) ----------

def test_maybe_refresh_stooklijn_dhw_skip():
    c = _mk()
    c.db.async_fetch_cop_samples = AsyncMock(return_value=[])
    c.data = SimpleNamespace(mode="dhw")
    asyncio.run(c._maybe_refresh_stooklijn(time.time()))
    assert c._stooklijn_cache.get("reason") == "dhw_active"


def test_maybe_refresh_stooklijn_dhw_already_cached():
    c = _mk()
    c.data = SimpleNamespace(mode="dhw")
    c._stooklijn_cache = {"reason": "dhw_active"}
    asyncio.run(c._maybe_refresh_stooklijn(time.time()))


def test_maybe_refresh_stooklijn_cache_hit():
    c = _mk()
    c._stooklijn_cache = {"state": "ok"}
    c._stooklijn_cache_ts = time.time()
    asyncio.run(c._maybe_refresh_stooklijn(time.time()))


def test_maybe_refresh_stooklijn_rows_not_list():
    c = _mk()
    c.db.async_fetch_cop_samples = AsyncMock(return_value=None)
    asyncio.run(c._maybe_refresh_stooklijn(time.time()))


def test_maybe_refresh_stooklijn_skips_invalid_cops():
    c = _mk()
    now = time.time()
    c.db.async_fetch_cop_samples = AsyncMock(return_value=[
        {"cop": "not-a-number", "ts": now},
        {"cop": -1.0, "ts": now},
    ])
    asyncio.run(c._maybe_refresh_stooklijn(now))
    assert c._stooklijn_cache.get("samples") == 0


def test_maybe_refresh_stooklijn_analyze_exception():
    c = _mk()
    now = time.time()
    c.db.async_fetch_cop_samples = AsyncMock(return_value=[
        {"cop": 3.0, "ts": now, "mode": "heating"},
    ])
    with patch(
        "custom_components.daikin_cycle_ml.engine.cop_analyzer.analyze_stooklijn",
        side_effect=RuntimeError("boom"),
    ):
        asyncio.run(c._maybe_refresh_stooklijn(now))


# ---------- B3. _maybe_notify_cop_low (700-701) ----------

def test_maybe_notify_cop_low_debounce():
    c = _mk()
    now = time.time()
    cop_dict = {"cop": 2.0, "samples_today": 5}
    c._last_alert_sent = {"cop_low": now - 3600}
    asyncio.run(c._maybe_notify_cop_low(now, cop_dict))


def test_maybe_notify_cop_low_emit_exception():
    c = _mk()
    now = time.time()
    cop_dict = {"cop": 2.0, "samples_today": 5}
    c._emit_alert = AsyncMock(side_effect=RuntimeError("boom"))
    asyncio.run(c._maybe_notify_cop_low(now, cop_dict))


# ---------- B4. _maybe_notify_stooklijn (715-716, 735-736) ----------

def test_maybe_notify_stooklijn_nan_values():
    c = _mk()
    cache = {
        "state": "verlaag_lwt_2c",
        "betrouwbaarheid": "not-a-number",
        "besparing_cop_pct": 10.0,
        "comfort_impact": 0.0,
    }
    asyncio.run(c._maybe_notify_stooklijn(time.time(), cache))


def test_maybe_notify_stooklijn_emit_exception():
    c = _mk()
    cache = {
        "state": "verlaag_lwt_2c",
        "betrouwbaarheid": 0.9,
        "besparing_cop_pct": 10.0,
        "comfort_impact": -0.2,
    }
    c._emit_alert = AsyncMock(side_effect=RuntimeError("boom"))
    asyncio.run(c._maybe_notify_stooklijn(time.time(), cache))


# ---------- B5. _effective_threshold (819-820) ----------

def test_effective_threshold_suggest_raises():
    c = _mk(options={"adaptive_thresholds_enabled": True})
    c.adaptive.suggest = MagicMock(side_effect=RuntimeError("boom"))
    assert c._effective_threshold("short_run_threshold_min", 20) == 20


# ---------- B6. _track_setpoint min_delta reset (887) ----------

def test_track_setpoint_min_delta_reset():
    c = _mk(options={"setpoint_osc_min_delta": "invalid"})
    n = c._track_setpoint({"lwt_setpoint": 30.0})
    assert n >= 0


# ---------- C. _snap_attr (1193, 1197) ----------

def test_snap_attr_raw_attrs_fallback():
    c = _mk()
    snap = SimpleNamespace(raw_attrs={"outdoor_temp": 7.5})
    assert c._snap_attr(snap, "outdoor_temp") == 7.5


def test_snap_attr_none_value_returns_none():
    c = _mk()
    snap = SimpleNamespace(raw_attrs={"a": None})
    assert c._snap_attr(snap, "a", "b") is None


# ---------- C2. _setpoint_current (1205, 1211) ----------

def test_setpoint_current_attrs_hit():
    c = _mk()
    snap = SimpleNamespace(attributes={"lwt_setpoint": 35.0})
    assert c._setpoint_current(snap) == 35.0


def test_setpoint_current_history_hit():
    c = _mk()
    c._setpoint_history = deque([(1.0, 28.5), (2.0, 30.0)])
    snap = SimpleNamespace(attributes={})
    assert c._setpoint_current(snap) == 30.0


def test_setpoint_current_history_plain_value():
    c = _mk()
    c._setpoint_history = deque([28.5])
    snap = SimpleNamespace(attributes={})
    assert c._setpoint_current(snap) == 28.5


# ---------- C3. _setpoint_delta (1226-1232) ----------

def test_setpoint_delta_mixed_types():
    c = _mk()
    c._setpoint_history = deque([(1.0, 28.5), "bad", (2.0, 30.0), (3.0, "bad")])
    d = c._setpoint_delta(SimpleNamespace(attributes={}))
    assert d == pytest.approx(1.5)


def test_setpoint_delta_less_than_two():
    c = _mk()
    c._setpoint_history = deque([(1.0, 30.0)])
    assert c._setpoint_delta(SimpleNamespace(attributes={})) is None


# ---------- C4. _build_alert_context (1277-1278, 1293-1294, 1377-1378) ----------

def test_build_alert_context_basic():
    c = _mk()
    snap = SimpleNamespace(
        mode="unknown", attributes={"outdoor_temp": 5.5},
        advice=[], anomaly=None, last_record=None,
    )
    ctx = c._build_alert_context(snap)
    assert "pendulum" in ctx
    assert "ml_anomaly" in ctx


def test_build_alert_context_mode_fallback_from_last_cycle():
    c = _mk()
    c.store.last_cycle = MagicMock(return_value={"mode": "heating"})
    snap = SimpleNamespace(
        mode="unknown", attributes={},
        advice=[], anomaly=None, last_record=None,
    )
    ctx = c._build_alert_context(snap)
    assert ctx["pendulum"]["mode"] == "heating"


def test_build_alert_context_f_formatter_invalid():
    c = _mk()
    snap = SimpleNamespace(
        mode="heating", attributes={"outdoor_temp": "not-a-num"},
        advice=[], anomaly=None, last_record=None,
    )
    ctx = c._build_alert_context(snap)
    assert ctx["pendulum"]["outdoor"] == "\u2014"


def test_build_alert_context_top_dim_out_of_range():
    c = _mk()
    anomaly = SimpleNamespace(
        severity="warning", is_anomaly=True,
        max_abs_z=3.5, top_dim=999,
    )
    snap = SimpleNamespace(
        mode="heating", attributes={},
        advice=[], anomaly=anomaly, last_record=None,
    )
    ctx = c._build_alert_context(snap)
    assert ctx["ml_anomaly"]["top_dim"].startswith("dim ")


# ---------- C5. _build_rich_status_snapshot (1037-1069) ----------

def test_build_rich_status_snapshot_all_failures():
    c = _mk()
    c._build_status_snapshot = MagicMock(return_value={})
    c.store.cycles_in_window = MagicMock(side_effect=RuntimeError("boom"))
    c.store.counters_snapshot = MagicMock(side_effect=RuntimeError("boom"))
    snap = SimpleNamespace(attributes=None, last_cycle="not-a-dict")
    c.data = snap
    c.db = MagicMock()
    c._db_cycle_stats = AsyncMock(side_effect=RuntimeError("boom"))
    out = asyncio.run(c._build_rich_status_snapshot())
    assert isinstance(out, dict)
    assert out.get("cycles_per_hour") is None


# ---------- C6. _db_cycle_stats exception (1090-1091) ----------

def test_db_cycle_stats_exception():
    c = _mk()
    c.db.async_count_cycles_since = AsyncMock(side_effect=RuntimeError("boom"))
    out = asyncio.run(c._db_cycle_stats())
    assert out["db_total"] is None


# ---------- C7. async_emit_test_alert filtered (1407-1411, 1468) ----------

def test_async_emit_test_alert_filtered_returns_message():
    c = _mk()
    c.data = SimpleNamespace(
        mode="heating", attributes={},
        advice=[], anomaly=None, last_record=None,
    )
    c._build_alert_context = MagicMock(return_value={})
    with patch(
        "custom_components.daikin_cycle_ml.engine.notification_engine.evaluate_alerts",
        return_value=[],
    ):
        out = asyncio.run(
            c.async_emit_test_alert("short_run", ignore_filters=True)
        )
    assert "[filtered]" in out


# ---------- C8. _emit_all_test_alerts seen-skip (1507) ----------

def test_emit_all_test_alerts_basic_paths():
    c = _mk()
    c.data = SimpleNamespace(
        mode="heating", attributes={},
        advice=[], anomaly=None, last_record=None,
    )
    c._build_alert_context = MagicMock(return_value={})
    c._emit_alert = AsyncMock()
    out = asyncio.run(c._emit_all_test_alerts(ignore_filters=True))
    assert "cop_low" in out

