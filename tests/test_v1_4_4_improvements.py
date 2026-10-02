"""v1.4.4 regression: hydrate marks _day_key."""
from __future__ import annotations

import time

from custom_components.daikin_cycle_ml.storage.store import CycleStore


def _today_ts(offset_s: float = 0.0) -> float:
    lt = time.localtime()
    base = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 12, 0, 0, 0, 0, -1))
    return float(base + offset_s)


def test_hydrate_sets_day_key():
    s = CycleStore()
    s.hydrate_from_rows([{"start_ts": _today_ts(), "quality_score": 90}])
    assert "_day_key" in s._counters
    expected = time.strftime("%Y-%m-%d", time.localtime())
    assert s._counters["_day_key"] == expected


def test_hydrate_then_daily_reset_same_day_keeps_counters():
    s = CycleStore()
    s.hydrate_from_rows([
        {"start_ts": _today_ts(), "quality_score": 90},
        {"start_ts": _today_ts(60), "quality_score": 30},
    ])
    assert s.get("good_cycles_today") == 1
    assert s.get("bad_cycles_today") == 1
    assert s.get("cycles_today") == 2
    assert s.daily_reset_if_needed(time.time()) is False
    assert s.get("good_cycles_today") == 1
    assert s.get("bad_cycles_today") == 1
    assert s.get("cycles_today") == 2


def test_daily_reset_next_day_clears_counters():
    s = CycleStore()
    s._counters["_day_key"] = "1970-01-01"
    s._counters["good_cycles_today"] = 5
    s._counters["bad_cycles_today"] = 3
    assert s.daily_reset_if_needed(time.time()) is True
    assert s.get("good_cycles_today") == 0
    assert s.get("bad_cycles_today") == 0
