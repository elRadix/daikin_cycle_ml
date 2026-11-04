"""v1.19.7 #261: v27 resilience — defensive except branches."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB


async def _mk_db(tmp_path, name="v27e.db"):
    db = CycleDB(str(tmp_path / name))
    await db.async_open()
    await db.async_initialize()
    return db


def _ts(y, mo, d, h=0):
    return datetime(y, mo, d, h, tzinfo=UTC).timestamp()


async def _ins(conn, start, end):
    await conn.execute(
        "INSERT INTO cycles (start_ts, end_ts, duration_s, mode, "
        "is_transient, is_reconstructed, quality_score, dT_max, rps_avg, "
        "buh_used, defrost_used, thermal_kw_avg) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (start, end, int(end - start), "heating", 0, 0, 80, 4.0, 25.0, 0, 0, 3.0),
    )


@pytest.mark.asyncio
async def test_v27_rollup_exception_resilient(tmp_path, monkeypatch):
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        await _ins(conn, _ts(2026,11,2,1), _ts(2026,11,2,7))
        await _ins(conn, _ts(2026,11,2,5), _ts(2026,11,2,7))
        await conn.commit()
        called = {"n": 0}
        async def failing_rollup(day, *a, **kw):
            called["n"] += 1
            raise RuntimeError("simulated rollup failure")
        monkeypatch.setattr(db, "async_rollup_day", failing_rollup)
        r = await db.async_migrate_to_v27()
        assert r["completed"] is True and r["overlap_fixed"] == 1
        assert called["n"] > 0
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_v27_rebuild_exception_resilient(tmp_path, monkeypatch):
    db = await _mk_db(tmp_path)
    try:
        async def failing_rebuild():
            raise RuntimeError("simulated rebuild failure")
        monkeypatch.setattr(db, "_rebuild_daily_summary_for_affected_days", failing_rebuild)
        r = await db.async_migrate_to_v27()
        assert r["completed"] is True
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)
