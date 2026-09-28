"""Daikin Cycle ML - Home Assistant custom integration."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN as DOMAIN
from .const import VERSION as VERSION
from .coordinator import DaikinCycleMLCoordinator
from .services import async_register_services
from .storage.db import CycleDB

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor", "binary_sensor"]

DB_RELATIVE = Path(".storage") / "daikin_cycle_ml.db"


CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, _config: dict[str, Any]) -> bool:
    """Register integration-wide services once per HA lifecycle."""
    await async_register_services(hass)
    return True


async def _async_setup_database(
    hass: HomeAssistant, coordinator: DaikinCycleMLCoordinator
) -> None:
    """Open + initialize SQLite DB, attach to coordinator (best-effort)."""
    db_path = Path(hass.config.config_dir) / DB_RELATIVE
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db = CycleDB(db_path)
        await db.async_open()
        await db.async_initialize()
        try:
            migrated = await db.async_migrate_features_to_v11()
            if migrated > 0:
                _LOGGER.info(
                    'Migrated %d legacy feature vectors to 11-dim',
                    migrated,
                )
            coordinator._migration_error = None
        except Exception as err:
            _LOGGER.exception('feature vector migration failed')
            coordinator._migration_error = str(err)
        try:
            await db.async_migrate_features_to_v12()
        except Exception as err:
            _LOGGER.exception('v12 migration failed')
            if coordinator._migration_error is None:  # pragma: no branch
                coordinator._migration_error = str(err)
        try:
            await db.async_migrate_cop_samples_to_v13()
        except Exception as err:
            _LOGGER.exception('v13 migration failed')
            if coordinator._migration_error is None:  # pragma: no branch
                coordinator._migration_error = str(err)
        try:
            await db.async_migrate_to_v14()
        except Exception as err:
            _LOGGER.exception('v14 migration failed')
            if coordinator._migration_error is None:  # pragma: no branch
                coordinator._migration_error = str(err)
        try:
            coordinator._db_integrity_ok = await db.async_integrity_check()
        except Exception:
            coordinator._db_integrity_ok = False
            _LOGGER.debug('initial integrity check failed', exc_info=True)
        coordinator.db = db
        _LOGGER.info("Cycle DB ready at %s", db_path)
    except Exception:
        _LOGGER.exception("Failed to initialize Cycle DB at %s", db_path)
        coordinator.db = None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Daikin Cycle ML from a config entry."""
    coordinator = DaikinCycleMLCoordinator(hass, entry)
    await _async_setup_database(hass, coordinator)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    try:
        await coordinator.async_setup_maintenance()
    except Exception:
        _LOGGER.exception('Failed to setup maintenance hook')
    try:
        await coordinator.async_setup_baseline_persistence()
    except Exception:
        _LOGGER.exception('Failed to setup baseline persistence')
    try:
        await coordinator.async_setup_kmeans()
    except Exception:
        _LOGGER.exception('Failed to setup kmeans scheduler')
    try:
        await coordinator.async_setup_status_updates()
    except Exception:
        _LOGGER.exception('Failed to setup status updates')
    try:
        await coordinator.async_setup_stooklijn()
    except Exception:
        _LOGGER.exception('Failed to setup stooklijn scheduler')
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info(
        "Daikin Cycle ML %s setup for entry %s", VERSION, entry.entry_id
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unloaded:
        return False
    coordinator = getattr(entry, "runtime_data", None)
    if coordinator is not None:
        for _attr in (
            "_maintenance_unsub",
            "_baseline_save_unsub",
            "_kmeans_unsub",
            "_status_update_unsub",
            "_stooklijn_unsub",
        ):
            _unsub = getattr(coordinator, _attr, None)
            if _unsub is not None:
                try:
                    _unsub()
                except Exception:  # pragma: no cover
                    _LOGGER.exception('Failed to unsub %s', _attr)
                setattr(coordinator, _attr, None)
    db = getattr(coordinator, "db", None) if coordinator is not None else None
    if db is not None:
        try:
            await db.async_close()
        except Exception:
            _LOGGER.exception("Failed closing Cycle DB")
    _LOGGER.info("Daikin Cycle ML unloaded entry %s", entry.entry_id)
    return True
