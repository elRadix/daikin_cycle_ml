"""Tests for engine/cop_analyzer.py (batch 14a)."""
from __future__ import annotations

from custom_components.daikin_cycle_ml.engine.cop_analyzer import (
    CopSample, StooklijnAdvies, _parse_bool, _parse_float,
    analyze_stooklijn, bucket_for_outdoor, parse_global_cop_attrs,
)


def test_parse_float_basic():
    assert _parse_float(35.2) == 35.2
    assert _parse_float('35.2') == 35.2


def test_parse_float_with_unit():
    assert _parse_float('29.5 C (After BUH)') == 29.5
    assert _parse_float('16.5 C') == 16.5
    assert _parse_float('0.02 kW (Comp + BUH)') == 0.02
    assert _parse_float('0.41 A') == 0.41
    assert _parse_float('236.29 V') == 236.29


def test_parse_float_invalid():
    assert _parse_float('Invalid (0.0)') is None
    assert _parse_float('unknown') is None
    assert _parse_float('unavailable') is None
    assert _parse_float(None) is None
    assert _parse_float('') is None
    assert _parse_float(True) is None


def test_parse_bool():
    assert _parse_bool(True) is True
    assert _parse_bool(False) is False
    assert _parse_bool('ON') is True
    assert _parse_bool('OFF') is False
    assert _parse_bool('on') is True


def test_bucket_for_outdoor():
    assert bucket_for_outdoor(None) == 'unknown'
    assert bucket_for_outdoor(16.5) == '16-18'
    assert bucket_for_outdoor(7.0) == '6-8'
    assert bucket_for_outdoor(-3.5) == '-4--2'
    assert bucket_for_outdoor(-15.0) == '-10-'
    assert bucket_for_outdoor(25.0) == '20+'
    assert bucket_for_outdoor(0.0) == '0-2'


def _attrs(**over):
    base = {
        'state': '3.5',
        'leaving_temp': '32.5 C (After BUH)',
        'inlet_temp': '28.0 C',
        'delta_t': '4.5 C',
        'thermal_power': '5.2 kW',
        'electrical_input': '1.5 kW (Comp + BUH)',
        'outdoor_temperature': '7.0 C',
        'flow_rate': '12.5 L/min',
        'backup_heater_active': False,
        'defrost_operation': 'OFF',
        'power_stable': True,
        'data_quality': 'Good',
    }
    base.update(over)
    return base


def test_parse_global_cop_attrs_valid():
    s = parse_global_cop_attrs(_attrs())
    assert s is not None
    assert s.cop == 3.5
    assert s.lwt == 32.5
    assert s.outdoor == 7.0
    assert s.flow_lmin == 12.5
    assert s.valid is True


def test_parse_global_cop_attrs_invalid_flow():
    s = parse_global_cop_attrs(_attrs(flow_rate='Invalid (0.0)'))
    assert s is not None
    assert s.flow_lmin is None


def test_parse_global_cop_attrs_defrost_invalid():
    s = parse_global_cop_attrs(_attrs(defrost_operation='ON'))
    assert s is not None
    assert s.defrost is True
    assert s.valid is False


def test_parse_global_cop_attrs_poor_quality():
    s = parse_global_cop_attrs(_attrs(data_quality='Poor/Idle'))
    assert s is not None
    assert s.valid is False


def test_parse_global_cop_attrs_empty():
    assert parse_global_cop_attrs(None) is None
    assert parse_global_cop_attrs({}) is None


def _mk_sample(cop, lwt, outdoor, q='Good'):
    return CopSample(
        cop=cop, lwt=lwt, outdoor=outdoor,
        defrost=False, data_quality=q,
    )


def test_analyze_no_samples():
    a = analyze_stooklijn([])
    assert a.state == 'unknown'


def test_analyze_few_samples():
    samples = [_mk_sample(3.0, 32.0, 7.0) for _ in range(3)]
    a = analyze_stooklijn(samples)
    assert a.samples == 3
    assert a.state == 'unknown'
    assert a.betrouwbaarheid == 0.3


def test_analyze_behoud():
    samples = [_mk_sample(3.5, 32.0, 7.0) for _ in range(10)]
    a = analyze_stooklijn(samples)
    assert a.state == 'behoud'
    assert a.samples == 10
    assert a.betrouwbaarheid == 1.0


def test_analyze_verlaag():
    samples = [_mk_sample(3.0, 32.0, 7.0) for _ in range(10)]
    samples.append(_mk_sample(2.5, 36.0, 7.0))
    a = analyze_stooklijn(samples)
    assert a.state == 'verlaag_lwt_2c'
    assert a.besparing_cop_pct > 0


def test_analyze_verhoog():
    samples = [_mk_sample(3.0, 36.0, 7.0) for _ in range(10)]
    samples.append(_mk_sample(3.5, 32.0, 7.0))
    a = analyze_stooklijn(samples)
    assert a.state == 'verhoog_lwt_2c'


def test_analyze_comfort_guard():
    samples = [_mk_sample(3.0, 32.0, 7.0) for _ in range(10)]
    samples.append(_mk_sample(2.5, 40.0, 7.0))
    a = analyze_stooklijn(samples, comfort_min=22.0, indoor_avg=22.0)
    assert a.state == 'behoud'
    assert a.comfort_impact < 0


def test_analyze_besparing_eur():
    samples = [_mk_sample(3.0, 32.0, 7.0) for _ in range(10)]
    samples.append(_mk_sample(2.5, 36.0, 7.0))
    a = analyze_stooklijn(samples, daily_kwh=15.0, price_eur_per_kwh=0.30)
    assert a.besparing_eur_dag > 0
    assert a.besparing_eur_dag < 10.0
