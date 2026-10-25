"""v1.12.5 #144: reverse split dhw->heating/cooling in _should_split."""
from custom_components.daikin_cycle_ml.engine.cycle_detector import (
    CycleDetector,
    MODE_DEBOUNCE_S,
    MAX_CYCLE_DURATION_S,
    STATE_RUNNING,
    STATE_IDLE,
)

VALVE_KEY = "3way valve(On:DHW_Off:Space)"


def _attrs_heating():
    return {"I/U operation mode": "Heating", "Operation Mode": "Heating"}


def _attrs_cooling():
    return {"I/U operation mode": "Cooling", "Operation Mode": "Cooling"}


def _attrs_dhw_valve_off():
    return {
        "I/U operation mode": "Heating + DHW",
        "Operation Mode": "Heating",
        VALVE_KEY: "OFF",
    }


def _attrs_dhw_valve_on():
    return {
        "I/U operation mode": "Heating + DHW",
        "Operation Mode": "Heating",
        VALVE_KEY: "ON",
    }


def _attrs_unknown():
    return {"I/U operation mode": "Unknown"}


def _mk_running(mode="dhw", start_ts=1000.0):
    d = CycleDetector(options={})
    d._state = STATE_RUNNING
    d._start_ts = start_ts
    d._mode = mode
    d._rps_samples = [30.0]
    d._dt_samples = [5.0]
    d._outdoor_samples = [10.0]
    d._thermal_kw_samples = [4.0]
    d._buh_used = False
    d._defrost_used = False
    d._pending_mode = None
    d._pending_mode_since = 0.0
    return d


def test_reverse_split_dhw_to_heating_after_debounce():
    d = _mk_running("dhw")
    t0 = 1000.0
    assert d._should_split(_attrs_heating(), t0) is False
    assert d._pending_mode == "heating"
    assert d._should_split(_attrs_heating(), t0 + MODE_DEBOUNCE_S + 1) is True


def test_reverse_split_dhw_to_heating_not_immediate():
    d = _mk_running("dhw")
    t0 = 1000.0
    d._should_split(_attrs_heating(), t0)
    assert d._should_split(_attrs_heating(), t0 + 30.0) is False
    assert d._should_split(_attrs_heating(), t0 + MODE_DEBOUNCE_S - 0.5) is False


def test_reverse_split_dhw_to_cooling_after_debounce():
    d = _mk_running("dhw")
    t0 = 1000.0
    d._should_split(_attrs_cooling(), t0)
    assert d._pending_mode == "cooling"
    assert d._should_split(_attrs_cooling(), t0 + MODE_DEBOUNCE_S + 1) is True


def test_reverse_split_clears_pending_on_unknown():
    d = _mk_running("dhw")
    t0 = 1000.0
    d._should_split(_attrs_heating(), t0)
    assert d._pending_mode == "heating"
    assert d._should_split(_attrs_unknown(), t0 + 30.0) is False
    assert d._pending_mode is None
    assert d._pending_mode_since == 0.0


def test_reverse_split_not_fired_when_dhw_stays_dhw():
    d = _mk_running("dhw")
    t0 = 1000.0
    for dt in (0, 30, 61, 300):
        assert d._should_split(_attrs_dhw_valve_on(), t0 + dt) is False


def test_existing_heating_to_dhw_split_valve_on_fires_at_valve_debounce():
    from custom_components.daikin_cycle_ml.engine.cycle_detector import VALVE_DEBOUNCE_S
    d = _mk_running("heating")
    t0 = 1000.0
    assert d._should_split(_attrs_dhw_valve_on(), t0) is False
    assert d._pending_mode == "dhw"
    assert d._should_split(_attrs_dhw_valve_on(), t0 + VALVE_DEBOUNCE_S + 1) is True


def test_reverse_split_full_restore_recovery():
    """Acceptance for #144: stuck-dhw restore recovers to heating."""
    d = _mk_running("dhw", start_ts=1000.0)
    t0 = 1005.0
    assert d._should_split(_attrs_heating(), t0) is False
    t1 = t0 + MODE_DEBOUNCE_S + 5
    assert d._should_split(_attrs_heating(), t1) is True

