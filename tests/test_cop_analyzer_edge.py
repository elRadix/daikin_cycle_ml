"""Batch 15: cop_analyzer edge-case coverage."""
from __future__ import annotations

import pytest

from custom_components.daikin_cycle_ml.engine.cop_analyzer import (
    CopSample,
    StooklijnAdvies,
    _avg,
    _bucket_sort_key,
    _group_by_bucket,
    _parse_bool,
    _parse_float,
    analyze_stooklijn,
    bucket_for_outdoor,
    bucket_summary,
    parse_global_cop_attrs,
)


def test_parse_float_none():
    assert _parse_float(None) is None


def test_parse_float_bool():
    assert _parse_float(True) is None
    assert _parse_float(False) is None


def test_parse_float_number():
    assert _parse_float(3) == 3.0
    assert _parse_float(3.5) == 3.5


def test_parse_float_non_str_type():
    assert _parse_float([1, 2]) is None
    assert _parse_float({"x": 1}) is None


def test_parse_float_empty_string():
    assert _parse_float("") is None
    assert _parse_float("   ") is None


def test_parse_float_invalid_words():
    assert _parse_float("invalid") is None
    assert _parse_float("UNKNOWN") is None
    assert _parse_float("unavailable") is None


def test_parse_float_no_digit():
    assert _parse_float("abc") is None
    assert _parse_float("---") is None


def test_parse_float_with_unit():
    assert _parse_float("12.5 kW") == 12.5
    assert _parse_float("-3.2 C") == -3.2


def test_parse_bool_direct():
    assert _parse_bool(True) is True
    assert _parse_bool(False) is False


def test_parse_bool_str():
    assert _parse_bool("ON") is True
    assert _parse_bool("on") is True
    assert _parse_bool(" OFF ") is False
    assert _parse_bool("anything") is False


def test_parse_bool_non_str():
    assert _parse_bool(1) is True
    assert _parse_bool(0) is False
    assert _parse_bool(None) is False


def test_copsample_valid_true():
    s = CopSample(cop=3.5, data_quality="Good")
    assert s.valid is True


def test_copsample_valid_false_cop_zero():
    s = CopSample(cop=0.0, data_quality="Good")
    assert s.valid is False


def test_copsample_valid_false_defrost():
    s = CopSample(cop=3.5, defrost=True, data_quality="Good")
    assert s.valid is False


def test_copsample_valid_false_quality():
    s = CopSample(cop=3.5, data_quality="Poor/Idle")
    assert s.valid is False


def test_parse_attrs_none():
    assert parse_global_cop_attrs(None) is None
    assert parse_global_cop_attrs({}) is None


def test_parse_attrs_no_cop():
    assert parse_global_cop_attrs({"leaving_temp": "30 C"}) is None


def test_parse_attrs_full():
    attrs = {
        "state": "3.5",
        "leaving_temp": "32.5 C",
        "inlet_temp": "28.0 C",
        "delta_t": "4.5 C",
        "thermal_power": "5.2 kW",
        "electrical_input": "1.5 kW",
        "outdoor_temperature": "7.0 C",
        "flow_rate": "12.5 L/min",
        "backup_heater_active": False,
        "defrost_operation": "OFF",
        "power_stable": True,
        "data_quality": "Good",
    }
    s = parse_global_cop_attrs(attrs)
    assert s is not None
    assert s.cop == 3.5
    assert s.lwt == 32.5
    assert s.flow_lmin == 12.5
    assert s.power_stable is True
    assert s.defrost is False
    assert s.valid is True


def test_parse_attrs_flow_invalid_string():
    attrs = {"state": "3.5", "flow_rate": "Invalid (0.0)"}
    s = parse_global_cop_attrs(attrs)
    assert s is not None
    assert s.flow_lmin is None


def test_parse_attrs_flow_non_str():
    attrs = {"state": "3.5", "flow_rate": 12.5}
    s = parse_global_cop_attrs(attrs)
    assert s is not None
    assert s.flow_lmin == 12.5


def test_bucket_none():
    assert bucket_for_outdoor(None) == "unknown"


def test_bucket_normal():
    assert bucket_for_outdoor(7.0) == "6-8"
    assert bucket_for_outdoor(-3.0) == "-4--2"


def test_bucket_below_minus_ten():
    assert bucket_for_outdoor(-15.0) == "-10-"


def test_bucket_above_twenty():
    assert bucket_for_outdoor(25.0) == "20+"
    assert bucket_for_outdoor(20.0) == "20+"


def test_group_empty():
    assert _group_by_bucket([]) == {}


def test_group_skips_invalid():
    samples = [
        CopSample(cop=3.0, outdoor=7.0, data_quality="Good"),
        CopSample(cop=0.0, outdoor=7.0, data_quality="Good"),
        CopSample(cop=3.0, outdoor=7.0, defrost=True, data_quality="Good"),
    ]
    g = _group_by_bucket(samples)
    assert "6-8" in g
    assert len(g["6-8"]) == 1


def test_avg_empty():
    assert _avg([]) is None


def test_avg_values():
    assert _avg([1.0, 2.0, 3.0]) == 2.0


def test_analyze_empty_returns_default():
    a = analyze_stooklijn([])
    assert isinstance(a, StooklijnAdvies)
    assert a.state == "unknown"


def test_analyze_last_invalid_falls_back():
    samples = [
        CopSample(cop=3.0, lwt=35.0, outdoor=7.0, data_quality="Good"),
        CopSample(cop=0.0, lwt=35.0, outdoor=7.0, data_quality="Good"),
    ]
    a = analyze_stooklijn(samples)
    assert a.bucket == "6-8"
    assert a.huidige_lwt == 35.0


def test_analyze_too_few_samples():
    samples = [
        CopSample(cop=3.0, lwt=35.0, outdoor=7.0, data_quality="Good")
        for _ in range(3)
    ]
    a = analyze_stooklijn(samples)
    assert a.state == "unknown"
    assert a.samples == 3


def test_analyze_avg_cop_none():
    samples = [
        CopSample(cop=3.0, lwt=None, outdoor=7.0, data_quality="Good")
        for _ in range(6)
    ]
    a = analyze_stooklijn(samples)
    assert a.state == "unknown"


def test_analyze_recent_lwt_none():
    samples = [
        CopSample(cop=3.0, lwt=35.0, outdoor=7.0, data_quality="Good")
        for _ in range(5)
    ]
    samples.append(
        CopSample(cop=3.0, lwt=None, outdoor=7.0, data_quality="Good")
    )
    a = analyze_stooklijn(samples)
    assert a.state == "unknown"


def test_analyze_verlaag():
    samples = [
        CopSample(cop=3.0, lwt=30.0, outdoor=7.0, data_quality="Good")
        for _ in range(5)
    ]
    samples.append(
        CopSample(cop=3.5, lwt=35.0, outdoor=7.0, data_quality="Good")
    )
    a = analyze_stooklijn(samples)
    assert a.state == "verlaag_lwt_2c"
    assert a.besparing_cop_pct > 0


def test_analyze_verhoog():
    samples = [
        CopSample(cop=3.0, lwt=35.0, outdoor=7.0, data_quality="Good")
        for _ in range(5)
    ]
    samples.append(
        CopSample(cop=3.0, lwt=30.0, outdoor=7.0, data_quality="Good")
    )
    a = analyze_stooklijn(samples)
    assert a.state == "verhoog_lwt_2c"


def test_analyze_behoud():
    samples = [
        CopSample(cop=3.0, lwt=32.0, outdoor=7.0, data_quality="Good")
        for _ in range(6)
    ]
    a = analyze_stooklijn(samples)
    assert a.state == "behoud"


def test_analyze_comfort_guard():
    samples = [
        CopSample(cop=3.0, lwt=30.0, outdoor=7.0, data_quality="Good")
        for _ in range(5)
    ]
    samples.append(
        CopSample(cop=3.5, lwt=40.0, outdoor=7.0, data_quality="Good")
    )
    a = analyze_stooklijn(samples, comfort_min=22.0, indoor_avg=21.0)
    assert a.state == "behoud"
    assert a.comfort_impact < 0


def test_analyze_indoor_avg_set_after_state():
    samples = [
        CopSample(cop=3.0, lwt=30.0, outdoor=7.0, data_quality="Good")
        for _ in range(5)
    ]
    samples.append(
        CopSample(cop=3.5, lwt=35.0, outdoor=7.0, data_quality="Good")
    )
    a = analyze_stooklijn(samples, comfort_min=10.0, indoor_avg=21.0)
    assert a.state == "verlaag_lwt_2c"
    assert a.comfort_impact != 0.0


def test_sort_key_unknown():
    assert _bucket_sort_key("unknown") == 9999


def test_sort_key_20plus():
    assert _bucket_sort_key("20+") == 20


def test_sort_key_minus10():
    assert _bucket_sort_key("-10-") == -10


def test_sort_key_normal():
    assert _bucket_sort_key("6-8") == 6
    assert _bucket_sort_key("-4--2") == -4


def test_bucket_summary_empty():
    assert bucket_summary([]) == {}


def test_bucket_summary_multiple():
    # FIX: 7.0 and 7.5 both in "6-8" (int(3.25)*2=6, int(3.75)*2=6)
    samples = [
        CopSample(cop=3.0, lwt=30.0, outdoor=7.0, data_quality="Good"),
        CopSample(cop=3.5, lwt=31.0, outdoor=7.5, data_quality="Good"),
        CopSample(cop=2.5, lwt=35.0, outdoor=-3.0, data_quality="Good"),
    ]
    out = bucket_summary(samples)
    assert "6-8" in out
    assert out["6-8"]["n"] == 2
    assert out["6-8"]["cop"] == 3.25
    assert out["6-8"]["lwt"] == 30.5
    assert "-4--2" in out


def test_bucket_summary_lwt_none():
    samples = [
        CopSample(cop=3.0, lwt=None, outdoor=7.0, data_quality="Good"),
    ]
    out = bucket_summary(samples)
    assert out["6-8"]["lwt"] is None


def test_bucket_summary_sort_order():
    # covers _bucket_sort_key with multiple buckets sorted numerically
    samples = [
        CopSample(cop=3.0, lwt=30.0, outdoor=-5.0, data_quality="Good"),
        CopSample(cop=3.0, lwt=30.0, outdoor=7.0, data_quality="Good"),
        CopSample(cop=3.0, lwt=30.0, outdoor=22.0, data_quality="Good"),
    ]
    out = bucket_summary(samples)
    keys = list(out.keys())
    # order should be: -6--4, 6-8, 20+
    assert keys[0] == "-6--4"
    assert keys[-1] == "20+"

