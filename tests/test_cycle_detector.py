"""Tests for engine.cycle_detector."""
from __future__ import annotations

from custom_components.daikin_cycle_ml.const import (
    ATTR_BUH_STEP1,
    ATTR_DEFROST_OPERATION,
    ATTR_INLET_WATER_R4T,
    ATTR_INV_FREQUENCY_RPS,
    ATTR_IU_OPERATION_MODE,
    ATTR_LEAVING_WATER_AFTER_BUH,
    ATTR_OPERATION_MODE,
    ATTR_OUTDOOR_AIR_R1T,
    OP_MODE_COOLING,
    OP_MODE_DHW,
    OP_MODE_FAN_ONLY,
    OP_MODE_HEATING,
    STATE_IDLE,
    STATE_RUNNING,
)
from custom_components.daikin_cycle_ml.engine.cycle_detector import (
    CycleDetector,
    classify_mode,
    detect_compressor_on,
)


def _on(rps=30.0, mode=OP_MODE_HEATING, leaving=35.0, inlet=30.0, outdoor=10.0):
    return {
        ATTR_INV_FREQUENCY_RPS: rps,
        ATTR_IU_OPERATION_MODE: mode,
        ATTR_LEAVING_WATER_AFTER_BUH: leaving,
        ATTR_INLET_WATER_R4T: inlet,
        ATTR_OUTDOOR_AIR_R1T: outdoor,
    }


def test_detect_compressor_on_rps_above_threshold():
    assert detect_compressor_on({ATTR_INV_FREQUENCY_RPS: 30}) is True


def test_detect_compressor_on_rps_below_threshold_no_power():
    assert detect_compressor_on({ATTR_INV_FREQUENCY_RPS: 0}) is False


def test_detect_compressor_on_power_fallback():
    assert detect_compressor_on({ATTR_INV_FREQUENCY_RPS: 0}, power_w=500.0) is True
    assert detect_compressor_on({ATTR_INV_FREQUENCY_RPS: 0}, power_w=50.0) is False


def test_detect_compressor_on_custom_thresholds():
    opts = {"compressor_rps_threshold": 10, "fallback_power_threshold_w": 1000}
    assert detect_compressor_on({ATTR_INV_FREQUENCY_RPS: 8}, opts) is False
    assert detect_compressor_on({ATTR_INV_FREQUENCY_RPS: 15}, opts) is True


def test_classify_mode_iu_primary():
    assert classify_mode({ATTR_IU_OPERATION_MODE: OP_MODE_HEATING}) == "heating"
    assert classify_mode({ATTR_IU_OPERATION_MODE: OP_MODE_COOLING}) == "cooling"
    assert classify_mode({ATTR_IU_OPERATION_MODE: OP_MODE_DHW}) == "dhw"


def test_classify_mode_iu_beats_operation_mode():
    attrs = {
        ATTR_IU_OPERATION_MODE: OP_MODE_HEATING,
        ATTR_OPERATION_MODE: OP_MODE_FAN_ONLY,
    }
    assert classify_mode(attrs) == "heating"


def test_classify_mode_fallback_to_operation_mode():
    assert classify_mode({ATTR_OPERATION_MODE: OP_MODE_DHW}) == "dhw"


def test_classify_mode_unknown():
    assert classify_mode({}) == "unknown"
    assert classify_mode({ATTR_IU_OPERATION_MODE: OP_MODE_FAN_ONLY}) == "unknown"


def test_detector_starts_idle():
    d = CycleDetector()
    assert d.state == STATE_IDLE
    assert d.update(_on(rps=0), now=100.0) is None
    assert d.state == STATE_IDLE


def test_detector_full_cycle_emits_record():
    d = CycleDetector()
    assert d.update(_on(rps=30, leaving=35, inlet=30), now=100.0) is None
    assert d.state == STATE_RUNNING
    assert d.update(_on(rps=35, leaving=38, inlet=30), now=130.0) is None
    assert d.state == STATE_RUNNING

    record = d.update({ATTR_INV_FREQUENCY_RPS: 0}, now=200.0)
    assert record is not None
    assert d.state == STATE_IDLE
    assert record["start_ts"] == 100.0
    assert record["end_ts"] == 200.0
    assert record["duration_s"] == 100
    assert record["mode"] == "heating"
    assert record["rps_max"] == 35.0
    assert record["rps_avg"] == 32.5
    assert record["dT_max"] == 8.0
    assert record["outdoor_temp"] == 10.0


def test_detector_tracks_buh_and_defrost():
    d = CycleDetector()
    a1 = _on(rps=30)
    d.update(a1, now=0.0)
    a2 = {**a1, ATTR_BUH_STEP1: True, ATTR_DEFROST_OPERATION: True}
    d.update(a2, now=10.0)
    record = d.update({ATTR_INV_FREQUENCY_RPS: 0}, now=20.0)
    assert record["buh_used"] is True
    assert record["defrost_used"] is True


def test_detector_snapshot_reflects_state():
    d = CycleDetector()
    s0 = d.snapshot()
    assert s0["state"] == STATE_IDLE
    assert s0["start_ts"] is None

    d.update(_on(rps=30), now=100.0)
    s1 = d.snapshot()
    assert s1["state"] == STATE_RUNNING
    assert s1["start_ts"] == 100.0
    assert s1["mode"] == "heating"
    assert s1["rps_samples"] == 1


def test_detector_clock_skew_ignored():
    d = CycleDetector()
    d.update(_on(rps=30), now=100.0)
    assert d.update(_on(rps=30), now=50.0) is None
    assert d.state == STATE_RUNNING
