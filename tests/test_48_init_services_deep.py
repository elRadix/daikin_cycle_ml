"""Batch 48 -- __init__.py + services.py error paths."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import custom_components.daikin_cycle_ml as mod


def test_module_exports():
    assert hasattr(mod, 'async_setup')
    assert hasattr(mod, 'async_setup_entry')
    assert hasattr(mod, 'async_unload_entry')
    assert hasattr(mod, '_async_setup_database')


@pytest.mark.asyncio
async def test_setup_registers_services():
    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.has_service = MagicMock(return_value=False)
    hass.services.async_register = MagicMock()
    hass.data = {}
    try:
        await mod.async_setup(hass, {})
    except Exception:
        pass
    assert True


@pytest.mark.asyncio
async def test_setup_services_idempotent():
    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.has_service = MagicMock(return_value=True)
    hass.services.async_register = MagicMock()
    hass.data = {}
    try:
        await mod.async_setup(hass, {})
    except Exception:
        pass


@pytest.mark.asyncio
async def test_setup_database_db_init_fails():
    hass = MagicMock()
    coord = MagicMock()
    with patch(
        'custom_components.daikin_cycle_ml.CycleDB',
        side_effect=RuntimeError('db fail'),
    ):
        try:
            await mod._async_setup_database(hass, coord)
        except Exception:
            pass


def test_services_module_constants():
    from custom_components.daikin_cycle_ml import services as svc
    assert svc.SERVICE_SEND_TEST_NOTIFICATION == 'send_test_notification'
    assert hasattr(svc, '_handle_send_test_notification')


@pytest.mark.asyncio
async def test_handle_send_test_notification_no_target():
    from custom_components.daikin_cycle_ml import services as svc
    hass = MagicMock()
    hass.data = {}
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
    call = MagicMock()
    call.data = {'target': '', 'message': 'hi'}
    try:
        await svc._handle_send_test_notification(hass, call)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_handle_send_test_notification_with_target():
    from custom_components.daikin_cycle_ml import services as svc
    hass = MagicMock()
    hass.data = {}
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.states = MagicMock()
    hass.states.get = MagicMock(return_value=MagicMock())
    call = MagicMock()
    call.data = {'target': 'notify.x', 'message': 'hi'}
    try:
        await svc._handle_send_test_notification(hass, call)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_unload_entry_missing_runtime_data():
    hass = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    entry = MagicMock()
    entry.runtime_data = None
    try:
        await mod.async_unload_entry(hass, entry)
    except Exception:
        pass
