"""Tests for async_rollup_day (v1.7.0, #42)."""
from __future__ import annotations

import asyncio
import time

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB


@pytest.fixture
async def db(tmp_path):
    d = CycleDB(tmp_path / "roll.db")
    await d.async_open()
    await d.async_initialize()
    try:
        yield d
    finally:
        await d.async_close()
        # R51: aiosqlite worker thread can outlive close()
        await asyncio.sleep(0.05)


async def _insert_cycle(
    db: CycleDB,
    *,
    end_ts: float,
    mode: str | None,
    duration_s: float | None = 3600.0,
    dT_max: float | None = 4.5,
    rps_avg: float | None = 24.0,
    quality_score: float | None = 80.0,
    buh_used: int = 0,
    defrost_used: int = 0,
) -> None:
    conn = db._require()
    await conn.execute(
        "INSERT INTO cycles "
        "(start_ts, end_ts, duration_s, mode, dT_max, rps_avg, "
        "quality_score, buh_used, defrost_used) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (
            (end_ts - (duration_s or 0.0)),
            end_ts,
            duration_s,
            mode,
            dT_max,
            rps_avg,
            quality_score,
            buh_used,
            defrost_used,
        ),
    )
    await conn.commit()


def _day(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts))


async def test_rollup_day_single_cycle(db):
    today = time.time()
    await _insert_cycle(db, end_ts=today, mode="heating")
    n = await db.async_rollup_day(_day(today))
    assert n == 1
    rows = await db.async_daily_summary(days=1)
    assert len(rows) == 1
    assert rows[0]["cycles"] == 1
    assert rows[0]["mode"] == "heating"


async def test_rollup_day_multiple_modes(db):
    today = time.time()
    await _insert_cycle(db, end_ts=today, mode="heating")
    await _insert_cycle(db, end_ts=today + 60, mode="dhw")
    n = await db.async_rollup_day(_day(today))
    assert n == 2
    rows = await db.async_daily_summary(days=1)
    assert {r["mode"] for r in rows} == {"heating", "dhw"}


async def test_rollup_day_empty(db):
    today = time.time()
    n = await db.async_rollup_day(_day(today))
    assert n == 0
    assert await db.async_daily_summary(days=1) == []


async def test_rollup_day_idempotent(db):
    today = time.time()
    await _insert_cycle(db, end_ts=today, mode="heating")
    await _insert_cycle(db, end_ts=today + 60, mode="heating")
    day = _day(today)
    n1 = await db.async_rollup_day(day)
    n2 = await db.async_rollup_day(day)
    assert n1 == n2 == 1
    rows = await db.async_daily_summary(days=1)
    assert len(rows) == 1
    assert rows[0]["cycles"] == 2


async def test_rollup_day_null_mode_maps_to_unknown(db):
    today = time.time()
    await _insert_cycle(db, end_ts=today, mode=None)
    n = await db.async_rollup_day(_day(today))
    assert n == 1
    rows = await db.async_daily_summary(days=1)
    assert rows[0]["mode"] == "unknown"


async def test_rollup_day_invalid_day_string(db):
    n = await db.async_rollup_day("not-a-date")
    assert n == 0


async def test_rollup_day_modes_filter(db):
    today = time.time()
    await _insert_cycle(db, end_ts=today, mode="heating")
    await _insert_cycle(db, end_ts=today + 60, mode="dhw")
    n = await db.async_rollup_day(_day(today), modes=("heating",))
    assert n == 1
    rows = await db.async_daily_summary(days=1)
    assert {r["mode"] for r in rows} == {"heating"}


async def test_rollup_day_null_metrics(db):
    today = time.time()
    await _insert_cycle(
        db,
        end_ts=today,
        mode="heating",
        duration_s=None,
        dT_max=None,
        rps_avg=None,
        quality_score=None,
    )
    n = await db.async_rollup_day(_day(today))
    assert n == 1
    rows = await db.async_daily_summary(days=1)
    assert rows[0]["cycles"] == 1


async def test_rollup_day_buh_defrost_counted(db):
    today = time.time()
    await _insert_cycle(db, end_ts=today, mode="heating", buh_used=1, defrost_used=1)
    await _insert_cycle(db, end_ts=today + 60, mode="heating", buh_used=0, defrost_used=0)
    n = await db.async_rollup_day(_day(today))
    assert n == 1
    rows = await db.async_daily_summary(days=1)
    assert rows[0]["buh_count"] == 1
    assert rows[0]["defrost_count"] == 1


# ---------- commit 2: maintenance integration ----------

async def test_maintenance_rolls_up_before_prune(db):
    day_ts = time.time() - 100 * 86400.0
    await _insert_cycle(db, end_ts=day_ts, mode="heating")
    await db.async_run_maintenance(
        cycle_retention_days=90, vacuum=False,
    )
    assert await db.async_count("cycles") == 0
    rows = await db.async_daily_summary(days=365)
    assert len(rows) == 1
    assert rows[0]["cycles"] == 1


async def test_maintenance_replace_semantics_no_double_count(db):
    day_ts = time.time() - 100 * 86400.0
    await _insert_cycle(db, end_ts=day_ts, mode="heating")
    day = time.strftime("%Y-%m-%d", time.localtime(day_ts))
    await db.async_rollup_day(day)
    await db.async_run_maintenance(
        cycle_retention_days=90, vacuum=False,
    )
    rows = await db.async_daily_summary(days=365)
    assert len(rows) == 1
    assert rows[0]["cycles"] == 1


async def test_maintenance_return_shape_preserved(db):
    day_ts = time.time() - 100 * 86400.0
    await _insert_cycle(db, end_ts=day_ts, mode="heating")
    await _insert_cycle(db, end_ts=day_ts + 60, mode="dhw")
    out = await db.async_run_maintenance(
        cycle_retention_days=90, vacuum=False,
    )
    assert out["days_rolled_up"] == 2
    assert out["cycles_rolled_up"] == 2
    assert out["cycles_deleted"] == 2
