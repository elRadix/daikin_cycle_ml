"""Multi-instance: two config entries must not interfere."""
from __future__ import annotations

import asyncio
import time

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB


def _sample(ts, mode="heating", cop=5.0):
    return {
        "ts": ts, "cop": cop, "lwt": 30.0, "outdoor": 7.0,
        "r1t": 28.0, "r4t": 27.0, "flow_lmin": 15.0,
        "power_stable": True, "mode": mode, "source": "interval",
        "boiler_active": 0, "boiler_mode": "",
    }


async def test_two_dbs_isolated(tmp_path):
    db_a = CycleDB(str(tmp_path / "a.db"))
    db_b = CycleDB(str(tmp_path / "b.db"))
    await db_a.async_open()
    await db_a.async_initialize()
    await db_b.async_open()
    await db_b.async_initialize()
    try:
        now = time.time()
        await db_a.async_insert_cop_sample(_sample(now - 60, "heating", 6.0))
        await db_b.async_insert_cop_sample(_sample(now - 60, "heating", 4.0))
        rows_a = await db_a.async_fetch_cop_samples_between(now - 3600, now + 60)
        rows_b = await db_b.async_fetch_cop_samples_between(now - 3600, now + 60)
        assert len(rows_a) == 1
        assert len(rows_b) == 1
        assert rows_a[0]["cop"] == 6.0
        assert rows_b[0]["cop"] == 4.0
    finally:
        await db_a.async_close()
        await db_b.async_close()
        await asyncio.sleep(0.05)


async def test_rollup_isolated(tmp_path):
    db_a = CycleDB(str(tmp_path / "ra.db"))
    db_b = CycleDB(str(tmp_path / "rb.db"))
    await db_a.async_open()
    await db_a.async_initialize()
    await db_b.async_open()
    await db_b.async_initialize()
    try:
        now = time.time()
        for i in range(5):
            await db_a.async_insert_cop_sample(_sample(now - i * 60, "dhw", 3.5))
        for i in range(3):
            await db_b.async_insert_cop_sample(_sample(now - i * 60, "heating", 6.0))
        await db_a.async_rollup_cop_hourly(window_hours=48)
        rows_a = await db_a.async_query_cop_hourly(since_ts=now - 3600)
        rows_b = await db_b.async_query_cop_hourly(since_ts=now - 3600)
        assert len(rows_a) == 1
        assert rows_a[0]["mode"] == "dhw"
        assert len(rows_b) == 0
    finally:
        await db_a.async_close()
        await db_b.async_close()
        await asyncio.sleep(0.05)
