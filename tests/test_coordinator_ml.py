"""Tests for coordinator ML pipeline (Batch 7c)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    DataSnapshot,
)
from custom_components.daikin_cycle_ml.ml.multi_baseline import MultiBaseline
from custom_components.daikin_cycle_ml.ml.features import VECTOR_LEN
from custom_components.daikin_cycle_ml.storage.store import CycleStore


def _bare_coord(options=None, store=None, db=None):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = options or {}
    c.store = store or CycleStore()
    c.entry = MagicMock()
    c.entry.entry_id = "test"
    c.hass = MagicMock()
    c.hass.services = MagicMock()
    c.hass.services.async_call = AsyncMock()
    c._last_alert_sent = {}
    c._errors_total = 0
    c.baseline = MultiBaseline(VECTOR_LEN)
    c.db = db
    return c


def _good_record(start_ts=100.0):
    return {
        "start_ts": start_ts,
        "end_ts": start_ts + 3600,
        "duration_s": 3600,
        "mode": "Heating",
        "dT_max": 7.5, "dT_avg": 5.2,
        "rps_max": 60, "rps_avg": 42.5,
        "outdoor_temp": 8.0,
        "buh_used": 0, "defrost_used": 0,
    }


def test_baseline_attached_in_new_coord():
    c = _bare_coord()
    assert c.baseline is not None
    assert c.baseline.dim == VECTOR_LEN


async def test_process_new_cycle_updates_baseline():
    c = _bare_coord()
    snap = DataSnapshot()
    await c._process_new_cycle(_good_record(), snap)
    assert c.baseline.total_samples() == 1


async def test_process_new_cycle_sets_snap_anomaly_attr():
    c = _bare_coord()
    snap = DataSnapshot()
    await c._process_new_cycle(_good_record(), snap)
    # attribute exists (may be None or AnomalyResult)
    assert hasattr(snap, "anomaly")


async def test_process_new_cycle_sets_advice_attr():
    c = _bare_coord()
    snap = DataSnapshot()
    await c._process_new_cycle(_good_record(), snap)
    assert hasattr(snap, "advice")


async def test_process_new_cycle_no_db_ok():
    c = _bare_coord(db=None)
    snap = DataSnapshot()
    # must not raise
    await c._process_new_cycle(_good_record(), snap)


async def test_process_new_cycle_db_insert_called():
    db = MagicMock()
    db.async_insert_cycle = AsyncMock(return_value=1)
    db.async_insert_features = AsyncMock()
    c = _bare_coord(db=db)
    snap = DataSnapshot()
    await c._process_new_cycle(_good_record(), snap)
    assert db.async_insert_cycle.await_count == 1
    assert db.async_insert_features.await_count == 1


async def test_process_new_cycle_db_failure_does_not_raise():
    db = MagicMock()
    db.async_insert_cycle = AsyncMock(side_effect=RuntimeError("boom"))
    c = _bare_coord(db=db)
    snap = DataSnapshot()
    # must not raise
    await c._process_new_cycle(_good_record(), snap)


async def test_process_new_cycle_after_enough_samples_anomaly_set():
    c = _bare_coord()
    snap = DataSnapshot()
    for i in range(10):
        await c._process_new_cycle(_good_record(start_ts=100.0 + i * 4000), snap)
    # Feed a wildly different cycle
    wild = _good_record(start_ts=100000.0)
    wild["duration_s"] = 999999
    wild["rps_max"] = 99999
    snap2 = DataSnapshot()
    await c._process_new_cycle(wild, snap2)
    assert snap2.anomaly is not None
    assert snap2.anomaly.is_anomaly is True


async def test_process_new_cycle_advice_is_list():
    c = _bare_coord()
    snap = DataSnapshot()
    await c._process_new_cycle(_good_record(), snap)
    assert isinstance(snap.advice, list)


async def test_process_new_cycle_never_raises_on_bad_record():
    c = _bare_coord()
    snap = DataSnapshot()
    await c._process_new_cycle({}, snap)
