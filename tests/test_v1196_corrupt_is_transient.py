"""v1.19.6 FASE 5: corrupt is_transient must not crash cycle counters.

Pre-v1.19.6 these queries used `int(c.get("is_transient") or 0)`, which
raises ValueError on non-numeric strings. Combined with the R580 fix
(no silent-except), a single corrupt record in the deque crashes all
4 cycle sensors. hydrate_from_rows does not filter is_transient.
"""

from __future__ import annotations

import time

from custom_components.daikin_cycle_ml.storage.store import CycleStore


def _cycle(start_ts, *, mode="heating", is_transient=None, include_key=True):
    r = {
        "start_ts": start_ts, "end_ts": start_ts + 60, "duration_s": 60,
        "mode": mode, "dT_max": 5.0, "dT_avg": 3.0, "rps_max": 30,
        "rps_avg": 20.0, "outdoor_temp": 10.0, "buh_used": 0, "defrost_used": 0,
    }
    if include_key:
        r["is_transient"] = is_transient
    return r


def _now():
    return time.time()


def test_cycles_in_window_string_is_transient_no_crash():
    """RED: is_transient='x' must not raise, treated as non-transient."""
    now = _now()
    s = CycleStore()
    s.add_cycle(_cycle(now - 60, is_transient="x"))
    # RED on HEAD: raises ValueError. After fix: 1 (treated as real).
    assert s.cycles_in_window(now, 3600) == 1


def test_cycles_in_window_string_true_is_transient_no_crash():
    """RED: is_transient='true' must not raise, treated as non-transient."""
    now = _now()
    s = CycleStore()
    s.add_cycle(_cycle(now - 60, is_transient="true"))
    assert s.cycles_in_window(now, 3600) == 1


def test_cycles_in_window_mode_string_is_transient_no_crash():
    """RED: same for cycles_in_window_mode."""
    now = _now()
    s = CycleStore()
    s.add_cycle(_cycle(now - 60, mode="heating", is_transient="x"))
    assert s.cycles_in_window_mode(now, 3600, "heating") == 1


def test_cycles_in_window_list_is_transient_no_crash():
    """RED: is_transient=[] must not raise (empty list -> falsy -> 0)."""
    now = _now()
    s = CycleStore()
    s.add_cycle(_cycle(now - 60, is_transient=[]))
    assert s.cycles_in_window(now, 3600) == 1


def test_cycles_in_window_bool_true_still_transient():
    """GUARD: is_transient=True (bool) -> still treated as transient."""
    now = _now()
    s = CycleStore()
    s.add_cycle(_cycle(now - 60, is_transient=True))
    assert s.cycles_in_window(now, 3600) == 0


def test_cycles_in_window_int_one_still_transient():
    """GUARD: is_transient=1 -> still treated as transient."""
    now = _now()
    s = CycleStore()
    s.add_cycle(_cycle(now - 60, is_transient=1))
    assert s.cycles_in_window(now, 3600) == 0
