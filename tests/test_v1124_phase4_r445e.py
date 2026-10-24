"""v1.12.4 Phase 4 R445e: dynamic Carnot artifact flag.

Carnot = (lwt + 273.15) / (lwt - outdoor).
Bounds: cop in [0.05*Carnot, 0.55*Carnot] = valid.
Datasheet max k = 0.447 (A7/W35), so 0.55 gives 23% margin.

Tests cover:
- Flag cop=19.5, lwt=27, out=9.7 (Carnot=15.9, ratio 1.23 >> 0.55)
- Flag cop=10.4, lwt=28.5, out=11.2 (ratio 0.60 > 0.55)
- Preserve cop=7.5, lwt=30, out=12 (Carnot=16.8, ratio 0.45 < 0.55)
- Flag lwt <= outdoor (division guard)
- Idempotent (already flagged = 0 new)
- Live evidence sample: cop=16.486, lwt=30.9, out=8.8 -> flagged
- NULL lwt/outdoor -> flagged conservatively
"""
from __future__ import annotations

from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB


async def _insert_sample(
    db: CycleDB, ts: float, cop: float,
    lwt: float | None, outdoor: float | None,
) -> int:
    conn = db._require()
    cur = await conn.execute(
        "INSERT INTO cop_samples "
        "(ts, cop, lwt, outdoor, flow_lmin, power_stable, mode) "
        "VALUES (?, ?, ?, ?, 26.0, 1, 'heating')",
        (ts, cop, lwt, outdoor),
    )
    sid = cur.lastrowid
    await cur.close()
    await conn.commit()
    return int(sid)


async def _fetch_flag(db: CycleDB, sid: int) -> int:
    conn = db._require()
    cur = await conn.execute(
        "SELECT is_transition_artifact FROM cop_samples WHERE id=?",
        (sid,),
    )
    row = await cur.fetchone()
    await cur.close()
    return int(row[0])


@pytest.fixture
async def db(tmp_path: Path):
    d = CycleDB(tmp_path / "r445e.db")
    await d.async_open()
    await d.async_initialize()
    yield d
    await d.async_close()


async def test_flags_absolute_high_cop(db):
    """cop=19.5, lwt=27, out=9.7 -> Carnot=15.9, ratio 1.23 -> flagged."""
    sid = await _insert_sample(db, 1000.0, 19.5, 27.0, 9.7)
    n = await db._flag_carnot_artifacts()
    assert n == 1
    assert await _fetch_flag(db, sid) == 1


async def test_flags_relative_high_cop(db):
    """cop=10.4, lwt=28.5, out=11.2 -> Carnot=17.4, ratio 0.60 -> flagged."""
    sid = await _insert_sample(db, 1000.0, 10.4, 28.5, 11.2)
    n = await db._flag_carnot_artifacts()
    assert n == 1
    assert await _fetch_flag(db, sid) == 1


async def test_preserves_legit_mild_weather(db):
    """cop=7.5, lwt=30, out=12 -> Carnot=16.8, ratio 0.45 -> NOT flagged."""
    sid = await _insert_sample(db, 1000.0, 7.5, 30.0, 12.0)
    n = await db._flag_carnot_artifacts()
    assert n == 0
    assert await _fetch_flag(db, sid) == 0


async def test_flags_negative_dt_division_guard(db):
    """lwt <= outdoor -> unconditional flag (div-by-zero guard)."""
    sid1 = await _insert_sample(db, 1000.0, 3.5, 5.0, 10.0)   # lwt < out
    sid2 = await _insert_sample(db, 1100.0, 3.5, 10.0, 10.0)  # lwt == out
    n = await db._flag_carnot_artifacts()
    assert n == 2
    assert await _fetch_flag(db, sid1) == 1
    assert await _fetch_flag(db, sid2) == 1


async def test_flags_null_lwt_or_outdoor(db):
    """NULL lwt or outdoor -> flagged conservatively."""
    sid1 = await _insert_sample(db, 1000.0, 3.5, None, 8.0)
    sid2 = await _insert_sample(db, 1100.0, 3.5, 40.0, None)
    n = await db._flag_carnot_artifacts()
    assert n == 2
    assert await _fetch_flag(db, sid1) == 1
    assert await _fetch_flag(db, sid2) == 1


async def test_idempotent_second_run(db):
    """Already flagged sample is not re-flagged."""
    await _insert_sample(db, 1000.0, 19.5, 27.0, 9.7)
    first = await db._flag_carnot_artifacts()
    second = await db._flag_carnot_artifacts()
    assert first == 1
    assert second == 0


async def test_flags_live_evidence_sample_2712(db):
    """Real pre-fix artifact: cop=16.486, lwt=30.9, out=8.8 -> flagged."""
    sid = await _insert_sample(db, 1000.0, 16.486, 30.9, 8.8)
    n = await db._flag_carnot_artifacts()
    assert n == 1
    assert await _fetch_flag(db, sid) == 1


async def test_skeleton_wires_step_3_stat(db):
    await _insert_sample(db, 1000.0, 19.5, 27.0, 9.7)
    stats = await db.async_migrate_to_v18()
    assert stats["artifacts_flagged"] == 1
