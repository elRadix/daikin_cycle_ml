"""v1.19.7 fix #12: migration v26 execution test (behavioral).

Complements source-inspection tests in test_v1197_thermal_kw_min_samples.py:
those prove the SQL strings exist; this file proves they execute correctly
against a real CycleDB — the fix for the coverage-gap that broke
attempt 5 of #12 (6 uncovered migration-body lines).
"""
from __future__ import annotations

import asyncio
import pathlib
import sqlite3

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB


async def _mk_db(tmp_path):
    db = CycleDB(str(tmp_path / "mig.db"))
    await db.async_open()
    await db.async_initialize()
    return db


async def _ins(conn, *, start_ts, duration_s, kw, mode="heating"):
    await conn.execute(
        "INSERT INTO cycles (start_ts, end_ts, duration_s, mode, thermal_kw_avg) "
        "VALUES (?, ?, ?, ?, ?)",
        (start_ts, start_ts + duration_s, duration_s, mode, kw),
    )


@pytest.mark.asyncio
async def test_migration_v26_nulls_dirty_preserves_clean(tmp_path):
    """3 dirty (dur<90, kw NOT NULL) + 2 clean -> 3 nulled, 2 preserved."""
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        for ts, dur, kw in [
            (1000, 30, 33.79), (2000, 60, 9.42), (3000, 29, 2.09),
            (4000, 300, 5.0), (5000, 1200, 7.5),
        ]:
            await _ins(conn, start_ts=ts, duration_s=dur, kw=kw)
        await conn.commit()

        r = await db.async_migrate_to_v26()
        assert r == {"nulled_short_cycles": 3, "completed": True}

        cur = await conn.execute(
            "SELECT duration_s, thermal_kw_avg FROM cycles ORDER BY start_ts"
        )
        rows = await cur.fetchall()
        await cur.close()
        assert rows[0][1] is None and rows[1][1] is None and rows[2][1] is None
        assert rows[3][1] == 5.0 and rows[4][1] == 7.5
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_migration_v26_idempotent(tmp_path):
    """Second run hits marker -> {nulled: 0, completed: True}."""
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        await _ins(conn, start_ts=1000, duration_s=30, kw=33.79)
        await conn.commit()
        assert await db.async_migrate_to_v26() == {"nulled_short_cycles": 1, "completed": True}
        assert await db.async_migrate_to_v26() == {"nulled_short_cycles": 0, "completed": True}
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_migration_v26_sets_marker(tmp_path):
    """Marker data_migration_v26_completed is set with correct payload."""
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        await _ins(conn, start_ts=1000, duration_s=30, kw=33.79)
        await conn.commit()
        await db.async_migrate_to_v26()
        m = await db.async_get_model_state("data_migration_v26_completed")
        assert m is not None and m.get("completed") is True
        assert m.get("nulled_short_cycles") == 1
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_migration_v26_empty_db(tmp_path):
    """Empty DB -> no crash, nulled=0, marker set."""
    db = await _mk_db(tmp_path)
    try:
        assert await db.async_migrate_to_v26() == {"nulled_short_cycles": 0, "completed": True}
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_migration_v26_real_fixture_replay(tmp_path):
    """Replay on 193-cycle prod fixture (16 dirty, 76 clean).

    Uses sqlite3.backup() for WAL-safe copy (R597).
    """
    src = pathlib.Path("tests/fixtures/_prod1_20261103.db")
    if not src.exists():
        pytest.skip("fixture missing")
    dst = tmp_path / "fixture.db"
    src_con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    dst_con = sqlite3.connect(dst)
    src_con.backup(dst_con)
    dst_con.close()
    src_con.close()

    db = CycleDB(str(dst))
    await db.async_open()
    try:
        def _count(sql):
            c = sqlite3.connect(str(dst))
            n = c.execute(sql).fetchone()[0]
            c.close()
            return n
        pre_clean = _count("SELECT COUNT(*) FROM cycles WHERE duration_s >= 90")
        r = await db.async_migrate_to_v26()
        assert r["nulled_short_cycles"] == 16
        assert r["completed"] is True
        post_clean = _count("SELECT COUNT(*) FROM cycles WHERE duration_s >= 90")
        assert post_clean == pre_clean
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)
