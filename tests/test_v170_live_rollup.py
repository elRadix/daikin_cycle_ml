"""Tests for live daily summary rollup (v1.7.0, #42)."""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)


class _Coord(DaikinCycleMLCoordinator):
    """Minimal coord for isolated testing of _maybe_rollup_day."""

    def __init__(self, options, db):
        self.options = options
        self.db = db


async def test_maybe_rollup_day_happy_path():
    db = AsyncMock()
    db.async_rollup_day = AsyncMock(return_value=1)
    c = _Coord({"daily_summary_live_enabled": True}, db)
    end_ts = time.time()
    await c._maybe_rollup_day({"end_ts": end_ts})
    expected = time.strftime("%Y-%m-%d", time.localtime(end_ts))
    db.async_rollup_day.assert_awaited_once_with(expected)


async def test_maybe_rollup_day_default_enabled():
    db = AsyncMock()
    db.async_rollup_day = AsyncMock(return_value=1)
    c = _Coord({}, db)
    await c._maybe_rollup_day({"end_ts": time.time()})
    db.async_rollup_day.assert_awaited_once()


async def test_maybe_rollup_day_disabled_by_option():
    db = AsyncMock()
    c = _Coord({"daily_summary_live_enabled": False}, db)
    await c._maybe_rollup_day({"end_ts": time.time()})
    db.async_rollup_day.assert_not_called()


async def test_maybe_rollup_day_no_db():
    c = _Coord({"daily_summary_live_enabled": True}, None)
    await c._maybe_rollup_day({"end_ts": time.time()})


async def test_maybe_rollup_day_non_numeric_end_ts():
    db = AsyncMock()
    c = _Coord({"daily_summary_live_enabled": True}, db)
    await c._maybe_rollup_day({"end_ts": "bad"})
    db.async_rollup_day.assert_not_called()


async def test_maybe_rollup_day_missing_end_ts():
    db = AsyncMock()
    c = _Coord({"daily_summary_live_enabled": True}, db)
    await c._maybe_rollup_day({})
    db.async_rollup_day.assert_not_called()


async def test_maybe_rollup_day_swallows_exception():
    db = AsyncMock()
    db.async_rollup_day = AsyncMock(side_effect=RuntimeError("boom"))
    c = _Coord({"daily_summary_live_enabled": True}, db)
    await c._maybe_rollup_day({"end_ts": time.time()})


async def test_process_new_cycle_invokes_rollup(monkeypatch):
    db = AsyncMock()
    db.async_insert_cycle = AsyncMock(return_value=1)
    db.async_insert_features = AsyncMock()
    db.async_update_cycle_cluster = AsyncMock()
    db.async_rollup_day = AsyncMock(return_value=1)
    c = _Coord(
        {"daily_summary_live_enabled": True,
         "action_advice_enabled": False},
        db,
    )
    c._collect_cycle_averages = AsyncMock(return_value=(None, None, None))
    c._assign_cluster = lambda vec: None
    c.baseline = MagicMock()
    c.baseline.get.return_value.update = MagicMock()
    c.adaptive = MagicMock()
    c.adaptive.observe_cycle = MagicMock()
    monkeypatch.setattr(
        "custom_components.daikin_cycle_ml.coordinator.extract_feature_vector",
        lambda *a, **kw: [0.0] * 12,
    )
    monkeypatch.setattr(
        "custom_components.daikin_cycle_ml.coordinator.evaluate_anomaly",
        lambda *a, **kw: MagicMock(),
    )
    snap = SimpleNamespace(
        anomaly=None, advice=None, cluster_id=None, mode="heating"
    )
    record = {"duration_s": 3600, "end_ts": time.time(), "mode": "heating"}
    await c._process_new_cycle(record, snap)
    db.async_rollup_day.assert_awaited_once()
