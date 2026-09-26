"""Batch 46 -- async_send_notification coverage."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml.engine.notification_engine import (
    async_send_notification,
)


def _hass_with_entity():
    h = MagicMock()
    h.states.get = MagicMock(return_value=MagicMock())
    h.services.async_call = AsyncMock()
    return h


def _hass_no_entity(services_map=None):
    h = MagicMock()
    h.states.get = MagicMock(return_value=None)
    h.services.async_services = MagicMock(return_value=services_map or {})
    h.services.async_call = AsyncMock()
    return h


def test_invalid_empty():
    h = MagicMock()
    assert asyncio.run(async_send_notification(h, '', 'x')) is False


def test_invalid_no_dot():
    h = MagicMock()
    assert asyncio.run(async_send_notification(h, 'nodot', 'x')) is False


def test_invalid_empty_name():
    h = MagicMock()
    assert asyncio.run(async_send_notification(h, 'notify.', 'x')) is False


def test_entity_path_success():
    h = _hass_with_entity()
    ok = asyncio.run(async_send_notification(h, 'notify.x', 'hi'))
    assert ok is True
    args, kwargs = h.services.async_call.call_args
    assert args[0] == 'notify'
    assert args[1] == 'send_message'
    assert kwargs['target'] == {'entity_id': 'notify.x'}


def test_entity_path_exception_returns_false():
    h = _hass_with_entity()
    h.services.async_call = AsyncMock(side_effect=RuntimeError('x'))
    assert asyncio.run(async_send_notification(h, 'notify.x', 'hi')) is False


def test_state_get_raises():
    h = MagicMock()
    h.states.get = MagicMock(side_effect=RuntimeError('state fail'))
    h.services.async_services = MagicMock(return_value={})
    h.services.async_call = AsyncMock()
    assert asyncio.run(async_send_notification(h, 'notify.x', 'hi')) is False


def test_legacy_path_registered():
    h = _hass_no_entity({'notify': {'telegram_bot': {}}})
    ok = asyncio.run(async_send_notification(h, 'notify.telegram_bot', 'hi'))
    assert ok is True
    args, _ = h.services.async_call.call_args
    assert args[0] == 'notify'
    assert args[1] == 'telegram_bot'


def test_legacy_path_not_registered():
    h = _hass_no_entity({'notify': {}})
    assert asyncio.run(async_send_notification(h, 'notify.missing', 'hi')) is False


def test_legacy_async_services_raises():
    h = _hass_no_entity()
    h.services.async_services = MagicMock(side_effect=RuntimeError('fail'))
    assert asyncio.run(async_send_notification(h, 'notify.x', 'hi')) is False


def test_generic_domain_fallback():
    h = _hass_no_entity({})
    ok = asyncio.run(async_send_notification(h, 'persistent_notification.create', 'hi'))
    assert ok is True


def test_generic_domain_fallback_exception():
    h = _hass_no_entity({})
    h.services.async_call = AsyncMock(side_effect=RuntimeError('x'))
    assert asyncio.run(async_send_notification(h, 'persistent_notification.create', 'hi')) is False
