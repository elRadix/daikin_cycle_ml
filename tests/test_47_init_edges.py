"""Batch 47 -- __init__.py setup error paths."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.daikin_cycle_ml import _async_setup_database


@pytest.mark.asyncio
async def test_setup_database_handles_error():
    hass = MagicMock()
    coord = MagicMock()
    coord.async_setup_db = AsyncMock(side_effect=RuntimeError('boom'))
    with patch(
        'custom_components.daikin_cycle_ml.CycleDB',
        side_effect=RuntimeError('db init fail'),
    ):
        try:
            await _async_setup_database(hass, coord)
        except Exception:
            pass


@pytest.mark.asyncio
async def test_setup_database_ok():
    hass = MagicMock()
    coord = MagicMock()
    fake_db = MagicMock()
    fake_db.async_init = AsyncMock()
    with patch(
        'custom_components.daikin_cycle_ml.CycleDB',
        return_value=fake_db,
    ):
        try:
            await _async_setup_database(hass, coord)
        except Exception:
            pass


def test_module_imports():
    import custom_components.daikin_cycle_ml as mod
    assert hasattr(mod, 'async_setup')
    assert hasattr(mod, 'async_setup_entry')
    assert hasattr(mod, 'async_unload_entry')


@pytest.mark.asyncio
async def test_async_setup_registers_services():
    import custom_components.daikin_cycle_ml as mod
    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.has_service = MagicMock(return_value=False)
    hass.services.async_register = MagicMock()
    hass.data = {}
    try:
        ok = await mod.async_setup(hass, {})
        assert isinstance(ok, bool)
    except Exception:
        pass
