"""B4: cop_hourly rollup + 6h scheduler hook.

Marker: B4_COP_HOURLY_ROLLUP_v1
"""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)
from custom_components.daikin_cycle_ml.storage.db import CycleDB


def _hour_ts(hour_offset: int = -1, extra: float = 10.0) -> float:
    return (int(time.time() // 3600) + hour_offset) * 3600.0 + extra


def _sample(ts, cop, mode="heating", lwt=35.0, outdoor=5.0,
            flow_lmin=15.0):
    return {
        "ts": ts, "cop": cop, "lwt": lwt, "outdoor": outdoor,
        "flow_lmin": flow_lmin, "power_stable": True,
        "mode": mode, "source": "interval",
    }


async def _make_db(tmp_path: Path) -> CycleDB:
    db = CycleDB(tmp_path / "b4.db")
    await db.async_initialize()
    return db


async def _rows(db: CycleDB):
    conn = db._require()
    async with conn.execute(
        "SELECT ts_hour, mode, n_samples, cop_mean, cop_p10, cop_p50, "
        "cop_p90, cop_std, lwt_mean, outdoor_mean, outdoor_min, "
        "outdoor_max, flow_mean FROM cop_hourly ORDER BY ts_hour, mode"
    ) as cur:
        return await cur.fetchall()


async def test_b4_empty_window_returns_zero(tmp_path):
    db = await _make_db(tmp_path)
    try:
        assert await db.async_rollup_cop_hourly(6) == 0
        assert await _rows(db) == []
    finally:
        await db.async_close()


async def test_b4_single_bucket_single_mode(tmp_path):
    db = await _make_db(tmp_path)
    try:
        base = _hour_ts(-1)
        for i, cop in enumerate([3.0, 4.0, 5.0]):
            await db.async_insert_cop_sample(_sample(base + i, cop))
        assert await db.async_rollup_cop_hourly(6) == 1
        rows = await _rows(db)
        assert len(rows) == 1
        assert rows[0]["n_samples"] == 3
        assert rows[0]["cop_mean"] == pytest.approx(4.0)
        assert rows[0]["cop_p50"] == pytest.approx(4.0)
    finally:
        await db.async_close()


async def test_b4_percentiles_known_series(tmp_path):
    db = await _make_db(tmp_path)
    try:
        base = _hour_ts(-1)
        for i in range(10):
            await db.async_insert_cop_sample(
                _sample(base + i, float(i + 1))
            )
        await db.async_rollup_cop_hourly(6)
        r = (await _rows(db))[0]
        assert r["n_samples"] == 10
        assert r["cop_p10"] == pytest.approx(1.9)
        assert r["cop_p50"] == pytest.approx(5.5)
        assert r["cop_p90"] == pytest.approx(9.1)
        assert r["cop_mean"] == pytest.approx(5.5)
    finally:
        await db.async_close()


async def test_b4_multi_bucket_multi_mode(tmp_path):
    db = await _make_db(tmp_path)
    try:
        h1 = _hour_ts(-2)
        h2 = _hour_ts(-1)
        await db.async_insert_cop_sample(
            _sample(h1, 3.0, mode="heating")
        )
        await db.async_insert_cop_sample(
            _sample(h1 + 5, 4.0, mode="heating")
        )
        await db.async_insert_cop_sample(
            _sample(h1 + 1, 2.0, mode="dhw")
        )
        await db.async_insert_cop_sample(
            _sample(h2, 5.0, mode="heating")
        )
        assert await db.async_rollup_cop_hourly(6) == 3
        assert len(await _rows(db)) == 3
    finally:
        await db.async_close()


async def test_b4_idempotent_upsert(tmp_path):
    db = await _make_db(tmp_path)
    try:
        base = _hour_ts(-1)
        await db.async_insert_cop_sample(_sample(base, 3.0))
        await db.async_insert_cop_sample(_sample(base + 1, 4.0))
        assert await db.async_rollup_cop_hourly(6) == 1
        assert await db.async_rollup_cop_hourly(6) == 1
        rows = await _rows(db)
        assert len(rows) == 1
        assert rows[0]["n_samples"] == 2
    finally:
        await db.async_close()


async def test_b4_null_lwt_outdoor_flow(tmp_path):
    db = await _make_db(tmp_path)
    try:
        base = _hour_ts(-1)
        await db.async_insert_cop_sample(
            _sample(base, 3.0, lwt=None, outdoor=None,
                    flow_lmin=None)
        )
        await db.async_insert_cop_sample(
            _sample(base + 1, 4.0, lwt=None, outdoor=None,
                    flow_lmin=None)
        )
        await db.async_rollup_cop_hourly(6)
        r = (await _rows(db))[0]
        assert r["lwt_mean"] is None
        assert r["outdoor_mean"] is None
        assert r["outdoor_min"] is None
        assert r["outdoor_max"] is None
        assert r["flow_mean"] is None
    finally:
        await db.async_close()


async def test_b4_null_mode_becomes_unknown(tmp_path):
    db = await _make_db(tmp_path)
    try:
        await db.async_insert_cop_sample(
            _sample(_hour_ts(-1), 3.0, mode=None)
        )
        await db.async_rollup_cop_hourly(6)
        assert (await _rows(db))[0]["mode"] == "unknown"
    finally:
        await db.async_close()


async def test_b4_single_sample_std_zero(tmp_path):
    db = await _make_db(tmp_path)
    try:
        await db.async_insert_cop_sample(
            _sample(_hour_ts(-1), 4.5)
        )
        await db.async_rollup_cop_hourly(6)
        r = (await _rows(db))[0]
        assert r["cop_std"] == 0.0
        assert r["cop_p10"] == pytest.approx(4.5)
    finally:
        await db.async_close()


async def test_b4_window_boundary_excludes_old(tmp_path):
    db = await _make_db(tmp_path)
    try:
        await db.async_insert_cop_sample(_sample(_hour_ts(-10), 9.9))
        await db.async_insert_cop_sample(_sample(_hour_ts(-1), 3.0))
        assert await db.async_rollup_cop_hourly(6) == 1
        r = (await _rows(db))[0]
        assert r["n_samples"] == 1
        assert r["cop_mean"] == pytest.approx(3.0)
    finally:
        await db.async_close()


async def test_b4_coord_rollup_db_none():
    obj = MagicMock()
    obj.db = None
    result = await DaikinCycleMLCoordinator._maybe_rollup_cop_hourly(obj)
    assert result == 0


async def test_b4_coord_rollup_delegates():
    obj = MagicMock()
    obj.db = MagicMock()
    obj.db.async_rollup_cop_hourly = AsyncMock(return_value=7)
    result = await DaikinCycleMLCoordinator._maybe_rollup_cop_hourly(obj)
    assert result == 7
    obj.db.async_rollup_cop_hourly.assert_awaited_once_with(
        window_hours=720
    )


async def test_b4_coord_callback_calls_both():
    obj = MagicMock()
    obj.async_save_baseline_state = AsyncMock(return_value=True)
    obj._maybe_rollup_cop_hourly = AsyncMock(return_value=3)
    await DaikinCycleMLCoordinator._async_baseline_save_callback(
        obj, 0.0
    )
    obj.async_save_baseline_state.assert_awaited_once()
    obj._maybe_rollup_cop_hourly.assert_awaited_once()


async def test_b4_coord_callback_swallows_baseline_error():
    obj = MagicMock()
    obj.async_save_baseline_state = AsyncMock(
        side_effect=RuntimeError("boom")
    )
    obj._maybe_rollup_cop_hourly = AsyncMock(return_value=0)
    await DaikinCycleMLCoordinator._async_baseline_save_callback(
        obj, 0.0
    )
    obj._maybe_rollup_cop_hourly.assert_awaited_once()


async def test_b4_coord_callback_swallows_rollup_error():
    obj = MagicMock()
    obj.async_save_baseline_state = AsyncMock(return_value=True)
    obj._maybe_rollup_cop_hourly = AsyncMock(
        side_effect=RuntimeError("boom")
    )
    await DaikinCycleMLCoordinator._async_baseline_save_callback(
        obj, 0.0
    )
    obj.async_save_baseline_state.assert_awaited_once()
