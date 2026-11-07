"""Per-attribute matrix for ESPAltherma v2 native support (issue #281).

User requirement: "all espaltherma sensors to be tested to ensure it works
the same as with attributes they must co-exist".

Proves for all 22 ATTR_* sensors used downstream:
1. `_normalize(raw)` returns expected canonical value
2. `read(mono_state)` returns expected (monolithic path)
3. `resolve_attrs(v2_hass)` returns expected (v2 path)
4. Both paths produce IDENTICAL values (coexistence safety, R634)

Note on ambiguity: "0"/"1" map to bool via _coerce_bool BEFORE float,
so use "15"/"35"/"4.5" for numeric test values.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.daikin_cycle_ml.const import (
    ATTR_3WAY_VALVE, ATTR_BE_COP, ATTR_BOILER_DHW_DEMAND,
    ATTR_BOILER_OPERATION_DEMAND, ATTR_BUH_STEP1, ATTR_BUH_STEP2,
    ATTR_COP, ATTR_DEFROST_OPERATION, ATTR_DHW_TANK_TEMP,
    ATTR_FLOW_SENSOR, ATTR_HYBRID_OP_MODE, ATTR_INDOOR_AMBIENT_R1T,
    ATTR_INLET_WATER_R4T, ATTR_INV_FREQUENCY_2_RPS,
    ATTR_INV_FREQUENCY_RPS, ATTR_IU_OPERATION_MODE,
    ATTR_LEAVING_WATER_AFTER_BUH, ATTR_LW_SETPOINT,
    ATTR_OPERATION_MODE, ATTR_OUTDOOR_AIR_R1T,
    ATTR_TARGET_COND_TEMP, ATTR_WATER_PUMP_OPERATION,
    DEFAULT_INDIVIDUAL_PREFIX,
)
from custom_components.daikin_cycle_ml.engine.attribute_reader import (
    _normalize, read,
)
from custom_components.daikin_cycle_ml.engine.espaltherma_v2.resolver import (
    resolve_attrs,
)
from custom_components.daikin_cycle_ml.engine.espaltherma_v2.slug import (
    make_json_key,
)

# 22 ATTR_* constants x (raw, expected-normalized)
SENSOR_MATRIX: list[tuple[str, str, float | bool | str]] = [
    # REQUIRED 12
    (ATTR_OPERATION_MODE, "Heating", "Heating"),
    (ATTR_IU_OPERATION_MODE, "Heating", "Heating"),
    (ATTR_3WAY_VALVE, "Off:Space", "Off:Space"),
    (ATTR_DEFROST_OPERATION, "OFF", False),
    (ATTR_LEAVING_WATER_AFTER_BUH, "35.0", 35.0),
    (ATTR_INLET_WATER_R4T, "30.0", 30.0),
    (ATTR_OUTDOOR_AIR_R1T, "8.5", 8.5),
    (ATTR_FLOW_SENSOR, "15.2", 15.2),
    (ATTR_WATER_PUMP_OPERATION, "ON", True),
    (ATTR_BUH_STEP1, "OFF", False),
    (ATTR_BUH_STEP2, "OFF", False),
    (ATTR_LW_SETPOINT, "40.0", 40.0),
    # COP / cycle
    (ATTR_COP, "4.5", 4.5),
    (ATTR_INV_FREQUENCY_RPS, "35", 35.0),
    (ATTR_INV_FREQUENCY_2_RPS, "15", 15.0),
    # Water / setpoint
    (ATTR_DHW_TANK_TEMP, "55.0", 55.0),
    (ATTR_INDOOR_AMBIENT_R1T, "21.5", 21.5),
    (ATTR_TARGET_COND_TEMP, "38.0", 38.0),
    # Hybrid
    (ATTR_BOILER_OPERATION_DEMAND, "OFF", False),
    (ATTR_BOILER_DHW_DEMAND, "OFF", False),
    (ATTR_HYBRID_OP_MODE, "H/P only", "H/P only"),
    (ATTR_BE_COP, "1.2", 1.2),
    # v1.20.0 #281: ESPAltherma Stats synthetic labels (v2 power-ups)
    ("Stats: Heat output (kW)", "4.5", 4.5),
    ("Stats: Electrical input estimated (kW)", "0.81", 0.81),
    ("Stats: Electricalinput estimated (kW)", "0.81", 0.81),
]

assert len(SENSOR_MATRIX) == 25, f"expected 25, got {len(SENSOR_MATRIX)}"

# _normalize edge cases
NORMALIZE_EDGES: list[tuple[object, object]] = [
    ("unknown", None), ("unavailable", None), ("", None),
    ("---", None), ("nan", None), ("null", None), ("none", None),
    ("inf", None), ("infinity", None), ("-inf", None), ("+inf", None),
    (None, None), (True, True), (False, False),
    ("ON", True), ("off", False), ("TRUE", True), ("no", False),
    ("yes", True), ("1", True), ("0", False),
    ("35.5", 35.5), ("-5.2", -5.2), ("1.5e-3", 0.0015),
    ("Heating", "Heating"), ("H/P only", "H/P only"),
    ("Off:Space", "Off:Space"),
]


@pytest.mark.parametrize("raw,expected", NORMALIZE_EDGES)
def test_normalize_returns_expected(raw, expected):
    """_normalize is the single source of truth for value coercion."""
    assert _normalize(raw) == expected


@pytest.mark.parametrize("attr_key,raw,expected", SENSOR_MATRIX)
def test_mono_read_returns_expected_value(attr_key, raw, expected):
    """Monolithic read() normalizes each of the 22 sensors to expected."""
    state = SimpleNamespace(attributes={attr_key: raw})
    result = read(state)
    assert attr_key in result
    assert result[attr_key] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("attr_key,raw,expected", SENSOR_MATRIX)
async def test_v2_resolve_returns_expected_value(hass, attr_key, raw, expected):
    """V2 resolve_attrs() normalizes each of the 22 sensors to expected."""
    eid = f"{DEFAULT_INDIVIDUAL_PREFIX}{make_json_key(attr_key)}"
    hass.states.async_set(eid, raw)
    result = resolve_attrs(hass, prefix=DEFAULT_INDIVIDUAL_PREFIX)
    assert attr_key in result.attrs, (
        f"v2 did not resolve {attr_key!r} (entity={eid}, "
        f"missing={result.missing_required})"
    )
    assert result.attrs[attr_key] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("attr_key,raw,expected", SENSOR_MATRIX)
async def test_same_normalized_value_via_mono_and_v2(hass, attr_key, raw, expected):
    """Mono read() and v2 resolve_attrs() yield identical values for this label.

    Regression guard for user requirement: "works the same as with
    attributes they must co-exist". Semantics: switching source (mono ->
    v2 or vice versa) must NOT change the canonical value for this label
    — otherwise historical comparisons break. Uses ONE source at a time
    (never concurrent reads), so no double-counting of sensor values.
    """
    mono = read(SimpleNamespace(attributes={attr_key: raw})).get(attr_key)

    eid = f"{DEFAULT_INDIVIDUAL_PREFIX}{make_json_key(attr_key)}"
    hass.states.async_set(eid, raw)
    v2 = resolve_attrs(hass, prefix=DEFAULT_INDIVIDUAL_PREFIX).attrs.get(attr_key)

    assert mono == expected
    assert v2 == expected
    assert mono == v2, f"coexistence mismatch: mono={mono!r} v2={v2!r}"
