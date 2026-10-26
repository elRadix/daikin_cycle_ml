"""v1.12.9 (#131): forward bridge-aware cycle merge."""
from __future__ import annotations

from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB


async def _insert_cycle(
    db: CycleDB, start_ts: float, end_ts: float,
    mode: str = "dhw", is_transient: int = 0,
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


async def _insert_features(db: CycleDB, cid: int) -> None:
    conn = db._require()
    await conn.execute(
        "INSERT OR IGNORE INTO features (cycle_id, vector_json) "
        "VALUES (?, ?)", (cid, "[0,0,0,0,0,0,0,0,0,0,0,0]"),
    )
    await conn.commit()


async def _insert_sample(
    db: CycleDB, ts: float, cop: float = 3.5, mode: str = "dhw",
) -> None:
    conn = db._require()
    await conn.execute(
        "INSERT INTO cop_samples (ts, cop, lwt, outdoor, "
        "flow_lmin, power_stable, mode) "
        "VALUES (?, ?, 40.0, 5.0, 26.0, 1, ?)", (ts, cop, mode),
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


async def _count(db: CycleDB) -> int:
    conn = db._require()
    cur = await conn.execute("SELECT COUNT(*) FROM cycles")
    row = await cur.fetchone()
    await cur.close()
    return int(row[0])


@pytest.fixture
async def db(tmp_path: Path):
    d = CycleDB(tmp_path / "v1129_131.db")
    await d.async_open()
    await d.async_initialize()
    yield d
    await d.async_close()


async def test_simple_two_cycle_merge(db):
    a = await _insert_cycle(db, 1000.0, 1600.0, "dhw", 0)
    b = await _insert_cycle(db, 1660.0, 2200.0, "dhw", 0)
    await _insert_sample(db, 1200.0, 3.5, "dhw")
    await _insert_sample(db, 1800.0, 3.7, "dhw")
    absorbed = await db.async_merge_cycle_forward(b)
    assert absorbed == 1
    assert await _count(db) == 1
    keeper = await _get_cycle(db, a)
    assert keeper is not None
    assert keeper["end_ts"] == 2200.0
    assert keeper["duration_s"] == 1200
    assert keeper["is_reconstructed"] == 1
    assert keeper["cop_sample_count"] == 2
    assert await _get_cycle(db, b) is None


async def test_bridge_three_cycle_merge_131_pattern(db):
    a = await _insert_cycle(db, 1000.0, 1900.0, "dhw", 0)
    ghost = await _insert_cycle(db, 1930.0, 1990.0, "dhw", 1)
    b = await _insert_cycle(db, 2050.0, 3000.0, "dhw", 0)
    await _insert_features(db, ghost)
    await _insert_sample(db, 1200.0, 3.5, "dhw")
    await _insert_sample(db, 2500.0, 3.9, "dhw")
    absorbed = await db.async_merge_cycle_forward(b)
    assert absorbed == 2
    assert await _count(db) == 1
    keeper = await _get_cycle(db, a)
    assert keeper is not None
    assert keeper["end_ts"] == 3000.0
    assert keeper["duration_s"] == 2000
    assert keeper["is_reconstructed"] == 1
    assert keeper["cop_sample_count"] == 2
    assert await _get_cycle(db, ghost) is None
    assert await _get_cycle(db, b) is None
    conn = db._require()
    cur = await conn.execute(
        "SELECT COUNT(*) FROM features WHERE cycle_id=?", (ghost,)
    )
    row = await cur.fetchone()
    await cur.close()
    assert int(row[0]) == 0


async def test_gap_too_large_no_merge(db):
    a = await _insert_cycle(db, 1000.0, 1600.0, "dhw", 0)
    b = await _insert_cycle(db, 1800.0, 2400.0, "dhw", 0)
    absorbed = await db.async_merge_cycle_forward(b)
    assert absorbed == 0
    assert await _count(db) == 2
    assert (await _get_cycle(db, a))["end_ts"] == 1600.0
    assert (await _get_cycle(db, b))["end_ts"] == 2400.0


async def test_different_mode_no_merge(db):
    await _insert_cycle(db, 1000.0, 1600.0, "heating", 0)
    b = await _insert_cycle(db, 1660.0, 2200.0, "dhw", 0)
    absorbed = await db.async_merge_cycle_forward(b)
    assert absorbed == 0
    assert await _count(db) == 2


async def test_new_is_transient_no_merge(db):
    await _insert_cycle(db, 1000.0, 1600.0, "dhw", 0)
    b = await _insert_cycle(db, 1660.0, 1720.0, "dhw", 1)
    absorbed = await db.async_merge_cycle_forward(b)
    assert absorbed == 0
    assert await _count(db) == 2


async def test_pp_transient_bridge_blocked(db):
    await _insert_cycle(db, 1000.0, 1600.0, "dhw", 1)
    await _insert_cycle(db, 1660.0, 1720.0, "dhw", 1)
    b = await _insert_cycle(db, 1780.0, 2400.0, "dhw", 0)
    absorbed = await db.async_merge_cycle_forward(b)
    assert absorbed == 0
    assert await _count(db) == 3


async def test_only_one_cycle_no_merge(db):
    a = await _insert_cycle(db, 1000.0, 1600.0, "dhw", 0)
    absorbed = await db.async_merge_cycle_forward(a)
    assert absorbed == 0
    assert await _count(db) == 1


async def test_idempotency_new_id_not_latest(db):
    a = await _insert_cycle(db, 1000.0, 1600.0, "dhw", 0)
    await _insert_cycle(db, 1660.0, 2200.0, "dhw", 0)
    absorbed = await db.async_merge_cycle_forward(a)
    assert absorbed == 0
    assert await _count(db) == 2


async def test_empty_db_no_merge(db):
    absorbed = await db.async_merge_cycle_forward(999)
    assert absorbed == 0


async def test_reverse_bridge_negative_gap_blocked(db):
    await _insert_cycle(db, 1000.0, 2000.0, "dhw", 0)
    b = await _insert_cycle(db, 1500.0, 2100.0, "dhw", 0)
    absorbed = await db.async_merge_cycle_forward(b)
    assert absorbed == 0
    assert await _count(db) == 2


async def test_merge_updates_cop_aggregates(db):
    a = await _insert_cycle(db, 1000.0, 1600.0, "dhw", 0)
    b = await _insert_cycle(db, 1660.0, 2200.0, "dhw", 0)
    await _insert_sample(db, 1100.0, 3.0, "dhw")
    await _insert_sample(db, 1300.0, 3.0, "dhw")
    await _insert_sample(db, 1800.0, 5.0, "dhw")
    await _insert_sample(db, 2000.0, 5.0, "dhw")
    absorbed = await db.async_merge_cycle_forward(b)
    assert absorbed == 1
    keeper = await _get_cycle(db, a)
    assert keeper["cop_sample_count"] == 4
    assert keeper["cop_avg"] is not None
    assert 3.0 <= keeper["cop_avg"] <= 5.0

async def test_bridge_blocked_when_only_two_rows(db):
    """L1120 branch: prev is transient but no pp row exists.

    Setup: 1 transient cycle + 1 new non-transient cycle (only 2 rows).
    """
    prev = await _insert_cycle(db, 1000.0, 1600.0, "dhw", 1)
    b = await _insert_cycle(db, 1660.0, 2200.0, "dhw", 0)
    absorbed = await db.async_merge_cycle_forward(b)
    assert absorbed == 0
    assert await _count(db) == 2
    assert (await _get_cycle(db, prev))["end_ts"] == 1600.0
    assert (await _get_cycle(db, b))["end_ts"] == 2200.0


async def test_bridge_blocked_when_pp_gap_too_large(db):
    """L1125 branch: pp non-transient same mode, gap(pp,prev) >= 120."""
    pp = await _insert_cycle(db, 1000.0, 1990.0, "dhw", 0)
    prev = await _insert_cycle(db, 2200.0, 2260.0, "dhw", 1)
    b = await _insert_cycle(db, 2320.0, 3000.0, "dhw", 0)
    absorbed = await db.async_merge_cycle_forward(b)
    assert absorbed == 0
    assert await _count(db) == 3
    assert (await _get_cycle(db, pp))["end_ts"] == 1990.0
    assert (await _get_cycle(db, prev))["end_ts"] == 2260.0
    assert (await _get_cycle(db, b))["end_ts"] == 3000.0
