"""Batch COV-5: anomaly_engine + clustering edge tests.

Targets:
  engine/anomaly_engine.py  (41-42, 69)
  ml/clustering.py          (34->33, 45, 83->88, 159->168, 198, 219, 236)

Includes Hypothesis property tests for mathematical invariants:
  - classify_severity is monotonic + abs-symmetric
  - _euclidean is symmetric
  - nearest_centroid(v, [v]) == 0
  - kmeans is deterministic for a fixed seed
"""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from custom_components.daikin_cycle_ml.engine.anomaly_engine import (
    SEV_CRITICAL,
    SEV_NORMAL,
    SEV_WARN,
    SEV_WATCH,
    _message,
    _opt_float,
    classify_severity,
)
from custom_components.daikin_cycle_ml.ml.clustering import (
    ClusteringResult,
    _euclidean,
    _mean_vector,
    classify_clusters,
    kmeans,
    labels_to_dict,
    nearest_centroid,
)


# ============ anomaly_engine.py ============

def test_opt_float_bad_value_returns_default():
    assert _opt_float({"watch_z": "not-a-number"}, "watch_z", 2.0) == 2.0


def test_opt_float_none_options():
    assert _opt_float(None, "watch_z", 3.0) == 3.0


def test_message_watch_severity():
    msg = _message(SEV_WATCH, 2.5, 3)
    assert msg.startswith("Watch:")
    assert "dim 3" in msg


def test_message_normal():
    assert _message(SEV_NORMAL, 0.5, None) == "No anomaly"


def test_message_critical_no_top_dim():
    msg = _message(SEV_CRITICAL, 6.0, None)
    assert "any dim" in msg
    assert "Critical" in msg


def test_message_warn_with_top_dim():
    msg = _message(SEV_WARN, 3.5, 7)
    assert "dim 7" in msg
    assert "Anomaly" in msg


# ============ clustering.py ============

def test_cluster_sizes_invalid_label_skipped():
    r = ClusteringResult(labels=[0, 1, 5, 2, -1], k=3)
    assert r.cluster_sizes() == [1, 1, 1]


def test_mean_vector_empty():
    assert _mean_vector([], 4) == [0.0, 0.0, 0.0, 0.0]


def test_kmeans_tolerance_negative_forces_exhaustion():
    # tolerance < 0 guarantees the loop never breaks early
    vectors = [[0.0, 0.0], [10.0, 0.0], [20.0, 0.0], [30.0, 0.0]]
    r = kmeans(vectors, k=2, max_iter=3, tolerance=-1.0, seed=1)
    assert r.iterations == 3
    assert len(r.centroids) == 2


def test_kmeans_plusplus_duplicate_points_hits_total_zero():
    # all identical -> d2 all zero -> total == 0 branch
    vectors = [[1.0, 2.0], [1.0, 2.0], [1.0, 2.0]]
    r = kmeans(vectors, k=2, seed=7)
    assert r.k == 2
    assert all(lbl in (0, 1) for lbl in r.labels)


def test_nearest_centroid_wrong_dim_returns_none():
    # both candidates skipped due to dim mismatch
    assert nearest_centroid([1.0, 2.0], [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]) is None


def test_nearest_centroid_skips_non_list_tuple():
    assert nearest_centroid([1.0, 2.0], ["nope", [1.0, 2.0]]) == 1


def test_classify_clusters_empty():
    assert classify_clusters([]) == {}


def test_classify_clusters_single():
    assert classify_clusters([[10.0, 5.0]]) == {0: "normal"}


def test_classify_clusters_three_covers_normal_fill():
    # 3 centroids: one pendulum (smallest dim0), one dhw_like
    # (largest dim1 among remaining), one normal (line 236)
    centroids = [[1.0, 5.0], [10.0, 20.0], [5.0, 3.0]]
    labels = classify_clusters(centroids)
    assert labels[0] == "pendulum"
    assert labels[1] == "dhw_like"
    assert labels[2] == "normal"


def test_labels_to_dict_roundtrip():
    r = kmeans([[0.0, 0.0], [10.0, 0.0]], k=2, seed=1)
    d = labels_to_dict(r)
    assert set(d.keys()) >= {"k", "n", "iterations", "inertia",
                             "labels", "centroids", "cluster_sizes"}


# ============ Hypothesis property tests ============

_SEV_ORDER = {SEV_NORMAL: 0, SEV_WATCH: 1, SEV_WARN: 2, SEV_CRITICAL: 3}

_floats = st.floats(
    allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6
)
_z = st.floats(
    allow_nan=False, allow_infinity=False, min_value=0.0, max_value=10.0
)


@given(z=_z)
@settings(max_examples=80, deadline=None)
def test_sev_abs_symmetric(z):
    assert classify_severity(z) == classify_severity(-z)


@given(z1=_z, z2=_z)
@settings(max_examples=80, deadline=None)
def test_sev_monotonic(z1, z2):
    if z1 <= z2:
        assert _SEV_ORDER[classify_severity(z1)] <= _SEV_ORDER[classify_severity(z2)]


@given(xs=st.lists(_floats, min_size=1, max_size=8))
@settings(max_examples=80, deadline=None)
def test_euclidean_symmetric(xs):
    ys = [x + 1.0 for x in xs]
    a = _euclidean(xs, ys)
    b = _euclidean(ys, xs)
    assert abs(a - b) < 1e-6


@given(v=st.lists(_floats, min_size=1, max_size=8))
@settings(max_examples=60, deadline=None)
def test_nearest_centroid_self_is_zero(v):
    assert nearest_centroid(list(v), [list(v)]) == 0


@given(
    vs=st.lists(st.lists(_floats, min_size=1, max_size=4),
                min_size=2, max_size=6),
    seed=st.integers(min_value=0, max_value=10_000),
)
@settings(max_examples=40, deadline=None)
def test_kmeans_deterministic(vs, seed):
    dim = len(vs[0])
    vs = [v for v in vs if len(v) == dim]
    if len(vs) < 2:
        return
    r1 = kmeans(vs, k=2, seed=seed)
    r2 = kmeans(vs, k=2, seed=seed)
    assert r1.labels == r2.labels
    assert r1.centroids == r2.centroids
