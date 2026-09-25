"""Tests voor 14c-2 coordinator wiring (LWT + indoor + cop_avg)."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml.engine.cycle_detector import CycleDetector

import pytest

from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
from custom_components.daikin_cycle_ml.ml.features import VECTOR_LEN


@pytest.fixture
def fake_hass():
    hass = MagicMock()
    hass.states.get = MagicMock(return_value=None)
    return hass


@pytest.fixture
def fake_entry():
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.options = {}
    entry.data = {}
    return entry


def _set_detector_state(c, state_value):
    """Replace detector with a MagicMock to force state."""
    mock_det = MagicMock(spec=CycleDetector)
    mock_det.state = state_value
    c.detector = mock_det


def test_accumulators_initialised(fake_hass, fake_entry):
    c = DaikinCycleMLCoordinator(fake_hass, fake_entry)
    assert c._cycle_lwt_sum == 0.0
    assert c._cycle_lwt_count == 0
    assert c._cycle_indoor_sum == 0.0
    assert c._cycle_indoor_count == 0


def test_indoor_entity_none_by_default(fake_hass, fake_entry):
    c = DaikinCycleMLCoordinator(fake_hass, fake_entry)
    assert c.indoor_temp_entity is None


def test_indoor_entity_from_options(fake_hass, fake_entry):
    fake_entry.options = {"indoor_temp_sensor": "sensor.living_room"}
    c = DaikinCycleMLCoordinator(fake_hass, fake_entry)
    assert c.indoor_temp_entity == "sensor.living_room"


def test_accumulate_skipped_when_idle(fake_hass, fake_entry):
    c = DaikinCycleMLCoordinator(fake_hass, fake_entry)
    _set_detector_state(c, 'idle')
    c._accumulate_cycle_samples({"lwt": 35.0})
    assert c._cycle_lwt_count == 0


def test_accumulate_lwt_when_active(fake_hass, fake_entry):
    c = DaikinCycleMLCoordinator(fake_hass, fake_entry)
    _set_detector_state(c, 'heating')
    c._accumulate_cycle_samples({"lwt": 35.0})
    c._accumulate_cycle_samples({'lwt': 37.0})
    assert c._cycle_lwt_count == 2
    assert c._cycle_lwt_sum == 72.0


def test_accumulate_lwt_alternate_keys(fake_hass, fake_entry):
    c = DaikinCycleMLCoordinator(fake_hass, fake_entry)
    _set_detector_state(c, 'heating')
    c._accumulate_cycle_samples({'leaving_water_temp': 34.0})
    assert c._cycle_lwt_sum == 34.0


def test_accumulate_indoor_when_entity_set(fake_hass, fake_entry):
    fake_entry.options = {"indoor_temp_sensor": "sensor.temp"}
    c = DaikinCycleMLCoordinator(fake_hass, fake_entry)
    _set_detector_state(c, 'heating')
    st = MagicMock()
    st.state = '21.5'
    fake_hass.states.get = MagicMock(return_value=st)
    c._accumulate_cycle_samples({})
    assert c._cycle_indoor_count == 1
    assert c._cycle_indoor_sum == 21.5


def test_accumulate_indoor_invalid_state(fake_hass, fake_entry):
    fake_entry.options = {"indoor_temp_sensor": "sensor.temp"}
    c = DaikinCycleMLCoordinator(fake_hass, fake_entry)
    _set_detector_state(c, 'heating')
    st = MagicMock()
    st.state = 'unknown'
    fake_hass.states.get = MagicMock(return_value=st)
    c._accumulate_cycle_samples({})
    assert c._cycle_indoor_count == 0


@pytest.mark.asyncio
async def test_collect_averages_no_data(fake_hass, fake_entry):
    c = DaikinCycleMLCoordinator(fake_hass, fake_entry)
    cop, lwt, indoor = await c._collect_cycle_averages({})
    assert cop is None
    assert lwt is None
    assert indoor is None


@pytest.mark.asyncio
async def test_collect_averages_lwt_only(fake_hass, fake_entry):
    c = DaikinCycleMLCoordinator(fake_hass, fake_entry)
    c._cycle_lwt_sum = 70.0
    c._cycle_lwt_count = 2
    cop, lwt, indoor = await c._collect_cycle_averages({})
    assert lwt == 35.0
    assert indoor is None
    assert cop is None


@pytest.mark.asyncio
async def test_collect_averages_resets_after(fake_hass, fake_entry):
    c = DaikinCycleMLCoordinator(fake_hass, fake_entry)
    c._cycle_lwt_sum = 70.0
    c._cycle_lwt_count = 2
    await c._collect_cycle_averages({})
    assert c._cycle_lwt_sum == 0.0
    assert c._cycle_lwt_count == 0


@pytest.mark.asyncio
async def test_collect_averages_cop_from_db(fake_hass, fake_entry):
    c = DaikinCycleMLCoordinator(fake_hass, fake_entry)
    c.db = MagicMock()
    c.db.async_avg_cop_between = AsyncMock(return_value=3.4)
    cop, _, _ = await c._collect_cycle_averages(
        {"start_ts": 100.0, "end_ts": 200.0}
    )
    assert cop == 3.4
    c.db.async_avg_cop_between.assert_awaited_once_with(100.0, 200.0)


@pytest.mark.asyncio
async def test_collect_averages_cop_db_error_swallowed(fake_hass, fake_entry):
    c = DaikinCycleMLCoordinator(fake_hass, fake_entry)
    c.db = MagicMock()
    c.db.async_avg_cop_between = AsyncMock(side_effect=RuntimeError('boom'))
    cop, _, _ = await c._collect_cycle_averages(
        {"start_ts": 100.0, "end_ts": 200.0}
    )
    assert cop is None


@pytest.mark.asyncio
async def test_collect_averages_no_start_end(fake_hass, fake_entry):
    c = DaikinCycleMLCoordinator(fake_hass, fake_entry)
    c.db = MagicMock()
    c.db.async_avg_cop_between = AsyncMock(return_value=3.4)
    cop, _, _ = await c._collect_cycle_averages({})
    assert cop is None
    c.db.async_avg_cop_between.assert_not_awaited()

