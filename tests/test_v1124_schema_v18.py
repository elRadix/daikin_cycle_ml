"""v1.12.4 (v18) schema migration tests.

Covers both paths of async_migrate_schema_to_v18:
- Fresh install: schema.sql already has v18 columns -> skip branch
- Upgrade from v16: pre-v18 tables exist -> ALTER branch
- Idempotency: second call returns 0/0
"""
from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB

V18_CYCLES_COLS = {"mode_original", "parent_cycle_id",
                   "is_dhw_tail", "is_reconstructed"}
V18_SAMPLES_COLS = {"mode_original", "is_transition_artifact"}
V18_INDICES = {"idx_cop_samples_artifact", "idx_cycles_reconstructed"}


PRE_V18_SCHEMA = """
CREATE TABLE cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_ts REAL NOT NULL, end_ts REAL, duration_s INTEGER, mode TEXT,
    dT_max REAL, dT_avg REAL, rps_max INTEGER, rps_avg REAL, outdoor_temp REAL,
    buh_used INTEGER DEFAULT 0, defrost_used INTEGER DEFAULT 0,
    quality_score INTEGER, label TEXT, cluster_id INTEGER,
    cop_avg REAL, cop_sample_count INTEGER, cop_sample_stdev REAL,
    cop_confidence TEXT, thermal_kw_avg REAL, is_transient INTEGER DEFAULT 0,
    UNIQUE(start_ts)
);
CREATE TABLE cop_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,
    cop REAL NOT NULL, lwt REAL, outdoor REAL, flow_lmin REAL,
    power_stable INTEGER DEFAULT 0, mode TEXT DEFAULT 'unknown',
    source TEXT DEFAULT 'interval'
);
CREATE TABLE model_state (key TEXT PRIMARY KEY, value_json TEXT NOT NULL,
    updated_ts REAL NOT NULL);
CREATE TABLE alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,
    alert_type TEXT NOT NULL, severity TEXT NOT NULL, message TEXT NOT NULL,
    aggregated_count INTEGER DEFAULT 1, UNIQUE(ts, alert_type));
CREATE TABLE features (cycle_id INTEGER PRIMARY KEY REFERENCES cycles(id),
    vector_json TEXT NOT NULL);
CREATE TABLE daily_summary (day TEXT NOT NULL, mode TEXT NOT NULL,
    cycles INTEGER NOT NULL DEFAULT 0, total_duration_s INTEGER NOT NULL DEFAULT 0,
    duration_min INTEGER, duration_max INTEGER,
    quality_sum INTEGER NOT NULL DEFAULT 0, dt_max_sum REAL NOT NULL DEFAULT 0,
    rps_sum REAL NOT NULL DEFAULT 0, buh_count INTEGER NOT NULL DEFAULT 0,
    defrost_count INTEGER NOT NULL DEFAULT 0, updated_ts REAL NOT NULL,
    PRIMARY KEY (day, mode));
CREATE TABLE cop_hourly (ts_hour INTEGER NOT NULL, mode TEXT NOT NULL,
    n_samples INTEGER NOT NULL, cop_mean REAL, cop_p10 REAL, cop_p50 REAL,
    cop_p90 REAL, cop_std REAL, lwt_mean REAL, outdoor_mean REAL,
    outdoor_min REAL, outdoor_max REAL, flow_mean REAL, updated_ts REAL NOT NULL,
    PRIMARY KEY (ts_hour, mode));
"""


async def _get_columns(db: CycleDB, table: str) -> set[str]:
    async with db._require().execute(f"PRAGMA table_info({table})") as cur:
        return {r[1] for r in await cur.fetchall()}


async def _get_indices(db: CycleDB) -> set[str]:
    async with db._require().execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
    ) as cur:
        return {r[0] for r in await cur.fetchall()}


@pytest.fixture
async def fresh_db(tmp_path: Path):
    db = CycleDB(tmp_path / "fresh.db")
    await db.async_open()
    await db.async_initialize()
    yield db
    await db.async_close()


async def test_fresh_db_has_v18_columns(fresh_db):
    assert V18_CYCLES_COLS <= await _get_columns(fresh_db, "cycles")
    assert V18_SAMPLES_COLS <= await _get_columns(fresh_db, "cop_samples")


async def test_fresh_db_has_v18_indices(fresh_db):
    assert V18_INDICES <= await _get_indices(fresh_db)


async def test_schema_migration_idempotent_on_fresh_db(fresh_db):
    added = await fresh_db.async_migrate_schema_to_v18()
    assert added == {"cycles": 0, "cop_samples": 0}


async def test_upgrade_from_v16_adds_v18_columns(tmp_path: Path):
    """Simulate v1.12.3 -> v1.12.4 upgrade path (the real prod scenario)."""
    db_path = tmp_path / "upgrade.db"

    # Create pre-v18 DB
    raw = await aiosqlite.connect(str(db_path))
    try:
        await raw.executescript(PRE_V18_SCHEMA)
        await raw.commit()
    finally:
        await raw.close()

    db = CycleDB(db_path)
    await db.async_open()
    try:
        # Sanity: pre-v18 state
        assert not (V18_CYCLES_COLS & await _get_columns(db, "cycles"))
        assert not (V18_SAMPLES_COLS & await _get_columns(db, "cop_samples"))
        assert not (V18_INDICES & await _get_indices(db))

        # Upgrade via async_initialize (production path)
        await db.async_initialize()

        assert V18_CYCLES_COLS <= await _get_columns(db, "cycles")
        assert V18_SAMPLES_COLS <= await _get_columns(db, "cop_samples")
        assert V18_INDICES <= await _get_indices(db)
    finally:
        await db.async_close()


async def test_direct_call_adds_columns_on_v16_db(tmp_path: Path):
    """ALTER branch exercised explicitly (covers added += 1)."""
    db_path = tmp_path / "direct.db"
    raw = await aiosqlite.connect(str(db_path))
    try:
        await raw.executescript(PRE_V18_SCHEMA)
        await raw.commit()
    finally:
        await raw.close()

    db = CycleDB(db_path)
    await db.async_open()
    try:
        added = await db.async_migrate_schema_to_v18()
        assert added == {"cycles": 4, "cop_samples": 2}
        # Second call: all exist -> 0/0
        assert await db.async_migrate_schema_to_v18() == {
            "cycles": 0, "cop_samples": 0,
        }
    finally:
        await db.async_close()
