"""v1.19.6 scope B: _build_alert_context cyc_today excludes transient.

Companion to FIX-3 (_is_pendulum_daily -> non_transient_today). Without
this fix, the alert message shows all cycles (incl. transients) while the
trigger counts only real cycles -> user-facing inconsistency.
"""

from __future__ import annotations

import datetime as _dt
import time
from collections import deque

import pytest
from freezegun import freeze_time

from custom_components.daikin_cycle_ml.binary_sensor import _is_pendulum_daily
from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    DataSnapshot,
)
from custom_components.daikin_cycle_ml.storage.store import CycleStore

FREEZE = "2026-11-03 14:00:00"


def _mk_coord(cycles, options=None):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = options or {}
    c._setpoint_history = deque()
    c._last_setpoint = None
    c.store = CycleStore()
    for rec in cycles:
        c.store.add_cycle(rec)
    return c


def _cycle(start_ts, *, mode="heating", is_transient=0, include_key=True):
    rec = {
        "start_ts": start_ts, "end_ts": start_ts + 60, "duration_s": 60,
        "mode": mode, "dT_max": 5.0, "dT_avg": 3.0, "rps_max": 30,
        "rps_avg": 20.0, "outdoor_temp": 10.0, "buh_used": 0, "defrost_used": 0,
    }
    if include_key:
        rec["is_transient"] = is_transient
    return rec


def _today_noon():
    return _dt.datetime.combine(_dt.date.today(), _dt.time(12, 0)).timestamp()


@freeze_time(FREEZE)
def test_build_alert_context_cyc_today_excludes_transient():
    """10 real + 5 transient -> cyc_today must be 10, not 15."""
    noon = _today_noon()
    cycles = (
        [_cycle(noon - 60 * (i + 1), is_transient=0) for i in range(10)]
        + [_cycle(noon - 60 * (i + 11), is_transient=1) for i in range(5)]
    )
    c = _mk_coord(cycles)
    ctx = c._build_alert_context(DataSnapshot())
    assert ctx["pendulum"]["cycles_today"] == 10


@freeze_time(FREEZE)
def test_build_alert_context_cyc_today_missing_field_counts_as_real():
    """Legacy records (no is_transient) count as real."""
    noon = _today_noon()
    cycles = [_cycle(noon - 60 * (i + 1), include_key=False) for i in range(10)]
    c = _mk_coord(cycles)
    ctx = c._build_alert_context(DataSnapshot())
    assert ctx["pendulum"]["cycles_today"] == 10


@freeze_time(FREEZE)
def test_build_alert_context_cyc_today_still_counts_real():
    """Guard: only real cycles -> count unchanged."""
    noon = _today_noon()
    cycles = [_cycle(noon - 60 * (i + 1), is_transient=0) for i in range(10)]
    c = _mk_coord(cycles)
    ctx = c._build_alert_context(DataSnapshot())
    assert ctx["pendulum"]["cycles_today"] == 10


@freeze_time(FREEZE)
def test_pendulum_daily_trigger_matches_alert_message():
    """Optie B invariant: trigger count == alert message count.

    30 real + 10 transient. threshold=40.
    Trigger: _is_pendulum_daily(coord) == False (30 < 40).
    Message: cyc_today == 30 (not 40). Before fix message showed 40.
    """
    noon = _today_noon()
    cycles = (
        [_cycle(noon - 60 * (i + 1), is_transient=0) for i in range(30)]
        + [_cycle(noon - 60 * (i + 31), is_transient=1) for i in range(10)]
    )
    c = _mk_coord(cycles, {"pendulum_cycles_per_day": 40})
    trigger = _is_pendulum_daily(DataSnapshot(), c)
    message_count = c._build_alert_context(DataSnapshot())["pendulum"]["cycles_today"]
    assert trigger is False
    assert message_count == 30
