"""Batch 49 -- config_flow remaining coverage."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml import config_flow as cf


def _hass(source_state=None):
    h = MagicMock()
    h.states = MagicMock()
    h.states.get = MagicMock(return_value=source_state)
    h.config_entries = MagicMock()
    h.services = MagicMock()
    h.services.async_services = MagicMock(return_value={})
    return h


def _wiz(source_state=None):
    flow = cf.DaikinCycleMLConfigFlow()
    flow.hass = _hass(source_state)
    flow._data = {}
    flow._options = {}
    flow._reconfigure_entry = None
    return flow


def test_model_custom_valid_json():
    flow = _wiz()
    r = asyncio.run(flow.async_step_model_custom(user_input={
        'custom_attribute_map': '{"a": "b"}',
    }))
    assert r['step_id'] == 'attributes'


def test_model_custom_non_dict_json():
    flow = _wiz()
    r = asyncio.run(flow.async_step_model_custom(user_input={
        'custom_attribute_map': '[1,2,3]',
    }))
    assert r['type'] == 'form'


def test_reconfigure_basic_entity_not_found():
    flow = _wiz()
    entry = MagicMock()
    entry.data = {'source_sensor': 'x', 'model': 'epra12eav3'}
    flow._get_reconfigure_entry = MagicMock(return_value=entry)
    r = asyncio.run(flow.async_step_reconfigure_basic(user_input={
        'source_sensor': 'sensor.missing',
        'model': 'epra12eav3',
    }))
    assert r['type'] == 'form'


def test_reconfigure_basic_missing_attrs():
    src = MagicMock()
    src.attributes = {}
    flow = _wiz(src)
    entry = MagicMock()
    entry.data = {'source_sensor': 'x', 'model': 'epra12eav3'}
    flow._get_reconfigure_entry = MagicMock(return_value=entry)
    r = asyncio.run(flow.async_step_reconfigure_basic(user_input={
        'source_sensor': 'sensor.x',
        'model': 'epra12eav3',
    }))
    assert r['type'] == 'form'


def test_reconfigure_basic_form_no_input():
    flow = _wiz()
    entry = MagicMock()
    entry.data = {'source_sensor': 'sensor.x', 'model': 'epra12eav3'}
    flow._get_reconfigure_entry = MagicMock(return_value=entry)
    r = asyncio.run(flow.async_step_reconfigure_basic())
    assert r['step_id'] == 'reconfigure_basic'


def test_options_flow_notifications_form():
    flow = cf.DaikinCycleMLOptionsFlow()
    flow.hass = _hass()
    entry = MagicMock()
    entry.entry_id = 'x'
    entry.options = {}
    entry.data = {}
    entry.runtime_data = None
    type(flow).config_entry = property(lambda self: entry)
    r = asyncio.run(flow.async_step_notifications())
    assert r['step_id'] == 'notifications'


def test_options_flow_test_notification_submit():
    flow = cf.DaikinCycleMLOptionsFlow()
    flow.hass = _hass()
    entry = MagicMock()
    entry.entry_id = 'x'
    entry.options = {}
    entry.data = {}
    entry.runtime_data = None
    type(flow).config_entry = property(lambda self: entry)
    coord = MagicMock()
    coord.async_emit_test_alert = AsyncMock(return_value='OK')
    flow._get_coordinator_handle = MagicMock(return_value=coord)
    r = asyncio.run(flow.async_step_test_notification(user_input={
        'alert_kind': 'short_run',
        'ignore_group_filters': True,
    }))
    assert r['step_id'] == 'test_notification_result'


def test_options_flow_test_notification_result():
    flow = cf.DaikinCycleMLOptionsFlow()
    flow.hass = _hass()
    entry = MagicMock()
    entry.entry_id = 'x'
    entry.options = {}
    entry.data = {}
    entry.runtime_data = None
    type(flow).config_entry = property(lambda self: entry)
    flow._test_result = {'status': 'sent', 'kind': 'short_run', 'preview': 'OK'}
    r = asyncio.run(flow.async_step_test_notification_result())
    assert r['step_id'] == 'test_notification_result'


def test_options_flow_test_notification_result_submit():
    flow = cf.DaikinCycleMLOptionsFlow()
    flow.hass = _hass()
    entry = MagicMock()
    entry.entry_id = 'x'
    entry.options = {}
    entry.data = {}
    entry.runtime_data = None
    type(flow).config_entry = property(lambda self: entry)
    flow.async_step_init = AsyncMock(return_value={'type': 'menu'})
    asyncio.run(flow.async_step_test_notification_result(user_input={}))
    flow.async_step_init.assert_awaited_once()
