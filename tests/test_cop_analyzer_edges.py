"""Edge-case tests for cop_analyzer (14b-3b)."""
from __future__ import annotations

from custom_components.daikin_cycle_ml.engine.cop_analyzer import (
    CopSample, _avg, _parse_bool, _parse_float,
    analyze_stooklijn, bucket_summary, parse_global_cop_attrs,
)


def test_parse_float_dict_returns_none():
    assert _parse_float({'a': 1}) is None


def test_parse_float_no_number_returns_none():
    assert _parse_float('geen cijfer') is None


def test_parse_bool_int():
    assert _parse_bool(1) is True
    assert _parse_bool(0) is False


def test_parse_global_cop_attrs_cop_none():
    assert parse_global_cop_attrs({'state': 'unknown'}) is None


def test_parse_global_cop_attrs_flow_numeric():
    s = parse_global_cop_attrs({
        'state': '3.5', 'flow_rate': 12.5,
        'data_quality': 'Good', 'power_stable': True,
    })
    assert s is not None
    assert s.flow_lmin == 12.5


def test_avg_empty():
    assert _avg([]) is None


def _valid(cop=3.0, lwt=32.0, outdoor=7.0):
    return CopSample(cop=cop, lwt=lwt, outdoor=outdoor,
                     defrost=False, data_quality='Good')


def _invalid(cop=0.0, outdoor=7.0):
    return CopSample(cop=cop, lwt=None, outdoor=outdoor,
                     defrost=False, data_quality='Poor/Idle')


def test_analyze_skips_invalid_samples():
    samples = [_valid() for _ in range(10)]
    samples.append(_invalid())
    a = analyze_stooklijn(samples)
    assert a.samples == 10


def test_analyze_all_invalid_returns_unknown():
    samples = [_invalid() for _ in range(5)]
    a = analyze_stooklijn(samples)
    assert a.state == 'unknown'


def test_analyze_recent_lwt_none_returns():
    samples = [_valid(lwt=32.0) for _ in range(10)]
    samples.append(_valid(lwt=None))
    a = analyze_stooklijn(samples)
    assert a.optimale_lwt is not None


def test_analyze_all_lwt_none_returns():
    samples = [_valid(lwt=None) for _ in range(10)]
    a = analyze_stooklijn(samples)
    assert a.samples == 10


def test_analyze_comfort_impact_set():
    samples = [_valid(lwt=32.0) for _ in range(10)]
    samples.append(_valid(lwt=36.0))
    a = analyze_stooklijn(samples, indoor_avg=22.0, comfort_min=20.0)
    assert a.comfort_impact != 0


def test_analyze_recent_invalid_scans_backwards():
    samples = [_valid() for _ in range(10)]
    samples.append(_invalid())
    a = analyze_stooklijn(samples)
    assert a.state in ('behoud', 'verlaag_lwt_2c', 'verhoog_lwt_2c')


def test_bucket_summary_extreme_buckets():
    samples = [
        _valid(lwt=45.0, outdoor=-15.0),
        _valid(lwt=30.0, outdoor=25.0),
        _valid(lwt=35.0, outdoor=None),
    ]
    out = bucket_summary(samples)
    assert '-10-' in out
    assert '20+' in out
    assert 'unknown' in out

