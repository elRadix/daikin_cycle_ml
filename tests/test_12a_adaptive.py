"""Tests for 12a: adaptive thresholds (pure percentile learning)."""
from __future__ import annotations

from custom_components.daikin_cycle_ml.ml.adaptive_thresholds import (
    AdaptiveThresholds,
    _clamp_int,
    _percentile,
)


def test_percentile_single_value():
    assert _percentile([5.0], 20.0) == 5.0


def test_percentile_empty_raises():
    try:
        _percentile([], 50.0)
    except ValueError:
        return
    assert False, 'expected ValueError'


def test_percentile_edges():
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert _percentile(vals, 0.0) == 1.0
    assert _percentile(vals, 100.0) == 5.0
    assert _percentile(vals, 50.0) == 3.0


def test_percentile_interpolates():
    vals = [1.0, 2.0, 3.0, 4.0]
    p25 = _percentile(vals, 25.0)
    assert 1.0 < p25 < 2.0


def test_clamp_int_bounds():
    assert _clamp_int(0.4, 1, 10) == 1
    assert _clamp_int(50.5, 1, 10) == 10
    assert _clamp_int(5.6, 1, 10) == 6


def test_observe_cycle_stores_both():
    at = AdaptiveThresholds(min_samples=3)
    assert at.observe_cycle('heating', 900.0, 600.0) is True
    counts = at.sample_count('heating')
    assert counts['run'] == 1
    assert counts['off'] == 1


def test_observe_cycle_skips_invalid():
    at = AdaptiveThresholds(min_samples=3)
    assert at.observe_cycle('heating', None, None) is False
    assert at.observe_cycle('heating', -10.0, None) is False
    assert at.sample_count('heating')['run'] == 0


def test_learn_short_run_returns_none_below_min():
    at = AdaptiveThresholds(min_samples=5)
    for d in (600, 700, 800):
        at.observe_cycle('heating', d, None)
    assert at.learn_short_run_min('heating') is None


def test_learn_short_run_p20():
    at = AdaptiveThresholds(min_samples=5)
    # 5 samples: 5, 10, 15, 20, 25 min -> p20 near 10
    for m in (5, 10, 15, 20, 25):
        at.observe_cycle('heating', m * 60.0, None)
    v = at.learn_short_run_min('heating')
    assert v is not None
    assert 8 <= v <= 12


def test_learn_good_off_p50():
    at = AdaptiveThresholds(min_samples=5)
    for m in (5, 10, 15, 20, 25):
        at.observe_cycle('heating', None, m * 60.0)
    v = at.learn_good_off_min('heating')
    assert v == 15


def test_learn_target_cycles_per_day():
    at = AdaptiveThresholds(min_samples=20)
    for c in (6, 8, 10, 12, 14):
        at.observe_day(c)
    v = at.learn_target_cycles_per_day()
    assert v is not None
    assert 8 <= v <= 12


def test_learn_target_returns_none_when_empty():
    at = AdaptiveThresholds()
    assert at.learn_target_cycles_per_day() is None


def test_modes_isolation():
    at = AdaptiveThresholds(min_samples=2)
    for _ in range(5):
        at.observe_cycle('heating', 900.0, None)
        at.observe_cycle('dhw', 300.0, None)
    h = at.learn_short_run_min('heating')
    d = at.learn_short_run_min('dhw')
    assert h is not None and h >= 14
    assert d is not None and d <= 6


def test_suggest_returns_available_keys():
    at = AdaptiveThresholds(min_samples=3)
    for _ in range(5):
        at.observe_cycle('heating', 1200.0, 900.0)
    for _ in range(5):
        at.observe_day(10)
    s = at.suggest('heating')
    assert 'short_run_threshold_min' in s
    assert 'good_off_threshold_min' in s
    assert 'target_cycles_per_day' in s


def test_clamp_upper_bound_run():
    at = AdaptiveThresholds(min_samples=2)
    for _ in range(10):
        at.observe_cycle('heating', 99999 * 60.0, None)
    v = at.learn_short_run_min('heating')
    assert v == 240


def test_to_from_dict_roundtrip():
    at = AdaptiveThresholds(min_samples=7)
    at.observe_cycle('heating', 900.0, 600.0)
    at.observe_cycle('dhw', 300.0, None)
    at.observe_day(8)
    at.observe_day(12)
    d = at.to_dict()
    restored = AdaptiveThresholds.from_dict(d)
    assert restored.min_samples == 7
    assert restored.sample_count('heating')['run'] == 1
    assert restored.sample_count('dhw')['run'] == 1
    assert restored.sample_count('heating')['days'] == 2


def test_from_dict_empty_returns_fresh():
    at = AdaptiveThresholds.from_dict(None)
    assert at.total_samples() == 0
    assert at.modes() == []


def test_reset_mode_only():
    at = AdaptiveThresholds(min_samples=2)
    at.observe_cycle('heating', 900.0, None)
    at.observe_cycle('dhw', 300.0, None)
    at.reset('heating')
    assert at.sample_count('heating')['run'] == 0
    assert at.sample_count('dhw')['run'] == 1


def test_reset_all():
    at = AdaptiveThresholds(min_samples=2)
    at.observe_cycle('heating', 900.0, 600.0)
    at.observe_day(10)
    at.reset()
    assert at.total_samples() == 0
    assert at.learn_target_cycles_per_day() is None


def test_total_samples_counts_both():
    at = AdaptiveThresholds(min_samples=2)
    at.observe_cycle('heating', 900.0, 600.0)
    at.observe_cycle('heating', 950.0, None)
    assert at.total_samples() == 3

