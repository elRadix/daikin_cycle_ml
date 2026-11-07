"""v1.20.0 #281 Suite #4: services end-to-end via real production path.

Bestaande test_50g_services_deep.py gebruikt hass.data[DOMAIN] lookup
die in productie NIET meer bestaat — productie gaat via
`_resolve_coordinator(hass, entry_id)` -> `entry.runtime_data`.
Die tests wrappen ook in `contextlib.suppress(Exception)` waardoor
echte fouten worden geslikt. Deze suite test het ECHTE pad.

R598: real hass.services.async_call, real _resolve_coordinator, real
_do_* implementations.
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daikin_cycle_ml.const import DOMAIN
from custom_components.daikin_cycle_ml.services import (
    async_register_services,
)


async def _setup_entry_with_coord(hass, entry_id="svc-test"):
    """Register services + create entry with runtime_data coordinator."""
    entry = MockConfigEntry(
        domain=DOMAIN, entry_id=entry_id, data={}, options={},
    )
    entry.add_to_hass(hass)

    coord = MagicMock()
    coord.store = MagicMock()
    coord.store.reset = MagicMock()
    coord.store.cycles = MagicMock(return_value=[
        {"start_ts": time.time() - 100, "mode": "heating",
         "duration_s": 1800, "quality_score": 90},
        {"start_ts": time.time() - 200, "mode": "dhw",
         "duration_s": 600, "quality_score": 85},
    ])
    coord.db = MagicMock()
    coord.db.async_label_cycle = AsyncMock(return_value=True)
    coord.options = {}
    coord.async_emit_test_alert = AsyncMock(return_value="test alert message")
    coord.async_run_maintenance = AsyncMock(return_value={"deleted": 0})

    entry.runtime_data = coord
    await async_register_services(hass)
    return entry, coord


# ============================================================
# 1. reset_counters
# ============================================================


@pytest.mark.asyncio
async def test_reset_counters_via_real_entry(hass) -> None:
    """Service resolves coord via runtime_data and calls store.reset."""
    entry, coord = await _setup_entry_with_coord(hass)
    await hass.services.async_call(
        DOMAIN, "reset_counters",
        {"entry_id": entry.entry_id},
        blocking=True,
    )
    coord.store.reset.assert_called_once()


@pytest.mark.asyncio
async def test_reset_specific_counters(hass) -> None:
    """Optional `counters` list forwards to store.reset."""
    entry, coord = await _setup_entry_with_coord(hass)
    await hass.services.async_call(
        DOMAIN, "reset_counters",
        {"entry_id": entry.entry_id, "counters": ["buh_step1", "defrost"]},
        blocking=True,
    )
    coord.store.reset.assert_called_once_with(["buh_step1", "defrost"])


# ============================================================
# 2. export_cycles
# ============================================================


@pytest.mark.asyncio
async def test_export_cycles_via_real_entry(hass) -> None:
    """Returns dict with format/days/cycles from store."""
    entry, coord = await _setup_entry_with_coord(hass)
    await hass.services.async_call(
        DOMAIN, "export_cycles",
        {"entry_id": entry.entry_id, "days": 30},
        blocking=True,
    )
    coord.store.cycles.assert_called_once()


# ============================================================
# 3. label_cycle
# ============================================================


@pytest.mark.asyncio
async def test_label_cycle_via_real_entry(hass) -> None:
    """Calls coord.db.async_label_cycle(cycle_id, label)."""
    entry, coord = await _setup_entry_with_coord(hass)
    await hass.services.async_call(
        DOMAIN, "label_cycle",
        {"entry_id": entry.entry_id, "cycle_id": 42, "label": "good"},
        blocking=True,
    )
    coord.db.async_label_cycle.assert_awaited_once_with(42, "good")


# ============================================================
# 4. send_test_notification via alert_kind
# ============================================================


@pytest.mark.asyncio
async def test_send_test_notification_via_real_entry(hass) -> None:
    """alert_kind path: coord.async_emit_test_alert is called."""
    entry, coord = await _setup_entry_with_coord(hass)
    await hass.services.async_call(
        DOMAIN, "send_test_notification",
        {"entry_id": entry.entry_id, "alert_kind": "short_run"},
        blocking=True,
    )
    coord.async_emit_test_alert.assert_awaited_once()


# ============================================================
# 5. run_maintenance
# ============================================================


@pytest.mark.asyncio
async def test_run_maintenance_via_real_entry(hass) -> None:
    """coord.async_run_maintenance called with force=True."""
    entry, coord = await _setup_entry_with_coord(hass)
    await hass.services.async_call(
        DOMAIN, "run_maintenance",
        {"entry_id": entry.entry_id},
        blocking=True,
    )
    coord.async_run_maintenance.assert_awaited_once()
    kw = coord.async_run_maintenance.call_args.kwargs
    assert kw["force"] is True


# ============================================================
# 6. R580: unknown entry raises (no silent fail)
# ============================================================


@pytest.mark.asyncio
async def test_unknown_entry_raises(hass) -> None:
    """Unknown entry_id -> HomeAssistantError, not silent."""
    await async_register_services(hass)
    with pytest.raises(HomeAssistantError, match="Unknown config entry"):
        await hass.services.async_call(
            DOMAIN, "reset_counters",
            {"entry_id": "does-not-exist"},
            blocking=True,
        )


# ============================================================
# 7. R580: missing coordinator raises
# ============================================================


@pytest.mark.asyncio
async def test_missing_coordinator_raises(hass) -> None:
    """Entry exists but runtime_data=None -> HomeAssistantError."""
    entry = MockConfigEntry(
        domain=DOMAIN, entry_id="no-coord", data={}, options={},
    )
    entry.add_to_hass(hass)
    entry.runtime_data = None
    await async_register_services(hass)
    with pytest.raises(HomeAssistantError, match="Coordinator not ready"):
        await hass.services.async_call(
            DOMAIN, "reset_counters",
            {"entry_id": "no-coord"},
            blocking=True,
        )
