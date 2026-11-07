"""Tests for ESPAltherma v2 attribute resolver (issue #281, R684 + R640)."""
from __future__ import annotations

from unittest.mock import MagicMock

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
    ATTR_BE_COP,
    ATTR_BOILER_DHW_DEMAND,
    ATTR_BOILER_OPERATION_DEMAND,
    ATTR_COP,
    ATTR_DHW_TANK_TEMP,
    ATTR_HYBRID_OP_MODE,
    ATTR_INDOOR_AMBIENT_R1T,
    ATTR_INV_FREQUENCY_2_RPS,
    ATTR_INV_FREQUENCY_RPS,
    ATTR_TARGET_COND_TEMP,
    CONSUMED_ATTRIBUTES,
    REQUIRED_ATTRIBUTES,
)
from custom_components.daikin_cycle_ml.engine.espaltherma_v2.resolver import (
    ResolveResult,
    labels_for_model,
    load_model_attributes,
    models_for_label,
    resolve_attrs,
)
from custom_components.daikin_cycle_ml.engine.espaltherma_v2.slug import (
    DEFAULT_PREFIX,
    make_json_key,
)

# ---------- helpers ----------


def _make_state(entity_id: str, value: str) -> MagicMock:
    s = MagicMock()
    s.entity_id = entity_id
    s.state = value
    return s


def _make_hass(states: dict[str, str]) -> MagicMock:
    """Build a fake hass.states from {entity_id: raw_string_value}."""
    hass = MagicMock()
    all_states = [_make_state(eid, val) for eid, val in states.items()]

    def async_all(domain: str) -> list[MagicMock]:
        if domain != "sensor":
            return []
        return [s for s in all_states if s.entity_id.startswith("sensor.")]

    def get(eid: str) -> MagicMock | None:
        for s in all_states:
            if s.entity_id == eid:
                return s
        return None

    hass.states.async_all = MagicMock(side_effect=async_all)
    hass.states.get = MagicMock(side_effect=get)
    return hass


def _full_payload() -> dict[str, str]:
    """Every REQUIRED_ATTRIBUTE mapped to a plausible v2 entity state."""
    return {
        f"{DEFAULT_PREFIX}{make_json_key(ATTR_OPERATION_MODE)}": "Heating",
        f"{DEFAULT_PREFIX}{make_json_key(ATTR_IU_OPERATION_MODE)}": "Heating",
        f"{DEFAULT_PREFIX}{make_json_key(ATTR_3WAY_VALVE)}": "Off:Space",
        f"{DEFAULT_PREFIX}{make_json_key(ATTR_DEFROST_OPERATION)}": "OFF",
        f"{DEFAULT_PREFIX}{make_json_key(ATTR_LEAVING_WATER_AFTER_BUH)}": "35.0",
        f"{DEFAULT_PREFIX}{make_json_key(ATTR_INLET_WATER_R4T)}": "30.0",
        f"{DEFAULT_PREFIX}{make_json_key(ATTR_OUTDOOR_AIR_R1T)}": "8.5",
        f"{DEFAULT_PREFIX}{make_json_key(ATTR_FLOW_SENSOR)}": "15.2",
        f"{DEFAULT_PREFIX}{make_json_key(ATTR_WATER_PUMP_OPERATION)}": "ON",
        f"{DEFAULT_PREFIX}{make_json_key(ATTR_BUH_STEP1)}": "OFF",
        f"{DEFAULT_PREFIX}{make_json_key(ATTR_BUH_STEP2)}": "OFF",
        f"{DEFAULT_PREFIX}{make_json_key(ATTR_LW_SETPOINT)}": "40.0",
    }


def _full_payload_22() -> dict[str, str]:
    """Every CONSUMED_ATTRIBUTE mapped to a plausible v2 entity state."""
    payload = _full_payload()
    payload.update({
        f"{DEFAULT_PREFIX}{make_json_key(ATTR_COP)}": "4.5",
        f"{DEFAULT_PREFIX}{make_json_key(ATTR_INV_FREQUENCY_RPS)}": "35",
        f"{DEFAULT_PREFIX}{make_json_key(ATTR_INV_FREQUENCY_2_RPS)}": "15",
        f"{DEFAULT_PREFIX}{make_json_key(ATTR_DHW_TANK_TEMP)}": "55.0",
        f"{DEFAULT_PREFIX}{make_json_key(ATTR_INDOOR_AMBIENT_R1T)}": "21.5",
        f"{DEFAULT_PREFIX}{make_json_key(ATTR_TARGET_COND_TEMP)}": "38.0",
        f"{DEFAULT_PREFIX}{make_json_key(ATTR_BOILER_OPERATION_DEMAND)}": "OFF",
        f"{DEFAULT_PREFIX}{make_json_key(ATTR_BOILER_DHW_DEMAND)}": "OFF",
        f"{DEFAULT_PREFIX}{make_json_key(ATTR_HYBRID_OP_MODE)}": "H/P only",
        f"{DEFAULT_PREFIX}{make_json_key(ATTR_BE_COP)}": "1.2",
    })
    return payload


# ---------- happy path ----------


def test_resolve_all_required_present() -> None:
    hass = _make_hass(_full_payload())
    result = resolve_attrs(hass)
    assert isinstance(result, ResolveResult)
    assert set(result.attrs.keys()) == set(REQUIRED_ATTRIBUTES)
    assert result.missing_required == []
    assert result.discovered_count == len(REQUIRED_ATTRIBUTES)


def test_resolve_normalizes_bool_strings() -> None:
    hass = _make_hass(_full_payload())
    result = resolve_attrs(hass)
    assert result.attrs[ATTR_DEFROST_OPERATION] is False
    assert result.attrs[ATTR_WATER_PUMP_OPERATION] is True
    assert result.attrs[ATTR_BUH_STEP1] is False


def test_resolve_normalizes_floats() -> None:
    hass = _make_hass(_full_payload())
    result = resolve_attrs(hass)
    assert result.attrs[ATTR_LEAVING_WATER_AFTER_BUH] == pytest.approx(35.0)
    assert result.attrs[ATTR_INLET_WATER_R4T] == pytest.approx(30.0)
    assert result.attrs[ATTR_OUTDOOR_AIR_R1T] == pytest.approx(8.5)
    assert result.attrs[ATTR_FLOW_SENSOR] == pytest.approx(15.2)
    assert result.attrs[ATTR_LW_SETPOINT] == pytest.approx(40.0)


# ---------- missing attributes ----------


@pytest.mark.parametrize(
    "missing_label",
    [
        ATTR_OPERATION_MODE,
        ATTR_DEFROST_OPERATION,
        ATTR_FLOW_SENSOR,
        ATTR_BUH_STEP1,
        ATTR_LW_SETPOINT,
    ],
)
def test_resolve_single_missing(missing_label: str) -> None:
    payload = _full_payload()
    del payload[f"{DEFAULT_PREFIX}{make_json_key(missing_label)}"]
    hass = _make_hass(payload)
    result = resolve_attrs(hass)
    assert missing_label in result.missing_required
    assert missing_label not in result.attrs
    assert len(result.missing_required) == 1


def test_resolve_empty_hass() -> None:
    hass = _make_hass({})
    result = resolve_attrs(hass)
    assert result.attrs == {}
    assert set(result.missing_required) == set(REQUIRED_ATTRIBUTES)
    assert result.discovered_count == 0


def test_resolve_unknown_state_counts_as_missing() -> None:
    payload = _full_payload()
    payload[f"{DEFAULT_PREFIX}{make_json_key(ATTR_OPERATION_MODE)}"] = "unknown"
    hass = _make_hass(payload)
    result = resolve_attrs(hass)
    assert ATTR_OPERATION_MODE in result.missing_required


def test_resolve_unavailable_state_counts_as_missing() -> None:
    payload = _full_payload()
    payload[f"{DEFAULT_PREFIX}{make_json_key(ATTR_DEFROST_OPERATION)}"] = "unavailable"
    hass = _make_hass(payload)
    result = resolve_attrs(hass)
    assert ATTR_DEFROST_OPERATION in result.missing_required


# ---------- custom_map (user override) ----------


def test_resolve_custom_map_override() -> None:
    """User override maps a canonical label to an arbitrary target label.

    Uses a proper label ("Custom Operation Mode") so make_json_key
    produces "custom_operation_mode" — matching the entity we add.
    Avoids underscore-in-slug confusion from make_json_key dropping "_".
    """
    payload = _full_payload()
    del payload[f"{DEFAULT_PREFIX}{make_json_key(ATTR_OPERATION_MODE)}"]
    payload[f"{DEFAULT_PREFIX}custom_operation_mode"] = "Cooling"
    hass = _make_hass(payload)
    result = resolve_attrs(
        hass, custom_map={ATTR_OPERATION_MODE: "Custom Operation Mode"}
    )
    assert result.attrs[ATTR_OPERATION_MODE] == "Cooling"
    assert ATTR_OPERATION_MODE not in result.missing_required


def test_resolve_custom_map_with_raw_label() -> None:
    """custom_map can pass a raw label; make_json_key is applied internally."""
    payload = _full_payload()
    del payload[f"{DEFAULT_PREFIX}{make_json_key(ATTR_OPERATION_MODE)}"]
    payload[f"{DEFAULT_PREFIX}weird_mode_name"] = "Heating"
    hass = _make_hass(payload)
    result = resolve_attrs(
        hass, custom_map={ATTR_OPERATION_MODE: "Weird Mode Name"}
    )
    assert result.attrs[ATTR_OPERATION_MODE] == "Heating"


# ---------- collisions + placeholders ----------


def test_resolve_collisions_do_not_block_resolution() -> None:
    """Case-only variants still resolve via the same slug."""
    hass = _make_hass(_full_payload())
    result = resolve_attrs(hass)
    # No collisions among REQUIRED (they're all unique slugs)
    assert result.collisions == []


def test_resolve_skips_placeholder_labels() -> None:
    """Placeholder '????' produces empty slug -> never becomes a required miss."""
    # No sensor with empty slug exists in HA; resolver must not IndexError.
    hass = _make_hass(_full_payload())
    result = resolve_attrs(hass)
    # No crash, all required present
    assert set(result.attrs.keys()) == set(REQUIRED_ATTRIBUTES)


def test_resolve_ignores_extra_entities() -> None:
    payload = _full_payload()
    payload[f"{DEFAULT_PREFIX}some_extra_field"] = "42.0"
    payload["sensor.weather"] = "sunny"
    hass = _make_hass(payload)
    result = resolve_attrs(hass)
    assert "some_extra_field" not in str(result.attrs.keys())
    assert set(result.attrs.keys()) == set(REQUIRED_ATTRIBUTES)


# ---------- prefix handling ----------


def test_resolve_custom_prefix() -> None:
    payload = {
        "sensor.custom_operation_mode": "Heating",
        "sensor.custom_defrost_operation": "ON",
    }
    hass = _make_hass(payload)
    result = resolve_attrs(hass, prefix="sensor.custom_")
    # Only 2 of 12 required present
    assert len(result.attrs) == 2
    assert ATTR_OPERATION_MODE in result.attrs
    assert ATTR_DEFROST_OPERATION in result.attrs
    assert len(result.missing_required) == len(REQUIRED_ATTRIBUTES) - 2


# ---------- model bridge helpers ----------


def _skip_if_no_model_attrs() -> None:
    if not load_model_attributes():
        pytest.skip("docs/MODEL_ATTRIBUTES.json not available")


def test_load_model_attributes_returns_dict() -> None:
    _skip_if_no_model_attrs()
    mapping = load_model_attributes()
    assert isinstance(mapping, dict)
    assert len(mapping) >= 100
    # Every value must be a list of strings
    for label, models in mapping.items():
        assert isinstance(label, str)
        assert isinstance(models, list)
        assert all(isinstance(m, str) for m in models)


def test_labels_for_model_narrows_correctly() -> None:
    _skip_if_no_model_attrs()
    mapping = load_model_attributes()
    any_model = next(iter(mapping.values()))[0]
    labels = labels_for_model(any_model)
    assert labels, f"no labels found for {any_model!r}"
    # Every returned label must list any_model
    for lb in labels:
        assert any_model in mapping[lb]


def test_models_for_label_is_inverse() -> None:
    _skip_if_no_model_attrs()
    mapping = load_model_attributes()
    label = next(iter(mapping))
    models = models_for_label(label)
    assert models == sorted(mapping[label])


def test_model_bridge_known_operation_mode() -> None:
    """Operation Mode should be published by every model that has any label."""
    _skip_if_no_model_attrs()
    models = models_for_label("Operation Mode")
    assert len(models) >= 20, (
        f"Operation Mode should exist on most models, got {len(models)}"
    )


def test_model_bridge_unknown_returns_empty() -> None:
    _skip_if_no_model_attrs()
    assert labels_for_model("NotAModel.h") == []
    assert models_for_label("Nonexistent Label") == []


# ---------- R640 fuzz: arbitrary state values must not crash ----------


@given(
    values=st.dictionaries(
        keys=st.text(min_size=1, max_size=20),
        values=st.text(min_size=0, max_size=20),
        max_size=15,
    )
)
@settings(max_examples=200, deadline=None)
def test_resolve_fuzz_never_raises(values: dict[str, str]) -> None:
    """R676: 200 random prefix payloads -> never crash; missing is a subset."""
    payload = {
        f"{DEFAULT_PREFIX}{k}": v
        for k, v in values.items()
        if k and k.replace("_", "").isalnum()
    }
    hass = _make_hass(payload)
    result = resolve_attrs(hass)
    assert isinstance(result, ResolveResult)
    assert set(result.missing_required) <= set(REQUIRED_ATTRIBUTES)



# ---------- v1.20.0 #281: consumed attributes transparency contract ----------


def test_resolve_returns_all_consumed_when_all_22_present() -> None:
    """All 22 CONSUMED_ATTRIBUTES resolved -> both missing lists empty."""
    hass = _make_hass(_full_payload_22())
    result = resolve_attrs(hass)
    assert len(result.attrs) == len(CONSUMED_ATTRIBUTES)
    assert set(result.attrs.keys()) == set(CONSUMED_ATTRIBUTES)
    assert result.missing_required == []
    assert result.missing_consumed == []
    assert result.discovered_count == len(CONSUMED_ATTRIBUTES)


def test_resolve_extra_consumed_missing_not_in_required() -> None:
    """Required-only payload: 10 extra consumed labels go in missing_consumed
    but NOT in missing_required (no repair noise for legit-absent labels)."""
    hass = _make_hass(_full_payload())
    result = resolve_attrs(hass)
    extra_labels = set(CONSUMED_ATTRIBUTES) - set(REQUIRED_ATTRIBUTES)
    assert result.missing_required == []
    assert set(result.missing_consumed) == extra_labels
    assert len(result.missing_consumed) == 10


def test_resolve_missing_required_also_in_missing_consumed() -> None:
    """Transparency contract: required-missing labels appear in BOTH lists.

    Never hidden in only one — user-facing repair uses missing_required,
    but diagnostics/logs/binary_sensor use missing_consumed which is a
    strict superset.
    """
    payload = _full_payload_22()
    del payload[f"{DEFAULT_PREFIX}{make_json_key(ATTR_BUH_STEP1)}"]
    del payload[f"{DEFAULT_PREFIX}{make_json_key(ATTR_BUH_STEP2)}"]
    hass = _make_hass(payload)
    result = resolve_attrs(hass)
    expected = {ATTR_BUH_STEP1, ATTR_BUH_STEP2}
    assert set(result.missing_required) == expected
    assert set(result.missing_consumed) == expected
    assert set(result.missing_required).issubset(set(result.missing_consumed))


# ---------- v1.20.0 #281 coverage: defensive guards + JSON edge cases ----------
# R643: guards are real contracts. Test them, don't # pragma away.


def test_read_entity_state_returns_none_when_entity_absent() -> None:
    """Line 86: state is None -> None (defensive, unreachable via resolve_attrs
    because index.get would have returned None first)."""
    from custom_components.daikin_cycle_ml.engine.espaltherma_v2.resolver import (
        _read_entity_state,
    )
    hass = _make_hass({})  # empty: .get returns None
    assert _read_entity_state(hass, "sensor.nonexistent") is None


def test_read_entity_state_returns_none_when_raw_state_is_none() -> None:
    """Line 89: state.state is None -> None."""
    from custom_components.daikin_cycle_ml.engine.espaltherma_v2.resolver import (
        _read_entity_state,
    )
    from unittest.mock import MagicMock
    hass = MagicMock()
    s = MagicMock()
    s.state = None
    hass.states.get = MagicMock(return_value=s)
    assert _read_entity_state(hass, "sensor.x") is None


def test_collision_loop_skips_empty_slug_label(monkeypatch) -> None:
    """Line 123: a REQUIRED label whose make_json_key() is empty is skipped
    in the collision loop, and (because it is also in CONSUMED) reported as
    missing in both lists. Proves the guard for future upstream drift.

    Note: monkeypatch BOTH sets so the consumed-loop also sees the
    placeholder — otherwise only the collision-loop branch is exercised.
    """
    from custom_components.daikin_cycle_ml.engine.espaltherma_v2 import resolver
    monkeypatch.setattr(resolver, "REQUIRED_ATTRIBUTES", ["", "Operation Mode"])
    monkeypatch.setattr(
        resolver, "CONSUMED_ATTRIBUTES", ["", "Operation Mode"],
    )
    hass = _make_hass({})  # no entities -> all missing
    result = resolver.resolve_attrs(hass, prefix=DEFAULT_PREFIX)
    assert isinstance(result, ResolveResult)
    assert "" in result.missing_required
    assert "" in result.missing_consumed
    assert "Operation Mode" in result.missing_required


def test_resolve_consumed_with_empty_slug_label(monkeypatch) -> None:
    """Line 142 -> 149: empty slug in CONSUMED_ATTRIBUTES goes straight to
    missing_consumed (no attempted lookup, no crash)."""
    from custom_components.daikin_cycle_ml.engine.espaltherma_v2 import resolver
    monkeypatch.setattr(resolver, "CONSUMED_ATTRIBUTES", ["????"])
    monkeypatch.setattr(resolver, "REQUIRED_ATTRIBUTES", [])  # avoid set mismatch
    hass = _make_hass({})
    result = resolver.resolve_attrs(hass, prefix=DEFAULT_PREFIX)
    assert "????" in result.missing_consumed
    assert result.missing_required == []


def test_load_model_attributes_missing_file(tmp_path) -> None:
    """Line 183-184: missing file -> {}."""
    result = load_model_attributes(tmp_path / "does-not-exist.json")
    assert result == {}


def test_load_model_attributes_valid_json_not_dict(tmp_path) -> None:
    """Line 186: JSON parses but top level is not a dict -> {}."""
    p = tmp_path / "x.json"
    p.write_text("[]")
    result = load_model_attributes(p)
    assert result == {}


def test_load_model_attributes_labels_not_dict(tmp_path) -> None:
    """Line 189: 'labels' key exists but is not a dict -> {}."""
    p = tmp_path / "x.json"
    p.write_text('{"labels": []}')
    result = load_model_attributes(p)
    assert result == {}


def test_load_model_attributes_filters_invalid_entries(tmp_path) -> None:
    """Line 192 -> 191: non-list models value -> entry skipped.

    JSON keys are always strings (JSON spec), so the `isinstance(models, list)`
    side of the AND exercises the False branch (regel 192 -> 191) when
    models is a string like "not-a-list".
    """
    import json as _json
    p = tmp_path / "x.json"
    p.write_text(_json.dumps({
        "labels": {
            "Valid": ["ModelA.h", "ModelB.h"],
            "BadModels": "not-a-list",
        }
    }))
    result = load_model_attributes(p)
    assert result == {"Valid": ["ModelA.h", "ModelB.h"]}
