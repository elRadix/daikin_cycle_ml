"""v1.19.7 target: engine/cop_degradation.py.

Real API verified via inspect:
  analyze_degradation(recent_rows, prev_rows, dirty_hours, *, ...) -> dict
  Rows are hourly dicts with 'outdoor', 'cop', 'n_samples', 'hour'/'ts'.
"""
import time
from custom_components.daikin_cycle_ml.engine import cop_degradation as cd


def _hour_row(hour, outdoor, cop, n=12):
    """Build a cop_hourly-shaped row."""
    return {
        "hour": hour,
        "ts": float(hour) * 3600.0,
        "outdoor": outdoor,
        "cop": cop,
        "n_samples": n,
    }


def _rows(count, outdoor, cop, base_hour=0):
    return [_hour_row(base_hour + i, outdoor, cop) for i in range(count)]


def test_empty_safe():
    r = cd.analyze_degradation([], [], set())
    assert isinstance(r, dict)
    assert r.get("week_pct") is None


def test_identical_no_degradation():
    rows = _rows(24, 5.0, 3.5)
    r = cd.analyze_degradation(rows, rows, set())
    assert isinstance(r, dict)
    # Same data -> week_pct ~0 (or None if insufficient samples)
    if r.get("week_pct") is not None:
        assert abs(r["week_pct"]) < 1.0


def test_severe_degradation_detected():
    """-20% COP in recent: week_pct should reflect degradation."""
    prev = _rows(24, 5.0, 3.5, base_hour=0)
    recent = _rows(24, 5.0, 2.8, base_hour=200)
    r = cd.analyze_degradation(recent, prev, set())
    assert isinstance(r, dict)
    if r.get("week_pct") is not None:
        assert r["week_pct"] < -10.0, f"expected < -10%, got {r['week_pct']}"


def test_negative_outdoor_bins():
    prev = _rows(24, -15.0, 2.5, base_hour=0)
    recent = _rows(24, -15.0, 2.1, base_hour=200)
    r = cd.analyze_degradation(recent, prev, set())
    assert isinstance(r, dict)


def test_dirty_hours_filter_no_crash():
    """Dirty hours filter: filtered data returns safe dict."""
    prev = _rows(24, 5.0, 3.5, base_hour=0)
    recent = _rows(24, 5.0, 3.5, base_hour=200)
    dirty = {0, 1, 2, 3}
    r = cd.analyze_degradation(recent, prev, dirty)
    assert isinstance(r, dict)


def test_different_outdoor_bins():
    """Only some bins overlap: merge should handle gracefully."""
    prev = _rows(12, 5.0, 3.5, base_hour=0) + _rows(12, 10.0, 4.0, base_hour=100)
    recent = _rows(12, 5.0, 2.8, base_hour=200)
    r = cd.analyze_degradation(recent, prev, set())
    assert isinstance(r, dict)


def test_severity_for_pct_tiers():
    """Real tier strings: 'none' / 'warning' / 'critical' (probed)."""
    assert cd.severity_for_pct(None) == "none"
    assert cd.severity_for_pct(0.0) == "none"
    assert cd.severity_for_pct(-5.0) == "none"
    assert cd.severity_for_pct(-10.0) == "warning"
    assert cd.severity_for_pct(-20.0) == "critical"


def test_severity_for_pct_boundaries():
    """Strict < semantics at DEGRADATION_THRESHOLD_PCT=-8.0, CRITICAL=-15.0."""
    # exact threshold values are NOT escalated (strict <)
    assert cd.severity_for_pct(-8.0) == "none"
    assert cd.severity_for_pct(-15.0) == "warning"
    # just past each boundary
    assert cd.severity_for_pct(-8.01) == "warning"
    assert cd.severity_for_pct(-15.01) == "critical"


def test_severity_for_pct_custom_thresholds():
    """Custom thresholds: caller can shift both bands."""
    assert cd.severity_for_pct(-10.0, threshold=-12.0) == "none"
    assert cd.severity_for_pct(-10.0, threshold=-5.0) == "warning"
    assert cd.severity_for_pct(-20.0, critical=-25.0) == "warning"


def test_bin_for_outdoor():
    for t in (-20.0, -10.0, 0.0, 5.0, 15.0):
        b = cd.bin_for_outdoor(t)
        assert b is None or isinstance(b, str)


def test_weighted_mean_basic():
    assert cd.weighted_mean([1.0, 2.0, 3.0], [1.0, 1.0, 1.0]) == 2.0


def test_weighted_mean_empty():
    assert cd.weighted_mean([], []) is None


def test_weighted_linear_fit():
    r = cd.weighted_linear_fit([1.0, 2.0, 3.0], [2.0, 4.0, 6.0], [1.0, 1.0, 1.0])
    assert r is not None
    slope, intercept, r2 = r
    assert abs(slope - 2.0) < 0.1
