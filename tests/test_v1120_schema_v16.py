"""v1.12.0: schema v16 migration tests (issues #105, #107)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from custom_components.daikin_cycle_ml.storage.db import CycleDB


async def _open(p: Path) -> CycleDB:
    db = CycleDB(str(p))
    await db.async_initialize()
    return db


def _create_v15_cycles(p: Path) -> None:
    """Create a pre-v16 cycles table (no is_transient, no thermal_kw_avg)."""
    conn = sqlite3.connect(str(p))
    conn.executescript("""
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
            cop_avg REAL,
            cop_sample_count INTEGER,
            cop_sample_stdev REAL,
            cop_confidence TEXT,
            UNIQUE(start_ts)
        );
    """)
    conn.commit()
    conn.close()


def _legacy_insert(p: Path, start_ts: float, duration_s: int,
                   dT_max: float | None, rps_max: int | None) -> None:
    conn = sqlite3.connect(str(p))
    conn.execute(
        "INSERT INTO cycles (start_ts, end_ts, duration_s, mode, "
        "dT_max, rps_max) VALUES (?,?,?,?,?,?)",
        (start_ts, start_ts + duration_s, duration_s, "heating",
         dT_max, rps_max),
    )
    conn.commit()
    conn.close()


def _cols(p: Path) -> set[str]:
    conn = sqlite3.connect(str(p))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(cycles)")}
    conn.close()
    return cols


async def test_new_db_has_v16_columns(tmp_path: Path) -> None:
    p = tmp_path / "new.db"
    db = await _open(p)
    try:
        cols = _cols(p)
        assert "is_transient" in cols
        assert "thermal_kw_avg" in cols
    finally:
        await db.async_close()


async def test_migration_adds_columns_to_legacy_db(tmp_path: Path) -> None:
    p = tmp_path / "legacy.db"
    _create_v15_cycles(p)
    assert "is_transient" not in _cols(p)
    assert "thermal_kw_avg" not in _cols(p)
    db = await _open(p)
    try:
        cols = _cols(p)
        assert "is_transient" in cols
        assert "thermal_kw_avg" in cols
    finally:
        await db.async_close()


async def test_backfill_marks_short_duration_transient(tmp_path: Path) -> None:
    p = tmp_path / "short.db"
    _create_v15_cycles(p)
    _legacy_insert(p, start_ts=1000.0, duration_s=60, dT_max=5.0, rps_max=30)
    db = await _open(p)
    try:
        conn = sqlite3.connect(str(p))
        v = conn.execute(
            "SELECT is_transient FROM cycles WHERE start_ts=1000.0"
        ).fetchone()[0]
        conn.close()
        assert v == 1
    finally:
        await db.async_close()


async def test_backfill_marks_near_max_transient(tmp_path: Path) -> None:
    p = tmp_path / "near.db"
    _create_v15_cycles(p)
    _legacy_insert(p, start_ts=2000.0, duration_s=200, dT_max=2.5, rps_max=45)
    db = await _open(p)
    try:
        conn = sqlite3.connect(str(p))
        v = conn.execute(
            "SELECT is_transient FROM cycles WHERE start_ts=2000.0"
        ).fetchone()[0]
        conn.close()
        assert v == 1
    finally:
        await db.async_close()


async def test_backfill_skips_normal_cycle(tmp_path: Path) -> None:
    p = tmp_path / "normal.db"
    _create_v15_cycles(p)
    _legacy_insert(p, start_ts=3000.0, duration_s=600, dT_max=5.0, rps_max=30)
    db = await _open(p)
    try:
        conn = sqlite3.connect(str(p))
        v = conn.execute(
            "SELECT is_transient FROM cycles WHERE start_ts=3000.0"
        ).fetchone()[0]
        conn.close()
        assert v == 0
    finally:
        await db.async_close()


async def test_backfill_idempotent(tmp_path: Path) -> None:
    p = tmp_path / "idem.db"
    _create_v15_cycles(p)
    _legacy_insert(p, start_ts=4000.0, duration_s=60, dT_max=5.0, rps_max=30)
    db1 = await _open(p)
    try:
        pass
    finally:
        await db1.async_close()
    db2 = await _open(p)
    try:
        conn = sqlite3.connect(str(p))
        count = conn.execute(
            "SELECT COUNT(*) FROM cycles WHERE is_transient=1"
        ).fetchone()[0]
        conn.close()
        assert count == 1
    finally:
        await db2.async_close()


async def test_insert_roundtrip_v16_columns(tmp_path: Path) -> None:
    p = tmp_path / "insert.db"
    db = await _open(p)
    try:
        # 1800s duration -> not matching the backfill rule, so an explicit
        # is_transient=1 survives even after a subsequent reopen.
        await db.async_insert_cycle({
            "start_ts": 5000.0, "end_ts": 6800.0, "duration_s": 1800,
            "mode": "heating", "dT_max": 5.0, "rps_max": 30,
            "thermal_kw_avg": 2.5, "is_transient": 1,
        })
        rows = await db.async_fetch_recent_cycles_for_hydration(limit=10)
        assert len(rows) == 1
        assert rows[0]["thermal_kw_avg"] == 2.5
        assert rows[0]["is_transient"] == 1
    finally:
        await db.async_close()


async def test_insert_defaults_when_not_provided(tmp_path: Path) -> None:
    p = tmp_path / "defaults.db"
    db = await _open(p)
    try:
        await db.async_insert_cycle({
            "start_ts": 6000.0, "end_ts": 6600.0, "duration_s": 600,
            "mode": "heating", "dT_max": 5.0, "rps_max": 30,
        })
        rows = await db.async_fetch_recent_cycles_for_hydration(limit=10)
        assert len(rows) == 1
        assert rows[0]["thermal_kw_avg"] is None
        assert rows[0]["is_transient"] == 0
    finally:
        await db.async_close()
