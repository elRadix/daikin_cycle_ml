"""Tests for CycleDB (Batch 6a)."""
from __future__ import annotations

import time

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB


@pytest.fixture
async def db(tmp_path):
    database = CycleDB(tmp_path / "test.db")
    await database.async_open()
    await database.async_initialize()
    try:
        yield database
    finally:
        await database.async_close()
        # R51: aiosqlite worker-thread may outlive close() briefly.
        # Yield to event loop so the thread joins before phcc checks.
        import asyncio as _asyncio
        await _asyncio.sleep(0.05)


def _rec(start_ts: float = 1000.0, **extra):
    base = {
        "start_ts": start_ts,
        "end_ts": start_ts + 600,
        "duration_s": 600,
        "mode": "Heating",
        "dT_max": 6.0,
        "dT_avg": 4.5,
        "rps_max": 60,
        "rps_avg": 45.0,
        "outdoor_temp": 8.0,
        "buh_used": 0,
        "defrost_used": 0,
    }
    base.update(extra)
    return base


async def test_open_sets_flag(tmp_path):
    d = CycleDB(tmp_path / "a.db")
    assert d.is_open is False
    await d.async_open()
    assert d.is_open is True
    await d.async_close()
    assert d.is_open is False


async def test_close_idempotent(tmp_path):
    d = CycleDB(tmp_path / "b.db")
    await d.async_open()
    await d.async_close()
    await d.async_close()


async def test_initialize_idempotent(tmp_path):
    d = CycleDB(tmp_path / "c.db")
    await d.async_open()
    await d.async_initialize()
    await d.async_initialize()
    assert await d.async_count("cycles") == 0
    await d.async_close()


async def test_insert_cycle_returns_id(db):
    cid = await db.async_insert_cycle(_rec(1000.0))
    assert isinstance(cid, int) and cid >= 1


async def test_insert_duplicate_start_ts_returns_none(db):
    await db.async_insert_cycle(_rec(2000.0))
    assert await db.async_insert_cycle(_rec(2000.0)) is None


async def test_count_reflects_inserts(db):
    await db.async_insert_cycle(_rec(3000.0))
    await db.async_insert_cycle(_rec(4000.0))
    assert await db.async_count("cycles") == 2


async def test_fetch_cycles_empty(db):
    assert await db.async_fetch_cycles() == []


async def test_fetch_cycles_returns_dicts(db):
    await db.async_insert_cycle(_rec(time.time() - 100))
    rows = await db.async_fetch_cycles(days=365)
    assert len(rows) == 1
    assert rows[0]["mode"] == "Heating"
    assert rows[0]["duration_s"] == 600


async def test_fetch_cycles_respects_days(db):
    now = time.time()
    await db.async_insert_cycle(_rec(now - 100, mode="Heating"))
    await db.async_insert_cycle(_rec(now - 40 * 86400, mode="Cooling"))
    rows = await db.async_fetch_cycles(days=7)
    assert len(rows) == 1
    assert rows[0]["mode"] == "Heating"


async def test_insert_features(db):
    cid = await db.async_insert_cycle(_rec(6000.0))
    assert cid is not None
    await db.async_insert_features(cid, [1.0, 2.0, 3.0])
    assert await db.async_count("features") == 1


async def test_features_upsert(db):
    cid = await db.async_insert_cycle(_rec(7000.0))
    await db.async_insert_features(cid, [1.0])
    await db.async_insert_features(cid, [2.0, 3.0])
    assert await db.async_count("features") == 1


async def test_model_state_roundtrip(db):
    await db.async_set_model_state("baseline", {"mean": 42, "n": 7})
    val = await db.async_get_model_state("baseline")
    assert val == {"mean": 42, "n": 7}


async def test_model_state_missing_returns_default(db):
    assert await db.async_get_model_state("nope", default="X") == "X"
    assert await db.async_get_model_state("nope") is None


async def test_insert_alert(db):
    aid = await db.async_insert_alert("pendulum", "warning", "test")
    assert isinstance(aid, int)
    assert await db.async_count("alerts") == 1


async def test_alert_duplicate_returns_none(db):
    ts = 12345.0
    assert await db.async_insert_alert("p", "w", "m", ts=ts) is not None
    assert await db.async_insert_alert("p", "w", "m", ts=ts) is None


async def test_label_cycle(db):
    cid = await db.async_insert_cycle(_rec(time.time() - 200))
    assert await db.async_label_cycle(cid, "good") is True
    rows = await db.async_fetch_cycles(days=365)
    assert rows[0]["label"] == "good"


async def test_label_unknown_cycle_returns_false(db):
    assert await db.async_label_cycle(99999, "x") is False


async def test_count_unknown_table_raises(db):
    with pytest.raises(ValueError):
        await db.async_count("bogus")


async def test_query_without_open_raises(tmp_path):
    d = CycleDB(tmp_path / "z.db")
    with pytest.raises(RuntimeError):
        await d.async_count()
