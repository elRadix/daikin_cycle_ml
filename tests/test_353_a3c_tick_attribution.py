"""#353 A3c: slow-tick attribution, lock-safe cop samples, conditional VACUUM.

Reproduction (2026-11-18): while another SQLite connection holds the write
lock, each statement of a tick waits up to busy_timeout (5 s) and a cop
sample that waits longer failed with "database is locked" and was dropped
(25 s lock: 2 of 6 samples stored). Prod-1 showed one isolated 27 s tick
with no way to tell when or where it happened.
"""
from __future__ import annotations

import asyncio
import sqlite3
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    _instrument_tick,
)
from custom_components.daikin_cycle_ml.diagnostics import (
    _coordinator_timing,
    _int_or_zero,
)
from custom_components.daikin_cycle_ml.storage import db as db_mod
from custom_components.daikin_cycle_ml.storage.db import (
    PENDING_COP_SAMPLES_MAX,
    VACUUM_MIN_FREE_RATIO,
    CycleDB,
    _is_locked,
)


def _sample(ts: float, cop: float = 3.5) -> dict[str, Any]:
    return {"ts": ts, "cop": cop, "lwt": 34.0, "outdoor": 7.0,
            "mode": "heating", "source": "interval", "power_stable": True}


async def _mk_db(tmp_path, name: str = "a3c.db") -> CycleDB:
    db = CycleDB(str(tmp_path / name), journal_mode="wal")
    await db.async_open()
    await db.async_initialize()
    await db.async_ensure_cop_samples_table()
    # short busy timeout so the lock test runs in milliseconds
    await db._require().execute("PRAGMA busy_timeout = 50")
    return db


async def _count(db: CycleDB) -> int:
    async with db._require().execute("SELECT COUNT(*) FROM cop_samples") as cur:
        row = await cur.fetchone()
    return int(row[0])


async def _close(db: CycleDB) -> None:
    await db.async_close()
    await asyncio.sleep(0.05)


# --- fix 2: cop samples survive a foreign write lock ---------------------------


async def test_locked_sample_is_queued_then_flushed(tmp_path, caplog):
    db = await _mk_db(tmp_path)
    try:
        now = time.time()
        async with aiosqlite.connect(db.path, isolation_level=None) as other:
            await other.execute("BEGIN EXCLUSIVE")
            assert await db.async_insert_cop_sample(_sample(now)) is True
            assert await db.async_insert_cop_sample(_sample(now + 60)) is True
            assert db.pending_cop_samples == 2
            await other.execute("COMMIT")
        assert "queued for retry" in caplog.text
        assert caplog.text.count("queued for retry") == 1  # logged once
        assert await db.async_insert_cop_sample(_sample(now + 120)) is True
        assert db.pending_cop_samples == 0
        assert await _count(db) == 3                       # nothing lost
        assert "queue flushed" in caplog.text
    finally:
        await _close(db)


async def test_queue_is_bounded(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        for i in range(PENDING_COP_SAMPLES_MAX + 5):
            db._pending_cop_samples.append(_sample(float(i)))
        assert db.pending_cop_samples == PENDING_COP_SAMPLES_MAX
    finally:
        await _close(db)


async def test_lock_during_flush_keeps_current_sample(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        db._pending_cop_samples.append(_sample(1.0))
        async with aiosqlite.connect(db.path, isolation_level=None) as other:
            await other.execute("BEGIN EXCLUSIVE")
            assert await db.async_insert_cop_sample(_sample(2.0)) is True
            await other.execute("COMMIT")
        assert db.pending_cop_samples == 2
    finally:
        await _close(db)


async def test_bad_queued_sample_is_dropped_not_blocking(tmp_path, caplog):
    db = await _mk_db(tmp_path)
    try:
        db._pending_cop_samples.append({"ts": "not-a-number", "cop": 3.0})
        assert await db.async_insert_cop_sample(_sample(time.time())) is True
        assert db.pending_cop_samples == 0
        assert await _count(db) == 1
        assert "dropping queued cop sample" in caplog.text
    finally:
        await _close(db)


async def test_other_operational_error_is_not_queued(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        db._exec_cop_insert = AsyncMock(  # type: ignore[method-assign]
            side_effect=sqlite3.OperationalError("no such column: x")
        )
        assert await db.async_insert_cop_sample(_sample(1.0)) is False
        assert db.pending_cop_samples == 0
    finally:
        await _close(db)


def test_is_locked_classifier():
    assert _is_locked(sqlite3.OperationalError("database is locked"))
    assert _is_locked(sqlite3.OperationalError("database table is BUSY"))
    assert not _is_locked(sqlite3.OperationalError("no such table"))
    assert not _is_locked(ValueError("database is locked"))


# --- fix 3: nightly VACUUM only when there is space to reclaim ------------------


async def test_free_page_ratio_and_conditional_vacuum(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        assert await db.async_free_page_ratio() < VACUUM_MIN_FREE_RATIO
        await db.async_run_maintenance(
            vacuum=True, vacuum_min_free_ratio=VACUUM_MIN_FREE_RATIO
        )
        assert db.last_vacuum["ran"] is False
        assert db.last_vacuum["skipped"] == "free_ratio_below_threshold"

        conn = db._require()
        await conn.executemany(
            "INSERT INTO cop_samples (ts, cop, mode, source, "
            "is_transition_artifact) VALUES (?, 3.5, 'heating', 'x', 0)",
            [(float(i),) for i in range(20000)],
        )
        await conn.commit()
        await conn.execute("DELETE FROM cop_samples")
        await conn.commit()
        assert await db.async_free_page_ratio() >= VACUUM_MIN_FREE_RATIO
        await db.async_run_maintenance(
            vacuum=True, vacuum_min_free_ratio=VACUUM_MIN_FREE_RATIO
        )
        assert db.last_vacuum["ran"] is True
        assert await db.async_free_page_ratio() < VACUUM_MIN_FREE_RATIO
    finally:
        await _close(db)


async def test_explicit_vacuum_always_runs(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        await db.async_run_maintenance(vacuum=True)  # default ratio 0.0
        assert db.last_vacuum["ran"] is True
        db.last_vacuum = {}
        await db.async_run_maintenance(vacuum=False)
        assert db.last_vacuum == {}
    finally:
        await _close(db)


async def test_free_page_ratio_error_means_vacuum(tmp_path, monkeypatch):
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()

        def boom(*_a, **_k):
            raise sqlite3.OperationalError("disk I/O error")

        monkeypatch.setattr(conn, "execute", boom)
        assert await db.async_free_page_ratio() == 1.0
    finally:
        monkeypatch.undo()
        await _close(db)


async def test_free_page_ratio_empty_rows(tmp_path, monkeypatch):
    db = await _mk_db(tmp_path)
    try:
        class _Cur:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def fetchone(self):
                return None

        monkeypatch.setattr(db._require(), "execute", lambda *_a, **_k: _Cur())
        assert await db.async_free_page_ratio() == 0.0
    finally:
        monkeypatch.undo()
        await _close(db)


@pytest.mark.parametrize(
    "vacuum,expected",
    [(None, VACUUM_MIN_FREE_RATIO), (True, 0.0), (False, 0.0)],
)
async def test_coordinator_passes_vacuum_ratio(vacuum, expected):
    class _C(DaikinCycleMLCoordinator):
        options: dict[str, Any] = {}  # type: ignore[assignment]

    c = object.__new__(_C)
    c.db = MagicMock()
    c.db.async_get_model_state = AsyncMock(return_value=None)
    c.db.async_run_maintenance = AsyncMock(return_value={})
    c.db.async_set_model_state = AsyncMock()
    c.db.async_integrity_check = AsyncMock(return_value=True)
    kw = {} if vacuum is None else {"vacuum": vacuum}
    out = await c.async_run_maintenance(**kw)
    assert out["ok"] is True
    got = c.db.async_run_maintenance.await_args.kwargs
    assert got["vacuum_min_free_ratio"] == expected


# --- fix 1: slow-tick attribution -----------------------------------------------


class _Ticker:
    _tick_mark = DaikinCycleMLCoordinator._tick_mark

    def __init__(self) -> None:
        self._tick_durations_ms: list[float] = []

    def _record_exception(self, exc: BaseException) -> None:  # pragma: no cover
        pass

    def _record_tick_health(self) -> None:
        pass

    @_instrument_tick
    async def run(self, slow: float, fast: float = 0.0, tail: float = 0.0) -> None:
        await asyncio.sleep(fast)
        self._tick_mark("fast_step")
        await asyncio.sleep(slow)
        self._tick_mark("slow_step")
        await asyncio.sleep(tail)


async def test_slowest_tick_is_attributed():
    t = _Ticker()
    await t.run(0.0)
    assert t._tick_duration_max_tick == 1
    before = time.time()
    await t.run(0.12, tail=0.03)
    assert t._tick_duration_max_tick == 2
    assert t._tick_duration_max_ts >= before
    phases = t._tick_duration_max_phases
    assert list(phases)[0] == "slow_step"
    assert phases["slow_step"] >= 100
    assert "rest" in phases                     # tail after the last mark
    # a faster tick does not overwrite the record
    await t.run(0.0)
    assert t._tick_duration_max_tick == 2
    assert len(t._tick_durations_ms) == 3


def test_tick_mark_without_phase_dict():
    t = _Ticker()
    t._tick_phases = None  # e.g. stub objects in older tests
    t._tick_mark("x")
    assert t._tick_mark_t > 0


def test_diagnostics_expose_attribution():
    t = _Ticker()
    t._tick_count = 4326
    t._tick_duration_max_ms = 27196.0
    t._tick_duration_max_ts = 1795000000.0
    t._tick_duration_max_tick = 1
    t._tick_duration_max_phases = {"cycle_close": 27000.0}
    out = _coordinator_timing(t)
    assert out["tick_duration_max_tick"] == 1
    assert out["tick_duration_max_ts"] == 1795000000.0
    assert out["tick_duration_max_phases_ms"] == {"cycle_close": 27000.0}
    empty = _coordinator_timing(object())
    assert empty["tick_duration_max_phases_ms"] == {}
    assert empty["tick_duration_max_tick"] is None


@pytest.mark.parametrize("v,exp", [(3, 3), (True, 0), (None, 0), ("2", 0)])
def test_int_or_zero(v, exp):
    assert _int_or_zero(v) == exp


def test_constants():
    assert db_mod.PENDING_COP_SAMPLES_MAX >= 60
    assert 0.0 < db_mod.VACUUM_MIN_FREE_RATIO < 1.0
