"""Batch 50e -- __init__.py setup paths."""
from __future__ import annotations

import asyncio

import pytest

from custom_components.daikin_cycle_ml.const import DOMAIN
from homeassistant.core import HomeAssistant

pytestmark = pytest.mark.asyncio


async def test_async_setup_registers_services(hass: HomeAssistant):
    from custom_components.daikin_cycle_ml import async_setup
    ok = await asyncio.wait_for(async_setup(hass, {}), timeout=3)
    assert ok is True
    assert hass.services.has_service(DOMAIN, "reset_counters")


async def test_async_setup_idempotent(hass: HomeAssistant):
    from custom_components.daikin_cycle_ml import async_setup
    await asyncio.wait_for(async_setup(hass, {}), timeout=3)
    ok = await asyncio.wait_for(async_setup(hass, {}), timeout=3)
    assert ok is True


async def test_async_unload_entry_not_loaded(hass: HomeAssistant):
    from unittest.mock import MagicMock

    from custom_components.daikin_cycle_ml import async_unload_entry
    entry = MagicMock()
    entry.entry_id = "nonexistent"
    entry.runtime_data = None
    result = await asyncio.wait_for(async_unload_entry(hass, entry), timeout=3)
    assert result is True
