"""v1.12.4 end-to-end migration test on synthetic fleet-like data."""
from __future__ import annotations

from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB


async def _cycle(db, s, e, mode='heating', is_transient=0):
    conn = db._require()
    cur = await conn.execute(
        "INSERT INTO cycles (start_ts, end_ts, duration_s, mode, "
        "is_transient, is_reconstructed) VALUES (?, ?, ?, ?, ?, 0)",
        (s, e, int(e - s), mode, is_transient),
    )
    cid = cur.lastrowid
    await cur.close()
    await conn.commit()
    return int(cid)


async def _sample(db, ts, cop=3.5, mode='heating', lwt=40.0,
                  outdoor=5.0, artifact=0):
    conn = db._require()
    await conn.execute(
        "INSERT INTO cop_samples (ts, cop, lwt, outdoor, flow_lmin, "
        "power_stable, mode, is_transition_artifact) "
        "VALUES (?, ?, ?, ?, 26.0, 1, ?, ?)",
        (ts, cop, lwt, outdoor, mode, artifact),
    )
    await conn.commit()


@pytest.fixture
async def db(tmp_path: Path):
    d = CycleDB(tmp_path / "e2e.db")
    await d.async_open()
    await d.async_initialize()
    yield d
    await d.async_close()


async def test_e2e_full_migration_on_synthetic_fleet(db):
    """Fleet scenario: pure-dhw cycle + mixed cycle + split pair + orphan."""
    # Cycle 1: pure dhw (ratio=1.0) -> shape A relabel
    await _cycle(db, 1000.0, 2000.0, mode='heating')
    for ts in (1100.0, 1400.0, 1700.0):
        await _sample(db, ts, mode='dhw', cop=4.0)

    # Cycle 2: mixed heating+dhw (ratio 0.5) -> shape B split
    # NOTE: heating cop=3.5 (realistic; at lwt=40 out=5 Carnot ceiling
    # is 4.92 — cop>4.92 correctly flagged as artifact by R445e).
    await _cycle(db, 3000.0, 5000.0, mode='heating')
    for ts in (3100.0, 3400.0, 3700.0, 4000.0):
        await _sample(db, ts, mode='heating', cop=3.5)
    for ts in (4200.0, 4400.0, 4600.0, 4800.0):
        await _sample(db, ts, mode='dhw', cop=3.5)

    # Cycle 3+4: split pair (gap 30s) -> R446b merge
    await _cycle(db, 6000.0, 7000.0, mode='dhw')
    await _cycle(db, 7030.0, 8000.0, mode='dhw')

    # Orphan dhw run (no cycle) -> R446 synthesis
    for ts in (10000.0, 10300.0, 10600.0, 10900.0, 11200.0):
        await _sample(db, ts, mode='dhw', cop=4.0)

    # Artifact sample (invalid Carnot) -> R445e flag
    await _sample(db, 1500.0, cop=99.0, lwt=30.0, outdoor=8.0)

    # Run full migration
    stats = await db.async_migrate_to_v18()
    assert stats.get("skipped") is None
    assert stats["completed"] is True
    assert stats["shape_a_relabelled"] >= 1
    assert stats["shape_b_split"] >= 1
    assert stats["splits_merged"] >= 1
    assert stats["cycles_synthesized"] >= 1
    assert stats["artifacts_flagged"] >= 1

    marker = await db.async_get_model_state("data_migration_v1_12_4")
    assert marker is not None
    assert marker.get("completed") is True

    stats2 = await db.async_migrate_to_v18()
    assert stats2 == {"skipped": 1}


async def test_e2e_rollback_data_preserved(db):
    """After migration, mode_original records enough for manual rollback."""
    await _cycle(db, 1000.0, 2000.0, mode='heating')
    for ts in (1100.0, 1400.0, 1700.0):
        await _sample(db, ts, mode='dhw', cop=4.0)
    await db.async_migrate_to_v18()

    conn = db._require()
    cur = await conn.execute(
        "SELECT mode, mode_original FROM cycles "
        "WHERE mode_original IS NOT NULL"
    )
    rows = await cur.fetchall()
    await cur.close()
    assert len(rows) >= 1
    for mode, orig in rows:
        assert orig is not None
