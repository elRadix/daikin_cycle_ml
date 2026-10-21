"""v1.12.0: short_cycle_ratio wiring into score_cycle (issue #105)."""
from __future__ import annotations

from unittest.mock import patch

from custom_components.daikin_cycle_ml.coordinator import score_and_count
from custom_components.daikin_cycle_ml.storage.store import CycleStore


def _rec(dur: float = 1800.0) -> dict:
    return {"duration_s": dur, "start_ts": 1000.0, "end_ts": 1000.0 + dur}


def _store(short: int, existing: int, off_s: float = 3600.0) -> CycleStore:
    s = CycleStore()
    s._counters["short_runs_today"] = short
    s._counters["cycles_today"] = existing
    s.off_time_since_last = lambda now: off_s
    return s


def _run(short: int, existing: int) -> float | None:
    s = _store(short=short, existing=existing)
    with patch("custom_components.daikin_cycle_ml.coordinator.score_cycle",
               return_value=100) as m:
        score_and_count(_rec(), {}, s, now=2000.0)
        _, kw = m.call_args
        return kw.get("short_cycle_ratio")


def test_ratio_zero_when_no_short():
    assert _run(short=0, existing=0) == 0.0


def test_ratio_computed_with_history():
    # 3 / (7+1) = 37.5
    assert _run(short=3, existing=7) == 37.5


def test_ratio_exactly_50_percent():
    # 1 / (1+1) = 50
    assert _run(short=1, existing=1) == 50.0


def test_ratio_high_fires_penalty():
    # 4 / (4+1) = 80
    assert _run(short=4, existing=4) == 80.0


def test_denominator_plus_one_fix():
    # 2 / (2+1) = 66.67 (without +1 it would be 100)
    assert _run(short=2, existing=2) == 66.67
