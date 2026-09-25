"""Batch 16 tests: notifications review."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml.const import DEFAULT_NOTIFY_SERVICE
from custom_components.daikin_cycle_ml.engine.notification_engine import (
    async_send_notification,
)
from custom_components.daikin_cycle_ml import config_flow as cf
from custom_components.daikin_cycle_ml import services as svc


def _hass_entity():
    h = MagicMock()
    h.states.get = MagicMock(return_value=MagicMock())
    h.services.async_call = AsyncMock()
    return h


def _hass_legacy(services_map):
    h = MagicMock()
    h.states.get = MagicMock(return_value=None)
    h.services.async_services = MagicMock(return_value=services_map)
    h.services.async_call = AsyncMock()
    return h


def test_default_empty():
    assert DEFAULT_NOTIFY_SERVICE == ""


def test_send_entity_path():
    h = _hass_entity()
    ok = asyncio.run(async_send_notification(h, "notify.x", "hi"))
    assert ok is True
    h.services.async_call.assert_awaited()
    args, kwargs = h.services.async_call.call_args
    assert args[0] == "notify"
    assert args[1] == "send_message"
    assert kwargs.get("target") == {"entity_id": "notify.x"}


def test_send_legacy_path():
    h = _hass_legacy({"notify": {"telegram_rachid": {}}})
    ok = asyncio.run(
        async_send_notification(h, "notify.telegram_rachid", "hi")
    )
    assert ok is True
    args, _ = h.services.async_call.call_args
    assert args[0] == "notify"
    assert args[1] == "telegram_rachid"


def test_send_invalid_empty():
    h = MagicMock()
    assert asyncio.run(async_send_notification(h, "", "x")) is False


def test_send_invalid_no_dot():
    h = MagicMock()
    assert asyncio.run(async_send_notification(h, "nodot", "x")) is False


def test_send_service_not_registered():
    h = _hass_legacy({"notify": {}})
    assert asyncio.run(
        async_send_notification(h, "notify.missing", "x")
    ) is False


def test_flatten_variants():
    assert cf._flatten_notify_choice(None) == ""
    assert cf._flatten_notify_choice("notify.x") == "notify.x"
    assert cf._flatten_notify_choice(
        {"active_choice": "entity", "entity": "notify.y"}
) == "notify.y"
    assert cf._flatten_notify_choice(
        {"active_choice": "service", "service": "notify.z"}
) == "notify.z"
    assert cf._flatten_notify_choice({}) == ""


def test_default_choice_string():
    h = MagicMock()
    assert cf._default_notify_choice(h, "notify.a") == "notify.a"
    assert cf._default_notify_choice(h, "") is None
    assert cf._default_notify_choice(h, None) is None


def test_default_choice_empty():
    h = MagicMock()
    assert cf._default_notify_choice(h, "") is None
    assert cf._default_notify_choice(h, None) is None


def test_services_constant():
    assert svc.SERVICE_SEND_TEST_NOTIFICATION == "send_test_notification"
    assert hasattr(svc, '_handle_send_test_notification')


def test_choose_selector_constructs():
    h = MagicMock()
    h.services.async_services = MagicMock(
        return_value={"notify": {"telegram_rachid": {}, "send_message": {}}}
    )
    s = cf._build_notify_selector(h)
    assert s is not None

