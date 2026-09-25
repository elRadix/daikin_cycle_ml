"""Pure-python quality scoring for Daikin Cycle ML (Batch 6a)."""
from __future__ import annotations

import logging
from typing import Any, Mapping

_LOGGER = logging.getLogger(__name__)

DEFAULT_GOOD_RUN_MIN = 45
DEFAULT_GOOD_DT_K = 5.0
DEFAULT_GOOD_OFF_MIN = 20
DEFAULT_SHORT_CYCLE_RATIO = 50

PENALTY_SHORT_RUN = 30
PENALTY_LOW_DT = 20
PENALTY_SHORT_OFF = 20
PENALTY_HIGH_RATIO = 20
PENALTY_BUH = 10


def _opt(options: Mapping[str, Any] | None, key: str, default: float) -> float:
    if not options:
        return default
    v = options.get(key, default)
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def score_cycle(
    record: Mapping[str, Any],
    options: Mapping[str, Any] | None = None,
    *,
    off_time_s: float | None = None,
    short_cycle_ratio: float | None = None,
) -> int:
    """Return 0..100 quality score. Missing fields => no penalty (lenient)."""
    good_run_min = _opt(options, "good_run_threshold_min", DEFAULT_GOOD_RUN_MIN)
    good_dt_k = _opt(options, "good_dt_threshold_k", DEFAULT_GOOD_DT_K)
    good_off_min = _opt(options, "good_off_threshold_min", DEFAULT_GOOD_OFF_MIN)
    ratio_thr = _opt(options, "short_cycle_ratio_threshold", DEFAULT_SHORT_CYCLE_RATIO)

    score = 100
    duration = record.get("duration_s")
    if isinstance(duration, (int, float)) and duration < good_run_min * 60:
        score -= PENALTY_SHORT_RUN

    dt = record.get("dT_max")
    if isinstance(dt, (int, float)) and dt < good_dt_k:
        score -= PENALTY_LOW_DT

    if isinstance(off_time_s, (int, float)) and off_time_s < good_off_min * 60:
        score -= PENALTY_SHORT_OFF

    if isinstance(short_cycle_ratio, (int, float)) and short_cycle_ratio > ratio_thr:
        score -= PENALTY_HIGH_RATIO

    if record.get("buh_used"):
        score -= PENALTY_BUH

    return max(0, int(score))
