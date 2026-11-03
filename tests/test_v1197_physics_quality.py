"""v1.19.7 target: physics.get_physical_cop_ceiling + quality_scorer.score_cycle.

Real API verified via inspect:
  get_physical_cop_ceiling(mode: str, lwt: float, outdoor: float) -> float | None
  score_cycle(record, options=None, *, off_time_s=None, short_cycle_ratio=None) -> int

Note: score_cycle penalizes BUH but NOT defrost. Defrost is normal
operation; BUH is COP=1 inefficient backup. The defrost test below
documents this deliberately (was a false-positive in prior version).
"""
import math
import pytest
from custom_components.daikin_cycle_ml.engine import physics as ph
from custom_components.daikin_cycle_ml.engine import quality_scorer as qs


# ---- Physics ----

def test_ceiling_heating_typical():
    c = ph.get_physical_cop_ceiling("heating", 35.0, 5.0)
    assert isinstance(c, float)
    assert 0 < c < 20


def test_ceiling_dhw_typical():
    c = ph.get_physical_cop_ceiling("dhw", 55.0, 5.0)
    assert isinstance(c, float)
    assert c > 0


def test_ceiling_cooling_returns_none():
    """Cooling mode not supported for Carnot ceiling -> None."""
    assert ph.get_physical_cop_ceiling("cooling", 12.0, 35.0) is None


def test_ceiling_unknown_mode_returns_none():
    assert ph.get_physical_cop_ceiling("defrost", 35.0, 5.0) is None


def test_ceiling_lwt_equal_outdoor_returns_none():
    """No thermal lift -> None."""
    assert ph.get_physical_cop_ceiling("heating", 5.0, 5.0) is None


def test_ceiling_lwt_below_outdoor_returns_none():
    assert ph.get_physical_cop_ceiling("heating", 0.0, 5.0) is None


def test_ceiling_deep_cold_finite():
    c = ph.get_physical_cop_ceiling("heating", 45.0, -15.0)
    assert isinstance(c, float)
    assert not math.isinf(c)
    assert c < 10


# ---- Quality scorer ----

def test_quality_full_good_cycle():
    """Long, good dT, no BUH -> high score (>= 80)."""
    c = {"duration_s": 3600, "dT_max": 5.0, "rps_max": 55, "buh_used": 0}
    assert qs.score_cycle(c) >= 80


def test_quality_short_cycle_penalized():
    """Short run: penalty applied (direction assertion, not absolute)."""
    long = {"duration_s": 3600, "dT_max": 5.0}
    short = {"duration_s": 180, "dT_max": 5.0}
    assert qs.score_cycle(short) < qs.score_cycle(long)


def test_quality_low_dt_penalized():
    """Low dT: penalty applied."""
    good = {"duration_s": 3600, "dT_max": 5.0}
    low = {"duration_s": 3600, "dT_max": 0.5}
    assert qs.score_cycle(low) < qs.score_cycle(good)


def test_quality_buh_penalized():
    """BUH usage penalized (COP=1 inefficiency)."""
    clean = {"duration_s": 3600, "dT_max": 5.0, "buh_used": 0}
    buh = {"duration_s": 3600, "dT_max": 5.0, "buh_used": 2}
    assert qs.score_cycle(buh) < qs.score_cycle(clean)


def test_quality_defrost_not_penalized():
    """R594 fix: defrost is normal operation, NOT penalized.

    Prior version of this test asserted 'defrost <= normal' which passed
    trivially (both 100). Honest assertion: defrost changes nothing.
    """
    base = {"duration_s": 3600, "dT_max": 5.0}
    with_defrost = {**base, "defrost_used": 1}
    assert qs.score_cycle(base) == qs.score_cycle(with_defrost)


def test_quality_short_off_time_penalized():
    """Short off-time penalty (off_time_s kwarg)."""
    base = {"duration_s": 3600, "dT_max": 5.0}
    long_off = qs.score_cycle(base, off_time_s=3600)
    short_off = qs.score_cycle(base, off_time_s=30)
    assert short_off < long_off


def test_quality_high_short_cycle_ratio_penalized():
    """High short-cycle ratio (kwarg) penalized."""
    base = {"duration_s": 3600, "dT_max": 5.0}
    low = qs.score_cycle(base, short_cycle_ratio=10)
    high = qs.score_cycle(base, short_cycle_ratio=90)
    assert high < low


def test_quality_missing_fields_lenient():
    """Empty record: no penalty (lenient) -> 100."""
    assert qs.score_cycle({}) == 100


def test_quality_range_always_0_100():
    for rec in [
        {}, {"duration_s": 0}, {"duration_s": 100, "dT_max": 0.1},
        {"duration_s": 3600, "dT_max": 5.0, "buh_used": 2},
        {"duration_s": 60, "dT_max": 0.0, "buh_used": 1},
    ]:
        s = qs.score_cycle(rec)
        assert 0 <= s <= 100


def test_quality_negative_dt_no_crash():
    s = qs.score_cycle({"duration_s": 3600, "dT_max": -1.0})
    assert 0 <= s <= 100


def test_quality_custom_options():
    """Custom thresholds shift the penalty decisions."""
    strict = {"good_run_threshold_min": 120, "good_dt_threshold_k": 8.0}
    record = {"duration_s": 1800, "dT_max": 5.0}  # 30min, 5K
    s_default = qs.score_cycle(record)
    s_strict = qs.score_cycle(record, strict)
    assert s_strict <= s_default
