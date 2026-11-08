"""v1.20.1: R709 (start-day attribution) + R710 (transient exclusion).

Prod evidence (issue #292):
- prod-2 (v1.19.x) + prod-3 (v1.20.0): +1 cycle per cross-midnight day
- dmin=29s from transient LWT-sampling pulses on every day

Fix scope (R689 preserved):
- cycles, quality_sum, buh_count, defrost_count, dt_max_sum, rps_sum,
  duration_min, duration_max: start-day only, non-transient only
- total_duration_s: pro-rata overlap (v1.19.7 #260, unchanged)
- New transient_count column tracks excluded pulses
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB


async def _mk_db(tmp_path, name="test.db"):
    db = CycleDB(str(tmp_path / name))
    await db.async_open()
    await db.async_initialize()
    return db


def _ts(y, mo, d, h=0, mi=0, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=UTC).timestamp()


async def _ins(conn, start, end, mode="heating", **kw):
    dur = int(end - start)
    await conn.execute(
        "INSERT INTO cycles "
        "(start_ts, end_ts, duration_s, mode, is_transient, "
        " is_reconstructed, quality_score, dT_max, rps_avg, "
        " buh_used, defrost_used, thermal_kw_avg) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            start,
            end,
            dur,
            mode,
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


async def _row(conn, day, mode="heating"):
    cur = await conn.execute(
        "SELECT * FROM daily_summary WHERE day=? AND mode=?",
        (day, mode),
    )
    r = await cur.fetchone()
    await cur.close()
    return r


# --- R709: start-day attribution ---------------------------------------------


@pytest.mark.asyncio
async def test_cross_midnight_cycles_counted_start_day_only(tmp_path):
    """R709: cycle starting Nov 5 ending Nov 6 counts only on Nov 5."""
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        await _ins(conn, _ts(2026, 11, 5, 22, 0), _ts(2026, 11, 6, 2, 0))
        await _ins(conn, _ts(2026, 11, 6, 10, 0), _ts(2026, 11, 6, 11, 0))
        await conn.commit()
        await db.async_rollup_day("2026-11-05")
        await db.async_rollup_day("2026-11-06")

        r5 = await _row(conn, "2026-11-05")
        r6 = await _row(conn, "2026-11-06")

        assert r5["cycles"] == 1, f"Nov 5 cycles={r5['cycles']} (expected 1: start-day only)"
        assert r6["cycles"] == 1, (
            f"Nov 6 cycles={r6['cycles']} (expected 1: cross-midnight belongs to Nov 5)"
        )
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_cross_midnight_quality_attributed_to_start_day(tmp_path):
    """R709: cross-midnight quality_score only on start-day."""
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        await _ins(
            conn,
            _ts(2026, 11, 5, 22, 0),
            _ts(2026, 11, 6, 2, 0),
            quality_score=100,
        )
        await _ins(
            conn,
            _ts(2026, 11, 5, 10, 0),
            _ts(2026, 11, 5, 11, 0),
            quality_score=50,
        )
        await conn.commit()
        await db.async_rollup_day("2026-11-05")
        await db.async_rollup_day("2026-11-06")

        r5 = await _row(conn, "2026-11-05")
        r6 = await _row(conn, "2026-11-06")

        assert r5["quality_sum"] == 150, (
            f"Nov 5 quality_sum={r5['quality_sum']} (expected 150: 100+50)"
        )
        if r6 is not None:
            assert r6["quality_sum"] == 0, (
                f"Nov 6 quality_sum={r6['quality_sum']} (cross-midnight belongs to Nov 5)"
            )
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_cross_midnight_buh_count_start_day_only(tmp_path):
    """R709: cross-midnight buh_used only on start-day."""
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        await _ins(
            conn,
            _ts(2026, 11, 5, 22, 0),
            _ts(2026, 11, 6, 2, 0),
            buh_used=1,
        )
        await conn.commit()
        await db.async_rollup_day("2026-11-05")
        await db.async_rollup_day("2026-11-06")

        r5 = await _row(conn, "2026-11-05")
        r6 = await _row(conn, "2026-11-06")

        assert r5["buh_count"] == 1, f"Nov 5 buh_count={r5['buh_count']}"
        if r6 is not None:
            assert r6["buh_count"] == 0, (
                f"Nov 6 buh_count={r6['buh_count']} (cross-midnight belongs to Nov 5)"
            )
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# --- R710: transient exclusion ----------------------------------------------


@pytest.mark.asyncio
async def test_transient_excluded_from_cycles_count(tmp_path):
    """R710: is_transient=1 not in daily_summary.cycles."""
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        await _ins(conn, _ts(2026, 11, 5, 10, 0), _ts(2026, 11, 5, 11, 0))
        await _ins(
            conn,
            _ts(2026, 11, 5, 12, 0),
            _ts(2026, 11, 5, 12, 0) + 29,
            is_transient=1,
        )
        await conn.commit()
        await db.async_rollup_day("2026-11-05")

        r = await _row(conn, "2026-11-05")
        assert r["cycles"] == 1, f"cycles={r['cycles']} (expected 1: transient excluded)"
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_transient_excluded_from_duration_min(tmp_path):
    """R710: duration_min from non-transient only."""
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        await _ins(conn, _ts(2026, 11, 5, 10, 0), _ts(2026, 11, 5, 11, 0))
        await _ins(
            conn,
            _ts(2026, 11, 5, 12, 0),
            _ts(2026, 11, 5, 12, 0) + 29,
            is_transient=1,
        )
        await conn.commit()
        await db.async_rollup_day("2026-11-05")

        r = await _row(conn, "2026-11-05")
        assert r["duration_min"] == 3600, (
            f"duration_min={r['duration_min']} (expected 3600s, transient excluded)"
        )
        assert r["duration_max"] == 3600
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_transient_excluded_from_quality_sum(tmp_path):
    """R710: transient quality_score not in quality_sum."""
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        await _ins(
            conn,
            _ts(2026, 11, 5, 10, 0),
            _ts(2026, 11, 5, 11, 0),
            quality_score=80,
        )
        await _ins(
            conn,
            _ts(2026, 11, 5, 12, 0),
            _ts(2026, 11, 5, 12, 0) + 29,
            quality_score=10,
            is_transient=1,
        )
        await conn.commit()
        await db.async_rollup_day("2026-11-05")

        r = await _row(conn, "2026-11-05")
        assert r["quality_sum"] == 80, (
            f"quality_sum={r['quality_sum']} (expected 80: transient excluded)"
        )
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_transient_count_column_populated(tmp_path):
    """R710: new transient_count column tracks excluded pulses."""
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        await _ins(conn, _ts(2026, 11, 5, 10, 0), _ts(2026, 11, 5, 11, 0))
        await _ins(
            conn,
            _ts(2026, 11, 5, 12, 0),
            _ts(2026, 11, 5, 12, 0) + 29,
            is_transient=1,
        )
        await _ins(
            conn,
            _ts(2026, 11, 5, 14, 0),
            _ts(2026, 11, 5, 14, 0) + 29,
            is_transient=1,
        )
        await conn.commit()
        await db.async_rollup_day("2026-11-05")

        r = await _row(conn, "2026-11-05")
        assert r["transient_count"] == 2, f"transient_count={r['transient_count']} (expected 2)"
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# --- Regression: v1.19.7 #260 pro-rata must stay ----------------------------


@pytest.mark.asyncio
async def test_pro_rata_duration_still_works(tmp_path):
    """v1.19.7 #260: total_duration_s must remain pro-rata."""
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        await _ins(
            conn,
            _ts(2026, 10, 26, 13, 31),
            _ts(2026, 10, 27, 5, 46),
        )
        await conn.commit()
        await db.async_rollup_day("2026-10-26")
        await db.async_rollup_day("2026-10-27")

        r26 = await _row(conn, "2026-10-26")
        r27 = await _row(conn, "2026-10-27")

        oct26 = r26["total_duration_s"]
        oct27 = r27["total_duration_s"]

        assert 9.5 * 3600 <= oct26 <= 11.5 * 3600, f"Oct26 {oct26 / 3600:.2f}h != ~10.5h"
        assert 5.0 * 3600 <= oct27 <= 6.5 * 3600, f"Oct27 {oct27 / 3600:.2f}h != ~5.75h"
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# --- v29 migration -----------------------------------------------------------


@pytest.mark.asyncio
async def test_v29_migration_rebuilds_and_is_idempotent(tmp_path):
    """v29: migration rebuilds daily_summary from cycles + is idempotent."""
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        await _ins(conn, _ts(2026, 11, 5, 22, 0), _ts(2026, 11, 6, 2, 0))
        await _ins(
            conn,
            _ts(2026, 11, 5, 12, 0),
            _ts(2026, 11, 5, 12, 0) + 29,
            is_transient=1,
        )
        await conn.commit()

        # Pre-populate daily_summary with "corrupt" pre-fix values
        await conn.execute(
            "INSERT INTO daily_summary "
            "(day, mode, cycles, total_duration_s, duration_min, duration_max, "
            " quality_sum, dt_max_sum, rps_sum, buh_count, defrost_count, "
            " transient_count, updated_ts) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("2026-11-05", "heating", 99, 99999, 29, 99999, 999, 99.0, 99.0, 99, 99, 0, 0.0),
        )
        await conn.execute(
            "INSERT INTO daily_summary "
            "(day, mode, cycles, total_duration_s, duration_min, duration_max, "
            " quality_sum, dt_max_sum, rps_sum, buh_count, defrost_count, "
            " transient_count, updated_ts) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("2026-11-06", "heating", 88, 88888, 88, 88888, 888, 88.0, 88.0, 88, 88, 0, 0.0),
        )
        await conn.commit()

        stats1 = await db.async_migrate_to_v29()
        assert stats1.get("completed") is True

        r5 = await _row(conn, "2026-11-05")
        r6 = await _row(conn, "2026-11-06")

        assert r5["cycles"] == 1, f"v29 Nov 5 cycles={r5['cycles']}"
        assert r5["transient_count"] == 1, f"v29 Nov 5 transient_count={r5['transient_count']}"
        if r6 is not None:
            assert r6["cycles"] == 0, f"v29 Nov 6 cycles={r6['cycles']}"

        # Idempotent
        stats2 = await db.async_migrate_to_v29()
        assert stats2.get("skipped") == 1, "v29 not idempotent"
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_v29_migration_empty_db(tmp_path):
    """v29: empty cycles table completes with 0 days rebuilt."""
    db = await _mk_db(tmp_path)
    try:
        stats = await db.async_migrate_to_v29()
        assert stats.get("days_rebuilt") == 0
        assert stats.get("completed") is True
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_v29_alter_adds_transient_count_to_old_schema(tmp_path):
    """v29: ALTER adds transient_count to pre-v29 daily_summary."""
    import sqlite3

    db_path = str(tmp_path / "alter.db")
    db = CycleDB(db_path)
    await db.async_open()
    await db.async_initialize()
    await db.async_close()
    await asyncio.sleep(0.05)

    raw = sqlite3.connect(db_path)
    raw.executescript(
        "DROP TABLE IF EXISTS daily_summary; "
        "CREATE TABLE daily_summary ("
        "day TEXT NOT NULL, mode TEXT NOT NULL, "
        "cycles INTEGER NOT NULL DEFAULT 0, "
        "total_duration_s INTEGER NOT NULL DEFAULT 0, "
        "duration_min INTEGER, duration_max INTEGER, "
        "quality_sum INTEGER NOT NULL DEFAULT 0, "
        "dt_max_sum REAL NOT NULL DEFAULT 0, "
        "rps_sum REAL NOT NULL DEFAULT 0, "
        "buh_count INTEGER NOT NULL DEFAULT 0, "
        "defrost_count INTEGER NOT NULL DEFAULT 0, "
        "updated_ts REAL NOT NULL, "
        "PRIMARY KEY (day, mode));"
    )
    raw.commit()
    raw.close()

    db2 = CycleDB(db_path)
    await db2.async_open()
    await db2.async_initialize()
    try:
        conn = db2._require()
        cur = await conn.execute("PRAGMA table_info(daily_summary)")
        cols = {row[1] for row in await cur.fetchall()}
        await cur.close()
        assert "transient_count" in cols, "v29 ALTER failed to add transient_count"
    finally:
        await db2.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_transient_spanning_midnight_not_counted_on_end_day(tmp_path):
    """Coverage L2215->2217: transient starting on previous day is
    excluded from BOTH days (starts_on_day=False branch + continue)."""
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        # Transient starts 2026-11-05 23:59:45 ends 2026-11-06 00:00:15
        await _ins(
            conn,
            _ts(2026, 11, 5, 23, 59, 45),
            _ts(2026, 11, 6, 0, 0, 15),
            is_transient=1,
        )
        await conn.commit()
        await db.async_rollup_day("2026-11-06")

        r6 = await _row(conn, "2026-11-06")
        # Row may be absent OR have transient_count=0. If present:
        if r6 is not None:
            assert r6["transient_count"] == 0, (
                f"transient_count={r6['transient_count']} "
                f"(cross-midnight transient belongs to Nov 5)"
            )
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_v29_skips_null_start_day(tmp_path):
    """Coverage L2051: date(start_ts) returning NULL is skipped.

    SQLite date() returns NULL for start_ts >= 1e20 (year ~3 trillion).
    The schema accepts REAL start_ts; the guard protects v29 rebuild
    against rows with unparseable dates. Verify: rebuild does not
    crash on such a row, and does not attempt to roll up a NULL day.
    """
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        # Valid cycle on Nov 5 -> rollup will succeed
        await _ins(
            conn, _ts(2026, 11, 5, 10, 0), _ts(2026, 11, 5, 11, 0)
        )
        # Invalid cycle with start_ts=1e20 -> date() returns NULL
        await conn.execute(
            "INSERT INTO cycles (start_ts, end_ts, duration_s, mode, is_transient) "
            "VALUES (?, ?, ?, ?, ?)",
            (1e20, 1e20 + 3600, 3600, "heating", 0),
        )
        await conn.commit()

        stats = await db.async_migrate_to_v29()
        assert stats.get("completed") is True
        # 2 distinct days returned by query: NULL + "2026-11-05"
        # The NULL row hits `if not day: continue`, so only 1 day rebuilt
        assert stats.get("days_rebuilt") == 1, (
            f"days_rebuilt={stats.get('days_rebuilt')} (expected 1: NULL day skipped)"
        )
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)
