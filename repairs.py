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


async def async_check_repairs(
    hass: HomeAssistant,
    entry_id: str,
    snap: Any,
) -> None:
    """Create/delete repair issues based on snapshot health."""
    try:
        _check_stale(hass, entry_id, snap)
        _check_missing_attrs(hass, entry_id, snap)
    except Exception:  # noqa: BLE001
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
