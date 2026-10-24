"""v1.12.4 Phase 2 skeleton test.

Verifies async_migrate_to_v18() skeleton:
- Returns all-zero stats
- Does NOT write marker (Phase 9 adds marker write)
- Second call behaves identically (no skip branch since no marker)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB


@pytest.fixture
async def db(tmp_path: Path):
    d = CycleDB(tmp_path / "phase2.db")
    await d.async_open()
    await d.async_initialize()
    yield d
    await d.async_close()


async def test_skeleton_returns_all_zero_stats(db):
    stats = await db.async_migrate_to_v18()
    assert stats["shape_a_relabelled"] == 0
    assert stats["shape_b_split"] == 0
    assert stats["shape_c_tail_marked"] == 0
    assert stats["unknown_in_dhw_fixed"] == 0
    assert stats["artifacts_flagged"] == 0
    assert stats["cycles_synthesized"] == 0
    assert stats["splits_merged"] == 0
    assert stats["cop_aggregates_backfilled"] == 0
    assert stats["hours_rebuilt"] == 0
    assert stats["days_rebuilt"] == 0
    assert stats["energy_acc_rebuilt"] is False
    assert stats["completed"] is False


async def test_skeleton_does_not_write_marker(db):
    await db.async_migrate_to_v18()
    marker = await db.async_get_model_state("data_migration_v1_12_4")
    assert marker is None


async def test_skeleton_reentrant_no_skip(db):
    """Without marker, second call re-runs (still returns zeros)."""
    stats1 = await db.async_migrate_to_v18()
    stats2 = await db.async_migrate_to_v18()
    assert stats1.get("skipped") is None
    assert stats2.get("skipped") is None
    assert stats2["completed"] is False


async def test_skeleton_skips_when_marker_completed(db):
    """Covers the `if marker and marker.get('completed')` True branch."""
    await db.async_set_model_state(
        "data_migration_v1_12_4", {"completed": True, "shape_a_relabelled": 5}
    )
    stats = await db.async_migrate_to_v18()
    assert stats == {"skipped": 1}


async def test_skeleton_runs_when_marker_incomplete(db):
    """Covers marker-exists-but-completed-False branch (falls through)."""
    await db.async_set_model_state(
        "data_migration_v1_12_4", {"completed": False}
    )
    stats = await db.async_migrate_to_v18()
    assert stats.get("skipped") is None
    assert stats["completed"] is False
