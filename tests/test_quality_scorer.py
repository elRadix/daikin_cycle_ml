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
    assert score_cycle(r, off_time_s=3600) == 100 - PENALTY_SHORT_RUN


def test_low_dt_penalty():
    r = _good_record()
    r["dT_max"] = 2.0
    assert score_cycle(r, off_time_s=3600) == 100 - PENALTY_LOW_DT


def test_short_off_penalty():
    assert score_cycle(_good_record(), off_time_s=120) == 100 - PENALTY_SHORT_OFF


def test_high_ratio_penalty():
    assert (
        score_cycle(_good_record(), off_time_s=3600, short_cycle_ratio=80)
        == 100 - PENALTY_HIGH_RATIO
    )


def test_buh_penalty():
    r = _good_record()
    r["buh_used"] = 1
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


def test_ratio_at_threshold_not_penalised():
    assert score_cycle(_good_record(), off_time_s=3600, short_cycle_ratio=50) == 100
