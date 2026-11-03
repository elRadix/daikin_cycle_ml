"""v1.19.6 FASE 2c: _is_dhw_pendulum behavior matrix.

Companion to test_v1196_transient_matrix.py (pendulum_hourly, high_cycle_rate).
dhw_pendulum counts DHW cycles in last 1h. Threshold default 3.
Mode-isolation: heating/cooling/defrost must NOT trigger.
"""

from __future__ import annotations

import time

from custom_components.daikin_cycle_ml.binary_sensor import _is_dhw_pendulum
from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
from custom_components.daikin_cycle_ml.storage.store import CycleStore


def _cycle(start_ts, *, mode="dhw", is_transient=0, include_key=True):
    rec = {
        "start_ts": start_ts, "end_ts": start_ts + 60, "duration_s": 60,
        "mode": mode, "dT_max": 5.0, "dT_avg": 3.0, "rps_max": 30,
        "rps_avg": 20.0, "outdoor_temp": 10.0, "buh_used": 0, "defrost_used": 0,
    }
    if include_key:
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
# dhw_pendulum: threshold (default 3) DHW cycles in last hour
# ============================================================================


def test_dhw_pendulum_real_above_threshold():
    now = _now()
    cyc = [_cycle(now - 60 * (i + 1), mode="dhw", is_transient=0) for i in range(4)]
    coord = _FakeCoord(cyc, {"dhw_pendulum_cycles_per_hour": 3})
    assert _is_dhw_pendulum(_snap(), coord) is True


def test_dhw_pendulum_real_at_threshold():
    """Boundary: exactly 3 (>= 3) fires."""
    now = _now()
    cyc = [_cycle(now - 60 * (i + 1), mode="dhw", is_transient=0) for i in range(3)]
    coord = _FakeCoord(cyc, {"dhw_pendulum_cycles_per_hour": 3})
    assert _is_dhw_pendulum(_snap(), coord) is True


def test_dhw_pendulum_real_below_threshold():
    now = _now()
    cyc = [_cycle(now - 60 * (i + 1), mode="dhw", is_transient=0) for i in range(2)]
    coord = _FakeCoord(cyc, {"dhw_pendulum_cycles_per_hour": 3})
    assert _is_dhw_pendulum(_snap(), coord) is False


def test_dhw_pendulum_all_transient_never_fires():
    """10 transients only -> 0 real -> False."""
    now = _now()
    cyc = [_cycle(now - 60 * (i + 1), mode="dhw", is_transient=1) for i in range(10)]
    coord = _FakeCoord(cyc, {"dhw_pendulum_cycles_per_hour": 3})
    assert _is_dhw_pendulum(_snap(), coord) is False


def test_dhw_pendulum_mixed_only_real_counts():
    """5 transients + 2 real -> 2 < 3 -> False."""
    now = _now()
    cyc = (
        [_cycle(now - 60 * (i + 1), mode="dhw", is_transient=1) for i in range(5)]
        + [_cycle(now - 60 * (i + 11), mode="dhw", is_transient=0) for i in range(2)]
    )
    coord = _FakeCoord(cyc, {"dhw_pendulum_cycles_per_hour": 3})
    assert _is_dhw_pendulum(_snap(), coord) is False


def test_dhw_pendulum_heating_does_not_trigger():
    """5 real heating -> 0 DHW -> False."""
    now = _now()
    cyc = [_cycle(now - 60 * (i + 1), mode="heating", is_transient=0) for i in range(5)]
    coord = _FakeCoord(cyc, {"dhw_pendulum_cycles_per_hour": 3})
    assert _is_dhw_pendulum(_snap(), coord) is False


def test_dhw_pendulum_cooling_defrost_do_not_trigger():
    """5 real cooling + 5 real defrost -> 0 DHW -> False."""
    now = _now()
    cyc = (
        [_cycle(now - 60 * (i + 1), mode="cooling", is_transient=0) for i in range(5)]
        + [_cycle(now - 60 * (i + 11), mode="defrost", is_transient=0) for i in range(5)]
    )
    coord = _FakeCoord(cyc, {"dhw_pendulum_cycles_per_hour": 3})
    assert _is_dhw_pendulum(_snap(), coord) is False


def test_dhw_pendulum_legacy_missing_field_counts_as_real():
    """3 legacy DHW records (no is_transient) -> 3 >= 3 -> True."""
    now = _now()
    cyc = [_cycle(now - 60 * (i + 1), mode="dhw", include_key=False) for i in range(3)]
    coord = _FakeCoord(cyc, {"dhw_pendulum_cycles_per_hour": 3})
    assert _is_dhw_pendulum(_snap(), coord) is True
