"""Reproduction tests for quality_score drift (prod cycle id=321).

Evidence (prod-1, 2026-11-08 08:13:30 -> 09:02:30):
  cycle 321: duration_s=2940 (49min), dT_max=4.3, buh_used=0
  stored quality_score = 50
  expected with current opts (45/4.0) = 100
  50 = score with 60/5.0 (SHORT_RUN + LOW_DT, stale options)

Additional bug: _async_backfill_quality calls _score_cycle(rec, None) which uses
DEFAULT constants (45/5.0), ignoring user options. Reproduces on prod cycles 278, 303.

Evidence: R634 - prod-1 DB cycles id=321; R735 - backfill default bug.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.daikin_cycle_ml.engine.quality_scorer import score_cycle


CYCLE_321 = {
    "start_ts": 1794122010.0,
    "end_ts": 1794124950.0,
    "duration_s": 2940,
    "mode": "heating",
    "dT_max": 4.3,
    "dT_avg": 3.5,
    "buh_used": False,
    "defrost_used": True,
    "is_transient": 0,
}

USER_OPTIONS = {
    "good_run_threshold_min": 45.0,
    "good_dt_threshold_k": 4.0,
    "good_off_threshold_min": 20.0,
    "short_cycle_ratio_threshold": 50.0,
}

STALE_OPTIONS = {
    "good_run_threshold_min": 60.0,
    "good_dt_threshold_k": 5.0,
}


def test_cycle_321_scores_100_with_user_options():
    """With current user opts (45/4.0), cycle 321 must score 100."""
    score = score_cycle(
        CYCLE_321, USER_OPTIONS,
        off_time_s=42456.0,
        short_cycle_ratio=0.0,
    )
    assert score == 100, f"cycle 321 must score 100 with user options, got {score}"


def test_cycle_321_scores_50_with_stale_options():
    """With hypothesized stale opts (60/5.0), cycle 321 scores 50 (== prod stored)."""
    score = score_cycle(
        CYCLE_321, STALE_OPTIONS,
        off_time_s=42456.0,
        short_cycle_ratio=0.0,
    )
    assert score == 50, "confirms stale-options hypothesis produces stored prod value"


def test_score_cycle_uses_options_not_defaults():
    """Guard: score_cycle must honor options, not fall back to defaults."""
    record = {"duration_s": 2940, "dT_max": 4.3, "buh_used": False}
    user_score = score_cycle(record, USER_OPTIONS, off_time_s=10000.0, short_cycle_ratio=0.0)
    default_score = score_cycle(record, None, off_time_s=10000.0, short_cycle_ratio=0.0)
    assert user_score == 100
    assert default_score == 80
    assert user_score > default_score


async def test_backfill_uses_user_options(hass):
    """REPRODUCER (R735): backfill must use user options, not defaults.

    Bug: _async_backfill_quality defines `_scorer(rec) -> _score_cycle(rec, None)`
    which always uses DEFAULT constants regardless of user options.

    If this test FAILS -> bug confirmed.
    """
    from custom_components.daikin_cycle_ml import _async_backfill_quality

    coordinator = MagicMock()
    coordinator.options = USER_OPTIONS
    coordinator.db = MagicMock()

    _test_record = {"duration_s": 2940, "dT_max": 4.3, "buh_used": False}

    def _mock_backfill(scorer):
        scorer(_test_record)
        return 1

    coordinator.db.async_backfill_quality_scores = AsyncMock(side_effect=_mock_backfill)

    with patch("custom_components.daikin_cycle_ml._score_cycle") as mock_score:
        mock_score.return_value = 100
        await _async_backfill_quality(coordinator)

        assert mock_score.called, "backfill must invoke _score_cycle"
        args, kwargs = mock_score.call_args_list[0]
        second_arg = args[1] if len(args) > 1 else kwargs.get("options")
        assert second_arg is not None, (
            "REGRESSION (R735): _async_backfill_quality calls _score_cycle(rec, None) - "
            "user options ignored. Prod evidence: cycles 278, 303 scored with defaults."
        )
        assert second_arg == USER_OPTIONS, (
            f"backfill must pass coordinator.options, got {second_arg}"
        )


def test_cycle_321_record_matches_prod_evidence():
    """Documentation: verify the CYCLE_321 fixture matches prod values."""
    assert CYCLE_321["duration_s"] == 2940
    assert CYCLE_321["dT_max"] == 4.3
    assert CYCLE_321["buh_used"] is False
    assert CYCLE_321["is_transient"] == 0
