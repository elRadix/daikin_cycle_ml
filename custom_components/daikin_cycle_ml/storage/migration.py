"""v1.10.0 #75 - per-entry DB file migration. Never raises."""
from __future__ import annotations

import asyncio
import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ..const import (
    DB_FILENAME,
    DB_FILENAME_TEMPLATE,
    DB_LEGACY_MARKER_FILENAME,
    DOMAIN,
)
from ..repairs import (
    clear_legacy_db_multi_entry,
    raise_legacy_db_multi_entry,
)

_LOGGER = logging.getLogger(__name__)
_MIGRATION_LOCK = asyncio.Lock()


@dataclass(frozen=True)
class MigrationResult:
    """Outcome of a per-entry DB migration attempt."""

    status: str
    legacy_path: Path | None = None
    assigned_entry_id: str | None = None
    backup_path: Path | None = None
    n_entries: int = 0
    error: str | None = None


def _storage_dir(hass: HomeAssistant) -> Path:
    return Path(hass.config.config_dir) / ".storage"


def _legacy_db_path(hass: HomeAssistant) -> Path:
    return _storage_dir(hass) / DB_FILENAME


def _marker_path(hass: HomeAssistant) -> Path:
    return _storage_dir(hass) / DB_LEGACY_MARKER_FILENAME


def _per_entry_db_path(hass: HomeAssistant, entry_id: str) -> Path:
    return _storage_dir(hass) / DB_FILENAME_TEMPLATE.format(
        entry_id=entry_id
    )


def _backup_path(hass: HomeAssistant) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return (
        Path(hass.config.config_dir)
        / ".daikin_backups"
        / f"{DB_FILENAME}.backup-{stamp}"
    )


def _write_marker(hass: HomeAssistant, payload: str) -> None:
    try:
        _marker_path(hass).write_text(payload, encoding="utf-8")
    except OSError:
        _LOGGER.exception("failed to write migration marker")


def _backup_legacy_file(
    hass: HomeAssistant, src: Path
) -> Path | None:
    try:
        dst = _backup_path(hass)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        _LOGGER.info("legacy DB backed up to %s", dst)
        return dst
    except OSError:
        _LOGGER.exception("failed to back up legacy DB")
        return None


def _select_oldest_entry(
    entries: list[ConfigEntry],
) -> ConfigEntry | None:
    """Return first entry in registration order (oldest)."""
    if not entries:
        return None
    return entries[0]


async def async_migrate_legacy_db(
    hass: HomeAssistant, entry: ConfigEntry
) -> MigrationResult:
    """Idempotent per-entry DB migration. Never raises."""
    async with _MIGRATION_LOCK:
        try:
            return await _async_migrate_impl(hass, entry)
        except Exception as err:
            _LOGGER.exception(
                "legacy DB migration failed for %s", entry.entry_id
            )
            return MigrationResult(status="error", error=str(err))


async def _async_migrate_impl(
    hass: HomeAssistant, entry: ConfigEntry
) -> MigrationResult:
    if _marker_path(hass).exists():
        return MigrationResult(status="already")
    legacy = _legacy_db_path(hass)
    if not legacy.exists():
        if any(_storage_dir(hass).glob("daikin_cycle_ml_*.db")):
            _write_marker(hass, "v1100:recovered\n")
            _LOGGER.info(
                "legacy DB already per-entry; marker recovered"
            )
            return MigrationResult(status="already")
        _write_marker(hass, "v1100:no-legacy\n")
        return MigrationResult(status="skipped")
    all_entries = hass.config_entries.async_entries(DOMAIN)
    n = len(all_entries)
    backup = _backup_legacy_file(hass, legacy)
    if backup is None:
        return MigrationResult(
            status="error",
            legacy_path=legacy,
            error="backup_failed",
            n_entries=n,
        )
    if n <= 1:
        return _migrate_single(hass, entry, legacy, backup, n)
    return _migrate_multi(
        hass, entry, all_entries, legacy, backup, n
    )


def _migrate_single(
    hass: HomeAssistant,
    entry: ConfigEntry,
    legacy: Path,
    backup: Path,
    n: int,
) -> MigrationResult:
    target = _per_entry_db_path(hass, entry.entry_id)
    if target.exists():
        _LOGGER.warning(
            "single-entry migration: target %s exists, keeping legacy",
            target,
        )
        _write_marker(
            hass, f"v1100:single-skip\nentry={entry.entry_id}\n"
        )
        return MigrationResult(
            status="error",
            legacy_path=legacy,
            backup_path=backup,
            assigned_entry_id=entry.entry_id,
            n_entries=n,
            error="target_exists",
        )
    return _do_rename(
        hass, legacy, target, backup, n, entry.entry_id, single=True
    )


def _migrate_multi(
    hass: HomeAssistant,
    entry: ConfigEntry,
    all_entries: list[ConfigEntry],
    legacy: Path,
    backup: Path,
    n: int,
) -> MigrationResult:
    oldest = _select_oldest_entry(all_entries)
    if oldest is None:
        return MigrationResult(
            status="error",
            legacy_path=legacy,
            backup_path=backup,
            error="no_entries",
            n_entries=n,
        )
    target = _per_entry_db_path(hass, oldest.entry_id)
    if target.exists():
        _LOGGER.warning(
            "multi-entry: target %s exists, keeping legacy", target
        )
        _write_marker(
            hass, f"v1100:multi-skip\nassigned={oldest.entry_id}\n"
        )
        raise_legacy_db_multi_entry(
            hass,
            entry.entry_id,
            assigned_title=oldest.title or oldest.entry_id,
            legacy_path=str(legacy),
            n_entries=n,
        )
        return MigrationResult(
            status="error",
            legacy_path=legacy,
            backup_path=backup,
            assigned_entry_id=oldest.entry_id,
            n_entries=n,
            error="target_exists",
        )
    result = _do_rename(
        hass, legacy, target, backup, n, oldest.entry_id, single=False
    )
    if result.status == "multi":
        raise_legacy_db_multi_entry(
            hass,
            entry.entry_id,
            assigned_title=oldest.title or oldest.entry_id,
            legacy_path=str(legacy),
            n_entries=n,
        )
        _LOGGER.warning(
            "multi-entry legacy assigned to %s (%s)",
            oldest.entry_id,
            oldest.title,
        )
    return result


def _do_rename(
    hass: HomeAssistant,
    legacy: Path,
    target: Path,
    backup: Path,
    n: int,
    assigned_entry_id: str,
    *,
    single: bool,
) -> MigrationResult:
    try:
        orig_size = legacy.stat().st_size
        legacy.replace(target)
        new_size = target.stat().st_size
    except OSError as err:
        _LOGGER.exception("legacy -> per-entry rename failed")
        return MigrationResult(
            status="error",
            legacy_path=legacy,
            backup_path=backup,
            assigned_entry_id=assigned_entry_id,
            n_entries=n,
            error=str(err),
        )
    if new_size != orig_size:
        _LOGGER.error(
            "size mismatch post-rename: %d != %d, rolling back",
            new_size,
            orig_size,
        )
        try:
            target.replace(legacy)
        except OSError:
            _LOGGER.exception("rollback failed")
        return MigrationResult(
            status="error",
            legacy_path=legacy,
            backup_path=backup,
            assigned_entry_id=assigned_entry_id,
            n_entries=n,
            error="size_mismatch",
        )
    status = "single" if single else "multi"
    _write_marker(
        hass, f"v1100:{status}\nentry={assigned_entry_id}\n"
    )
    if single:
        clear_legacy_db_multi_entry(hass, assigned_entry_id)
    _LOGGER.info("legacy DB migrated (%s) to %s", status, target)
    return MigrationResult(
        status=status,
        legacy_path=legacy,
        backup_path=backup,
        assigned_entry_id=assigned_entry_id,
        n_entries=n,
    )
