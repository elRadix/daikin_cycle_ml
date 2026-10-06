"""R298: cop_samples.mode DEFAULT 'unknown' (schema + INSERT + migratie)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from custom_components.daikin_cycle_ml.storage.db import CycleDB


LEGACY_COP = """
CREATE TABLE cop_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    cop REAL NOT NULL,
    lwt REAL,
    outdoor REAL,
    flow_lmin REAL,
    power_stable INTEGER DEFAULT 0,
    mode TEXT DEFAULT NULL,
    source TEXT DEFAULT 'interval'
)
"""


async def _open(path: Path) -> CycleDB:
    db = CycleDB(str(path))
    await db.async_open()
    await db.async_initialize()
    return db


async def test_schema_default_unknown(tmp_path: Path) -> None:
    p = tmp_path / "fresh.db"
    db = await _open(p)
    await db.async_close()
    conn = sqlite3.connect(str(p))
    conn.execute("INSERT INTO cop_samples (ts, cop) VALUES (1.0, 3.0)")
    conn.commit()
    row = conn.execute("SELECT mode FROM cop_samples").fetchone()
    assert row[0] == 'unknown'
    conn.close()


async def test_insert_fallback_explicit_none(tmp_path: Path) -> None:
    p = tmp_path / "fallback.db"
    db = await _open(p)
    try:
        await db.async_insert_cop_sample({
            'ts': 1000.0, 'cop': 3.0, 'mode': None,
        })
    finally:
        await db.async_close()
    conn = sqlite3.connect(str(p))
    row = conn.execute("SELECT mode FROM cop_samples").fetchone()
    assert row[0] == 'unknown'
    conn.close()


async def test_migrate_null_to_unknown_idempotent(tmp_path: Path) -> None:
    p = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(p))
    conn.executescript(LEGACY_COP + ";")
    conn.execute("INSERT INTO cop_samples (ts, cop, mode) VALUES (1.0, 3.0, NULL)")
    conn.execute("INSERT INTO cop_samples (ts, cop, mode) VALUES (2.0, 3.0, 'heating')")
    conn.commit()
    conn.close()

    db = await _open(p)
    try:
        first = await db.async_migrate_cop_samples_mode_default_v15()
        assert first == 1
        second = await db.async_migrate_cop_samples_mode_default_v15()
        assert second == 0
    finally:
        await db.async_close()

    conn = sqlite3.connect(str(p))
    rows = list(conn.execute("SELECT ts, mode FROM cop_samples ORDER BY ts"))
    assert rows == [(1.0, 'unknown'), (2.0, 'heating')]
    conn.close()
