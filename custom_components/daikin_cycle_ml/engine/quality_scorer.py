"""Pure-python quality scoring for Daikin Cycle ML (Batch 6a, #421).

Every penalty is proportional to how far the cycle is from good, with a
fixed maximum (docs/ML.md "Quality score"). Missing fields give no
penalty (lenient). Before #421 the penalties were all-or-nothing: a 2 min
and an 8 min backup-heater run both cost 10 points, a 44 min run cost the
same 30 points as a 5 min run.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from typing import Any

_LOGGER = logging.getLogger(__name__)

DEFAULT_GOOD_RUN_MIN = 45
DEFAULT_GOOD_DT_K = 5.0
DEFAULT_GOOD_OFF_MIN = 20
DEFAULT_SHORT_CYCLE_RATIO = 50

# maximum points per penalty
PENALTY_SHORT_RUN = 30
PENALTY_LOW_DT = 20
PENALTY_SHORT_OFF = 20
PENALTY_HIGH_RATIO = 20
PENALTY_BUH = 20
PENALTY_DEFROST = 10

# 1 point per % of the run time (BUH step 2 counts double)
BUH_POINTS_PER_PCT = 1.0
# defrost up to 5 % of the run time is normal; 1 point per % above
DEFROST_FREE_PCT = 5.0
DEFROST_POINTS_PER_PCT = 1.0
# BUH used but its time unknown (cycles stored before #421)
BUH_UNKNOWN_S = 300.0

PENALTY_KEYS = ("short_run", "low_dt", "short_off", "short_ratio", "buh", "defrost")


def _opt(options: Mapping[str, Any] | None, key: str, default: float) -> float:
    if not options:
        return default
    v = options.get(key, default)
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def _shortfall(value: float | None, good: float, points: float) -> float:
    """``points`` x the fraction ``value`` falls short of ``good`` (0..points)."""
    if value is None or good <= 0:
        return 0.0
    return points * min(1.0, max(0.0, (good - value) / good))


def _buh_waived(record: Mapping[str, Any], options: Mapping[str, Any] | None) -> bool:
    """#289: DHW legionella run (tank >= 60 °C) needs the BUH."""
    tank = _num(record.get("dhw_tank_temp"))
    return (
        _opt(options, "buh_penalty_legionella_waived", 1.0) > 0
        and record.get("mode") == "dhw"
        and tank is not None and tank >= 60.0
    )


def score_breakdown(
    record: Mapping[str, Any],
    options: Mapping[str, Any] | None = None,
    *,
    off_time_s: float | None = None,
    short_cycle_ratio: float | None = None,
    segment: bool = False,
    running: bool = False,
) -> dict[str, float]:
    """Penalty points per criterion (rounded to 0.1).

    ``segment``: part of a longer run (heating <-> DHW split, 48 h cap),
    no short-run penalty (#419). ``running``: an open cycle whose length
    and dT_max can still grow, neither is judged (#419).
    """
    good_run_s = _opt(options, "good_run_threshold_min", DEFAULT_GOOD_RUN_MIN) * 60
    good_dt_k = _opt(options, "good_dt_threshold_k", DEFAULT_GOOD_DT_K)
    good_off_s = _opt(options, "good_off_threshold_min", DEFAULT_GOOD_OFF_MIN) * 60
    ratio_thr = _opt(options, "short_cycle_ratio_threshold", DEFAULT_SHORT_CYCLE_RATIO)
    duration = _num(record.get("duration_s"))

    out = dict.fromkeys(PENALTY_KEYS, 0.0)
    if not segment and not running:
        out["short_run"] = _shortfall(duration, good_run_s, PENALTY_SHORT_RUN)
    if not running:
        out["low_dt"] = _shortfall(_num(record.get("dT_max")), good_dt_k, PENALTY_LOW_DT)
    out["short_off"] = _shortfall(_num(off_time_s), good_off_s, PENALTY_SHORT_OFF)

    ratio = _num(short_cycle_ratio)
    if ratio is not None and ratio_thr > 0:
        # 0 up to half the threshold, full penalty at 1.5 x the threshold
        frac = (ratio - ratio_thr / 2.0) / ratio_thr
        out["short_ratio"] = PENALTY_HIGH_RATIO * min(1.0, max(0.0, frac))

    if duration and duration > 0:
        if record.get("buh_used") and not _buh_waived(record, options):
            buh_s = _num(record.get("buh_s"))
            buh_s = BUH_UNKNOWN_S if buh_s is None or buh_s <= 0 else buh_s
            out["buh"] = min(
                float(PENALTY_BUH), 100.0 * buh_s / duration * BUH_POINTS_PER_PCT,
            )
        defrost_s = _num(record.get("defrost_s"))
        if defrost_s:
            excess = 100.0 * defrost_s / duration - DEFROST_FREE_PCT
            out["defrost"] = min(
                float(PENALTY_DEFROST), max(0.0, excess * DEFROST_POINTS_PER_PCT),
            )
    return {k: round(v, 1) for k, v in out.items()}


def score_cycle(
    record: Mapping[str, Any],
    options: Mapping[str, Any] | None = None,
    *,
    off_time_s: float | None = None,
    short_cycle_ratio: float | None = None,
    segment: bool = False,
    running: bool = False,
) -> int:
    """Return 0..100 quality score: 100 minus the proportional penalties."""
    pen = score_breakdown(
        record, options, off_time_s=off_time_s,
        short_cycle_ratio=short_cycle_ratio, segment=segment, running=running,
    )
    return max(0, min(100, int(round(100.0 - sum(pen.values())))))


# --- #421: rescoring stored cycles -----------------------------------------------

# consecutive cycles closer than this are one run (heating <-> DHW split)
SEGMENT_GAP_S = 90.0
# defrost used but its time unknown (cycles stored before #421): one defrost
DEFROST_UNKNOWN_S = 360.0


def _local_day(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def _estimate_buh_s(
    rows: list[dict[str, Any]], events_by_day: Mapping[str, Any] | None,
) -> dict[Any, float]:
    """BUH seconds for cycles without ``buh_s``: the day's recorded BUH
    minutes shared over that day's BUH cycles by run length."""
    out: dict[Any, float] = {}
    by_day: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        if r.get("buh_used") and _num(r.get("buh_s")) is None:
            by_day.setdefault(_local_day(float(r["start_ts"])), []).append(r)
    for day, cycles in by_day.items():
        ev = (events_by_day or {}).get(day) or {}
        minutes = _num(ev.get("buh_min")) if isinstance(ev, Mapping) else None
        total = sum(_num(c.get("duration_s")) or 0.0 for c in cycles)
        for c in cycles:
            dur = _num(c.get("duration_s")) or 0.0
            out[c["id"]] = (
                minutes * 60.0 * dur / total if minutes and total > 0
                else BUH_UNKNOWN_S
            )
    return out


def rescore_history(
    rows: list[dict[str, Any]],
    options: Mapping[str, Any] | None = None,
    events_by_day: Mapping[str, Any] | None = None,
) -> dict[Any, int | None]:
    """Score stored cycles (ordered by start) with the #421 formula.

    Rebuilds what the live pipeline knew at close: the pause before each
    cycle (start - previous end; a gap <= SEGMENT_GAP_S is a split, no
    pause), split segments, and the day's short-run ratio. Cycles rebuilt
    from COP samples only (is_reconstructed, no dT) keep no score.
    """
    sr_s = _opt(options, "short_run_threshold_min", 20) * 60
    buh_est = _estimate_buh_s(rows, events_by_day)
    scores: dict[Any, int | None] = {}
    day_cycles: dict[str, int] = {}
    day_short: dict[str, int] = {}
    for i, r in enumerate(rows):
        start, end = float(r["start_ts"]), float(r["end_ts"])
        prev = rows[i - 1] if i > 0 else None
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        gap_before = start - float(prev["end_ts"]) if prev else None
        continued = gap_before is not None and 0 <= gap_before <= SEGMENT_GAP_S
        ends_split = nxt is not None and 0 <= float(nxt["start_ts"]) - end <= SEGMENT_GAP_S
        segment = continued or ends_split
        day = _local_day(start)
        dur = _num(r.get("duration_s"))
        if not segment and dur is not None and dur < sr_s:
            day_short[day] = day_short.get(day, 0) + 1
        ratio = 100.0 * day_short.get(day, 0) / (day_cycles.get(day, 0) + 1)
        day_cycles[day] = day_cycles.get(day, 0) + 1
        if r.get("is_reconstructed") and _num(r.get("dT_max")) is None:
            scores[r["id"]] = r.get("quality_score")
            continue
        rec = dict(r)
        if rec.get("id") in buh_est:
            rec["buh_s"] = buh_est[rec["id"]]
        if rec.get("defrost_used") and _num(rec.get("defrost_s")) is None:
            rec["defrost_s"] = DEFROST_UNKNOWN_S
        off = None if continued or gap_before is None or gap_before < 0 else gap_before
        scores[r["id"]] = score_cycle(
            rec, options, off_time_s=off, short_cycle_ratio=ratio, segment=segment,
        )
    return scores
