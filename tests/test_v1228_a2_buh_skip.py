"""A2 (v1.22.8): BUH-active suppressie op heating_curve_advice (#353)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.const import ATTR_BUH_STEP1, ATTR_BUH_STEP2


def _mk_coord(buh1='OFF', buh2='OFF', cache=None, mode='heating', db=True):
    c = MagicMock()
    c.db = MagicMock() if db else None
    c.data = MagicMock()
    c.data.attrs = {ATTR_BUH_STEP1: buh1, ATTR_BUH_STEP2: buh2}
    c.data.mode = mode
    c._stooklijn_cache = dict(cache) if cache else {}
    c._stooklijn_cache_ts = 0.0
    return c


def _D():
    from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
    return DaikinCycleMLCoordinator


@pytest.mark.asyncio
async def test_buh_step1_writes_buh_active_cache():
    c = _mk_coord(buh1='ON')
    await _D()._maybe_refresh_stooklijn(c, 1000.0)
    assert c._stooklijn_cache['state'] == 'keep'
    assert c._stooklijn_cache['reason'] == 'buh_active'
    assert c._stooklijn_cache_ts == 1000.0


@pytest.mark.asyncio
async def test_buh_step2_writes_buh_active_cache():
    c = _mk_coord(buh2='ON')
    await _D()._maybe_refresh_stooklijn(c, 1000.0)
    assert c._stooklijn_cache['reason'] == 'buh_active'


@pytest.mark.asyncio
async def test_buh_active_idempotent():
    c = _mk_coord(buh1='ON')
    await _D()._maybe_refresh_stooklijn(c, 1000.0)
    ts1 = c._stooklijn_cache_ts
    await _D()._maybe_refresh_stooklijn(c, 1030.0)
    assert c._stooklijn_cache_ts == ts1


@pytest.mark.asyncio
async def test_buh_active_overrides_lower_lwt_cache():
    c = _mk_coord(buh1='ON', cache={'state': 'lower_lwt', 'reason': ''})
    await _D()._maybe_refresh_stooklijn(c, 2000.0)
    assert c._stooklijn_cache['state'] == 'keep'
    assert c._stooklijn_cache['reason'] == 'buh_active'


@pytest.mark.asyncio
async def test_buh_active_during_force_writes_cache():
    c = _mk_coord(buh1='ON')
    await _D()._maybe_refresh_stooklijn(c, 1500.0, force=True)
    assert c._stooklijn_cache['reason'] == 'buh_active'


@pytest.mark.asyncio
async def test_buh_off_invalidates_buh_active_cache():
    c = _mk_coord(buh1='OFF', cache={'state': 'keep', 'reason': 'buh_active'})
    c._stooklijn_cache_ts = 9999.0
    await _D()._maybe_refresh_stooklijn(c, 10000.0)
    assert c._stooklijn_cache_ts == 0.0


@pytest.mark.asyncio
async def test_buh_off_preserves_non_buh_cache():
    c = _mk_coord(buh1='OFF', cache={'state': 'lower_lwt', 'reason': ''})
    c._stooklijn_cache_ts = 5000.0
    c.db.async_fetch_cop_samples = AsyncMock(return_value=[])
    await _D()._maybe_refresh_stooklijn(c, 5100.0)
    assert c._stooklijn_cache_ts == 5000.0


@pytest.mark.asyncio
async def test_buh_active_during_setup_no_data_no_crash():
    c = _mk_coord(buh1='ON')
    c.data = None
    await _D()._maybe_refresh_stooklijn(c, 1000.0)
    assert c._stooklijn_cache.get('reason') != 'buh_active'


@pytest.mark.asyncio
async def test_buh_takes_priority_over_dhw():
    c = _mk_coord(buh1='ON', mode='dhw')
    await _D()._maybe_refresh_stooklijn(c, 1000.0)
    assert c._stooklijn_cache['reason'] == 'buh_active'


@pytest.mark.asyncio
async def test_db_none_returns_early():
    c = _mk_coord(buh1='ON', db=False)
    await _D()._maybe_refresh_stooklijn(c, 1000.0)
    assert c._stooklijn_cache == {}


def test_attrs_stooklijn_exposes_suppressed_by():
    from custom_components.daikin_cycle_ml.sensor import _attrs_stooklijn
    s = MagicMock()
    s.stooklijn_advies = {'state': 'keep', 'reason': 'buh_active', 'step_c': 0}
    c = MagicMock()
    c.options = {'notification_language': 'en'}
    attrs = _attrs_stooklijn(s, c)
    assert attrs['suppressed_by'] == 'buh_active'


def test_attrs_stooklijn_suppressed_by_none_when_normal():
    from custom_components.daikin_cycle_ml.sensor import _attrs_stooklijn
    s = MagicMock()
    s.stooklijn_advies = {'state': 'lower_lwt', 'reason': '', 'step_c': 2}
    c = MagicMock()
    c.options = {'notification_language': 'en'}
    attrs = _attrs_stooklijn(s, c)
    assert attrs['suppressed_by'] is None


@pytest.mark.asyncio
async def test_buh_skip_handles_non_dict_attrs():
    """Branch 3242->3247: _attrs is niet-dict → BUH-detectie overgeslagen."""
    c = _mk_coord(buh1='ON')
    c.data.attrs = "invalid"
    await _D()._maybe_refresh_stooklijn(c, 1000.0)
    assert c._stooklijn_cache.get('reason') != 'buh_active'


@pytest.mark.asyncio
async def test_buh_off_then_fresh_tick_recomputes():
    """Full flow: BUH on → cache=buh_active → BUH off → volgende tick fetcht opnieuw."""
    c = _mk_coord(buh1='ON')
    await _D()._maybe_refresh_stooklijn(c, 1000.0)
    assert c._stooklijn_cache['reason'] == 'buh_active'
    c.data.attrs = {ATTR_BUH_STEP1: 'OFF', ATTR_BUH_STEP2: 'OFF'}
    c.db.async_fetch_cop_samples = AsyncMock(return_value=[])
    # now=5000: after invalidation cache_ts=0.0, (5000-0) > 3600 -> TTL expired
    await _D()._maybe_refresh_stooklijn(c, 5000.0)
    assert c.db.async_fetch_cop_samples.called
