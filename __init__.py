"""Daikin Cycle ML - Home Assistant custom integration."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, VERSION
from .coordinator import DaikinCycleMLCoordinator
from .services import async_register_services
from .storage.db import CycleDB

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor", "binary_sensor"]

DB_RELATIVE = Path(".storage") / "daikin_cycle_ml.db"


async def async_setup(hass: HomeAssistant, _config: dict) -> bool:
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
        coordinator.db = db
        _LOGGER.info("Cycle DB ready at %s", db_path)
    except Exception:  # noqa: BLE001
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
    except Exception:  # noqa: BLE001
        _LOGGER.exception('Failed to setup maintenance hook')
    try:
        await coordinator.async_setup_baseline_persistence()
    except Exception:  # noqa: BLE001
        _LOGGER.exception('Failed to setup baseline persistence')
    try:
        await coordinator.async_setup_kmeans()
    except Exception:  # noqa: BLE001
        _LOGGER.exception('Failed to setup kmeans scheduler')
    try:
        await coordinator.async_setup_status_updates()
    except Exception:  # noqa: BLE001
        _LOGGER.exception('Failed to setup status updates')
    try:
        await coordinator.async_setup_stooklijn()
    except Exception:  # noqa: BLE001
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
                except Exception:  # noqa: BLE001
                    _LOGGER.exception('Failed to unsub %s', _attr)
                setattr(coordinator, _attr, None)
    db = getattr(coordinator, "db", None) if coordinator is not None else None
    if db is not None:
        try:
            await db.async_close()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Failed closing Cycle DB")
    _LOGGER.info("Daikin Cycle ML unloaded entry %s", entry.entry_id)
    return True
