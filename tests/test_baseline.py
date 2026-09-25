"""Tests for ml.baseline (Batch 7a)."""
from __future__ import annotations

import math

import pytest

from custom_components.daikin_cycle_ml.ml.baseline import (
    DEFAULT_Z_THRESHOLD,
    MIN_SAMPLES_FOR_Z,
    Baseline,
)


def test_init_rejects_zero_dim():
    with pytest.raises(ValueError):
        Baseline(0)


def test_init_dim_and_count():
    b = Baseline(3)
    assert b.dim == 3
    assert b.sample_count == 0


def test_initial_mean_zeros():
    b = Baseline(3)
    assert b.mean == [0.0, 0.0, 0.0]


def test_initial_std_zeros():
    b = Baseline(3)
    assert b.std == [0.0, 0.0, 0.0]


def test_update_single_vector_sets_mean():
    b = Baseline(2)
    b.update([4.0, 8.0])
    assert b.mean == [4.0, 8.0]
    assert b.sample_count == 1


def test_update_wrong_dim_raises():
    b = Baseline(2)
    with pytest.raises(ValueError):
        b.update([1.0, 2.0, 3.0])


def test_fit_two_vectors_mean():
    b = Baseline(2)
    b.fit([[0.0, 0.0], [2.0, 4.0]])
    assert b.mean == [1.0, 2.0]


def test_fit_std_matches_formula():
    b = Baseline(1)
    b.fit([[1.0], [3.0]])
    # sample std = sqrt(((1-2)^2 + (3-2)^2)/(2-1)) = sqrt(2)
    assert abs(b.std[0] - math.sqrt(2.0)) < 1e-9


def test_fit_resets_previous_state():
    b = Baseline(1)
    b.fit([[10.0], [20.0], [30.0]])
    b.fit([[1.0], [1.0]])
    assert b.mean == [1.0]
    assert b.sample_count == 2


def test_z_scores_below_min_samples():
    b = Baseline(1)
    b.update([5.0])
    b.update([6.0])
    assert b.z_scores([100.0]) == [0.0]  # n=2 < MIN_SAMPLES_FOR_Z


def test_z_scores_zero_for_std_zero_dim():
    b = Baseline(2)
    b.fit([[1.0, 5.0], [1.0, 7.0], [1.0, 9.0]])
    zs = b.z_scores([1.0, 7.0])
    assert zs[0] == 0.0  # zero variance dim
    assert zs[1] == 0.0  # at mean


def test_z_scores_value_at_mean_is_zero():
    b = Baseline(1)
    b.fit([[1.0], [2.0], [3.0], [4.0]])
    assert abs(b.z_scores([2.5])[0]) < 1e-9


def test_max_abs_z_for_outlier():
    b = Baseline(1)
    b.fit([[1.0], [2.0], [3.0], [4.0], [5.0]])
    z = b.max_abs_z([100.0])
    assert z > 3.0


def test_max_abs_z_zero_below_min_samples():
    b = Baseline(1)
    b.update([1.0])
    assert b.max_abs_z([999.0]) == 0.0


def test_is_anomaly_default_threshold():
    b = Baseline(1)
    b.fit([[1.0], [2.0], [3.0], [4.0], [5.0]])
    assert b.is_anomaly([100.0]) is True
    assert b.is_anomaly([3.0]) is False


def test_is_anomaly_custom_threshold():
    b = Baseline(1)
    b.fit([[1.0], [2.0], [3.0], [4.0], [5.0]])
    assert b.is_anomaly([10.0], threshold=100.0) is False


def test_top_dim_returns_none_when_no_signal():
    b = Baseline(3)
    b.fit([[1.0, 1.0, 1.0]] * 5)
    assert b.top_dim([1.0, 1.0, 1.0]) is None


def test_top_dim_returns_largest_z_index():
    b = Baseline(3)
    b.fit([[1.0, 1.0, 1.0], [3.0, 3.0, 3.0], [5.0, 5.0, 5.0]])
    idx = b.top_dim([1.0, 50.0, 1.0])
    assert idx == 1


def test_to_dict_roundtrip():
    b = Baseline(2)
    b.fit([[1.0, 2.0], [3.0, 4.0]])
    d = b.to_dict()
    b2 = Baseline.from_dict(d)
    assert b2.dim == 2
    assert b2.sample_count == 2
    assert b2.mean == b.mean


def test_to_json_roundtrip():
    b = Baseline(1)
    b.fit([[1.0], [2.0], [3.0]])
    raw = b.to_json()
    b2 = Baseline.from_json(raw)
    assert b2.mean == b.mean
    assert b2.sample_count == 3


def test_from_dict_empty_mean_falls_back_zeros():
    b = Baseline.from_dict({"dim": 2, "n": 0})
    assert b.mean == [0.0, 0.0]
    assert b.std == [0.0, 0.0]


def test_min_samples_constant_is_reasonable():
    assert MIN_SAMPLES_FOR_Z >= 2
    assert DEFAULT_Z_THRESHOLD > 0
