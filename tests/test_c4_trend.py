"""C4: analyze_trend tests (regression COP ~ T_outdoor).

Marker: C4_TREND_TESTS_v1
"""
from __future__ import annotations

from custom_components.daikin_cycle_ml.engine.cop_degradation import (
    SEVERITY_CRITICAL,
    SEVERITY_NONE,
    SEVERITY_WARNING,
    analyze_trend,
)


def _linear_baseline() -> list[dict]:
    """Perfect linear: COP = 4.5 - 0.1 * T_outdoor."""
    return [
        {"ts_hour": 24 * (i % 20) + i,
         "outdoor_mean": float(i),
         "cop_mean": 4.5 - 0.1 * float(i),
         "n_samples": 20, "lwt_mean": 35.0}
        for i in range(20)
    ]


def _recent_factor(factor: float, n: int = 10) -> list[dict]:
    """Recent rows scaled by factor vs perfect baseline prediction."""
    return [
        {"ts_hour": 24 * (20 + i),
         "outdoor_mean": float(5 + i % 10),
         "cop_mean": (4.5 - 0.1 * float(5 + i % 10)) * factor,
         "n_samples": 30, "lwt_mean": 35.0}
        for i in range(n)
    ]


# --- happy paths ---

def test_perfect_fit_zero_trend():
    r = analyze_trend(_linear_baseline(), _recent_factor(1.0), set())
    assert r["valid"] is True
    assert abs(r["trend_30d"]) < 0.01
    assert abs(r["fit_slope"] + 0.1) < 1e-9
    assert abs(r["fit_intercept"] - 4.5) < 1e-9
    assert r["fit_r2"] > 0.999


def test_degraded_warning():
    r = analyze_trend(_linear_baseline(), _recent_factor(0.9), set())
    assert r["valid"] is True
    assert abs(r["trend_30d"] + 10.0) < 0.5
    assert r["severity"] == SEVERITY_WARNING


def test_degraded_critical():
    r = analyze_trend(_linear_baseline(), _recent_factor(0.8), set())
    assert r["valid"] is True
    assert abs(r["trend_30d"] + 20.0) < 0.5
    assert r["severity"] == SEVERITY_CRITICAL


def test_better_than_expected_positive():
    r = analyze_trend(_linear_baseline(), _recent_factor(1.1), set())
    assert r["valid"] is True
    assert r["trend_30d"] > 5.0
    assert r["severity"] == SEVERITY_NONE


# --- invalid / degenerate ---

def test_insufficient_hours():
    thin = _linear_baseline()[:5]
    r = analyze_trend(thin, _recent_factor(1.0), set())
    assert r["valid"] is False
    assert r["trend_30d"] is None
    assert r["fit_slope"] is None
    assert r["n_hours_baseline"] == 5


def test_insufficient_spread():
    narrow = [
        {"ts_hour": 24 * i, "outdoor_mean": 7.0 + 0.1 * i,
         "cop_mean": 4.0, "n_samples": 20, "lwt_mean": 35.0}
        for i in range(20)
    ]
    r = analyze_trend(narrow, _recent_factor(1.0), set())
    assert r["valid"] is False
    assert r["outdoor_spread_baseline_c"] < 5.0


def test_empty_baseline():
    r = analyze_trend([], _recent_factor(1.0), set())
    assert r["valid"] is False
    assert r["trend_30d"] is None
    assert r["n_hours_baseline"] == 0


def test_empty_recent():
    r = analyze_trend(_linear_baseline(), [], set())
    assert r["valid"] is False
    assert r["trend_30d"] is None


def test_baseline_null_outdoor_skipped():
    base = _linear_baseline()
    base[0]["outdoor_mean"] = None
    r = analyze_trend(base, _recent_factor(1.0), set())
    assert r["n_hours_baseline"] == 19


def test_baseline_null_cop_skipped():
    base = _linear_baseline()
    base[0]["cop_mean"] = None
    r = analyze_trend(base, _recent_factor(1.0), set())
    assert r["n_hours_baseline"] == 19


def test_baseline_zero_samples_skipped():
    base = _linear_baseline()
    base[0]["n_samples"] = 0
    r = analyze_trend(base, _recent_factor(1.0), set())
    assert r["n_hours_baseline"] == 19


def test_dirty_hours_filtered_from_baseline():
    base = _linear_baseline()
    dirty = {base[0]["ts_hour"]}
    r = analyze_trend(base, _recent_factor(1.0), dirty)
    assert r["n_hours_baseline"] == 19


# --- attrs presence ---

def test_all_attrs_present():
    r = analyze_trend(_linear_baseline(), _recent_factor(1.0), set())
    for k in (
        "mode", "window_days", "baseline_days", "recent_days",
        "trend_30d", "trend_30d_raw", "severity",
        "threshold_pct", "critical_pct",
        "n_hours_baseline", "n_hours_recent",
        "outdoor_spread_baseline_c",
        "fit_slope", "fit_intercept", "fit_r2",
        "cop_predicted_recent", "cop_observed_recent",
        "valid", "updated_ts",
    ):
        assert k in r, k


def test_now_timestamp():
    r = analyze_trend([], [], set(), now=9999.0)
    assert r["updated_ts"] == 9999.0


def test_now_timestamp_none():
    r = analyze_trend([], [], set())
    assert r["updated_ts"] is None


def test_predicted_recent_below_observed_when_degraded():
    r = analyze_trend(_linear_baseline(), _recent_factor(0.85), set())
    assert r["valid"] is True
    assert r["cop_predicted_recent"] is not None
    assert r["cop_observed_recent"] is not None
    assert r["cop_observed_recent"] < r["cop_predicted_recent"]


def test_trend_recent_all_invalid():
    baseline = _linear_baseline()
    recent = [
        {"ts_hour": 24 * (20 + i), "outdoor_mean": None,
         "cop_mean": 3.0, "n_samples": 30, "lwt_mean": 35.0}
        for i in range(10)
    ]
    r = analyze_trend(baseline, recent, set())
    assert r["valid"] is False
    assert r["cop_predicted_recent"] is None


def test_trend_predicted_nonpositive():
    # steep baseline COP = 10 - 2*T over 0..5C -> pred at 6 = -2
    baseline = [
        {"ts_hour": 24 * i, "outdoor_mean": float(i // 3),
         "cop_mean": 10.0 - 2.0 * float(i // 3),
         "n_samples": 20, "lwt_mean": 35.0}
        for i in range(18)
    ]
    recent = [
        {"ts_hour": 24 * (20 + i), "outdoor_mean": 6.0,
         "cop_mean": 1.0, "n_samples": 30, "lwt_mean": 35.0}
        for i in range(10)
    ]
    r = analyze_trend(baseline, recent, set())
    assert r["valid"] is False
    assert r["trend_30d"] is None
    assert r["cop_predicted_recent"] is not None
    assert r["cop_predicted_recent"] <= 0.0
