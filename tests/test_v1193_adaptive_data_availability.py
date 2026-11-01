"""v1.19.3 (#249) — adaptive data-availability fixes.

Three gaps:
  1. observe_cycle filtered on is_transient (was: all cycles)
  2. off_s attached to record in score_and_count (was: computed but unused)
  3. observe_day called from _async_maintenance_callback (was: never)
"""
from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    score_and_count,
)


def _mk_coord() -> Any:
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = {"action_advice_enabled": False}
    c.db = MagicMock()
    c.db.async_insert_cycle = AsyncMock(return_value=1)
    c.db.async_insert_features = AsyncMock()
    c.db.async_update_cycle_cluster = AsyncMock()
    c.db.async_rollup_day = AsyncMock(return_value=1)
    c.db.async_daily_summary = AsyncMock(return_value=[])
    c._collect_cycle_averages = AsyncMock(return_value=(None, None, None))
    c._assign_cluster = MagicMock(return_value=None)
    c._maybe_rollup_day = AsyncMock()
    c.baseline = MagicMock()
    c.baseline.get.return_value.update = MagicMock()
    c.adaptive = MagicMock()
    c.adaptive.observe_cycle = MagicMock()
    c.adaptive.observe_day = MagicMock(return_value=True)
    c.async_save_adaptive_state = AsyncMock(return_value=True)
    c._clamp_duration = lambda d, m: d
    return c


def _snap() -> Any:
    s = MagicMock()
    s.mode = "heating"
    s.anomaly = None
    s.advice = None
    s.cluster_id = None
    return s


def _rec(transient: int | None = None, dur: float = 3600.0) -> dict[str, Any]:
    r: dict[str, Any] = {
        "start_ts": 1000.0,
        "end_ts": 1000.0 + dur,
        "duration_s": dur,
        "mode": "heating",
        "dT_max": 5.0,
        "dT_avg": 3.0,
        "rps_max": 30,
        "rps_avg": 20.0,
        "thermal_kw_avg": 2.5,
        "buh_used": 0,
        "defrost_used": 0,
    }
    if transient is not None:
        r["is_transient"] = transient
    return r


async def _run_process(c: Any, rec: dict[str, Any]) -> None:
    import custom_components.daikin_cycle_ml.coordinator as co
    with patch.object(co, "extract_feature_vector", return_value=[0.0] * 12), \
         patch.object(co, "evaluate_anomaly", return_value=MagicMock(is_anomaly=False)):
        await c._process_new_cycle(rec, _snap())


async def test_observe_cycle_called_for_non_transient() -> None:
    c = _mk_coord()
    await _run_process(c, _rec(transient=0))
    c.adaptive.observe_cycle.assert_called_once()


async def test_observe_cycle_skipped_for_transient() -> None:
    c = _mk_coord()
    await _run_process(c, _rec(transient=1))
    c.adaptive.observe_cycle.assert_not_called()


async def test_observe_cycle_called_when_is_transient_missing() -> None:
    """Backward compat: records without is_transient key still call observe."""
    c = _mk_coord()
    await _run_process(c, _rec(transient=None))
    c.adaptive.observe_cycle.assert_called_once()


def test_score_and_count_attaches_off_s() -> None:
    rec = _rec()
    store = MagicMock()
    store.off_time_since_last = MagicMock(return_value=1800.0)
    store.get = MagicMock(return_value=0)
    store.record_short_run = MagicMock()
    store.record_short_off = MagicMock()
    store.record_cycle_score = MagicMock()
    with patch("custom_components.daikin_cycle_ml.coordinator.score_cycle", return_value=80):
        score_and_count(rec, {}, store, time.time())
    assert rec.get("off_s") == 1800.0


def test_score_and_count_skips_off_s_when_none() -> None:
    rec = _rec()
    store = MagicMock()
    store.off_time_since_last = MagicMock(return_value=None)
    store.get = MagicMock(return_value=0)
    store.record_short_run = MagicMock()
    store.record_short_off = MagicMock()
    store.record_cycle_score = MagicMock()
    with patch("custom_components.daikin_cycle_ml.coordinator.score_cycle", return_value=80):
        score_and_count(rec, {}, store, time.time())
    assert "off_s" not in rec


async def test_maintenance_calls_observe_day_when_yesterday_has_cycles() -> None:
    c = _mk_coord()
    yesterday = time.strftime(
        "%Y-%m-%d", time.localtime(time.time() - 86400)
    )
    c.db.async_daily_summary = AsyncMock(return_value=[
        {"day": yesterday, "mode": "heating", "cycles": 6},
        {"day": yesterday, "mode": "dhw", "cycles": 2},
    ])
    c.async_run_maintenance = AsyncMock(return_value={})
    await c._async_maintenance_callback(None)
    c.adaptive.observe_day.assert_called_once_with(8)
    c.async_save_adaptive_state.assert_awaited_once()


async def test_maintenance_skips_observe_day_when_zero_cycles() -> None:
    c = _mk_coord()
    yesterday = time.strftime(
        "%Y-%m-%d", time.localtime(time.time() - 86400)
    )
    c.db.async_daily_summary = AsyncMock(return_value=[
        {"day": yesterday, "mode": "heating", "cycles": 0},
    ])
    c.async_run_maintenance = AsyncMock(return_value={})
    await c._async_maintenance_callback(None)
    c.adaptive.observe_day.assert_not_called()


async def test_maintenance_skips_when_db_is_none() -> None:
    c = _mk_coord()
    c.db = None
    c.async_run_maintenance = AsyncMock(return_value={})
    await c._async_maintenance_callback(None)
    c.adaptive.observe_day.assert_not_called()


async def test_maintenance_swallows_observe_day_exception() -> None:
    """Exception in observe_day block must not propagate (#249)."""
    c = _mk_coord()
    c.db.async_daily_summary = AsyncMock(
        side_effect=RuntimeError("db gone")
    )
    c.async_run_maintenance = AsyncMock(return_value={})
    await c._async_maintenance_callback(None)
    c.adaptive.observe_day.assert_not_called()


async def test_maintenance_swallows_save_adaptive_exception() -> None:
    """Save failure after observe_day must not propagate."""
    c = _mk_coord()
    yesterday = time.strftime(
        "%Y-%m-%d", time.localtime(time.time() - 86400)
    )
    c.db.async_daily_summary = AsyncMock(return_value=[
        {"day": yesterday, "mode": "heating", "cycles": 3},
    ])
    c.async_save_adaptive_state = AsyncMock(
        side_effect=RuntimeError("save failed")
    )
    c.async_run_maintenance = AsyncMock(return_value={})
    await c._async_maintenance_callback(None)
    c.adaptive.observe_day.assert_called_once_with(3)
