"""v1.12.9 (#131 PR-2): coordinator forward-merge hook integration."""
from __future__ import annotations
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)
from custom_components.daikin_cycle_ml.storage.store import CycleStore


class _Snap(SimpleNamespace):
    cluster_id = None
    anomaly = None
    advice = None
    mode = "heating"
    last_record = None


class _Coord(DaikinCycleMLCoordinator):
    def __init__(self, options, db):
        self.options = options
        self.db = db
        self.store = CycleStore()


def _rec(mode="heating", start=0, end=60, is_transient=0):
    return {
        "start_ts": start, "end_ts": end,
        "duration_s": end - start,
        "mode": mode,
        "dT_max": 5.0, "dT_avg": 3.0,
        "rps_max": 30, "rps_avg": 20.0,
        "outdoor_temp": 10.0,
        "buh_used": 0, "defrost_used": 0,
        "is_transient": is_transient,
    }


def _make_coord(absorbed: int, cid: int = 999) -> tuple:
    db = AsyncMock()
    db.async_insert_cycle = AsyncMock(return_value=cid)
    db.async_merge_cycle_forward = AsyncMock(return_value=absorbed)
    db.async_insert_features = AsyncMock()
    db.async_update_cycle_cluster = AsyncMock()
    db.async_rollup_day = AsyncMock(return_value=1)
    db.async_daily_summary = AsyncMock(return_value=[])
    c = _Coord({"action_advice_enabled": False}, db)
    c._collect_cycle_averages = AsyncMock(return_value=(None, None, None))
    c._assign_cluster = lambda vec: None
    c.baseline = MagicMock()
    c.baseline.get.return_value.update = MagicMock()
    c.adaptive = MagicMock()
    return c, db


async def test_simple_merge_absorbed_1():
    c, db = _make_coord(absorbed=1)
    c.store.add_cycle(_rec(start=0, end=100))
    c.store.add_cycle(_rec(start=110, end=200))
    snap = _Snap()
    await c._process_new_cycle(_rec(start=110, end=200), snap)
    assert c.store.get("cycles_total") == 1
    assert c.store.get("cycles_today") == 1
    assert c.store.get("cycles_heating") == 1
    assert len(c.store.cycles()) == 1
    assert c.store.last_cycle()["end_ts"] == 100
    db.async_merge_cycle_forward.assert_awaited_once_with(999)
    db.async_insert_features.assert_not_called()
    db.async_update_cycle_cluster.assert_not_called()
    db.async_rollup_day.assert_not_called()


async def test_bridge_merge_absorbed_2():
    c, db = _make_coord(absorbed=2)
    c.store.add_cycle(_rec(start=0, end=600))
    c.store.add_cycle(_rec(start=610, end=670, is_transient=1))
    c.store.add_cycle(_rec(start=680, end=1300))
    snap = _Snap()
    await c._process_new_cycle(_rec(start=680, end=1300), snap)
    assert c.store.get("cycles_total") == 1
    assert c.store.get("cycles_heating") == 1
    assert len(c.store.cycles()) == 1
    assert c.store.last_cycle()["end_ts"] == 600
    assert c.store.last_cycle()["is_transient"] == 0
    db.async_insert_features.assert_not_called()
    db.async_rollup_day.assert_not_called()


async def test_no_merge_absorbed_0():
    c, db = _make_coord(absorbed=0)
    c.store.add_cycle(_rec(start=0, end=100))
    c.store.add_cycle(_rec(start=110, end=200))
    snap = _Snap()
    await c._process_new_cycle(_rec(start=110, end=200), snap)
    assert c.store.get("cycles_total") == 2
    assert len(c.store.cycles()) == 2
    db.async_insert_features.assert_awaited_once()
    db.async_rollup_day.assert_awaited_once()


async def test_new_transient_skips_primitive():
    c, db = _make_coord(absorbed=0)
    c.store.add_cycle(_rec(start=0, end=100))
    c.store.add_cycle(_rec(start=110, end=150, is_transient=1))
    snap = _Snap()
    await c._process_new_cycle(
        _rec(start=110, end=150, is_transient=1), snap
    )
    db.async_merge_cycle_forward.assert_not_awaited()
    assert c.store.get("cycles_total") == 2


async def test_merge_exception_caught():
    c, db = _make_coord(absorbed=0)
    db.async_merge_cycle_forward = AsyncMock(
        side_effect=RuntimeError("db boom")
    )
    c.store.add_cycle(_rec(start=0, end=100))
    c.store.add_cycle(_rec(start=110, end=200))
    snap = _Snap()
    await c._process_new_cycle(_rec(start=110, end=200), snap)
    assert c.store.get("cycles_total") == 2
    assert len(c.store.cycles()) == 2
    db.async_insert_features.assert_awaited_once()
    db.async_rollup_day.assert_awaited_once()


async def test_cid_none_skips_primitive():
    c, db = _make_coord(absorbed=1)
    db.async_insert_cycle = AsyncMock(return_value=None)
    c.store.add_cycle(_rec(start=0, end=100))
    snap = _Snap()
    await c._process_new_cycle(_rec(start=0, end=100), snap)
    db.async_merge_cycle_forward.assert_not_awaited()
    assert c.store.get("cycles_total") == 1


async def test_counter_coherence_all_absorbed():
    for absorbed in (0, 1, 2):
        c, db = _make_coord(absorbed=absorbed)
        n_prev = max(absorbed, 1)
        for i in range(n_prev):
            c.store.add_cycle(_rec(start=i * 100, end=i * 100 + 60))
        c.store.add_cycle(_rec(start=999, end=1059))
        snap = _Snap()
        await c._process_new_cycle(_rec(start=999, end=1059), snap)
        total = c.store.get("cycles_total")
        assert total == len(c.store.cycles())
        assert c.store.get("cycles_today") == total
        assert c.store.get("cycles_heating") == total
