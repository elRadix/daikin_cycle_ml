"""Tests for ml.clustering (Batch 7b)."""
from __future__ import annotations

import pytest

from custom_components.daikin_cycle_ml.ml.clustering import (
    ClusteringResult,
    kmeans,
    labels_to_dict,
)


def _two_blobs():
    # 20 points close to (0,0), 20 close to (10,10)
    a = [[0.0 + i * 0.01, 0.0 + i * 0.01] for i in range(20)]
    b = [[10.0 + i * 0.01, 10.0 + i * 0.01] for i in range(20)]
    return a + b


def test_kmeans_returns_result_dataclass():
    r = kmeans(_two_blobs(), k=2)
    assert isinstance(r, ClusteringResult)


def test_kmeans_labels_length():
    r = kmeans(_two_blobs(), k=2)
    assert len(r.labels) == 40


def test_kmeans_centroids_count_matches_k():
    r = kmeans(_two_blobs(), k=2)
    assert len(r.centroids) == 2


def test_kmeans_separates_two_blobs():
    r = kmeans(_two_blobs(), k=2)
    sizes = sorted(r.cluster_sizes())
    assert sizes == [20, 20]


def test_kmeans_two_distinct_labels():
    r = kmeans(_two_blobs(), k=2)
    assert set(r.labels) == {0, 1}


def test_kmeans_deterministic_same_seed():
    v = _two_blobs()
    r1 = kmeans(v, k=2, seed=42)
    r2 = kmeans(v, k=2, seed=42)
    assert r1.labels == r2.labels


def test_kmeans_empty_raises():
    with pytest.raises(ValueError):
        kmeans([], k=2)


def test_kmeans_zero_k_raises():
    with pytest.raises(ValueError):
        kmeans([[1.0]], k=0)


def test_kmeans_zero_dim_raises():
    with pytest.raises(ValueError):
        kmeans([[]], k=1)


def test_kmeans_mismatched_dim_raises():
    with pytest.raises(ValueError):
        kmeans([[1.0, 2.0], [1.0]], k=1)


def test_kmeans_k_greater_than_n_clamps():
    r = kmeans([[1.0], [2.0]], k=10)
    assert r.k == 2
    assert len(r.centroids) == 2


def test_kmeans_k_one_gives_single_label():
    r = kmeans([[1.0], [2.0], [3.0]], k=1)
    assert r.k == 1
    assert set(r.labels) == {0}


def test_kmeans_inertia_non_negative():
    r = kmeans(_two_blobs(), k=2)
    assert r.inertia >= 0.0


def test_kmeans_iterations_within_cap():
    r = kmeans(_two_blobs(), k=2, max_iter=5)
    assert r.iterations <= 5


def test_cluster_sizes_sum_to_n():
    r = kmeans(_two_blobs(), k=2)
    assert sum(r.cluster_sizes()) == r.n_samples


def test_labels_to_dict_keys():
    r = kmeans(_two_blobs(), k=2)
    d = labels_to_dict(r)
    assert set(d.keys()) == {
        "k", "n", "iterations", "inertia",
        "labels", "centroids", "cluster_sizes",
    }


def test_labels_to_dict_roundtrip_sizes():
    r = kmeans(_two_blobs(), k=2)
    d = labels_to_dict(r)
    assert d["n"] == r.n_samples
    assert d["k"] == r.k
    assert d["cluster_sizes"] == r.cluster_sizes()


def test_kmeans_identical_points_single_cluster_semantics():
    # 3 identical points, k=3: should still work, sizes sum to 3
    r = kmeans([[1.0, 1.0]] * 3, k=3)
    assert r.n_samples == 3
    assert sum(r.cluster_sizes()) == 3
