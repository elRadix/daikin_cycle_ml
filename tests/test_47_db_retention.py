"""Batch 47 -- db retention + count/avg helpers."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml.storage.db import CycleDB


def _db_no_conn():
    db = CycleDB.__new__(CycleDB)
    db._conn = None
    return db


def test_count_no_conn():
    db = _db_no_conn()
    assert asyncio.run(db.async_count_cycles_since(0)) == 0


def test_avg_no_conn():
    db = _db_no_conn()
    assert asyncio.run(db.async_avg_duration_since(0)) is None


def test_count_conn_raises():
    db = _db_no_conn()
    conn = MagicMock()
    conn.execute = AsyncMock(side_effect=RuntimeError('fail'))
    db._conn = conn
    assert asyncio.run(db.async_count_cycles_since(0)) == 0


def test_avg_conn_raises():
    db = _db_no_conn()
    conn = MagicMock()
    conn.execute = AsyncMock(side_effect=RuntimeError('fail'))
    db._conn = conn
    assert asyncio.run(db.async_avg_duration_since(0)) is None


def test_count_row_none():
    db = _db_no_conn()
    cur = MagicMock()
    cur.fetchone = AsyncMock(return_value=None)
    cur.close = AsyncMock()
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    db._conn = conn
    assert asyncio.run(db.async_count_cycles_since(0)) == 0


def test_count_row_valid():
    db = _db_no_conn()
    cur = MagicMock()
    cur.fetchone = AsyncMock(return_value=(42,))
    cur.close = AsyncMock()
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    db._conn = conn
    assert asyncio.run(db.async_count_cycles_since(0)) == 42


def test_avg_row_none():
    db = _db_no_conn()
    cur = MagicMock()
    cur.fetchone = AsyncMock(return_value=(None,))
    cur.close = AsyncMock()
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    db._conn = conn
    assert asyncio.run(db.async_avg_duration_since(0)) is None


def test_avg_row_valid():
    db = _db_no_conn()
    cur = MagicMock()
    cur.fetchone = AsyncMock(return_value=(120.5,))
    cur.close = AsyncMock()
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    db._conn = conn
    v = asyncio.run(db.async_avg_duration_since(0))
    assert v == 120.5


def test_avg_fetch_returns_empty_tuple():
    db = _db_no_conn()
    cur = MagicMock()
    cur.fetchone = AsyncMock(return_value=())
    cur.close = AsyncMock()
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    db._conn = conn
    assert asyncio.run(db.async_avg_duration_since(0)) is None
