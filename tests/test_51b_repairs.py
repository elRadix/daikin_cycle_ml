"""Batch 51b -- repair trigger tests."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.helpers import issue_registry as ir

from custom_components.daikin_cycle_ml.const import DOMAIN
from custom_components.daikin_cycle_ml.repairs import (
    ISSUE_DB_CORRUPT,
    ISSUE_MIGRATION_FAILED,
    ISSUE_NOTIFY_FAILED,
    NOTIFY_FAIL_THRESHOLD,
    async_check_repairs,
)

ENTRY_ID = "test_entry_51b"


def _snap():
    s = MagicMock()
    s.last_success_ts = 9999999999.0
    s.missing_attrs = []
    return s


def _coord(**kw):
    c = MagicMock()
    c._db_integrity_ok = True
    c._notify_fail_streak = 0
    c._notify_fail_target = ""
    c._migration_error = None
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def _has(hass, issue_type):
    reg = ir.async_get(hass)
    return reg.async_get_issue(DOMAIN, issue_type + "_" + ENTRY_ID) is not None


async def test_db_corrupt_creates_issue(hass):
    await async_check_repairs(hass, ENTRY_ID, _snap(), _coord(_db_integrity_ok=False))
    assert _has(hass, ISSUE_DB_CORRUPT)


async def test_db_corrupt_resolves(hass):
    await async_check_repairs(hass, ENTRY_ID, _snap(), _coord(_db_integrity_ok=False))
    assert _has(hass, ISSUE_DB_CORRUPT)
    await async_check_repairs(hass, ENTRY_ID, _snap(), _coord(_db_integrity_ok=True))
    assert not _has(hass, ISSUE_DB_CORRUPT)


async def test_notify_failed_creates_issue(hass):
    await async_check_repairs(
        hass, ENTRY_ID, _snap(),
        _coord(_notify_fail_streak=NOTIFY_FAIL_THRESHOLD, _notify_fail_target="notify.x"),
    )
    assert _has(hass, ISSUE_NOTIFY_FAILED)


async def test_notify_failed_below_threshold(hass):
    await async_check_repairs(
        hass, ENTRY_ID, _snap(),
        _coord(_notify_fail_streak=NOTIFY_FAIL_THRESHOLD - 1),
    )
    assert not _has(hass, ISSUE_NOTIFY_FAILED)


async def test_notify_failed_resolves(hass):
    await async_check_repairs(
        hass, ENTRY_ID, _snap(),
        _coord(_notify_fail_streak=NOTIFY_FAIL_THRESHOLD),
    )
    assert _has(hass, ISSUE_NOTIFY_FAILED)
    await async_check_repairs(hass, ENTRY_ID, _snap(), _coord(_notify_fail_streak=0))
    assert not _has(hass, ISSUE_NOTIFY_FAILED)


async def test_migration_failed_creates_issue(hass):
    await async_check_repairs(
        hass, ENTRY_ID, _snap(),
        _coord(_migration_error="boom"),
    )
    assert _has(hass, ISSUE_MIGRATION_FAILED)


async def test_migration_failed_resolves(hass):
    await async_check_repairs(
        hass, ENTRY_ID, _snap(),
        _coord(_migration_error="boom"),
    )
    assert _has(hass, ISSUE_MIGRATION_FAILED)
    await async_check_repairs(hass, ENTRY_ID, _snap(), _coord(_migration_error=None))
    assert not _has(hass, ISSUE_MIGRATION_FAILED)


async def test_coordinator_optional(hass):
    await async_check_repairs(hass, ENTRY_ID, _snap())
    assert not _has(hass, ISSUE_DB_CORRUPT)
    assert not _has(hass, ISSUE_NOTIFY_FAILED)
    assert not _has(hass, ISSUE_MIGRATION_FAILED)
