"""v1.12.5 #133: _collect_cycle_averages uses real DB COUNT(*)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)
from custom_components.daikin_cycle_ml.storage.db import CycleDB


def _bare():
    c = object.__new__(DaikinCycleMLCoordinator)
    c._cycle_lwt_sum = 0.0
    c._cycle_lwt_count = 0
    c._cycle_indoor_sum = 0.0
    c._cycle_indoor_count = 0
    c._cycle_cop_w_sum = 0.0
    c._cycle_cop_weight_sum = 0.0
    c._cycle_cop_sq_w_sum = 0.0
    c._cycle_cop_count = 0
    c.indoor_temp_entity = None
    c.db = None
    return c


async def _seed_samples(db, rows):
    conn = db._require()
    for ts, cop, mode, artifact in rows:
        await conn.execute(
            "INSERT INTO cop_samples (ts, cop, mode, is_transition_artifact) "
            "VALUES (?, ?, ?, ?)",
            (ts, cop, mode, artifact),
        )
    await conn.commit()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_real_db_count_heating(tmp_path):
    db = CycleDB(str(tmp_path / "t.db"))
    await db.async_open()
    await db.async_initialize()
    await _seed_samples(db, [
        (100.0, 3.0, "heating", 0),
        (200.0, 3.2, "heating", 0),
        (300.0, 3.1, "heating", 0),
    ])
    c = _bare()
    c.db = db
    record = {
        "start_ts": 50.0, "end_ts": 400.0,
        "duration_s": 350.0, "mode": "heating",
    }
    await c._collect_cycle_averages(record)
    assert record["cop_sample_count"] == 3
    assert record["cop_confidence"] == "low"
    await db.async_close()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_real_db_count_dhw(tmp_path):
    db = CycleDB(str(tmp_path / "t.db"))
    await db.async_open()
    await db.async_initialize()
    await _seed_samples(db, [
        (100.0, 2.5, "dhw", 0) for _ in range(7)
    ] + [(float(i * 10), 2.5, "dhw", 0) for i in range(7)])
    c = _bare()
    c.db = db
    record = {
        "start_ts": 0.0, "end_ts": 1000.0,
        "duration_s": 1000.0, "mode": "dhw",
    }
    await c._collect_cycle_averages(record)
    assert record["cop_sample_count"] == 14
    assert record["cop_confidence"] == "high"
    await db.async_close()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_mode_filter_excludes_other_mode(tmp_path):
    db = CycleDB(str(tmp_path / "t.db"))
    await db.async_open()
    await db.async_initialize()
    await _seed_samples(db, [
        (10.0, 3.0, "heating", 0),
        (20.0, 4.0, "dhw", 0),
        (30.0, 5.0, "heating", 0),
        (40.0, 6.0, "dhw", 0),
        (50.0, 7.0, "heating", 0),
    ])
    c = _bare()
    c.db = db
    record = {
        "start_ts": 0.0, "end_ts": 100.0,
        "duration_s": 100.0, "mode": "heating",
    }
    await c._collect_cycle_averages(record)
    assert record["cop_sample_count"] == 3
    await db.async_close()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_pw_avg_wins_over_db_avg():
    c = _bare()
    c._cycle_cop_count = 10
    c._cycle_cop_w_sum = 30.0
    c._cycle_cop_weight_sum = 10.0
    c._cycle_cop_sq_w_sum = 90.0
    c.db = MagicMock()
    c.db._sample_aggregates = AsyncMock(return_value=(99.0, 20))
    record = {
        "start_ts": 1.0, "end_ts": 2.0,
        "duration_s": 600.0, "mode": "heating",
    }
    await c._collect_cycle_averages(record)
    assert record["cop_avg"] == 3.0
    assert record["cop_sample_count"] == 20
    assert record["cop_confidence"] == "high"


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_no_ticks_uses_db_avg():
    c = _bare()
    c.db = MagicMock()
    c.db._sample_aggregates = AsyncMock(return_value=(4.2, 8))
    record = {
        "start_ts": 1.0, "end_ts": 2.0,
        "duration_s": 600.0, "mode": "heating",
    }
    await c._collect_cycle_averages(record)
    assert record["cop_avg"] == 4.2
    assert record["cop_sample_count"] == 8
    assert record["cop_sample_stdev"] is None
    assert record["cop_confidence"] == "medium"


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_no_ticks_no_db_returns_none():
    c = _bare()
    c.db = None
    record = {
        "start_ts": 1.0, "end_ts": 2.0,
        "duration_s": 600.0, "mode": "heating",
    }
    await c._collect_cycle_averages(record)
    assert record["cop_avg"] is None
    assert record["cop_sample_count"] is None
    assert record["cop_confidence"] == "none"


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_db_none_falls_back_to_tick():
    c = _bare()
    c._cycle_cop_count = 5
    c._cycle_cop_w_sum = 15.0
    c._cycle_cop_weight_sum = 5.0
    c._cycle_cop_sq_w_sum = 45.0
    c.db = None
    record = {
        "start_ts": 1.0, "end_ts": 2.0,
        "duration_s": 600.0, "mode": "heating",
    }
    await c._collect_cycle_averages(record)
    assert record["cop_sample_count"] == 5
    assert record["cop_confidence"] == "low"


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_db_query_raises_falls_back():
    c = _bare()
    c._cycle_cop_count = 5
    c._cycle_cop_w_sum = 15.0
    c._cycle_cop_weight_sum = 5.0
    c._cycle_cop_sq_w_sum = 45.0
    c.db = MagicMock()
    c.db._sample_aggregates = AsyncMock(side_effect=RuntimeError("boom"))
    record = {
        "start_ts": 1.0, "end_ts": 2.0,
        "duration_s": 600.0, "mode": "heating",
    }
    await c._collect_cycle_averages(record)
    assert record["cop_sample_count"] == 5
    assert record["cop_confidence"] == "low"


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_mode_none_skips_query():
    c = _bare()
    c._cycle_cop_count = 5
    c._cycle_cop_w_sum = 15.0
    c._cycle_cop_weight_sum = 5.0
    c._cycle_cop_sq_w_sum = 45.0
    c.db = MagicMock()
    c.db._sample_aggregates = AsyncMock(return_value=(4.0, 20))
    record = {"start_ts": 1.0, "end_ts": 2.0, "duration_s": 600.0}
    await c._collect_cycle_averages(record)
    assert record["cop_sample_count"] == 5
    c.db._sample_aggregates.assert_not_called()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_start_ts_none_skips_query():
    c = _bare()
    c._cycle_cop_count = 5
    c._cycle_cop_w_sum = 15.0
    c._cycle_cop_weight_sum = 5.0
    c._cycle_cop_sq_w_sum = 45.0
    c.db = MagicMock()
    c.db._sample_aggregates = AsyncMock(return_value=(4.0, 20))
    record = {"duration_s": 600.0, "mode": "heating"}
    await c._collect_cycle_averages(record)
    assert record["cop_sample_count"] == 5
    c.db._sample_aggregates.assert_not_called()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_zero_db_count_sets_none():
    c = _bare()
    c.db = MagicMock()
    c.db._sample_aggregates = AsyncMock(return_value=(None, 0))
    record = {
        "start_ts": 1.0, "end_ts": 2.0,
        "duration_s": 600.0, "mode": "heating",
    }
    await c._collect_cycle_averages(record)
    assert record["cop_sample_count"] is None
    assert record["cop_confidence"] == "none"


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_confidence_matches_db_count_tier(tmp_path):
    db = CycleDB(str(tmp_path / "t.db"))
    await db.async_open()
    await db.async_initialize()
    await _seed_samples(db, [
        (float(10 + i), 3.0, "heating", 0) for i in range(15)
    ])
    c = _bare()
    c.db = db
    record = {
        "start_ts": 0.0, "end_ts": 1000.0,
        "duration_s": 1000.0, "mode": "heating",
    }
    await c._collect_cycle_averages(record)
    assert record["cop_sample_count"] == 15
    assert record["cop_confidence"] == "high"
    await db.async_close()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_end_ts_none_skips_query():
    c = _bare()
    c._cycle_cop_count = 5
    c._cycle_cop_w_sum = 15.0
    c._cycle_cop_weight_sum = 5.0
    c._cycle_cop_sq_w_sum = 45.0
    c.db = MagicMock()
    c.db._sample_aggregates = AsyncMock(return_value=(4.0, 20))
    record = {"start_ts": 1.0, "duration_s": 600.0, "mode": "heating"}
    await c._collect_cycle_averages(record)
    assert record["cop_sample_count"] == 5
    c.db._sample_aggregates.assert_not_called()
