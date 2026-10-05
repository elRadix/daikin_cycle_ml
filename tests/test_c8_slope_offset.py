"""Tests for C8: slope/offset derivation on stooklijn advies."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)
from custom_components.daikin_cycle_ml.engine.cop_analyzer import (
    T_REF_STOOKLIJN,
    CopSample,
    StooklijnAdvies,
    _slope_delta,
    analyze_stooklijn,
)
from custom_components.daikin_cycle_ml.sensor import _attrs_stooklijn


def test_slope_delta_outdoor_none():
    assert _slope_delta(-2.0, None) is None


def test_slope_delta_denom_zero():
    assert _slope_delta(-2.0, 20.0) is None


def test_slope_delta_denom_near_zero():
    assert _slope_delta(-2.0, 20.05) is None
    assert _slope_delta(-2.0, 19.95) is None


def test_slope_delta_negative():
    assert _slope_delta(-2.0, 5.0) == round(-2.0 / 15.0, 4)


def test_slope_delta_positive():
    assert _slope_delta(2.0, 10.0) == round(2.0 / 10.0, 4)


def test_slope_delta_zero():
    assert _slope_delta(0.0, 10.0) == 0.0


def test_t_ref_value():
    assert T_REF_STOOKLIJN == 20.0


def test_advies_defaults():
    a = StooklijnAdvies()
    assert a.offset_delta_c == 0.0
    assert a.slope_delta is None


def _samples(n_hist, lwt_hist, lwt_recent, outdoor=7.0, cop=3.0):
    now = time.time()
    out = []
    for i in range(n_hist):
        out.append(CopSample(
            cop=cop, lwt=lwt_hist, outdoor=outdoor,
            flow_lmin=10.0, defrost=False, data_quality='Good',
            power_stable=True, mode='heating',
            ts=now - (n_hist + 1 - i) * 300,
        ))
    out.append(CopSample(
        cop=cop, lwt=lwt_recent, outdoor=outdoor,
        flow_lmin=10.0, defrost=False, data_quality='Good',
        power_stable=True, mode='heating', ts=now - 30,
    ))
    return out


# legacy branch (setpoint_lwt=None)

def test_legacy_lower_fills_offset_slope():
    a = analyze_stooklijn(_samples(5, 32.0, 36.0, outdoor=7.0))
    assert a.state == 'lower_lwt'
    assert a.delta_c == -2.0
    assert a.offset_delta_c == -2.0
    assert a.slope_delta == round(-2.0 / 13.0, 4)


def test_legacy_raise_fills_offset_slope():
    a = analyze_stooklijn(_samples(5, 36.0, 32.0, outdoor=7.0))
    assert a.state == 'raise_lwt'
    assert a.delta_c == 2.0
    assert a.offset_delta_c == 2.0
    assert a.slope_delta == round(2.0 / 13.0, 4)


def test_legacy_keep_fills_zero_offset():
    a = analyze_stooklijn(_samples(5, 35.0, 35.0, outdoor=7.0))
    assert a.state == 'keep'
    assert a.offset_delta_c == 0.0
    assert a.slope_delta == 0.0


def test_legacy_comfort_floor_early_return():
    a = analyze_stooklijn(
        _samples(5, 30.0, 40.0, outdoor=7.0),
        comfort_min=20.0, indoor_avg=20.5,
    )
    assert a.state == 'keep'
    assert a.reason == 'comfort_floor_reached'
    assert a.offset_delta_c == 0.0
    assert a.slope_delta is None


# B13 branch (setpoint_lwt + indoor_avg given)

def test_b13_lower_fills_offset_slope():
    a = analyze_stooklijn(
        _samples(10, 35.0, 35.0, outdoor=7.0),
        comfort_min=20.0, indoor_avg=22.0,
        setpoint_lwt=38.0, comfort_max=24.0,
    )
    assert a.state == 'lower_lwt'
    assert a.delta_c == -2.0
    assert a.offset_delta_c == -2.0
    assert a.slope_delta == round(-2.0 / 13.0, 4)


def test_b13_raise_fills_offset_slope():
    a = analyze_stooklijn(
        _samples(10, 35.0, 35.0, outdoor=7.0),
        comfort_min=20.0, indoor_avg=22.0,
        setpoint_lwt=32.0, comfort_max=24.0,
    )
    assert a.state == 'raise_lwt'
    assert a.delta_c == 2.0
    assert a.offset_delta_c == 2.0
    assert a.slope_delta == round(2.0 / 13.0, 4)


def test_b13_keep_early_return():
    a = analyze_stooklijn(
        _samples(10, 35.0, 35.0, outdoor=7.0),
        comfort_min=20.0, indoor_avg=22.0,
        setpoint_lwt=35.5, comfort_max=24.0,
    )
    assert a.state == 'keep'
    assert a.offset_delta_c == 0.0
    assert a.slope_delta is None


def test_b13_no_indoor_early_return():
    a = analyze_stooklijn(
        _samples(10, 35.0, 35.0, outdoor=7.0),
        comfort_min=20.0, indoor_avg=None,
        setpoint_lwt=38.0,
    )
    assert a.state == 'keep'
    assert a.reason == 'no_indoor_sensor'
    assert a.offset_delta_c == 0.0
    assert a.slope_delta is None


# coordinator + sensor wiring

async def test_coordinator_cache_has_new_keys():
    now = time.time()
    rows = [
        {'cop': 3.0, 'lwt': 35.0, 'outdoor': 7.0,
         'flow_lmin': 12.0, 'power_stable': 1,
         'mode': 'heating', 'ts': now - 100},
    ]
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.db = MagicMock()
    c.db.async_fetch_cop_samples = AsyncMock(return_value=rows)
    c.options = {}
    c._stooklijn_cache = {}
    c._stooklijn_cache_ts = 0.0
    c.hass = None
    await c._maybe_refresh_stooklijn(now)
    assert 'offset_delta_c' in c._stooklijn_cache
    assert 'slope_delta' in c._stooklijn_cache


def test_attrs_stooklijn_has_new_keys():
    s = MagicMock()
    s.stooklijn_advies = {
        'state': 'lower_lwt', 'step_c': 2,
        'offset_delta_c': -2.0, 'slope_delta': -0.1538,
    }
    c = MagicMock()
    c.options = {}
    out = _attrs_stooklijn(s, c)
    assert out['offset_delta_c'] == -2.0
    assert out['slope_delta'] == -0.1538


def test_attrs_stooklijn_missing_new_keys():
    s = MagicMock()
    s.stooklijn_advies = {}
    c = MagicMock()
    c.options = {}
    out = _attrs_stooklijn(s, c)
    assert out['offset_delta_c'] is None
    assert out['slope_delta'] is None
