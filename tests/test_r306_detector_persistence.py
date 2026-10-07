"""R306: CycleDetector state persistence across HA reloads."""
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
    MAX_RESUME_GAP_S,
    CycleDetector,
)


def _attrs() -> dict:
    return {
        ATTR_WATER_PUMP_OPERATION: "ON",
        ATTR_INV_FREQUENCY_RPS: 20.0,
        ATTR_IU_OPERATION_MODE: OP_MODE_HEATING,
        ATTR_LEAVING_WATER_AFTER_BUH: 35.0,
        ATTR_INLET_WATER_R4T: 30.0,
    }


def _running() -> CycleDetector:
    d = CycleDetector()
    d.update(_attrs(), now=1000.0)
    assert d.state == STATE_RUNNING
    return d


def test_to_dict_idle_returns_empty() -> None:
    assert CycleDetector().to_dict() == {}


def test_to_dict_running_contains_state() -> None:
    payload = _running().to_dict()
    assert payload["state"] == STATE_RUNNING
    assert payload["start_ts"] == 1000.0
    assert payload["mode"] == "heating"
    assert payload["rps_samples"] == [20.0]
    assert payload["dt_samples"] == [5.0]


def test_restore_from_dict_valid() -> None:
    payload = _running().to_dict()
    d = CycleDetector()
    d.restore_from_dict(payload, now=1100.0)
    assert d.state == STATE_RUNNING
    assert d.snapshot()["start_ts"] == 1000.0
    assert d.snapshot()["mode"] == "heating"


def test_restore_from_dict_stale_gap() -> None:
    payload = _running().to_dict()
    d = CycleDetector()
    d.restore_from_dict(payload, now=1000.0 + MAX_RESUME_GAP_S + 1)
    assert d.state == STATE_IDLE


def test_restore_from_dict_invalid_payload() -> None:
    for bad in (None, {}, "x", 1, [], {"state": STATE_RUNNING},
                {"state": STATE_RUNNING, "start_ts": "bad"}):
        d = CycleDetector()
        d.restore_from_dict(bad, now=1000.0)
        assert d.state == STATE_IDLE


def test_restore_roundtrip_samples() -> None:
    d1 = _running()
    d1.update(_attrs(), now=1030.0)
    d1.update(_attrs(), now=1060.0)
    d2 = CycleDetector()
    d2.restore_from_dict(d1.to_dict(), now=1090.0)
    assert d2.to_dict()["rps_samples"] == d1.to_dict()["rps_samples"]
