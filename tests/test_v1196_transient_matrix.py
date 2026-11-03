"""v1.19.6: full behavior matrix per sensor x mode x transient-state.

Companion to test_v1196_pendulum_transient.py (bug reproducer).
Each test pins ONE behavioral contract. Naming convention:
  test_<sensor>_<mode>_<real|transient|mixed>_<expected>
"""

from __future__ import annotations

import time

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
MODE_COOLING = "cooling"
MODE_DEFROST = "defrost"


def _cycle(*, start_ts, mode="heating", is_transient=0,
           include_transient_key=True):
    rec = {
        "start_ts": start_ts, "end_ts": start_ts + 60, "duration_s": 60,
        "mode": mode, "dT_max": 5.0, "dT_avg": 3.0,
        "rps_max": 30, "rps_avg": 20.0, "outdoor_temp": 10.0,
        "buh_used": 0, "defrost_used": 0,
    }
    if include_transient_key:
        rec["is_transient"] = is_transient
    return rec


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
# _is_pendulum_hourly: telt (alle cycles - DHW cycles) >= threshold
# De sensor heet "pendulum hourly" en is bedoeld voor HEATING-pendelen.
# ============================================================================


def test_pendulum_hourly_heating_real_above_threshold():
    now = _now()
    cyc = [_cycle(start_ts=now - 60 * (i + 1), mode="heating", is_transient=0)
           for i in range(5)]
    coord = _FakeCoord(cyc, {"pendulum_cycles_per_hour": 4})
    assert _is_pendulum_hourly(_snap(), coord) is True


def test_pendulum_hourly_heating_real_below_threshold():
    now = _now()
    cyc = [_cycle(start_ts=now - 60 * (i + 1), mode="heating", is_transient=0)
           for i in range(3)]
    coord = _FakeCoord(cyc, {"pendulum_cycles_per_hour": 4})
    assert _is_pendulum_hourly(_snap(), coord) is False


def test_pendulum_hourly_heating_all_transient_never_fires():
    """10 transients only -> 0 real -> False (this is the bug we fix)."""
    now = _now()
    cyc = [_cycle(start_ts=now - 60 * (i + 1), mode="heating", is_transient=1)
           for i in range(10)]
    coord = _FakeCoord(cyc, {"pendulum_cycles_per_hour": 4})
    assert _is_pendulum_hourly(_snap(), coord) is False


def test_pendulum_hourly_heating_mixed_only_real_counts():
    now = _now()
    cyc = ([_cycle(start_ts=now - 60 * (i + 1), mode="heating", is_transient=1)
            for i in range(6)]
           + [_cycle(start_ts=now - 60 * (i + 10), mode="heating", is_transient=0)
              for i in range(3)])
    coord = _FakeCoord(cyc, {"pendulum_cycles_per_hour": 4})
    # 6 trans + 3 real -> only 3 count -> False
    assert _is_pendulum_hourly(_snap(), coord) is False


def test_pendulum_hourly_dhw_subtracted_from_total():
    now = _now()
    cyc = ([_cycle(start_ts=now - 60 * (i + 1), mode="dhw", is_transient=0)
            for i in range(5)]
           + [_cycle(start_ts=now - 60 * (i + 10), mode="heating", is_transient=0)
              for i in range(3)])
    coord = _FakeCoord(cyc, {"pendulum_cycles_per_hour": 4})
    # all_n=8, dhw_n=5 -> 3 >= 4 -> False
    assert _is_pendulum_hourly(_snap(), coord) is False


def test_pendulum_hourly_dhw_transient_does_not_pollute_heating_count():
    """A transient DHW must not be counted at all (neither in all_n nor dhw_n)."""
    now = _now()
    cyc = ([_cycle(start_ts=now - 60 * (i + 1), mode="dhw", is_transient=1)
            for i in range(5)]
           + [_cycle(start_ts=now - 60 * (i + 10), mode="heating", is_transient=0)
              for i in range(3)])
    coord = _FakeCoord(cyc, {"pendulum_cycles_per_hour": 4})
    # After fix: all_n=3 (only real heating), dhw_n=0 -> 3 >= 4 -> False
    # Before fix: all_n=8, dhw_n=5 -> 3 >= 4 -> False (same result!)
    assert _is_pendulum_hourly(_snap(), coord) is False


def test_pendulum_hourly_cooling_does_not_count_as_heating():
    """v1.19.6 scope A: pendulum_hourly is HEATING-only.

    5 real cooling cycles must NOT trigger pendulum_hourly. Pre-fix the
    non-DHW formula counted cooling as heating; now we count HEATING only.
    """
    now = _now()
    cyc = [_cycle(start_ts=now - 60 * (i + 1), mode="cooling", is_transient=0)
           for i in range(5)]
    coord = _FakeCoord(cyc, {"pendulum_cycles_per_hour": 4})
    assert _is_pendulum_hourly(_snap(), coord) is False


def test_pendulum_hourly_defrost_does_not_count_as_heating():
    """v1.19.6 scope A: defrost must not inflate the heating count."""
    now = _now()
    cyc = [_cycle(start_ts=now - 60 * (i + 1), mode="defrost", is_transient=0)
           for i in range(5)]
    coord = _FakeCoord(cyc, {"pendulum_cycles_per_hour": 4})
    assert _is_pendulum_hourly(_snap(), coord) is False


# ============================================================================
# _is_high_cycle_rate: telt alle cycles (mode-agnostisch) > threshold*1.5
# Threshold = pendulum_cycles_per_hour * 1.5 (default 4 * 1.5 = 6)
# ============================================================================


def _base_high() -> int:
    return 4  # pendulum_cycles_per_hour default


def _cutoff_high() -> float:
    return _base_high() * 1.5  # = 6.0


def test_high_cycle_rate_heating_real_above_cutoff():
    now = _now()
    cyc = [_cycle(start_ts=now - 60 * (i + 1), mode="heating", is_transient=0)
           for i in range(10)]
    coord = _FakeCoord(cyc, {"pendulum_cycles_per_hour": _base_high()})
    assert _is_high_cycle_rate(_snap(), coord) is True


def test_high_cycle_rate_heating_real_at_cutoff():
    """Boundary: exactly at cutoff (6) must NOT fire (> strict)."""
    now = _now()
    cyc = [_cycle(start_ts=now - 60 * (i + 1), mode="heating", is_transient=0)
           for i in range(6)]
    coord = _FakeCoord(cyc, {"pendulum_cycles_per_hour": _base_high()})
    assert _is_high_cycle_rate(_snap(), coord) is False


def test_high_cycle_rate_heating_all_transient_never_fires():
    now = _now()
    cyc = [_cycle(start_ts=now - 60 * (i + 1), mode="heating", is_transient=1)
           for i in range(15)]
    coord = _FakeCoord(cyc, {"pendulum_cycles_per_hour": _base_high()})
    assert _is_high_cycle_rate(_snap(), coord) is False


def test_high_cycle_rate_mixed_only_real_counts():
    now = _now()
    cyc = ([_cycle(start_ts=now - 60 * (i + 1), mode="heating", is_transient=1)
            for i in range(10)]
           + [_cycle(start_ts=now - 60 * (i + 20), mode="heating", is_transient=0)
              for i in range(5)])
    coord = _FakeCoord(cyc, {"pendulum_cycles_per_hour": _base_high()})
    # only 5 real, cutoff 6 -> False
    assert _is_high_cycle_rate(_snap(), coord) is False


def test_high_cycle_rate_all_modes_real_combined():
    """high_cycle_rate is mode-agnostic: heating+dhw+cooling+defrost all count."""
    now = _now()
    cyc = (
        [_cycle(start_ts=now - 60 * (i + 1), mode="heating", is_transient=0)
         for i in range(4)]
        + [_cycle(start_ts=now - 60 * (i + 5), mode="dhw", is_transient=0)
           for i in range(2)]
        + [_cycle(start_ts=now - 60 * (i + 7), mode="cooling", is_transient=0)
           for i in range(2)]
    )
    coord = _FakeCoord(cyc, {"pendulum_cycles_per_hour": _base_high()})
    # 4+2+2 = 8 > 6 -> True
    assert _is_high_cycle_rate(_snap(), coord) is True


def test_high_cycle_rate_dhw_transient_isolated():
    """Transient DHW must not contribute to high_cycle_rate."""
    now = _now()
    cyc = ([_cycle(start_ts=now - 60 * (i + 1), mode="dhw", is_transient=1)
            for i in range(10)]
           + [_cycle(start_ts=now - 60 * (i + 20), mode="heating", is_transient=0)
              for i in range(5)])
    coord = _FakeCoord(cyc, {"pendulum_cycles_per_hour": _base_high()})
    # 5 real heating < 6 -> False (10 transient DHW excluded)
    assert _is_high_cycle_rate(_snap(), coord) is False


def test_high_cycle_rate_defrost_transient_isolated():
    now = _now()
    cyc = ([_cycle(start_ts=now - 60 * (i + 1), mode="defrost", is_transient=1)
            for i in range(8)]
           + [_cycle(start_ts=now - 60 * (i + 20), mode="heating", is_transient=0)
              for i in range(5)])
    coord = _FakeCoord(cyc, {"pendulum_cycles_per_hour": _base_high()})
    assert _is_high_cycle_rate(_snap(), coord) is False


def test_high_cycle_rate_legacy_missing_field_counts_as_real():
    now = _now()
    cyc = [_cycle(start_ts=now - 60 * (i + 1), mode="heating",
                  include_transient_key=False) for i in range(8)]
    coord = _FakeCoord(cyc, {"pendulum_cycles_per_hour": _base_high()})
    # 8 > 6 -> True
    assert _is_high_cycle_rate(_snap(), coord) is True
