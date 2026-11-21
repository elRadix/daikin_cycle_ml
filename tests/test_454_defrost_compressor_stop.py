"""Discussion #454: the compressor stops inside a defrost; the run goes on.

EDLA09D3V3 monobloc (ESPAltherma v1), reporter's history of 2026-11-21:
Defrost Operation ON 09:31-09:40, INV frequency 0 rps 09:33-09:35, back
to 58 rps after. The detector closed the run on the first 0-rps sample:
a low-quality cycle, a short-run alert and a new run "since 09:34".
"""
from __future__ import annotations

from custom_components.daikin_cycle_ml.engine.cycle_detector import (
    DEFROST_HOLD_MAX_S,
    CycleDetector,
)
from tests.test_435_no_dhw_detection import ATTRS_454


def _sample(rps: float, defrost: str = "OFF") -> dict:
    return {**ATTRS_454, "INV frequency (rps)": rps, "Defrost Operation": defrost}


def _run(det: CycleDetector, samples: list[tuple[float, dict]]) -> list[dict]:
    closed = []
    for t, attrs in samples:
        rec = det.update(attrs, t)
        if rec:
            closed.append(rec)
    return closed


def test_compressor_stop_inside_defrost_keeps_the_run():
    det = CycleDetector({}, dhw_present=True)
    t0 = 1_000_000.0
    samples = [(t0 + i * 30, _sample(40)) for i in range(80)]           # 40 min heating
    t = samples[-1][0]
    samples += [(t + 30 * (i + 1), _sample(58, "ON")) for i in range(4)]  # defrost starts
    t = samples[-1][0]
    samples += [(t + 30 * (i + 1), _sample(0, "ON")) for i in range(4)]   # 2 min at 0 rps
    t = samples[-1][0]
    samples += [(t + 30 * (i + 1), _sample(58, "ON")) for i in range(10)]
    t = samples[-1][0]
    samples += [(t + 30 * (i + 1), _sample(30)) for i in range(40)]       # heating again
    assert _run(det, samples) == []
    assert det.state == "running"
    rec = det.partial_record(samples[-1][0])
    assert rec["duration_s"] >= 60 * 60 and rec["defrost_used"] is True


def test_stop_without_defrost_still_ends_the_run():
    det = CycleDetector({}, dhw_present=True)
    t0 = 2_000_000.0
    closed = _run(det, [(t0 + i * 30, _sample(40)) for i in range(40)] + [(t0 + 40 * 30, _sample(0))])
    assert len(closed) == 1 and det.state == "idle"


def test_defrost_hold_is_bounded():
    det = CycleDetector({}, dhw_present=True)
    t0 = 3_000_000.0
    samples = [(t0 + i * 30, _sample(40)) for i in range(20)]
    t = samples[-1][0]
    n = int(DEFROST_HOLD_MAX_S / 30) + 2
    samples += [(t + 30 * (i + 1), _sample(0, "ON")) for i in range(n)]
    closed = _run(det, samples)
    assert len(closed) == 1 and det.state == "idle"


def test_hold_resets_when_the_compressor_runs_again():
    det = CycleDetector({}, dhw_present=True)
    t0 = 4_000_000.0
    samples = [(t0 + i * 30, _sample(40)) for i in range(20)]
    for _ in range(3):  # three defrosts in one long run, each with a 2 min stop
        t = samples[-1][0]
        samples += [(t + 30 * (i + 1), _sample(0, "ON")) for i in range(4)]
        t = samples[-1][0]
        samples += [(t + 30 * (i + 1), _sample(40)) for i in range(60)]
    assert _run(det, samples) == [] and det.state == "running"
