"""#133b: async_migrate_to_v1_12_5_sample_count_fix tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB


async def _insert_cycle(db, start_ts, end_ts, mode='heating',
                        cop_sample_count=0):
    conn = db._require()
    cur = await conn.execute(
        "INSERT INTO cycles (start_ts, end_ts, duration_s, mode, "
        "is_transient, is_reconstructed, cop_sample_count) "
        "VALUES (?, ?, ?, ?, 0, 0, ?)",
        (start_ts, end_ts, int(end_ts - start_ts), mode, cop_sample_count),
    )
    cid = cur.lastrowid
    await cur.close()
    await conn.commit()
    return int(cid)


async def _insert_sample(db, ts, cop=3.5, mode='heating', artifact=0):
    conn = db._require()
    await conn.execute(
        "INSERT INTO cop_samples (ts, cop, lwt, outdoor, flow_lmin, "
        "power_stable, mode, is_transition_artifact) "
        "VALUES (?, ?, 40.0, 5.0, 26.0, 1, ?, ?)",
        (ts, cop, mode, artifact),
    )
    await conn.commit()


async def _get_count(db, cid):
    conn = db._require()
    cur = await conn.execute(
        "SELECT cop_sample_count FROM cycles WHERE id=?", (cid,)
    )
    row = await cur.fetchone()
    await cur.close()
    return int(row[0]) if row else None


@pytest.fixture
async def db(tmp_path: Path):
    d = CycleDB(tmp_path / "v133b.db")
    await d.async_open()
    await d.async_initialize()
    yield d
    await d.async_close()


async def test_inflated_count_corrected(db):
    cid = await _insert_cycle(db, 1000.0, 2000.0,
                              mode='heating', cop_sample_count=100)
    for ts in (1100.0, 1400.0, 1700.0):
        await _insert_sample(db, ts, mode='heating')
    stats = await db.async_migrate_to_v1_12_5_sample_count_fix()
    assert stats["updated"] == 1
    assert await _get_count(db, cid) == 3


async def test_correct_count_untouched(db):
    cid = await _insert_cycle(db, 1000.0, 2000.0,
                              mode='heating', cop_sample_count=3)
    for ts in (1100.0, 1400.0, 1700.0):
        await _insert_sample(db, ts, mode='heating')
    stats = await db.async_migrate_to_v1_12_5_sample_count_fix()
    assert stats["updated"] == 0
    assert stats["skipped_no_change"] == 1
    assert await _get_count(db, cid) == 3


async def test_zero_real_samples_skipped(db):
    cid = await _insert_cycle(db, 1000.0, 2000.0,
                              mode='heating', cop_sample_count=50)
    stats = await db.async_migrate_to_v1_12_5_sample_count_fix()
    assert stats["skipped_no_samples"] == 1
    assert stats["updated"] == 0
    assert await _get_count(db, cid) == 50


async def test_artifact_samples_excluded(db):
    cid = await _insert_cycle(db, 1000.0, 2000.0,
                              mode='heating', cop_sample_count=30)
    for ts in (1100.0, 1400.0, 1700.0):
        await _insert_sample(db, ts, mode='heating', artifact=1)
    stats = await db.async_migrate_to_v1_12_5_sample_count_fix()
    assert stats["skipped_no_samples"] == 1
    assert await _get_count(db, cid) == 30


async def test_idempotent_re_run(db):
    await _insert_cycle(db, 1000.0, 2000.0,
                        mode='heating', cop_sample_count=100)
    for ts in (1100.0, 1400.0, 1700.0):
        await _insert_sample(db, ts, mode='heating')
    first = await db.async_migrate_to_v1_12_5_sample_count_fix()
    assert first["updated"] == 1
    second = await db.async_migrate_to_v1_12_5_sample_count_fix()
    assert second.get("skipped") == 1
