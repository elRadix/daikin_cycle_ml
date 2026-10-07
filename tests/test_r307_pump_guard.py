"""R307: pump-off in RUNNING state is soft, not a hard stop."""
from __future__ import annotations

from custom_components.daikin_cycle_ml.const import (
    ATTR_INLET_WATER_R4T,
    ATTR_INV_FREQUENCY_RPS,
    ATTR_IU_OPERATION_MODE,
    ATTR_LEAVING_WATER_AFTER_BUH,
    ATTR_WATER_PUMP_OPERATION,
    OP_MODE_HEATING,
    STATE_IDLE,
    STATE_RUNNING,
)
from custom_components.daikin_cycle_ml.engine.cycle_detector import (
    PUMP_OFF_MAX_SAMPLES,
    CycleDetector,
)


def _attrs(pump: bool, rps: float) -> dict:
    return {
        ATTR_WATER_PUMP_OPERATION: pump,
        ATTR_INV_FREQUENCY_RPS: rps,
        ATTR_IU_OPERATION_MODE: OP_MODE_HEATING,
        ATTR_LEAVING_WATER_AFTER_BUH: 35.0,
        ATTR_INLET_WATER_R4T: 30.0,
    }


def test_idle_pump_off_rps_zero_still_skips() -> None:
    d = CycleDetector()
    assert d.update(_attrs(False, 0.0), now=1000.0) is None
    assert d.state == STATE_IDLE


def test_idle_pump_off_rps_high_still_skips() -> None:
    d = CycleDetector()
    assert d.update(_attrs(False, 20.0), now=1000.0) is None
    assert d.state == STATE_IDLE


def test_running_pump_off_with_compressor_keeps_running() -> None:
    d = CycleDetector()
    d.update(_attrs(True, 20.0), now=1000.0)
    assert d.state == STATE_RUNNING
    assert d.update(_attrs(False, 20.0), now=1030.0) is None
    assert d.state == STATE_RUNNING


def test_running_pump_off_sustained_closes_after_max() -> None:
    d = CycleDetector()
    d.update(_attrs(True, 20.0), now=1000.0)
    record = None
    for i in range(1, PUMP_OFF_MAX_SAMPLES + 1):
        record = d.update(_attrs(False, 20.0), now=1000.0 + 30.0 * i)
    assert record is not None
    assert d.state == STATE_IDLE


def test_running_pump_off_compressor_stops_closes_immediately() -> None:
    d = CycleDetector()
    d.update(_attrs(True, 20.0), now=1000.0)
    record = d.update(_attrs(False, 0.0), now=1030.0)
    assert record is not None
    assert d.state == STATE_IDLE


def test_running_pump_off_then_pump_on_resets_counter() -> None:
    d = CycleDetector()
    d.update(_attrs(True, 20.0), now=1000.0)
    d.update(_attrs(False, 20.0), now=1030.0)
    d.update(_attrs(False, 20.0), now=1060.0)
    assert d._pump_off_count == 2
    d.update(_attrs(True, 20.0), now=1090.0)
    assert d._pump_off_count == 0
