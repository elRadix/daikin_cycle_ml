from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daikin_cycle_ml import (
    async_remove_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.daikin_cycle_ml.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState


def _make_entry(hass, entry_id):
    entry = MockConfigEntry(domain=DOMAIN, entry_id=entry_id)
    entry.add_to_hass(hass)
    object.__setattr__(entry, "state", ConfigEntryState.SETUP_IN_PROGRESS)
    return entry


@pytest.mark.asyncio
async def test_setup_entry_returns_bool(hass):
    """HA Core 2026+ contract: async_setup_entry MUST return bool."""
    entry = _make_entry(hass, "test_setup")
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)
    try:
        result = await async_setup_entry(hass, entry)
        assert isinstance(result, bool), f"Expected bool, got {type(result)}"
    finally:
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        # NB: do NOT set entry.runtime_data = None before unload;
        # unload needs it to clean up the 8 timers.
        await async_unload_entry(hass, entry)


@pytest.mark.asyncio
async def test_unload_entry_returns_bool(hass):
    """HA Core 2026+ contract: async_unload_entry MUST return bool."""
    entry = _make_entry(hass, "test_unload")
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    entry.runtime_data = None
    result = await async_unload_entry(hass, entry)
    assert isinstance(result, bool)
    assert result is True


@pytest.mark.asyncio
async def test_remove_entry_never_raises(hass):
    """HA Core 2026+ contract: async_remove_entry must never raise."""
    entry = _make_entry(hass, "test_remove")
    try:
        await async_remove_entry(hass, entry)
    except Exception as e:
        pytest.fail(f"Remove crashed: {e}")
