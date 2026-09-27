"""COV-2: db.py + store.py edge-case coverage.

Targets missing lines/branches from branch recon on e7a43e3:
  db.py: 132, 153-154, 296->302, 306->308, 309->311, 386-387,
         412, 419-421, 457-460, 627->625, 630
  store.py: 84, 88, 91

Test-only. No source changes.
"""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB
from custom_components.daikin_cycle_ml.storage.store import CycleStore


class _FakeCur:
    def __init__(self, rows):
        self._rows = rows

    async def fetchall(self):
        return self._rows

    async def close(self):
        return None


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, sql, params=None):
        return _FakeCur(self._rows)


@pytest.fixture
async def db(tmp_path):
    database = CycleDB(tmp_path / "cov2.db")
    await database.async_open()
    await database.async_initialize()
    try:
        yield database
    finally:
        await database.async_close()
        import asyncio as _a
        await _a.sleep(0.05)


# ---------- store.py missing lines ----------

def test_store_daily_reset_removes_today_keys():
    # line 84: pop *_today counters on day change
    s = CycleStore()
    s.increment("cycles_today", 3)
    s.increment("short_runs_today", 1)
    s._counters["_day_key"] = "1900-01-01"
    changed = s.daily_reset_if_needed(time.time())
    assert changed is True
    assert s.get("cycles_today") == 0
    assert s.get("short_runs_today") == 0


def test_store_record_short_run_and_off():
    # lines 88, 91
    s = CycleStore()
    assert s.record_short_run() == 1
    assert s.record_short_run() == 2
    assert s.record_short_off() == 1
    assert s.get("short_runs_today") == 2
    assert s.get("short_offs_today") == 1


# ---------- db.py integrity check: rows[0][0] != "ok" ----------

async def test_integrity_check_not_ok(db):
    # line 132: rows[0][0] != "ok"
    with patch.object(db, "_conn", _FakeConn([("not ok",)])):
        assert await db.async_integrity_check() is False


# ---------- db.py migrate_v11: malformed json skip ----------

async def test_migrate_v11_skips_malformed_json(db):
    # lines 153-154: json.loads raises -> continue
    # features.cycle_id has FK to cycles.id -> insert real cycles first
    now = time.time()
    cid_bad = await db.async_insert_cycle({
        "start_ts": now - 1000, "end_ts": now - 500, "duration_s": 500,
        "mode": "Heating", "dT_max": 5.0, "dT_avg": 4.0, "rps_max": 50,
        "rps_avg": 40.0, "outdoor_temp": 8.0, "buh_used": 0,
        "defrost_used": 0, "quality_score": 70,
    })
    cid_ok = await db.async_insert_cycle({
        "start_ts": now - 400, "end_ts": now - 200, "duration_s": 200,
        "mode": "Heating", "dT_max": 5.0, "dT_avg": 4.0, "rps_max": 50,
        "rps_avg": 40.0, "outdoor_temp": 8.0, "buh_used": 0,
        "defrost_used": 0, "quality_score": 70,
    })
    assert cid_bad and cid_ok
    conn = db._require()
    await conn.execute(
        "INSERT INTO features (cycle_id, vector_json) VALUES (?, ?)",
        (cid_bad, "{not valid json"),
    )
    await conn.execute(
        "INSERT INTO features (cycle_id, vector_json) VALUES (?, ?)",
        (cid_ok, "[1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0]"),
    )
    await conn.commit()
    n = await db.async_migrate_features_to_v11()
    assert n == 1  # only the 8-dim row migrated


# ---------- db.py run_maintenance: non-numeric fields ----------

async def test_maintenance_handles_non_numeric_fields(db):
    # branches 296->302, 306->308, 309->311 (isinstance checks)
    conn = db._require()
    now = time.time()
    await conn.execute(
        "INSERT INTO cycles (start_ts, end_ts, duration_s, mode, dT_max, dT_avg,"
        " rps_max, rps_avg, outdoor_temp, buh_used, defrost_used,"
        " quality_score) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (now - 3600, now - 3000, "bad", "Heating", "bad", 4.0,
         60, "bad", 8.0, 1, 1, "bad"),
    )
    await conn.commit()
    result = await db.async_run_maintenance(cycle_retention_days=0, vacuum=False)
    assert result["cycles_rolled_up"] >= 1


# ---------- db.py cop_samples prune exception ----------

async def test_maintenance_cop_prune_exception(db):
    # lines 386-387
    with patch.object(
        type(db), "async_ensure_cop_samples_table",
        side_effect=RuntimeError("boom"),
    ):
        result = await db.async_run_maintenance(vacuum=False)
    assert "cop_deleted" in result


# ---------- db.py vacuum paths ----------

async def test_vacuum_no_connection_returns_false(db):
    # line 412
    with patch.object(db, "_conn", None):
        assert await db.async_vacuum() is False


async def test_vacuum_exception_returns_false(db):
    # lines 419-421
    import aiosqlite as _ai
    with patch.object(_ai, "connect", side_effect=RuntimeError("nope")):
        assert await db.async_vacuum() is False


# ---------- db.py daily_summary n==0 branch ----------

async def test_daily_summary_zero_cycles(db):
    # lines 457-460: n = 0 -> *_avg = None
    conn = db._require()
    today = time.strftime("%Y-%m-%d")
    await conn.execute(
        "INSERT OR REPLACE INTO daily_summary"
        " (day, mode, cycles, total_duration_s, duration_min, duration_max,"
        "  quality_sum, dt_max_sum, rps_sum, buh_count, defrost_count,"
        "  updated_ts) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (today, "Heating", 0, 0, None, None, 0, 0.0, 0.0, 0, 0, time.time()),
    )
    await conn.commit()
    rows = await db.async_daily_summary(days=1)
    zero_rows = [r for r in rows if r.get("cycles") == 0]
    assert zero_rows, "expected at least one zero-cycle row"
    assert zero_rows[0]["duration_avg"] is None
    assert zero_rows[0]["quality_avg"] is None


# ---------- db.py avg_cop_between empty / non-numeric ----------

async def test_avg_cop_between_empty(db):
    # line 630: no cops -> None
    result = await db.async_avg_cop_between(1.0, 2.0)
    assert result is None


async def test_avg_cop_between_only_bad_values(db):
    # branch 627->625: cop is non-numeric
    conn = db._require()
    await db.async_ensure_cop_samples_table()
    await conn.execute(
        "INSERT INTO cop_samples (ts, cop, lwt, outdoor, flow_lmin, power_stable)"
        " VALUES (?,?,?,?,?,?)",
        (1.5, "bad", 40.0, 8.0, 20.0, 1),
    )
    await conn.commit()
    result = await db.async_avg_cop_between(1.0, 2.0)
    assert result is None
