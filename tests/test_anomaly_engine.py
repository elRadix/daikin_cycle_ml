"""Tests for engine.anomaly_engine (Batch 7b)."""
from __future__ import annotations

from custom_components.daikin_cycle_ml.engine.anomaly_engine import (
    DEFAULT_CRITICAL_Z,
    DEFAULT_WARN_Z,
    DEFAULT_WATCH_Z,
    SEV_CRITICAL,
    SEV_NORMAL,
    SEV_WARN,
    SEV_WATCH,
    AnomalyResult,
    classify_severity,
    evaluate,
)
from custom_components.daikin_cycle_ml.ml.baseline import Baseline


def _fitted(dim=2, n=10):
    b = Baseline(dim)
    for i in range(n):
        b.update([float(i)] * dim)
    return b


def test_classify_normal():
    assert classify_severity(0.5) == SEV_NORMAL


def test_classify_watch():
    assert classify_severity(DEFAULT_WATCH_Z) == SEV_WATCH


def test_classify_warn():
    assert classify_severity(DEFAULT_WARN_Z) == SEV_WARN


def test_classify_critical():
    assert classify_severity(DEFAULT_CRITICAL_Z) == SEV_CRITICAL


def test_classify_abs_applied():
    assert classify_severity(-DEFAULT_WARN_Z) == SEV_WARN


def test_evaluate_returns_anomaly_result():
    r = evaluate([4.5, 4.5], _fitted())
    assert isinstance(r, AnomalyResult)


def test_evaluate_empty_vector():
    r = evaluate([], _fitted())
    assert r.is_anomaly is False
    assert r.severity == SEV_NORMAL
    assert r.details.get("reason") == "empty"


def test_evaluate_dim_mismatch():
    b = _fitted(dim=2)
    r = evaluate([1.0, 2.0, 3.0], b)
    assert r.is_anomaly is False
    assert r.details.get("reason") == "dim_mismatch"


def test_evaluate_not_ready_when_few_samples():
    b = Baseline(2)
    b.update([1.0, 1.0])
    b.update([2.0, 2.0])
    r = evaluate([1.0, 1.0], b)
    assert r.details.get("reason") == "not_ready"
    assert r.is_anomaly is False


def test_evaluate_at_mean_not_anomaly():
    b = _fitted(dim=1, n=10)
    r = evaluate([4.5], b)
    assert r.is_anomaly is False
    assert r.severity in (SEV_NORMAL, SEV_WATCH)


def test_evaluate_far_outlier_critical():
    b = _fitted(dim=1, n=20)
    r = evaluate([1000.0], b)
    assert r.is_anomaly is True
    assert r.severity == SEV_CRITICAL


def test_evaluate_top_dim_points_to_outlier():
    b = Baseline(3)
    for i in range(10):
        b.update([float(i), float(i), float(i)])
    r = evaluate([4.5, 1000.0, 4.5], b)
    assert r.top_dim == 1
    assert r.is_anomaly is True


def test_evaluate_custom_thresholds_allow():
    b = _fitted(dim=1, n=20)
    r = evaluate([1000.0], b, options={"anomaly_critical_z": 1e9})
    assert r.severity != SEV_CRITICAL


def test_evaluate_message_non_empty():
    r = evaluate([4.5, 4.5], _fitted())
    assert isinstance(r.message, str) and r.message


def test_evaluate_max_abs_z_rounded():
    b = _fitted(dim=1, n=20)
    r = evaluate([100.0], b)
    # rounding to 3 decimals
    assert r.max_abs_z == round(r.max_abs_z, 3)


def test_evaluate_details_include_n():
    b = _fitted(dim=1, n=10)
    r = evaluate([4.5], b)
    assert r.details.get("n") == 10


def test_evaluate_details_include_z_threshold():
    b = _fitted(dim=1, n=10)
    r = evaluate([4.5], b, options={"anomaly_z_threshold": 2.5})
    assert r.details.get("z_threshold") == 2.5
