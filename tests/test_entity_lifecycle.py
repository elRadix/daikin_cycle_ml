from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daikin_cycle_ml import async_unload_entry


@pytest.mark.asyncio
async def test_entity_registry_cleanup_on_unload(hass):
    entry = MockConfigEntry(domain="daikin_cycle_ml", entry_id="unload_test")
    entry.runtime_data = MagicMock()
    entry.runtime_data.db = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    # We checken of unload niet crasht als de registry leeg is
    await async_unload_entry(hass, entry)
    assert entry.entry_id not in hass.data.get("daikin_cycle_ml", {})
