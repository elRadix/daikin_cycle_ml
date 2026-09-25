"""Lightweight k-means clustering (Batch 7b). Pure Python, no numpy."""
from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from typing import Any

_LOGGER = logging.getLogger(__name__)

DEFAULT_MAX_ITER = 100
DEFAULT_TOLERANCE = 1e-4
DEFAULT_SEED = 42
DEFAULT_K = 4
MIN_SAMPLES_PER_CLUSTER = 1


@dataclass
class ClusteringResult:
    labels: list[int] = field(default_factory=list)
    centroids: list[list[float]] = field(default_factory=list)
    inertia: float = 0.0
    iterations: int = 0
    k: int = 0

    @property
    def n_samples(self) -> int:
        return len(self.labels)

    def cluster_sizes(self) -> list[int]:
        sizes = [0] * self.k
        for lbl in self.labels:
            if 0 <= lbl < self.k:
                sizes[lbl] += 1
        return sizes


def _euclidean(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _mean_vector(vectors: list[list[float]], dim: int) -> list[float]:
    if not vectors:
        return [0.0] * dim
    out = [0.0] * dim
    for v in vectors:
        for i, x in enumerate(v):
            out[i] += x
    return [x / len(vectors) for x in out]


def _validate(vectors: list[list[float]]) -> int:
    if not vectors:
        raise ValueError("vectors must not be empty")
    dim = len(vectors[0])
    if dim == 0:
        raise ValueError("vectors must have dim >= 1")
    for v in vectors:
        if len(v) != dim:
            raise ValueError("all vectors must share dim")
    return dim


def _kmeans_plusplus_init(
    vectors: list[list[float]], k: int, rng: random.Random
) -> list[list[float]]:
    n = len(vectors)
    first = rng.randrange(n)
    centroids = [list(vectors[first])]
    while len(centroids) < k:
        d2 = []
        for v in vectors:
            best = min(_euclidean(v, c) ** 2 for c in centroids)
            d2.append(best)
        total = sum(d2)
        if total <= 0.0:
            idx = rng.randrange(n)
        else:
            r = rng.random() * total
            acc = 0.0
            idx = n - 1
            for i, w in enumerate(d2):
                acc += w
                if acc >= r:
                    idx = i
                    break
        centroids.append(list(vectors[idx]))
    return centroids


def _assign(
    vectors: list[list[float]], centroids: list[list[float]]
) -> tuple[list[int], float]:
    labels: list[int] = []
    inertia = 0.0
    for v in vectors:
        best_i, best_d = 0, float("inf")
        for i, c in enumerate(centroids):
            d = _euclidean(v, c)
            if d < best_d:
                best_d, best_i = d, i
        labels.append(best_i)
        inertia += best_d * best_d
    return labels, inertia


def _update_centroids(
    vectors: list[list[float]], labels: list[int], k: int, dim: int
) -> list[list[float]]:
    buckets: list[list[list[float]]] = [[] for _ in range(k)]
    for v, lbl in zip(vectors, labels):
        buckets[lbl].append(v)
    out: list[list[float]] = []
    for i in range(k):
        if not buckets[i]:
            out.append(_mean_vector(vectors, dim))  # orphan -> global mean
        else:
            out.append(_mean_vector(buckets[i], dim))
    return out


def _max_shift(a: list[list[float]], b: list[list[float]]) -> float:
    return max(
        (_euclidean(x, y) for x, y in zip(a, b)),
        default=0.0,
    )


def kmeans(
    vectors: list[list[float]],
    k: int = DEFAULT_K,
    *,
    max_iter: int = DEFAULT_MAX_ITER,
    tolerance: float = DEFAULT_TOLERANCE,
    seed: int = DEFAULT_SEED,
) -> ClusteringResult:
    """Deterministic k-means (seed-based). Handles k>=n by clamping k."""
    dim = _validate(vectors)
    n = len(vectors)
    if k <= 0:
        raise ValueError("k must be >= 1")
    k_eff = min(k, n)
    if k_eff == 1:
        centroid = _mean_vector(vectors, dim)
        labels = [0] * n
        inertia = sum(_euclidean(v, centroid) ** 2 for v in vectors)
        return ClusteringResult(
            labels=labels, centroids=[centroid],
            inertia=inertia, iterations=0, k=1,
        )

    rng = random.Random(seed)
    centroids = _kmeans_plusplus_init(vectors, k_eff, rng)
    labels: list[int] = [0] * n
    inertia = 0.0
    iters = 0

    for it in range(1, max_iter + 1):
        labels, inertia = _assign(vectors, centroids)
        new_centroids = _update_centroids(vectors, labels, k_eff, dim)
        shift = _max_shift(centroids, new_centroids)
        centroids = new_centroids
        iters = it
        if shift <= tolerance:
            break

    return ClusteringResult(
        labels=labels, centroids=centroids,
        inertia=inertia, iterations=iters, k=k_eff,
    )


def labels_to_dict(result: ClusteringResult) -> dict[str, Any]:
    """Export a compact dict (labels + centroids + sizes)."""
    return {
        "k": result.k,
        "n": result.n_samples,
        "iterations": result.iterations,
        "inertia": result.inertia,
        "labels": list(result.labels),
        "centroids": [list(c) for c in result.centroids],
        "cluster_sizes": result.cluster_sizes(),
    }


def nearest_centroid(vector: list[float], centroids: list[list[float]]) -> int | None:
    """Return index of nearest centroid by squared euclidean distance.

    Returns None if centroids is empty or dimensions mismatch all.
    """
    if not centroids:
        return None
    best_idx: int | None = None
    best_d = float("inf")
    for i, c in enumerate(centroids):
        if not isinstance(c, (list, tuple)) or len(c) != len(vector):
            continue
        d = 0.0
        for a, b in zip(vector, c):
            d += (float(a) - float(b)) ** 2
        if d < best_d:
            best_d = d
            best_idx = i
    return best_idx


def classify_clusters(centroids: list[list[float]]) -> dict[int, str]:
    """Assign semantic labels to cluster indices based on centroid properties.

    Heuristic:
      - Shortest mean duration (dim 0)          -> "pendulum"
      - Highest dT_max (dim 1) among remaining  -> "dhw_like"
      - Everything else                         -> "normal"

    Deterministic for a given centroid set.
    """
    if not centroids:
        return {}
    if len(centroids) == 1:
        return {0: "normal"}

    # sorted by duration ascending
    indexed = sorted(range(len(centroids)), key=lambda i: float(centroids[i][0]))

    labels: dict[int, str] = {}
    labels[indexed[0]] = "pendulum"

    remaining = indexed[1:]
    # highest dT_max among remaining
    dhw_idx = max(remaining, key=lambda i: float(centroids[i][1]))
    labels[dhw_idx] = "dhw_like"

    for i in remaining:
        if i not in labels:
            labels[i] = "normal"

    return labels
