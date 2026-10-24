"""v1.12.4 Phase 7+8+9: Amend 7 backfill + R447 cop_hourly + R448 daily_summary."""
from __future__ import annotations

from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB


async def _insert_cycle(
    db, start_ts, end_ts, mode='dhw',
    cop_sample_count=None, is_transient=0, is_reconstructed=0,
) -> int:
    conn = db._require()
    cur = await conn.execute(
        "INSERT INTO cycles (start_ts, end_ts, duration_s, mode, "
        "is_transient, is_reconstructed, cop_sample_count) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (start_ts, end_ts, int(end_ts - start_ts), mode,
         is_transient, is_reconstructed, cop_sample_count),
    )
    cid = cur.lastrowid
    await cur.close()
    await conn.commit()
    return int(cid)


async def _insert_sample(db, ts, cop=3.5, mode='dhw', artifact=0):
    conn = db._require()
    await conn.execute(
        "INSERT INTO cop_samples (ts, cop, lwt, outdoor, "
        "flow_lmin, power_stable, mode, is_transition_artifact) "
        "VALUES (?, ?, 40.0, 5.0, 26.0, 1, ?, ?)",
        (ts, cop, mode, artifact),
    )
    await conn.commit()


async def _get_cycle(db, cid):
    conn = db._require()
    cur = await conn.execute(
        "SELECT cop_avg, cop_sample_count FROM cycles WHERE id=?",
        (cid,),
    )
    row = await cur.fetchone()
    await cur.close()
    return dict(zip(("cop_avg", "cop_sample_count"), row)) if row else None


@pytest.fixture
async def db(tmp_path: Path):
    d = CycleDB(tmp_path / "p789.db")
    await d.async_open()
    await d.async_initialize()
    yield d
    await d.async_close()


# ---- Phase 7 Amend 7 ----

async def test_p7_backfills_null_count(db):
    cid = await _insert_cycle(db, 1000.0, 2000.0, cop_sample_count=None)
    await _insert_sample(db, 1100.0, cop=3.0)
    await _insert_sample(db, 1500.0, cop=4.0)
    n = await db._backfill_null_aggregates()
    assert n == 1
    row = await _get_cycle(db, cid)
    assert row is not None
    assert row["cop_sample_count"] == 2
    assert row["cop_avg"] == pytest.approx(3.5)


async def test_p7_backfills_zero_count(db):
    cid = await _insert_cycle(db, 1000.0, 2000.0, cop_sample_count=0)
    await _insert_sample(db, 1100.0, cop=3.0)
    n = await db._backfill_null_aggregates()
    assert n == 1
    row = await _get_cycle(db, cid)
    assert row is not None
    assert row["cop_sample_count"] == 1


async def test_p7_skips_cycles_with_samples_present(db):
    """Cycle already has count -> not targeted."""
    cid = await _insert_cycle(db, 1000.0, 2000.0, cop_sample_count=5)
    await _insert_sample(db, 1100.0)
    n = await db._backfill_null_aggregates()
    assert n == 0
    row = await _get_cycle(db, cid)
    assert row is not None
    assert row["cop_sample_count"] == 5


async def test_p7_skips_cycles_with_no_samples(db):
    cid = await _insert_cycle(db, 1000.0, 2000.0, cop_sample_count=None)
    n = await db._backfill_null_aggregates()
    assert n == 0
    row = await _get_cycle(db, cid)
    assert row is not None
    assert row["cop_sample_count"] is None


async def test_p7_excludes_artifacts(db):
    cid = await _insert_cycle(db, 1000.0, 2000.0, cop_sample_count=None)
    await _insert_sample(db, 1100.0, cop=3.0, artifact=0)
    await _insert_sample(db, 1200.0, cop=3.0, artifact=0)
    await _insert_sample(db, 1300.0, cop=99.9, artifact=1)
    await db._backfill_null_aggregates()
    row = await _get_cycle(db, cid)
    assert row is not None
    assert row["cop_sample_count"] == 2
    assert row["cop_avg"] == pytest.approx(3.0)


# ---- Phase 8 R447 ----

async def test_p8_rebuilds_hour_with_artifact_samples(db):
    await _insert_sample(db, 1000.0, cop=3.0, artifact=1)  # hour 0
    await _insert_sample(db, 1100.0, cop=3.5, artifact=0, mode='heating')
    await _insert_sample(db, 1200.0, cop=4.0, artifact=0, mode='heating')
    # also mark mode_original to trigger rebuild
    conn = db._require()
    await conn.execute(
        "UPDATE cop_samples SET mode_original='heating' WHERE id=2"
    )
    await conn.commit()
    n = await db._rebuild_cop_hourly_for_affected_hours()
    assert n >= 1
    cur = await conn.execute(
        "SELECT mode, n_samples, cop_mean FROM cop_hourly "
        "WHERE ts_hour=0 ORDER BY mode"
    )
    rows = await cur.fetchall()
    await cur.close()
    assert len(rows) == 1  # only heating (artifact excluded)
    assert rows[0][0] == 'heating'
    assert rows[0][1] == 2


async def test_p8_returns_zero_if_no_affected(db):
    await _insert_sample(db, 1000.0, cop=3.0, artifact=0)
    n = await db._rebuild_cop_hourly_for_affected_hours()
    assert n == 0


async def test_p8_hour_with_only_artifacts_gets_cleared(db):
    """Hour with only artifact samples: delete row, no re-insert (inner loop 0x)."""
    await _insert_sample(db, 1000.0, cop=99.9, artifact=1)
    await _insert_sample(db, 1100.0, cop=99.9, artifact=1)
    n = await db._rebuild_cop_hourly_for_affected_hours()
    assert n == 1
    conn = db._require()
    cur = await conn.execute(
        "SELECT COUNT(*) FROM cop_hourly WHERE ts_hour=0"
    )
    row = await cur.fetchone()
    await cur.close()
    assert int(row[0]) == 0


# ---- Phase 9 R448 ----

async def test_p9_rebuilds_reconstructed_day(db):
    """Synthetic cycle's day gets rebuilt."""
    await _insert_cycle(db, 1000.0, 2000.0,
                        mode='dhw', is_reconstructed=1)
    n = await db._rebuild_daily_summary_for_affected_days()
    assert n == 1
    conn = db._require()
    cur = await conn.execute(
        "SELECT cycles FROM daily_summary "
        "WHERE mode='dhw'"
    )
    row = await cur.fetchone()
    await cur.close()
    assert row is not None
    assert int(row[0]) == 1


async def test_p9_returns_zero_if_no_affected(db):
    await _insert_cycle(db, 1000.0, 2000.0,
                        mode='dhw', is_reconstructed=0)
    n = await db._rebuild_daily_summary_for_affected_days()
    assert n == 0


# ---- Skeleton integration ----

async def test_skeleton_wires_phase789_stats(db):
    await _insert_cycle(db, 1000.0, 2000.0, cop_sample_count=None)
    await _insert_sample(db, 1100.0, cop=3.0)
    stats = await db.async_migrate_to_v18()
    assert stats["cop_aggregates_backfilled"] == 1
    assert "hours_rebuilt" in stats
    assert "days_rebuilt" in stats
    assert stats["completed"] is False
