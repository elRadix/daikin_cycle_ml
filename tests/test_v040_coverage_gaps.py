from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from custom_components.daikin_cycle_ml.sensor import (
    DaikinCycleMLSensor, _avg, _avg_off_time,
    async_setup_entry as sensor_setup,
)
from custom_components.daikin_cycle_ml.binary_sensor import (
    DaikinCycleMLBinarySensor, # removed-class-ref,
    _attr_on, _is_short_run, _is_source_stale,
    async_setup_entry as bs_setup,
)
from custom_components.daikin_cycle_ml.storage.db import CycleDB


def test_avg_rounded():
    assert _avg([1.0, 2.0, 3.0]) == 2.0


def test_avg_off_time_gaps():
    cycles = [
        {'start_ts': 100.0, 'end_ts': 200.0},
        {'start_ts': 300.0, 'end_ts': 400.0},
    ]
    assert _avg_off_time(cycles) == 100.0


def test_avg_off_time_no_end_ts():
    cycles = [{'start_ts': 100.0}, {'start_ts': 300.0}]
    assert _avg_off_time(cycles) is None


def test_native_value_exception_none():
    s = object.__new__(DaikinCycleMLSensor)
    s.coordinator = MagicMock()
    s._key = 'k'
    s._value_fn = lambda snap, coord: 1 / 0
    s.snapshot = lambda: MagicMock()
    assert s.native_value is None


async def test_sensor_setup_no_coordinator():
    entry = MagicMock()
    entry.runtime_data = None
    entry.entry_id = 'test_entry'
    added = MagicMock()
    await sensor_setup(MagicMock(), entry, added)
    added.assert_not_called()


def test_attr_on_true():
    assert _attr_on({'x': True}, 'x') is True


def test_attr_on_false():
    assert _attr_on({'x': False}, 'x') is False


def test_is_short_run_non_numeric():
    s = MagicMock()
    c = MagicMock()
    c.store.last_cycle.return_value = {'duration_s': 'abc'}
    c.options = {'short_run_threshold_min': 20}
    assert _is_short_run(s, c) is False


def test_is_source_stale_zero():
    s = MagicMock()
    s.last_success_ts = 0
    assert _is_source_stale(s, MagicMock()) is False


def test_binary_is_on_exception_false():
    b = object.__new__(DaikinCycleMLBinarySensor)
    b.coordinator = MagicMock()
    b._key = 'k'
    b._state_fn = lambda snap, coord: 1 / 0
    b.snapshot = lambda: MagicMock()
    assert b.is_on is False


async def test_bs_setup_no_coordinator():
    entry = MagicMock()
    entry.runtime_data = None
    entry.entry_id = 'test_entry'
    added = MagicMock()
    await bs_setup(MagicMock(), entry, added)
    added.assert_not_called()


