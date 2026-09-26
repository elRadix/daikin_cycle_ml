"""Batch 47 -- config_flow test_all_notifications step coverage."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml import config_flow as cf


def _flow(coord):
    flow = cf.DaikinCycleMLOptionsFlow()
    flow.hass = MagicMock()
    flow.hass.config_entries = MagicMock()
    entry = MagicMock()
    entry.entry_id = 'test_entry'
    entry.options = {}
    entry.data = {}
    entry.runtime_data = coord
    type(flow).config_entry = property(lambda self: entry)
    flow._get_coordinator_handle = MagicMock(return_value=coord)
    flow._test_all_result = None
    return flow


def test_form_no_input():
    flow = _flow(None)
    r = asyncio.run(flow.async_step_test_all_notifications())
    assert r['type'] == 'form'
    assert r['step_id'] == 'test_all_notifications'


def test_submit_success():
    coord = MagicMock()
    coord.async_emit_test_alert = AsyncMock(
        return_value='=== a ===\nX\n=== b ===\nY\n=== c ===\nZ'
    )
    flow = _flow(coord)
    r = asyncio.run(flow.async_step_test_all_notifications(user_input={}))
    coord.async_emit_test_alert.assert_awaited_once()
    args, kwargs = coord.async_emit_test_alert.call_args
    assert args[0] == 'all_alerts'
    assert kwargs.get('ignore_filters') is True
    assert flow._test_all_result['status'] == 'sent'
    assert flow._test_all_result['count'] == 3
    assert r['step_id'] == 'test_all_notifications_result'


def test_submit_no_coordinator():
    flow = _flow(None)
    asyncio.run(flow.async_step_test_all_notifications(user_input={}))
    assert flow._test_all_result['status'] == 'no_coordinator'
    assert 'Reload' in flow._test_all_result['preview']


def test_submit_coordinator_fails():
    coord = MagicMock()
    coord.async_emit_test_alert = AsyncMock(side_effect=RuntimeError('kaboom'))
    flow = _flow(coord)
    asyncio.run(flow.async_step_test_all_notifications(user_input={}))
    assert flow._test_all_result['status'] == 'failed'
    assert 'kaboom' in flow._test_all_result['preview']


def test_submit_none_message():
    coord = MagicMock()
    coord.async_emit_test_alert = AsyncMock(return_value=None)
    flow = _flow(coord)
    asyncio.run(flow.async_step_test_all_notifications(user_input={}))
    assert flow._test_all_result['status'] == 'sent'
    assert flow._test_all_result['count'] == 0


def test_result_step_render():
    flow = _flow(None)
    flow._test_all_result = {
        'status': 'sent', 'count': 9, 'preview': 'some preview',
    }
    r = asyncio.run(flow.async_step_test_all_notifications_result())
    assert r['step_id'] == 'test_all_notifications_result'
    assert 'description_placeholders' in r
    ph = r['description_placeholders']
    assert ph.get('status') == 'sent'
    assert ph.get('count') == '9'


def test_result_step_no_result_yet():
    flow = _flow(None)
    flow._test_all_result = None
    r = asyncio.run(flow.async_step_test_all_notifications_result())
    assert r['step_id'] == 'test_all_notifications_result'
    ph = r.get('description_placeholders') or {}
    assert ph.get('status') == 'unknown'


def test_result_step_submit():
    flow = _flow(None)
    flow.async_step_init = AsyncMock(return_value={'type': 'menu'})
    asyncio.run(flow.async_step_test_all_notifications_result(user_input={'x': 1}))
    flow.async_step_init.assert_awaited_once()
