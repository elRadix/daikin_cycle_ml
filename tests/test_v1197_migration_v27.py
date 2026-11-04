"""v1.19.7 #260/#261: v27 migration tests."""
from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB


async def _mk_db(tmp_path, name="v27.db"):
    db = CycleDB(str(tmp_path / name))
    await db.async_open()
    await db.async_initialize()
    return db


def _ts(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=UTC).timestamp()


async def _ins(conn, start, end):
    await conn.execute(
        "INSERT INTO cycles (start_ts, end_ts, duration_s, mode, "
        "is_transient, is_reconstructed, quality_score, dT_max, rps_avg, "
        "buh_used, defrost_used, thermal_kw_avg) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (start, end, int(end - start), "heating", 0, 0, 80, 4.0, 25.0, 0, 0, 3.0),
    )


@pytest.mark.asyncio
async def test_v27_fixes_overlapping_pair(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        await _ins(conn, _ts(2026,11,2,1,10), _ts(2026,11,2,7,11))
        await _ins(conn, _ts(2026,11,2,5,11), _ts(2026,11,2,7,11))
        await conn.commit()
        r = await db.async_migrate_to_v27()
        assert r["overlap_fixed"] == 1 and r["completed"] is True
        row = await (await conn.execute(
            "SELECT end_ts, duration_s FROM cycles WHERE start_ts = ?",
            (_ts(2026,11,2,1,10),),
        )).fetchone()
        assert abs(row[0] - _ts(2026,11,2,5,11)) < 1
        assert 3*3600 < row[1] < 5*3600
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_v27_no_overlap_idempotent(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        await _ins(conn, _ts(2026,11,2,1), _ts(2026,11,2,3))
        await _ins(conn, _ts(2026,11,2,4), _ts(2026,11,2,6))
        await conn.commit()
        r = await db.async_migrate_to_v27()
        assert r["overlap_fixed"] == 0 and r["completed"] is True
        r2 = await db.async_migrate_to_v27()
        assert r2.get("skipped") == 1
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_v27_marker_set(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        await _ins(conn, _ts(2026,11,2,1), _ts(2026,11,2,3))
        await conn.commit()
        await db.async_migrate_to_v27()
        m = await db.async_get_model_state("data_migration_v27_completed")
        assert m is not None and m.get("completed") is True
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_v27_empty_db(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        r = await db.async_migrate_to_v27()
        assert r["overlap_fixed"] == 0 and r["completed"] is True
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_v27_rebuilds_summary(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        await _ins(conn, _ts(2026,11,2,1), _ts(2026,11,2,5))
        await _ins(conn, _ts(2026,11,2,3), _ts(2026,11,2,5))
        await conn.commit()
        await db.async_migrate_to_v27()
        row = await (await conn.execute(
            "SELECT total_duration_s FROM daily_summary "
            "WHERE day='2026-11-02' AND mode='heating'"
        )).fetchone()
        assert row is not None
        assert 3.9 <= row[0]/3600 <= 4.1
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_v27_real_fixture(tmp_path):
    src = Path(__file__).parent / "fixtures" / "_prod1_20261104.db"
    if not src.exists():
        pytest.skip("fixture missing")
    dst = tmp_path / "fixture.db"
    sc = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    dc = sqlite3.connect(dst)
    sc.backup(dc)
    dc.close()
    sc.close()
    db = CycleDB(str(dst))
    await db.async_open()
    try:
        r = await db.async_migrate_to_v27()
        assert r["completed"] is True
        assert r["overlap_fixed"] >= 3
        c = sqlite3.connect(dst)
        try:
            row = c.execute(
                "SELECT end_ts, duration_s FROM cycles WHERE id=175"
            ).fetchone()
            if row:
                assert row[0] == 1792991487.841368
                assert 14300 < row[1] < 14500
        finally:
            c.close()
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)
