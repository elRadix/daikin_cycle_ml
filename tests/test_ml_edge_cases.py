"""ML edge cases: adaptive thresholds, baselines, kmeans, anomaly."""
from __future__ import annotations

import pytest

from custom_components.daikin_cycle_ml.ml.adaptive_thresholds import (
    AdaptiveThresholds, MIN_RUN_MIN,
)
from custom_components.daikin_cycle_ml.ml.baseline import (
    Baseline, AdaptiveBaseline, baseline_from_dict,
)
from custom_components.daikin_cycle_ml.ml.clustering import (
    kmeans, classify_clusters, nearest_centroid, labels_to_dict,
)
from custom_components.daikin_cycle_ml.ml.multi_baseline import MultiBaseline


def test_adaptive_empty_returns_none():
    t = AdaptiveThresholds(min_samples=20)
    assert t.learn_short_run_min("heating") is None
    assert t.learn_good_off_min("heating") is None
    assert t.learn_target_cycles_per_day() is None


def test_adaptive_below_min_samples_returns_none():
    t = AdaptiveThresholds(min_samples=20)
    for _ in range(19):
        t.observe_cycle("heating", duration_s=3600, off_s=300)
    assert t.learn_short_run_min("heating") is None


def test_adaptive_at_min_samples_learns():
    t = AdaptiveThresholds(min_samples=20)
    for i in range(20):
        t.observe_cycle("heating", duration_s=3600 + i, off_s=300 + i)
    assert t.learn_short_run_min("heating") is not None


def test_adaptive_clamps_short_run():
    t = AdaptiveThresholds(min_samples=10)
    for _ in range(10):
        t.observe_cycle("heating", duration_s=1)
    assert t.learn_short_run_min("heating") == MIN_RUN_MIN


def test_adaptive_modes_isolated():
    t = AdaptiveThresholds(min_samples=5)
    for _ in range(10):
        t.observe_cycle("heating", duration_s=600, off_s=120)
    assert t.learn_short_run_min("heating") is not None
    assert t.learn_short_run_min("dhw") is None


def test_adaptive_reset_specific_mode():
    t = AdaptiveThresholds(min_samples=5)
    for _ in range(10):
        t.observe_cycle("heating", duration_s=600, off_s=120)
        t.observe_cycle("dhw", duration_s=1200, off_s=60)
    t.reset("heating")
    assert t.learn_short_run_min("heating") is None
    assert t.learn_short_run_min("dhw") is not None


def test_adaptive_to_dict_roundtrip():
    t = AdaptiveThresholds(min_samples=5)
    for _ in range(10):
        t.observe_cycle("heating", duration_s=600, off_s=120)
    d = t.to_dict()
    t2 = AdaptiveThresholds.from_dict(d)
    assert t2.sample_count("heating") == t.sample_count("heating")


def test_welford_baseline_std_zero_for_single_sample():
    b = Baseline(dim=3)
    b.update([1.0, 2.0, 3.0])
    assert b.std == [0.0, 0.0, 0.0]
    assert b.z_scores([1.0, 2.0, 3.0]) == [0.0, 0.0, 0.0]


def test_welford_baseline_exact():
    b = Baseline(dim=1)
    for v in (10, 20, 30):
        b.update([v])
    assert b.mean[0] == pytest.approx(20.0)
    assert b.std[0] == pytest.approx(10.0, abs=0.01)


def test_welford_baseline_needs_min_samples_for_z():
    from custom_components.daikin_cycle_ml.ml.baseline import MIN_SAMPLES_FOR_Z
    b = Baseline(dim=1)
    for _ in range(MIN_SAMPLES_FOR_Z - 1):
        b.update([10.0])
    assert b.z_scores([100.0]) == [0.0]


def test_ewma_baseline_skips_outliers():
    b = AdaptiveBaseline(dim=1, alpha=0.1, outlier_skip_z=5.0, min_samples_before_skip=3)
    for _ in range(10):
        b.update([10.0])
    assert b.sample_count == 10
    result = b.update([1000.0])
    assert result is False
    assert b.sample_count == 10


def test_ewma_baseline_zero_variance_accepts_identical():
    b = AdaptiveBaseline(dim=1, alpha=0.1, outlier_skip_z=5.0, min_samples_before_skip=3)
    for _ in range(10):
        b.update([10.0])
    result = b.update([10.0])
    assert result is True
    assert b.sample_count == 11


def test_ewma_baseline_nonzero_variance_skips_outlier():
    b = AdaptiveBaseline(dim=1, alpha=0.1, outlier_skip_z=3.0, min_samples_before_skip=5)
    for i in range(10):
        b.update([5.0 if i % 2 == 0 else 15.0])
    result = b.update([1000.0])
    assert result is False


def test_ewma_baseline_alpha_clamped():
    from custom_components.daikin_cycle_ml.ml.baseline import MIN_ALPHA, MAX_ALPHA
    b = AdaptiveBaseline(dim=1, alpha=-0.5)
    assert b.alpha == MIN_ALPHA
    b2 = AdaptiveBaseline(dim=1, alpha=99.0)
    assert b2.alpha == MAX_ALPHA


def test_baseline_from_dict_dispatches_ewma():
    b = AdaptiveBaseline(dim=2)
    b.update([1.0, 2.0])
    restored = baseline_from_dict(b.to_dict())
    assert isinstance(restored, AdaptiveBaseline)


def test_baseline_from_dict_dispatches_welford():
    b = Baseline(dim=2)
    b.update([1.0, 2.0])
    restored = baseline_from_dict(b.to_dict())
    assert isinstance(restored, Baseline)
    assert not isinstance(restored, AdaptiveBaseline)


def test_kmeans_k1_returns_single_cluster():
    r = kmeans([[1.0], [2.0], [3.0]], k=1)
    assert r.k == 1
    assert r.labels == [0, 0, 0]


def test_kmeans_k_greater_than_n():
    r = kmeans([[1.0], [2.0]], k=5)
    assert r.k == 2


def test_kmeans_empty_raises():
    with pytest.raises(ValueError):
        kmeans([], k=3)


def test_kmeans_inconsistent_dims_raises():
    with pytest.raises(ValueError):
        kmeans([[1.0], [2.0, 3.0]], k=2)


def test_kmeans_deterministic_with_seed():
    vectors = [[float(i)] for i in range(10)]
    r1 = kmeans(vectors, k=3, seed=42)
    r2 = kmeans(vectors, k=3, seed=42)
    assert r1.labels == r2.labels


def test_kmeans_classify_pendulum_long_cycle():
    labels = classify_clusters([[1000.0], [3000.0], [10000.0]])
    assert labels[0] == "pendulum"
    assert labels[1] == "normal"
    assert labels[2] == "long_cycle"


def test_classify_empty_returns_empty():
    assert classify_clusters([]) == {}


def test_classify_single_returns_normal():
    assert classify_clusters([[1000.0]]) == {0: "normal"}


def test_nearest_centroid_empty_returns_none():
    assert nearest_centroid([1.0, 2.0], []) is None


def test_nearest_centroid_dim_mismatch_returns_none():
    assert nearest_centroid([1.0, 2.0], [[1.0, 2.0, 3.0]]) is None


def test_labels_to_dict_structure():
    r = kmeans([[0.0], [1.0], [10.0], [11.0]], k=2)
    d = labels_to_dict(r)
    assert set(d.keys()) == {"k", "n", "iterations", "inertia",
                              "labels", "centroids", "cluster_sizes"}


def test_multibaseline_isolates_modes():
    mb = MultiBaseline(dim=3)
    for _ in range(5):
        mb.update("heating", [10.0, 20.0, 30.0])
        mb.update("dhw", [50.0, 60.0, 70.0])
    heat = mb.get("heating")
    dhw = mb.get("dhw")
    assert heat.mean[0] == pytest.approx(10.0, abs=0.1)
    assert dhw.mean[0] == pytest.approx(50.0, abs=0.1)


def test_multibaseline_unknown_mode_default():
    mb = MultiBaseline(dim=2)
    mb.update(None, [1.0, 2.0])
    assert "unknown" in mb.modes()


def test_multibaseline_from_dict_migration():
    from custom_components.daikin_cycle_ml.ml.features import VECTOR_LEN_LEGACY, VECTOR_LEN
    old = {"dim": VECTOR_LEN_LEGACY, "baselines": {}}
    mb = MultiBaseline.from_dict(old)
    assert mb.dim == VECTOR_LEN
    assert mb._migrated_from_dim == VECTOR_LEN_LEGACY
