"""v20 migration tests (#188)."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock
from custom_components.daikin_cycle_ml.storage.db import CycleDB

def _mk_db():
    db = CycleDB.__new__(CycleDB)
    cur = MagicMock()
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    conn.commit = AsyncMock()
    db._require = MagicMock(return_value=conn)
    db.async_set_model_state = AsyncMock()
    return db, conn, cur

@pytest.mark.asyncio
async def test_v20_adds_columns():
    db, conn, cur = _mk_db()
    cur.fetchall = AsyncMock(return_value=[
        (0, "id", "INTEGER", 0, None, 1),
        (1, "ts", "REAL", 1, None, 0),
    ])
    db.async_get_model_state = AsyncMock(return_value=None)
    result = await db.async_migrate_to_v20()
    assert "r1t" in result["columns_added"]
    assert "r4t" in result["columns_added"]
    assert result["completed"] is True

@pytest.mark.asyncio
async def test_v20_columns_exist():
    db, conn, cur = _mk_db()
    cur.fetchall = AsyncMock(return_value=[
        (0, "r1t", "REAL", 0, None, 0),
        (1, "r4t", "REAL", 0, None, 0),
    ])
    db.async_get_model_state = AsyncMock(return_value=None)
    result = await db.async_migrate_to_v20()
    assert result["columns_added"] == []
    assert result["completed"] is True

@pytest.mark.asyncio
async def test_v20_idempotent():
    db, conn, cur = _mk_db()
    db.async_get_model_state = AsyncMock(return_value={"completed": True})
    result = await db.async_migrate_to_v20()
    assert result == {"skipped": 1}
