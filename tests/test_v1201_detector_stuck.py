"""Reproduction tests for cycle detector stuck-IDLE bug (prod 2026-11-07 20:25).

Background: prod-1 evidence shows detector stuck in IDLE for 11h48m after a
transient cycle close, while compressor ran continuously (rps=26, flow=15.5,
11 cop_samples/hour). No cycle opened until reload at 08:13.

These are sequence-based state-machine guards (R722). If they PASS, the
isolated CycleDetector logic is correct and the bug is coordinator-level
(attrs went bad). If they FAIL, the state machine itself is broken.

Evidence: R634 - prod-1 DB gap 2026-11-07 20:25:52 -> 2026-11-08 08:13:30
"""
from __future__ import annotations

import pytest

from custom_components.daikin_cycle_ml.engine.cycle_detector import (
    CycleDetector,
    STATE_IDLE,
    STATE_RUNNING,
)


def _attrs_on(rps: int = 30, flow: float = 15.5, cop: float = 5.5) -> dict:
    return {
        "INV frequency (rps)": rps,
        "Flow sensor (l/min)": flow,
        "Leaving water temp. before BUH (R1T)": 32.0,
        "Inlet water temp.(R4T)": 29.0,
        "Outdoor air temp.(R1T)": 7.0,
        "Operation Mode": "Heating",
        "Thermostat ON/OFF": "ON",
        "BE COP": cop,
    }


def _attrs_off() -> dict:
    return {
        "INV frequency (rps)": 0,
        "Flow sensor (l/min)": 0,
        "Leaving water temp. before BUH (R1T)": 32.0,
        "Inlet water temp.(R4T)": 32.0,
        "Outdoor air temp.(R1T)": 7.0,
        "Operation Mode": "Heating",
        "Thermostat ON/OFF": "OFF",
        "BE COP": 0.0,
    }


def test_detector_reopens_after_single_transient_close():
    """Prod sequence: normal close -> transient reopen -> transient close -> SUSTAINED.

    Reproduces prod-1: cycle 317 (normal) -> 320 (transient) -> STUCK 11h48m.
    """
    det = CycleDetector()

    # 1. Normal cycle opens
    det.update(_attrs_on(), now=1000.0)
    assert det.state == STATE_RUNNING

    # 2. Run for 5 min
    for t in range(1030, 1300, 30):
        det.update(_attrs_on(), now=float(t))

    # 3. Close normally
    rec = det.update(_attrs_off(), now=1300.0)
    assert rec is not None, "normal cycle must close"
    assert det.state == STATE_IDLE

    # 4. Reopen 30s later (matches prod: 317 close -> 320 open at +30s)
    det.update(_attrs_on(), now=1330.0)
    assert det.state == STATE_RUNNING

    # 5. Close as transient 60s later
    rec2 = det.update(_attrs_off(), now=1390.0)
    assert rec2 is not None, "transient cycle must close"
    assert det.state == STATE_IDLE

    # 6. SUSTAINED run 5 min later (matches prod 02:21 + rps=26)
    det.update(_attrs_on(rps=26), now=1690.0)
    assert det.state == STATE_RUNNING, (
        "REGRESSION (prod 2026-11-07 20:25): detector stuck IDLE "
        "after transient close despite compressor running"
    )


def test_detector_reopens_after_transient_cascade():
    """3 consecutive transient closes must eventually reopen."""
    det = CycleDetector()
    det.update(_attrs_on(), now=1000.0)
    det.update(_attrs_on(), now=1300.0)
    det.update(_attrs_off(), now=1310.0)
    assert det.state == STATE_IDLE

    for i in range(3):
        t_on = 1330.0 + i * 120
        t_off = t_on + 60
        det.update(_attrs_on(), now=t_on)
        det.update(_attrs_off(), now=t_off)

    det.update(_attrs_on(), now=1800.0)
    assert det.state == STATE_RUNNING, "detector must reopen after transient cascade"


def test_detector_reopens_with_rps_only():
    """Reopen with only rps present (other attrs missing)."""
    det = CycleDetector()
    det.update(_attrs_on(), now=1000.0)
    det.update(_attrs_off(), now=1010.0)

    sparse_attrs = {"INV frequency (rps)": 30}
    det.update(sparse_attrs, now=1040.0)
    assert det.state == STATE_RUNNING, (
        "detector must reopen on rps > threshold even without flow/cop"
    )
