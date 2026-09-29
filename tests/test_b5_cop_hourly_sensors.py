"""B5: cop_hourly KPI sensors (day/week/month).

Marker: B5_COP_HOURLY_SENSORS_v1
"""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    DataSnapshot,
)
from custom_components.daikin_cycle_ml.sensor import (
    SENSOR_DEFS,
    _attrs_cop_hourly,
    _cop_hourly_heating_mean,
)
from custom_components.daikin_cycle_ml.storage.db import CycleDB


async def _make_db(tmp_path: Path) -> CycleDB:
    db = CycleDB(tmp_path / "b5.db")
    await db.async_initialize()
    await db.async_create_cop_hourly_v14()
    return db


async def _seed_hourly(
    db: CycleDB, ts_hour: int, mode: str, n: int, cop_mean: float,
    cop_p10: float | None = None, cop_p90: float | None = None,
) -> None:
    conn = db._require()
    if cop_p10 is None:
        cop_p10 = cop_mean
    if cop_p90 is None:
        cop_p90 = cop_mean
    await conn.execute(
        "INSERT INTO cop_hourly (ts_hour, mode, n_samples, cop_mean, "
        "cop_p10, cop_p50, cop_p90, cop_std, lwt_mean, outdoor_mean, "
        "outdoor_min, outdoor_max, flow_mean, updated_ts) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (ts_hour, mode, n, cop_mean, cop_p10, cop_mean, cop_p90, 0.1,
         None, None, None, None, None, time.time()),
    )
    await conn.commit()


async def test_b5_query_empty(tmp_path):
    db = await _make_db(tmp_path)
    try:
        rows = await db.async_query_cop_hourly(since_ts=0.0)
        assert rows == []
    finally:
        await db.async_close()


async def test_b5_query_single_row(tmp_path):
    db = await _make_db(tmp_path)
    try:
        now = int(time.time() // 3600)
        await _seed_hourly(db, now - 1, "heating", 12, 3.5)
        rows = await db.async_query_cop_hourly(since_ts=0.0)
        assert len(rows) == 1
        assert rows[0]["mode"] == "heating"
        assert rows[0]["cop_mean"] == pytest.approx(3.5)
    finally:
        await db.async_close()


async def test_b5_query_order_by_ts_hour(tmp_path):
    db = await _make_db(tmp_path)
    try:
        now = int(time.time() // 3600)
        await _seed_hourly(db, now - 2, "heating", 12, 3.0)
        await _seed_hourly(db, now - 1, "heating", 12, 4.0)
        rows = await db.async_query_cop_hourly(since_ts=0.0)
        assert [r["ts_hour"] for r in rows] == [now - 2, now - 1]
    finally:
        await db.async_close()


async def test_b5_query_mode_filter(tmp_path):
    db = await _make_db(tmp_path)
    try:
        now = int(time.time() // 3600)
        await _seed_hourly(db, now - 1, "heating", 12, 3.5)
        await _seed_hourly(db, now - 1, "dhw", 4, 2.0)
        rows = await db.async_query_cop_hourly(since_ts=0.0, mode="dhw")
        assert len(rows) == 1
        assert rows[0]["mode"] == "dhw"
    finally:
        await db.async_close()


async def test_b5_query_until_ts(tmp_path):
    db = await _make_db(tmp_path)
    try:
        now = int(time.time() // 3600)
        await _seed_hourly(db, now - 5, "heating", 12, 3.0)
        await _seed_hourly(db, now - 1, "heating", 12, 4.0)
        rows = await db.async_query_cop_hourly(
            since_ts=0.0, until_ts=float((now - 3) * 3600)
        )
        assert len(rows) == 1
        assert rows[0]["ts_hour"] == now - 5
    finally:
        await db.async_close()


async def test_b5_query_limit(tmp_path):
    db = await _make_db(tmp_path)
    try:
        now = int(time.time() // 3600)
        for i in range(3):
            await _seed_hourly(db, now - 3 + i, "heating", 12, 3.0 + i)
        rows = await db.async_query_cop_hourly(since_ts=0.0, limit=2)
        assert len(rows) == 2
    finally:
        await db.async_close()


async def test_b5_stats_empty(tmp_path):
    db = await _make_db(tmp_path)
    try:
        stats = await db.async_cop_hourly_stats(since_ts=0.0)
        assert stats == {
            "n_hours": 0, "n_samples": 0,
            "cop_mean": None, "cop_p10": None, "cop_p90": None,
            "cop_min": None, "cop_max": None,
        }
    finally:
        await db.async_close()


async def test_b5_stats_single_bucket(tmp_path):
    db = await _make_db(tmp_path)
    try:
        now = int(time.time() // 3600)
        await _seed_hourly(
            db, now - 1, "heating", 12, 3.5, cop_p10=3.0, cop_p90=4.0
        )
        stats = await db.async_cop_hourly_stats(since_ts=0.0)
        assert stats["n_hours"] == 1
        assert stats["n_samples"] == 12
        assert stats["cop_mean"] == pytest.approx(3.5)
        assert stats["cop_p10"] == pytest.approx(3.0)
        assert stats["cop_p90"] == pytest.approx(4.0)
        assert stats["cop_min"] == pytest.approx(3.5)
        assert stats["cop_max"] == pytest.approx(3.5)
    finally:
        await db.async_close()


async def test_b5_stats_weighted_mean(tmp_path):
    db = await _make_db(tmp_path)
    try:
        now = int(time.time() // 3600)
        await _seed_hourly(db, now - 2, "heating", 20, 3.0)
        await _seed_hourly(db, now - 1, "heating", 4, 5.0)
        stats = await db.async_cop_hourly_stats(since_ts=0.0)
        assert stats["n_hours"] == 2
        assert stats["n_samples"] == 24
        assert stats["cop_mean"] == pytest.approx(
            (20 * 3.0 + 4 * 5.0) / 24
        )
        assert stats["cop_min"] == pytest.approx(3.0)
        assert stats["cop_max"] == pytest.approx(5.0)
    finally:
        await db.async_close()


async def test_b5_stats_mode_filter(tmp_path):
    db = await _make_db(tmp_path)
    try:
        now = int(time.time() // 3600)
        await _seed_hourly(db, now - 1, "heating", 12, 3.5)
        await _seed_hourly(db, now - 1, "dhw", 4, 2.0)
        stats = await db.async_cop_hourly_stats(
            since_ts=0.0, mode="dhw"
        )
        assert stats["n_hours"] == 1
        assert stats["cop_mean"] == pytest.approx(2.0)
    finally:
        await db.async_close()


async def test_b5_by_mode_empty(tmp_path):
    db = await _make_db(tmp_path)
    try:
        out = await db.async_cop_hourly_by_mode(since_ts=0.0)
        assert out == {}
    finally:
        await db.async_close()


async def test_b5_by_mode_multi(tmp_path):
    db = await _make_db(tmp_path)
    try:
        now = int(time.time() // 3600)
        await _seed_hourly(db, now - 1, "heating", 12, 3.5)
        await _seed_hourly(db, now - 1, "dhw", 4, 2.0)
        out = await db.async_cop_hourly_by_mode(since_ts=0.0)
        assert set(out) == {"heating", "dhw"}
        assert out["heating"]["cop_mean"] == pytest.approx(3.5)
        assert out["dhw"]["cop_mean"] == pytest.approx(2.0)
    finally:
        await db.async_close()


async def test_b5_coord_refresh_db_none():
    obj = MagicMock()
    obj.db = None
    obj._cop_hourly_cache = {}
    obj._cop_hourly_cache_ts = 0.0
    await DaikinCycleMLCoordinator._maybe_refresh_cop_hourly(obj, 1000.0)
    assert obj._cop_hourly_cache == {}


async def test_b5_coord_refresh_throttle():
    obj = MagicMock()
    obj.db = MagicMock()
    obj.db.async_cop_hourly_stats = AsyncMock()
    obj.db.async_cop_hourly_by_mode = AsyncMock()
    obj._cop_hourly_cache = {}
    obj._cop_hourly_cache_ts = 100.0
    await DaikinCycleMLCoordinator._maybe_refresh_cop_hourly(obj, 200.0)
    obj.db.async_cop_hourly_stats.assert_not_awaited()


async def test_b5_coord_refresh_populates():
    obj = MagicMock()
    obj.db = MagicMock()
    obj.db.async_cop_hourly_stats = AsyncMock(
        return_value={"n_hours": 24, "n_samples": 100,
                      "cop_mean": 3.5, "cop_p10": 3.0,
                      "cop_p90": 4.0, "cop_min": 3.0, "cop_max": 4.0}
    )
    obj.db.async_cop_hourly_by_mode = AsyncMock(
        return_value={"heating": {"cop_mean": 3.5}}
    )
    obj._cop_hourly_cache = {}
    obj._cop_hourly_cache_ts = 0.0
    await DaikinCycleMLCoordinator._maybe_refresh_cop_hourly(obj, 1000.0)
    assert set(obj._cop_hourly_cache) == {"day", "week", "month"}
    assert obj._cop_hourly_cache["day"]["by_mode"] == {
        "heating": {"cop_mean": 3.5}
    }
    assert obj._cop_hourly_cache_ts == 1000.0


async def test_b5_coord_refresh_swallows_error():
    obj = MagicMock()
    obj.db = MagicMock()
    obj.db.async_cop_hourly_stats = AsyncMock(
        side_effect=RuntimeError("boom")
    )
    obj._cop_hourly_cache = {}
    obj._cop_hourly_cache_ts = 0.0
    await DaikinCycleMLCoordinator._maybe_refresh_cop_hourly(obj, 1000.0)
    assert obj._cop_hourly_cache == {}
    assert obj._cop_hourly_cache_ts == 0.0


def test_b5_sensor_defs_include_new_keys():
    keys = [d["key"] for d in SENSOR_DEFS]
    assert set(keys) >= {
        "cop_mean_day", "cop_mean_week", "cop_mean_month",
    }


def test_b5_heating_mean_helper():
    snap = DataSnapshot()
    snap.cop_hourly_day = {
        "by_mode": {
            "heating": {"cop_mean": 3.42},
            "dhw": {"cop_mean": 2.0},
        },
    }
    fn = _cop_hourly_heating_mean("day")
    obj = MagicMock()
    assert fn(snap, obj) == pytest.approx(3.42)


def test_b5_heating_mean_missing():
    snap = DataSnapshot()
    fn = _cop_hourly_heating_mean("day")
    obj = MagicMock()
    assert fn(snap, obj) is None
    snap.cop_hourly_day = {"by_mode": {"dhw": {"cop_mean": 2.0}}}
    assert fn(snap, obj) is None


def test_b5_attrs_helper():
    snap = DataSnapshot()
    snap.cop_hourly_week = {
        "n_hours": 168, "n_samples": 500,
        "cop_p10": 2.9, "cop_p90": 4.1,
        "cop_min": 2.8, "cop_max": 4.2,
        "by_mode": {"heating": {"cop_mean": 3.5}},
    }
    fn = _attrs_cop_hourly("week")
    obj = MagicMock()
    attrs = fn(snap, obj)
    assert attrs["period"] == "week"
    assert attrs["n_hours"] == 168
    assert attrs["by_mode"] == {"heating": {"cop_mean": 3.5}}


def test_b5_attrs_helper_empty():
    snap = DataSnapshot()
    fn = _attrs_cop_hourly("month")
    obj = MagicMock()
    attrs = fn(snap, obj)
    assert attrs["period"] == "month"
    assert attrs["n_hours"] is None
    assert attrs["by_mode"] == {}
