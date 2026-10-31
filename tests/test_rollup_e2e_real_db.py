"""Real-DB E2E tests for cop_hourly rollup (v1.17.0)."""
from __future__ import annotations

import asyncio
import time

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB


async def _mk_db(tmp_path, name="e2e.db"):
    db = CycleDB(str(tmp_path / name))
    await db.async_open()
    await db.async_initialize()
    return db


def _sample(ts, mode="heating", cop=5.0):
    return {
        "ts": ts, "cop": cop, "lwt": 30.0, "outdoor": 7.0,
        "r1t": 28.0, "r4t": 27.0, "flow_lmin": 15.0,
        "power_stable": True, "mode": mode, "source": "interval",
        "boiler_active": 0, "boiler_mode": "",
    }


async def test_dhw_cycle_end_to_cop_hourly_queryable(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        now = time.time()
        for i in range(17):
            await db.async_insert_cop_sample(_sample(now - (16 - i) * 300, "dhw", 3.0 + i * 0.05))
        for i in range(10):
            await db.async_insert_cop_sample(_sample(now - (9 - i) * 300, "heating", 6.0))
        await db.async_rollup_cop_hourly(window_hours=48)
        lt = time.localtime(now)
        today_start = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
        by_mode = await db.async_cop_hourly_by_mode(since_ts=today_start)
        assert "dhw" in by_mode
        assert "heating" in by_mode
        assert by_mode["dhw"]["n_samples"] == 17
        assert by_mode["heating"]["n_samples"] == 10
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


async def test_after_rollup_query_returns_data_immediately(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        now = time.time()
        await db.async_insert_cop_sample(_sample(now - 60, "dhw", 4.5))
        n = await db.async_rollup_cop_hourly(window_hours=48)
        assert n >= 1
        rows = await db.async_query_cop_hourly(since_ts=now - 3600, mode="dhw")
        assert len(rows) >= 1
        assert 4.0 < rows[0]["cop_mean"] < 5.0
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


async def test_two_rollups_same_window_idempotent(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        now = time.time()
        for i in range(5):
            await db.async_insert_cop_sample(_sample(now - i * 60, "heating", 5.5))
        await db.async_rollup_cop_hourly(window_hours=48)
        await db.async_rollup_cop_hourly(window_hours=48)
        await db.async_rollup_cop_hourly(window_hours=48)
        rows = await db.async_query_cop_hourly(since_ts=now - 3600, mode="heating")
        assert len(rows) == 1
        assert rows[0]["n_samples"] == 5
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


async def test_startup_rollup_fills_gap_from_previous_session(tmp_path):
    """Deterministic: pins samples to exact hour boundaries."""
    db = await _mk_db(tmp_path)
    try:
        now = time.time()
        current_hour = int(now // 3600) * 3600
        for hour_offset in range(1, 4):
            hour_ts = current_hour - hour_offset * 3600 + 60
            for i in range(6):
                ts = hour_ts + i * 60
                await db.async_insert_cop_sample(
                    _sample(ts, "heating", 5.0 + hour_offset * 0.1)
                )
        n = await db.async_rollup_cop_hourly(window_hours=720)
        assert n == 3, f"Expected exactly 3 hour buckets, got {n}"
        rows = await db.async_query_cop_hourly(
            since_ts=current_hour - 4 * 3600, mode="heating"
        )
        assert len(rows) == 3
        for r in rows:
            assert r["n_samples"] == 6
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


async def test_rollup_30_days_within_720h_window(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        now = time.time()
        current_hour = int(now // 3600) * 3600
        for day_offset in range(30):
            for i in range(4):
                ts = current_hour - day_offset * 86400 - i * 3600 + 60
                await db.async_insert_cop_sample(
                    _sample(ts, "heating", 5.5 + (day_offset % 3) * 0.1)
                )
        n = await db.async_rollup_cop_hourly(window_hours=720)
        assert n == 120, f"Expected 120, got {n}"
        rows = await db.async_query_cop_hourly(
            since_ts=current_hour - 31 * 86400, mode="heating"
        )
        assert len(rows) == 120
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


async def test_rollup_outside_window_not_included(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        now = time.time()
        await db.async_insert_cop_sample(_sample(now - 60, "heating", 5.0))
        await db.async_insert_cop_sample(_sample(now - 10 * 3600, "heating", 6.0))
        n = await db.async_rollup_cop_hourly(window_hours=6)
        assert n == 1
        rows = await db.async_query_cop_hourly(since_ts=now - 24 * 3600)
        assert len(rows) == 1
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


async def test_rollup_empty_db_returns_zero(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        n = await db.async_rollup_cop_hourly(window_hours=48)
        assert n == 0
        rows = await db.async_query_cop_hourly(since_ts=0)
        assert rows == []
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)
