"""Regression: OverflowError in nearest_centroid (Audit v44.0 A1)."""
from custom_components.daikin_cycle_ml.ml.clustering import nearest_centroid

EXTREME = 2.6815615859885194e154  # (x)**2 would overflow float64


def test_nearest_centroid_handles_extreme_vectors():
    idx = nearest_centroid([0.0, 0.0], [[0.0, 0.0], [0.0, EXTREME]])
    assert idx == 0
