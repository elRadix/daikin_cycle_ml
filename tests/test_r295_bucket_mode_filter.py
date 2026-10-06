"""R295: bucket_summary mode-filter regression (issue #29).

DHW samples must not pollute outdoor-temperature buckets. Default
filter matches analyze_stooklijn: ('heating', 'unknown').
"""
from __future__ import annotations

from custom_components.daikin_cycle_ml.engine.cop_analyzer import (
    CopSample,
    bucket_summary,
)


def _s(cop, lwt, outdoor, mode):
    return CopSample(
        cop=cop, lwt=lwt, outdoor=outdoor, mode=mode,
        defrost=False, data_quality="Good",
    )


def test_default_filters_out_dhw():
    samples = [
        _s(6.0, 28.0, 19.0, "heating"),
        _s(2.5, 46.0, 19.5, "dhw"),
    ]
    out = bucket_summary(samples)
    assert "18-20" in out
    assert out["18-20"]["n"] == 1
    assert out["18-20"]["lwt"] == 28.0
    assert out["18-20"]["cop"] == 6.0


def test_default_includes_heating_and_unknown():
    samples = [
        _s(6.0, 28.0, 19.0, "heating"),
        _s(6.5, 30.0, 19.5, "unknown"),
    ]
    out = bucket_summary(samples)
    assert out["18-20"]["n"] == 2


def test_default_excludes_null_mode():
    s_null = CopSample(
        cop=5.0, lwt=40.0, outdoor=19.0,
        defrost=False, data_quality="Good",
    )
    s_null.mode = None  # type: ignore[assignment]
    samples = [
        _s(6.0, 28.0, 19.0, "heating"),
        s_null,
    ]
    out = bucket_summary(samples)
    assert out["18-20"]["n"] == 1


def test_include_modes_none_disables_filter():
    samples = [
        _s(6.0, 28.0, 19.0, "heating"),
        _s(2.5, 46.0, 19.5, "dhw"),
    ]
    out = bucket_summary(samples, include_modes=None)
    assert out["18-20"]["n"] == 2


def test_include_modes_custom_tuple():
    samples = [
        _s(6.0, 28.0, 19.0, "heating"),
        _s(2.5, 46.0, 19.5, "dhw"),
        _s(3.0, 15.0, 19.0, "cooling"),
    ]
    out = bucket_summary(samples, include_modes=("dhw",))
    assert out["18-20"]["n"] == 1
    assert out["18-20"]["cop"] == 2.5


def test_default_empty_samples():
    assert bucket_summary([]) == {}


def test_default_all_filtered_out_returns_empty():
    samples = [_s(2.5, 46.0, 19.0, "dhw")]
    assert bucket_summary(samples) == {}


def test_prod_scenario_mild_weather():
    # Reproduces issue #29: DHW samples inflating mild-weather bucket.
    samples = [
        _s(5.22, 26.6, 20.5, "heating"),
        _s(6.46, 28.7, 19.0, "heating"),
        _s(2.49, 46.6, 20.7, "dhw"),
        _s(1.80, 43.9, 19.0, "dhw"),
    ]
    out = bucket_summary(samples)
    assert out["20+"]["n"] == 1
    assert out["20+"]["lwt"] == 26.6
    assert out["20+"]["cop"] == 5.22
    assert out["18-20"]["n"] == 1
