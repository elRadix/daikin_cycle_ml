"""Per-mode k-means on standardised behaviour vectors (#443, ML v2).

The v1 job clustered the raw 12-dimension feature vectors of all modes
together (k = 3) and labelled clusters relatively: the shortest centroid
was always "pendulum". In the winter simulation 838 of 852 "pendulum"
cycles ran 20 minutes or more, DHW and transients shared clusters with
heating, and duration_s (seconds) dominated the unscaled distances.

v2:

- one model per mode (heating / DHW / cooling never share a cluster);
- transients and boiler co-fire cycles are left out of training;
- behaviour dimensions only, standardised with the mode's mean / std,
  stored with the model so training and assignment use the same scale;
- labels are absolute: a centroid whose run length is under the
  short-run threshold is "pendulum", over 180 min "long_cycle", else
  "normal" (two clusters can share a label).

Cluster ids are global ints (cycles.cluster_id): mode index * 10 + i.
Pure Python, no Home Assistant imports.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from .behaviour_baseline import BEHAVIOUR_DIMS, scaled_value, behaviour_values
from .clustering import kmeans, nearest_centroid

KMEANS_VERSION = 2
DEFAULT_K = 3
MIN_CYCLES_PER_MODE = 12
MIN_DIM_COVERAGE = 0.5        # a dimension measured in < 50 % of runs is dropped
LONG_CYCLE_MIN = 180.0
ID_STRIDE = 10


def _train_rows(
    cycles: Sequence[Mapping[str, Any]],
) -> dict[str, list[dict[str, float | None]]]:
    by_mode: dict[str, list[dict[str, float | None]]] = {}
    for rec in cycles:
        if rec.get("is_transient") or int(rec.get("boiler_contribution_samples") or 0) > 0:
            continue
        vals = behaviour_values(rec, lwt_avg=rec.get("lwt_avg"))
        if vals.get("duration_s") is None:
            continue
        mode = rec.get("mode") or "unknown"
        by_mode.setdefault(str(mode), []).append(vals)
    return by_mode


def _vector(
    vals: Mapping[str, float | None], dims: Sequence[str],
    mu: Sequence[float], sd: Sequence[float],
) -> list[float]:
    out: list[float] = []
    for name, m, s in zip(dims, mu, sd, strict=True):
        raw = vals.get(name)
        out.append(0.0 if raw is None else (scaled_value(name, raw) - m) / s)
    return out


def _label(duration_log_min: float, short_run_min: float) -> str:
    minutes = math.exp(duration_log_min)
    if minutes < short_run_min:
        return "pendulum"
    if minutes > LONG_CYCLE_MIN:
        return "long_cycle"
    return "normal"


def _train_mode(
    rows: list[dict[str, float | None]], short_run_min: float, k: int,
) -> dict[str, Any] | None:
    if len(rows) < MIN_CYCLES_PER_MODE:
        return None
    dims: list[str] = []
    mu: list[float] = []
    sd: list[float] = []
    for name in BEHAVIOUR_DIMS:
        xs = [scaled_value(name, r[name]) for r in rows if r.get(name) is not None]  # type: ignore[arg-type]
        if len(xs) < MIN_DIM_COVERAGE * len(rows):
            continue
        m = sum(xs) / len(xs)
        var = sum((x - m) ** 2 for x in xs) / len(xs)
        dims.append(name)
        mu.append(m)
        sd.append(max(math.sqrt(var), 1e-6))
    # duration is always kept: _train_rows drops runs without it
    vecs = [_vector(r, dims, mu, sd) for r in rows]
    res = kmeans(vecs, k=min(k, max(1, len(rows) // 4)))
    d_i = dims.index("duration_s")
    labels = [
        _label(c[d_i] * sd[d_i] + mu[d_i], short_run_min) for c in res.centroids
    ]
    return {
        "dims": dims,
        "mu": [round(x, 6) for x in mu],
        "sd": [round(x, 6) for x in sd],
        "centroids": [[round(x, 5) for x in c] for c in res.centroids],
        "labels": labels,
        "sizes": res.cluster_sizes(),
        "n": len(rows),
    }


def train(
    cycles: Sequence[Mapping[str, Any]],
    *,
    short_run_min: float = 20.0,
    k: int = DEFAULT_K,
) -> dict[str, Any]:
    """Train one model per mode. Returns the kmeans_state payload."""
    by_mode = _train_rows(cycles)
    modes: dict[str, Any] = {}
    for idx, mode in enumerate(sorted(by_mode)):
        model = _train_mode(by_mode[mode], short_run_min, k)
        if model is not None:
            model["id_base"] = idx * ID_STRIDE
            modes[mode] = model
    n = sum(m["n"] for m in modes.values())
    return {
        "version": KMEANS_VERSION,
        "short_run_min": short_run_min,
        "modes": modes,
        "n": n,
        "k": sum(len(m["centroids"]) for m in modes.values()),
    }


def assign(
    state: Mapping[str, Any] | None, mode: str | None, vals: Mapping[str, float | None],
) -> int | None:
    """Global cluster id of a cycle, or None (no model for the mode)."""
    if not isinstance(state, Mapping):
        return None
    model = (state.get("modes") or {}).get(mode or "unknown")
    if not isinstance(model, Mapping) or vals.get("duration_s") is None:
        return None
    try:
        vec = _vector(vals, model["dims"], model["mu"], model["sd"])
        i = nearest_centroid(vec, model["centroids"])
        return None if i is None else int(model["id_base"]) + i
    except (KeyError, TypeError, ValueError):
        return None


def labels(state: Mapping[str, Any] | None) -> dict[int, str]:
    """{global cluster id: label} for every mode model."""
    out: dict[int, str] = {}
    if not isinstance(state, Mapping):
        return out
    for model in (state.get("modes") or {}).values():
        try:
            base = int(model["id_base"])
            for i, lbl in enumerate(model["labels"]):
                out[base + i] = str(lbl)
        except (KeyError, TypeError, ValueError):
            continue
    return out


def centroids(state: Mapping[str, Any] | None) -> list[list[float]]:
    """All centroids (standardised), in global id order (diagnostics)."""
    out: list[list[float]] = []
    if not isinstance(state, Mapping):
        return out
    for model in sorted(
        (state.get("modes") or {}).values(), key=lambda m: int(m.get("id_base", 0)),
    ):
        out.extend(list(c) for c in model.get("centroids") or [])
    return out
