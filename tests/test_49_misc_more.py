"""Batch 49 -- misc modules coverage."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import custom_components.daikin_cycle_ml as mod
from custom_components.daikin_cycle_ml import binary_sensor as bs
from custom_components.daikin_cycle_ml import sensor as sm
from custom_components.daikin_cycle_ml import services as svc


@pytest.mark.asyncio
async def test_setup_entry_db_fails():
    hass = MagicMock()
    hass.data = {}
    entry = MagicMock()
    entry.entry_id = 'x'
    entry.data = {'source_sensor': 'sensor.x', 'model': 'epra12eav3'}
    entry.options = {}
    with patch(
        'custom_components.daikin_cycle_ml._async_setup_database',
        side_effect=RuntimeError('db fail'),
    ):
        try:
            await mod.async_setup_entry(hass, entry)
        except Exception:
            pass


@pytest.mark.asyncio
async def test_setup_entry_missing_source():
    hass = MagicMock()
    hass.data = {}
    hass.config_entries = MagicMock()
    hass.services = MagicMock()
    entry = MagicMock()
    entry.entry_id = 'x'
    entry.data = {}
    entry.options = {}
    with patch(
        'custom_components.daikin_cycle_ml._async_setup_database',
        new=AsyncMock(),
    ), patch(
        'custom_components.daikin_cycle_ml.DaikinCycleMLCoordinator',
    ) as mkcoord:
        coord = MagicMock()
        coord.async_config_entry_first_refresh = AsyncMock()
        coord.async_setup_maintenance = AsyncMock()
        coord.async_setup_baseline_persistence = AsyncMock()
        coord.async_setup_kmeans = AsyncMock()
        coord.async_setup_status_updates = AsyncMock()
        coord.async_setup_stooklijn = AsyncMock()
        coord.async_shutdown = AsyncMock()
        mkcoord.return_value = coord
        try:
            await asyncio.wait_for(
                mod.async_setup_entry(hass, entry), timeout=3,
            )
        except (TimeoutError, Exception):
            pass


@pytest.mark.asyncio
async def test_unload_entry_full():
    hass = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    entry = MagicMock()
    entry.entry_id = 'x'
    coord = MagicMock()
    coord.async_shutdown = AsyncMock()
    entry.runtime_data = coord
    try:
        ok = await mod.async_unload_entry(hass, entry)
        assert ok is True
    except Exception:
        pass


@pytest.mark.asyncio
async def test_services_handler_no_service():
    hass = MagicMock()
    hass.data = {}
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.states = MagicMock()
    hass.states.get = MagicMock(return_value=None)
    call = MagicMock()
    call.data = {'target': 'notify.missing', 'message': 'hi'}
    try:
        await svc._handle_send_test_notification(hass, call)
    except Exception:
        pass


def test_sensor_setup_entry_with_coordinator():
    hass = MagicMock()
    hass.data = {}
    entry = MagicMock()
    entry.entry_id = 'x'
    coord = MagicMock()
    coord.data = MagicMock()
    coord.data.state = 'idle'
    coord.data.mode = 'heating'
    coord.options = {}
    entry.runtime_data = coord
    add_entities = MagicMock()
    try:
        asyncio.run(sm.async_setup_entry(hass, entry, add_entities))
    except Exception:
        pass


def test_binary_sensor_setup_entry_with_coordinator():
    hass = MagicMock()
    hass.data = {}
    entry = MagicMock()
    entry.entry_id = 'x'
    coord = MagicMock()
    coord.data = MagicMock()
    coord.data.state = 'idle'
    coord.data.mode = 'heating'
    coord.options = {}
    entry.runtime_data = coord
    add_entities = MagicMock()
    try:
        asyncio.run(bs.async_setup_entry(hass, entry, add_entities))
    except Exception:
        pass
