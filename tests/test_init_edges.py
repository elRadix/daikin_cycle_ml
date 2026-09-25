"""Tests for __init__ edge paths (Batch 8d)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.daikin_cycle_ml import (
    _async_setup_database,
    async_unload_entry,
)


async def test_setup_database_exception_sets_db_none():
    hass = MagicMock()
    hass.config.config_dir = "/tmp"
    coord = MagicMock()
    coord.db = None
    with patch(
        "custom_components.daikin_cycle_ml.CycleDB",
        side_effect=RuntimeError("boom"),
    ):
        await _async_setup_database(hass, coord)
    assert coord.db is None


async def test_unload_returns_false_when_platform_unload_fails():
    hass = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)
    entry = MagicMock()
    entry.runtime_data = MagicMock()
    out = await async_unload_entry(hass, entry)
    assert out is False


async def test_unload_db_close_error_caught():
    hass = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    db = MagicMock()
    db.async_close = AsyncMock(side_effect=RuntimeError("boom"))
    coord = MagicMock()
    coord.db = db
    entry = MagicMock()
    entry.runtime_data = coord
    # must not raise
    out = await async_unload_entry(hass, entry)
    assert out is True


async def test_unload_no_coordinator_ok():
    hass = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    entry = MagicMock()
    entry.runtime_data = None
    out = await async_unload_entry(hass, entry)
    assert out is True


async def test_unload_db_none_ok():
    hass = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    coord = MagicMock()
    coord.db = None
    entry = MagicMock()
    entry.runtime_data = coord
    out = await async_unload_entry(hass, entry)
    assert out is True
