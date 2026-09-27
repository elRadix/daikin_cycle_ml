"""Batch 52e-3: edge coverage for ml/adaptive_thresholds.py (marker: batch-52e3-adaptive-coverage)."""
from __future__ import annotations

from custom_components.daikin_cycle_ml.ml.adaptive_thresholds import (
    AdaptiveThresholds,
)


def test_observe_cycle_bad_duration_type():
    at = AdaptiveThresholds(min_samples=2)
    assert at.observe_cycle('heating', 'abc') is False


def test_observe_cycle_bad_off_type():
    at = AdaptiveThresholds(min_samples=2)
    assert at.observe_cycle('heating', 900.0, 'xyz') is True
    assert at.sample_count('heating')['run'] == 1
    assert at.sample_count('heating')['off'] == 0


def test_observe_day_none():
    at = AdaptiveThresholds(min_samples=2)
    assert at.observe_day(None) is False


def test_observe_day_bad_type():
    at = AdaptiveThresholds(min_samples=2)
    assert at.observe_day('abc') is False


def test_observe_day_negative():
    at = AdaptiveThresholds(min_samples=2)
    assert at.observe_day(-1) is False
