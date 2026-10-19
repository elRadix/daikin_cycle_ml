"""Tests for services handlers + resolve (Batch 8d)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml.services import (
    _handle_export_cycles,
    _handle_label_cycle,
    _handle_recompute_baseline,
    _handle_reset_counters,
    _resolve_coordinator,
    async_register_services,
)
from custom_components.daikin_cycle_ml.storage.store import CycleStore
from homeassistant.exceptions import HomeAssistantError


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


# ============ C4b (I2): recompute_kmeans service ============

@pytest.mark.asyncio
async def test_handle_recompute_kmeans_success(monkeypatch):
    from custom_components.daikin_cycle_ml.services import _handle_recompute_kmeans
    from unittest.mock import AsyncMock

    coord = MagicMock()
    coord.async_run_kmeans = AsyncMock(return_value={"ok": True, "n": 47, "k": 3})
    entry = MagicMock()
    entry.runtime_data = coord
    hass = _hass_with_entry(entry)
    # Mock async_create_task to run eagerly and avoid dangling tasks
    notified = []
    def fake_create_task(coro):
        notified.append(coro)
    hass.async_create_task = fake_create_task
    hass.services.async_call = MagicMock()

    call = _call({"entry_id": "e1"})
    result = await _handle_recompute_kmeans(hass, call)

    assert result == {"ok": True, "n": 47, "k": 3}
    coord.async_run_kmeans.assert_awaited_once_with(days=7)
    assert len(notified) == 1


@pytest.mark.asyncio
async def test_handle_recompute_kmeans_failure_reason(monkeypatch):
    from custom_components.daikin_cycle_ml.services import _handle_recompute_kmeans
    from unittest.mock import AsyncMock

    coord = MagicMock()
    coord.async_run_kmeans = AsyncMock(return_value={"ok": False, "reason": "too_few", "n": 2})
    entry = MagicMock()
    entry.runtime_data = coord
    hass = _hass_with_entry(entry)
    notified = []
    hass.async_create_task = lambda coro: notified.append(coro)
    hass.services.async_call = MagicMock()

    result = await _handle_recompute_kmeans(hass, _call({"entry_id": "e1"}))
    assert result["ok"] is False
    assert result["reason"] == "too_few"
    assert len(notified) == 1


@pytest.mark.asyncio
async def test_handle_recompute_kmeans_custom_days():
    from custom_components.daikin_cycle_ml.services import _handle_recompute_kmeans
    from unittest.mock import AsyncMock

    coord = MagicMock()
    coord.async_run_kmeans = AsyncMock(return_value={"ok": True, "n": 10, "k": 3})
    entry = MagicMock()
    entry.runtime_data = coord
    hass = _hass_with_entry(entry)
    hass.async_create_task = lambda c: None
    hass.services.async_call = MagicMock()

    await _handle_recompute_kmeans(hass, _call({"entry_id": "e1", "days": 14}))
    coord.async_run_kmeans.assert_awaited_once_with(days=14)


@pytest.mark.asyncio
async def test_handle_recompute_kmeans_unknown_entry():
    from custom_components.daikin_cycle_ml.services import _handle_recompute_kmeans
    hass = MagicMock()
    hass.config_entries.async_get_entry = MagicMock(return_value=None)

    with pytest.raises(HomeAssistantError):
        await _handle_recompute_kmeans(hass, _call({"entry_id": "missing"}))


@pytest.mark.asyncio
async def test_handle_recompute_kmeans_notification_failure_swallowed():
    from custom_components.daikin_cycle_ml.services import _handle_recompute_kmeans
    from unittest.mock import AsyncMock

    coord = MagicMock()
    coord.async_run_kmeans = AsyncMock(return_value={"ok": True, "n": 5, "k": 3})
    entry = MagicMock()
    entry.runtime_data = coord
    hass = _hass_with_entry(entry)
    def boom(coro):
        raise RuntimeError("create_task boom")
    hass.async_create_task = boom
    hass.services.async_call = MagicMock()

    # Should not raise despite notification failure
    result = await _handle_recompute_kmeans(hass, _call({"entry_id": "e1"}))
    assert result == {"ok": True, "n": 5, "k": 3}


def test_schema_recompute_kmeans_valid():
    from custom_components.daikin_cycle_ml.services import SCHEMA_RECOMPUTE_KMEANS
    data = SCHEMA_RECOMPUTE_KMEANS({"entry_id": "e1", "days": 14})
    assert data["entry_id"] == "e1"
    assert data["days"] == 14


def test_schema_recompute_kmeans_default_days():
    from custom_components.daikin_cycle_ml.services import SCHEMA_RECOMPUTE_KMEANS
    data = SCHEMA_RECOMPUTE_KMEANS({"entry_id": "e1"})
    assert data["days"] == 7


@pytest.mark.asyncio
async def test_register_services_includes_recompute_kmeans():
    from custom_components.daikin_cycle_ml.services import (
        SERVICE_RECOMPUTE_KMEANS,
        async_register_services,
    )
    from custom_components.daikin_cycle_ml.const import DOMAIN
    from unittest.mock import MagicMock

    hass = MagicMock()
    hass.services.has_service = MagicMock(return_value=False)
    hass.services.async_register = MagicMock()

    await async_register_services(hass)

    names = [c.args[1] for c in hass.services.async_register.call_args_list if len(c.args) >= 2]
    assert SERVICE_RECOMPUTE_KMEANS in names
