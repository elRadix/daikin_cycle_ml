"""Reproducer for pendulum/high_cycle_rate/dhw_pendulum transient leak.

Companion to #245 (short_off) and #246 (short_run) - same bug class.

On HEAD=9270941 the 3 RED tests below FAIL (proving the bug).
After the v1.19.6 fix they must PASS; the GUARD tests must stay green.
"""

from __future__ import annotations

import time

from freezegun import freeze_time

from custom_components.daikin_cycle_ml import binary_sensor as _bs
from custom_components.daikin_cycle_ml.binary_sensor import (
    _is_dhw_pendulum,
    _is_high_cycle_rate,
    _is_pendulum_daily,
    _is_pendulum_hourly,
)
from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
from custom_components.daikin_cycle_ml.storage.store import CycleStore

MODE_DHW = getattr(_bs, "MODE_DHW", "dhw")


def _cycle(
    *,
    start_ts: float,
    mode: str = "heating",
    is_transient: int = 0,
    include_transient_key: bool = True,
) -> dict:
    rec = {
        "start_ts": start_ts,
        "end_ts": start_ts + 60,
        "duration_s": 60,
        "mode": mode,
        "dT_max": 5.0,
        "dT_avg": 3.0,
        "rps_max": 30,
        "rps_avg": 20.0,
        "outdoor_temp": 10.0,
        "buh_used": 0,
        "defrost_used": 0,
    }
    if include_transient_key:
        rec["is_transient"] = is_transient
    return rec


class _FakeCoord:
    def __init__(self, cycles: list[dict], options: dict | None = None):
        self.store = CycleStore()
        for c in cycles:
            self.store.add_cycle(c)
        self.options = options or {}


def _snap() -> DataSnapshot:
    return DataSnapshot()


# ---------------------------------------------------------------------------
# RED tests - prove the bug on HEAD=9270941
# ---------------------------------------------------------------------------


def test_pendulum_hourly_ignores_transient():
    """5 transients + 3 real heating, threshold=4 -> correct answer is False."""
    now = time.time()
    cycles = [
        _cycle(start_ts=now - 60 * (i + 1), is_transient=1) for i in range(5)
    ] + [
        _cycle(start_ts=now - 60 * (i + 10), is_transient=0) for i in range(3)
    ]
    coord = _FakeCoord(cycles, {"pendulum_cycles_per_hour": 4})
    # HEAD bug: 8 >= 4 -> True.  Correct after fix: 3 >= 4 -> False.
    assert _is_pendulum_hourly(_snap(), coord) is False


def test_high_cycle_rate_ignores_transient():
    """4 transients + 5 real heating, base=4 (cutoff 6) -> correct is False."""
    now = time.time()
    cycles = [
        _cycle(start_ts=now - 60 * (i + 1), is_transient=1) for i in range(4)
    ] + [
        _cycle(start_ts=now - 60 * (i + 10), is_transient=0) for i in range(5)
    ]
    coord = _FakeCoord(cycles, {"pendulum_cycles_per_hour": 4})
    # HEAD bug: 9 > 6 -> True.  Correct after fix: 5 > 6 -> False.
    assert _is_high_cycle_rate(_snap(), coord) is False


def test_dhw_pendulum_ignores_transient():
    """3 transient DHW + 2 real DHW, threshold=3 -> correct answer is False."""
    now = time.time()
    cycles = [
        _cycle(start_ts=now - 60 * (i + 1), mode=MODE_DHW, is_transient=1)
        for i in range(3)
    ] + [
        _cycle(start_ts=now - 60 * (i + 10), mode=MODE_DHW, is_transient=0)
        for i in range(2)
    ]
    coord = _FakeCoord(cycles, {"dhw_pendulum_cycles_per_hour": 3})
    # HEAD bug: 5 >= 3 -> True.  Correct after fix: 2 >= 3 -> False.
    assert _is_dhw_pendulum(_snap(), coord) is False


# ---------------------------------------------------------------------------
# GUARD tests - must remain green after the fix (no over-fix)
# ---------------------------------------------------------------------------


def test_pendulum_hourly_still_fires_on_real():
    now = time.time()
    cycles = [
        _cycle(start_ts=now - 60 * (i + 1), is_transient=0) for i in range(5)
    ]
    coord = _FakeCoord(cycles, {"pendulum_cycles_per_hour": 4})
    assert _is_pendulum_hourly(_snap(), coord) is True


def test_high_cycle_rate_still_fires_on_real():
    now = time.time()
    cycles = [
        _cycle(start_ts=now - 60 * (i + 1), is_transient=0) for i in range(10)
    ]
    coord = _FakeCoord(cycles, {"pendulum_cycles_per_hour": 4})
    assert _is_high_cycle_rate(_snap(), coord) is True


def test_dhw_pendulum_still_fires_on_real():
    now = time.time()
    cycles = [
        _cycle(start_ts=now - 60 * (i + 1), mode=MODE_DHW, is_transient=0)
        for i in range(4)
    ]
    coord = _FakeCoord(cycles, {"dhw_pendulum_cycles_per_hour": 3})
    assert _is_dhw_pendulum(_snap(), coord) is True


# ---------------------------------------------------------------------------
# BACKWARD-COMPAT - cycles without is_transient field must count as real
# ---------------------------------------------------------------------------


def test_missing_is_transient_treated_as_real():
    now = time.time()
    cycles = [
        _cycle(start_ts=now - 60 * (i + 1), include_transient_key=False)
        for i in range(5)
    ]
    coord = _FakeCoord(cycles, {"pendulum_cycles_per_hour": 4})
    assert _is_pendulum_hourly(_snap(), coord) is True



# ---------------------------------------------------------------------------
# v1.19.6 extension: pendulum_daily (uses cycles_today -> non_transient_today)
# ---------------------------------------------------------------------------


def _today_noon() -> float:
    import datetime as _dt
    return _dt.datetime.combine(_dt.date.today(), _dt.time(12, 0)).timestamp()


@freeze_time("2026-11-03 14:00:00")
def test_pendulum_daily_ignores_transient():
    """30 real + 10 transient today, threshold=40 -> correct is False."""
    noon = _today_noon()
    cycles = [
        _cycle(start_ts=noon - 60 * (i + 1), is_transient=1) for i in range(10)
    ] + [
        _cycle(start_ts=noon - 60 * (i + 20), is_transient=0) for i in range(30)
    ]
    coord = _FakeCoord(cycles, {"pendulum_cycles_per_day": 40})
    # HEAD bug: 40 >= 40 -> True.  Correct after fix: 30 >= 40 -> False.
    assert _is_pendulum_daily(_snap(), coord) is False


@freeze_time("2026-11-03 14:00:00")
def test_pendulum_daily_still_fires_on_real():
    noon = _today_noon()
    cycles = [
        _cycle(start_ts=noon - 60 * (i + 1), is_transient=0) for i in range(45)
    ]
    coord = _FakeCoord(cycles, {"pendulum_cycles_per_day": 40})
    assert _is_pendulum_daily(_snap(), coord) is True


@freeze_time("2026-11-03 14:00:00")
def test_pendulum_daily_missing_is_transient_counts_as_real():
    noon = _today_noon()
    cycles = [
        _cycle(start_ts=noon - 60 * (i + 1), include_transient_key=False)
        for i in range(45)
    ]
    coord = _FakeCoord(cycles, {"pendulum_cycles_per_day": 40})
    assert _is_pendulum_daily(_snap(), coord) is True
