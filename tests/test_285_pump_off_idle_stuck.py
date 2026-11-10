"""Issue #285: detector stuck in IDLE when pump reports OFF while
compressor is still running.

Root cause: R307's unconditional early-return
    `if _pump_is_off(pump) and self._state == STATE_IDLE: return None`
ran BEFORE `detect_compressor_on()`. Two legitimate cases report
pump=OFF while the compressor produces heat:

  1. DHW tank warmup — 3-way valve diverts the circulation pump to the
     tank, but the compressor keeps running (RPS>thr, flow+COP evidence).
  2. ESPAltherma template drift — stale `Water pump operation` value
     while RPS/flow/COP still say "on".

Prod-1 evidence (2026-11-07 20:25 → 2026-11-08 08:13): 11h48m IDLE gap,
68 cop_samples inside the gap all with flow=17+ and cop=6+, RPS=26.
Detector was never woken up.

Fix R772: compute `on = detect_compressor_on(...)` first, and only skip
the sample when pump=OFF AND compressor is off.
"""
from __future__ import annotations

from custom_components.daikin_cycle_ml.engine.cycle_detector import (
    STATE_IDLE,
    STATE_RUNNING,
    CycleDetector,
)


def _dhw_warmup_attrs() -> dict:
    """Realistic DHW tank warmup: 3-way valve diverts pump, compressor runs."""
    return {
        "INV frequency (rps)": 45,
        "Flow sensor (l/min)": 0.5,
        "Operation Mode": "DHW",
        "I/U operation mode": "DHW",
        "Water pump operation": "OFF",
        "COP": 4.5,
    }


def _dhw_off_attrs() -> dict:
    """Genuinely off: pump OFF, compressor OFF, nothing to detect."""
    return {
        "INV frequency (rps)": 0,
        "Flow sensor (l/min)": 0.0,
        "Operation Mode": "DHW",
        "I/U operation mode": "DHW",
        "Water pump operation": "OFF",
        "COP": 0.0,
    }


def test_285_pump_off_compressor_on_opens_cycle():
    """Regression: pump=OFF + compressor ON must open a cycle (#285)."""
    det = CycleDetector()
    # Simulate 30 min of DHW warmup with pump reported OFF
    for i in range(60):
        det.update(_dhw_warmup_attrs(), now=1000.0 + i * 30)
    assert det.state == STATE_RUNNING, (
        "Issue #285 regression: pump=OFF + compressor ON must open a cycle "
        "(DHW tank warmup or template drift)"
    )


def test_285_pump_off_compressor_off_still_skips():
    """Guard: pump=OFF + compressor OFF must still skip (R307 behaviour)."""
    det = CycleDetector()
    for i in range(10):
        det.update(_dhw_off_attrs(), now=1000.0 + i * 30)
    assert det.state == STATE_IDLE, (
        "R307 regression: pump=OFF + compressor OFF must NOT open a cycle"
    )


def test_285_pump_off_compressor_on_rps_only_opens_cycle():
    """Sparse attrs: only RPS>threshold with pump=OFF must still open."""
    det = CycleDetector()
    attrs = {
        "INV frequency (rps)": 30,
        "Water pump operation": "OFF",
    }
    det.update(attrs, now=1000.0)
    assert det.state == STATE_RUNNING, (
        "RPS-only evidence + pump=OFF must open cycle (#285)"
    )


def test_285_pump_off_idle_no_clock_skew_regression():
    """Clock-skew guard must still fire before on-computation."""
    det = CycleDetector()
    det.update(_dhw_warmup_attrs(), now=2000.0)
    assert det.state == STATE_RUNNING
    # Backwards time must not close nor open
    det.update(_dhw_warmup_attrs(), now=1900.0)
    assert det.state == STATE_RUNNING
