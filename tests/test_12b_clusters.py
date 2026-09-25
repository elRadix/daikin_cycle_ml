"""Tests for 12b: cluster activation (nearest_centroid + classify + wiring)."""
from __future__ import annotations

from custom_components.daikin_cycle_ml.ml.clustering import (
    classify_clusters,
    nearest_centroid,
)


def test_nearest_centroid_empty():
    assert nearest_centroid([1.0, 2.0], []) is None


def test_nearest_centroid_simple():
    c = [[0.0, 0.0], [10.0, 10.0], [20.0, 20.0]]
    assert nearest_centroid([1.0, 1.0], c) == 0
    assert nearest_centroid([11.0, 11.0], c) == 1
    assert nearest_centroid([19.0, 21.0], c) == 2


def test_nearest_centroid_dim_mismatch_skips():
    c = [[0.0, 0.0], [1.0, 2.0, 3.0]]
    # only first centroid matches dim, second is skipped
    assert nearest_centroid([0.5, 0.5], c) == 0


def test_classify_empty():
    assert classify_clusters([]) == {}


def test_classify_single():
    assert classify_clusters([[10.0, 5.0]]) == {0: "normal"}


def test_classify_three_typical():
    # index 0: short duration, low dT -> pendulum
    # index 1: long duration, high dT -> dhw_like
    # index 2: medium -> normal
    centroids = [
        [300.0, 3.0, 2.0, 40.0, 25.0, 2.0, 0.0, 0.0],   # pendulum
        [1800.0, 9.0, 7.0, 65.0, 55.0, 2.0, 1.0, 0.0],  # dhw
        [1500.0, 5.0, 4.0, 45.0, 32.0, 2.0, 0.0, 0.0],  # normal
    ]
    labels = classify_clusters(centroids)
    assert labels[0] == "pendulum"
    assert labels[1] == "dhw_like"
    assert labels[2] == "normal"


def test_classify_two_clusters():
    centroids = [
        [400.0, 3.0],   # short
        [2000.0, 8.0],  # long
    ]
    labels = classify_clusters(centroids)
    assert labels[0] == "pendulum"
    assert labels[1] == "dhw_like"


def test_coordinator_has_assign_cluster():
    from custom_components.daikin_cycle_ml import coordinator as cmod
    assert hasattr(cmod.DaikinCycleMLCoordinator, "_assign_cluster")


def test_coordinator_has_load_kmeans():
    from custom_components.daikin_cycle_ml import coordinator as cmod
    assert hasattr(cmod.DaikinCycleMLCoordinator, "_load_kmeans_state")


def test_snapshot_has_cluster_id():
    from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
    snap = DataSnapshot()
    assert hasattr(snap, "cluster_id")
    assert snap.cluster_id is None


def test_db_has_cluster_methods():
    from custom_components.daikin_cycle_ml.storage.db import CycleDB
    assert hasattr(CycleDB, "async_update_cycle_cluster")
    assert hasattr(CycleDB, "async_count_by_cluster")
    assert hasattr(CycleDB, "async_ensure_cluster_column")


def test_binary_sensor_has_cluster_class():
    from custom_components.daikin_cycle_ml import binary_sensor as bmod
    assert hasattr(bmod, "DaikinCycleMLClusterBinary")
    assert hasattr(bmod, "_build_cluster_binaries")


def test_en_translations_cluster_keys():
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "translations" / "en.json"
    data = json.loads(p.read_text())
    keys = data["entity"]["binary_sensor"]
    for k in ("cluster_pendulum", "cluster_normal", "cluster_dhw_like"):
        assert k in keys

