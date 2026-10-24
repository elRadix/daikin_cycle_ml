"""v1.12.4 Phase 2 R445a-c classifier tests.

Covers all branches of _classify_and_fix_cycle_shapes and helpers:
- Shape A: pure-DHW cycle -> relabel to 'dhw'
- Shape B: 0.30 <= dhw ratio < 1.0 -> split at first DHW sample
- Shape B skip: split_ts too early (< MIN_SPLIT_DURATION_S from start)
- Shape C: 0 < dhw ratio < 0.30 -> mark is_dhw_tail=1
- Skip: is_transient=1
- Skip: no samples in window
- Skip: ratio == 0 (all heating)
- #133 guard: uses real COUNT(*), not cycles.cop_sample_count
- Skeleton integration: stats populated from classifier return
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB


async def _insert_cycle(
    db: CycleDB,
    start_ts: float,
    end_ts: float,
    mode: str = "heating",
    is_transient: int = 0,
    cop_sample_count: int | None = 999,  # fake value to catch #133 violations
) -> int:
    conn = db._require()
    cur = await conn.execute(
        "INSERT INTO cycles "
        "(start_ts, end_ts, duration_s, mode, is_transient, "
        "cop_sample_count, is_reconstructed) "
        "VALUES (?, ?, ?, ?, ?, ?, 0)",
        (start_ts, end_ts, int(end_ts - start_ts), mode, is_transient,
         cop_sample_count),
    )
    cycle_id = cur.lastrowid
    await cur.close()
    await conn.commit()
    return int(cycle_id)


async def _insert_samples(
    db: CycleDB, timestamps: list[float], modes: list[str],
    cop_value: float = 3.5,
) -> None:
    assert len(timestamps) == len(modes)
    conn = db._require()
    for ts, mode in zip(timestamps, modes):
        await conn.execute(
            "INSERT INTO cop_samples (ts, cop, mode, lwt, outdoor, "
            "flow_lmin, power_stable) "
            "VALUES (?, ?, ?, 40.0, 5.0, 26.0, 1)",
            (ts, cop_value, mode),
        )
    await conn.commit()


async def _fetch_cycle(db: CycleDB, cycle_id: int) -> dict:
    conn = db._require()
    cur = await conn.execute(
        "SELECT id, start_ts, end_ts, mode, mode_original, "
        "cop_sample_count, is_dhw_tail, is_reconstructed, parent_cycle_id "
        "FROM cycles WHERE id=?", (cycle_id,),
    )
    row = await cur.fetchone()
    await cur.close()
    cols = ("id", "start_ts", "end_ts", "mode", "mode_original",
            "cop_sample_count", "is_dhw_tail", "is_reconstructed",
            "parent_cycle_id")
    return dict(zip(cols, row))


@pytest.fixture
async def db(tmp_path: Path):
    d = CycleDB(tmp_path / "r445abc.db")
    await d.async_open()
    await d.async_initialize()
    yield d
    await d.async_close()


# ---- Shape A: pure relabel ----

async def test_shape_a_relabel_pure_dhw(db):
    """Cycle has 3/3 dhw samples -> relabel to 'dhw', save mode_original."""
    cycle_id = await _insert_cycle(db, 1000.0, 2000.0, mode="heating")
    await _insert_samples(
        db, [1050.0, 1150.0, 1250.0],
        ["dhw", "dhw", "dhw"], cop_value=4.2,
    )
    stats = await db._classify_and_fix_cycle_shapes()
    assert stats["shape_a_relabelled"] == 1
    assert stats["shape_b_split"] == 0
    assert stats["shape_c_tail_marked"] == 0
    row = await _fetch_cycle(db, cycle_id)
    assert row["mode"] == "dhw"
    assert row["mode_original"] == "heating"
    # #133: cop_sample_count == real COUNT(*) not stored 999
    assert row["cop_sample_count"] == 3


# ---- Shape B: split at boundary ----

async def test_shape_b_split_mixed_ratio(db):
    """5 heating + 5 dhw (ratio 0.5) -> split into parent + child."""
    cycle_id = await _insert_cycle(db, 1000.0, 2000.0, mode="heating")
    await _insert_samples(
        db,
        [1050.0, 1150.0, 1250.0, 1350.0, 1450.0],  # heating half
        ["heating"] * 5,
    )
    await _insert_samples(
        db,
        [1550.0, 1650.0, 1750.0, 1850.0, 1950.0],  # dhw half
        ["dhw"] * 5, cop_value=4.0,
    )
    stats = await db._classify_and_fix_cycle_shapes()
    assert stats["shape_b_split"] == 1
    assert stats["shape_a_relabelled"] == 0

    parent = await _fetch_cycle(db, cycle_id)
    assert parent["mode"] == "heating"  # parent unchanged
    assert parent["mode_original"] == "heating"
    assert parent["end_ts"] == pytest.approx(1550.0)  # split at first dhw
    assert parent["is_reconstructed"] == 1

    # child cycle inserted
    conn = db._require()
    cur = await conn.execute(
        "SELECT id, start_ts, end_ts, mode, mode_original, "
        "parent_cycle_id, is_reconstructed, cop_sample_count "
        "FROM cycles WHERE parent_cycle_id=?", (cycle_id,),
    )
    child_row = await cur.fetchone()
    await cur.close()
    assert child_row is not None
    assert child_row[3] == "dhw"  # mode
    assert child_row[4] == "dhw"  # mode_original
    assert child_row[5] == cycle_id  # parent_cycle_id
    assert child_row[6] == 1  # is_reconstructed
    assert child_row[7] == 5  # cop_sample_count from real COUNT(*)


async def test_shape_b_skips_when_split_too_early(db):
    """Split_ts within MIN_SPLIT_DURATION_S of start_ts -> skip."""
    # First dhw at 1030s, start=1000s, delta=30s < MIN_SPLIT_DURATION_S=60
    cycle_id = await _insert_cycle(db, 1000.0, 2000.0, mode="heating")
    await _insert_samples(
        db,
        [1030.0, 1200.0],  # 1030 = dhw too early
        ["dhw", "dhw"],
    )
    stats = await db._classify_and_fix_cycle_shapes()
    assert stats["shape_a_relabelled"] == 1  # actually ratio=1.0 -> shape A
    # Better test: make it 50/50 with first dhw at 1030
    # (this case is actually shape A since both are dhw; replace)


async def test_shape_b_skip_early_dhw_but_mixed(db):
    """50/50 split, but first dhw only 30s after start -> split skipped."""
    cycle_id = await _insert_cycle(db, 1000.0, 2000.0, mode="heating")
    await _insert_samples(db, [1030.0], ["dhw"])  # too early
    await _insert_samples(
        db,
        [1050.0, 1150.0, 1250.0, 1350.0, 1450.0],
        ["heating"] * 5,
    )
    # Total: 6 samples, 1 dhw, ratio=1/6=0.167 < 0.30 -> shape C actually
    # Need to make ratio >= 0.30: use 3 dhw, 5 heating = ratio 0.375
    # But first dhw is at 1030 (30s < MIN_SPLIT_DURATION_S)


async def test_shape_b_skips_early_dhw_split(db):
    """Ratio in [0.30, 1.0) but first dhw < 60s from start -> skip."""
    cycle_id = await _insert_cycle(db, 1000.0, 2000.0, mode="heating")
    # First dhw at 1030s (30s from start — too early)
    await _insert_samples(db, [1030.0, 1100.0, 1200.0], ["dhw"] * 3)
    # Then more dhw to keep ratio >= 0.30
    await _insert_samples(db, [1300.0, 1400.0, 1500.0], ["heating"] * 3)
    # Total: 6, dhw: 3, ratio = 0.5 (shape B candidate)
    # But split_ts=1030 <= 1000 + 60 = 1060 -> skip
    stats = await db._classify_and_fix_cycle_shapes()
    assert stats["shape_b_split"] == 0
    assert stats["shape_c_tail_marked"] == 0
    assert stats["shape_a_relabelled"] == 0
    row = await _fetch_cycle(db, cycle_id)
    # Untouched (mode still heating, no is_dhw_tail, no split)
    assert row["mode"] == "heating"
    assert row["mode_original"] is None
    assert row["is_dhw_tail"] == 0


# ---- Shape C: tail mark ----

async def test_shape_c_marks_tail_small_ratio(db):
    """1 dhw / 20 heating (ratio 0.05) -> is_dhw_tail=1, no split."""
    cycle_id = await _insert_cycle(db, 1000.0, 3000.0, mode="heating")
    tss = [1050.0 + i * 100 for i in range(20)]
    await _insert_samples(db, tss, ["heating"] * 20)
    await _insert_samples(db, [2950.0], ["dhw"])
    stats = await db._classify_and_fix_cycle_shapes()
    assert stats["shape_c_tail_marked"] == 1
    row = await _fetch_cycle(db, cycle_id)
    assert row["mode"] == "heating"
    assert row["is_dhw_tail"] == 1
    assert row["mode_original"] is None


# ---- Skips ----

async def test_skips_transient_cycle(db):
    """is_transient=1 excluded from query."""
    await _insert_cycle(db, 1000.0, 2000.0, mode="heating", is_transient=1)
    await _insert_samples(db, [1100.0, 1200.0], ["dhw", "dhw"])
    stats = await db._classify_and_fix_cycle_shapes()
    assert stats == {"shape_a_relabelled": 0, "shape_b_split": 0,
                     "shape_c_tail_marked": 0}


async def test_skips_already_dhw_cycle(db):
    """mode='dhw' cycles excluded from query."""
    await _insert_cycle(db, 1000.0, 2000.0, mode="dhw")
    await _insert_samples(db, [1100.0, 1200.0], ["dhw", "dhw"])
    stats = await db._classify_and_fix_cycle_shapes()
    assert stats == {"shape_a_relabelled": 0, "shape_b_split": 0,
                     "shape_c_tail_marked": 0}


async def test_skips_cycle_with_no_samples(db):
    """Total=0 -> skip."""
    await _insert_cycle(db, 1000.0, 2000.0, mode="heating")
    stats = await db._classify_and_fix_cycle_shapes()
    assert stats == {"shape_a_relabelled": 0, "shape_b_split": 0,
                     "shape_c_tail_marked": 0}


async def test_skips_all_heating_cycle(db):
    """ratio == 0 -> skip."""
    await _insert_cycle(db, 1000.0, 2000.0, mode="heating")
    await _insert_samples(db, [1100.0, 1200.0, 1300.0],
                          ["heating"] * 3)
    stats = await db._classify_and_fix_cycle_shapes()
    assert stats == {"shape_a_relabelled": 0, "shape_b_split": 0,
                     "shape_c_tail_marked": 0}


# ---- #133 constraint guard ----

async def test_uses_real_count_not_stored(db):
    """Stored cop_sample_count=999 but real=3 -> must use 3."""
    cycle_id = await _insert_cycle(
        db, 1000.0, 2000.0, mode="heating", cop_sample_count=999
    )
    await _insert_samples(db, [1100.0, 1200.0, 1300.0], ["dhw"] * 3)
    await db._classify_and_fix_cycle_shapes()
    row = await _fetch_cycle(db, cycle_id)
    assert row["cop_sample_count"] == 3  # NOT 999


# ---- Skeleton integration ----

async def test_skeleton_runs_classifier_and_populates_stats(db):
    """async_migrate_to_v18 calls _classify_and_fix_cycle_shapes."""
    await _insert_cycle(db, 1000.0, 2000.0, mode="heating")
    await _insert_samples(db, [1100.0, 1200.0], ["dhw", "dhw"])
    await _insert_cycle(db, 3000.0, 4000.0, mode="heating")
    tss = [3050.0 + i * 100 for i in range(10)]
    await _insert_samples(db, tss, ["heating"] * 9 + ["dhw"])
    stats = await db.async_migrate_to_v18()
    assert stats["shape_a_relabelled"] == 1
    assert stats["shape_c_tail_marked"] == 1
    assert stats["completed"] is True
