"""v1.15.1 — v25 migration merges capped-cycle artifacts (4h hard-cap bug)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from custom_components.daikin_cycle_ml.storage.db import CycleDB


def _row(start: float, end: float, dur: int, mode: str = "heating",
         dT: float = 5.0, rps: int = 30, buh: int = 0, dfr: int = 0) -> dict:
    return {
        "start_ts": start, "end_ts": end, "duration_s": dur, "mode": mode,
        "dT_max": dT, "dT_avg": dT, "rps_max": rps, "rps_avg": rps * 0.8,
        "outdoor_temp": 7.0, "buh_used": buh, "defrost_used": dfr,
    }


@pytest.mark.asyncio
async def test_v25_merges_capped_parent_and_child(tmp_path):
    db = CycleDB(str(tmp_path / "t.db"))
    await db.async_initialize()
    try:
        # Parent: 4h capped at 14400, end_ts extends 30s past 14400 (cap fired at +14405s)
        pid = await db.async_insert_cycle(
            _row(1000.0, 15405.0, 14400, dT=5.0, dfr=1)
        )
        # Child: starts 30s later, 2h continuation, no defrost
        cid = await db.async_insert_cycle(
            _row(15435.0, 22635.0, 7200, dT=6.0, dfr=0)
        )
        assert pid and cid

        stats = await db.async_migrate_to_v25()
        assert stats["merged"] == 1
        assert stats["standalone"] == 0

        conn = db._require()
        cur = await conn.execute(
            "SELECT duration_s, end_ts, dT_max, defrost_used FROM cycles "
            "WHERE id = ?", (pid,)
        )
        row = await cur.fetchone()
        assert row is not None
        assert row["duration_s"] == 21635  # 22635 - 1000
        assert row["end_ts"] == 22635.0
        assert row["dT_max"] == 6.0
        assert row["defrost_used"] == 1  # MAX(1,0) preserved

        cur = await conn.execute("SELECT 1 FROM cycles WHERE id = ?", (cid,))
        assert await cur.fetchone() is None  # child deleted
    finally:
        await db.async_close()


@pytest.mark.asyncio
async def test_v25_standalone_capped_untouched(tmp_path):
    db = CycleDB(str(tmp_path / "t.db"))
    await db.async_initialize()
    try:
        # Standalone capped cycle — no child within 60s
        pid = await db.async_insert_cycle(_row(1000.0, 15405.0, 14400))
        stats = await db.async_migrate_to_v25()
        assert stats["merged"] == 0
        assert stats["standalone"] == 1

        conn = db._require()
        cur = await conn.execute(
            "SELECT duration_s FROM cycles WHERE id = ?", (pid,)
        )
        row = await cur.fetchone()
        assert row is not None
        assert row["duration_s"] == 14400  # unchanged
    finally:
        await db.async_close()


@pytest.mark.asyncio
async def test_v25_refuses_to_merge_different_mode(tmp_path):
    db = CycleDB(str(tmp_path / "t.db"))
    await db.async_initialize()
    try:
        pid = await db.async_insert_cycle(
            _row(1000.0, 15405.0, 14400, mode="heating")
        )
        # Child is DHW — must NOT merge into heating parent
        cid = await db.async_insert_cycle(
            _row(15435.0, 22635.0, 7200, mode="dhw")
        )
        stats = await db.async_migrate_to_v25()
        assert stats["merged"] == 0
        assert stats["standalone"] == 1

        conn = db._require()
        for i in (pid, cid):
            cur = await conn.execute(
                "SELECT 1 FROM cycles WHERE id = ?", (i,)
            )
            assert await cur.fetchone() is not None  # both survived
    finally:
        await db.async_close()


@pytest.mark.asyncio
async def test_v25_idempotent_via_marker(tmp_path):
    db = CycleDB(str(tmp_path / "t.db"))
    await db.async_initialize()
    try:
        await db.async_insert_cycle(_row(1000.0, 15405.0, 14400))
        await db.async_insert_cycle(_row(15435.0, 22635.0, 7200))

        s1 = await db.async_migrate_to_v25()
        assert s1["merged"] == 1
        s2 = await db.async_migrate_to_v25()
        assert s2.get("skipped") == 1
    finally:
        await db.async_close()


@pytest.mark.asyncio
async def test_v25_rollup_failure_logged_not_fatal(tmp_path, caplog):
    """v25 must not abort if async_rollup_day raises — rollup retried next startup."""
    import logging
    db = CycleDB(str(tmp_path / "t.db"))
    await db.async_initialize()
    try:
        await db.async_insert_cycle(_row(1000.0, 15405.0, 14400))
        await db.async_insert_cycle(_row(15435.0, 22635.0, 7200))

        async def _boom(day: str) -> int:
            raise RuntimeError("rollup-simulated-failure")

        with caplog.at_level(logging.WARNING), \
             pytest.MonkeyPatch.context() as mp:
            mp.setattr(db, "async_rollup_day", _boom)
            stats = await db.async_migrate_to_v25()

        assert stats["merged"] == 1
        assert stats["days_rerolled"] == []
        assert "v25 rollup failed" in caplog.text
    finally:
        await db.async_close()
