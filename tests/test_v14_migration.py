"""Test v14 schema migration via CycleDB public methods."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from custom_components.daikin_cycle_ml.storage.db import CycleDB


LEGACY_CYCLES = """
CREATE TABLE cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_ts REAL NOT NULL,
    end_ts REAL,
    duration_s INTEGER,
    mode TEXT,
    dT_max REAL,
    dT_avg REAL,
    rps_max INTEGER,
    rps_avg REAL,
    outdoor_temp REAL,
    buh_used INTEGER DEFAULT 0,
    defrost_used INTEGER DEFAULT 0,
    quality_score INTEGER,
    label TEXT,
    cluster_id INTEGER,
    UNIQUE(start_ts)
)
"""

LEGACY_COP = """
CREATE TABLE cop_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    cop REAL NOT NULL,
    lwt REAL,
    outdoor REAL,
    flow_lmin REAL,
    power_stable INTEGER DEFAULT 0,
    mode TEXT DEFAULT NULL
)
"""


def _write_legacy(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(LEGACY_CYCLES + ";" + LEGACY_COP + ";")
    conn.commit()
    conn.close()


async def _open(path: Path) -> CycleDB:
    db = CycleDB(str(path))
    await db.async_open()
    await db.async_initialize()
    return db


async def test_v14_cycles_columns_added_and_idempotent(tmp_path: Path) -> None:
    p = tmp_path / "legacy.db"
    _write_legacy(p)
    db = await _open(p)
    try:
        first = await db.async_migrate_cycles_to_v14()
        assert first == 4
        second = await db.async_migrate_cycles_to_v14()
        assert second == 0
    finally:
        await db.async_close()
    conn = sqlite3.connect(str(p))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(cycles)")}
    assert {"cop_avg", "cop_sample_count", "cop_sample_stdev", "cop_confidence"} <= cols
    conn.close()


async def test_v14_cop_samples_source_added_and_idempotent(tmp_path: Path) -> None:
    p = tmp_path / "legacy.db"
    _write_legacy(p)
    db = await _open(p)
    try:
        assert await db.async_migrate_cop_samples_source_v14() is True
        assert await db.async_migrate_cop_samples_source_v14() is True
    finally:
        await db.async_close()
    conn = sqlite3.connect(str(p))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(cop_samples)")}
    assert "source" in cols
    conn.execute("INSERT INTO cop_samples (ts, cop) VALUES (1.0, 3.5)")
    conn.commit()
    src = conn.execute("SELECT source FROM cop_samples").fetchone()[0]
    assert src == "interval"
    conn.close()


async def test_v14_cop_hourly_created(tmp_path: Path) -> None:
    p = tmp_path / "legacy.db"
    _write_legacy(p)
    db = await _open(p)
    try:
        assert await db.async_create_cop_hourly_v14() is True
        assert await db.async_create_cop_hourly_v14() is True
    finally:
        await db.async_close()
    conn = sqlite3.connect(str(p))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(cop_hourly)")}
    assert {"cop_mean", "cop_p10", "cop_p90", "n_samples", "ts_hour", "mode"} <= cols
    idx = {r[1] for r in conn.execute("PRAGMA index_list(cop_hourly)")}
    assert "idx_cop_hourly_ts" in idx
    conn.close()


async def test_v14_orchestrator_on_legacy(tmp_path: Path) -> None:
    p = tmp_path / "legacy.db"
    _write_legacy(p)
    db = await _open(p)
    try:
        added, src_ok, hourly_ok = await db.async_migrate_to_v14()
        assert added == 4
        assert src_ok is True
        assert hourly_ok is True
    finally:
        await db.async_close()


async def test_v14_orchestrator_on_fresh_db_is_noop(tmp_path: Path) -> None:
    p = tmp_path / "fresh.db"
    db = await _open(p)
    try:
        added, src_ok, hourly_ok = await db.async_migrate_to_v14()
        assert added == 0
        assert src_ok is True
        assert hourly_ok is True
    finally:
        await db.async_close()


async def test_v14_preserves_existing_rows(tmp_path: Path) -> None:
    p = tmp_path / "legacy.db"
    _write_legacy(p)
    conn = sqlite3.connect(str(p))
    conn.execute("INSERT INTO cycles (start_ts, duration_s, quality_score) VALUES (1.0, 600, 85)")
    conn.commit()
    conn.close()
    db = await _open(p)
    try:
        await db.async_migrate_to_v14()
    finally:
        await db.async_close()
    conn = sqlite3.connect(str(p))
    row = conn.execute(
        "SELECT start_ts, duration_s, quality_score, cop_avg, cop_sample_count FROM cycles"
    ).fetchone()
    assert row[0] == 1.0
    assert row[1] == 600
    assert row[2] == 85
    assert row[3] is None
    assert row[4] is None
    conn.close()
