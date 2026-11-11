"""#329b: CycleStore.last_cycle must reflect forward-merge extension."""
from __future__ import annotations

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB
from custom_components.daikin_cycle_ml.storage.store import CycleStore



def _rec(*, start, end, mode="heating", dur=None, trans=0):
    """Minimal cycle record. duration_s defaults to end-start."""
    return {
        "start_ts": float(start),
        "end_ts": float(end),
        "duration_s": int(dur if dur is not None else end - start),
        "mode": mode,
        "is_transient": trans,
        "dT_max": 5.0, "dT_avg": 3.0,
        "rps_max": 40, "rps_avg": 25,
        "outdoor_temp": 8.0,
        "buh_used": 0, "defrost_used": 0,
        "quality_score": 70, "thermal_kw_avg": 4.0,
    }


async def _read_cycle_by_id(db, cycle_id):
    """Fetch cycle row via raw SQL (no async_get_cycle_by_id exists)."""
    conn = db._require()
    cur = await conn.execute(
        "SELECT id, start_ts, end_ts, duration_s, is_reconstructed "
        "FROM cycles WHERE id = ?", (cycle_id,))
    try:
        row = await cur.fetchone()
    finally:
        await cur.close()
    return row



@pytest.mark.asyncio
async def test_forward_merge_refreshes_store(tmp_path):
    """#329b: 2-cycle merge extends DB keeper; store must reflect it."""
    db = CycleDB(str(tmp_path / "t.db"))
    await db.async_initialize()
    try:
        store = CycleStore()
        a = _rec(start=1000, end=4600)
        id_a = await db.async_insert_cycle(a)
        store.add_cycle(a)
        b = _rec(start=4630, end=5230)  # gap=30 < 120
        id_b = await db.async_insert_cycle(b)
        store.add_cycle(b)

        absorbed = await db.async_merge_cycle_forward(id_b)
        assert absorbed == 1

        store.rollback_last_cycles(absorbed)
        synced = await store.sync_last_cycle_from_db(db)
        assert synced is True
        assert store.count() == 1

        row = await _read_cycle_by_id(db, id_a)
        assert row["duration_s"] == 4230
        assert row["end_ts"] == 5230
        assert row["is_reconstructed"] == 1

        lc = store.last_cycle()
        assert lc["duration_s"] == 4230, f"store stale: {lc['duration_s']} vs 4230"
        assert lc["end_ts"] == 5230
    finally:
        await db.async_close()


@pytest.mark.asyncio
async def test_no_merge_leaves_store_alone(tmp_path):
    """Regression: gap >= threshold -> no merge, store keeps both."""
    db = CycleDB(str(tmp_path / "t.db"))
    await db.async_initialize()
    try:
        store = CycleStore()
        a = _rec(start=1000, end=4600)
        await db.async_insert_cycle(a)
        store.add_cycle(a)
        b = _rec(start=4720, end=5320)  # gap=120 >= threshold
        id_b = await db.async_insert_cycle(b)
        store.add_cycle(b)

        absorbed = await db.async_merge_cycle_forward(id_b)
        assert absorbed == 0

        assert store.count() == 2
        assert store.last_cycle()["duration_s"] == 600
        assert store.last_cycle()["end_ts"] == 5320
    finally:
        await db.async_close()


@pytest.mark.asyncio
async def test_three_cycle_sandwich_merge(tmp_path):
    """#329b edge: 3-cycle sandwich (transient between non-transients) -> absorbed=2."""
    db = CycleDB(str(tmp_path / "t.db"))
    await db.async_initialize()
    try:
        store = CycleStore()
        a = _rec(start=1000, end=4600, dur=3600)
        id_a = await db.async_insert_cycle(a)
        store.add_cycle(a)
        t = _rec(start=4630, end=4700, dur=70, trans=1)  # gap=30 < 120
        await db.async_insert_cycle(t)
        store.add_cycle(t)
        b = _rec(start=4730, end=5330, dur=600)  # gap(prev,B)=30 < 120
        id_b = await db.async_insert_cycle(b)
        store.add_cycle(b)

        absorbed = await db.async_merge_cycle_forward(id_b)
        assert absorbed == 2

        store.rollback_last_cycles(absorbed)
        synced = await store.sync_last_cycle_from_db(db)
        assert synced is True
        assert store.count() == 1

        row = await _read_cycle_by_id(db, id_a)
        assert row["duration_s"] == 4330
        assert row["end_ts"] == 5330

        lc = store.last_cycle()
        assert lc["duration_s"] == 4330, f"store stale: {lc['duration_s']} vs 4330"
    finally:
        await db.async_close()

@pytest.mark.asyncio
async def test_sync_empty_store_returns_false():
    """#329b guard: sync on empty store is a no-op."""
    from unittest.mock import AsyncMock
    store = CycleStore()
    db = AsyncMock()
    result = await store.sync_last_cycle_from_db(db)
    assert result is False
    db.async_get_cycle_by_start_ts.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_missing_start_ts_returns_false():
    """#329b guard: sync without start_ts in last cycle is a no-op."""
    from unittest.mock import AsyncMock
    store = CycleStore()
    store.add_cycle({"mode": "heating"})
    db = AsyncMock()
    result = await store.sync_last_cycle_from_db(db)
    assert result is False
    db.async_get_cycle_by_start_ts.assert_not_awaited()
