"""Batch 52b: cop_samples.mode + heating-only stooklijn."""
import asyncio
import sqlite3
import time

import aiosqlite
import pytest

from custom_components.daikin_cycle_ml.engine.cop_analyzer import (
    CopSample,
    analyze_stooklijn,
)
from custom_components.daikin_cycle_ml.storage.db import CycleDB


def _mk(cop, lwt, out, mode, n=6):
    return [
        CopSample(cop=cop, lwt=lwt, outdoor=out, mode=mode,
                  data_quality="Good")
        for _ in range(n)
    ]


def test_cop_sample_default_mode():
    s = CopSample(cop=3.5)
    assert s.mode == "unknown"


def test_stooklijn_excludes_dhw():
    heating = _mk(4.0, 35.0, 5.0, "heating")
    dhw = _mk(1.0, 55.0, 5.0, "dhw")
    a = analyze_stooklijn(dhw + heating)
    b = analyze_stooklijn(heating)
    assert a.state == b.state
    assert a.optimale_lwt == b.optimale_lwt
    assert a.huidige_lwt == b.huidige_lwt


def test_stooklijn_filters_trailing_dhw():
    heating = _mk(4.0, 35.0, 5.0, "heating")
    dhw = _mk(1.0, 55.0, 5.0, "dhw")
    a = analyze_stooklijn(heating + dhw)
    b = analyze_stooklijn(heating)
    assert a.huidige_lwt == b.huidige_lwt


def test_unknown_mode_still_analyzed():
    unknown = _mk(4.0, 35.0, 5.0, "unknown")
    a = analyze_stooklijn(unknown)
    assert a.samples == 6


@pytest.mark.asyncio
async def test_migration_v13_legacy_table(tmp_path):
    path = tmp_path / "legacy52b.db"
    async with aiosqlite.connect(str(path)) as conn:
        await conn.execute(
            "CREATE TABLE cop_samples ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, "
            "cop REAL NOT NULL, lwt REAL, outdoor REAL, "
            "flow_lmin REAL, power_stable INTEGER DEFAULT 0)"
        )
        await conn.commit()
    db = CycleDB(path)
    try:
        await db.async_open()
        r1 = await db.async_migrate_cop_samples_to_v13()
        r2 = await db.async_migrate_cop_samples_to_v13()
        assert r1 == 0 and r2 == 0
        conn2 = sqlite3.connect(str(path))
        cols = {r[1] for r in conn2.execute("PRAGMA table_info(cop_samples)")}
        conn2.close()
        assert "mode" in cols
    finally:
        await db.async_close()
        await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_insert_cop_sample_with_mode(tmp_path):
    db = CycleDB(tmp_path / "ins52b.db")
    try:
        await db.async_open()
        await db.async_initialize()
        now = time.time()
        ok = await db.async_insert_cop_sample({
            "ts": now, "cop": 3.2, "lwt": 35.0, "outdoor": 5.0,
            "flow_lmin": 8.0, "power_stable": True, "mode": "heating",
        })
        assert ok is True
        rows = await db.async_fetch_cop_samples(days=1)
        assert len(rows) == 1
        assert rows[0]["mode"] == "heating"
    finally:
        await db.async_close()
        await asyncio.sleep(0.1)
