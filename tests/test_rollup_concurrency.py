"""Concurrency tests: startup + post-cycle rollup running at once."""
from __future__ import annotations

import asyncio
import time

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB


async def _mk_db(tmp_path):
    db = CycleDB(str(tmp_path / "concur.db"))
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


async def test_concurrent_rollups_no_duplicate_rows(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        now = time.time()
        for i in range(6):
            await db.async_insert_cop_sample(_sample(now - i * 60, "heating", 5.5))
        await asyncio.gather(
            db.async_rollup_cop_hourly(window_hours=48),
            db.async_rollup_cop_hourly(window_hours=48),
        )
        rows = await db.async_query_cop_hourly(since_ts=now - 3600, mode="heating")
        assert len(rows) == 1
        assert rows[0]["n_samples"] == 6
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


async def test_concurrent_insert_and_rollup(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        now = time.time()
        async def insert_batch():
            for i in range(5):
                await db.async_insert_cop_sample(_sample(now - i * 60, "dhw", 4.0))
        async def rollup():
            await db.async_rollup_cop_hourly(window_hours=48)
        await asyncio.gather(insert_batch(), rollup())
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)
