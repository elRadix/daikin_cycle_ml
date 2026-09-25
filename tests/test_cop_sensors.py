"""Tests for cop sensors (batch 14b-2)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator, DataSnapshot,
)
from custom_components.daikin_cycle_ml.engine.cop_analyzer import (
    CopSample, bucket_summary,
)
from custom_components.daikin_cycle_ml.sensor import (
    _cop_today_attrs, _stooklijn_attrs,
)


def _bare(db=None, options=None):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.db = db
    c.options = options or {}
    c._stooklijn_cache = {}
    c._stooklijn_cache_ts = 0.0
    c._cop_today_cache = {}
    return c


def _mk(cop, lwt, outdoor):
    return CopSample(
        cop=cop, lwt=lwt, outdoor=outdoor,
        defrost=False, data_quality='Good',
    )


def test_bucket_summary_groups():
    samples = [
        _mk(2.4, 42.0, 1.0),
        _mk(2.8, 40.0, 3.0),
        _mk(3.4, 35.0, 5.0),
        _mk(3.6, 34.0, 5.0),
    ]
    out = bucket_summary(samples)
    assert '0-2' in out
    assert out['0-2']['n'] == 1
    assert out['4-6']['n'] == 2
    assert out['4-6']['cop'] == 3.5


def test_bucket_summary_empty():
    assert bucket_summary([]) == {}


def test_stooklijn_attrs_empty():
    assert _stooklijn_attrs(None) == {}
    assert _stooklijn_attrs({}) == {}


def test_stooklijn_attrs_full():
    data = {
        'state': 'verlaag_lwt_2c', 'optimale_lwt': 32.0,
        'huidige_lwt': 36.0, 'besparing_cop_pct': 8.0,
        'comfort_impact': -0.3, 'betrouwbaarheid': 0.85,
        'bucket': '6-8', 'samples': 87,
        'buckets': {'6-8': {'cop': 3.8, 'n': 87, 'lwt': 35.0}},
    }
    out = _stooklijn_attrs(data)
    assert out['optimale_lwt'] == 32.0
    assert out['bucket'] == '6-8'
    assert '6-8' in out['buckets']


def test_cop_today_attrs_empty():
    assert _cop_today_attrs(None) == {}
    assert _cop_today_attrs({}) == {}


def test_cop_today_attrs_full():
    data = {
        'cop': 3.42, 'samples_today': 142,
        'cop_min': 2.1, 'cop_max': 4.8,
        'baseline_cop_verlies_pct': 12.5,
    }
    out = _cop_today_attrs(data)
    assert out['samples_today'] == 142
    assert out['baseline_cop_verlies_pct'] == 12.5


async def test_refresh_cop_today_no_db():
    c = _bare(db=None)
    await c._refresh_cop_today(1000.0)
    assert c._cop_today_cache == {}


async def test_refresh_cop_today_no_samples():
    db = MagicMock()
    db.async_fetch_cop_samples = AsyncMock(return_value=[])
    c = _bare(db=db)
    await c._refresh_cop_today(1000.0)
    assert c._cop_today_cache == {}


async def test_refresh_cop_today_valid():
    import time as _t
    now = _t.time()
    rows = [
        {'ts': now - 100, 'cop': 3.0},
        {'ts': now - 200, 'cop': 3.5},
        {'ts': now - 300, 'cop': 4.0},
    ]
    db = MagicMock()
    db.async_fetch_cop_samples = AsyncMock(return_value=rows)
    c = _bare(db=db)
    await c._refresh_cop_today(now)
    assert c._cop_today_cache['cop'] == 3.5
    assert c._cop_today_cache['samples_today'] == 3
    assert c._cop_today_cache['cop_min'] == 3.0
    assert c._cop_today_cache['cop_max'] == 4.0


async def test_refresh_cop_today_bad_response():
    db = MagicMock()
    db.async_fetch_cop_samples = AsyncMock(return_value=MagicMock())
    c = _bare(db=db)
    await c._refresh_cop_today(1000.0)
    assert c._cop_today_cache == {}


async def test_maybe_refresh_stooklijn_cache_hit():
    db = MagicMock()
    db.async_fetch_cop_samples = AsyncMock(return_value=[])
    c = _bare(db=db)
    c._stooklijn_cache = {'state': 'behoud'}
    c._stooklijn_cache_ts = 1000.0
    await c._maybe_refresh_stooklijn(1100.0)
    db.async_fetch_cop_samples.assert_not_awaited()


async def test_maybe_refresh_stooklijn_no_db():
    c = _bare(db=None)
    await c._maybe_refresh_stooklijn(1000.0)
    assert c._stooklijn_cache == {}


async def test_maybe_refresh_stooklijn_valid():
    rows = [
        {'cop': 3.0, 'lwt': 32.0, 'outdoor': 7.0,
         'flow_lmin': 12.0, 'power_stable': 1},
    ]
    db = MagicMock()
    db.async_fetch_cop_samples = AsyncMock(return_value=rows)
    c = _bare(db=db, options={'comfort_min_c': 20.0})
    await c._maybe_refresh_stooklijn(5000.0)
    assert c._stooklijn_cache['state'] == 'unknown'
    assert c._stooklijn_cache_ts == 5000.0
    assert 'buckets' in c._stooklijn_cache

