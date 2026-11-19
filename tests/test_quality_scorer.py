"""Tests for quality_scorer (Batch 6a)."""

from __future__ import annotations

from custom_components.daikin_cycle_ml.engine.quality_scorer import (
    PENALTY_BUH,
    PENALTY_HIGH_RATIO,
    PENALTY_LOW_DT,
    PENALTY_SHORT_OFF,
    PENALTY_SHORT_RUN,
    score_cycle,
)


def _good_record():
    return {
        "duration_s": 3600,
        "dT_max": 8.0,
        "buh_used": 0,
    }


def test_perfect_cycle_scores_100():
    assert score_cycle(_good_record(), off_time_s=3600) == 100


def test_missing_record_scores_100():
    assert score_cycle({}) == 100


def test_none_options_uses_defaults():
    assert score_cycle(_good_record(), None, off_time_s=3600) == 100


def test_short_run_penalty():
    r = _good_record()
    r["duration_s"] = 600
    # #421: proportional, 30 x (45 - 10) / 45 = 23.3
    assert score_cycle(r, off_time_s=3600) == 77
    r["duration_s"] = 0
    assert score_cycle(r, off_time_s=3600) == 100 - PENALTY_SHORT_RUN


def test_low_dt_penalty():
    r = _good_record()
    r["dT_max"] = 2.0
    # #421: 20 x (5 - 2) / 5 = 12
    assert score_cycle(r, off_time_s=3600) == 88
    r["dT_max"] = 0.0
    assert score_cycle(r, off_time_s=3600) == 100 - PENALTY_LOW_DT


def test_short_off_penalty():
    # #421: 20 x (20 - 2) / 20 = 18
    assert score_cycle(_good_record(), off_time_s=120) == 82
    assert score_cycle(_good_record(), off_time_s=0) == 100 - PENALTY_SHORT_OFF


def test_high_ratio_penalty():
    assert (
        score_cycle(_good_record(), off_time_s=3600, short_cycle_ratio=80)
        == 100 - PENALTY_HIGH_RATIO
    )


def test_buh_penalty():
    r = _good_record()
    r["buh_used"] = 1
    # #421: unknown BUH time = 5 min of a 60 min run = 8.3 % -> 8.3 points
    assert score_cycle(r, off_time_s=3600) == 92
    r["buh_s"] = 120.0                      # 2 min -> 3.3 %
    assert score_cycle(r, off_time_s=3600) == 97
    r["buh_s"] = 480.0                      # 8 min -> 13.3 %
    assert score_cycle(r, off_time_s=3600) == 87
    r["buh_s"] = 3600.0                     # whole run -> capped
    assert score_cycle(r, off_time_s=3600) == 100 - PENALTY_BUH


def test_all_penalties_clamped_to_zero():
    r = {"duration_s": 100, "dT_max": 1.0, "buh_used": 1}
    assert score_cycle(r, off_time_s=60, short_cycle_ratio=90) == 0


def test_custom_thresholds():
    r = {"duration_s": 100, "dT_max": 8.0, "buh_used": 0}
    opts = {"good_run_threshold_min": 1}
    assert score_cycle(r, opts, off_time_s=3600) == 100


def test_invalid_duration_ignored():
    r = {"duration_s": "garbage", "dT_max": 8.0, "buh_used": 0}
    assert score_cycle(r, off_time_s=3600) == 100


def test_ratio_penalty_is_proportional():
    # #421: 0 up to half the threshold (25 %), half at the threshold, full at 75 %
    assert score_cycle(_good_record(), off_time_s=3600, short_cycle_ratio=25) == 100
    assert score_cycle(_good_record(), off_time_s=3600, short_cycle_ratio=50) == 90
    assert score_cycle(_good_record(), off_time_s=3600, short_cycle_ratio=75) == 80
