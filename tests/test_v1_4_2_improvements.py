"""v1.4.2 tests."""
from __future__ import annotations

import inspect
import time

import pytest

from custom_components.daikin_cycle_ml.const import COP_ROLLUP_WINDOW_HOURS
from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)
from custom_components.daikin_cycle_ml.storage.db import CycleDB
from custom_components.daikin_cycle_ml.storage.store import CycleStore


def _today_ts(offset_s: float = 0.0) -> float:
    lt = time.localtime()
    base = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 12, 0, 0, 0, 0, -1))
    return float(base + offset_s)


def _old_ts() -> float:
    return _today_ts() - 3.0 * 86400.0


def test_rollup_window_const_is_720():
    assert COP_ROLLUP_WINDOW_HOURS == 720


def test_coordinator_rollup_default_uses_const():
    sig = inspect.signature(DaikinCycleMLCoordinator._maybe_rollup_cop_hourly)
    assert sig.parameters["window_hours"].default == COP_ROLLUP_WINDOW_HOURS


def test_hydrate_empty_returns_zero():
    s = CycleStore()
    assert s.hydrate_from_rows([]) == 0
    assert s.count() == 0


def test_hydrate_populates_deque_chronological():
    s = CycleStore()
    ts1, ts2 = _today_ts(0), _today_ts(60)
    n = s.hydrate_from_rows([
        {"start_ts": ts1, "quality_score": 90, "mode": "heating"},
        {"start_ts": ts2, "quality_score": 30, "mode": "heating"},
    ])
    assert n == 2
    assert s.last_cycle()["start_ts"] == ts2


def test_hydrate_recomputes_today_counters():
    s = CycleStore()
    ts = _today_ts()
    s.hydrate_from_rows([
        {"start_ts": ts, "quality_score": 80},
        {"start_ts": ts + 60, "quality_score": 30},
        {"start_ts": ts + 120, "quality_score": 100},
    ])
    assert s.get("good_cycles_today") == 2
    assert s.get("bad_cycles_today") == 1
    assert s.get("cycles_today") == 3


def test_hydrate_skips_missing_start_ts():
    s = CycleStore()
    s.hydrate_from_rows([
        {"quality_score": 80},
        {"start_ts": _today_ts(), "quality_score": 80},
    ])
    assert s.get("cycles_today") == 1
    assert s.get("good_cycles_today") == 1


def test_hydrate_skips_bool_start_ts():
    s = CycleStore()
    s.hydrate_from_rows([{"start_ts": True, "quality_score": 80}])
    assert s.get("cycles_today") == 0


def test_hydrate_skips_non_today():
    s = CycleStore()
    s.hydrate_from_rows([
        {"start_ts": _old_ts(), "quality_score": 90},
        {"start_ts": _today_ts(), "quality_score": 30},
    ])
    assert s.get("cycles_today") == 1
    assert s.get("bad_cycles_today") == 1
    assert s.get("good_cycles_today") == 0


def test_hydrate_skips_none_quality():
    s = CycleStore()
    s.hydrate_from_rows([{"start_ts": _today_ts(), "quality_score": None}])
    assert s.get("cycles_today") == 1
    assert s.get("good_cycles_today") == 0


def test_hydrate_skips_bool_quality():
    s = CycleStore()
    s.hydrate_from_rows([{"start_ts": _today_ts(), "quality_score": True}])
    assert s.get("good_cycles_today") == 0
    assert s.get("bad_cycles_today") == 0


def test_hydrate_maxlen_pops_oldest():
    s = CycleStore(maxlen=2)
    ts = _today_ts()
    n = s.hydrate_from_rows([
        {"start_ts": ts},
        {"start_ts": ts + 1},
        {"start_ts": ts + 2},
    ])
    assert n == 2
    assert s.last_cycle()["start_ts"] == ts + 2


@pytest.fixture
async def db(tmp_path):
    d = CycleDB(tmp_path / "test.db")
    await d.async_open()
    await d.async_initialize()
    yield d
    await d.async_close()


async def test_fetch_recent_cycles_empty(db):
    assert await db.async_fetch_recent_cycles_for_hydration() == []


async def test_fetch_recent_cycles_chronological(db):
    await db.async_insert_cycle(
        {"start_ts": 1.0, "duration_s": 3600, "mode": "heating"}
    )
    await db.async_insert_cycle(
        {"start_ts": 2.0, "duration_s": 60, "mode": "dhw"}
    )
    rows = await db.async_fetch_recent_cycles_for_hydration()
    assert len(rows) == 2
    assert rows[0]["start_ts"] == 1.0
    assert rows[1]["start_ts"] == 2.0


async def test_backfill_updates_null_scores(db):
    await db.async_insert_cycle(
        {"start_ts": 1.0, "duration_s": 3600, "dT_max": 8.0}
    )
    await db.async_insert_cycle(
        {"start_ts": 2.0, "duration_s": 60, "dT_max": 1.0}
    )

    def _scorer(rec):
        return 100 if rec["duration_s"] >= 3600 else 30

    assert await db.async_backfill_quality_scores(_scorer) == 2
    assert await db.async_backfill_quality_scores(_scorer) == 0


async def test_backfill_empty_table(db):
    assert await db.async_backfill_quality_scores(lambda r: 50) == 0


async def test_backfill_scorer_exception_skipped(db):
    await db.async_insert_cycle({"start_ts": 1.0, "duration_s": 100})

    def _boom(rec):
        raise RuntimeError("boom")

    assert await db.async_backfill_quality_scores(_boom) == 0


async def test_backfill_scorer_none_skipped(db):
    await db.async_insert_cycle({"start_ts": 1.0, "duration_s": 100})
    assert await db.async_backfill_quality_scores(lambda r: None) == 0


async def test_backfill_scorer_bool_skipped(db):
    await db.async_insert_cycle({"start_ts": 1.0, "duration_s": 100})
    assert await db.async_backfill_quality_scores(lambda r: True) == 0


async def test_prune_cop_hourly_empty(db):
    assert await db.async_prune_cop_hourly(retention_days=365) == 0


async def test_prune_cop_hourly_deletes_old(db):
    conn = db._require()
    old_ts = int(time.time()) - 400 * 86400
    await conn.execute(
        "INSERT INTO cop_hourly (ts_hour, mode, n_samples, updated_ts) "
        "VALUES (?, ?, ?, ?)",
        (old_ts, "heating", 1, time.time()),
    )
    await conn.commit()
    assert await db.async_prune_cop_hourly(retention_days=365) >= 1


async def test_run_maintenance_prunes_cop_hourly(db):
    conn = db._require()
    old_ts = int(time.time()) - 500 * 86400
    await conn.execute(
        "INSERT INTO cop_hourly (ts_hour, mode, n_samples, updated_ts) "
        "VALUES (?, ?, ?, ?)",
        (old_ts, "heating", 1, time.time()),
    )
    await conn.commit()
    await db.async_run_maintenance(vacuum=False)
    cur = await conn.execute(
        "SELECT COUNT(*) FROM cop_hourly WHERE ts_hour = ?", (old_ts,)
    )
    row = await cur.fetchone()
    await cur.close()
    assert row[0] == 0


async def test_run_maintenance_prune_raises(db, monkeypatch):
    async def _boom(self, retention_days=365):
        raise RuntimeError("boom")

    monkeypatch.setattr(CycleDB, "async_prune_cop_hourly", _boom)
    conn = db._require()
    old_ts = int(time.time()) - 500 * 86400
    await conn.execute(
        "INSERT INTO cop_hourly (ts_hour, mode, n_samples, updated_ts) "
        "VALUES (?, ?, ?, ?)",
        (old_ts, "heating", 1, time.time()),
    )
    await conn.commit()
    await db.async_run_maintenance(vacuum=False)


class _FakeCoord:
    def __init__(self, db_obj=None):
        self.db = db_obj
        self.store = CycleStore()


async def test_hydrate_store_no_db():
    from custom_components.daikin_cycle_ml import _async_hydrate_store
    assert await _async_hydrate_store(_FakeCoord(db_obj=None)) == 0


async def test_hydrate_store_wrong_return():
    from custom_components.daikin_cycle_ml import _async_hydrate_store

    class _DB:
        async def async_fetch_recent_cycles_for_hydration(self):
            return "not-a-list"

    assert await _async_hydrate_store(_FakeCoord(db_obj=_DB())) == 0


async def test_hydrate_store_raises():
    from custom_components.daikin_cycle_ml import _async_hydrate_store

    class _DB:
        async def async_fetch_recent_cycles_for_hydration(self):
            raise RuntimeError("boom")

    assert await _async_hydrate_store(_FakeCoord(db_obj=_DB())) == 0


async def test_hydrate_store_with_rows():
    from custom_components.daikin_cycle_ml import _async_hydrate_store

    class _DB:
        async def async_fetch_recent_cycles_for_hydration(self):
            return [{"start_ts": _today_ts(), "quality_score": 90}]

    c = _FakeCoord(db_obj=_DB())
    assert await _async_hydrate_store(c) == 1
    assert c.store.get("good_cycles_today") == 1


async def test_hydrate_store_empty_list():
    from custom_components.daikin_cycle_ml import _async_hydrate_store

    class _DB:
        async def async_fetch_recent_cycles_for_hydration(self):
            return []

    assert await _async_hydrate_store(_FakeCoord(db_obj=_DB())) == 0


async def test_backfill_quality_no_db():
    from custom_components.daikin_cycle_ml import _async_backfill_quality
    assert await _async_backfill_quality(_FakeCoord(db_obj=None)) == 0


async def test_backfill_quality_raises():
    from custom_components.daikin_cycle_ml import _async_backfill_quality

    class _DB:
        async def async_backfill_quality_scores(self, scorer):
            raise RuntimeError("boom")

    assert await _async_backfill_quality(_FakeCoord(db_obj=_DB())) == 0


async def test_backfill_quality_calls_db():
    from custom_components.daikin_cycle_ml import _async_backfill_quality

    captured = {}

    class _DB:
        async def async_backfill_quality_scores(self, scorer):
            captured["scorer"] = scorer
            return 5

    n = await _async_backfill_quality(_FakeCoord(db_obj=_DB()))
    assert n == 5
    assert callable(captured["scorer"])


async def test_backfill_quality_scorer_invoked():
    """Force _scorer to execute so its return statement is covered."""
    from custom_components.daikin_cycle_ml import _async_backfill_quality

    seen = {}

    class _DB:
        async def async_backfill_quality_scores(self, scorer):
            seen["r"] = scorer(
                {"duration_s": 3600, "dT_max": 8.0, "buh_used": False}
            )
            return 1

    n = await _async_backfill_quality(_FakeCoord(db_obj=_DB()))
    assert n == 1
    assert isinstance(seen["r"], int)


async def test_backfill_quality_non_int_return():
    from custom_components.daikin_cycle_ml import _async_backfill_quality

    class _DB:
        async def async_backfill_quality_scores(self, scorer):
            return None

    assert await _async_backfill_quality(_FakeCoord(db_obj=_DB())) == 0
