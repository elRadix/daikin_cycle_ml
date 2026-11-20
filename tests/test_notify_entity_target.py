"""HA 2025.11+: notify targets can be entities (Telegram chats, ...).

notify.telegram_<chat> is then an entity, sent to with notify.send_message,
not a legacy notify.<name> service ("notify service ... not found").
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml import config_flow as cf
from custom_components.daikin_cycle_ml import coordinator as co
from homeassistant.exceptions import ServiceNotFound


def _coord(*, has_service: bool, entity: bool):
    c = co.DaikinCycleMLCoordinator.__new__(co.DaikinCycleMLCoordinator)
    c.hass = MagicMock()
    c.hass.services.has_service = MagicMock(return_value=has_service)
    c.hass.states.get = MagicMock(return_value=SimpleNamespace() if entity else None)
    c.hass.services.async_call = AsyncMock()
    c._notify_fail_streak = 0
    c._notify_fail_target = ""
    c._notify_fail_logged = set()
    return c


@pytest.mark.asyncio
async def test_entity_target_uses_send_message():
    c = _coord(has_service=False, entity=True)
    assert await c._dispatch_notify("notify.telegram_chat", "hello") is True
    c.hass.services.async_call.assert_awaited_once_with(
        "notify", "send_message",
        {"message": "hello", "entity_id": "notify.telegram_chat"}, blocking=False,
    )


@pytest.mark.asyncio
async def test_legacy_service_still_called_directly():
    c = _coord(has_service=True, entity=True)
    assert await c._dispatch_notify("notify.mobile_app_x", "hi") is True
    c.hass.services.async_call.assert_awaited_once_with(
        "notify", "mobile_app_x", {"message": "hi"}, blocking=False,
    )


@pytest.mark.asyncio
async def test_neither_service_nor_entity_reports_not_found():
    c = _coord(has_service=False, entity=False)
    c.hass.services.async_call = AsyncMock(side_effect=ServiceNotFound("notify", "gone"))
    assert await c._dispatch_notify("notify.gone", "x") is False
    assert c._notify_fail_target == "notify.gone"


@pytest.mark.asyncio
async def test_non_notify_domain_untouched():
    c = _coord(has_service=False, entity=True)
    assert await c._dispatch_notify("script.alert_me", "x") is True
    c.hass.services.async_call.assert_awaited_once_with(
        "script", "alert_me", {"message": "x"}, blocking=False,
    )


def test_selector_lists_entities_then_legacy_services():
    h = MagicMock()
    h.states.async_entity_ids = MagicMock(return_value=["notify.telegram_chat", "notify.plain"])
    named = SimpleNamespace(attributes={"friendly_name": "Telegram chat"})
    h.states.get = MagicMock(side_effect=lambda e: named if e == "notify.telegram_chat"
                             else SimpleNamespace(attributes={}))
    h.services.async_services = MagicMock(return_value={
        "notify": {"mobile_app_x": {}, "send_message": {}, "plain": {}},
    })
    opts = cf._build_notify_selector(h).config["options"]
    assert [o["value"] for o in opts] == [
        "notify.plain", "notify.telegram_chat", "notify.mobile_app_x",
    ]
    assert opts[1]["label"] == "Telegram chat (notify.telegram_chat)"
    assert opts[0]["label"] == "notify.plain"


def test_entity_options_without_states():
    h = MagicMock()
    h.states.async_entity_ids = MagicMock(side_effect=RuntimeError)
    assert cf._notify_entity_options(h) == []
    h2 = MagicMock()
    h2.states.async_entity_ids = MagicMock(return_value=["notify.gone"])
    h2.states.get = MagicMock(return_value=None)
    assert cf._notify_entity_options(h2) == [{"value": "notify.gone", "label": "notify.gone"}]
