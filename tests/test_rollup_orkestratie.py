"""Tests for cop_hourly rollup orchestration (v1.17.0, Optie A+B)."""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator


def _mk_coord(db=None, options=None):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.hass = MagicMock()
    c.options = dict(options or {})
    c.entry = MagicMock()
    c.entry.entry_id = "test"
    c.db = db
    c.baseline = MagicMock()
    c.baseline._migrated_from_dim = None
    c.baseline.get.return_value.update = MagicMock()
    c.adaptive = MagicMock()
    c.adaptive.observe_cycle = MagicMock()
    c._baseline_save_unsub = None
    c._maintenance_unsub = None
    c._kmeans_unsub = None
    c._status_update_unsub = None
    c._stooklijn_unsub = None
    return c


def _patch_baseline_deps(c):
    return [
        patch.object(c, "async_load_adaptive_state", new=AsyncMock()),
        patch.object(c, "_restore_detector_state", new=AsyncMock()),
        patch.object(c, "_restore_runtime_acc", new=AsyncMock()),
        patch.object(c, "_restore_energy_acc", new=AsyncMock()),
        patch.object(c, "_maybe_backfill_daily_summary", new=AsyncMock()),
        patch.object(c, "_load_kmeans_state", new=AsyncMock()),
        patch("custom_components.daikin_cycle_ml.coordinator.async_track_time_interval",
              return_value=MagicMock()),
    ]


async def test_startup_invokes_cop_hourly_rollup():
    db = AsyncMock()
    db.async_rollup_cop_hourly = AsyncMock(return_value=5)
    db.async_get_model_state = AsyncMock(return_value=None)
    db.async_ensure_cluster_column = AsyncMock()
    c = _mk_coord(db=db)
    patches = _patch_baseline_deps(c)
    for p in patches:
        p.start()
    try:
        await c.async_setup_baseline_persistence()
    finally:
        for p in patches:
            p.stop()
    db.async_rollup_cop_hourly.assert_awaited_once()


async def test_startup_rollup_swallows_exception():
    db = AsyncMock()
    db.async_rollup_cop_hourly = AsyncMock(side_effect=RuntimeError("db down"))
    db.async_get_model_state = AsyncMock(return_value=None)
    db.async_ensure_cluster_column = AsyncMock()
    c = _mk_coord(db=db)
    patches = _patch_baseline_deps(c)
    for p in patches:
        p.start()
    try:
        await c.async_setup_baseline_persistence()
    finally:
        for p in patches:
            p.stop()
    db.async_rollup_cop_hourly.assert_awaited_once()


async def test_startup_rollup_noop_when_db_none():
    c = _mk_coord(db=None)
    patches = _patch_baseline_deps(c)
    for p in patches:
        p.start()
    try:
        await c.async_setup_baseline_persistence()
    finally:
        for p in patches:
            p.stop()


async def test_post_cycle_invokes_cop_hourly_rollup_with_48h():
    db = AsyncMock()
    db.async_insert_cycle = AsyncMock(return_value=1)
    db.async_insert_features = AsyncMock()
    db.async_update_cycle_cluster = AsyncMock()
    db.async_rollup_day = AsyncMock(return_value=1)
    db.async_rollup_cop_hourly = AsyncMock(return_value=5)
    db.async_daily_summary = AsyncMock(return_value=[])
    c = _mk_coord(
        db=db,
        options={"daily_summary_live_enabled": True, "action_advice_enabled": False},
    )
    c._collect_cycle_averages = AsyncMock(return_value=(None, None, None))
    c._assign_cluster = lambda vec: None
    c._refresh_daily_summary_recent = AsyncMock()
    with patch("custom_components.daikin_cycle_ml.coordinator.extract_feature_vector",
               lambda *a, **kw: [0.0] * 12), \
         patch("custom_components.daikin_cycle_ml.coordinator.evaluate_anomaly",
               lambda *a, **kw: MagicMock()):
        snap = SimpleNamespace(anomaly=None, advice=None, cluster_id=None, mode="dhw")
        record = {"duration_s": 3600, "end_ts": time.time(), "mode": "dhw"}
        await c._process_new_cycle(record, snap)
    db.async_rollup_cop_hourly.assert_awaited_once_with(window_hours=48)


async def test_post_cycle_rollup_swallows_exception():
    db = AsyncMock()
    db.async_insert_cycle = AsyncMock(return_value=1)
    db.async_insert_features = AsyncMock()
    db.async_update_cycle_cluster = AsyncMock()
    db.async_rollup_day = AsyncMock(return_value=1)
    db.async_rollup_cop_hourly = AsyncMock(side_effect=RuntimeError("db down"))
    db.async_daily_summary = AsyncMock(return_value=[])
    c = _mk_coord(
        db=db,
        options={"daily_summary_live_enabled": True, "action_advice_enabled": False},
    )
    c._collect_cycle_averages = AsyncMock(return_value=(None, None, None))
    c._assign_cluster = lambda vec: None
    c._refresh_daily_summary_recent = AsyncMock()
    with patch("custom_components.daikin_cycle_ml.coordinator.extract_feature_vector",
               lambda *a, **kw: [0.0] * 12), \
         patch("custom_components.daikin_cycle_ml.coordinator.evaluate_anomaly",
               lambda *a, **kw: MagicMock()):
        snap = SimpleNamespace(anomaly=None, advice=None, cluster_id=None, mode="heating")
        record = {"duration_s": 3600, "end_ts": time.time(), "mode": "heating"}
        await c._process_new_cycle(record, snap)
    db.async_rollup_cop_hourly.assert_awaited_once()


async def test_startup_plus_post_cycle_rollups_idempotent():
    db = AsyncMock()
    db.async_rollup_cop_hourly = AsyncMock(return_value=0)
    db.async_get_model_state = AsyncMock(return_value=None)
    db.async_ensure_cluster_column = AsyncMock()
    db.async_insert_cycle = AsyncMock(return_value=1)
    db.async_insert_features = AsyncMock()
    db.async_update_cycle_cluster = AsyncMock()
    db.async_rollup_day = AsyncMock(return_value=1)
    db.async_daily_summary = AsyncMock(return_value=[])
    c = _mk_coord(
        db=db,
        options={"daily_summary_live_enabled": True, "action_advice_enabled": False},
    )
    c._collect_cycle_averages = AsyncMock(return_value=(None, None, None))
    c._assign_cluster = lambda vec: None
    c._refresh_daily_summary_recent = AsyncMock()
    patches = _patch_baseline_deps(c)
    patches.extend([
        patch("custom_components.daikin_cycle_ml.coordinator.extract_feature_vector",
              lambda *a, **kw: [0.0] * 12),
        patch("custom_components.daikin_cycle_ml.coordinator.evaluate_anomaly",
              lambda *a, **kw: MagicMock()),
    ])
    for p in patches:
        p.start()
    try:
        await c.async_setup_baseline_persistence()
        snap = SimpleNamespace(anomaly=None, advice=None, cluster_id=None, mode="heating")
        record = {"duration_s": 3600, "end_ts": time.time(), "mode": "heating"}
        await c._process_new_cycle(record, snap)
    finally:
        for p in patches:
            p.stop()
    assert db.async_rollup_cop_hourly.await_count == 2
