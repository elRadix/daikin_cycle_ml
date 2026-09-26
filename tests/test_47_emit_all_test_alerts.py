"""Batch 47 -- coordinator._emit_all_test_alerts deep coverage."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)


def _bare(options=None):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = dict(options or {})
    c.data = MagicMock()
    c.store = MagicMock()
    c.store.last_cycle = MagicMock(return_value=None)
    c.store.cycles_in_window = MagicMock(return_value=0)
    c.store.cycles_today = MagicMock(return_value=[])
    c.store.counters_snapshot = MagicMock(return_value={})
    c.store.off_time_since_last = MagicMock(return_value=None)
    c.hass = MagicMock()
    c.hass.services = MagicMock()
    c.hass.services.async_call = AsyncMock()
    c._last_alert_sent = {}
    c._setpoint_history = []
    c._emit_alert = AsyncMock()
    c._build_alert_context = MagicMock(return_value={})
    return c


def test_emit_all_no_ignore():
    c = _bare()
    out = asyncio.run(c._emit_all_test_alerts(ignore_filters=False))
    assert isinstance(out, str)
    assert 'pendulum_hourly' in out
    assert 'pendulum_daily' in out
    assert 'short_run' in out
    assert 'short_off' in out
    assert 'ml_anomaly' in out
    assert 'setpoint_osc' in out
    assert 'cop_low' in out
    assert 'stooklijn_advies' in out
    assert c._emit_alert.await_count >= 8


def test_emit_all_ignore_filters():
    c = _bare(options={
        'quiet_hours_enabled': True,
        'quiet_hours_start': '00:00',
        'quiet_hours_end': '23:59',
        'alert_group_pendulum': False,
        'alert_group_short_cycle': False,
        'alert_group_ml': False,
    })
    out = asyncio.run(c._emit_all_test_alerts(ignore_filters=True))
    assert 'pendulum_hourly' in out
    assert 'ml_anomaly' in out
    assert c._emit_alert.await_count >= 8


def test_emit_all_persistent_off():
    c = _bare(options={'persistent_enabled': False})
    asyncio.run(c._emit_all_test_alerts(ignore_filters=True))
    for call in c._emit_alert.await_args_list:
        spec = call.args[0]
        assert spec.persistent is False


def test_emit_all_persistent_on():
    c = _bare(options={'persistent_enabled': True})
    asyncio.run(c._emit_all_test_alerts(ignore_filters=True))
    for call in c._emit_alert.await_args_list:
        spec = call.args[0]
        assert spec.persistent is True


def test_emit_all_language_en():
    c = _bare(options={'notification_language': 'en'})
    out = asyncio.run(c._emit_all_test_alerts(ignore_filters=True))
    assert 'Pendulum detected' in out or 'pendulum_hourly' in out


def test_emit_all_language_nl():
    c = _bare(options={'notification_language': 'nl'})
    out = asyncio.run(c._emit_all_test_alerts(ignore_filters=True))
    assert 'Pendelen' in out or 'pendulum_hourly' in out


def test_emit_all_emoji_off():
    c = _bare(options={'notify_emoji_enabled': False})
    out = asyncio.run(c._emit_all_test_alerts(ignore_filters=True))
    assert 'Daikin Cycle ML' in out


def test_async_emit_test_alert_all_alerts():
    c = _bare()
    c._emit_all_test_alerts = AsyncMock(return_value='ALL OK')
    out = asyncio.run(c.async_emit_test_alert('all_alerts', ignore_filters=True))
    assert out == 'ALL OK'
    c._emit_all_test_alerts.assert_awaited_once()


def test_async_emit_test_alert_status_summary():
    c = _bare()
    c.async_emit_status_update = AsyncMock(return_value='STATUS OK')
    out = asyncio.run(c.async_emit_test_alert('status_summary'))
    assert out == 'STATUS OK'


def test_async_emit_test_alert_cop_low():
    c = _bare()
    out = asyncio.run(c.async_emit_test_alert('cop_low'))
    assert isinstance(out, str)
    assert 'COP' in out or '2.10' in out


def test_async_emit_test_alert_stooklijn():
    c = _bare()
    out = asyncio.run(c.async_emit_test_alert('stooklijn_advies'))
    assert isinstance(out, str)
    assert 'Stooklijn' in out


def test_async_emit_test_alert_pendulum_hourly():
    c = _bare()
    out = asyncio.run(c.async_emit_test_alert('pendulum_hourly'))
    assert isinstance(out, str)


def test_async_emit_test_alert_unknown_kind():
    c = _bare()
    try:
        asyncio.run(c.async_emit_test_alert('nonsense_kind'))
        raise AssertionError("unreachable")
    except ValueError as e:
        assert 'nonsense_kind' in str(e)
