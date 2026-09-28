"""COV-9: T1 in-cycle COP integration tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import (
    COP_MIN_TICKS,
    DaikinCycleMLCoordinator,
    _cop_confidence,
    _weighted_mean_stdev,
)
from custom_components.daikin_cycle_ml.storage.db import CycleDB


def _bare_coord() -> DaikinCycleMLCoordinator:
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
    c.cop_sensor_entity = "sensor.cop"
    c.power_sensor = None
    c.db = None
    c.hass = MagicMock()
    c.detector = MagicMock()
    c.detector.state = "running"
    return c


def _state(value: str, unit: str = "") -> MagicMock:
    st = MagicMock()
    st.state = value
    st.attributes = {"unit_of_measurement": unit} if unit else {}
    return st


# ---------------- module-level helpers ----------------


def test_cop_confidence_none_below_min():
    assert _cop_confidence(0, 600.0) == "none"
    assert _cop_confidence(3, 600.0) == "none"


def test_cop_confidence_low_duration_none():
    assert _cop_confidence(4, None) == "low"


def test_cop_confidence_low_duration_zero():
    assert _cop_confidence(4, 0.0) == "low"


def test_cop_confidence_high():
    assert _cop_confidence(20, 600.0) == "high"


def test_cop_confidence_low_sparse():
    assert _cop_confidence(5, 600.0) == "low"


def test_weighted_mean_stdev_zero_weight():
    assert _weighted_mean_stdev(0.0, 0.0, 0.0) == (None, None)


def test_weighted_mean_stdev_happy():
    mean, stdev = _weighted_mean_stdev(6.0, 2.0, 18.0)
    assert mean == 3.0
    assert stdev == 0.0


def test_weighted_mean_stdev_negvar_clamped():
    # sq_sum/weight < mean**2 -> float-negative variance -> clamp to 0
    mean, stdev = _weighted_mean_stdev(3.0, 1.0, 8.999999999999999)
    assert mean == 3.0
    assert stdev == 0.0


# ---------------- _accumulate_cycle_samples ----------------


def test_accumulate_cop_tick_weighted():
    c = _bare_coord()
    c.power_sensor = "sensor.power"
    c.hass.states.get = MagicMock(side_effect=[
        _state("3.0"),   # cop
        _state("1500.0", "W"),  # power
    ])
    c._accumulate_cycle_samples({})
    assert c._cycle_cop_count == 1
    assert c._cycle_cop_w_sum == pytest.approx(3.0 * 1500.0)
    assert c._cycle_cop_weight_sum == pytest.approx(1500.0)


def test_accumulate_cop_tick_unweighted_no_power():
    c = _bare_coord()
    c.power_sensor = None
    c.hass.states.get = MagicMock(return_value=_state("3.0"))
    c._accumulate_cycle_samples({})
    assert c._cycle_cop_count == 1
    assert c._cycle_cop_weight_sum == pytest.approx(1.0)


def test_accumulate_cop_tick_unweighted_zero_power():
    c = _bare_coord()
    c.power_sensor = "sensor.power"
    c.hass.states.get = MagicMock(side_effect=[
        _state("3.0"),
        _state("0.0", "W"),
    ])
    c._accumulate_cycle_samples({})
    assert c._cycle_cop_count == 1
    assert c._cycle_cop_weight_sum == pytest.approx(1.0)


def test_accumulate_cop_tick_cop_zero_skipped():
    c = _bare_coord()
    c.hass.states.get = MagicMock(return_value=_state("0.0"))
    c._accumulate_cycle_samples({})
    assert c._cycle_cop_count == 0


def test_accumulate_cop_tick_cop_none_skipped():
    c = _bare_coord()
    c.hass.states.get = MagicMock(return_value=None)
    c._accumulate_cycle_samples({})
    assert c._cycle_cop_count == 0


# ---------------- _collect_cycle_averages ----------------


async def test_collect_cycle_averages_memory_used():
    c = _bare_coord()
    c._cycle_cop_w_sum = 30.0
    c._cycle_cop_weight_sum = 10.0
    c._cycle_cop_sq_w_sum = 90.0
    c._cycle_cop_count = 10
    c.db = MagicMock()
    c.db.async_avg_cop_between = AsyncMock(return_value=99.0)
    record = {"start_ts": 1.0, "end_ts": 2.0, "duration_s": 600.0}
    cop_avg, _, _ = await c._collect_cycle_averages(record)
    assert cop_avg == 3.0
    c.db.async_avg_cop_between.assert_not_awaited()
    assert record["cop_avg"] == 3.0
    assert record["cop_sample_count"] == 10
    assert record["cop_sample_stdev"] == 0.0
    assert record["cop_confidence"] == "high"
    assert c._cycle_cop_count == 0  # reset


async def test_collect_cycle_averages_fallback_used():
    c = _bare_coord()
    c._cycle_cop_count = 1
    c._cycle_cop_w_sum = 3.0
    c._cycle_cop_weight_sum = 1.0
    c._cycle_cop_sq_w_sum = 9.0
    c.db = MagicMock()
    c.db.async_avg_cop_between = AsyncMock(return_value=4.5)
    record = {"start_ts": 1.0, "end_ts": 2.0, "duration_s": 600.0}
    cop_avg, _, _ = await c._collect_cycle_averages(record)
    assert cop_avg == 4.5
    c.db.async_avg_cop_between.assert_awaited_once()
    assert record["cop_confidence"] == "none"


async def test_collect_cycle_averages_fallback_none_keeps_memory():
    c = _bare_coord()
    c._cycle_cop_count = 1
    c._cycle_cop_w_sum = 3.0
    c._cycle_cop_weight_sum = 1.0
    c._cycle_cop_sq_w_sum = 9.0
    c.db = MagicMock()
    c.db.async_avg_cop_between = AsyncMock(return_value=None)
    record = {"start_ts": 1.0, "end_ts": 2.0, "duration_s": 600.0}
    cop_avg, _, _ = await c._collect_cycle_averages(record)
    assert cop_avg == 3.0


async def test_collect_cycle_averages_db_raises():
    c = _bare_coord()
    c._cycle_cop_count = 0
    c.db = MagicMock()
    c.db.async_avg_cop_between = AsyncMock(side_effect=RuntimeError("boom"))
    record = {"start_ts": 1.0, "end_ts": 2.0, "duration_s": 600.0}
    cop_avg, _, _ = await c._collect_cycle_averages(record)
    assert cop_avg is None


async def test_collect_cycle_averages_no_db():
    c = _bare_coord()
    c.db = None
    record = {"start_ts": 1.0, "end_ts": 2.0, "duration_s": 600.0}
    cop_avg, _, _ = await c._collect_cycle_averages(record)
    assert cop_avg is None
    assert record["cop_confidence"] == "none"


async def test_collect_cycle_averages_no_start_ts_skips_fallback():
    c = _bare_coord()
    c.db = MagicMock()
    c.db.async_avg_cop_between = AsyncMock(return_value=4.5)
    record = {"duration_s": 600.0}
    cop_avg, _, _ = await c._collect_cycle_averages(record)
    assert cop_avg is None
    c.db.async_avg_cop_between.assert_not_awaited()


# ---------------- async_insert_cycle ----------------


async def test_insert_cycle_with_cop_fields(tmp_path):
    db = CycleDB(str(tmp_path / "t.db"))
    await db.async_open()
    await db.async_initialize()
    cid = await db.async_insert_cycle({
        "start_ts": 100.0, "end_ts": 200.0, "duration_s": 100,
        "mode": "heating", "cop_avg": 3.5, "cop_sample_count": 12,
        "cop_sample_stdev": 0.3, "cop_confidence": "high",
    })
    assert cid is not None
    await db.async_close()
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "t.db"))
    row = conn.execute(
        "SELECT cop_avg, cop_sample_count, cop_sample_stdev, cop_confidence "
        "FROM cycles WHERE id=?", (cid,)
    ).fetchone()
    assert row == (3.5, 12, 0.3, "high")
    conn.close()


async def test_insert_cycle_without_cop_fields(tmp_path):
    db = CycleDB(str(tmp_path / "t.db"))
    await db.async_open()
    await db.async_initialize()
    cid = await db.async_insert_cycle({
        "start_ts": 100.0, "end_ts": 200.0, "duration_s": 100,
        "mode": "heating",
    })
    assert cid is not None
    await db.async_close()
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "t.db"))
    row = conn.execute(
        "SELECT cop_avg, cop_sample_count, cop_sample_stdev, cop_confidence "
        "FROM cycles WHERE id=?", (cid,)
    ).fetchone()
    assert row == (None, None, None, None)
    conn.close()
