"""Batch COV-3: coordinator.py edge-case coverage (95% -> 96%+).

Targets defensive branches in async_run_stooklijn_analysis,
_refresh_cop_today, _resolve_cop_sample_mode, _assign_cluster,
cluster_label, _build_rich_status_snapshot, _build_alert_context,
_db_cycle_stats, _maybe_notify_cop_low.

Style matches existing tests: DaikinCycleMLCoordinator.__new__ +
asyncio.run, no HA fixtures, SimpleNamespace args (R153).
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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
    c.entry.entry_id = "cov3"
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
    c._cop_today_cache = {}
    c._cop_today_value = None
    c._cop_today_samples = None
    c._stooklijn_cache = {}
    c._stooklijn_cache_ts = 0.0
    c._kmeans_centroids = []
    c._cluster_labels = {}
    c._setpoint_history = []
    c._last_alert_sent = {}
    c._errors_total = 0
    return c


def test_run_stooklijn_analysis_success():
    c = _mk()
    c.db = MagicMock()
    c._maybe_refresh_stooklijn = AsyncMock()
    c._refresh_cop_today = AsyncMock()
    c._maybe_notify_cop_low = AsyncMock()
    c._maybe_notify_stooklijn = AsyncMock()
    c._stooklijn_cache = {"state": "ok", "samples": 7}
    out = asyncio.run(c.async_run_stooklijn_analysis())
    assert out == {"ok": True, "state": "ok", "samples": 7}


def test_run_stooklijn_analysis_refresh_fails():
    c = _mk()
    c.db = MagicMock()
    c._maybe_refresh_stooklijn = AsyncMock(side_effect=RuntimeError("boom"))
    c._refresh_cop_today = AsyncMock()
    out = asyncio.run(c.async_run_stooklijn_analysis())
    assert out == {"ok": False, "reason": "refresh_failed"}


def test_refresh_cop_today_exception_clears_cache():
    c = _mk()
    c.db = MagicMock()
    c.db.async_fetch_cop_samples = AsyncMock(
        return_value=[{"ts": 1.0, "cop": 2.0}]
    )
    c._cop_today_cache = {"stale": True}
    with patch(
        "custom_components.daikin_cycle_ml.coordinator.time.localtime",
        side_effect=RuntimeError("boom"),
    ):
        asyncio.run(c._refresh_cop_today(time.time()))
    assert c._cop_today_cache == {}


def test_resolve_cop_sample_mode_no_data():
    c = _mk()
    c.data = None
    assert c._resolve_cop_sample_mode() == "unknown"


def test_resolve_cop_sample_mode_attrs_branches():
    c = _mk()
    c.data = SimpleNamespace(
        mode=None,
        attrs={
            "I/U operation mode": 123,
            "iu_operation_mode": "other",
            "ATTR_IU_OPERATION_MODE": "heating",
        },
    )
    assert c._resolve_cop_sample_mode() == "heating"


def test_resolve_cop_sample_mode_classify_fallback():
    c = _mk()
    c.data = SimpleNamespace(mode="unknown", attrs={"x": "y"})
    with patch(
        "custom_components.daikin_cycle_ml.engine.cycle_detector.classify_mode",
        return_value="heating",
    ):
        assert c._resolve_cop_sample_mode() == "heating"


def test_resolve_cop_sample_mode_classify_unknown():
    c = _mk()
    c.data = SimpleNamespace(mode="unknown", attrs={"x": "y"})
    with patch(
        "custom_components.daikin_cycle_ml.engine.cycle_detector.classify_mode",
        return_value="unknown",
    ):
        assert c._resolve_cop_sample_mode() == "unknown"


def test_resolve_cop_sample_mode_classify_raises():
    c = _mk()
    c.data = SimpleNamespace(mode="unknown", attrs={"x": "y"})
    with patch(
        "custom_components.daikin_cycle_ml.engine.cycle_detector.classify_mode",
        side_effect=RuntimeError("boom"),
    ):
        assert c._resolve_cop_sample_mode() == "unknown"


def test_assign_cluster_empty_returns_none():
    c = _mk()
    assert c._assign_cluster([1.0, 2.0]) is None


def test_assign_cluster_exception_returns_none():
    c = _mk()
    c._kmeans_centroids = [[1.0, 2.0]]
    with patch(
        "custom_components.daikin_cycle_ml.coordinator.nearest_centroid",
        side_effect=RuntimeError("boom"),
    ):
        assert c._assign_cluster([1.0, 2.0]) is None


def test_cluster_label_none_returns_none():
    c = _mk()
    assert c.cluster_label(None) is None


def test_cluster_label_known():
    c = _mk()
    c._cluster_labels = {0: "A", 1: "B"}
    assert c.cluster_label(1) == "B"
    assert c.cluster_label(9) is None


def test_rich_snapshot_attrs_get_raises():
    c = _mk()
    c._build_status_snapshot = MagicMock(return_value={})
    c.data = MagicMock()
    c.data.attributes = object()
    asyncio.run(c._build_rich_status_snapshot())


class _BadGetDict(dict):
    def get(self, key, default=None):
        raise RuntimeError("boom")


def test_rich_snapshot_last_cycle_get_raises():
    c = _mk()
    c._build_status_snapshot = MagicMock(return_value={})
    c.data = MagicMock()
    c.data.attributes = {}
    c.data.last_cycle = _BadGetDict()
    asyncio.run(c._build_rich_status_snapshot())


def test_rich_snapshot_store_bare():
    c = _mk()
    c._build_status_snapshot = MagicMock(return_value={})

    class _Bare:
        pass

    c.store = _Bare()
    asyncio.run(c._build_rich_status_snapshot())


def test_build_alert_context_store_last_cycle_raises():
    c = _mk()
    c.store.last_cycle = MagicMock(side_effect=RuntimeError("boom"))
    snap = SimpleNamespace(
        mode="unknown", advice=[], last_record=None, anomaly=None
    )
    ctx = c._build_alert_context(snap)
    assert isinstance(ctx, dict)
    assert ctx["short_run"]["mode"] == "unknown"


def test_build_alert_context_off_time_raises():
    c = _mk()
    c.store.off_time_since_last = MagicMock(side_effect=RuntimeError("boom"))
    snap = SimpleNamespace(
        mode="heating", advice=[], last_record=None, anomaly=None
    )
    ctx = c._build_alert_context(snap)
    assert isinstance(ctx, dict)


def test_build_alert_context_top_dim_int_raises():
    c = _mk()
    snap = SimpleNamespace(
        mode="heating",
        advice=[],
        last_record=None,
        anomaly=SimpleNamespace(
            max_abs_z=3.0, top_dim="not-an-int", severity=None
        ),
    )
    ctx = c._build_alert_context(snap)
    assert ctx["ml_anomaly"]["z_max"] == 3.0


def test_build_alert_context_z_none_top_dim_none():
    c = _mk()
    snap = SimpleNamespace(
        mode="heating",
        advice=[],
        last_record=None,
        anomaly=SimpleNamespace(max_abs_z=None, top_dim=None, severity=None),
    )
    ctx = c._build_alert_context(snap)
    assert ctx["ml_anomaly"]["z_max"] is None


def test_build_alert_context_top_dim_out_of_range():
    c = _mk()
    snap = SimpleNamespace(
        mode="heating",
        advice=[],
        last_record=None,
        anomaly=SimpleNamespace(max_abs_z=1.0, top_dim=9999, severity=None),
    )
    ctx = c._build_alert_context(snap)
    assert isinstance(ctx["ml_anomaly"]["top_dim"], str)


def test_build_alert_context_advice_title_empty():
    c = _mk()
    snap = SimpleNamespace(
        mode="heating",
        advice=[SimpleNamespace(title="", text="")],
        last_record=None,
        anomaly=None,
    )
    ctx = c._build_alert_context(snap)
    assert ctx["short_run"]["advice"] == ""


def test_db_cycle_stats_db_none():
    c = _mk()
    c.db = None
    out = asyncio.run(c._db_cycle_stats())
    assert out["db_total"] is None
    assert out["db_7d"] is None
    assert out["db_30d"] is None
    assert out["db_avg_duration_min"] is None


def test_db_cycle_stats_no_methods():
    c = _mk()

    class _Bare:
        pass

    c.db = _Bare()
    out = asyncio.run(c._db_cycle_stats())
    assert out["db_total"] is None
    assert out["db_avg_duration_min"] is None


def test_db_cycle_stats_getter_not_callable():
    c = _mk()
    c.db = MagicMock()
    c.db.async_count_cycles_since = "nope"
    c.db.async_avg_duration_since = "nope"
    out = asyncio.run(c._db_cycle_stats())
    assert out["db_total"] is None


def test_db_cycle_stats_avg_none():
    c = _mk()
    c.db = MagicMock()
    c.db.async_count_cycles_since = AsyncMock(return_value=5)
    c.db.async_avg_duration_since = AsyncMock(return_value=None)
    out = asyncio.run(c._db_cycle_stats())
    assert out["db_total"] == 5
    assert out["db_avg_duration_min"] is None


def test_maybe_notify_cop_low_no_cop():
    c = _mk()
    asyncio.run(c._maybe_notify_cop_low(time.time(), {}))


def test_maybe_notify_cop_low_high_cop_returns():
    c = _mk()
    asyncio.run(
        c._maybe_notify_cop_low(
            time.time(), {"cop": 3.5, "samples_today": 10}
        )
    )


def test_maybe_notify_cop_low_low_samples():
    c = _mk()
    asyncio.run(
        c._maybe_notify_cop_low(
            time.time(), {"cop": 1.5, "samples_today": 1}
        )
    )
