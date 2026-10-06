"""R284: comfort_cap is None op early-return paden (was 3.0)."""
from __future__ import annotations

import time

from custom_components.daikin_cycle_ml.engine.cop_analyzer import (
    CopSample,
    StooklijnAdvies,
    analyze_stooklijn,
)


def _heating_samples(n, lwt, outdoor=8.0):
    now = time.time()
    return [
        CopSample(
            cop=3.0, lwt=lwt, outdoor=outdoor, flow_lmin=10.0,
            defrost=False, data_quality='Good', power_stable=True,
            mode='heating', ts=now - (n - i) * 300,
        )
        for i in range(n)
    ]


def test_dataclass_default_none():
    assert StooklijnAdvies().comfort_cap is None


def test_no_data_empty_samples():
    a = analyze_stooklijn([])
    assert a.comfort_cap is None


def test_no_recent_heating():
    now = time.time()
    s = [CopSample(
        cop=3.0, lwt=40.0, outdoor=8.0, defrost=False,
        data_quality='Good', mode='dhw', ts=now - 300,
    )]
    a = analyze_stooklijn(s)
    assert a.reason == 'no_recent_heating'
    assert a.comfort_cap is None


def test_no_indoor_sensor():
    a = analyze_stooklijn(
        _heating_samples(10, 35.0),
        indoor_avg=None, setpoint_lwt=38.0,
    )
    assert a.reason == 'no_indoor_sensor'
    assert a.comfort_cap is None


def test_legacy_comfort_floor_early_return():
    a = analyze_stooklijn(
        _heating_samples(10, 40.0),
        comfort_min=21.0, indoor_avg=20.5,
    )
    assert a.reason == 'comfort_floor_reached'
    assert a.comfort_cap is None


def test_b13_computed_cap_is_float():
    a = analyze_stooklijn(
        _heating_samples(10, 35.0),
        comfort_min=20.0, indoor_avg=22.0,
        setpoint_lwt=38.0, comfort_max=24.0,
    )
    assert isinstance(a.comfort_cap, float)
    assert a.comfort_cap > 0.0
