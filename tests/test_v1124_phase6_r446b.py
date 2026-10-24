"""v1.12.4 Phase 6 R446b: merge adjacent same-mode split cycles."""
from __future__ import annotations

from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB


async def _insert_cycle(
    db: CycleDB, start_ts: float, end_ts: float,
    mode: str = 'dhw', is_transient: int = 0,
) -> int:
    conn = db._require()
    cur = await conn.execute(
        "INSERT INTO cycles (start_ts, end_ts, duration_s, mode, "
        "is_transient, is_reconstructed) VALUES (?, ?, ?, ?, ?, 0)",
        (start_ts, end_ts, int(end_ts - start_ts), mode, is_transient),
    )
    cid = cur.lastrowid
    await cur.close()
    await conn.commit()
    return int(cid)


async def _insert_sample(db: CycleDB, ts: float, cop: float = 3.5) -> None:
    conn = db._require()
    await conn.execute(
        "INSERT INTO cop_samples (ts, cop, lwt, outdoor, "
        "flow_lmin, power_stable, mode) "
        "VALUES (?, ?, 40.0, 5.0, 26.0, 1, 'dhw')", (ts, cop),
    )
    await conn.commit()


async def _get_cycle(db: CycleDB, cid: int) -> dict | None:
    conn = db._require()
    cur = await conn.execute(
        "SELECT id, start_ts, end_ts, duration_s, mode, cop_avg, "
        "cop_sample_count, is_reconstructed FROM cycles WHERE id=?",
        (cid,),
    )
    row = await cur.fetchone()
    await cur.close()
    if row is None:
        return None
    cols = ("id", "start_ts", "end_ts", "duration_s", "mode",
            "cop_avg", "cop_sample_count", "is_reconstructed")
    return dict(zip(cols, row))


async def _count_cycles(db: CycleDB) -> int:
    conn = db._require()
    cur = await conn.execute("SELECT COUNT(*) FROM cycles")
    row = await cur.fetchone()
    await cur.close()
    return int(row[0])


@pytest.fixture
async def db(tmp_path: Path):
    d = CycleDB(tmp_path / "r446b.db")
    await d.async_open()
    await d.async_initialize()
    yield d
    await d.async_close()


async def test_merges_single_pair(db):
    keep_id = await _insert_cycle(db, 1000.0, 2000.0, mode='dhw')
    drop_id = await _insert_cycle(db, 2030.0, 3000.0, mode='dhw')
    await _insert_sample(db, 1500.0, cop=3.0)
    await _insert_sample(db, 2500.0, cop=4.0)
    n = await db._merge_adjacent_same_mode_cycles()
    assert n == 1
    assert await _get_cycle(db, drop_id) is None
    kept = await _get_cycle(db, keep_id)
    assert kept is not None
    assert kept["end_ts"] == pytest.approx(3000.0)
    assert kept["duration_s"] == 2000
    assert kept["is_reconstructed"] == 1


async def test_merges_chain_of_three(db):
    id1 = await _insert_cycle(db, 1000.0, 1500.0, mode='dhw')
    id2 = await _insert_cycle(db, 1530.0, 2000.0, mode='dhw')
    id3 = await _insert_cycle(db, 2030.0, 2500.0, mode='dhw')
    n = await db._merge_adjacent_same_mode_cycles()
    assert n == 2
    assert await _get_cycle(db, id2) is None
    assert await _get_cycle(db, id3) is None
    kept = await _get_cycle(db, id1)
    assert kept is not None
    assert kept["end_ts"] == pytest.approx(2500.0)


async def test_skips_gap_too_large(db):
    await _insert_cycle(db, 1000.0, 2000.0, mode='dhw')
    await _insert_cycle(db, 2200.0, 3000.0, mode='dhw')
    n = await db._merge_adjacent_same_mode_cycles()
    assert n == 0
    assert await _count_cycles(db) == 2


async def test_skips_different_mode(db):
    await _insert_cycle(db, 1000.0, 2000.0, mode='heating')
    await _insert_cycle(db, 2030.0, 3000.0, mode='dhw')
    n = await db._merge_adjacent_same_mode_cycles()
    assert n == 0


async def test_skips_transient_first(db):
    await _insert_cycle(db, 1000.0, 2000.0, mode='dhw', is_transient=1)
    await _insert_cycle(db, 2030.0, 3000.0, mode='dhw')
    n = await db._merge_adjacent_same_mode_cycles()
    assert n == 0


async def test_skips_transient_second(db):
    await _insert_cycle(db, 1000.0, 2000.0, mode='dhw')
    await _insert_cycle(db, 2030.0, 3000.0, mode='dhw', is_transient=1)
    n = await db._merge_adjacent_same_mode_cycles()
    assert n == 0


async def test_recomputes_aggregates(db):
    keep_id = await _insert_cycle(db, 1000.0, 2000.0, mode='dhw')
    await _insert_cycle(db, 2030.0, 3000.0, mode='dhw')
    for ts, cop in [(1100.0, 3.0), (1500.0, 3.5), (2100.0, 4.0),
                    (2500.0, 4.5)]:
        await _insert_sample(db, ts, cop=cop)
    await db._merge_adjacent_same_mode_cycles()
    kept = await _get_cycle(db, keep_id)
    assert kept is not None
    assert kept["cop_sample_count"] == 4
    assert kept["cop_avg"] == pytest.approx(3.75)


async def test_deletes_features_row(db):
    await _insert_cycle(db, 1000.0, 2000.0, mode='dhw')
    drop_id = await _insert_cycle(db, 2030.0, 3000.0, mode='dhw')
    conn = db._require()
    await conn.execute(
        "INSERT INTO features (cycle_id, vector_json) VALUES (?, ?)",
        (drop_id, "[0,0,0,0,0,0,0,0,0,0,0,0]"),
    )
    await conn.commit()
    n = await db._merge_adjacent_same_mode_cycles()
    assert n == 1
    cur = await conn.execute(
        "SELECT COUNT(*) FROM features WHERE cycle_id=?", (drop_id,)
    )
    row = await cur.fetchone()
    await cur.close()
    assert int(row[0]) == 0


async def test_idempotent_second_run(db):
    await _insert_cycle(db, 1000.0, 2000.0, mode='dhw')
    await _insert_cycle(db, 2030.0, 3000.0, mode='dhw')
    first = await db._merge_adjacent_same_mode_cycles()
    second = await db._merge_adjacent_same_mode_cycles()
    assert first == 1
    assert second == 0


async def test_skeleton_wires_step_5_stat(db):
    await _insert_cycle(db, 1000.0, 2000.0, mode='dhw')
    await _insert_cycle(db, 2030.0, 3000.0, mode='dhw')
    stats = await db.async_migrate_to_v18()
    assert stats["splits_merged"] == 1
