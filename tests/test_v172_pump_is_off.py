"""Tests for v1.7.2 L2: _pump_is_off() helper (R316, issue #49).

Covers all value shapes that attribute_reader._normalize() may produce,
and validates that issue #49's root-cause path (string 'OFF' while
detector is RUNNING) now closes the cycle immediately.
"""
from __future__ import annotations

import pytest

from custom_components.daikin_cycle_ml.const import (
    ATTR_INV_FREQUENCY_RPS,
    ATTR_WATER_PUMP_OPERATION,
    STATE_IDLE,
    STATE_RUNNING,
)
from custom_components.daikin_cycle_ml.engine.cycle_detector import (
    CycleDetector,
    _pump_is_off,
)


# ── Helper unit tests: parametrised over all off/on/unknown inputs ────────

@pytest.mark.parametrize(
    "value",
    [
        False,
        "OFF", "off", "Off", " OFF ",
        "FALSE", "false",
        "NO", "no",
        "",
    ],
)
def test_pump_is_off_recognised_off_forms(value) -> None:
    assert _pump_is_off(value) is True


@pytest.mark.parametrize(
    "value",
    [
        True,
        "ON", "on", "On",
        "YES", "TRUE",
        "1", "0", "maybe",
        0, 0.0, 1, 1.5, 30.0,      # numerics are unknown, not off
        ["list"], {"dict": 1},
    ],
)
def test_pump_is_off_recognised_on_or_unknown(value) -> None:
    assert _pump_is_off(value) is False


def test_pump_is_off_none_is_unknown_not_off() -> None:
    """Missing attr != reported off; None must return False."""
    assert _pump_is_off(None) is False


# ── Integration: issue #49 scenario closes immediately ───────────────────

def _running_attrs(rps: float, pump) -> dict:
    return {
        ATTR_INV_FREQUENCY_RPS: rps,
        ATTR_WATER_PUMP_OPERATION: pump,
    }


def _open_cycle(det: CycleDetector, t0: float = 1000.0) -> None:
    det.update(
        {ATTR_INV_FREQUENCY_RPS: 30.0, ATTR_WATER_PUMP_OPERATION: "ON"},
        now=t0,
        power_w=None,
    )
    assert det.state == STATE_RUNNING


@pytest.mark.parametrize("pump_off_form", ["OFF", "off", False, ""])
def test_running_string_pump_off_closes_cycle(pump_off_form) -> None:
    """Issue #49 regression: any explicit off-form must close the cycle
    when the compressor is also off."""
    det = CycleDetector()
    t0 = 1000.0
    _open_cycle(det, t0)
    # Compressor off (rps=0) + pump off (string) => close
    result = det.update(
        _running_attrs(rps=0.0, pump=pump_off_form),
        now=t0 + 60.0,
        power_w=None,
    )
    assert result is not None
    assert det.state == STATE_IDLE


def test_idle_string_pump_off_skips() -> None:
    """IDLE + pump='OFF' must skip entirely (no cycle open)."""
    det = CycleDetector()
    assert det.state == STATE_IDLE
    result = det.update(
        _running_attrs(rps=30.0, pump="OFF"),
        now=1000.0,
        power_w=None,
    )
    assert result is None
    assert det.state == STATE_IDLE


def test_idle_none_pump_does_not_skip() -> None:
    """Missing pump attr must NOT trigger the IDLE skip (preserve legacy)."""
    det = CycleDetector()
    assert det.state == STATE_IDLE
    result = det.update(
        _running_attrs(rps=30.0, pump=None),
        now=1000.0,
        power_w=None,
    )
    # Cycle opens because pump=None is not treated as off
    assert result is None
    assert det.state == STATE_RUNNING
