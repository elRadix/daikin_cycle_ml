"""Tests for v1.7.2 L1: MAX_CYCLE_DURATION_S hard cap (R315)."""
from __future__ import annotations

import logging

import pytest

from custom_components.daikin_cycle_ml.const import (
    ATTR_INV_FREQUENCY_RPS,
    ATTR_WATER_PUMP_OPERATION,
    MAX_CYCLE_DURATION_S,
    STATE_IDLE,
    STATE_RUNNING,
)
from custom_components.daikin_cycle_ml.engine.cycle_detector import CycleDetector


def _running_attrs(rps: float = 30.0, pump: str = "ON") -> dict:
    """Minimal attrs that make detect_compressor_on() return True."""
    return {
        ATTR_INV_FREQUENCY_RPS: rps,
        ATTR_WATER_PUMP_OPERATION: pump,
    }


def _open_cycle(det: CycleDetector, t0: float = 1000.0) -> None:
    det.update(_running_attrs(), now=t0, power_w=None)
    assert det.state == STATE_RUNNING


# -- Constant -------------------------------------------------------------

def test_max_cycle_duration_constant_value() -> None:
    assert MAX_CYCLE_DURATION_S == 4 * 3600.0
    assert MAX_CYCLE_DURATION_S == 14400.0


# -- Branch: state==RUNNING, start_ts set, over cap -> force close ---------

def test_running_over_cap_forces_close() -> None:
    det = CycleDetector()
    t0 = 1000.0
    _open_cycle(det, t0)
    t1 = t0 + MAX_CYCLE_DURATION_S + 1.0
    result = det.update(_running_attrs(), now=t1, power_w=None)
    assert result is not None
    assert result["duration_s"] == int(t1 - t0)
    assert det.state == STATE_IDLE


def test_hard_cap_force_close_emits_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    det = CycleDetector()
    t0 = 1000.0
    _open_cycle(det, t0)
    with caplog.at_level(logging.WARNING):
        det.update(
            _running_attrs(),
            now=t0 + MAX_CYCLE_DURATION_S + 1.0,
            power_w=None,
        )
    assert any("exceeded hard cap" in r.getMessage() for r in caplog.records)


def test_hard_cap_resets_state_to_idle() -> None:
    det = CycleDetector()
    t0 = 1000.0
    _open_cycle(det, t0)
    det.update(
        _running_attrs(),
        now=t0 + MAX_CYCLE_DURATION_S + 1.0,
        power_w=None,
    )
    assert det.state == STATE_IDLE
    snap = det.snapshot()
    assert snap.get("state") == STATE_IDLE


# -- Branch: state==RUNNING, start_ts set, at / under cap -> no close ------

def test_running_at_exactly_cap_does_not_close() -> None:
    """Boundary: '>' means exactly at cap does NOT force close."""
    det = CycleDetector()
    t0 = 1000.0
    _open_cycle(det, t0)
    result = det.update(
        _running_attrs(),
        now=t0 + MAX_CYCLE_DURATION_S,
        power_w=None,
    )
    assert result is None
    assert det.state == STATE_RUNNING


def test_running_under_cap_does_not_close() -> None:
    det = CycleDetector()
    t0 = 1000.0
    _open_cycle(det, t0)
    result = det.update(_running_attrs(), now=t0 + 3600.0, power_w=None)
    assert result is None
    assert det.state == STATE_RUNNING


# -- Branch: state==IDLE (short-circuit on outer if) ----------------------

def test_hard_cap_skipped_in_idle() -> None:
    det = CycleDetector()
    assert det.state == STATE_IDLE
    result = det.update(_running_attrs(), now=1000.0, power_w=None)
    # Cycle just opened; hard cap branch was skipped because state==IDLE
    assert result is None
    assert det.state == STATE_RUNNING


# -- Branch: state==RUNNING but _start_ts is None (defensive) -------------

def test_hard_cap_skips_when_start_ts_missing() -> None:
    """Defensive: RUNNING with _start_ts=None must not crash on cap check."""
    det = CycleDetector()
    _open_cycle(det, 1000.0)
    det._start_ts = None  # type: ignore[assignment]
    result = det.update(_running_attrs(), now=1e12, power_w=None)
    assert result is None
    assert det.state == STATE_RUNNING
