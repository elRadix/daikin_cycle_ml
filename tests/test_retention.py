"""Tests for retention / daily_summary (Batch 11b-1)."""
from __future__ import annotations

import time

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB


@pytest.fixture
async def db(tmp_path):
    d = CycleDB(tmp_path / "ret.db")
    await d.async_open()
    await d.async_initialize()
    try:
        yield d
    finally:
        await d.async_close()


def _rec(days_ago: float, mode: str = "Heating", quality: int = 80) -> dict:
    end = time.time() - days_ago * 86400.0
    return {
        "start_ts": end - 3600,
        "end_ts": end,
        "duration_s": 3600,
        "mode": mode,
        "dT_max": 7.0,
        "dT_avg": 4.5,
        "rps_max": 60,
        "rps_avg": 45.0,
        "outdoor_temp": 8.0,
        "buh_used": 0,
        "defrost_used": 0,
        "quality_score": quality,
    }


# ---------- schema ----------

async def test_daily_summary_table_exists(db):
    assert await db.async_count("daily_summary") == 0


async def test_count_rejects_unknown_table(db):
    with pytest.raises(ValueError):
        await db.async_count("nonexistent")


# ---------- rollup ----------

async def test_maintenance_no_data(db):
    out = await db.async_run_maintenance()
    assert out["cycles_rolled_up"] == 0
    assert out["cycles_deleted"] == 0


async def test_maintenance_rolls_up_old_cycles(db):
    await db.async_insert_cycle(_rec(100))
    await db.async_insert_cycle(_rec(100, mode="DHW"))
    out = await db.async_run_maintenance(cycle_retention_days=90)
    assert out["cycles_rolled_up"] == 2
    assert out["cycles_deleted"] == 2
    assert out["days_rolled_up"] == 2  # (day, Heating) + (day, DHW)


async def test_maintenance_keeps_recent(db):
    await db.async_insert_cycle(_rec(100))
    await db.async_insert_cycle(_rec(10))
    out = await db.async_run_maintenance(cycle_retention_days=90)
    assert out["cycles_deleted"] == 1
    assert await db.async_count("cycles") == 1


async def test_maintenance_prunes_orphan_features(db):
    cid = await db.async_insert_cycle(_rec(100))
    await db.async_insert_features(cid, [1.0, 2.0])
    await db.async_run_maintenance(cycle_retention_days=90)
    assert await db.async_count("features") == 0


async def test_maintenance_keeps_recent_features(db):
    cid = await db.async_insert_cycle(_rec(10))
    await db.async_insert_features(cid, [1.0])
    await db.async_run_maintenance(cycle_retention_days=90)
    assert await db.async_count("features") == 1


async def test_maintenance_prunes_old_alerts(db):
    old_ts = time.time() - 100 * 86400.0
    await db.async_insert_alert("p", "w", "old", ts=old_ts)
    await db.async_insert_alert("q", "w", "new", ts=time.time())
    out = await db.async_run_maintenance(alert_retention_days=30)
    assert out["alerts_deleted"] == 1
    assert await db.async_count("alerts") == 1


async def test_maintenance_idempotent(db):
    await db.async_insert_cycle(_rec(100))
    out1 = await db.async_run_maintenance(cycle_retention_days=90)
    out2 = await db.async_run_maintenance(cycle_retention_days=90)
    assert out1["cycles_deleted"] == 1
    assert out2["cycles_deleted"] == 0
    # first rolled up 1 cycle, second has nothing to roll
    assert out1["cycles_rolled_up"] == 1
    assert out2["cycles_rolled_up"] == 0


@pytest.mark.expected_lingering_tasks(True)
@pytest.mark.expected_lingering_timers(True)
async def test_maintenance_no_vacuum_when_disabled(db):
    await db.async_insert_cycle(_rec(100))
    out = await db.async_run_maintenance(
        cycle_retention_days=90, vacuum=False
    )
    assert out["cycles_deleted"] == 1


# ---------- daily_summary query ----------

async def test_daily_summary_empty(db):
    assert await db.async_daily_summary() == []


async def test_daily_summary_after_rollup(db):
    await db.async_insert_cycle(_rec(100, quality=80))
    await db.async_insert_cycle(_rec(100, quality=60))
    await db.async_run_maintenance(cycle_retention_days=90)
    rows = await db.async_daily_summary(days=365)
    assert len(rows) >= 1
    r = rows[0]
    assert r["cycles"] == 2
    assert r["quality_avg"] == 70.0
    assert r["duration_avg"] == 3600.0


async def test_daily_summary_mode_filter(db):
    await db.async_insert_cycle(_rec(100, mode="Heating"))
    await db.async_insert_cycle(_rec(100, mode="DHW"))
    await db.async_run_maintenance(cycle_retention_days=90)
    heat = await db.async_daily_summary(days=365, mode="Heating")
    dhw = await db.async_daily_summary(days=365, mode="DHW")
    assert all(r["mode"] == "Heating" for r in heat)
    assert all(r["mode"] == "DHW" for r in dhw)


async def test_daily_summary_respects_days_window(db):
    await db.async_insert_cycle(_rec(100))
    await db.async_run_maintenance(cycle_retention_days=90)
    # 100-day old rollup, ask for last 30 days -> nothing
    rows = await db.async_daily_summary(days=30)
    assert rows == []


async def test_vacuum_returns_bool(db):
    result = await db.async_vacuum()
    assert isinstance(result, bool)


async def test_maintenance_survives_vacuum(db):
    """After maintenance with vacuum, queries still work."""
    await db.async_insert_cycle(_rec(100))
    await db.async_run_maintenance(cycle_retention_days=90)
    # If VACUUM broke the connection, these would raise
    assert await db.async_count("cycles") == 0
    rows = await db.async_daily_summary(days=365)
    assert isinstance(rows, list)
