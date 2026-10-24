"""v1.12.4 Phase 3 R445d: relabel unknown samples inside cycle windows.

Coverage:
- sample inside dhw cycle -> mode='dhw', mode_original='unknown'
- sample inside heating cycle -> mode='heating'
- sample outside any cycle -> unchanged
- sample inside cycle with mode=NULL -> unchanged
- sample inside cycle with mode='unknown' -> unchanged
- integration: skeleton populates unknown_in_dhw_fixed stat
- idempotency: second run returns 0 (already relabeled -> not 'unknown')
"""
from __future__ import annotations

from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB


async def _insert_cycle(
    db: CycleDB, start_ts: float, end_ts: float,
    mode: str | None = 'heating',
) -> int:
    conn = db._require()
    cur = await conn.execute(
        "INSERT INTO cycles (start_ts, end_ts, duration_s, mode, "
        "is_transient, is_reconstructed) VALUES (?, ?, ?, ?, 0, 0)",
        (start_ts, end_ts, int(end_ts - start_ts), mode),
    )
    cid = cur.lastrowid
    await cur.close()
    await conn.commit()
    return int(cid)


async def _insert_sample(
    db: CycleDB, ts: float, mode: str = 'unknown',
) -> int:
    conn = db._require()
    cur = await conn.execute(
        "INSERT INTO cop_samples (ts, cop, mode, lwt, outdoor, "
        "flow_lmin, power_stable) VALUES (?, 3.5, ?, 40.0, 5.0, 26.0, 1)",
        (ts, mode),
    )
    sid = cur.lastrowid
    await cur.close()
    await conn.commit()
    return int(sid)


async def _fetch_sample(db: CycleDB, sample_id: int) -> dict:
    conn = db._require()
    cur = await conn.execute(
        "SELECT id, mode, mode_original FROM cop_samples WHERE id=?",
        (sample_id,),
    )
    row = await cur.fetchone()
    await cur.close()
    return dict(zip(("id", "mode", "mode_original"), row))


@pytest.fixture
async def db(tmp_path: Path):
    d = CycleDB(tmp_path / "r445d.db")
    await d.async_open()
    await d.async_initialize()
    yield d
    await d.async_close()


async def test_relabels_unknown_inside_dhw_cycle(db):
    await _insert_cycle(db, 1000.0, 2000.0, mode='dhw')
    sid = await _insert_sample(db, 1500.0, mode='unknown')
    n = await db._relabel_in_cycle_unknowns()
    assert n == 1
    s = await _fetch_sample(db, sid)
    assert s["mode"] == 'dhw'
    assert s["mode_original"] == 'unknown'


async def test_relabels_unknown_inside_heating_cycle(db):
    await _insert_cycle(db, 1000.0, 2000.0, mode='heating')
    sid = await _insert_sample(db, 1500.0, mode='unknown')
    n = await db._relabel_in_cycle_unknowns()
    assert n == 1
    s = await _fetch_sample(db, sid)
    assert s["mode"] == 'heating'
    assert s["mode_original"] == 'unknown'


async def test_skips_unknown_outside_any_cycle(db):
    await _insert_cycle(db, 1000.0, 2000.0, mode='dhw')
    sid = await _insert_sample(db, 5000.0, mode='unknown')  # outside
    n = await db._relabel_in_cycle_unknowns()
    assert n == 0
    s = await _fetch_sample(db, sid)
    assert s["mode"] == 'unknown'
    assert s["mode_original"] is None


async def test_skips_unknown_inside_null_mode_cycle(db):
    await _insert_cycle(db, 1000.0, 2000.0, mode=None)
    sid = await _insert_sample(db, 1500.0, mode='unknown')
    n = await db._relabel_in_cycle_unknowns()
    assert n == 0
    s = await _fetch_sample(db, sid)
    assert s["mode"] == 'unknown'


async def test_skips_unknown_inside_unknown_mode_cycle(db):
    await _insert_cycle(db, 1000.0, 2000.0, mode='unknown')
    sid = await _insert_sample(db, 1500.0, mode='unknown')
    n = await db._relabel_in_cycle_unknowns()
    assert n == 0
    s = await _fetch_sample(db, sid)
    assert s["mode"] == 'unknown'


async def test_idempotent_second_run_returns_zero(db):
    await _insert_cycle(db, 1000.0, 2000.0, mode='dhw')
    await _insert_sample(db, 1500.0, mode='unknown')
    first = await db._relabel_in_cycle_unknowns()
    second = await db._relabel_in_cycle_unknowns()
    assert first == 1
    assert second == 0


async def test_skips_known_samples_unaffected(db):
    """Non-unknown samples untouched even if inside cycle."""
    await _insert_cycle(db, 1000.0, 2000.0, mode='dhw')
    sid = await _insert_sample(db, 1500.0, mode='heating')
    n = await db._relabel_in_cycle_unknowns()
    assert n == 0
    s = await _fetch_sample(db, sid)
    assert s["mode"] == 'heating'
    assert s["mode_original"] is None


async def test_skeleton_wires_step_2_stat(db):
    await _insert_cycle(db, 1000.0, 2000.0, mode='dhw')
    await _insert_sample(db, 1500.0, mode='unknown')
    stats = await db.async_migrate_to_v18()
    assert stats["unknown_in_dhw_fixed"] == 1
