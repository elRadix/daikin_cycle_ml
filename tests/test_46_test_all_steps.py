"""Batch 46 -- config_flow test_all_notifications step coverage."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml import config_flow as cf


def _flow_with_coordinator(coord):
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


def test_show_form_when_no_input():
    coord = MagicMock()
    coord.async_emit_test_alert = AsyncMock()
    flow = _flow_with_coordinator(coord)
    import asyncio
    r = asyncio.run(flow.async_step_test_all_notifications())
    assert r['type'] == 'form'
    assert r['step_id'] == 'test_all_notifications'


def test_submit_calls_coordinator():
    import asyncio
    coord = MagicMock()
    coord.async_emit_test_alert = AsyncMock(return_value='=== x ===\nA\n=== y ===\nB')
    flow = _flow_with_coordinator(coord)
    r = asyncio.run(flow.async_step_test_all_notifications(user_input={}))
    coord.async_emit_test_alert.assert_awaited_once()
    assert r['step_id'] == 'test_all_notifications_result'
    assert flow._test_all_result['status'] == 'sent'
    assert flow._test_all_result['count'] >= 2


def test_no_coordinator():
    import asyncio
    flow = _flow_with_coordinator(None)
    r = asyncio.run(flow.async_step_test_all_notifications(user_input={}))
    assert flow._test_all_result['status'] == 'no_coordinator'


def test_coordinator_raises():
    import asyncio
    coord = MagicMock()
    coord.async_emit_test_alert = AsyncMock(side_effect=RuntimeError('boom'))
    flow = _flow_with_coordinator(coord)
    r = asyncio.run(flow.async_step_test_all_notifications(user_input={}))
    assert flow._test_all_result['status'] == 'failed'
    assert 'boom' in flow._test_all_result['preview']


def test_result_step_returns_to_menu():
    import asyncio
    flow = _flow_with_coordinator(None)
    flow._test_all_result = {'status': 'sent', 'count': 9, 'preview': 'X'}
    r = asyncio.run(flow.async_step_test_all_notifications_result())
    assert r['step_id'] == 'test_all_notifications_result'


def test_result_step_submit_returns_init():
    import asyncio
    flow = _flow_with_coordinator(None)
    flow.async_step_init = AsyncMock(return_value={'type': 'menu'})
    r = asyncio.run(flow.async_step_test_all_notifications_result(user_input={'back': True}))
    flow.async_step_init.assert_awaited_once()
