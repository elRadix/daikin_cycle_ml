"""v1.12.2: DB data-integrity fixes.

- #111: async_prune_cop_hourly cutoff in hours (matches ts_hour storage)
- #112: v17 migration reclassifies unknown-mode cycles with valid data
- #114: v17 migration backfills thermal_kw_avg from features.vector_json[11]

WAL (#113) deferred to v1.12.3 — see issue #113 for design rationale.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB


@pytest.fixture
async def db(tmp_path: Path):
    d = CycleDB(tmp_path / "v1122.db")
    await d.async_open()
    await d.async_initialize()
    yield d
    await d.async_close()


async def _insert_cop_hourly(db, ts_hours: int, mode: str = "heating") -> None:
    conn = db._require()
    await conn.execute(
        "INSERT OR REPLACE INTO cop_hourly "
        "(ts_hour, mode, n_samples, cop_mean, updated_ts) "
        "VALUES (?, ?, ?, ?, ?)",
        (ts_hours, mode, 1, 3.0, time.time()),
    )
    await conn.commit()


async def _count_cop_hourly(db) -> int:
    conn = db._require()
    cur = await conn.execute("SELECT COUNT(*) FROM cop_hourly")
    row = await cur.fetchone()
    await cur.close()
    return int(row[0])


# --- #111: retention uses hours ---

async def test_prune_uses_hours_units_empty(db):
    assert await db.async_prune_cop_hourly(retention_days=365) == 0
    assert await _count_cop_hourly(db) == 0


async def test_prune_uses_hours_units_prunes_old(db):
    # 500 days ago in HOURS-since-epoch (correct storage format)
    old_hours = int((time.time() - 500 * 86400) // 3600)
    await _insert_cop_hourly(db, old_hours)
    assert await _count_cop_hourly(db) == 1
    deleted = await db.async_prune_cop_hourly(retention_days=365)
    assert deleted == 1
    assert await _count_cop_hourly(db) == 0


async def test_prune_uses_hours_units_preserves_recent(db):
    # 30 days ago — well within 365d window
    recent_hours = int((time.time() - 30 * 86400) // 3600)
    await _insert_cop_hourly(db, recent_hours)
    deleted = await db.async_prune_cop_hourly(retention_days=365)
    assert deleted == 0
    assert await _count_cop_hourly(db) == 1


async def test_prune_uses_hours_units_boundary(db):
    # 364 days ago — just inside window, must survive
    inside_hours = int((time.time() - 364 * 86400) // 3600)
    await _insert_cop_hourly(db, inside_hours)
    assert await db.async_prune_cop_hourly(retention_days=365) == 0
    assert await _count_cop_hourly(db) == 1


async def test_prune_does_not_delete_when_ts_was_seconds(db):
    # Regression: v1.12.1 stored/compared inconsistently, every row matched.
    # If any legacy code inserts SECONDS into ts_hour, prune with hours
    # cutoff would correctly NOT delete it (seconds > hours threshold),
    # but v17 migration is responsible for converting such rows.
    # This test asserts no destructive prune on mixed-format state.
    bad_seconds_ts = int(time.time())  # huge value, not hours
    await _insert_cop_hourly(db, bad_seconds_ts)
    # prune compares hours cutoff vs this row -> row NOT pruned
    deleted = await db.async_prune_cop_hourly(retention_days=365)
    assert deleted == 0
    assert await _count_cop_hourly(db) == 1


# --- v17 migration helpers ---

async def _insert_cycle(db, **fields) -> int:
    defaults = {
        "start_ts": time.time() + hash(str(fields)) % 1_000_000,
        "end_ts": None,
        "duration_s": 600,
        "mode": "heating",
        "dT_max": 5.0,
        "rps_max": 30,
        "quality_score": 50,
        "is_transient": 0,
        "thermal_kw_avg": None,
    }
    defaults.update(fields)
    cid = await db.async_insert_cycle(defaults)
    assert cid is not None
    return int(cid)


async def _insert_feature(db, cycle_id: int, vector: list) -> None:
    conn = db._require()
    await conn.execute(
        "INSERT OR REPLACE INTO features (cycle_id, vector_json) VALUES (?, ?)",
        (cycle_id, json.dumps(vector)),
    )
    await conn.commit()


async def _get_cycle(db, cid: int) -> dict:
    conn = db._require()
    cur = await conn.execute(
        "SELECT mode, thermal_kw_avg FROM cycles WHERE id = ?", (cid,)
    )
    row = await cur.fetchone()
    await cur.close()
    assert row is not None
    return {"mode": row[0], "thermal_kw_avg": row[1]}


async def _get_marker(db) -> str | None:
    conn = db._require()
    cur = await conn.execute(
        "SELECT value_json FROM model_state WHERE key='data_migration_v1_12_2'"
    )
    row = await cur.fetchone()
    await cur.close()
    return row[0] if row else None


# --- #112: v17 reclassifies unknown-mode cycles with valid data ---

async def test_v17_reclassifies_unknown_with_valid_data(db):
    cid = await _insert_cycle(
        db, mode="unknown", rps_max=40, dT_max=4.0, duration_s=1200
    )
    await db.async_migrate_to_v17()
    row = await _get_cycle(db, cid)
    assert row["mode"] == "heating"


async def test_v17_keeps_unknown_without_compressor_data(db):
    """User3 edge case: unknown cycle with no rps / short duration stays unknown."""
    cid = await _insert_cycle(
        db, mode="unknown", rps_max=0, dT_max=0.0, duration_s=60
    )
    await db.async_migrate_to_v17()
    row = await _get_cycle(db, cid)
    assert row["mode"] == "unknown"


async def test_v17_keeps_unknown_when_duration_short(db):
    """Duration <= 300s → excluded even if rps/dT present (transient-like)."""
    cid = await _insert_cycle(
        db, mode="unknown", rps_max=40, dT_max=4.0, duration_s=120
    )
    await db.async_migrate_to_v17()
    row = await _get_cycle(db, cid)
    assert row["mode"] == "unknown"


# --- #114: v17 backfills thermal_kw_avg from vector_json[11] ---

async def test_v17_backfills_thermal_from_vector_json(db):
    cid = await _insert_cycle(db, thermal_kw_avg=None)
    vector = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3.7]
    await _insert_feature(db, cid, vector)
    await db.async_migrate_to_v17()
    row = await _get_cycle(db, cid)
    assert row["thermal_kw_avg"] == pytest.approx(3.7)


async def test_v17_skips_malformed_vector_json(db):
    cid = await _insert_cycle(db, thermal_kw_avg=None)
    conn = db._require()
    await conn.execute(
        "INSERT OR REPLACE INTO features (cycle_id, vector_json) VALUES (?, ?)",
        (cid, "{not-json-at-all"),
    )
    await conn.commit()
    # Must not crash, must not populate
    await db.async_migrate_to_v17()
    row = await _get_cycle(db, cid)
    assert row["thermal_kw_avg"] is None


async def test_v17_skips_short_legacy_vector(db):
    cid = await _insert_cycle(db, thermal_kw_avg=None)
    await _insert_feature(db, cid, [0, 0, 0, 0])  # only 4 dims, pre-v11
    await db.async_migrate_to_v17()
    row = await _get_cycle(db, cid)
    assert row["thermal_kw_avg"] is None


async def test_v17_preserves_existing_thermal_kw(db):
    """Never overwrite non-NULL thermal_kw_avg even if vector differs."""
    cid = await _insert_cycle(db, thermal_kw_avg=9.9)
    await _insert_feature(
        db, cid, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1.1]
    )
    await db.async_migrate_to_v17()
    row = await _get_cycle(db, cid)
    assert row["thermal_kw_avg"] == pytest.approx(9.9)


async def test_v17_marker_prevents_rerun(db):
    cid = await _insert_cycle(db, mode="unknown", rps_max=40, dT_max=4.0, duration_s=1200)
    await db.async_migrate_to_v17()
    assert await _get_marker(db) is not None
    # Manually flip back to unknown to test idempotency guard
    conn = db._require()
    await conn.execute("UPDATE cycles SET mode='unknown' WHERE id=?", (cid,))
    await conn.commit()
    # Second call should be a no-op (marker present)
    result = await db.async_migrate_to_v17()
    assert result.get("skipped") == 1
    row = await _get_cycle(db, cid)
    assert row["mode"] == "unknown"  # NOT re-fixed


# --- #112b: v17 rebuilds daily_summary for unknown-mode days ---

async def _insert_unknown_ds(db, day: str) -> None:
    conn = db._require()
    await conn.execute(
        "INSERT OR REPLACE INTO daily_summary "
        "(day, mode, cycles, total_duration_s, updated_ts) "
        "VALUES (?, 'unknown', 1, 600, ?)",
        (day, time.time()),
    )
    await conn.commit()


async def test_v17_rebuilds_ds_for_unknown_days(db):
    """Loop body executes when daily_summary has unknown-mode row."""
    cid = await _insert_cycle(
        db, mode="unknown", rps_max=40, dT_max=4.0, duration_s=1200,
    )
    # Need a cycle for rollup to see — but write an unknown DS row too
    conn = db._require()
    # Set start_ts so rollup covers today
    start = time.time() - 600
    await conn.execute(
        "UPDATE cycles SET start_ts=?, end_ts=? WHERE id=?",
        (start, start + 1200, cid),
    )
    await conn.commit()
    today = time.strftime("%Y-%m-%d", time.localtime(start))
    await _insert_unknown_ds(db, today)

    result = await db.async_migrate_to_v17()
    assert result["mode_reclassified"] >= 1
    assert result["ds_days_rebuilt"] >= 1

    # Verify unknown DS row replaced by rollup
    cur = await conn.execute(
        "SELECT COUNT(*) FROM daily_summary WHERE day=? AND mode='unknown'",
        (today,),
    )
    row = await cur.fetchone()
    await cur.close()
    assert int(row[0]) == 0  # unknown row replaced


async def test_v17_ds_rebuild_failure_isolated(db, monkeypatch):
    """Per-day rollup failure must not abort the migration."""
    await _insert_cycle(
        db, mode="unknown", rps_max=40, dT_max=4.0, duration_s=1200,
    )
    await _insert_unknown_ds(db, "2026-10-22")

    async def _boom(self, day, **_):
        raise RuntimeError("rollup boom")

    monkeypatch.setattr(CycleDB, "async_rollup_day", _boom)
    # Must NOT raise even though rollup fails
    result = await db.async_migrate_to_v17()
    assert result["mode_reclassified"] >= 1
    # Marker still written despite rollup failure
    assert await _get_marker(db) is not None


async def test_v17_ds_unknown_delete_failure_isolated(db):
    """DS DELETE failure must be caught, migration continues, marker written.

    Covers defensive except branch (db.py:453-454) that handles
    DELETE FROM daily_summary failure (WAL lock, IO error, corruption).
    """
    await _insert_cycle(
        db, mode="unknown", rps_max=40, dT_max=4.0, duration_s=1200,
    )
    await _insert_unknown_ds(db, "2026-10-22")

    real_conn = db._conn

    class _FailingDeleteConn:
        def __init__(self, inner):
            self._inner = inner

        async def execute(self, sql, *args, **kwargs):
            if isinstance(sql, str) and "DELETE FROM daily_summary" in sql:
                raise RuntimeError("forced delete failure")
            return await self._inner.execute(sql, *args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._inner, name)

    db._conn = _FailingDeleteConn(real_conn)
    try:
        result = await db.async_migrate_to_v17()
    finally:
        db._conn = real_conn

    # Migration completed despite DELETE failure
    assert result["mode_reclassified"] >= 1
    assert await _get_marker(db) is not None
