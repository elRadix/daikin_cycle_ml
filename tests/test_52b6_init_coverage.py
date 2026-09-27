"""Batch 52b6: coverage for __init__.py setup paths."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.daikin_cycle_ml import (
    _async_setup_database,
    async_setup_entry,
)


def _mock_db(**kw):
    inst = MagicMock()
    inst.async_open = AsyncMock()
    inst.async_initialize = AsyncMock()
    inst.async_migrate_features_to_v11 = AsyncMock(return_value=0)
    inst.async_migrate_features_to_v12 = AsyncMock(return_value=0)
    inst.async_migrate_cop_samples_to_v13 = AsyncMock(return_value=0)
    inst.async_integrity_check = AsyncMock(return_value=True)
    for k, v in kw.items():
        setattr(inst, k, v)
    return inst


async def test_v11_migration_success_logs(hass):
    """Cover lijn 42: _LOGGER.info bij migrated > 0."""
    coord = MagicMock()
    inst = _mock_db()
    inst.async_migrate_features_to_v11 = AsyncMock(return_value=3)
    with patch("custom_components.daikin_cycle_ml.CycleDB",
               return_value=inst):
        await _async_setup_database(hass, coord)
    assert coord._migration_error is None


async def test_v13_migration_raises(hass):
    """Cover lijn 58-61."""
    coord = MagicMock()
    coord._migration_error = None
    inst = _mock_db()
    inst.async_migrate_cop_samples_to_v13 = AsyncMock(
        side_effect=RuntimeError("v13 boom"))
    with patch("custom_components.daikin_cycle_ml.CycleDB",
               return_value=inst):
        await _async_setup_database(hass, coord)
    assert coord._migration_error == "v13 boom"


async def test_integrity_check_raises(hass):
    """Cover lijn 64-66."""
    coord = MagicMock()
    inst = _mock_db()
    inst.async_integrity_check = AsyncMock(
        side_effect=RuntimeError("integrity boom"))
    with patch("custom_components.daikin_cycle_ml.CycleDB",
               return_value=inst):
        await _async_setup_database(hass, coord)
    assert coord._db_integrity_ok is False


async def test_setup_entry_maintenance_raises(hass):
    """Cover lijn 82-83."""
    coord = MagicMock()
    coord.async_config_entry_first_refresh = AsyncMock()
    coord.async_setup_maintenance = AsyncMock(
        side_effect=RuntimeError("maint fail"))
    coord.async_setup_baseline_persistence = AsyncMock()
    coord.async_setup_kmeans = AsyncMock()
    coord.async_setup_status_updates = AsyncMock()
    coord.async_setup_stooklijn = AsyncMock()

    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = {"source_sensor": "sensor.x", "model": "epra12eav3"}
    entry.options = {}
    entry.runtime_data = None

    with patch("custom_components.daikin_cycle_ml.DaikinCycleMLCoordinator",
               return_value=coord), \
         patch("custom_components.daikin_cycle_ml._async_setup_database",
               new=AsyncMock()), \
         patch.object(hass.config_entries,
                      "async_forward_entry_setups",
                      new=AsyncMock()):
        result = await async_setup_entry(hass, entry)
    assert result is True


async def test_setup_entry_all_hooks_raise(hass):
    """Cover lijn 82-83, 86-87, 90-91, 94-95, 98-99."""
    coord = MagicMock()
    coord.async_config_entry_first_refresh = AsyncMock()
    for hook in ("async_setup_maintenance",
                 "async_setup_baseline_persistence",
                 "async_setup_kmeans",
                 "async_setup_status_updates",
                 "async_setup_stooklijn"):
        setattr(coord, hook, AsyncMock(side_effect=RuntimeError(hook + " boom")))

    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = {"source_sensor": "sensor.x", "model": "epra12eav3"}
    entry.options = {}
    entry.runtime_data = None

    with patch("custom_components.daikin_cycle_ml.DaikinCycleMLCoordinator",
               return_value=coord), \
         patch("custom_components.daikin_cycle_ml._async_setup_database",
               new=AsyncMock()), \
         patch.object(hass.config_entries,
                      "async_forward_entry_setups",
                      new=AsyncMock()):
        result = await async_setup_entry(hass, entry)
    assert result is True
