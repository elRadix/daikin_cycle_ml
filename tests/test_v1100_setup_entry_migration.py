"""v1.10.0 #75 - end-to-end migration via async_setup_entry tests."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daikin_cycle_ml.const import (
    DB_FILENAME,
    DB_FILENAME_TEMPLATE,
    DB_LEGACY_MARKER_FILENAME,
    DOMAIN,
)
from custom_components.daikin_cycle_ml.storage import migration
from homeassistant.core import HomeAssistant


def _mock_coordinator(entry_id: str) -> MagicMock:
    c = MagicMock()
    c.entry = MagicMock()
    c.entry.entry_id = entry_id
    c.entry.options = {}
    c.entry.data = {}
    c.entry.title = "Daikin Cycle ML"
    c.data = {}
    c.async_reload_user_datasheets = AsyncMock()
    c.async_setup_alert_persistence = AsyncMock()
    c.async_setup_maintenance = AsyncMock()
    c.async_setup_baseline_persistence = AsyncMock()
    c.async_setup_kmeans = AsyncMock()
    c.async_setup_status_updates = AsyncMock()
    c.async_setup_stooklijn = AsyncMock()
    c.async_config_entry_first_refresh = AsyncMock()
    c.db = None
    return c


def _mock_cycle_db() -> MagicMock:
    inst = MagicMock()
    inst.async_open = AsyncMock()
    inst.async_initialize = AsyncMock()
    inst.async_migrate_features_to_v11 = AsyncMock(return_value=0)
    inst.async_migrate_features_to_v12 = AsyncMock()
    inst.async_migrate_cop_samples_to_v13 = AsyncMock()
    inst.async_migrate_to_v14 = AsyncMock()
    inst.async_migrate_cop_samples_mode_default_v15 = AsyncMock(return_value=0)
    inst.async_integrity_check = AsyncMock(return_value=True)
    inst.async_close = AsyncMock()
    inst.async_backfill_quality_scores = AsyncMock(return_value=0)
    inst.async_fetch_recent_cycles_for_hydration = AsyncMock(return_value=[])
    inst.path = "mock"
    inst.is_open = True
    return inst


@pytest.mark.asyncio
@pytest.mark.expected_lingering_timers(True)
@pytest.mark.expected_lingering_tasks(True)
async def test_migration_runs_end_to_end_through_async_setup_entry(
    hass: HomeAssistant,
    tmp_path: Path,
) -> None:
    """Direct async_setup_entry migrates legacy DB to per-entry.

    Uses direct call (not hass.config_entries.async_setup) to avoid full
    HA lifecycle which hangs on real sensor platform loading. CycleDB is
    patched to a mock so we test migration logic, not SQLite init.
    """
    migration._MIGRATION_LOCK = asyncio.Lock()

    hass.config.config_dir = str(tmp_path)
    storage = tmp_path / ".storage"
    storage.mkdir()
    legacy = storage / DB_FILENAME
    legacy_bytes = b"legacy-db-content"
    legacy.write_bytes(legacy_bytes)

    entry_id = "e2e_mig_1"
    coord = _mock_coordinator(entry_id)
    mock_db = _mock_cycle_db()

    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id=entry_id,
        data={},
        options={},
        title="Daikin Cycle ML",
    )
    entry.add_to_hass(hass)

    from custom_components.daikin_cycle_ml import async_setup_entry

    with patch(
        "custom_components.daikin_cycle_ml.DaikinCycleMLCoordinator",
        return_value=coord,
    ), patch(
        "custom_components.daikin_cycle_ml.CycleDB",
        return_value=mock_db,
    ), patch(
        "custom_components.daikin_cycle_ml.async_register_services",
        new=AsyncMock(),
    ), patch(
        "custom_components.daikin_cycle_ml.PLATFORMS",
        (),
    ), patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        new=AsyncMock(return_value=True),
    ):
        ok = await async_setup_entry(hass, entry)

    assert ok is True, "async_setup_entry returned False"

    per_entry = storage / DB_FILENAME_TEMPLATE.format(entry_id=entry_id)
    assert per_entry.exists(), "per-entry DB not created"
    assert not legacy.exists(), "legacy DB should have been migrated away"
    assert per_entry.read_bytes() == legacy_bytes, "content not preserved"
    assert (storage / DB_LEGACY_MARKER_FILENAME).exists(), "marker not written"
    assert coord.db is mock_db, "coordinator.db should be the patched mock"
