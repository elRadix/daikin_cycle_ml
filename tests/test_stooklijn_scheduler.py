"""Tests for stooklijn scheduler + notify (14b-3)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)


def _bare(db=None, options=None, hass=None):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.db = db
    c.options = options or {}
    c.hass = hass or MagicMock()
    c.hass.services = MagicMock()
    c.hass.services.async_call = AsyncMock()
    c._last_alert_sent = {}
    c._stooklijn_cache = {}
    c._stooklijn_cache_ts = 0.0
    c._cop_today_cache = {}
    c._stooklijn_unsub = None
    return c


async def test_setup_stooklijn_registers():
    c = _bare()
    await c.async_setup_stooklijn()
    assert c._stooklijn_unsub is not None


async def test_setup_stooklijn_idempotent():
    c = _bare()
    await c.async_setup_stooklijn()
    first = c._stooklijn_unsub
    await c.async_setup_stooklijn()
    assert c._stooklijn_unsub is first


async def test_callback_swallows_exception():
    c = _bare()
    c.async_run_stooklijn_analysis = AsyncMock(
        side_effect=RuntimeError('boom'))
    await c._async_stooklijn_callback(None)


async def test_notify_cop_low_skips_empty():
    c = _bare()
    await c._maybe_notify_cop_low(1000.0, {})
    c.hass.services.async_call.assert_not_awaited()


async def test_notify_cop_low_skips_ok_cop():
    c = _bare()
    await c._maybe_notify_cop_low(1000.0, {
        'cop': 3.5, 'samples_today': 10},
    )
    c.hass.services.async_call.assert_not_awaited()


async def test_notify_cop_low_skips_few_samples():
    c = _bare()
    await c._maybe_notify_cop_low(1000.0, {
        'cop': 2.0, 'samples_today': 2},
    )
    c.hass.services.async_call.assert_not_awaited()


async def test_notify_cop_low_sends():
    c = _bare()
    await c._maybe_notify_cop_low(100000.0, {
        'cop': 2.0, 'samples_today': 10},
    )
    c.hass.services.async_call.assert_awaited()
    assert 'cop_low' in c._last_alert_sent


async def test_notify_cop_low_dedup():
    c = _bare()
    c._last_alert_sent['cop_low'] = 9900.0
    await c._maybe_notify_cop_low(10000.0, {
        'cop': 2.0, 'samples_today': 10},
    )
    c.hass.services.async_call.assert_not_awaited()


async def test_notify_stooklijn_skips_behoud():
    c = _bare()
    await c._maybe_notify_stooklijn(10000.0, {'state': 'behoud'})
    c.hass.services.async_call.assert_not_awaited()


async def test_notify_stooklijn_skips_low_conf():
    c = _bare()
    await c._maybe_notify_stooklijn(10000.0, {
        'state': 'verlaag_lwt_2c',
        'betrouwbaarheid': 0.5, 'besparing_cop_pct': 8.0,
        'comfort_impact': -0.3},
    )
    c.hass.services.async_call.assert_not_awaited()


async def test_notify_stooklijn_skips_low_saving():
    c = _bare()
    await c._maybe_notify_stooklijn(10000.0, {
        'state': 'verlaag_lwt_2c',
        'betrouwbaarheid': 0.85, 'besparing_cop_pct': 2.0,
        'comfort_impact': -0.3},
    )
    c.hass.services.async_call.assert_not_awaited()


async def test_notify_stooklijn_sends():
    c = _bare()
    await c._maybe_notify_stooklijn(100000.0, {
        'state': 'verlaag_lwt_2c',
        'betrouwbaarheid': 0.85, 'besparing_cop_pct': 8.0,
        'comfort_impact': -0.3},
    )
    c.hass.services.async_call.assert_awaited()
    assert 'stooklijn_advies' in c._last_alert_sent


async def test_run_analysis_no_db():
    c = _bare(db=None)
    out = await c.async_run_stooklijn_analysis()
    assert out['ok'] is False


async def test_run_analysis_refresh_fails():
    c = _bare()
    c._maybe_refresh_stooklijn = AsyncMock(
        side_effect=RuntimeError('boom'))
    out = await c.async_run_stooklijn_analysis()
    assert out['ok'] is False

