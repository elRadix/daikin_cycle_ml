"""C4: analyze_degradation tests.

Marker: C4_DEGRADATION_TESTS_v1
"""
from __future__ import annotations

from custom_components.daikin_cycle_ml.engine.cop_degradation import (
    SEVERITY_CRITICAL,
    SEVERITY_INFO,
    SEVERITY_NONE,
    SEVERITY_WARNING,
    analyze_degradation,
)


def _rows(
    base_day: int, n_days: int, cop: float, outdoor: float = 7.0,
    n_samples: int = 50, lwt: float = 35.0,
) -> list[dict]:
    """Generate hourly rows spread over n_days distinct UTC days."""
    return [
        {"ts_hour": 24 * (base_day + i) + 10,
         "outdoor_mean": outdoor, "cop_mean": cop,
         "n_samples": n_samples, "lwt_mean": lwt}
        for i in range(n_days)
    ]


# --- happy paths ---

def test_valid_1bin_critical():
    recent = _rows(20, 8, 3.0)
    prev = _rows(10, 8, 3.6)
    r = analyze_degradation(recent, prev, set())
    assert r["valid"] is True
    assert r["n_bins_used"] == 1
    assert r["dynamic_min_samples"] == 200
    assert r["n_samples_recent"] == 400
    assert r["n_days_recent"] == 8
    expected = (3.0 / 3.6 - 1.0) * 100.0
    assert abs(r["week_pct"] - expected) < 1e-9
    assert r["severity_raw"] == SEVERITY_CRITICAL
    assert r["severity"] == SEVERITY_CRITICAL
    assert r["severity_downgraded"] is False


def test_valid_2bins_warning():
    # both bins -10% so weighted mean stays below -8 threshold
    recent = _rows(20, 8, 3.24, outdoor=7.0) + _rows(20, 8, 2.7, outdoor=12.0)
    prev = _rows(10, 8, 3.6, outdoor=7.0) + _rows(10, 8, 3.0, outdoor=12.0)
    r = analyze_degradation(recent, prev, set())
    assert r["valid"] is True
    assert r["n_bins_used"] == 2
    assert r["dynamic_min_samples"] == 100
    assert abs(r["week_pct"] - (-10.0)) < 1e-9
    assert r["severity_raw"] == SEVERITY_WARNING
    assert r["severity"] == SEVERITY_WARNING


def test_valid_3bins_neutral():
    recent = (
        _rows(20, 8, 3.6, outdoor=2.0)
        + _rows(20, 8, 3.5, outdoor=7.0)
        + _rows(20, 8, 3.3, outdoor=12.0)
    )
    prev = (
        _rows(10, 8, 3.6, outdoor=2.0)
        + _rows(10, 8, 3.5, outdoor=7.0)
        + _rows(10, 8, 3.3, outdoor=12.0)
    )
    r = analyze_degradation(recent, prev, set())
    assert r["valid"] is True
    assert r["n_bins_used"] == 3
    assert r["dynamic_min_samples"] == 80
    assert abs(r["week_pct"]) < 1e-9
    assert r["severity"] == SEVERITY_NONE


# --- invalid paths ---

def test_invalid_no_bins():
    r = analyze_degradation([], [], set())
    assert r["valid"] is False
    assert r["week_pct"] is None
    assert r["week_pct_raw"] is None
    assert r["n_bins_used"] == 0
    assert r["severity"] == SEVERITY_NONE


def test_invalid_only_recent():
    recent = _rows(20, 8, 3.0)
    r = analyze_degradation(recent, [], set())
    assert r["valid"] is False
    assert r["week_pct"] is None


def test_invalid_samples_below_dynamic_floor():
    recent = _rows(20, 8, 3.0, n_samples=5)
    prev = _rows(10, 8, 3.6, n_samples=5)
    r = analyze_degradation(recent, prev, set())
    assert r["valid"] is False
    assert r["week_pct_raw"] is not None
    assert r["n_samples_recent"] == 40


def test_invalid_too_few_days():
    # all hours within 1 UTC day
    recent = [
        {"ts_hour": 24 * 20 + h, "outdoor_mean": 7.0, "cop_mean": 3.0,
         "n_samples": 100, "lwt_mean": 35.0}
        for h in range(8)
    ]
    prev = _rows(10, 8, 3.6)
    r = analyze_degradation(recent, prev, set())
    assert r["valid"] is False
    assert r["n_days_recent"] == 1


# --- exclusion skew ---

def test_skew_below_threshold_still_valid():
    recent = _rows(20, 8, 3.0)
    prev = _rows(10, 8, 3.6)
    dirty = {24 * 10 + 10}  # kills 1 of 8 prev hours
    r = analyze_degradation(recent, prev, dirty)
    assert r["excluded_hours_prev"] == 1
    assert r["excluded_hours_recent"] == 0
    assert abs(r["exclusion_skew"] - 0.125) < 1e-9
    assert r["valid"] is True


def test_skew_above_threshold_invalid():
    recent = _rows(20, 8, 3.0)
    prev = _rows(10, 8, 3.6)
    dirty = {24 * 10 + 10, 24 * 11 + 10, 24 * 12 + 10}
    r = analyze_degradation(recent, prev, dirty)
    assert r["excluded_hours_prev"] == 3
    assert r["exclusion_skew"] >= 0.15
    assert r["valid"] is False


# --- LWT shift / Optie C ---

def test_lwt_shift_critical_downgraded_to_warning():
    recent = _rows(20, 8, 3.0, lwt=35.0)
    prev = _rows(10, 8, 3.6, lwt=29.0)
    r = analyze_degradation(recent, prev, set())
    assert r["lwt_shift_detected"] is True
    assert r["severity_raw"] == SEVERITY_CRITICAL
    assert r["severity"] == SEVERITY_WARNING
    assert r["severity_downgraded"] is True


def test_lwt_shift_warning_downgraded_to_info():
    recent = _rows(20, 8, 3.3, lwt=35.0)
    prev = _rows(10, 8, 3.6, lwt=29.0)
    r = analyze_degradation(recent, prev, set())
    assert r["lwt_shift_detected"] is True
    assert r["severity_raw"] == SEVERITY_WARNING
    assert r["severity"] == SEVERITY_INFO
    assert r["severity_downgraded"] is True


def test_lwt_shift_exactly_at_threshold_no_downgrade():
    recent = _rows(20, 8, 3.0, lwt=35.0)
    prev = _rows(10, 8, 3.6, lwt=30.0)
    r = analyze_degradation(recent, prev, set())
    # |35-30| = 5.0, threshold is "> 5.0" strictly -> no shift
    assert r["lwt_shift_detected"] is False
    assert r["severity"] == SEVERITY_CRITICAL


def test_no_lwt_shift_no_downgrade():
    recent = _rows(20, 8, 3.0, lwt=35.0)
    prev = _rows(10, 8, 3.6, lwt=34.0)
    r = analyze_degradation(recent, prev, set())
    assert r["lwt_shift_detected"] is False
    assert r["severity"] == SEVERITY_CRITICAL
    assert r["severity_downgraded"] is False


# --- attr presence ---

def test_all_attrs_present():
    recent = _rows(20, 8, 3.0)
    prev = _rows(10, 8, 3.6)
    r = analyze_degradation(recent, prev, set())
    for k in (
        "mode", "window_days", "week_pct", "week_pct_raw",
        "severity", "severity_raw", "severity_downgraded",
        "threshold_pct", "critical_pct",
        "n_samples_recent", "n_samples_prev",
        "n_days_recent", "n_days_prev",
        "n_bins_used", "dynamic_min_samples", "bins_used",
        "excluded_hours_recent", "excluded_hours_prev", "exclusion_skew",
        "lwt_mean_recent", "lwt_mean_prev",
        "lwt_shift_detected", "lwt_shift_c",
        "valid", "updated_ts",
    ):
        assert k in r, k


def test_bins_used_detail_structure():
    recent = _rows(20, 8, 3.3)
    prev = _rows(10, 8, 3.6)
    r = analyze_degradation(recent, prev, set())
    assert len(r["bins_used"]) == 1
    b = r["bins_used"][0]
    for k in ("range", "hours_recent", "hours_prev",
              "cop_recent", "cop_prev", "ratio", "weight"):
        assert k in b, k


def test_now_timestamp_present():
    r = analyze_degradation([], [], set(), now=12345.0)
    assert r["updated_ts"] == 12345.0


def test_now_timestamp_none():
    r = analyze_degradation([], [], set())
    assert r["updated_ts"] is None


def test_lwt_all_none():
    recent = _rows(20, 8, 3.0, lwt=None)
    prev = _rows(10, 8, 3.6, lwt=None)
    r = analyze_degradation(recent, prev, set())
    assert r["lwt_mean_recent"] is None
    assert r["lwt_mean_prev"] is None
    assert r["lwt_shift_detected"] is False
