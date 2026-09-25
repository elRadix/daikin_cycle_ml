"""Anomaly classification on top of Baseline (Batch 7b). Pure Python."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Mapping

from ..ml.baseline import Baseline, DEFAULT_Z_THRESHOLD

_LOGGER = logging.getLogger(__name__)

SEV_NORMAL = "normal"
SEV_WATCH = "watch"
SEV_WARN = "warn"
SEV_CRITICAL = "critical"

DEFAULT_WATCH_Z = 2.0
DEFAULT_WARN_Z = 3.0
DEFAULT_CRITICAL_Z = 4.5


@dataclass(frozen=True)
class AnomalyResult:
    is_anomaly: bool
    severity: str
    max_abs_z: float
    top_dim: int | None
    top_dim_value: float
    message: str
    details: dict[str, Any] = field(default_factory=dict)


def _opt_float(
    options: Mapping[str, Any] | None, key: str, default: float
) -> float:
    if not options:
        return default
    try:
        return float(options.get(key, default))
    except (TypeError, ValueError):
        return default


def classify_severity(
    max_abs_z: float,
    *,
    watch: float = DEFAULT_WATCH_Z,
    warn: float = DEFAULT_WARN_Z,
    critical: float = DEFAULT_CRITICAL_Z,
) -> str:
    z = abs(float(max_abs_z))
    if z >= critical:
        return SEV_CRITICAL
    if z >= warn:
        return SEV_WARN
    if z >= watch:
        return SEV_WATCH
    return SEV_NORMAL


def _message(severity: str, max_abs_z: float, top_dim: int | None) -> str:
    where = f"dim {top_dim}" if top_dim is not None else "any dim"
    if severity == SEV_CRITICAL:
        return f"Critical anomaly at {where} (z={max_abs_z:.2f})"
    if severity == SEV_WARN:
        return f"Anomaly detected at {where} (z={max_abs_z:.2f})"
    if severity == SEV_WATCH:
        return f"Watch: elevated deviation at {where} (z={max_abs_z:.2f})"
    return "No anomaly"


def evaluate(
    vector: list[float],
    baseline: Baseline,
    options: Mapping[str, Any] | None = None,
) -> AnomalyResult:
    """Evaluate a single feature vector against a fitted Baseline."""
    if not vector:
        return AnomalyResult(
            is_anomaly=False, severity=SEV_NORMAL,
            max_abs_z=0.0, top_dim=None, top_dim_value=0.0,
            message="Empty vector", details={"reason": "empty"},
        )
    if len(vector) != baseline.dim:
        return AnomalyResult(
            is_anomaly=False, severity=SEV_NORMAL,
            max_abs_z=0.0, top_dim=None, top_dim_value=0.0,
            message="Dim mismatch", details={"reason": "dim_mismatch"},
        )
    if baseline.sample_count < 3:
        return AnomalyResult(
            is_anomaly=False, severity=SEV_NORMAL,
            max_abs_z=0.0, top_dim=None, top_dim_value=0.0,
            message="Baseline not ready",
            details={"reason": "not_ready", "n": baseline.sample_count},
        )

    watch = _opt_float(options, "anomaly_watch_z", DEFAULT_WATCH_Z)
    warn = _opt_float(options, "anomaly_warn_z", DEFAULT_WARN_Z)
    critical = _opt_float(options, "anomaly_critical_z", DEFAULT_CRITICAL_Z)
    z_threshold = _opt_float(options, "anomaly_z_threshold", DEFAULT_Z_THRESHOLD)

    mz = baseline.max_abs_z(vector)
    top = baseline.top_dim(vector)
    top_val = float(vector[top]) if top is not None else 0.0
    sev = classify_severity(mz, watch=watch, warn=warn, critical=critical)
    is_anom = mz > z_threshold and sev != SEV_NORMAL
    return AnomalyResult(
        is_anomaly=is_anom,
        severity=sev,
        max_abs_z=round(mz, 3),
        top_dim=top,
        top_dim_value=round(top_val, 3),
        message=_message(sev, mz, top),
        details={"z_threshold": z_threshold, "n": baseline.sample_count},
    )
