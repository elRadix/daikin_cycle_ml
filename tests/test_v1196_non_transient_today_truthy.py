"""v1.19.6 FASE 5C: non_transient_today truthy bug + hydration end-to-end.

FASE 5A fixed cycles_in_window / cycles_in_window_mode with _is_transient_int.
FASE 5C fixes the remaining truthy check in non_transient_today() which
feeds _is_pendulum_daily via _is_pendulum_daily -> non_transient_today().

Also covers hydration (reboot) scenarios: corrupt is_transient in DB
must not crash sensors after hydrate_from_rows + _is_pendulum_* evaluation.
"""

from __future__ import annotations

import datetime as _dt
import time

from freezegun import freeze_time

from custom_components.daikin_cycle_ml.binary_sensor import (
    _is_pendulum_daily,
    _is_short_off,
    _is_short_run,
)
from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
from custom_components.daikin_cycle_ml.storage.store import CycleStore

FREEZE = "2026-11-03 14:00:00"


def _cycle(start_ts, *, mode="heating", is_transient=None, include_key=True):
    r = {
        "start_ts": start_ts, "end_ts": start_ts + 60, "duration_s": 60,
        "mode": mode, "dT_max": 5.0, "rps_max": 30,
        "quality_score": 80,
    }
    if include_key:
        r["is_transient"] = is_transient
    return r


def _today_noon():
    return _dt.datetime.combine(_dt.date.today(), _dt.time(12, 0)).timestamp()


# ============================================================================
# non_transient_today truthy bug (RED on HEAD after FASE 5A)
# ============================================================================


@freeze_time(FREEZE)
def test_non_transient_today_string_zero_included():
    """RED: is_transient='0' must be treated as 0 -> INCLUDED (real)."""
    now = time.time()
    s = CycleStore()
    s.add_cycle(_cycle(now - 60, is_transient="0"))
    assert len(s.non_transient_today(now)) == 1


@freeze_time(FREEZE)
def test_non_transient_today_string_false_included():
    """RED: is_transient='false' -> unknown -> INCLUDED per FASE 5A policy."""
    now = time.time()
    s = CycleStore()
    s.add_cycle(_cycle(now - 60, is_transient="false"))
    assert len(s.non_transient_today(now)) == 1


@freeze_time(FREEZE)
def test_non_transient_today_string_x_included():
    """RED: is_transient='x' -> unknown -> INCLUDED per FASE 5A policy."""
    now = time.time()
    s = CycleStore()
    s.add_cycle(_cycle(now - 60, is_transient="x"))
    assert len(s.non_transient_today(now)) == 1


@freeze_time(FREEZE)
def test_non_transient_today_int_1_excluded():
    """GUARD: is_transient=1 -> EXCLUDED (real transient)."""
    now = time.time()
    s = CycleStore()
    s.add_cycle(_cycle(now - 60, is_transient=1))
    assert len(s.non_transient_today(now)) == 0


@freeze_time(FREEZE)
def test_non_transient_today_bool_true_excluded():
    """GUARD: is_transient=True -> EXCLUDED."""
    now = time.time()
    s = CycleStore()
    s.add_cycle(_cycle(now - 60, is_transient=True))
    assert len(s.non_transient_today(now)) == 0


@freeze_time(FREEZE)
def test_non_transient_today_missing_key_included():
    """GUARD: missing is_transient -> INCLUDED (backward compat)."""
    now = time.time()
    s = CycleStore()
    s.add_cycle(_cycle(now - 60, include_key=False))
    assert len(s.non_transient_today(now)) == 1


# ============================================================================
# Hydration end-to-end (reboot lifecycle)
# ============================================================================


@freeze_time(FREEZE)
def test_hydration_corrupt_is_transient_end_to_end_pendulum_daily():
    """RED: 45 cycles with corrupt is_transient="0" (string) -> pendulum_daily must be True.

    The truthy-check bug EXCLUDES corrupt strings, causing false NEGATIVES.
    Setup: 45 legitimate cycles whose is_transient field was stringified
    (DB-import, manual SQL fix). Pre-fix: `not "0"` = False -> all excluded
    -> 0 >= 40 = False (WRONG, false negative). Post-fix: _is_transient_int("0")
    == 0 -> all included -> 45 >= 40 = True (correct).
    """
    now = time.time()
    s = CycleStore()
    rows = [
        {"start_ts": now - 60 * (i + 1), "mode": "heating",
         "quality_score": 80, "is_transient": "0"}
        for i in range(45)
    ]
    s.hydrate_from_rows(rows)

    class _Coord:
        store = s
        options = {"pendulum_cycles_per_day": 40}

    assert _is_pendulum_daily(DataSnapshot(), _Coord()) is True


@freeze_time(FREEZE)
def test_hydration_corrupt_is_transient_no_crash():
    """RED: hydration of corrupt records must not crash pendulum_daily."""
    now = time.time()
    s = CycleStore()
    rows = [
        {"start_ts": now - 60, "mode": "heating",
         "quality_score": 80, "is_transient": "corrupt-string"},
        {"start_ts": now - 120, "mode": "heating",
         "quality_score": 80, "is_transient": [1, 2]},
    ]
    s.hydrate_from_rows(rows)

    class _Coord:
        store = s
        options = {"pendulum_cycles_per_day": 40}

    # Must not crash; correctness is tested above.
    assert _is_pendulum_daily(DataSnapshot(), _Coord()) is False


# ============================================================================
# Reboot mid-cycle (no completed cycle after hydration)
# ============================================================================


def test_reboot_mid_cycle_short_run_no_last_cycle():
    """Reboot mid-cycle: store empty, coord mid-cycle. short_run -> False."""
    class _Coord:
        store = CycleStore()
        options = {"short_run_threshold_min": 20}

    snap = DataSnapshot()
    snap.mode = "heating"
    snap.cycle_start_ts = time.time() - 300  # cycle started 5min ago
    assert _is_short_run(snap, _Coord()) is False


def test_reboot_mid_cycle_short_off_no_last_cycle():
    """Reboot mid-cycle: store empty. short_off -> False."""
    class _Coord:
        store = CycleStore()
        options = {"short_off_threshold_min": 5}

    snap = DataSnapshot()
    snap.mode = "heating"
    snap.cycle_start_ts = time.time() - 300
    assert _is_short_off(snap, _Coord()) is False


def test_reboot_mid_cycle_uses_last_completed_from_hydration():
    """Reboot mid-cycle but DB has completed cycles -> last_cycle() used."""
    now = time.time()
    s = CycleStore()
    s.hydrate_from_rows([
        {"start_ts": now - 1800, "end_ts": now - 1200, "duration_s": 300,
         "mode": "heating", "off_s": 100, "quality_score": 80, "is_transient": 0},
    ])

    class _Coord:
        store = s
        options = {"short_run_threshold_min": 20, "short_off_threshold_min": 5}

    snap = DataSnapshot()
    snap.mode = "heating"
    snap.cycle_start_ts = now - 300  # new cycle started, last_cycle still old
    # Last cycle was 5min (300s), threshold 20min=1200s -> short_run True
    assert _is_short_run(snap, _Coord()) is True
    # off_s was 100s, threshold 5min=300s -> 100 < 300 -> short_off True
    assert _is_short_off(snap, _Coord()) is True
