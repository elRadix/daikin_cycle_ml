"""Repairs support for Daikin Cycle ML (Batch 6b-3b). Never raises."""
from __future__ import annotations

import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN, UPDATE_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)

ISSUE_SOURCE_STALE = "source_stale"
ISSUE_MISSING_ATTRS = "missing_attrs"
STALE_FACTOR = 2.0
ISSUE_DB_CORRUPT = "db_corrupt"
ISSUE_NOTIFY_FAILED = "notify_failed"
ISSUE_MIGRATION_FAILED = "migration_failed"
NOTIFY_FAIL_THRESHOLD = 3
ISSUE_DATASHEET_IMPORT_INVALID = "datasheet_import_invalid"
ISSUE_DATASHEET_SCHEMA_UNKNOWN = "datasheet_schema_unknown"
ISSUE_DATASHEET_LOAD_FAILED = "datasheet_load_failed"


async def async_check_repairs(
    hass: HomeAssistant,
    entry_id: str,
    snap: Any,
    coordinator: Any = None,
) -> None:
    """Create/delete repair issues based on snapshot health."""
    try:
        _check_stale(hass, entry_id, snap)
        _check_missing_attrs(hass, entry_id, snap)
        if coordinator is not None:
            _check_db_corrupt(hass, entry_id, coordinator)
            _check_notify_failed(hass, entry_id, coordinator)
            _check_migration_failed(hass, entry_id, coordinator)
    except Exception:
        _LOGGER.exception("Repairs check failed for %s", entry_id)


def _check_stale(hass: HomeAssistant, entry_id: str, snap: Any) -> None:
    issue_id = f"{ISSUE_SOURCE_STALE}_{entry_id}"
    last = float(getattr(snap, "last_success_ts", 0.0) or 0.0)
    now = time.time()
    stale = last > 0 and (now - last) > STALE_FACTOR * UPDATE_INTERVAL_SECONDS
    if stale:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_SOURCE_STALE,
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)


def _check_missing_attrs(hass: HomeAssistant, entry_id: str, snap: Any) -> None:
    issue_id = f"{ISSUE_MISSING_ATTRS}_{entry_id}"
    missing = list(getattr(snap, "missing_attrs", []) or [])
    if missing:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_MISSING_ATTRS,
            translation_placeholders={"count": str(len(missing))},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)


def _check_db_corrupt(hass: HomeAssistant, entry_id: str, coord: Any) -> None:
    issue_id = f"{ISSUE_DB_CORRUPT}_{entry_id}"
    ok = bool(getattr(coord, "_db_integrity_ok", True))
    if ok:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key=ISSUE_DB_CORRUPT,
    )


def _check_notify_failed(hass: HomeAssistant, entry_id: str, coord: Any) -> None:
    issue_id = f"{ISSUE_NOTIFY_FAILED}_{entry_id}"
    streak = int(getattr(coord, "_notify_fail_streak", 0) or 0)
    if streak < NOTIFY_FAIL_THRESHOLD:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return
    target = str(getattr(coord, "_notify_fail_target", "") or "")
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_NOTIFY_FAILED,
        translation_placeholders={"count": str(streak), "target": target},
    )


def _check_migration_failed(hass: HomeAssistant, entry_id: str, coord: Any) -> None:
    issue_id = f"{ISSUE_MIGRATION_FAILED}_{entry_id}"
    err = getattr(coord, "_migration_error", None)
    if not err:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_MIGRATION_FAILED,
        translation_placeholders={"error": str(err)[:120]},
    )


def raise_datasheet_import_invalid(
    hass: HomeAssistant, entry_id: str, errors: list[str]
) -> None:
    """Create import_invalid issue with error summary as placeholder."""
    issue_id = f"{ISSUE_DATASHEET_IMPORT_INVALID}_{entry_id}"
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_DATASHEET_IMPORT_INVALID,
        translation_placeholders={"count": str(len(errors)), "first": errors[0][:120] if errors else ""},
    )


def clear_datasheet_import_invalid(hass: HomeAssistant, entry_id: str) -> None:
    ir.async_delete_issue(
        hass, DOMAIN, f"{ISSUE_DATASHEET_IMPORT_INVALID}_{entry_id}"
    )


def raise_datasheet_schema_unknown(
    hass: HomeAssistant, entry_id: str, found: object
) -> None:
    issue_id = f"{ISSUE_DATASHEET_SCHEMA_UNKNOWN}_{entry_id}"
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key=ISSUE_DATASHEET_SCHEMA_UNKNOWN,
        translation_placeholders={"found": str(found)},
    )


def clear_datasheet_schema_unknown(hass: HomeAssistant, entry_id: str) -> None:
    ir.async_delete_issue(
        hass, DOMAIN, f"{ISSUE_DATASHEET_SCHEMA_UNKNOWN}_{entry_id}"
    )


def raise_datasheet_load_failed(
    hass: HomeAssistant, entry_id: str, reason: str
) -> None:
    issue_id = f"{ISSUE_DATASHEET_LOAD_FAILED}_{entry_id}"
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key=ISSUE_DATASHEET_LOAD_FAILED,
        translation_placeholders={"reason": reason[:120]},
    )


def clear_datasheet_load_failed(hass: HomeAssistant, entry_id: str) -> None:
    ir.async_delete_issue(
        hass, DOMAIN, f"{ISSUE_DATASHEET_LOAD_FAILED}_{entry_id}"
    )

