"""v1.12.4 Phase 5 R446: orphan DHW synthesis.

Tests cover:
- Single continuous run >= 15min -> 1 synthetic cycle
- Short run < 15min -> skipped
- Two runs separated by gap > 15min -> 2 cycles
- Run covered by existing cycle window -> skipped (NOT EXISTS)
- Real COUNT from samples not cached (#133)
- Artifact exclusion from cop_avg + cop_sample_count
- Idempotency (INSERT OR IGNORE on UNIQUE(start_ts))
- thermal_kw_avg is NULL (R5T unavailable in cop_samples)
- Skeleton integration: stats["cycles_synthesized"]
"""
from __future__ import annotations

from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB


async def _insert_cycle(
    db: CycleDB, start_ts: float, end_ts: float, mode: str = 'heating',
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
    db: CycleDB, ts: float, cop: float = 3.5, mode: str = 'dhw',
    is_transition_artifact: int = 0,
) -> int:
    conn = db._require()
    cur = await conn.execute(
        "INSERT INTO cop_samples "
        "(ts, cop, lwt, outdoor, flow_lmin, power_stable, mode, "
        "is_transition_artifact) "
        "VALUES (?, ?, 40.0, 5.0, 26.0, 1, ?, ?)",
        (ts, cop, mode, is_transition_artifact),
    )
    sid = cur.lastrowid
    await cur.close()
    await conn.commit()
    return int(sid)


async def _fetch_synth_cycle(db: CycleDB, start_ts: float) -> dict | None:
    conn = db._require()
    cur = await conn.execute(
        "SELECT id, start_ts, end_ts, duration_s, mode, mode_original, "
        "cop_avg, cop_sample_count, thermal_kw_avg, is_reconstructed "
        "FROM cycles WHERE start_ts = ?",
        (start_ts,),
    )
    row = await cur.fetchone()
    await cur.close()
    if row is None:
        return None
    cols = ("id", "start_ts", "end_ts", "duration_s", "mode",
            "mode_original", "cop_avg", "cop_sample_count",
            "thermal_kw_avg", "is_reconstructed")
    return dict(zip(cols, row))


@pytest.fixture
async def db(tmp_path: Path):
    d = CycleDB(tmp_path / "r446.db")
    await d.async_open()
    await d.async_initialize()
    yield d
    await d.async_close()


async def test_synthesizes_single_orphan_run(db):
    """5 dhw samples spanning 1200s (20min) with no existing cycles."""
    for ts in (1000.0, 1300.0, 1600.0, 1900.0, 2200.0):
        await _insert_sample(db, ts, cop=3.5)
    n = await db._synthesize_orphan_dhw_runs()
    assert n == 1
    cyc = await _fetch_synth_cycle(db, 1000.0)
    assert cyc is not None
    assert cyc["end_ts"] == pytest.approx(2200.0)
    assert cyc["duration_s"] == 1200
    assert cyc["mode"] == 'dhw'
    assert cyc["mode_original"] == 'dhw'
    assert cyc["is_reconstructed"] == 1


async def test_skips_short_run(db):
    """Only 600s span -> below 900s min -> skipped."""
    for ts in (1000.0, 1300.0, 1600.0):
        await _insert_sample(db, ts)
    n = await db._synthesize_orphan_dhw_runs()
    assert n == 0


async def test_groups_split_by_gap(db):
    """Two runs 1200s each, separated by 2800s gap -> 2 cycles."""
    for ts in (1000.0, 1300.0, 1600.0, 1900.0, 2200.0):
        await _insert_sample(db, ts)
    for ts in (5000.0, 5300.0, 5600.0, 5900.0, 6200.0):
        await _insert_sample(db, ts)
    n = await db._synthesize_orphan_dhw_runs()
    assert n == 2
    assert await _fetch_synth_cycle(db, 1000.0) is not None
    assert await _fetch_synth_cycle(db, 5000.0) is not None


async def test_skips_run_covered_by_existing_cycle(db):
    """Samples inside existing cycle window -> not orphans -> skipped."""
    await _insert_cycle(db, 500.0, 2500.0, mode='heating')
    for ts in (1000.0, 1300.0, 1600.0, 1900.0, 2200.0):
        await _insert_sample(db, ts)
    n = await db._synthesize_orphan_dhw_runs()
    assert n == 0


async def test_uses_real_count_not_stored(db):
    """Synthesized cycle cop_sample_count = COUNT(*), not cached value."""
    for ts in (1000.0, 1300.0, 1600.0, 1900.0, 2200.0):
        await _insert_sample(db, ts)
    await db._synthesize_orphan_dhw_runs()
    cyc = await _fetch_synth_cycle(db, 1000.0)
    assert cyc is not None
    assert cyc["cop_sample_count"] == 5


async def test_excludes_artifacts_from_avg_and_count(db):
    """Flagged artifacts not counted in cop_avg/cop_sample_count."""
    # 3 valid + 2 artifacts in same run
    await _insert_sample(db, 1000.0, cop=3.5)
    await _insert_sample(db, 1300.0, cop=3.5)
    await _insert_sample(db, 1600.0, cop=3.5)
    await _insert_sample(db, 1900.0, cop=99.9, is_transition_artifact=1)
    await _insert_sample(db, 2200.0, cop=99.9, is_transition_artifact=1)
    await db._synthesize_orphan_dhw_runs()
    cyc = await _fetch_synth_cycle(db, 1000.0)
    assert cyc is not None
    assert cyc["cop_sample_count"] == 3
    assert cyc["cop_avg"] == pytest.approx(3.5)


async def test_idempotent_second_run(db):
    for ts in (1000.0, 1300.0, 1600.0, 1900.0, 2200.0):
        await _insert_sample(db, ts)
    first = await db._synthesize_orphan_dhw_runs()
    second = await db._synthesize_orphan_dhw_runs()
    assert first == 1
    assert second == 0


async def test_thermal_kw_avg_is_null(db):
    """Explicit doc: R5T not stored -> thermal_kw_avg is NULL."""
    for ts in (1000.0, 1300.0, 1600.0, 1900.0, 2200.0):
        await _insert_sample(db, ts)
    await db._synthesize_orphan_dhw_runs()
    cyc = await _fetch_synth_cycle(db, 1000.0)
    assert cyc is not None
    assert cyc["thermal_kw_avg"] is None


async def test_skeleton_wires_step_4_stat(db):
    for ts in (1000.0, 1300.0, 1600.0, 1900.0, 2200.0):
        await _insert_sample(db, ts)
    stats = await db.async_migrate_to_v18()
    assert stats["cycles_synthesized"] == 1
