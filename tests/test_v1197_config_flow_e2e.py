"""v1.19.7 G2: config-flow E2E for uncovered steps."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml import config_flow as cf


def _hass(source_state=None):
    h = MagicMock()
    h.states = MagicMock()
    h.states.get = MagicMock(return_value=source_state)
    h.config_entries = MagicMock()
    h.services = MagicMock()
    h.services.async_services = MagicMock(return_value={})
    return h


def _mk_state(attrs=None):
    s = MagicMock()
    s.attributes = dict(attrs or {})
    return s


def _wizard(source_state=None, data=None):
    flow = cf.DaikinCycleMLConfigFlow()
    flow.hass = _hass(source_state)
    flow._data = dict(data or {})
    flow._options = {}
    flow._reconfigure_entry = None
    return flow


def _mk_entry(**kw):
    e = MagicMock()
    e.entry_id = kw.get("entry_id", "test_entry")
    e.options = dict(kw.get("options") or {})
    e.data = dict(kw.get("data") or {})
    e.runtime_data = kw.get("runtime_data")
    return e


def _options_flow(config_entry):
    flow = cf.DaikinCycleMLOptionsFlow()
    flow.hass = _hass()
    cf.DaikinCycleMLOptionsFlow.config_entry = config_entry
    return flow


@pytest.fixture(autouse=True)
def _restore_options_flow_class():
    yield
    if "config_entry" in cf.DaikinCycleMLOptionsFlow.__dict__:
        del cf.DaikinCycleMLOptionsFlow.config_entry


# ============ async_step_diagnose ============

def test_diagnose_form_when_no_input():
    flow = _wizard()
    r = asyncio.run(flow.async_step_diagnose())
    assert r["type"] == "form"
    assert r["step_id"] == "diagnose"


def test_diagnose_form_with_state():
    state = _mk_state(attrs={"outdoor_temp": 8.0, "leaving_water_temp": 32.0})
    flow = _wizard(source_state=state)
    flow._data["source_sensor"] = "sensor.test"
    flow._data["_smart_available"] = ["outdoor_temp", "leaving_water_temp"]
    r = asyncio.run(flow.async_step_diagnose())
    assert r["type"] == "form"
    assert r["step_id"] == "diagnose"


def test_diagnose_routes_to_attributes_on_input():
    flow = _wizard()
    flow._data["model"] = "some_model_not_custom"
    r = asyncio.run(flow.async_step_diagnose(user_input={"confirm": True}))
    assert r["type"] == "form"
    assert r["step_id"] == "attributes"


# ============ async_step_map_attributes ============

def test_map_attributes_form_when_no_input():
    flow = _wizard()
    r = asyncio.run(flow.async_step_map_attributes())
    assert r["type"] == "form"
    assert r["step_id"] == "map_attributes"


def test_map_attributes_errors_on_unknown_key():
    flow = _wizard()  # no source_state → hass.states.get returns None → available empty
    flow._data["source_sensor"] = "sensor.test"
    from custom_components.daikin_cycle_ml.const import REQUIRED_ATTRIBUTES
    user_input = {c: "sensor.nonexistent" for c in REQUIRED_ATTRIBUTES}
    r = asyncio.run(flow.async_step_map_attributes(user_input=user_input))
    assert r["type"] == "form"
    assert r["step_id"] == "map_attributes"
    errors = r.get("errors") or {}
    assert errors.get("base") == "attribute_not_found"


# ============ OptionsFlow steps ============

def test_notifications_enabled_form():
    flow = _options_flow(_mk_entry())
    r = asyncio.run(flow.async_step_notifications_enabled())
    assert r["type"] == "form"
    assert r["step_id"] == "notifications_enabled"


def test_notifications_quiet_hours_form():
    flow = _options_flow(_mk_entry())
    r = asyncio.run(flow.async_step_notifications_quiet_hours())
    assert r["type"] == "form"
    assert r["step_id"] == "notifications_quiet_hours"


def test_notifications_test_menu_returns_menu():
    flow = _options_flow(_mk_entry())
    r = asyncio.run(flow.async_step_notifications_test_menu())
    assert r["type"] == "menu"
    assert r["step_id"] == "notifications_test_menu"
    opts = list(r.get("menu_options") or [])
    assert "test_notification" in opts
    assert "test_all_notifications" in opts
