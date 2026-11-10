"""Batch 31b tests: water pump guard + thermal_kW + VECTOR_LEN 12."""

from __future__ import annotations

from custom_components.daikin_cycle_ml.const import (
    ATTR_FLOW_SENSOR,
    ATTR_INLET_WATER_R4T,
    ATTR_INV_FREQUENCY_RPS,
    ATTR_IU_OPERATION_MODE,
    ATTR_LEAVING_WATER_AFTER_BUH,
    ATTR_OUTDOOR_AIR_R1T,
    ATTR_WATER_PUMP_OPERATION,
    OP_MODE_HEATING,
)
from custom_components.daikin_cycle_ml.engine.cycle_detector import CycleDetector
from custom_components.daikin_cycle_ml.ml.features import (
    FEATURE_NAMES,
    VECTOR_LEN,
    extract_feature_vector,
)


def _attrs(rps=40.0, lwt=40.0, inlet=35.0, flow=12.0, pump=True):
    return {
        ATTR_INV_FREQUENCY_RPS: rps,
        ATTR_IU_OPERATION_MODE: OP_MODE_HEATING,
        ATTR_LEAVING_WATER_AFTER_BUH: lwt,
        ATTR_INLET_WATER_R4T: inlet,
        ATTR_OUTDOOR_AIR_R1T: 8.0,
        ATTR_FLOW_SENSOR: flow,
        ATTR_WATER_PUMP_OPERATION: pump,
    }


# ---- water pump guard ----


def test_pump_off_with_compressor_off_blocks_cycle_start():
    """R307 guard: pump=OFF + compressor OFF must not open a cycle.

    R772 (#285): previously this test used rps=40 (compressor ON) and
    passed only because the pump=OFF early-return ran BEFORE
    detect_compressor_on(). Now that the check is `pump=OFF AND not on`,
    we must set the compressor explicitly off (rps=0, flow=0).
    """
    det = CycleDetector({})
    det.update(_attrs(rps=0.0, flow=0.0, pump=False), now=1000.0)
    assert det.snapshot()["state"] == "idle"


def test_pump_off_with_compressor_on_opens_cycle():
    """R772 (#285): pump=OFF + compressor ON must open a cycle.

    Real-world: DHW tank warmup (3-way valve diverts pump) or
    ESPAltherma template drift (stale pump attribute while compressor
    still runs at RPS>threshold).
    """
    det = CycleDetector({})
    det.update(_attrs(pump=False), now=1000.0)  # rps=40 default → ON
    assert det.snapshot()["state"] == "running"


def test_pump_missing_allows_cycle_start():
    det = CycleDetector({})
    attrs = _attrs()
    del attrs[ATTR_WATER_PUMP_OPERATION]
    det.update(attrs, now=1000.0)
    assert det.snapshot()["state"] == "running"


def test_pump_on_allows_cycle_start():
    det = CycleDetector({})
    det.update(_attrs(pump=True), now=1000.0)
    assert det.snapshot()["state"] == "running"


def test_pump_off_during_running_ignores_sample():
    det = CycleDetector({})
    det.update(_attrs(pump=True), now=1000.0)
    det.update(_attrs(pump=True), now=1100.0)
    assert det.snapshot()["state"] == "running"
    # pump off → sample ignored, cycle stays running
    det.update(_attrs(pump=False), now=1200.0)
    assert det.snapshot()["state"] == "running"


# ---- thermal_kW ----


def test_thermal_kw_avg_in_record():
    """Realistic cadence: update every 60s for 10 min = 10 samples.

    v1.19.7 fix #12 requires MIN_THERMAL_SAMPLES samples for thermal_kw_avg.
    The old body only had 2 update() calls in an 800s cycle -- a test
    shortcut that hid the reality that a real 800s cycle would have ~26
    samples. Restoring realistic cadence exercises the same flow_dt path
    while satisfying the sample floor.
    """
    det = CycleDetector({})
    # 10 samples at 60s intervals (matches production 30s tick densified)
    for t in range(1000, 1601, 60):
        det.update(_attrs(flow=10.0, lwt=40.0, inlet=35.0), now=float(t))
    rec = det.update({ATTR_INV_FREQUENCY_RPS: 0.0, ATTR_WATER_PUMP_OPERATION: True}, now=1700.0)
    assert rec is not None
    assert "thermal_kw_avg" in rec
    # 10/60 * 4.18 * 5 = 3.483
    assert 3.4 < rec["thermal_kw_avg"] < 3.6


def test_thermal_kw_none_when_no_flow():
    """Missing flow sensor: thermal_kw_avg must be None even with enough samples.

    v1.19.7 fix #12 added MIN_THERMAL_SAMPLES=3 floor. Prior body had only
    2 samples, so post-fix this test would pass via the sample floor, not
    via the flow-sensor absence -- a false positive. Realistic cadence
    ensures the no-flow path is actually exercised.
    """
    det = CycleDetector({})
    attrs = _attrs()
    del attrs[ATTR_FLOW_SENSOR]
    for t in range(1000, 1601, 60):
        det.update(attrs, now=float(t))
    rec = det.update({ATTR_INV_FREQUENCY_RPS: 0.0, ATTR_WATER_PUMP_OPERATION: True}, now=1700.0)
    assert rec is not None
    assert rec["thermal_kw_avg"] is None


# ---- feature vector ----


def test_vector_len_is_12():
    assert VECTOR_LEN == 12


def test_feature_names_includes_thermal_kw():
    assert "thermal_kw_avg" in FEATURE_NAMES
    assert FEATURE_NAMES[-1] == "thermal_kw_avg"


def test_extract_vector_uses_thermal_kw():
    rec = {"duration_s": 100, "dT_max": 5.0, "rps_max": 40.0}
    v = extract_feature_vector(rec, thermal_kw_avg=3.5)
    assert len(v) == 12
    assert v[-1] == 3.5


def test_extract_vector_default_zero():
    rec = {"duration_s": 100}
    v = extract_feature_vector(rec)
    assert v[-1] == 0.0
