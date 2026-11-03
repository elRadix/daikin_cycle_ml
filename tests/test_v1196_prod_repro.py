"""v1.19.6 FASE 6: production incident reproduction tests.

Each test reproduces a REAL false positive from Prod 1 DB audit
(2026-11-03, session v124.0). Data is verbatim from that audit — no
synthetic thresholds, no invented cycle counts.

Audit summary (SQL: 1h-window flip simulation on Prod 1, 178 windows scanned):
  2026-10-07 17:35  heat 3/4  dhw 0/0  all 3/4  old=(True,False,False) new=(False,False,False)
  2026-10-16 09:55  heat 0/0  dhw 1/3  all 1/3  old=(False,True,False) new=(False,False,False)
  2026-10-16 10:24  heat 1/1  dhw 1/3  all 2/4  old=(False,True,False) new=(False,False,False)
  2026-10-26 12:48  heat 1/4  dhw 0/0  all 1/4  old=(True,False,False) new=(False,False,False)
Legend: sensor tuple = (pendulum_hourly, dhw_pendulum, high_cycle_rate)

v1.19.5 behavior (formula, no transient filter):
  pendulum_hourly = (all_n - dhw_n) >= 4
  dhw_pendulum    = dhw_n >= 3
v1.19.6 behavior (mode-strict + transient-aware):
  pendulum_hourly = heating_real >= 4
  dhw_pendulum    = dhw_real >= 3
"""

from __future__ import annotations

import time

from custom_components.daikin_cycle_ml.binary_sensor import (
    _is_dhw_pendulum,
    _is_pendulum_hourly,
)
from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
from custom_components.daikin_cycle_ml.storage.store import CycleStore


def _cycle(start_ts, *, mode="heating", is_transient=0):
    return {
        "start_ts": start_ts, "end_ts": start_ts + 60,
        "duration_s": 60, "mode": mode,
        "dT_max": 5.0, "dT_avg": 3.0, "rps_max": 30, "rps_avg": 20.0,
        "outdoor_temp": 10.0, "buh_used": 0, "defrost_used": 0,
        "is_transient": is_transient,
    }


class _FakeCoord:
    def __init__(self, cycles, options=None):
        self.store = CycleStore()
        for c in cycles:
            self.store.add_cycle(c)
        self.options = options or {"pendulum_cycles_per_hour": 4,
                                   "dhw_pendulum_cycles_per_hour": 3}


def _snap():
    return DataSnapshot()


# ============================================================================
# Incident data — verbatim from Prod 1 audit
# ============================================================================


def _incident_2026_10_07_1735():
    """3 real heating + 1 transient heating (1h window)."""
    now = time.time()
    return [
        _cycle(now - 60 * 1, mode="heating", is_transient=0),
        _cycle(now - 60 * 2, mode="heating", is_transient=0),
        _cycle(now - 60 * 3, mode="heating", is_transient=0),
        _cycle(now - 60 * 4, mode="heating", is_transient=1),
    ]


def _incident_2026_10_16_0955():
    """0 heating, 1 real DHW + 2 transient DHW."""
    now = time.time()
    return [
        _cycle(now - 60 * 1, mode="dhw", is_transient=0),
        _cycle(now - 60 * 2, mode="dhw", is_transient=1),
        _cycle(now - 60 * 3, mode="dhw", is_transient=1),
    ]


def _incident_2026_10_16_1024():
    """1 real heating, 1 real DHW + 2 transient DHW."""
    now = time.time()
    return [
        _cycle(now - 60 * 1, mode="dhw", is_transient=0),
        _cycle(now - 60 * 2, mode="dhw", is_transient=1),
        _cycle(now - 60 * 3, mode="dhw", is_transient=1),
        _cycle(now - 60 * 4, mode="heating", is_transient=0),
    ]


def _incident_2026_10_26_1248():
    """1 real heating + 3 transient heating."""
    now = time.time()
    return [
        _cycle(now - 60 * 1, mode="heating", is_transient=0),
        _cycle(now - 60 * 2, mode="heating", is_transient=1),
        _cycle(now - 60 * 3, mode="heating", is_transient=1),
        _cycle(now - 60 * 4, mode="heating", is_transient=1),
    ]


# ============================================================================
# Test 1: 2026-10-07 17:35 — pendulum_hourly false positive
# ============================================================================


def test_incident_2026_10_07_pendulum_hourly_false_positive():
    """REPRO: 3 real heat + 1 trans heat, threshold 4.

    v1.19.5: (all_n - dhw_n) = (4 - 0) = 4 >= 4 -> True (FALSE POSITIVE)
    v1.19.6: heating_real = 3 < 4 -> False (correct)
    """
    coord = _FakeCoord(_incident_2026_10_07_1735())
    assert _is_pendulum_hourly(_snap(), coord) is False


# ============================================================================
# Test 2: 2026-10-16 09:55 — dhw_pendulum false positive
# ============================================================================


def test_incident_2026_10_16_0955_dhw_pendulum_false_positive():
    """REPRO: 1 real DHW + 2 trans DHW, threshold 3.

    v1.19.5: dhw_n = 3 >= 3 -> True (FALSE POSITIVE)
    v1.19.6: dhw_real = 1 < 3 -> False (correct)
    """
    coord = _FakeCoord(_incident_2026_10_16_0955())
    assert _is_dhw_pendulum(_snap(), coord) is False


# ============================================================================
# Test 3: 2026-10-16 10:24 — dhw_pendulum false positive (2e keer die dag)
# ============================================================================


def test_incident_2026_10_16_1024_dhw_pendulum_false_positive():
    """REPRO: 1 real DHW + 2 trans DHW (+1 real heating irrelevant), threshold 3.

    v1.19.5: dhw_n = 3 >= 3 -> True (FALSE POSITIVE)
    v1.19.6: dhw_real = 1 < 3 -> False (correct)
    """
    coord = _FakeCoord(_incident_2026_10_16_1024())
    assert _is_dhw_pendulum(_snap(), coord) is False


# ============================================================================
# Test 4: 2026-10-26 12:48 — pendulum_hourly false positive
# ============================================================================


def test_incident_2026_10_26_pendulum_hourly_false_positive():
    """REPRO: 1 real heat + 3 trans heat, threshold 4.

    v1.19.5: (all_n - dhw_n) = (4 - 0) = 4 >= 4 -> True (FALSE POSITIVE)
    v1.19.6: heating_real = 1 < 4 -> False (correct)
    """
    coord = _FakeCoord(_incident_2026_10_26_1248())
    assert _is_pendulum_hourly(_snap(), coord) is False


# ============================================================================
# Test 5: Summary — alle 4 incidenten in één tabel-check
# ============================================================================


def test_all_4_production_incidents_now_silent():
    """SUMMARY: all 4 historical false positives must be silent on v1.19.6.

    This is the end-of-run proof that the fix resolves every real DB
    false-positive documented in the 2026-11-03 audit.
    """
    cases = [
        ("2026-10-07 17:35 pendulum_hourly",
         _incident_2026_10_07_1735(), "pendulum_hourly"),
        ("2026-10-16 09:55 dhw_pendulum",
         _incident_2026_10_16_0955(), "dhw_pendulum"),
        ("2026-10-16 10:24 dhw_pendulum",
         _incident_2026_10_16_1024(), "dhw_pendulum"),
        ("2026-10-26 12:48 pendulum_hourly",
         _incident_2026_10_26_1248(), "pendulum_hourly"),
    ]
    for label, cycles, sensor in cases:
        coord = _FakeCoord(cycles)
        if sensor == "pendulum_hourly":
            result = _is_pendulum_hourly(_snap(), coord)
        elif sensor == "dhw_pendulum":
            result = _is_dhw_pendulum(_snap(), coord)
        else:
            raise AssertionError(f"unexpected sensor {sensor}")
        assert result is False, f"{label}: expected False, got {result}"
