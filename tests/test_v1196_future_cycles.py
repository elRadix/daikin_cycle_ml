"""v1.19.6 FASE 4: future-cycle guard for window counters.

Same family as v1.14.0 (#? clock skew tolerance in cycles_today) and
FIX A/B/C (transient exclusion). The future_cutoff guard exists only on
cycles_today; cycles_in_window and cycles_in_window_mode accept any
distant-future start_ts, inflating counts on HA-reboot+clock-drift,
DB-import corruption, or multi-device skew.

Parity target: cycles_today (v1.14.0) -> >now+60s skipped, <=60s kept.
"""

from __future__ import annotations

import time

from custom_components.daikin_cycle_ml.binary_sensor import (
    _is_dhw_pendulum,
    _is_high_cycle_rate,
    _is_pendulum_hourly,
)
from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
from custom_components.daikin_cycle_ml.storage.store import CycleStore


def _cycle(start_ts, *, mode="heating", is_transient=0):
    return {
        "start_ts": start_ts, "end_ts": start_ts + 60, "duration_s": 60,
        "mode": mode, "dT_max": 5.0, "dT_avg": 3.0, "rps_max": 30,
        "rps_avg": 20.0, "outdoor_temp": 10.0, "buh_used": 0, "defrost_used": 0,
        "is_transient": is_transient,
    }


class _FakeCoord:
    def __init__(self, cycles, options=None):
        self.store = CycleStore()
        for c in cycles:
            self.store.add_cycle(c)
        self.options = options or {}


def _snap():
    return DataSnapshot()


def _now():
    return time.time()


# ============================================================================
# Store-level: cycles_in_window / cycles_in_window_mode
# ============================================================================


def test_cycles_in_window_skips_far_future():
    """RED: cycle at now+3600 must NOT count in window (parity with cycles_today)."""
    now = _now()
    s = CycleStore()
    s.add_cycle(_cycle(now - 60))           # past, counts
    s.add_cycle(_cycle(now + 3600))         # far future, must NOT count
    assert s.cycles_in_window(now, 3600) == 1


def test_cycles_in_window_60s_tolerance_kept():
    """GUARD: cycle at now+30 (within skew) MUST still count."""
    now = _now()
    s = CycleStore()
    s.add_cycle(_cycle(now + 30))
    assert s.cycles_in_window(now, 3600) == 1


def test_cycles_in_window_mode_skips_far_future():
    """RED: same rule for cycles_in_window_mode."""
    now = _now()
    s = CycleStore()
    s.add_cycle(_cycle(now - 60, mode="heating"))
    s.add_cycle(_cycle(now + 3600, mode="heating"))
    assert s.cycles_in_window_mode(now, 3600, "heating") == 1


def test_cycles_in_window_mode_60s_tolerance_kept():
    """GUARD: within skew still counts."""
    now = _now()
    s = CycleStore()
    s.add_cycle(_cycle(now + 30, mode="dhw"))
    assert s.cycles_in_window_mode(now, 3600, "dhw") == 1


# ============================================================================
# Binary-sensor level: sensors must not trigger on future cycles
# ============================================================================


def test_pendulum_hourly_ignores_future_cycles():
    """RED: 5 future heating cycles -> sensor must NOT fire."""
    now = _now()
    cyc = [_cycle(now + 3600 + 60 * i, mode="heating") for i in range(5)]
    coord = _FakeCoord(cyc, {"pendulum_cycles_per_hour": 4})
    assert _is_pendulum_hourly(_snap(), coord) is False


def test_dhw_pendulum_ignores_future_cycles():
    """RED: 5 future DHW cycles -> sensor must NOT fire."""
    now = _now()
    cyc = [_cycle(now + 3600 + 60 * i, mode="dhw") for i in range(5)]
    coord = _FakeCoord(cyc, {"dhw_pendulum_cycles_per_hour": 3})
    assert _is_dhw_pendulum(_snap(), coord) is False


def test_high_cycle_rate_ignores_future_cycles():
    """RED: 10 future heating cycles -> not > 6 -> must NOT fire."""
    now = _now()
    cyc = [_cycle(now + 3600 + 60 * i, mode="heating") for i in range(10)]
    coord = _FakeCoord(cyc, {"pendulum_cycles_per_hour": 4})
    assert _is_high_cycle_rate(_snap(), coord) is False
