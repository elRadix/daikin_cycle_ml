"""v1.19.9 #123 R639/R644: v28 migration replay test."""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB


FIXTURE = pathlib.Path("tests/fixtures/_prod1_20261105.db")

pytestmark = pytest.mark.skipif(
    not FIXTURE.exists(), reason="prod-1 snapshot missing",
)


async def _load_snapshot(tmp_path):
    work = tmp_path / "v28_snap.db"
    shutil.copy(FIXTURE, work)
    db = CycleDB(str(work))
    await db.async_open()
    return db


@pytest.mark.asyncio
async def test_gap5_v28_reclassifies_snapshot(tmp_path):
    """R639/R644: v28 -> unflagged>=40, flagged>=15, rejected>=1."""
    db = await _load_snapshot(tmp_path)
    try:
        async with db._conn.execute(
            "SELECT COUNT(*) FROM cop_samples WHERE is_transition_artifact = 1"
        ) as cur:
            flagged_before = (await cur.fetchone())[0]
        assert flagged_before > 0

        stats = await db.async_migrate_to_v28()
        assert stats.get("completed") is True
        scanned = stats["scanned"]
        unflagged = stats["unflagged"]
        flagged = stats["flagged"]
        rejected = stats["rejected"]

        print(f"v28 stats: scanned={scanned} unflagged={unflagged} "
              f"flagged={flagged} rejected={rejected}")

        assert scanned >= 5000, f"scanned={scanned}"
        assert unflagged >= 40, f"unflagged too few: {unflagged}"
        assert flagged >= 15, f"flagged too few: {flagged}"
        assert rejected >= 1, f"rejected too few: {rejected}"
        assert unflagged < scanned, "unflagged == scanned is suspicious"

        async with db._conn.execute(
            "SELECT COUNT(*) FROM cop_samples WHERE is_transition_artifact = 1"
        ) as cur:
            flagged_after = (await cur.fetchone())[0]

        expected = flagged_before - unflagged + flagged + rejected
        assert flagged_after == expected, (
            f"count mismatch: {flagged_before}-{unflagged}+{flagged}+"
            f"{rejected}={expected}, got {flagged_after}"
        )
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_gap5_v28_idempotent(tmp_path):
    """R639: second run -> {"skipped": 1}."""
    db = await _load_snapshot(tmp_path)
    try:
        first = await db.async_migrate_to_v28()
        assert first.get("completed") is True
        second = await db.async_migrate_to_v28()
        assert second.get("skipped") == 1
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_gap5_v28_marker_persisted(tmp_path):
    """R639: marker contains exact stats."""
    db = await _load_snapshot(tmp_path)
    try:
        stats = await db.async_migrate_to_v28()
        marker = await db.async_get_model_state(
            "data_migration_v28_completed"
        )
        assert marker is not None
        assert marker.get("completed") is True
        for k in ("scanned", "unflagged", "flagged", "rejected"):
            assert marker[k] == stats[k], f"{k}: {marker[k]} vs {stats[k]}"
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_gap5_v28_does_not_touch_not_applicable(tmp_path):
    """R639: not_applicable samples stay unchanged."""
    db = await _load_snapshot(tmp_path)
    try:
        async with db._conn.execute(
            "SELECT id, is_transition_artifact FROM cop_samples "
            "WHERE mode IN ('heating', 'dhw') "
            "  AND lwt IS NOT NULL AND outdoor IS NOT NULL "
            "  AND lwt <= outdoor"
        ) as cur:
            not_applicable = await cur.fetchall()

        if len(not_applicable) == 0:
            pytest.skip("no not_applicable samples in snapshot")

        before = {r[0]: r[1] for r in not_applicable}
        await db.async_migrate_to_v28()

        ids = ",".join(str(r[0]) for r in not_applicable)
        async with db._conn.execute(
            f"SELECT id, is_transition_artifact FROM cop_samples "
            f"WHERE id IN ({ids})"
        ) as cur:
            after = {r[0]: r[1] for r in await cur.fetchall()}

        assert before == after
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_gap5_v28_rerun_is_noop(tmp_path):
    """R639: after 1st run, 2nd run (marker cleared) -> all zeros."""
    db = await _load_snapshot(tmp_path)
    try:
        await db.async_migrate_to_v28()
        # Clear marker to force re-run
        await db.async_set_model_state(
            "data_migration_v28_completed", {"cleared": True}
        )
        stats = await db.async_migrate_to_v28()
        assert stats["unflagged"] == 0, f"unflagged={stats['unflagged']}"
        assert stats["flagged"] == 0
        assert stats["rejected"] == 0
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)

# ============================================================
# R643: synthetic not_applicable coverage (line 2081-2082 in db.py)
# ============================================================

@pytest.mark.asyncio
async def test_v28_skips_not_applicable_synthetic(tmp_path):
    """R643: v28 skips lwt<=outdoor samples without UPDATE (2081-2082).

    Prod-1 has 0 such samples so this test synthesizes one to cover
    the defensive guard in v28's main loop.
    """
    from tests.test_rollup_concurrency import _mk_db
    db = await _mk_db(tmp_path)
    try:
        # lwt == outdoor -> classifier returns not_applicable
        await db.async_insert_cop_sample({
            "ts": 1793608800.0, "cop": 5.0,
            "lwt": 30.0, "outdoor": 30.0,
            "mode": "heating", "source": "interval",
            "power_stable": True,
        })
        # And one valid sample to ensure the migration runs the loop body
        await db.async_insert_cop_sample({
            "ts": 1793608801.0, "cop": 5.0,
            "lwt": 30.0, "outdoor": 10.0,
            "mode": "heating", "source": "interval",
            "power_stable": True,
        })

        stats = await db.async_migrate_to_v28()
        assert stats["scanned"] == 2, f"scanned={stats['scanned']}"
        # not_applicable + already-accept -> 0 changes
        assert stats["unflagged"] == 0
        assert stats["flagged"] == 0
        assert stats["rejected"] == 0

        # Both samples unchanged (still flag=0)
        async with db._conn.execute(
            "SELECT is_transition_artifact FROM cop_samples ORDER BY ts"
        ) as cur:
            flags = [r[0] for r in await cur.fetchall()]
        assert flags == [0, 0], f"flags={flags}"
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)

