"""Batch 46 -- coordinator._emit_all_test_alerts coverage."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator


def _bare_coord(options=None, data=None):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = options or {}
    c.data = data or MagicMock()
    c.hass = MagicMock()
    c.hass.services = MagicMock()
    c.hass.services.async_call = AsyncMock()
    c._last_alert_sent = {}
    c._setpoint_history = []
    c._emit_alert = AsyncMock()
    return c


def test_emit_all_test_alerts_no_filters():
    c = _bare_coord()
    out = asyncio.run(c._emit_all_test_alerts(ignore_filters=False))
    assert isinstance(out, str)
    assert '=== pendulum_hourly ===' in out
    assert '=== cop_low ===' in out
    assert '=== stooklijn_advies ===' in out
    assert c._emit_alert.await_count >= 8


def test_emit_all_test_alerts_with_filters_bypass():
    c = _bare_coord(options={
        'quiet_hours_enabled': True,
        'quiet_hours_start': '00:00',
        'quiet_hours_end': '23:59',
        'alert_group_pendulum': False,
    })
    out = asyncio.run(c._emit_all_test_alerts(ignore_filters=True))
    assert '=== pendulum_hourly ===' in out
    assert '=== pendulum_daily ===' in out
    assert c._emit_alert.await_count >= 8


def test_emit_all_test_alerts_persistent_off():
    c = _bare_coord(options={'persistent_enabled': False})
    asyncio.run(c._emit_all_test_alerts(ignore_filters=True))
    # All calls should have persistent=False
    for call in c._emit_alert.await_args_list:
        spec = call.args[0]
        assert spec.persistent is False


def test_emit_all_test_alerts_all_languages():
    for lang in ('en', 'nl'):
        c = _bare_coord(options={'notification_language': lang})
        out = asyncio.run(c._emit_all_test_alerts(ignore_filters=True))
        assert 'Daikin Cycle ML' in out


def test_async_emit_test_alert_all_alerts_dispatch():
    c = _bare_coord()
    c._emit_all_test_alerts = AsyncMock(return_value='OK')
    out = asyncio.run(c.async_emit_test_alert("all_alerts", ignore_filters=True))
    assert out == 'OK'
    c._emit_all_test_alerts.assert_awaited_once()
