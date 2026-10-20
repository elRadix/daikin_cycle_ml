"""v1.9.2 HACS review — security regression tests."""
import asyncio
from unittest.mock import AsyncMock, MagicMock
from custom_components.daikin_cycle_ml.engine.notification_engine import (
    async_send_notification,
)


def _mock_hass():
    h = MagicMock()
    h.states = MagicMock()
    h.states.get.return_value = None
    h.services = MagicMock()
    h.services.async_services.return_value = {}
    h.services.async_call = AsyncMock()
    return h


def _assert_rejected(target):
    h = _mock_hass()
    ok = asyncio.run(async_send_notification(h, target, 'hi'))
    assert ok is False
    assert h.services.async_call.call_count == 0


def test_reject_homeassistant_stop():
    _assert_rejected('homeassistant.stop')


def test_reject_light_turn_on():
    _assert_rejected('light.turn_on')


def test_reject_script_reload():
    _assert_rejected('script.reload')


def test_reject_persistent_notification_create():
    _assert_rejected('persistent_notification.create')


def test_accept_notify_entity_path():
    h = _mock_hass()
    h.states.get.return_value = MagicMock()
    ok = asyncio.run(async_send_notification(h, 'notify.mobile_app_phone', 'hi'))
    assert ok is True
    assert h.services.async_call.call_count == 1
