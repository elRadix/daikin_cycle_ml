"""v1.19.8 #262: verify daily_summary heal on real prod snapshot.

Skipped in CI when fixture absent (tests/fixtures/*.db is gitignored).
Run locally: cp prod DB to tests/fixtures/_prod1_20261105.db.
"""
from __future__ import annotations

import asyncio
import pathlib

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB

FIXTURE = pathlib.Path("tests/fixtures/_prod1_20261105.db")

pytestmark = pytest.mark.skipif(
    not FIXTURE.exists(),
    reason="prod snapshot missing (tests/fixtures/_prod1_20261105.db)",
)


@pytest.mark.asyncio
async def test_snapshot_heals_after_backfill(tmp_path):
    """Nov 4+5 daily_summary healed by async_backfill_daily_summary_recent.

    Snapshot pre-fix (real prod 2026-11-05 11:00 Brussels):
      Nov 4 heating 16.10h (upd 17:54, pre-cycle-280-extension)
      Nov 5 heating  0.98h (upd 23:59, cycle 280 closed 07:03 next day)

    After backfill, Nov 5 must include cycle 280's pro-rata runtime
    for Nov 5 (07.06h) + any open cycle. Expected total > 6h.
    """
    import shutil
    work = tmp_path / "snap.db"
    shutil.copy(FIXTURE, work)

    db = CycleDB(str(work))
    await db.async_open()
    try:
        rows_before = await db.async_daily_summary(days=7)
        by = {(r["day"], r["mode"]): r for r in rows_before}
        n5_before = by.get(("2026-11-05", "heating"), {}).get(
            "total_duration_s", 0
        )

        n_rebuilt = await db.async_backfill_daily_summary_recent(days=7)
        assert n_rebuilt == 7, f"rebuilt={n_rebuilt}, expected 7"

        rows_after = await db.async_daily_summary(days=7)
        by = {(r["day"], r["mode"]): r for r in rows_after}
        n5_after = by.get(("2026-11-05", "heating"), {}).get(
            "total_duration_s", 0
        )

        assert n5_after > n5_before, (
            f"Nov 5 did NOT heal: {n5_before}s -> {n5_after}s. "
            f"Backfill should have rolled up cycle 280's Nov 5 portion."
        )
        assert n5_after >= 6 * 3600, (
            f"Nov 5 after backfill = {n5_after / 3600:.2f}h, expected >= 6h "
            f"(cycle 280 pro-rata for Nov 5)"
        )
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)
