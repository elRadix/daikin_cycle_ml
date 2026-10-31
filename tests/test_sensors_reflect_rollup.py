"""Sensor-level tests: does cop_dhw_day actually show data after a cycle?"""
from __future__ import annotations

import asyncio
import time

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB


async def _mk_db(tmp_path):
    db = CycleDB(str(tmp_path / "sensor.db"))
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


async def test_cop_dhw_day_reflects_after_dhw_cycle(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        now = time.time()
        for i in range(17):
            await db.async_insert_cop_sample(_sample(now - (16 - i) * 300, "dhw", 3.5))
        await db.async_rollup_cop_hourly(window_hours=48)
        lt = time.localtime(now)
        day_start = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
        by_mode = await db.async_cop_hourly_by_mode(since_ts=day_start)
        assert "dhw" in by_mode
        assert by_mode["dhw"]["n_samples"] == 17
        assert 3.0 < by_mode["dhw"]["cop_mean"] < 4.0
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


async def test_cop_heating_day_reflects_after_heating_cycle(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        now = time.time()
        for i in range(12):
            await db.async_insert_cop_sample(_sample(now - (11 - i) * 300, "heating", 6.0))
        await db.async_rollup_cop_hourly(window_hours=48)
        lt = time.localtime(now)
        day_start = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
        by_mode = await db.async_cop_hourly_by_mode(since_ts=day_start)
        assert "heating" in by_mode
        assert by_mode["heating"]["n_samples"] == 12
        assert 5.5 < by_mode["heating"]["cop_mean"] < 6.5
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


async def test_cop_today_with_mixed_modes(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        now = time.time()
        for i in range(6):
            await db.async_insert_cop_sample(_sample(now - i * 300, "dhw", 3.5))
        for i in range(12):
            await db.async_insert_cop_sample(_sample(now - i * 300, "heating", 6.0))
        await db.async_rollup_cop_hourly(window_hours=48)
        lt = time.localtime(now)
        day_start = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
        by_mode = await db.async_cop_hourly_by_mode(since_ts=day_start)
        assert "dhw" in by_mode
        assert "heating" in by_mode
        assert by_mode["dhw"]["n_samples"] == 6
        assert by_mode["heating"]["n_samples"] == 12
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)
