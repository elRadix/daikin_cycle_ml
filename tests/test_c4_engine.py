"""C4: cop_degradation engine helpers.

Marker: C4_ENGINE_TESTS_v1
"""
from __future__ import annotations

import pytest

from custom_components.daikin_cycle_ml.engine.cop_degradation import (
    SEVERITY_CRITICAL,
    SEVERITY_INFO,
    SEVERITY_NONE,
    SEVERITY_WARNING,
    aggregate_by_bin,
    bin_for_outdoor,
    build_dirty_hours,
    downgrade_for_lwt,
    filter_dirty_hours,
    merge_bins,
    severity_for_pct,
    weighted_linear_fit,
    weighted_mean,
)


# --- bin_for_outdoor ---

@pytest.mark.parametrize("t,expected", [
    (-30.0, None),
    (-25.0, "very_cold"),
    (-15.0, "very_cold"),
    (-10.0, "cold"),
    (-5.0, "cold"),
    (0.0, "cool"),
    (4.9, "cool"),
    (5.0, "mild"),
    (7.5, "mild"),
    (10.0, "warm"),
    (14.9, "warm"),
    (15.0, "hot"),
    (24.9, "hot"),
    (25.0, None),
    (30.0, None),
])
def test_bin_for_outdoor(t, expected):
    assert bin_for_outdoor(t) == expected


def test_bin_for_outdoor_none():
    assert bin_for_outdoor(None) is None


# --- weighted_mean ---

def test_weighted_mean_uniform():
    assert weighted_mean([1.0, 3.0], [1.0, 1.0]) == 2.0


def test_weighted_mean_skewed():
    assert weighted_mean([1.0, 3.0], [3.0, 1.0]) == 1.5


def test_weighted_mean_empty():
    assert weighted_mean([], []) is None


def test_weighted_mean_mismatch():
    assert weighted_mean([1.0], [1.0, 2.0]) is None


def test_weighted_mean_zero_weights():
    assert weighted_mean([1.0, 2.0], [0.0, 0.0]) is None


def test_weighted_mean_skips_neg_weight():
    assert weighted_mean([1.0, 5.0], [-1.0, 2.0]) == 5.0


# --- weighted_linear_fit ---

def test_fit_perfect_line():
    r = weighted_linear_fit([1.0, 2.0, 3.0], [1.0, 3.0, 5.0], [1.0, 1.0, 1.0])
    assert r is not None
    slope, intercept, r2 = r
    assert abs(slope - 2.0) < 1e-9
    assert abs(intercept + 1.0) < 1e-9
    assert abs(r2 - 1.0) < 1e-9


def test_fit_weighted_shifts_slope():
    # outlier at the END of x-range; weighting it shifts slope up
    xs = [1.0, 2.0, 3.0]
    ys = [1.0, 3.0, 10.0]  # x=3 is outlier above line
    r_uniform = weighted_linear_fit(xs, ys, [1.0, 1.0, 1.0])
    r_skewed = weighted_linear_fit(xs, ys, [1.0, 1.0, 10.0])
    assert r_uniform is not None and r_skewed is not None
    assert r_skewed[0] > r_uniform[0]


def test_fit_too_few():
    assert weighted_linear_fit([1.0], [1.0], [1.0]) is None


def test_fit_empty():
    assert weighted_linear_fit([], [], []) is None


def test_fit_mismatch():
    assert weighted_linear_fit([1.0, 2.0], [1.0], [1.0, 1.0]) is None


def test_fit_zero_x_variance():
    assert weighted_linear_fit([1.0, 1.0, 1.0], [1.0, 2.0, 3.0], [1.0, 1.0, 1.0]) is None


def test_fit_zero_weight():
    assert weighted_linear_fit([1.0, 2.0], [1.0, 2.0], [0.0, 0.0]) is None


# --- severity_for_pct ---

@pytest.mark.parametrize("pct,expected", [
    (None, SEVERITY_NONE),
    (5.0, SEVERITY_NONE),
    (0.0, SEVERITY_NONE),
    (-7.99, SEVERITY_NONE),
    (-8.0, SEVERITY_NONE),
    (-8.01, SEVERITY_WARNING),
    (-10.0, SEVERITY_WARNING),
    (-14.99, SEVERITY_WARNING),
    (-15.0, SEVERITY_WARNING),
    (-15.01, SEVERITY_CRITICAL),
    (-25.0, SEVERITY_CRITICAL),
])
def test_severity_for_pct(pct, expected):
    assert severity_for_pct(pct) == expected


# --- downgrade_for_lwt ---

def test_downgrade_critical_to_warning():
    sev, dg = downgrade_for_lwt(SEVERITY_CRITICAL, True)
    assert sev == SEVERITY_WARNING and dg is True


def test_downgrade_warning_to_info():
    sev, dg = downgrade_for_lwt(SEVERITY_WARNING, True)
    assert sev == SEVERITY_INFO and dg is True


def test_downgrade_none_unchanged():
    sev, dg = downgrade_for_lwt(SEVERITY_NONE, True)
    assert sev == SEVERITY_NONE and dg is False


def test_downgrade_info_unchanged():
    sev, dg = downgrade_for_lwt(SEVERITY_INFO, True)
    assert sev == SEVERITY_INFO and dg is False


def test_no_downgrade_without_shift():
    sev, dg = downgrade_for_lwt(SEVERITY_CRITICAL, False)
    assert sev == SEVERITY_CRITICAL and dg is False


# --- build_dirty_hours ---

def test_dirty_basic():
    cycles = [
        {"start_ts": 3600 * 100, "end_ts": 3600 * 100 + 1800,
         "buh_used": 1, "defrost_used": 0},
        {"start_ts": 3600 * 200, "end_ts": None, "duration_s": 7200,
         "buh_used": 0, "defrost_used": 1},
        {"start_ts": 3600 * 300, "end_ts": 3600 * 300 + 600,
         "buh_used": 0, "defrost_used": 0},
    ]
    d = build_dirty_hours(cycles)
    assert 100 in d
    assert 200 in d and 201 in d and 202 in d
    assert 300 not in d
    assert len(d) == 4


def test_dirty_end_falls_back_to_start():
    cycles = [{"start_ts": 3600 * 50, "end_ts": None, "duration_s": None,
               "buh_used": 1, "defrost_used": 0}]
    assert build_dirty_hours(cycles) == {50}


def test_dirty_no_start():
    cycles = [{"start_ts": None, "end_ts": 1234,
               "buh_used": 1, "defrost_used": 0}]
    assert build_dirty_hours(cycles) == set()


def test_dirty_end_before_start():
    cycles = [{"start_ts": 3600 * 300, "end_ts": 3600 * 299,
               "buh_used": 1, "defrost_used": 0}]
    d = build_dirty_hours(cycles)
    assert 299 in d and 300 in d


def test_dirty_empty():
    assert build_dirty_hours([]) == set()


# --- filter_dirty_hours ---

def test_filter_dirty_basic():
    rows = [{"ts_hour": 100}, {"ts_hour": 200}, {"ts_hour": 999}]
    assert [r["ts_hour"] for r in filter_dirty_hours(rows, {100, 200})] == [999]


def test_filter_dirty_empty_set():
    rows = [{"ts_hour": 1}]
    assert filter_dirty_hours(rows, set()) == rows


# --- aggregate_by_bin ---

def test_aggregate_basic():
    rows = [
        {"outdoor_mean": 7.0, "cop_mean": 3.0, "n_samples": 10, "lwt_mean": 35.0},
        {"outdoor_mean": 8.0, "cop_mean": 4.0, "n_samples": 30, "lwt_mean": 36.0},
        {"outdoor_mean": 12.0, "cop_mean": 4.5, "n_samples": 5, "lwt_mean": 33.0},
    ]
    a = aggregate_by_bin(rows)
    assert a["mild"]["hours"] == 2
    assert abs(a["mild"]["cop_mean"] - (3.0 * 10 + 4.0 * 30) / 40) < 1e-9
    assert a["warm"]["cop_mean"] == 4.5


def test_aggregate_skips_null_outdoor():
    rows = [{"outdoor_mean": None, "cop_mean": 3.0, "n_samples": 5}]
    assert aggregate_by_bin(rows) == {}


def test_aggregate_skips_null_cop():
    rows = [{"outdoor_mean": 7.0, "cop_mean": None, "n_samples": 5}]
    assert aggregate_by_bin(rows) == {}


def test_aggregate_skips_zero_samples():
    rows = [{"outdoor_mean": 7.0, "cop_mean": 3.0, "n_samples": 0}]
    assert aggregate_by_bin(rows) == {}


def test_aggregate_skips_out_of_range():
    rows = [{"outdoor_mean": -30.0, "cop_mean": 3.0, "n_samples": 5}]
    assert aggregate_by_bin(rows) == {}


def test_aggregate_lwt_none():
    rows = [{"outdoor_mean": 7.0, "cop_mean": 3.0,
             "n_samples": 5, "lwt_mean": None}]
    a = aggregate_by_bin(rows)
    assert a["mild"]["lwt_mean"] is None


# --- merge_bins ---

def test_merge_basic():
    r = {"mild": {"hours": 10, "cop_mean": 3.2, "n_samples": 50, "lwt_mean": 35.0}}
    p = {"mild": {"hours": 8, "cop_mean": 3.6, "n_samples": 40, "lwt_mean": 34.0}}
    m = merge_bins(r, p, min_hours=6)
    assert len(m) == 1
    assert m[0]["range"] == "mild"
    assert abs(m[0]["ratio"] - 3.2 / 3.6) < 1e-9
    assert m[0]["weight"] == 8


def test_merge_below_min_hours():
    r = {"mild": {"hours": 2, "cop_mean": 3.0, "n_samples": 5, "lwt_mean": 35.0}}
    p = {"mild": {"hours": 8, "cop_mean": 3.6, "n_samples": 40, "lwt_mean": 34.0}}
    assert merge_bins(r, p, min_hours=6) == []


def test_merge_bin_missing_in_one_side():
    r = {"mild": {"hours": 10, "cop_mean": 3.0, "n_samples": 50, "lwt_mean": 35.0}}
    p = {"cold": {"hours": 8, "cop_mean": 3.6, "n_samples": 40, "lwt_mean": 34.0}}
    assert merge_bins(r, p, min_hours=6) == []


def test_merge_skips_zero_prev_cop():
    r = {"mild": {"hours": 10, "cop_mean": 3.0, "n_samples": 50, "lwt_mean": 35.0}}
    p = {"mild": {"hours": 8, "cop_mean": 0.0, "n_samples": 40, "lwt_mean": 34.0}}
    assert merge_bins(r, p, min_hours=6) == []


def test_merge_order():
    r = {
        "warm": {"hours": 10, "cop_mean": 4.0, "n_samples": 50, "lwt_mean": 30.0},
        "cold": {"hours": 10, "cop_mean": 2.5, "n_samples": 50, "lwt_mean": 40.0},
    }
    p = {
        "warm": {"hours": 10, "cop_mean": 4.2, "n_samples": 50, "lwt_mean": 30.0},
        "cold": {"hours": 10, "cop_mean": 2.8, "n_samples": 50, "lwt_mean": 40.0},
    }
    m = merge_bins(r, p, min_hours=6)
    assert [b["range"] for b in m] == ["cold", "warm"]


def test_dirty_invalid_start_ts():
    cycles = [{"start_ts": "abc", "end_ts": 3600,
               "buh_used": 1, "defrost_used": 0}]
    assert build_dirty_hours(cycles) == set()


def test_dirty_invalid_end_ts():
    cycles = [{"start_ts": 3600, "end_ts": "xyz",
               "buh_used": 1, "defrost_used": 0}]
    assert build_dirty_hours(cycles) == set()
