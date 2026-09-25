"""Tests for AdaptiveBaseline (Batch 11a)."""
from __future__ import annotations

import math

import pytest

from custom_components.daikin_cycle_ml.ml.baseline import (
    AdaptiveBaseline,
    Baseline,
    MAX_ALPHA,
    MIN_ALPHA,
    baseline_from_dict,
)


def test_alpha_clamped_above_max():
    b = AdaptiveBaseline(1, alpha=99.0)
    assert b.alpha == MAX_ALPHA


def test_alpha_clamped_below_min():
    b = AdaptiveBaseline(1, alpha=0.0)
    assert b.alpha == MIN_ALPHA


def test_first_sample_seeds_mean():
    b = AdaptiveBaseline(2, alpha=0.5)
    assert b.update([4.0, 8.0]) is True
    assert b.mean == [4.0, 8.0]
    assert b.sample_count == 1


def test_ewma_mean_formula_two_samples():
    b = AdaptiveBaseline(1, alpha=0.5)
    b.update([0.0])
    b.update([1.0])
    assert abs(b.mean[0] - 0.5) < 1e-9


def test_ewma_mean_after_three_samples():
    b = AdaptiveBaseline(1, alpha=0.5)
    b.update([0.0])
    b.update([1.0])
    b.update([2.0])
    # 0.5 * 0.5 + 0.5 * 2.0 = 1.25
    assert abs(b.mean[0] - 1.25) < 1e-9


def test_ewma_window_shrinks_with_alpha():
    # Larger alpha = more weight to recent. Compare after same input.
    b_slow = AdaptiveBaseline(1, alpha=0.01)
    b_fast = AdaptiveBaseline(1, alpha=0.5)
    for v in [10.0, 0.0, 0.0, 0.0, 0.0]:
        b_slow.update([v])
        b_fast.update([v])
    # b_slow mean stays closer to 10 (slower decay)
    assert b_slow.mean[0] > b_fast.mean[0]


def test_outlier_skip_when_enough_samples():
    b = AdaptiveBaseline(1, alpha=0.1, outlier_skip_z=3.0,
                         min_samples_before_skip=5)
    for i in range(10):
        b.update([float(i)])
    n_before = b.sample_count
    ok = b.update([9999.0])
    assert ok is False
    assert b.sample_count == n_before


def test_outlier_not_skipped_before_threshold():
    b = AdaptiveBaseline(1, alpha=0.1, outlier_skip_z=3.0,
                         min_samples_before_skip=100)
    for i in range(5):
        b.update([float(i)])
    n_before = b.sample_count
    ok = b.update([9999.0])
    assert ok is True
    assert b.sample_count == n_before + 1


def test_outlier_skip_disabled_when_zero():
    b = AdaptiveBaseline(1, alpha=0.1, outlier_skip_z=0.0,
                         min_samples_before_skip=5)
    for i in range(10):
        b.update([float(i)])
    assert b.update([9999.0]) is True


def test_wrong_dim_raises():
    b = AdaptiveBaseline(2)
    with pytest.raises(ValueError):
        b.update([1.0])


def test_fit_resets_and_rebuilds():
    b = AdaptiveBaseline(1, alpha=0.5)
    b.update([100.0])
    b.fit([[0.0], [1.0]])
    assert b.sample_count == 2
    assert abs(b.mean[0] - 0.5) < 1e-9


def test_std_zero_below_two_samples():
    b = AdaptiveBaseline(2, alpha=0.5)
    b.update([1.0, 1.0])
    assert b.std == [0.0, 0.0]


def test_std_non_negative():
    b = AdaptiveBaseline(1, alpha=0.3)
    for v in [1.0, 2.0, 3.0, 2.0, 1.0]:
        b.update([v])
    assert b.std[0] >= 0.0


def test_to_dict_includes_type_and_alpha():
    b = AdaptiveBaseline(2, alpha=0.25)
    d = b.to_dict()
    assert d["type"] == "ewma"
    assert d["alpha"] == 0.25
    assert "outlier_skip_z" in d


def test_from_dict_roundtrip_preserves_alpha():
    b = AdaptiveBaseline(1, alpha=0.25)
    b.update([5.0])
    b.update([7.0])
    b2 = AdaptiveBaseline.from_dict(b.to_dict())
    assert b2.alpha == b.alpha
    assert b2.mean == b.mean
    assert b2.sample_count == b.sample_count


def test_from_dict_default_alpha_when_missing():
    b = AdaptiveBaseline.from_dict({"type": "ewma", "dim": 1, "n": 0})
    assert b.alpha > 0.0


def test_baseline_from_dict_dispatches_welford():
    b = baseline_from_dict({"type": "welford", "dim": 1, "n": 0})
    assert isinstance(b, Baseline)
    assert not isinstance(b, AdaptiveBaseline)


def test_baseline_from_dict_dispatches_ewma():
    b = baseline_from_dict({"type": "ewma", "dim": 1, "n": 0})
    assert isinstance(b, AdaptiveBaseline)


def test_baseline_from_dict_missing_type_defaults_welford():
    b = baseline_from_dict({"dim": 1, "n": 0})
    assert type(b) is Baseline
