"""Boundary gap tests from mutation audit v44.0.

Each test targets a specific `< vs <=`, `== 0`, `== threshold`, or
edge-input case discovered during hand-rolled mutation testing. All
tests validate existing correct behaviour.
"""
from __future__ import annotations

import math


from custom_components.daikin_cycle_ml.engine.quality_scorer import (
    score_cycle,
    DEFAULT_GOOD_RUN_MIN,
    DEFAULT_GOOD_DT_K,
    DEFAULT_GOOD_OFF_MIN,
    PENALTY_SHORT_RUN,
)
from custom_components.daikin_cycle_ml.engine.thermal import (
    safe_float,
    dt_from_attrs,
    compute_thermal_power_live,
)
from custom_components.daikin_cycle_ml.ml.features import is_valid_record
from custom_components.daikin_cycle_ml.engine.cop_analyzer import (
    bucket_for_outdoor,
    _parse_float,
)
from custom_components.daikin_cycle_ml.engine.anomaly_engine import (
    classify_severity,
)
from custom_components.daikin_cycle_ml.engine.cycle_detector import (
    detect_compressor_on,
    _is_on,
)
from custom_components.daikin_cycle_ml.ml.adaptive_thresholds import (
    _percentile,
)
from custom_components.daikin_cycle_ml.ml.baseline import (
    Baseline,
    AdaptiveBaseline,
)
from custom_components.daikin_cycle_ml.const import (
    ATTR_LEAVING_WATER_AFTER_BUH,
    ATTR_INLET_WATER_R4T,
    ATTR_INV_FREQUENCY_RPS,
    ATTR_BUH_STEP1,
    ATTR_BUH_STEP2,
)


# ── quality_scorer boundaries ────────────────────────────────────────

def test_quality_duration_exactly_at_threshold():
    """duration == good_run_min*60 → NO penalty (uses <)."""
    exact = DEFAULT_GOOD_RUN_MIN * 60
    assert score_cycle({"duration_s": exact}) == 100
    assert score_cycle({"duration_s": exact - 1}) == 100 - PENALTY_SHORT_RUN


def test_quality_dt_exactly_at_threshold():
    """dT_max == good_dt_k → NO penalty (uses <)."""
    assert score_cycle({"dT_max": DEFAULT_GOOD_DT_K}) == 100
    assert score_cycle({"dT_max": DEFAULT_GOOD_DT_K - 0.01}) < 100


def test_quality_off_time_exactly_at_threshold():
    """off_time_s == good_off_min*60 → NO penalty (uses <)."""
    exact = DEFAULT_GOOD_OFF_MIN * 60
    assert score_cycle({}, None, off_time_s=exact) == 100
    assert score_cycle({}, None, off_time_s=exact - 1) < 100


# ── thermal boundaries ───────────────────────────────────────────────

def test_thermal_safe_float_rejects_bool():
    """bool is not a valid float for sensor inputs."""
    assert safe_float(True) is None
    assert safe_float(False) is None


def test_thermal_dt_uses_abs():
    """dt is magnitude, not signed — leaving < inlet is valid."""
    attrs = {
        ATTR_LEAVING_WATER_AFTER_BUH: 30.0,
        ATTR_INLET_WATER_R4T: 35.0,
    }
    assert dt_from_attrs(attrs) == 5.0


def test_thermal_dt_rounds_to_2_decimals():
    """dt is rounded to 2 decimals, not 3 or more."""
    attrs = {
        ATTR_LEAVING_WATER_AFTER_BUH: 35.12345,
        ATTR_INLET_WATER_R4T: 30.0,
    }
    assert dt_from_attrs(attrs) == 5.12


def test_thermal_power_zero_is_idle():
    """power_w == 0 or cop == 0 → not the power_cop branch."""
    kw, src = compute_thermal_power_live(
        power_w=0.0, cop=2.5, flow_lmin=None, dt_k=None, rps=None,
    )
    assert kw is None
    assert src == "idle"
    kw, src = compute_thermal_power_live(
        power_w=1000.0, cop=0.0, flow_lmin=None, dt_k=None, rps=None,
    )
    assert kw is None
    assert src == "idle"


# ── ml/features boundaries ───────────────────────────────────────────

def test_features_valid_record_empty_dict():
    """Empty dict → not a valid record."""
    assert is_valid_record({}) is False


# ── cop_analyzer boundaries ──────────────────────────────────────────

def test_bucket_at_minus_10_boundary():
    """temp in [-10, -8) → bucket -10--8 (not -10-)."""
    assert bucket_for_outdoor(-10.0) == "-10--8"
    assert bucket_for_outdoor(-10.5) == "-10-"


def test_parse_float_filters_all_null_variants():
    """all three markers → None."""
    assert _parse_float("Invalid") is None
    assert _parse_float("unknown") is None
    assert _parse_float("UNAVAILABLE") is None


# ── anomaly_engine boundaries ────────────────────────────────────────

def test_severity_watch_boundary_uses_ge():
    """z == watch → WATCH (uses >=)."""
    assert classify_severity(2.0, watch=2.0, warn=3.0, critical=4.5) == "watch"
    assert classify_severity(1.99, watch=2.0, warn=3.0, critical=4.5) == "normal"


# ── cycle_detector boundaries ────────────────────────────────────────

def test_compressor_rps_exactly_at_threshold_off():
    """rps == threshold → OFF (uses >)."""
    assert detect_compressor_on(
        {ATTR_INV_FREQUENCY_RPS: 3.0},
        {"compressor_rps_threshold": 3.0},
    ) is False
    assert detect_compressor_on(
        {ATTR_INV_FREQUENCY_RPS: 3.01},
        {"compressor_rps_threshold": 3.0},
    ) is True


def test_is_on_requires_literal_true():
    """_is_on uses identity — 1, 'on', truthy are NOT True."""
    assert _is_on({ATTR_BUH_STEP1: True}, ATTR_BUH_STEP1) is True
    assert _is_on({ATTR_BUH_STEP1: 1}, ATTR_BUH_STEP1) is False
    assert _is_on({ATTR_BUH_STEP1: "on"}, ATTR_BUH_STEP1) is False
    assert _is_on({}, ATTR_BUH_STEP2) is False


# ── adaptive_thresholds boundaries ───────────────────────────────────

def test_percentile_pct_zero_returns_min():
    """pct == 0 → min (uses <=)."""
    assert _percentile([5.0, 1.0, 3.0, 2.0, 4.0], 0.0) == 1.0


def test_percentile_pct_100_returns_max():
    """pct == 100 → max (uses >=)."""
    assert _percentile([5.0, 1.0, 3.0, 2.0, 4.0], 100.0) == 5.0


# ── baseline boundaries ──────────────────────────────────────────────

def test_welford_std_uses_sample_variance():
    """Welford std uses n-1 (sample), not n (population)."""
    b = Baseline(1).fit([[1.0], [2.0], [3.0]])
    # Sample std of [1,2,3] = 1.0; population std = sqrt(2/3) ≈ 0.816
    assert math.isclose(b.std[0], 1.0, abs_tol=1e-9)


def test_adaptive_baseline_std_ewma_formula():
    """EWMA std = sqrt(m2); alpha=1.0 degenerates to zero variance.

    With alpha=0.5, after [3.0] then [5.0]:
      mean = 0.5*3 + 0.5*5 = 4.0
      m2   = 0.5 * (0 + 0.5*(5-3)^2) = 1.0
      std  = sqrt(1.0) = 1.0
    """
    b = AdaptiveBaseline(1, alpha=0.5)
    b.update([3.0])
    b.update([5.0])
    assert math.isclose(b.std[0], 1.0, abs_tol=1e-9)


def test_adaptive_baseline_alpha_one_degenerates_to_zero_variance():
    """alpha=1.0 → m2 always multiplied by (1-alpha)=0 → std=0."""
    b = AdaptiveBaseline(1, alpha=1.0)
    b.update([3.0])
    b.update([5.0])
    b.update([7.0])
    assert b.std[0] == 0.0


def test_baseline_is_anomaly_uses_strict_gt():
    """max_abs_z == threshold → NOT anomaly (uses >)."""
    b = Baseline(1).fit([[1.0], [2.0], [3.0], [4.0], [5.0]])
    # z-score of mean = 0; threshold 0 → not > 0 → False
    assert b.is_anomaly([3.0], threshold=0.0) is False
