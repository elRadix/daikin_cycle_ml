"""Daikin Cycle ML - Home Assistant custom integration."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN as DOMAIN
from .const import VERSION as VERSION
from .const import GOOD_CYCLE_MIN_SCORE as GOOD_CYCLE_MIN_SCORE
from .const import DB_FILENAME as DB_FILENAME
from .const import DB_FILENAME_TEMPLATE as DB_FILENAME_TEMPLATE
from .engine.quality_scorer import score_cycle as _score_cycle
from .coordinator import DaikinCycleMLCoordinator
from .repairs import (
    clear_datasheet_load_failed,
    raise_datasheet_load_failed,
)
from .services import async_register_services
from .api import CopHourlyView
from .storage.db import CycleDB
from .storage.migration import async_migrate_legacy_db

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor", "binary_sensor"]



CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, _config: dict[str, Any]) -> bool:
    """Register integration-wide services + HTTP view once per HA."""
    await async_register_services(hass)
    _VIEW_FLAG = f"{DOMAIN}_view_registered"
    if not hass.data.get(_VIEW_FLAG):  # pragma: no branch
        try:
            hass.http.register_view(CopHourlyView(hass))
            hass.data[_VIEW_FLAG] = True
        except Exception:
            _LOGGER.exception("cop_hourly view registration failed")
    return True


async def _async_setup_database(
    hass: HomeAssistant,
    coordinator: DaikinCycleMLCoordinator,
    entry: ConfigEntry | None = None,
) -> None:
    """Open + initialize SQLite DB, attach to coordinator (best-effort)."""
    if entry is not None:
        migration = await async_migrate_legacy_db(hass, entry)
        if migration.status == "error":
            _LOGGER.warning(
                "legacy DB migration error: %s", migration.error
            )
        elif migration.status == "multi":
            _LOGGER.info(
                "legacy DB assigned to %s",
                migration.assigned_entry_id,
            )
    if entry is None:
        db_path = Path(hass.config.config_dir) / ".storage" / DB_FILENAME
    else:
        db_path = (
            Path(hass.config.config_dir)
            / ".storage"
            / DB_FILENAME_TEMPLATE.format(entry_id=entry.entry_id)
        )
    try:
        await hass.async_add_executor_job(
            lambda: db_path.parent.mkdir(
                parents=True, exist_ok=True
            )
        )
        db = CycleDB(db_path, journal_mode="wal")
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
            await db.async_migrate_cop_samples_mode_default_v15()
        except Exception as err:
            _LOGGER.exception('v15 mode-default migration failed')
            if coordinator._migration_error is None:  # pragma: no branch
                coordinator._migration_error = str(err)
        # v1.12.2 (#112, #114): data migration — reclassify unknown-mode
        # cycles with valid compressor data, backfill thermal_kw_avg
        # from features.vector_json[11], rebuild affected DS days.
        # Runs AFTER v11-v15 so vector_json is guaranteed 12-dim.
        # Non-critical: failure degrades gracefully (no _migration_error),
        # since data-only fix — cycle inserts keep working regardless.
        try:
            v17 = await db.async_migrate_to_v17()
            _LOGGER.info("v17 data migration: %s", v17)
        except Exception:
            _LOGGER.exception('v17 data migration failed')
        # v1.12.4 (#116, #130): DHW backfill v18 migration.
        # Non-critical: failure degrades gracefully (no _migration_error).
        try:
            v18 = await db.async_migrate_to_v18()
            _LOGGER.info("v18 data migration: %s", v18)
        except Exception:
            _LOGGER.exception('v18 data migration failed')
        try:
            v133b = await db.async_migrate_to_v1_12_5_sample_count_fix()
            _LOGGER.info("v1.12.5 sample_count fix: %s", v133b)
        except Exception:
            _LOGGER.exception('v1.12.5 sample_count fix migration failed')
        try:
            v19 = await db.async_migrate_to_v19()
            await db.async_migrate_to_v20()
            await db.async_migrate_to_v21()
            await db.async_migrate_to_v22()
            await db.async_migrate_to_v23()
            await db.async_migrate_to_v24()
            await db.async_migrate_to_v25()
            _LOGGER.info("v19 thermal rebuild: %s", v19)
        except Exception:
            _LOGGER.exception('v19 thermal rebuild migration failed')
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


async def _async_hydrate_store(
    coordinator: DaikinCycleMLCoordinator,
) -> int:
    """v1.4.2: preload recent cycles. Never raises."""
    if coordinator.db is None:
        return 0
    try:
        rows = await coordinator.db.async_fetch_recent_cycles_for_hydration()
    except Exception:
        _LOGGER.exception("CycleStore hydration failed")
        return 0
    if not isinstance(rows, list):
        return 0
    n = coordinator.store.hydrate_from_rows(
        rows, good_threshold=GOOD_CYCLE_MIN_SCORE
    )
    _LOGGER.info("Hydrated %d cycles from DB", n)
    return n


async def _async_backfill_quality(
    coordinator: DaikinCycleMLCoordinator,
) -> int:
    """v1.4.2: backfill NULL quality scores. Never raises."""
    if coordinator.db is None:
        return 0

    def _scorer(rec: dict[str, Any]) -> int:
        return _score_cycle(rec, None)

    try:
        result = await coordinator.db.async_backfill_quality_scores(_scorer)
    except Exception:
        _LOGGER.exception("quality_score backfill failed")
        return 0
    n = result if isinstance(result, int) else 0
    _LOGGER.info("Backfilled %d quality scores", n)
    return n


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Daikin Cycle ML from a config entry."""
    coordinator = DaikinCycleMLCoordinator(hass, entry)
    try:
        await coordinator.async_reload_user_datasheets()
        clear_datasheet_load_failed(hass, entry.entry_id)
    except Exception as err:
        _LOGGER.exception("user datasheet store load failed")
        raise_datasheet_load_failed(hass, entry.entry_id, str(err))
    await _async_setup_database(hass, coordinator, entry)
    await _async_backfill_quality(coordinator)
    await _async_hydrate_store(coordinator)
    try:
        await coordinator.async_setup_alert_persistence()
    except Exception:
        _LOGGER.exception('Failed to setup alert persistence')
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(
        hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP,
            coordinator._async_handle_shutdown,
        )
    )
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
        await coordinator.async_setup_kmeans_backfill(entry)
    except Exception:
        _LOGGER.exception('Failed to setup kmeans backfill')
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


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unloaded:
        raise HomeAssistantError('Unload failed')
    coordinator = getattr(entry, "runtime_data", None)
    if coordinator is not None:
        try:
            await coordinator._async_flush_accumulators()
        except Exception:  # pragma: no cover
            _LOGGER.exception('Failed to flush accumulators on unload')
        try:
            await coordinator._async_persist_last_alert_sent()
        except Exception:  # pragma: no cover
            _LOGGER.exception('Failed to flush alert persistence on unload')
        for _attr in (
            "_maintenance_unsub",
            "_baseline_save_unsub",
            "_kmeans_unsub",
            "_status_update_unsub",
            "_stooklijn_unsub",
            "_alert_save_unsub",
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
    pass


async def async_remove_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Delete per-entry SQLite DB when the config entry is removed.

    Fixes pre-existing orphan bug: prior to v1.10.0 the shared DB was
    left on disk after entry removal. Now each entry cleans up its own
    file. Legacy `.legacy-<ts>` and backup files are preserved - those
    are user artifacts, not integration state.

    Never raises. Log-and-continue on OSError.
    """
    from .storage.migration import _per_entry_db_path

    db_path = _per_entry_db_path(hass, entry.entry_id)
    if not db_path.exists():
        _LOGGER.debug(
            "per-entry DB %s already absent, nothing to remove", db_path
        )
        return
    try:
        await hass.async_add_executor_job(db_path.unlink)
    except OSError:
        _LOGGER.exception(
            "failed to delete per-entry DB %s on entry removal", db_path
        )
        return
    _LOGGER.info(
        "per-entry DB %s deleted (entry %s removed)",
        db_path,
        entry.entry_id,
    )
