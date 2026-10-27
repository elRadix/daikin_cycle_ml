"""Tests for v19 thermal_kw_avg rebuild migration (#169)."""
from __future__ import annotations

import json
from typing import Any

import pytest

from custom_components.daikin_cycle_ml.const import MAX_THERMAL_KW
from custom_components.daikin_cycle_ml.storage.db import CycleDB


@pytest.fixture
async def db(tmp_path):
    db = CycleDB(str(tmp_path / "v19.db"), journal_mode="delete")
    await db.async_initialize()
    yield db
    await db.async_close()


async def _insert_cycle(
    db: CycleDB,
    *,
    start_ts: float = 1000.0,
    end_ts: float = 2000.0,
    mode: str = "heating",
    thermal: float | None = 0.0,
) -> int:
    conn = db._require()
    cur = await conn.execute(
        "INSERT INTO cycles (start_ts, end_ts, mode, thermal_kw_avg, "
        "duration_s) VALUES (?, ?, ?, ?, ?)",
        (start_ts, end_ts, mode, thermal, end_ts - start_ts),
    )
    await conn.commit()
    cid = cur.lastrowid
    await cur.close()
    return int(cid)


async def _insert_feature(db: CycleDB, cycle_id: int, v11: float) -> None:
    vec = [0.0] * 12
    vec[11] = v11
    await db.async_insert_features(cycle_id, vec)


async def _insert_sample(
    db: CycleDB,
    *,
    ts: float,
    cop: float = 4.0,
    lwt: float = 35.0,
    outdoor: float = 10.0,
    flow_lmin: float = 20.0,
    mode: str = "heating",
    is_transition_artifact: int = 0,
) -> None:
    conn = db._require()
    await conn.execute(
        "INSERT INTO cop_samples (ts, cop, lwt, outdoor, flow_lmin, mode, "
        "is_transition_artifact) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ts, cop, lwt, outdoor, flow_lmin, mode, is_transition_artifact),
    )
    await conn.commit()


async def test_v19_idempotent_skip(db):
    conn = db._require()
    await db.async_set_model_state(
        "data_migration_v19_completed",
        {"completed": True, "completed_ts": 12345.0},
    )
    stats = await db.async_migrate_to_v19()
    assert stats == {"skipped": 1}


async def test_v19_marker_written(db):
    await _insert_cycle(db, start_ts=1000.0, end_ts=2000.0)
    stats = await db.async_migrate_to_v19()
    assert stats["completed"] is True
    assert "completed_ts" in stats
    marker = await db.async_get_model_state("data_migration_v19_completed")
    assert marker["completed"] is True
    assert "completed_ts" in marker


async def test_v19_recoverable_recomputes_average(db):
    cid = await _insert_cycle(db, start_ts=1000.0, end_ts=2000.0, thermal=0.0)
    # flow=5, lwt=35, outdoor=10 => dt=25
    # flow_dt = 5 * 0.997 * 4.186 * 25 / 60 = 8.69 kW  (< MAX_THERMAL_KW)
    for ts in (1100.0, 1200.0, 1300.0):
        await _insert_sample(db, ts=ts, flow_lmin=5.0, lwt=35.0, outdoor=10.0)
    stats = await db.async_migrate_to_v19()
    assert stats["recovered"] == 1
    assert stats["nulled"] == 0
    conn = db._require()
    cur = await conn.execute(
        "SELECT thermal_kw_avg FROM cycles WHERE id = ?", (cid,)
    )
    row = await cur.fetchone()
    await cur.close()
    assert row["thermal_kw_avg"] is not None
    assert abs(row["thermal_kw_avg"] - 8.69) < 0.5


async def test_v19_sparse_nulls(db):
    cid = await _insert_cycle(db, thermal=0.0)
    await _insert_sample(db, ts=1100.0)
    await _insert_sample(db, ts=1200.0)
    stats = await db.async_migrate_to_v19()
    assert stats["recovered"] == 0
    assert stats["nulled"] == 1
    conn = db._require()
    cur = await conn.execute(
        "SELECT thermal_kw_avg FROM cycles WHERE id = ?", (cid,)
    )
    row = await cur.fetchone()
    await cur.close()
    assert row["thermal_kw_avg"] is None


async def test_v19_no_samples_nulls(db):
    cid = await _insert_cycle(db, thermal=0.0)
    stats = await db.async_migrate_to_v19()
    assert stats["nulled"] == 1
    conn = db._require()
    cur = await conn.execute(
        "SELECT thermal_kw_avg FROM cycles WHERE id = ?", (cid,)
    )
    row = await cur.fetchone()
    await cur.close()
    assert row["thermal_kw_avg"] is None


async def test_v19_sanity_gate_rejects_overshoot(db):
    cid = await _insert_cycle(db, thermal=0.0)
    # flow=50, lwt=80, outdoor=0 => dt=80 => flow_dt=277.9 -> >MAX
    for ts in (1100.0, 1200.0, 1300.0):
        await _insert_sample(db, ts=ts, flow_lmin=50.0, lwt=80.0, outdoor=0.0)
    stats = await db.async_migrate_to_v19()
    assert stats["nulled"] == 1
    assert stats["recovered"] == 0


async def test_v19_dhw_uses_flow_dt(db):
    cid = await _insert_cycle(db, mode="dhw", thermal=0.0)
    # DHW R486: flow_dt preferred. Same formula as heating (in v19 both
    # use flow_dt because power_w is unavailable in cop_samples).
    for ts in (1100.0, 1200.0, 1300.0):
        await _insert_sample(
            db, ts=ts, mode="dhw", flow_lmin=4.0, lwt=50.0, outdoor=10.0
        )
    stats = await db.async_migrate_to_v19()
    assert stats["recovered"] == 1


async def test_v19_features_v11_overwritten(db):
    cid = await _insert_cycle(db, start_ts=1000.0, end_ts=2000.0, thermal=0.0)
    await _insert_feature(db, cid, v11=0.0)
    for ts in (1100.0, 1200.0, 1300.0):
        await _insert_sample(db, ts=ts, flow_lmin=5.0)
    stats = await db.async_migrate_to_v19()
    assert stats["recovered"] == 1
    assert stats["features_updated"] == 1
    conn = db._require()
    cur = await conn.execute(
        "SELECT vector_json FROM features WHERE cycle_id = ?", (cid,)
    )
    row = await cur.fetchone()
    await cur.close()
    vec = json.loads(row["vector_json"])
    assert vec[11] > 0.0


async def test_v19_features_v11_zeroed_for_nulled(db):
    cid = await _insert_cycle(db, thermal=0.0)
    await _insert_feature(db, cid, v11=5.0)
    # 0 samples -> nulled -> vector[11] set to 0.0
    stats = await db.async_migrate_to_v19()
    assert stats["nulled"] == 1
    assert stats["features_updated"] == 1
    conn = db._require()
    cur = await conn.execute(
        "SELECT vector_json FROM features WHERE cycle_id = ?", (cid,)
    )
    row = await cur.fetchone()
    await cur.close()
    vec = json.loads(row["vector_json"])
    assert vec[11] == 0.0


async def test_v19_daily_summary_rebuilt(db):
    # cycle 1: 2026-10-27 in local time
    import time
    day_ts = time.mktime((2026, 10, 27, 12, 0, 0, 0, 0, -1))
    await _insert_cycle(
        db, start_ts=day_ts, end_ts=day_ts + 600.0, thermal=0.0
    )
    for ts in (day_ts + 100.0, day_ts + 200.0, day_ts + 300.0):
        await _insert_sample(db, ts=ts)
    stats = await db.async_migrate_to_v19()
    assert stats["days_rebuilt"] == 1


async def test_v19_cop_hourly_rebuilt(db):
    await _insert_cycle(db, start_ts=1000.0, end_ts=2000.0, thermal=0.0)
    for ts in (1100.0, 1200.0, 1300.0):
        await _insert_sample(db, ts=ts)
    stats = await db.async_migrate_to_v19()
    assert stats["hours_rebuilt"] >= 1


# --- patch 3b: coverage for defensive branches (lines 1245-1434) ---


async def test_v19_thermal_helper_missing_fields(db):
    """Line 1245: _thermal_from_sample returns None on missing fields."""
    row = {"flow_lmin": None, "lwt": 35.0, "outdoor": 10.0}
    assert await db._thermal_from_sample(row, "heating") is None
    row = {"flow_lmin": 5.0, "lwt": None, "outdoor": 10.0}
    assert await db._thermal_from_sample(row, "heating") is None
    row = {"flow_lmin": 5.0, "lwt": 35.0, "outdoor": None}
    assert await db._thermal_from_sample(row, "heating") is None


async def test_v19_thermal_helper_nonpositive(db):
    """Line 1249: _thermal_from_sample returns None on flow<=0 or dt<=0."""
    row = {"flow_lmin": 0.0, "lwt": 35.0, "outdoor": 10.0}
    assert await db._thermal_from_sample(row, "heating") is None
    row = {"flow_lmin": -1.0, "lwt": 35.0, "outdoor": 10.0}
    assert await db._thermal_from_sample(row, "heating") is None
    row = {"flow_lmin": 5.0, "lwt": 10.0, "outdoor": 10.0}
    assert await db._thermal_from_sample(row, "heating") is None
    row = {"flow_lmin": 5.0, "lwt": 5.0, "outdoor": 10.0}
    assert await db._thermal_from_sample(row, "heating") is None


async def test_v19_features_corrupt_json(db):
    """Lines 1344-1345: corrupt vector_json -> vec=None -> skip update."""
    cid = await _insert_cycle(db, thermal=0.0)
    conn = db._require()
    await conn.execute(
        "INSERT INTO features (cycle_id, vector_json) VALUES (?, ?)",
        (cid, "{not valid json"),
    )
    await conn.commit()
    for ts in (1100.0, 1200.0, 1300.0):
        await _insert_sample(db, ts=ts, flow_lmin=5.0)
    stats = await db.async_migrate_to_v19()
    # migration still succeeds, feature update is skipped
    assert stats["recovered"] == 1
    assert stats["features_updated"] == 0


async def test_v19_features_short_vector(db):
    """Line 1346->1358: vector_json with len<12 -> skip update."""
    cid = await _insert_cycle(db, thermal=0.0)
    conn = db._require()
    await conn.execute(
        "INSERT INTO features (cycle_id, vector_json) VALUES (?, ?)",
        (cid, "[]"),
    )
    await conn.commit()
    for ts in (1100.0, 1200.0, 1300.0):
        await _insert_sample(db, ts=ts, flow_lmin=5.0)
    stats = await db.async_migrate_to_v19()
    assert stats["recovered"] == 1
    assert stats["features_updated"] == 0


async def test_v19_timestamp_localtime_error(db):
    """Lines 1363-1364: time.localtime overflows -> day skipped."""
    # 1e30 is a valid SQLite REAL (NOT NULL ok) but time.localtime()
    # raises OverflowError on it, exercising the except branch.
    cid = await _insert_cycle(
        db, start_ts=1e30, end_ts=1e30, thermal=0.0
    )
    # no samples in window (1e30 > any sample ts); cycle still processed
    for ts in (1100.0, 1200.0, 1300.0):
        await _insert_sample(db, ts=ts, flow_lmin=5.0)
    stats = await db.async_migrate_to_v19()
    # recovered 0 (no samples in 1e30 window), nulled 1, day skipped
    assert stats["nulled"] == 1
    assert stats["days_rebuilt"] == 0
    assert stats["completed"] is True


async def test_v19_rollup_exception_logged(db, monkeypatch):
    """Line 1407: async_rollup_day raising is caught + logged."""
    cid = await _insert_cycle(
        db, start_ts=1000.0, end_ts=2000.0, thermal=0.0
    )
    for ts in (1100.0, 1200.0, 1300.0):
        await _insert_sample(db, ts=ts, flow_lmin=5.0)

    async def boom(day):
        raise RuntimeError("rollup exploded")

    monkeypatch.setattr(db, "async_rollup_day", boom)
    stats = await db.async_migrate_to_v19()
    # recovered + features updated, days attempted but rollup failed
    assert stats["recovered"] == 1
    assert stats["days_rebuilt"] == 1  # counter counts attempts
    assert stats["completed"] is True


async def test_v19_hourly_empty_list(db):
    """Line 1421: _rebuild_cop_hourly_for_hours([]) -> 0."""
    assert await db._rebuild_cop_hourly_for_hours([]) == 0


async def test_v19_hourly_no_rows(db):
    """Line 1434: _rebuild_cop_hourly_for_hours with no matching samples -> 0."""
    # far-future hour with no samples
    assert await db._rebuild_cop_hourly_for_hours([999999999]) == 0
