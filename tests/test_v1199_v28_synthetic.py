"""v1.19.9 R655: v28 synthetic tests (no fixture required).

These tests cover the v28 migration loop-body when the prod-1 snapshot
fixture is absent (CI environment, gitignored).

R565: fully self-contained (sys.path + CycleDB import + _mk_db helper)
so this file runs standalone or in full suite without cross-module
dependencies.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest

# R565: sys.path bootstrap (works even when this file runs alone)
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from custom_components.daikin_cycle_ml.storage.db import CycleDB


async def _mk_db_local(tmp_path):
    """Local _mk_db: no cross-module import."""
    db = CycleDB(str(tmp_path / "synth.db"))
    await db.async_open()
    await db.async_initialize()
    return db


# ============================================================
# v28 synthetic coverage (no fixture required)
# ============================================================

@pytest.mark.asyncio
async def test_v28_idempotent_synthetic(tmp_path):
    """R655: idempotency works without fixture (covers db.py line 2055).

    1st run: processes DB -> {completed: True}
    2nd run: marker guard hit -> {skipped: 1}
    """
    db = await _mk_db_local(tmp_path)
    try:
        await db.async_insert_cop_sample({
            "ts": 1793608800.0, "cop": 5.0,
            "lwt": 30.0, "outdoor": 10.0,
            "mode": "heating", "source": "interval",
            "power_stable": True,
        })

        first = await db.async_migrate_to_v28()
        assert first.get("completed") is True
        assert first["scanned"] == 1

        second = await db.async_migrate_to_v28()
        assert second.get("skipped") == 1, f"not idempotent: {second}"
    finally:
        await db.async_close()
        await asyncio.sleep(0.3)


@pytest.mark.asyncio
async def test_v28_update_pad_synthetic(tmp_path):
    """R655: UPDATE-path works without fixture (covers db.py lines 2077-2099).

    Sample flagged at 0.55 but accepted at 0.65 -> unflag UPDATE fires.
    """
    db = await _mk_db_local(tmp_path)
    try:
        await db.async_insert_cop_sample({
            "ts": 1793608800.0, "cop": 8.48,
            "lwt": 31.4, "outdoor": 8.0,
            "mode": "heating", "source": "interval",
            "power_stable": True,
            "is_transition_artifact": 1,
        })

        async with db._conn.execute(
            "SELECT is_transition_artifact FROM cop_samples"
        ) as cur:
            before = (await cur.fetchone())[0]
        assert before == 1

        stats = await db.async_migrate_to_v28()
        assert stats.get("completed") is True
        assert stats["unflagged"] == 1, f"expected 1 unflag, got {stats}"
        assert stats["flagged"] == 0
        assert stats["rejected"] == 0

        async with db._conn.execute(
            "SELECT is_transition_artifact FROM cop_samples"
        ) as cur:
            after = (await cur.fetchone())[0]
        assert after == 0, f"UPDATE failed, flag={after}"
    finally:
        await db.async_close()
        await asyncio.sleep(0.3)


@pytest.mark.asyncio
async def test_v28_flag_and_reject_synthetic(tmp_path):
    """R655: flag + reject paths work without fixture.

    Covers `if cls == 'reject'` inner branch (line 2086) and flag branch.
    """
    db = await _mk_db_local(tmp_path)
    try:
        # Flag path: cop=10.05 at lwt=38.5/out=14.7 -> flag
        await db.async_insert_cop_sample({
            "ts": 1793608800.0, "cop": 10.05,
            "lwt": 38.5, "outdoor": 14.7,
            "mode": "heating", "source": "interval",
            "power_stable": True,
        })
        # Reject path: cop=100 at lwt=30/out=5 -> reject
        await db.async_insert_cop_sample({
            "ts": 1793608801.0, "cop": 100.0,
            "lwt": 30.0, "outdoor": 5.0,
            "mode": "heating", "source": "interval",
            "power_stable": True,
        })

        stats = await db.async_migrate_to_v28()
        assert stats["flagged"] == 1, f"expected 1 flag, got {stats}"
        assert stats["rejected"] == 1, f"expected 1 reject, got {stats}"
        assert stats["unflagged"] == 0

        async with db._conn.execute(
            "SELECT is_transition_artifact FROM cop_samples ORDER BY ts"
        ) as cur:
            flags = [r[0] for r in await cur.fetchall()]
        assert flags == [1, 1], f"flags={flags}"
    finally:
        await db.async_close()
        await asyncio.sleep(0.3)
