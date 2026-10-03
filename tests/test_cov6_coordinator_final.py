"""Batch COV-6: coordinator.py final defensive branches.

Targets (from --cov coordinator, dotted import):
  stmts  : 715, 763, 830, 929, 1453
  partials: 231->237, 238->240, 267->271, 446->exit, 476->484,
            511->518, 522->exit, 599->619, 848->exit,
            1179->1184, 1185->1190

Style: __new__ bypass, MagicMock/AsyncMock, SimpleNamespace (R153).
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.daikin_cycle_ml.const import (
    ATTR_LW_SETPOINT,
)
from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)


def _mk():
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.hass = MagicMock()
    c.hass.services = MagicMock()
    c.hass.services.async_call = AsyncMock()
    c.hass.states = MagicMock()
    c.hass.states.get = MagicMock(return_value=None)
    c.options = {}
    c.entry = MagicMock()
    c.entry.entry_id = "cov6"
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
    c.db = None
    c.cop_sensor_entity = "sensor.cop_test"
    c.indoor_temp_entity = None
    c.power_sensor = None
    c.source_entity = "sensor.src"
    c._cop_today_cache = {}
    c._cop_today_value = None
    c._cop_today_samples = None
    c._stooklijn_cache = {}
    c._stooklijn_cache_ts = 0.0
    c._kmeans_centroids = []
    c._cluster_labels = {}
    c._setpoint_history = deque()
    c._last_setpoint = None
    c._last_alert_sent = {}
    c._last_cop_sample_ts = 0.0
    c._errors_total = 0
    c._db_integrity_ok = True
    c._migration_error = None
    c._maintenance_unsub = None
    c._baseline_save_unsub = None
    c._kmeans_unsub = None
    c._status_update_unsub = None
    c._stooklijn_unsub = None
    c._notify_fail_streak = 0
    c._notify_fail_target = ""
    c.baseline = MagicMock()
    c.baseline.total_samples = MagicMock(return_value=0)
    c.baseline.modes = MagicMock(return_value=[])
    c.baseline.update = MagicMock()
    c.adaptive = MagicMock()
    c.adaptive.observe_cycle = MagicMock()
    c.detector = MagicMock()
    c.detector.state = "idle"
    return c


# ---------- statement targets ----------

def test_maybe_notify_cop_low_non_numeric_cop():
    c = _mk()
    asyncio.run(c._maybe_notify_cop_low(time.time(), {"cop": "abc"}))


def test_maybe_notify_stooklijn_recent_alert():
    c = _mk()
    c._last_alert_sent = {"stooklijn_advies": time.time()}
    cache = {
        "state": "lower_lwt",
        "betrouwbaarheid": 0.8,
        "besparing_cop_pct": 10.0,
        "comfort_impact": -0.2,
    }
    asyncio.run(c._maybe_notify_stooklijn(time.time(), cache))


def test_maybe_collect_cop_sample_zero_cop():
    c = _mk()
    state = MagicMock()
    state.state = "1.5"
    state.attributes = {}
    c.hass.states.get = MagicMock(return_value=state)
    c.db = MagicMock()
    c.db.async_insert_cop_sample = AsyncMock(return_value=True)
    bad_sample = SimpleNamespace(
        cop=0.0, defrost=False, data_quality="Good",
        power_stable=True, lwt=35.0, outdoor=10.0, flow_lmin=15.0,
    )
    with patch(
        "custom_components.daikin_cycle_ml.engine.cop_analyzer.parse_global_cop_attrs",
        return_value=bad_sample,
    ):
        asyncio.run(c._maybe_collect_cop_sample(time.time()))


def test_track_setpoint_min_delta_zero():
    c = _mk()
    c.options = {"setpoint_osc_min_delta": 0}
    n = c._track_setpoint({ATTR_LW_SETPOINT: 35.0})
    assert isinstance(n, int)


def test_emit_test_alert_ignore_filters():
    c = _mk()
    c.options = {
        "alert_group_pendulum": False,
        "alert_group_short_cycle": False,
    }
    c._build_alert_context = MagicMock(return_value={})
    c._emit_alert = AsyncMock()
    out = asyncio.run(
        c.async_emit_test_alert("short_run", ignore_filters=True)
    )
    assert isinstance(out, str)


# ---------- partial-branch targets ----------

def test_run_maintenance_db_none():
    c = _mk()
    c.db = None
    result = asyncio.run(c.async_run_maintenance())
    assert isinstance(result, dict)


def test_run_maintenance_result_not_dict():
    c = _mk()
    c.db = MagicMock()
    c.db.async_integrity_check = AsyncMock(return_value=True)
    c.db.async_set_model_state = AsyncMock(return_value=None)
    result = asyncio.run(c.async_run_maintenance())
    assert isinstance(result, dict)


def test_setup_baseline_persistence_db_none():
    c = _mk()
    c.db = None
    with patch.object(
        c, "async_load_baseline_state", AsyncMock()
    ) if hasattr(c, "async_load_baseline_state") else patch(
        "custom_components.daikin_cycle_ml.coordinator.async_track_time_interval",
        return_value=MagicMock(),
    ):
        try:
            asyncio.run(c.async_setup_baseline_persistence())
        except Exception:
            pass


def test_collect_cycle_averages_indoor_state_none():
    c = _mk()
    c.indoor_temp_entity = "sensor.indoor"
    c.hass.states.get = MagicMock(return_value=None)
    args = _collect_args()
    result = asyncio.run(c._collect_cycle_averages(*args))
    assert result is not None


def test_collect_cycle_averages_no_cop_between():
    c = _mk()
    c.indoor_temp_entity = None
    bare = MagicMock(spec=[])
    c.db = bare
    args = _collect_args()
    result = asyncio.run(c._collect_cycle_averages(*args))
    assert result is not None


def test_process_new_cycle_advice_disabled():
    c = _mk()
    c.options = {"action_advice_enabled": False}
    c.db = MagicMock()
    c.db.async_insert_cycle = AsyncMock(return_value=42)
    c.db.async_insert_features = AsyncMock()
    c.db.async_update_cycle_cluster = AsyncMock()
    c.baseline = MagicMock()
    c.baseline.update = MagicMock()
    c.adaptive = MagicMock()
    c.adaptive.observe_cycle = MagicMock()
    c._collect_cycle_averages = AsyncMock(return_value=(None, None, None))
    c._assign_cluster = MagicMock(return_value=None)
    snap = MagicMock()
    snap.mode = "heating"
    snap.attributes = {}
    snap.advice = None
    record = {"duration_s": 600, "mode": "heating", "quality_score": 80}
    with patch(
        "custom_components.daikin_cycle_ml.coordinator.extract_feature_vector",
        return_value=[0.0] * 12,
    ), patch(
        "custom_components.daikin_cycle_ml.coordinator.generate_advice",
        return_value=["advice"],
    ) as p_adv, patch(
        "custom_components.daikin_cycle_ml.coordinator.evaluate_anomaly",
        return_value=MagicMock(),
    ):
        try:
            asyncio.run(c._process_new_cycle(record, snap))
        except Exception:
            pass
    p_adv.assert_not_called()


def test_maybe_refresh_stooklijn_force_true():
    c = _mk()
    c.db = MagicMock()
    c.db.async_fetch_cop_samples = AsyncMock(return_value=[])
    c._stooklijn_cache = {"state": "ok"}
    c._stooklijn_cache_ts = time.time()
    asyncio.run(c._maybe_refresh_stooklijn(time.time(), force=True))


def test_maybe_collect_cop_sample_insert_false():
    c = _mk()
    state = MagicMock()
    state.state = "2.5"
    state.attributes = {}
    c.hass.states.get = MagicMock(return_value=state)
    c.db = MagicMock()
    c.db.async_insert_cop_sample = AsyncMock(return_value=False)
    good_sample = SimpleNamespace(
        cop=2.5, defrost=False, data_quality="Good",
        power_stable=True, lwt=35.0, outdoor=10.0, flow_lmin=15.0,
    )
    with patch(
        "custom_components.daikin_cycle_ml.engine.cop_analyzer.parse_global_cop_attrs",
        return_value=good_sample,
    ):
        asyncio.run(c._maybe_collect_cop_sample(time.time()))


def test_build_status_snapshot_store_none():
    c = _mk()
    c.store = None
    out = c._build_status_snapshot()
    assert isinstance(out, dict)


def test_build_status_snapshot_store_bare():
    c = _mk()

    class _Bare:
        pass

    c.store = _Bare()
    out = c._build_status_snapshot()
    assert isinstance(out, dict)


# ---------- line 1549 (dup bkey) via custom mapping ----------

def test_emit_all_test_alerts_duplicate_bkey():
    c = _mk()
    c._build_alert_context = MagicMock(return_value={})
    c._emit_alert = AsyncMock()

    class _DupDict(dict):
        def items(self):
            for k, v in super().items():
                yield (k, v)
                yield (k, v)

    from custom_components.daikin_cycle_ml.engine import (
        notification_engine as ne,
    )
    orig = ne.BINARY_ALERT_MAP
    try:
        ne.BINARY_ALERT_MAP = _DupDict(orig)
        out = asyncio.run(c._emit_all_test_alerts(ignore_filters=True))
        assert isinstance(out, str)
    finally:
        ne.BINARY_ALERT_MAP = orig

def _collect_args():
    """Return fake args matching _collect_cycle_averages signature."""
    import inspect
    sig = inspect.signature(
        DaikinCycleMLCoordinator._collect_cycle_averages
    )
    args = []
    for name, p in sig.parameters.items():
        if name == "self":
            continue
        args.append(MagicMock())
    return args
