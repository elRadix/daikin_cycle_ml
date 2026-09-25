"""Tests for repairs (Batch 6b-3b)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
from custom_components.daikin_cycle_ml.repairs import (
    ISSUE_MISSING_ATTRS,
    ISSUE_SOURCE_STALE,
    async_check_repairs,
)

_MOD = "custom_components.daikin_cycle_ml.repairs"


@pytest.fixture
def hass():
    return MagicMock()


async def test_stale_creates_issue(hass):
    snap = DataSnapshot(last_success_ts=1.0)  # long ago
    with patch(f"{_MOD}.ir.async_create_issue") as m_create, \
         patch(f"{_MOD}.ir.async_delete_issue") as m_delete:
        await async_check_repairs(hass, "e1", snap)
        assert m_create.called
        created_ids = [c.args[2] for c in m_create.call_args_list]
        assert f"{ISSUE_SOURCE_STALE}_e1" in created_ids
        delete_ids = [c.args[2] for c in m_delete.call_args_list]
        assert f"{ISSUE_SOURCE_STALE}_e1" not in delete_ids


async def test_fresh_deletes_stale_issue(hass):
    import time
    snap = DataSnapshot(last_success_ts=time.time())
    with patch(f"{_MOD}.ir.async_create_issue") as m_create, \
         patch(f"{_MOD}.ir.async_delete_issue") as m_delete:
        await async_check_repairs(hass, "e1", snap)
        delete_ids = [c.args[2] for c in m_delete.call_args_list]
        assert f"{ISSUE_SOURCE_STALE}_e1" in delete_ids


async def test_zero_last_success_does_not_create_stale(hass):
    snap = DataSnapshot(last_success_ts=0.0)
    with patch(f"{_MOD}.ir.async_create_issue") as m_create, \
         patch(f"{_MOD}.ir.async_delete_issue"):
        await async_check_repairs(hass, "e1", snap)
        create_ids = [c.args[2] for c in m_create.call_args_list]
        assert f"{ISSUE_SOURCE_STALE}_e1" not in create_ids


async def test_missing_attrs_creates_issue(hass):
    snap = DataSnapshot(last_success_ts=1.0, missing_attrs=["a", "b"])
    with patch(f"{_MOD}.ir.async_create_issue") as m_create, \
         patch(f"{_MOD}.ir.async_delete_issue"):
        await async_check_repairs(hass, "e1", snap)
        create_ids = [c.args[2] for c in m_create.call_args_list]
        assert f"{ISSUE_MISSING_ATTRS}_e1" in create_ids


async def test_no_missing_deletes_issue(hass):
    snap = DataSnapshot(last_success_ts=1.0, missing_attrs=[])
    with patch(f"{_MOD}.ir.async_create_issue"), \
         patch(f"{_MOD}.ir.async_delete_issue") as m_delete:
        await async_check_repairs(hass, "e1", snap)
        delete_ids = [c.args[2] for c in m_delete.call_args_list]
        assert f"{ISSUE_MISSING_ATTRS}_e1" in delete_ids


async def test_missing_attrs_placeholders(hass):
    snap = DataSnapshot(last_success_ts=1.0, missing_attrs=["a", "b", "c"])
    with patch(f"{_MOD}.ir.async_create_issue") as m_create, \
         patch(f"{_MOD}.ir.async_delete_issue"):
        await async_check_repairs(hass, "e1", snap)
        calls = [c for c in m_create.call_args_list
                 if c.args[2] == f"{ISSUE_MISSING_ATTRS}_e1"]
        assert calls
        assert calls[0].kwargs["translation_placeholders"] == {"count": "3"}


async def test_never_raises_on_registry_error(hass):
    snap = DataSnapshot(last_success_ts=1.0, missing_attrs=["a"])
    with patch(f"{_MOD}.ir.async_create_issue",
               side_effect=RuntimeError("boom")), \
         patch(f"{_MOD}.ir.async_delete_issue"):
        # must not raise
        await async_check_repairs(hass, "e1", snap)


async def test_stale_and_missing_both_handled(hass):
    snap = DataSnapshot(last_success_ts=1.0, missing_attrs=["x"])
    with patch(f"{_MOD}.ir.async_create_issue") as m_create, \
         patch(f"{_MOD}.ir.async_delete_issue"):
        await async_check_repairs(hass, "e1", snap)
        ids = {c.args[2] for c in m_create.call_args_list}
        assert f"{ISSUE_SOURCE_STALE}_e1" in ids
        assert f"{ISSUE_MISSING_ATTRS}_e1" in ids


async def test_entry_id_scoped(hass):
    snap = DataSnapshot(last_success_ts=1.0, missing_attrs=["a"])
    with patch(f"{_MOD}.ir.async_create_issue") as m_create, \
         patch(f"{_MOD}.ir.async_delete_issue"):
        await async_check_repairs(hass, "unique-42", snap)
        ids = {c.args[2] for c in m_create.call_args_list}
        assert all("unique-42" in i for i in ids)
