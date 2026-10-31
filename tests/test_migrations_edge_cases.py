"""Migration edge cases: idempotency, data preservation."""
from __future__ import annotations

import asyncio
import time

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB


async def _mk_db(tmp_path, name="mig.db"):
    db = CycleDB(str(tmp_path / name))
    await db.async_open()
    await db.async_initialize()
    return db


async def test_v25_runs_once_marker_guarded(tmp_path):
    db = await _mk_db(tmp_path, "v25.db")
    try:
        await db.async_migrate_to_v25()
        marker1 = await db.async_get_model_state("data_migration_v25_completed")
        assert marker1 is not None
        await db.async_migrate_to_v25()
        marker2 = await db.async_get_model_state("data_migration_v25_completed")
        assert marker2 == marker1
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


async def test_v21_v22_v23_v24_markers_set(tmp_path):
    db = await _mk_db(tmp_path, "v2124.db")
    try:
        await db.async_migrate_to_v21()
        await db.async_migrate_to_v22()
        await db.async_migrate_to_v23()
        await db.async_migrate_to_v24()
        for v in (21, 22, 23, 24):
            marker = await db.async_get_model_state(f"data_migration_v{v}_completed")
            assert marker is not None
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


async def test_existing_cycles_preserved_after_v25(tmp_path):
    db = await _mk_db(tmp_path, "preserve.db")
    try:
        now = time.time()
        cid = await db.async_insert_cycle({
            "start_ts": now - 7200, "end_ts": now, "duration_s": 7200,
            "mode": "heating", "dT_max": 5.0, "dT_avg": 3.0,
            "rps_max": 40, "rps_avg": 30, "outdoor_temp": 7,
            "buh_used": 0, "defrost_used": 0, "quality_score": 80,
        })
        assert cid is not None
        await db.async_migrate_to_v25()
        cycles = await db.async_fetch_cycles(days=1)
        assert len(cycles) == 1
        assert cycles[0]["duration_s"] == 7200
        assert cycles[0]["is_reconstructed"] == 0
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


async def test_integrity_check_after_migrations(tmp_path):
    db = await _mk_db(tmp_path, "integ.db")
    try:
        for m in (21, 22, 23, 24, 25):
            await getattr(db, f"async_migrate_to_v{m}")()
        ok = await db.async_integrity_check()
        assert ok is True
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)
