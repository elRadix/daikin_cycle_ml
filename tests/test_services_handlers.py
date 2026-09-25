"""Tests for services handlers + resolve (Batch 8d)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.daikin_cycle_ml.services import (
    SCHEMA_RESET,
    SERVICE_RESET_COUNTERS,
    _handle_export_cycles,
    _handle_label_cycle,
    _handle_recompute_baseline,
    _handle_reset_counters,
    _resolve_coordinator,
    async_register_services,
)
from custom_components.daikin_cycle_ml.storage.store import CycleStore


def _hass_with_entry(entry):
    hass = MagicMock()
    hass.config_entries.async_get_entry = MagicMock(return_value=entry)
    return hass


def _coord():
    c = MagicMock()
    c.store = CycleStore()
    c.db = MagicMock()
    async def fake_label(cid, lbl):
        return True
    c.db.async_label_cycle = fake_label
    return c


def _call(data):
    call = MagicMock()
    call.data = data
    return call


# ---------- _resolve_coordinator ----------

def test_resolve_unknown_entry_raises():
    hass = _hass_with_entry(None)
    with pytest.raises(HomeAssistantError):
        _resolve_coordinator(hass, "missing")


def test_resolve_no_runtime_data_raises():
    entry = MagicMock()
    entry.runtime_data = None
    hass = _hass_with_entry(entry)
    with pytest.raises(HomeAssistantError):
        _resolve_coordinator(hass, "e1")


def test_resolve_returns_coordinator():
    entry = MagicMock()
    coord = _coord()
    entry.runtime_data = coord
    hass = _hass_with_entry(entry)
    assert _resolve_coordinator(hass, "e1") is coord


# ---------- handlers ----------

async def test_handle_reset_counters():
    entry = MagicMock()
    entry.runtime_data = _coord()
    hass = _hass_with_entry(entry)
    call = _call({"entry_id": "e1"})
    out = await _handle_reset_counters(hass, call)
    assert out["reset"] is True


async def test_handle_export_cycles():
    entry = MagicMock()
    entry.runtime_data = _coord()
    hass = _hass_with_entry(entry)
    call = _call({"entry_id": "e1", "days": 30, "format": "json"})
    out = await _handle_export_cycles(hass, call)
    assert out["format"] == "json"


async def test_handle_label_cycle():
    entry = MagicMock()
    entry.runtime_data = _coord()
    hass = _hass_with_entry(entry)
    call = _call({"entry_id": "e1", "cycle_id": 5, "label": "good"})
    out = await _handle_label_cycle(hass, call)
    assert out["labeled"] is True


async def test_handle_recompute_baseline():
    entry = MagicMock()
    entry.runtime_data = _coord()
    hass = _hass_with_entry(entry)
    call = _call({"entry_id": "e1", "days": 7})
    out = await _handle_recompute_baseline(hass, call)
    assert out["days"] == 7
    assert out["computed"] is False


# ---------- registration idempotence ----------

async def test_register_short_circuits_when_present():
    hass = MagicMock()
    hass.services.has_service = MagicMock(return_value=True)
    await async_register_services(hass)
    # already registered -> no async_register calls
    hass.services.async_register.assert_not_called()
