"""v1.12.3 compound-mode tests (issue #116)."""
from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.daikin_cycle_ml.binary_sensor import (
    _attr_contains_mode,
    _is_dhw_active,
)
from custom_components.daikin_cycle_ml.const import (
    ATTR_3WAY_VALVE,
    ATTR_INV_FREQUENCY_RPS,
    ATTR_IU_OPERATION_MODE,
    ATTR_OPERATION_MODE,
    OP_MODE_DHW,
    OP_MODE_HEATING,
)
from custom_components.daikin_cycle_ml.engine.cycle_detector import (
    MODE_DEBOUNCE_S,
    STATE_IDLE,
    STATE_RUNNING,
    VALVE_DEBOUNCE_S,
    CycleDetector,
    classify_mode,
)


def _rps(attrs: dict, rps: float = 30.0) -> dict:
    """Add rps above threshold so compressor-on gate passes."""
    return {**attrs, ATTR_INV_FREQUENCY_RPS: rps}


# --- classify_mode (6 tests) ---

def test_classify_heating_only():
    assert classify_mode({ATTR_IU_OPERATION_MODE: OP_MODE_HEATING}) == "heating"


def test_classify_dhw_only():
    assert classify_mode({ATTR_IU_OPERATION_MODE: OP_MODE_DHW}) == "dhw"


def test_classify_heating_plus_dhw():
    assert classify_mode({ATTR_IU_OPERATION_MODE: "Heating + DHW"}) == "dhw"


def test_classify_cooling_plus_dhw():
    assert classify_mode({ATTR_IU_OPERATION_MODE: "Cooling + DHW"}) == "dhw"


def test_classify_slash_separator():
    assert classify_mode({ATTR_IU_OPERATION_MODE: "Heating/DHW"}) == "dhw"


def test_classify_fallback_operation_mode():
    assert classify_mode({ATTR_OPERATION_MODE: OP_MODE_HEATING}) == "heating"


# --- splitter (4 tests) ---

def test_splitter_mode_transition_debounce():
    d = CycleDetector()
    d.update(_rps({ATTR_IU_OPERATION_MODE: OP_MODE_HEATING}), now=100.0)
    assert d.state == STATE_RUNNING
    t_transition = 100.0 + MODE_DEBOUNCE_S
    d.update(_rps({ATTR_IU_OPERATION_MODE: "Heating + DHW"}), now=t_transition)
    assert d.state == STATE_RUNNING
    t_split = t_transition + MODE_DEBOUNCE_S
    record = d.update(_rps({ATTR_IU_OPERATION_MODE: "Heating + DHW"}), now=t_split)
    assert record is not None
    assert record["mode"] == "heating"
    assert record["start_ts"] == 100.0
    assert record["end_ts"] == t_split
    assert d.state == STATE_RUNNING
    assert d.snapshot()["mode"] == "dhw"


def test_splitter_valve_shortens_debounce():
    d = CycleDetector()
    d.update(_rps({ATTR_IU_OPERATION_MODE: OP_MODE_HEATING}), now=100.0)
    t_transition = 100.0 + VALVE_DEBOUNCE_S
    d.update(_rps({ATTR_IU_OPERATION_MODE: "Heating + DHW", ATTR_3WAY_VALVE: "ON"}), now=t_transition)
    assert d.state == STATE_RUNNING
    t_split = t_transition + VALVE_DEBOUNCE_S
    record = d.update(_rps({ATTR_IU_OPERATION_MODE: "Heating + DHW", ATTR_3WAY_VALVE: "ON"}), now=t_split)
    assert record is not None
    assert record["mode"] == "heating"
    assert d.snapshot()["mode"] == "dhw"


def test_splitter_valve_only_no_mode_transition_no_split():
    d = CycleDetector()
    d.update(_rps({ATTR_IU_OPERATION_MODE: OP_MODE_HEATING, ATTR_3WAY_VALVE: "OFF"}), now=100.0)
    d.update(_rps({ATTR_IU_OPERATION_MODE: OP_MODE_HEATING, ATTR_3WAY_VALVE: "ON"}), now=200.0)
    d.update(_rps({ATTR_IU_OPERATION_MODE: OP_MODE_HEATING, ATTR_3WAY_VALVE: "ON"}), now=400.0)
    assert d.state == STATE_RUNNING
    assert d.snapshot()["mode"] == "heating"


def test_splitter_idle_opens_dhw_directly():
    d = CycleDetector()
    assert d.state == STATE_IDLE
    d.update(_rps({ATTR_IU_OPERATION_MODE: "Heating + DHW"}), now=100.0)
    assert d.state == STATE_RUNNING
    assert d.snapshot()["mode"] == "dhw"


# --- _attr_contains_mode + _is_dhw_active (4 tests) ---

def test_attr_contains_mode_compound_dhw():
    attrs = {ATTR_IU_OPERATION_MODE: "Heating + DHW"}
    assert _attr_contains_mode(attrs, ATTR_IU_OPERATION_MODE, "dhw") is True


def test_attr_contains_mode_heating_only_false():
    attrs = {ATTR_IU_OPERATION_MODE: "Heating"}
    assert _attr_contains_mode(attrs, ATTR_IU_OPERATION_MODE, "dhw") is False


def test_is_dhw_active_compound_running():
    s = MagicMock()
    s.state = "running"
    s.attrs = {ATTR_IU_OPERATION_MODE: "Heating + DHW"}
    assert _is_dhw_active(s, MagicMock()) is True


def test_is_dhw_active_heating_only_false():
    s = MagicMock()
    s.state = "running"
    s.attrs = {ATTR_IU_OPERATION_MODE: "Heating"}
    assert _is_dhw_active(s, MagicMock()) is False


# --- persistence (3 tests) ---

def test_to_dict_includes_pending_fields():
    d = CycleDetector()
    d.update(_rps({ATTR_IU_OPERATION_MODE: OP_MODE_HEATING}), now=100.0)
    d.update(_rps({ATTR_IU_OPERATION_MODE: "Heating + DHW"}), now=130.0)
    snap = d.to_dict()
    assert snap["pending_mode"] == "dhw"
    assert snap["pending_mode_since"] == 130.0


def test_restore_roundtrip_preserves_pending_and_split():
    d1 = CycleDetector()
    d1.update(_rps({ATTR_IU_OPERATION_MODE: OP_MODE_HEATING}), now=100.0)
    d1.update(_rps({ATTR_IU_OPERATION_MODE: "Heating + DHW"}), now=130.0)
    payload = d1.to_dict()
    d2 = CycleDetector()
    d2.restore_from_dict(payload, now=140.0)
    assert d2.state == STATE_RUNNING
    assert d2._pending_mode == "dhw"
    assert d2._pending_mode_since == 130.0
    record = d2.update(_rps({ATTR_IU_OPERATION_MODE: "Heating + DHW"}), now=200.0)
    assert record is not None
    assert record["mode"] == "heating"
    assert d2.snapshot()["mode"] == "dhw"


def test_restore_old_payload_missing_pending_fields():
    old_payload = {
        "state": "running",
        "start_ts": 100.0,
        "mode": "heating",
        "rps_samples": [30.0],
        "dt_samples": [],
        "outdoor_samples": [],
        "buh_used": False,
        "defrost_used": False,
        "thermal_kw_samples": [],
    }
    d = CycleDetector()
    d.restore_from_dict(old_payload, now=140.0)
    assert d.state == STATE_RUNNING
    assert d._pending_mode is None
    assert d._pending_mode_since == 0.0


# --- coverage completeness (5 tests, branch-level) ---

def test_parse_valve_edge_cases():
    from custom_components.daikin_cycle_ml.engine.cycle_detector import _parse_valve
    assert _parse_valve({ATTR_3WAY_VALVE: "garbage"}) is None
    assert _parse_valve({ATTR_3WAY_VALVE: "on"}) == "ON"
    assert _parse_valve({ATTR_3WAY_VALVE: "off"}) == "OFF"
    assert _parse_valve("not-a-mapping") is None


def test_mode_tokens_empty_and_repeated_separators():
    from custom_components.daikin_cycle_ml.engine.cycle_detector import _mode_tokens
    assert _mode_tokens("") == set()
    assert _mode_tokens(" + ") == set()
    assert _mode_tokens("Heating + + DHW") == {"heating", "dhw"}


def test_should_split_already_dhw_returns_false():
    d = CycleDetector()
    d.update(_rps({ATTR_IU_OPERATION_MODE: "Heating + DHW"}), now=100.0)
    assert d.snapshot()["mode"] == "dhw"
    d.update(_rps({ATTR_IU_OPERATION_MODE: "Heating + DHW"}), now=200.0)
    assert d.state == STATE_RUNNING
    assert d.snapshot()["mode"] == "dhw"


def test_should_split_before_debounce_elapsed():
    d = CycleDetector()
    d.update(_rps({ATTR_IU_OPERATION_MODE: OP_MODE_HEATING}), now=100.0)
    d.update(_rps({ATTR_IU_OPERATION_MODE: "Heating + DHW"}), now=130.0)
    d.update(_rps({ATTR_IU_OPERATION_MODE: "Heating + DHW"}), now=160.0)
    assert d.state == STATE_RUNNING
    assert d.snapshot()["mode"] == "heating"


def test_attr_contains_mode_non_str_and_empty_tokens():
    assert _attr_contains_mode({ATTR_IU_OPERATION_MODE: 42}, ATTR_IU_OPERATION_MODE, "dhw") is False
    assert _attr_contains_mode({ATTR_IU_OPERATION_MODE: ""}, ATTR_IU_OPERATION_MODE, "dhw") is False
    attrs = {ATTR_IU_OPERATION_MODE: "Heating + + DHW"}
    assert _attr_contains_mode(attrs, ATTR_IU_OPERATION_MODE, "dhw") is True
