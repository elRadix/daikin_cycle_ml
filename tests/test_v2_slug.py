"""Tests for ESPAltherma v2 slug helpers (issue #281, R684 + R640).

R684 matrix: every REQUIRED_ATTRIBUTE -> known v2 slug.
R640 fuzz: hypothesis >=200 cases to prove ASCII-safe invariant.
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from custom_components.daikin_cycle_ml.const import (
    ATTR_3WAY_VALVE,
    ATTR_BUH_STEP1,
    ATTR_BUH_STEP2,
    ATTR_DEFROST_OPERATION,
    ATTR_FLOW_SENSOR,
    ATTR_INLET_WATER_R4T,
    ATTR_IU_OPERATION_MODE,
    ATTR_LEAVING_WATER_AFTER_BUH,
    ATTR_LW_SETPOINT,
    ATTR_OPERATION_MODE,
    ATTR_OUTDOOR_AIR_R1T,
    ATTR_WATER_PUMP_OPERATION,
    REQUIRED_ATTRIBUTES,
)
from custom_components.daikin_cycle_ml.engine.espaltherma_v2.slug import (
    DEFAULT_PREFIX,
    entity_id_for,
    make_json_key,
)

# ---------- R684: every required attribute maps to the known slug ----------


@pytest.mark.parametrize(
    ("label", "expected_slug"),
    [
        (ATTR_OPERATION_MODE, "operation_mode"),
        (ATTR_IU_OPERATION_MODE, "iu_operation_mode"),
        (ATTR_3WAY_VALVE, "3way_valveondhwoffspace"),
        (ATTR_DEFROST_OPERATION, "defrost_operation"),
        (ATTR_LEAVING_WATER_AFTER_BUH, "leaving_water_temp_after_buh_r2t"),
        (ATTR_INLET_WATER_R4T, "inlet_water_tempr4t"),
        (ATTR_OUTDOOR_AIR_R1T, "outdoor_air_tempr1t"),
        (ATTR_FLOW_SENSOR, "flow_sensor_lmin"),
        (ATTR_WATER_PUMP_OPERATION, "water_pump_operation"),
        (ATTR_BUH_STEP1, "buh_step1"),
        (ATTR_BUH_STEP2, "buh_step2"),
        (ATTR_LW_SETPOINT, "lw_setpoint_main"),
    ],
)
def test_required_attribute_slug(label: str, expected_slug: str) -> None:
    assert make_json_key(label) == expected_slug


def test_all_required_attributes_are_covered() -> None:
    """Every REQUIRED_ATTRIBUTE must have an explicit expectation above."""
    covered = {
        ATTR_OPERATION_MODE, ATTR_IU_OPERATION_MODE, ATTR_3WAY_VALVE,
        ATTR_DEFROST_OPERATION, ATTR_LEAVING_WATER_AFTER_BUH,
        ATTR_INLET_WATER_R4T, ATTR_OUTDOOR_AIR_R1T, ATTR_FLOW_SENSOR,
        ATTR_WATER_PUMP_OPERATION, ATTR_BUH_STEP1, ATTR_BUH_STEP2,
        ATTR_LW_SETPOINT,
    }
    missing = set(REQUIRED_ATTRIBUTES) - covered
    assert not missing, f"REQUIRED_ATTRIBUTES without slug expectation: {missing}"


# ---------- Quirk-specific tests ----------


@pytest.mark.parametrize(
    ("label", "expected", "why"),
    [
        ("Outdoor air temp.(R1T)", "outdoor_air_tempr1t",
         "period+paren dropped, no separator before r1t"),
        ("Inlet water temp.(R4T)", "inlet_water_tempr4t",
         "period+paren dropped, no separator before r4t"),
        ("Flow sensor (l/min)", "flow_sensor_lmin",
         "slash+paren dropped, no separator before lmin"),
        ("3way valve(On:DHW_Off:Space)", "3way_valveondhwoffspace",
         "all punctuation and `_` dropped"),
        ("I/U operation mode", "iu_operation_mode",
         "slash dropped, I/U lowercased"),
        ("A_B", "ab",
         "`_` is dropped (not alnum, not space)"),
        ("a.b-c", "abc",
         "period and hyphen dropped"),
        ("a  b", "a__b",
         "two spaces -> two underscores"),
    ],
)
def test_quirks(label: str, expected: str, why: str) -> None:
    assert make_json_key(label) == expected, why


# ---------- Edge cases ----------


def test_empty_string_returns_empty() -> None:
    assert make_json_key("") == ""


def test_only_spaces_returns_underscores() -> None:
    assert make_json_key("   ") == "___"


def test_unicode_letters_dropped() -> None:
    """C++ std::isalnum is ASCII-only; non-ASCII chars must be dropped."""
    assert make_json_key("café") == "caf"
    assert make_json_key("αβγ") == ""
    assert make_json_key("Ä") == ""


def test_all_ascii_uppercase_lowered() -> None:
    assert make_json_key("ABC XYZ") == "abc_xyz"


# ---------- entity_id_for ----------


def test_entity_id_for_default_prefix() -> None:
    assert (
        entity_id_for("Operation Mode")
        == "sensor.espaltherma_operation_mode"
    )


def test_entity_id_for_custom_prefix() -> None:
    assert (
        entity_id_for("Operation Mode", prefix="sensor.custom_")
        == "sensor.custom_operation_mode"
    )


def test_default_prefix_constant() -> None:
    assert DEFAULT_PREFIX == "sensor.espaltherma_"


# ---------- R640 fuzz: 200 cases, invariant = ASCII + no spaces/uppercase ----------


@given(
    s=st.text(
        alphabet=st.characters(min_codepoint=32, max_codepoint=126),
        max_size=40,
    )
)
@settings(max_examples=200, deadline=None)
def test_make_json_key_fuzz_invariant(s: str) -> None:
    """R676: 200 cases; result must be ASCII alnum+underscore only, lowercase."""
    out = make_json_key(s)
    assert isinstance(out, str)
    for ch in out:
        assert ch.isascii()
        assert ch.isalnum() or ch == "_"
        if ch.isalpha():
            assert ch.islower()
