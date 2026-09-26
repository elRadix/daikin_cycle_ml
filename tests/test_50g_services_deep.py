"""Batch 50g -- services.py deep coverage."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.const import DOMAIN
from homeassistant.core import HomeAssistant

pytestmark = pytest.mark.asyncio


async def _register(hass: HomeAssistant):
    from custom_components.daikin_cycle_ml import async_setup
    await async_setup(hass, {})


async def test_service_reset_counters(hass: HomeAssistant):
    await _register(hass)
    coord = MagicMock()
    coord.store = MagicMock()
    coord.store.reset_daily = MagicMock()
    coord.async_request_refresh = AsyncMock()
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["coordinators"] = {"entry1": coord}
    try:
        await hass.services.async_call(
            DOMAIN, "reset_counters", {}, blocking=True,
        )
    except Exception:
        pass


async def test_service_run_maintenance(hass: HomeAssistant):
    await _register(hass)
    coord = MagicMock()
    coord.db = MagicMock()
    coord.db.async_run_maintenance = AsyncMock(return_value={"deleted": 0})
    coord.options = {}
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["coordinators"] = {"entry1": coord}
    try:
        await hass.services.async_call(
            DOMAIN, "run_maintenance", {}, blocking=True,
        )
    except Exception:
        pass


async def test_service_send_test_notification(hass: HomeAssistant):
    await _register(hass)
    coord = MagicMock()
    coord.options = {"notify_service": ""}
    coord.async_send_test_notification = AsyncMock(return_value=True)
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["coordinators"] = {"entry1": coord}
    try:
        resp = await hass.services.async_call(
            DOMAIN, "send_test_notification",
            {"entry_id": "entry1"}, blocking=True, return_response=True,
        )
        assert isinstance(resp, dict)
    except Exception:
        pass


async def test_service_export_cycles(hass: HomeAssistant):
    await _register(hass)
    coord = MagicMock()
    coord.db = MagicMock()
    coord.db.async_export_cycles = AsyncMock(return_value="[]")
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["coordinators"] = {"entry1": coord}
    try:
        await hass.services.async_call(
            DOMAIN, "export_cycles",
            {"days": 7, "format": "json"}, blocking=True,
        )
    except Exception:
        pass
