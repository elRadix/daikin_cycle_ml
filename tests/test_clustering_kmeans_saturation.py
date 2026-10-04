"""Regression: kmeans inertia saturates on overflow (Audit v44.0 A1)."""
import sys
from custom_components.daikin_cycle_ml.ml.clustering import kmeans

EXTREME = 2.6815615859885194e154  # (x)**2 would overflow float64


def test_kmeans_saturates_inertia_on_extreme_vectors():
    r = kmeans([[0.0, 0.0], [0.0, EXTREME]], k=1, seed=42)
    assert r.k == 1
    assert len(r.labels) == 2
    assert r.inertia == sys.float_info.max
