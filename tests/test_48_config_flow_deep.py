"""Batch 48 -- config_flow wizard + OptionsFlow deep coverage."""
from __future__ import annotations

import asyncio

import pytest
from unittest.mock import MagicMock

from custom_components.daikin_cycle_ml import config_flow as cf


def _hass(source_state=None):
    h = MagicMock()
    h.states = MagicMock()
    h.states.get = MagicMock(return_value=source_state)
    h.config_entries = MagicMock()
    h.services = MagicMock()
    h.services.async_services = MagicMock(return_value={})
    return h


def _wizard(source_state=None):
    flow = cf.DaikinCycleMLConfigFlow()
    flow.hass = _hass(source_state)
    flow._data = {}
    flow._options = {}
    flow._reconfigure_entry = None
    return flow


@pytest.fixture(autouse=True)
def _restore_flow_config_entry_property():
    """Restore class-level config_entry patch leaked by OptionsFlow tests."""
    yield
    if "config_entry" in cf.DaikinCycleMLOptionsFlow.__dict__:
        del cf.DaikinCycleMLOptionsFlow.config_entry


def test_user_step_form_no_state():
    flow = _wizard()
    r = asyncio.run(flow.async_step_user())
    assert r['type'] == 'form'
    assert r['step_id'] == 'user'


def test_user_step_entity_not_found():
    flow = _wizard()
    r = asyncio.run(flow.async_step_user(user_input={
        'source_sensor': 'sensor.missing',
        'model': 'epra12eav3',
    }))
    assert r['type'] == 'form'
    assert 'source_sensor' in (r.get('errors') or {})


def test_user_step_missing_attributes():
    src = MagicMock()
    src.attributes = {}
    flow = _wizard(src)
    r = asyncio.run(flow.async_step_user(user_input={
        'source_sensor': 'sensor.x',
        'model': 'epra12eav3',
    }))
    assert r['type'] == 'form'


def test_user_step_custom_model_redirects():
    src = MagicMock()
    src.attributes = dict.fromkeys(('INV frequency (rps)', 'Operation Mode', 'I/U operation mode', '3way valve(On:DHW_Off:Space)', 'Defrost Operation', 'Leaving water temp. after BUH (R2T)', 'Inlet water temp.(R4T)', 'Outdoor air temp.(R1T)', 'Flow sensor (l/min)', 'Water pump operation', 'BUH Step1', 'BUH Step2', 'LW setpoint (main)'), 1)
    flow = _wizard(src)
    r = asyncio.run(flow.async_step_user(user_input={
        'source_sensor': 'sensor.x',
        'model': 'custom',
    }))
    assert r['type'] == 'form'
    assert r['step_id'] == 'model_custom_info'


def test_user_step_valid_redirects_to_attributes():
    src = MagicMock()
    src.attributes = dict.fromkeys(('INV frequency (rps)', 'Operation Mode', 'I/U operation mode', '3way valve(On:DHW_Off:Space)', 'Defrost Operation', 'Leaving water temp. after BUH (R2T)', 'Inlet water temp.(R4T)', 'Outdoor air temp.(R1T)', 'Flow sensor (l/min)', 'Water pump operation', 'BUH Step1', 'BUH Step2', 'LW setpoint (main)'), 1)
    flow = _wizard(src)
    r = asyncio.run(flow.async_step_user(user_input={
        'source_sensor': 'sensor.x',
        'model': 'epra12eav3',
    }))
    assert r['type'] == 'form'
    assert r['step_id'] == 'attributes'


def test_model_custom_invalid_json():
    flow = _wizard()
    r = asyncio.run(flow.async_step_model_custom(user_input={
        'custom_attribute_map': 'not json',
    }))
    assert r['type'] == 'form'


def test_attributes_step_form():
    src = MagicMock()
    src.attributes = dict.fromkeys(('INV frequency (rps)', 'Operation Mode', 'I/U operation mode', '3way valve(On:DHW_Off:Space)', 'Defrost Operation', 'Leaving water temp. after BUH (R2T)', 'Inlet water temp.(R4T)', 'Outdoor air temp.(R1T)', 'Flow sensor (l/min)', 'Water pump operation', 'BUH Step1', 'BUH Step2', 'LW setpoint (main)'), 1)
    flow = _wizard(src)
    flow._data = {'source_sensor': 'sensor.x', 'model': 'epra12eav3'}
    r = asyncio.run(flow.async_step_attributes())
    assert r['type'] == 'form'


def test_attributes_step_submit_goes_to_cycle():
    flow = _wizard()
    r = asyncio.run(flow.async_step_attributes(user_input={}))
    assert r['type'] == 'form'
    assert r['step_id'] == 'cycle'


def test_cycle_step_form():
    flow = _wizard()
    r = asyncio.run(flow.async_step_cycle())
    assert r['step_id'] == 'cycle'


def test_cycle_step_submit():
    flow = _wizard()
    r = asyncio.run(flow.async_step_cycle(user_input={
        'compressor_rps_threshold': 3,
        'fallback_power_threshold_w': 200,
    }))
    assert r['step_id'] == 'pendulum'


def test_pendulum_step_form():
    flow = _wizard()
    r = asyncio.run(flow.async_step_pendulum())
    assert r['step_id'] == 'pendulum'


def test_pendulum_step_submit():
    flow = _wizard()
    r = asyncio.run(flow.async_step_pendulum(user_input={}))
    assert r['step_id'] == 'quality'


def test_quality_step_form():
    flow = _wizard()
    r = asyncio.run(flow.async_step_quality())
    assert r['step_id'] == 'quality'


def test_quality_step_submit():
    flow = _wizard()
    r = asyncio.run(flow.async_step_quality(user_input={}))
    assert r['step_id'] == 'notifications'


def test_notifications_step_form():
    flow = _wizard()
    r = asyncio.run(flow.async_step_notifications())
    assert r['step_id'] == 'notifications'


def test_notifications_step_submit():
    flow = _wizard()
    r = asyncio.run(flow.async_step_notifications(user_input={}))
    assert r['step_id'] == 'finalize'


def test_finalize_step_form():
    flow = _wizard()
    flow._data = {'source_sensor': 'sensor.x', 'model': 'epra12eav3'}
    r = asyncio.run(flow.async_step_finalize())
    assert r['type'] == 'form'


def test_reconfigure_step_menu():
    flow = _wizard()
    r = asyncio.run(flow.async_step_reconfigure())
    assert r['type'] == 'menu'


def test_options_flow_init_menu():
    flow = cf.DaikinCycleMLOptionsFlow()
    flow.hass = _hass()
    flow.hass.config_entries = MagicMock()
    entry = MagicMock()
    entry.entry_id = 'x'
    entry.options = {}
    entry.data = {}
    entry.runtime_data = None
    type(flow).config_entry = property(lambda self: entry)
    r = asyncio.run(flow.async_step_init())
    assert r['type'] == 'menu'


def test_options_flow_device_form():
    flow = cf.DaikinCycleMLOptionsFlow()
    flow.hass = _hass()
    entry = MagicMock()
    entry.entry_id = 'x'
    entry.options = {}
    entry.data = {}
    entry.runtime_data = None
    type(flow).config_entry = property(lambda self: entry)
    r = asyncio.run(flow.async_step_device())
    assert r['step_id'] == 'device'


def test_options_flow_pendulum_form():
    flow = cf.DaikinCycleMLOptionsFlow()
    flow.hass = _hass()
    entry = MagicMock()
    entry.entry_id = 'x'
    entry.options = {}
    entry.data = {}
    entry.runtime_data = None
    type(flow).config_entry = property(lambda self: entry)
    r = asyncio.run(flow.async_step_pendulum())
    assert r['step_id'] == 'pendulum'


def test_options_flow_quality_form():
    flow = cf.DaikinCycleMLOptionsFlow()
    flow.hass = _hass()
    entry = MagicMock()
    entry.entry_id = 'x'
    entry.options = {}
    entry.data = {}
    entry.runtime_data = None
    type(flow).config_entry = property(lambda self: entry)
    r = asyncio.run(flow.async_step_quality_ml())
    assert r['step_id'] == 'quality_ml'


def test_options_flow_ml_form():
    flow = cf.DaikinCycleMLOptionsFlow()
    flow.hass = _hass()
    entry = MagicMock()
    entry.entry_id = 'x'
    entry.options = {}
    entry.data = {}
    entry.runtime_data = None
    type(flow).config_entry = property(lambda self: entry)
    r = asyncio.run(flow.async_step_quality_ml())
    assert r['step_id'] == 'quality_ml'


def test_options_flow_maintenance_form():
    flow = cf.DaikinCycleMLOptionsFlow()
    flow.hass = _hass()
    entry = MagicMock()
    entry.entry_id = 'x'
    entry.options = {}
    entry.data = {}
    entry.runtime_data = None
    type(flow).config_entry = property(lambda self: entry)
    r = asyncio.run(flow.async_step_advanced())
    assert r['step_id'] == 'advanced'


def test_options_flow_test_notification_form():
    flow = cf.DaikinCycleMLOptionsFlow()
    flow.hass = _hass()
    entry = MagicMock()
    entry.entry_id = 'x'
    entry.options = {}
    entry.data = {}
    entry.runtime_data = None
    type(flow).config_entry = property(lambda self: entry)
    flow._get_coordinator_handle = MagicMock(return_value=None)
    r = asyncio.run(flow.async_step_test_notification())
    assert r['step_id'] == 'test_notification'


def test_options_flow_test_all_form():
    flow = cf.DaikinCycleMLOptionsFlow()
    flow.hass = _hass()
    entry = MagicMock()
    entry.entry_id = 'x'
    entry.options = {}
    entry.data = {}
    entry.runtime_data = None
    type(flow).config_entry = property(lambda self: entry)
    flow._get_coordinator_handle = MagicMock(return_value=None)
    r = asyncio.run(flow.async_step_test_all_notifications())
    assert r['step_id'] == 'test_all_notifications'


def test_options_flow_test_all_submit_no_coord():
    flow = cf.DaikinCycleMLOptionsFlow()
    flow.hass = _hass()
    entry = MagicMock()
    entry.entry_id = 'x'
    entry.options = {}
    entry.data = {}
    entry.runtime_data = None
    type(flow).config_entry = property(lambda self: entry)
    flow._get_coordinator_handle = MagicMock(return_value=None)
    asyncio.run(flow.async_step_test_all_notifications(user_input={}))
    assert flow._test_all_result['status'] == 'no_coordinator'


def test_model_custom_info_submit_routes_to_model_custom():
    """Page A (issue #54): info-only, submit -> existing JSON mapping step."""
    flow = _wizard()
    r = asyncio.run(flow.async_step_model_custom_info())
    assert r['type'] == 'form'
    assert r['step_id'] == 'model_custom_info'
    r = asyncio.run(flow.async_step_model_custom_info(user_input={}))
    assert r['step_id'] == 'model_custom'
