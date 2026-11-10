"""R782: open cycles must be visible in daily_summary BEFORE they close.

v1.19.8 #262 intent was explicitly: "include open cycles so a long run
is visible in daily_summary BEFORE it closes." The SQL in
async_rollup_day supports this (end_ts IS NULL -> c_end=cap_ts), but
async_rollup_day was only called from _maybe_rollup_day (cycle close).
No periodic path existed, so an open 20-hour heating cycle left
daily_summary stale for its entire duration.

Prod evidence (issue #316, ed-vanleeuwen 2026-11-10):
  daily_summary(2026-11-10, heating): cycles=0, total_duration_s=22493
  The 22493s is pro-rata overlap from yesterday's cycle ending today.
  The currently-open cycle (5851s at snapshot time) is NOT reflected.
  updated_ts stuck at 17:00 (=DHW cycle close). Next 18:00 tick:
  _refresh_7d_rollups refreshed caches but did NOT re-rollup today.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import custom_components.daikin_cycle_ml.coordinator as coord_mod
from custom_components.daikin_cycle_ml.const import (
    OPTION_DAILY_SUMMARY_LIVE_ENABLED,
)
from custom_components.daikin_cycle_ml.storage.db import CycleDB


@pytest.fixture(autouse=True)
async def _close_dbs():
    """Ensure DBs close cleanly even when a test asserts early."""
    yield
    # aiosqlite closes on GC; force flush by yielding control once
    import asyncio as _asyncio
    await _asyncio.sleep(0)


async def _mk_db(tmp_path, name="test.db"):
    db = CycleDB(str(tmp_path / name))
    await db.async_open()
    await db.async_initialize()
    return db


async def _insert_cycle(conn, start, end, mode="heating", **kw):
    dur = int(end - start) if end is not None else None
    await conn.execute(
        "INSERT INTO cycles "
        "(start_ts, end_ts, duration_s, mode, is_transient, "
        " is_reconstructed, quality_score, dT_max, rps_avg, "
        " buh_used, defrost_used, thermal_kw_avg) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            start, end, dur, mode,
            kw.get("is_transient", 0),
            kw.get("is_reconstructed", 0),
            kw.get("quality_score", 80),
            kw.get("dT_max", 4.0),
            kw.get("rps_avg", 25.0),
            kw.get("buh_used", 0),
            kw.get("defrost_used", 0),
            kw.get("thermal_kw_avg", 3.0),
        ),
    )
    await conn.commit()


async def _row(conn, day, mode="heating"):
    cur = await conn.execute(
        "SELECT * FROM daily_summary WHERE day=? AND mode=?",
        (day, mode),
    )
    r = await cur.fetchone()
    await cur.close()
    return r


def _make_coordinator(db, state="running"):
    return SimpleNamespace(
        db=db,
        options={},
        detector=SimpleNamespace(state=state),
        _last_rollup_today_ts=0.0,
        _refresh_daily_summary_recent=AsyncMock(),
    )


def _live_rollup():
    cls = getattr(coord_mod, "DaikinCycleMLCoordinator", None)
    if cls is None:
        raise RuntimeError(
            "Coordinator class not found. Available: "
            + str([n for n in dir(coord_mod) if n.endswith("Coordinator")])
        )
    method = getattr(cls, "_maybe_rollup_today_live", None)
    if method is None:
        raise AttributeError(
            "_maybe_rollup_today_live is not implemented yet (R782 RED test)"
        )
    return method


# --- Sanity: SQL already supports open cycles when called directly ----------


@pytest.mark.asyncio
async def test_sql_supports_open_cycles_when_called_directly(tmp_path):
    """Baseline: async_rollup_day already handles end_ts IS NULL.

    PASSES on current code. Must continue to pass after the fix. Proves
    the bug is in the missing caller, not in the SQL.
    """
    db = await _mk_db(tmp_path)
    now = time.time()
    today = time.strftime("%Y-%m-%d", time.localtime(now))

    await _insert_cycle(db._conn, now - 3600, None, "heating")

    await db.async_rollup_day(today)

    row = await _row(db._conn, today, "heating")
    assert row is not None
    assert row["total_duration_s"] >= 3500
    assert row["cycles"] == 1
    assert row["duration_min"] is None  # open cycle has duration_s=NULL


# --- RED: the missing production path ---------------------------------------


@pytest.mark.asyncio
async def test_open_cycle_visible_via_live_rollup(tmp_path):
    """R782: _maybe_rollup_today_live must surface open cycles.

    Current code: AttributeError (method does not exist).
    After fix: PASS.
    """
    db = await _mk_db(tmp_path)
    now = time.time()
    today = time.strftime("%Y-%m-%d", time.localtime(now))

    await _insert_cycle(db._conn, now - 7200, now - 3600, "heating",
                        quality_score=80)
    # Open cycle: score_cycle() runs only on close, so quality_score is
    # NULL in production. Explicit None overrides the helper's default 80.
    await _insert_cycle(db._conn, now - 3600, None, "heating",
                        quality_score=None)

    coord = _make_coordinator(db)
    method = _live_rollup()
    await method(coord, now)

    row = await _row(db._conn, today, "heating")
    assert row is not None
    assert row["total_duration_s"] >= 7100
    assert row["cycles"] == 2  # closed + open both started today
    assert row["quality_sum"] == 80  # open cycle quality_score is NULL
    coord._refresh_daily_summary_recent.assert_awaited()


@pytest.mark.asyncio
async def test_live_rollup_skips_when_no_open_cycle(tmp_path):
    """R782: no rollup when detector.state != 'running'."""
    db = await _mk_db(tmp_path)
    now = time.time()
    coord = _make_coordinator(db, state="idle")

    method = _live_rollup()
    await method(coord, now)

    coord._refresh_daily_summary_recent.assert_not_called()
    assert coord._last_rollup_today_ts == 0.0


@pytest.mark.asyncio
async def test_live_rollup_respects_15min_throttle(tmp_path):
    """R782: throttle to 15 min between live rollups."""
    db = await _mk_db(tmp_path)
    now = time.time()
    await _insert_cycle(db._conn, now - 3600, None, "heating")
    coord = _make_coordinator(db)
    method = _live_rollup()

    await method(coord, now)
    first_ts = coord._last_rollup_today_ts
    assert first_ts == now

    await method(coord, now + 60)
    assert coord._last_rollup_today_ts == first_ts

    await method(coord, now + 901)
    assert coord._last_rollup_today_ts == now + 901


@pytest.mark.asyncio
async def test_live_rollup_skips_when_option_disabled(tmp_path):
    """R782: honour OPTION_DAILY_SUMMARY_LIVE_ENABLED == False."""
    db = await _mk_db(tmp_path)
    now = time.time()
    coord = _make_coordinator(db)
    coord.options = {OPTION_DAILY_SUMMARY_LIVE_ENABLED: False}

    method = _live_rollup()
    await method(coord, now)

    coord._refresh_daily_summary_recent.assert_not_called()
    assert coord._last_rollup_today_ts == 0.0

# --- Coverage: guard branches ------------------------------------------------


@pytest.mark.asyncio
async def test_live_rollup_returns_when_db_is_none():
    """R782: db is None -> early return (defensive)."""
    now = time.time()
    coord = _make_coordinator(db=None)

    method = _live_rollup()
    await method(coord, now)

    coord._refresh_daily_summary_recent.assert_not_called()
    assert coord._last_rollup_today_ts == 0.0


@pytest.mark.asyncio
async def test_live_rollup_returns_when_detector_is_none(tmp_path):
    """R782: detector is None -> early return (defensive)."""
    db = await _mk_db(tmp_path)
    now = time.time()
    coord = SimpleNamespace(
        db=db,
        options={},
        detector=None,
        _last_rollup_today_ts=0.0,
        _refresh_daily_summary_recent=AsyncMock(),
    )

    method = _live_rollup()
    await method(coord, now)

    coord._refresh_daily_summary_recent.assert_not_called()
    assert coord._last_rollup_today_ts == 0.0


@pytest.mark.asyncio
async def test_live_rollup_swallows_db_exception(tmp_path):
    """R782: async_rollup_day raises -> logged, no refresh, no crash."""
    now = time.time()
    db = AsyncMock()
    db.async_rollup_day = AsyncMock(side_effect=RuntimeError("db down"))
    coord = _make_coordinator(db)
    coord._last_rollup_today_ts = 0.0

    method = _live_rollup()
    await method(coord, now)

    # Timestamp updated before try (throttle consumed even on error)
    assert coord._last_rollup_today_ts == now
    # refresh must NOT run after failure
    coord._refresh_daily_summary_recent.assert_not_called()


@pytest.mark.asyncio
async def test_live_rollup_skips_refresh_when_helper_missing(tmp_path):
    """R782: coordinator without _refresh_daily_summary_recent -> skip gracefully."""
    db = await _mk_db(tmp_path)
    now = time.time()
    today = time.strftime("%Y-%m-%d", time.localtime(now))
    await _insert_cycle(db._conn, now - 3600, None, "heating",
                        quality_score=None)

    # No _refresh_daily_summary_recent attribute at all
    coord = SimpleNamespace(
        db=db,
        options={},
        detector=SimpleNamespace(state="running"),
        _last_rollup_today_ts=0.0,
    )

    method = _live_rollup()
    await method(coord, now)

    row = await _row(db._conn, today, "heating")
    assert row is not None
    assert row["total_duration_s"] >= 3500
