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



def test_schema_rejects_non_notify_target():
    import pytest
    import voluptuous as vol
    from custom_components.daikin_cycle_ml.services import SCHEMA_SEND_TEST
    with pytest.raises(vol.Invalid):
        SCHEMA_SEND_TEST({"target": "light.turn_on"})


def test_schema_accepts_notify_target():
    from custom_components.daikin_cycle_ml.services import SCHEMA_SEND_TEST
    out = SCHEMA_SEND_TEST({"target": "notify.mobile_app_phone"})
    assert out["target"] == "notify.mobile_app_phone"


def test_handler_refuses_option_injected_target(monkeypatch):
    from custom_components.daikin_cycle_ml import services as svc
    bad = MagicMock(); bad.options = {"notify_service": "light.turn_on"}
    monkeypatch.setattr(svc, "_resolve_optional_coordinator", lambda h, e: bad)
    c = MagicMock(); c.data = {"target": None, "entry_id": None, "alert_kind": None}
    r = asyncio.run(svc._handle_send_test_notification(MagicMock(), c))
    assert r["ok"] is False and "notify" in r["error"]


def test_handler_accepts_notify_target(monkeypatch):
    from custom_components.daikin_cycle_ml import services as svc
    coord = MagicMock(); coord.options = {}
    monkeypatch.setattr(svc, "_resolve_optional_coordinator", lambda h, e: coord)
    async def fake(h, t, m): return True
    monkeypatch.setattr(
        "custom_components.daikin_cycle_ml.engine.notification_engine.async_send_notification",
        fake,
    )
    c = MagicMock()
    c.data = {"target": "notify.mobile_app_phone", "entry_id": None, "alert_kind": None, "message": "hi"}
    r = asyncio.run(svc._handle_send_test_notification(MagicMock(), c))
    assert r["ok"] is True



def test_flatten_rejects_non_notify():
    from custom_components.daikin_cycle_ml.config_flow import _flatten_notify_choice
    assert _flatten_notify_choice("light.turn_on") == ""
    assert _flatten_notify_choice("homeassistant.stop") == ""
    assert _flatten_notify_choice({"active_choice": "service", "service": "light.turn_on"}) == ""


def test_flatten_accepts_notify():
    from custom_components.daikin_cycle_ml.config_flow import _flatten_notify_choice
    assert _flatten_notify_choice("notify.mobile_app_phone") == "notify.mobile_app_phone"
    assert _flatten_notify_choice({"active_choice": "entity", "entity": "notify.x"}) == "notify.x"


def test_flatten_empty_passthrough():
    from custom_components.daikin_cycle_ml.config_flow import _flatten_notify_choice
    assert _flatten_notify_choice(None) == ""
    assert _flatten_notify_choice("") == ""
