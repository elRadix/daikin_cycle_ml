"""Edge case tests for cop_hourly rollup (v1.17.0)."""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB
from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator


async def _mk_db(tmp_path, name="edge.db"):
    db = CycleDB(str(tmp_path / name))
    await db.async_open()
    await db.async_initialize()
    return db


def _sample(ts, mode="heating", cop=5.0, *, boiler_active=0, **overrides):
    row = {
        "ts": ts, "cop": cop, "lwt": 30.0, "outdoor": 7.0,
        "r1t": 28.0, "r4t": 27.0, "flow_lmin": 15.0,
        "power_stable": True, "mode": mode, "source": "interval",
        "boiler_active": boiler_active, "boiler_mode": "",
    }
    row.update(overrides)
    return row


async def test_rollup_excludes_cofire_samples(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        now = time.time()
        for i in range(3):
            await db.async_insert_cop_sample(_sample(now - i * 60, "heating", 6.0, boiler_active=0))
        for i in range(2):
            await db.async_insert_cop_sample(_sample(now - 300 - i * 60, "heating", 3.0, boiler_active=1))
        await db.async_rollup_cop_hourly(window_hours=48)
        rows = await db.async_query_cop_hourly(since_ts=now - 3600, mode="heating")
        assert len(rows) == 1
        assert rows[0]["n_samples"] == 3
        assert 5.8 < rows[0]["cop_mean"] < 6.2
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


async def test_rollup_handles_mixed_modes_same_hour(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        now = time.time()
        base_hour = (now // 3600) * 3600
        for i in range(3):
            await db.async_insert_cop_sample(_sample(base_hour + 60 + i * 60, "dhw", 3.5))
        for i in range(5):
            await db.async_insert_cop_sample(_sample(base_hour + 600 + i * 60, "heating", 6.0))
        await db.async_rollup_cop_hourly(window_hours=48)
        rows = await db.async_query_cop_hourly(since_ts=now - 3600)
        assert len(rows) == 2
        modes = {r["mode"]: r for r in rows}
        assert modes["dhw"]["n_samples"] == 3
        assert modes["heating"]["n_samples"] == 5
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


async def test_rollup_handles_null_lwt_outdoor_flow(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        now = time.time()
        await db.async_insert_cop_sample({
            "ts": now - 60, "cop": 5.0, "lwt": None, "outdoor": None,
            "r1t": None, "r4t": None, "flow_lmin": None,
            "power_stable": True, "mode": "heating", "source": "interval",
            "boiler_active": 0, "boiler_mode": "",
        })
        await db.async_rollup_cop_hourly(window_hours=48)
        rows = await db.async_query_cop_hourly(since_ts=now - 3600)
        assert len(rows) == 1
        assert rows[0]["lwt_mean"] is None
        assert rows[0]["cop_mean"] == 5.0
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


async def test_rollup_mode_none_becomes_unknown(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        now = time.time()
        await db.async_insert_cop_sample(_sample(now - 60, mode=None, cop=5.0))
        await db.async_rollup_cop_hourly(window_hours=48)
        rows = await db.async_query_cop_hourly(since_ts=now - 3600)
        assert len(rows) == 1
        assert rows[0]["mode"] == "unknown"
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


async def test_dhw_cycle_spanning_three_hours(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        now = time.time()
        for i in range(6):
            ts = now - (5 - i) * 1800
            await db.async_insert_cop_sample(_sample(ts, "dhw", 3.0 + i * 0.1))
        await db.async_rollup_cop_hourly(window_hours=48)
        rows = await db.async_query_cop_hourly(since_ts=now - 4 * 3600, mode="dhw")
        assert len(rows) >= 2
        total = sum(r["n_samples"] for r in rows)
        assert total == 6
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


async def test_prune_removes_old_keeps_recent(tmp_path):
    db = await _mk_db(tmp_path, "prune.db")
    try:
        now = time.time()
        await db.async_insert_cop_sample(_sample(now - 5 * 86400, "heating", 5.0))
        await db.async_insert_cop_sample(_sample(now - 60, "heating", 6.0))
        await db.async_rollup_cop_hourly(window_hours=720)
        all_rows = await db.async_query_cop_hourly(since_ts=now - 8 * 86400)
        assert len(all_rows) == 2
        deleted = await db.async_prune_cop_hourly(retention_days=1)
        assert deleted == 1
        rows = await db.async_query_cop_hourly(since_ts=now - 8 * 86400)
        assert len(rows) == 1
        assert 5.5 < rows[0]["cop_mean"] < 6.5
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)
