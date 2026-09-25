"""Tests for storage.store.CycleStore."""
from __future__ import annotations

from custom_components.daikin_cycle_ml.storage.store import CycleStore


def _rec(start=0.0, end=100.0, mode="heating"):
    return {"start_ts": start, "end_ts": end, "mode": mode, "duration_s": 100}


def test_add_and_retrieve():
    s = CycleStore()
    s.add_cycle(_rec())
    assert s.count() == 1
    assert s.last_cycle()["mode"] == "heating"


def test_maxlen_drops_oldest():
    s = CycleStore(maxlen=3)
    for i in range(5):
        s.add_cycle(_rec(start=float(i), end=float(i + 1)))
    assert s.count() == 3
    assert s.cycles()[0]["start_ts"] == 2.0


def test_counters_track_total_and_mode():
    s = CycleStore()
    s.add_cycle(_rec(mode="heating"))
    s.add_cycle(_rec(mode="dhw"))
    s.add_cycle(_rec(mode="heating"))
    assert s.get("cycles_total") == 3
    assert s.get("cycles_heating") == 2
    assert s.get("cycles_dhw") == 1


def test_increment_and_reset():
    s = CycleStore()
    assert s.increment("foo") == 1
    assert s.increment("foo", 5) == 6
    s.reset(["foo"])
    assert s.get("foo") == 0


def test_reset_all():
    s = CycleStore()
    s.increment("a")
    s.increment("b")
    s.reset()
    assert s.get("a") == 0
    assert s.get("b") == 0


def test_off_time_since_last():
    s = CycleStore()
    assert s.off_time_since_last(100.0) is None
    s.add_cycle(_rec(end=50.0))
    assert s.off_time_since_last(70.0) == 20.0
    assert s.off_time_since_last(30.0) == 0.0


def test_last_cycle_returns_copy():
    s = CycleStore()
    s.add_cycle(_rec())
    a = s.last_cycle()
    a["mode"] = "mutated"
    assert s.last_cycle()["mode"] == "heating"
