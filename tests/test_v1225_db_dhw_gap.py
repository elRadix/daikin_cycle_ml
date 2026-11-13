"""Coverage for async_get_median_dhw_gap in db.py (Issue #340)."""
import pytest
import aiosqlite
from unittest.mock import MagicMock
from custom_components.daikin_cycle_ml.storage.db import CycleDB

@pytest.fixture
async def db():
    db = CycleDB.__new__(CycleDB)
    db._conn = await aiosqlite.connect(":memory:")
    await db._conn.execute("CREATE TABLE cycles (id INTEGER PRIMARY KEY, mode TEXT, start_ts REAL, end_ts REAL)")
    db._require = lambda: db._conn
    yield db
    await db._conn.close()

@pytest.mark.asyncio
async def test_median_dhw_gap_odd(db):
    # 1 paar (oneven) -> gap = 200 -> 200 * 2.5 = 500
    await db._conn.execute("INSERT INTO cycles (id, mode, start_ts, end_ts) VALUES (1, 'dhw', 100, 200)")
    await db._conn.execute("INSERT INTO cycles (id, mode, start_ts, end_ts) VALUES (2, 'heating', 400, 500)")
    await db._conn.commit()
    res = await db.async_get_median_dhw_gap()
    assert res == 500.0

@pytest.mark.asyncio
async def test_median_dhw_gap_even(db):
    # 2 paar (even) -> gaps 200 en 400 -> median = 300 -> 300 * 2.5 = 750
    await db._conn.execute("INSERT INTO cycles (id, mode, start_ts, end_ts) VALUES (1, 'dhw', 100, 200)")
    await db._conn.execute("INSERT INTO cycles (id, mode, start_ts, end_ts) VALUES (2, 'heating', 400, 500)")
    await db._conn.execute("INSERT INTO cycles (id, mode, start_ts, end_ts) VALUES (3, 'dhw', 600, 700)")
    await db._conn.execute("INSERT INTO cycles (id, mode, start_ts, end_ts) VALUES (4, 'heating', 1100, 1200)")
    await db._conn.commit()
    res = await db.async_get_median_dhw_gap()
    assert res == 750.0

@pytest.mark.asyncio
async def test_median_dhw_gap_empty(db):
    # Geen paren -> fallback 300.0
    res = await db.async_get_median_dhw_gap()
    assert res == 300.0

@pytest.mark.asyncio
async def test_median_dhw_gap_all_none(db):
    # Wel paren, maar gap is NULL -> fallback 300.0
    await db._conn.execute("INSERT INTO cycles (id, mode, start_ts, end_ts) VALUES (1, 'dhw', 100, NULL)")
    await db._conn.execute("INSERT INTO cycles (id, mode, start_ts, end_ts) VALUES (2, 'heating', 400, 500)")
    await db._conn.commit()
    res = await db.async_get_median_dhw_gap()
    assert res == 300.0

@pytest.mark.asyncio
async def test_median_dhw_gap_exception(db):
    # Exception in DB -> fallback 300.0
    db._require = MagicMock(side_effect=Exception("DB error"))
    res = await db.async_get_median_dhw_gap()
    assert res == 300.0
