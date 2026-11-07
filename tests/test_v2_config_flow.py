"""RED tests for ESPAltherma v2 source-type selection (issue #281).

R634: These tests MUST FAIL on current code if the source_type feature is
missing. Expected RED failures:
- `async_step_user` form does not include `source_type`
- `source_type=individual` does NOT route to `individual_prefix`
- `async_step_individual_prefix` does not exist
- `async_step_individual_review` does not exist

Existing behavior (monolithic + legacy shim) must remain green.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml.config_flow import (
    DaikinCycleMLConfigFlow,
)
from custom_components.daikin_cycle_ml.const import (
    CONF_INDIVIDUAL_PREFIX,
    CONF_SOURCE_TYPE,
    DEFAULT_INDIVIDUAL_PREFIX,
    REQUIRED_ATTRIBUTES,
    SOURCE_TYPE_AUTO,
    SOURCE_TYPE_INDIVIDUAL,
    SOURCE_TYPE_MONOLITHIC,
)


def _fresh_flow() -> DaikinCycleMLConfigFlow:
    """Minimal fresh flow state for calling async_step_* directly."""
    flow = DaikinCycleMLConfigFlow()
    flow.hass = MagicMock()
    flow.hass.states.async_all = MagicMock(return_value=[])
    flow.hass.states.get = MagicMock(return_value=None)
    flow.context = {}
    flow._data = {}
    flow._options = {}
    flow._selected_family = None
    flow._selected_model = None
    flow._reconfigure_entry = None
    return flow


def _schema_keys(schema_obj) -> set[str]:
    """Extract key names from a vol.Schema. Keys are vol.Optional/Required."""
    out: set[str] = set()
    for k in schema_obj.schema.keys():
        name = getattr(k, "schema", k)
        out.add(str(name))
    return out


# ---------- user form: source_type field presence ----------


@pytest.mark.asyncio
async def test_user_form_has_source_type_field() -> None:
    """RED: current form only has 'family'."""
    flow = _fresh_flow()
    result = await flow.async_step_user()
    assert result["type"] == "form"
    assert result["step_id"] == "user"
    keys = _schema_keys(result["data_schema"])
    assert "family" in keys, "existing family field must remain"
    assert "source_type" in keys, "source_type field must be added (#281)"


# ---------- user submit: routing per source_type ----------


@pytest.mark.asyncio
async def test_user_default_source_type_is_monolithic() -> None:
    """Backwards-compat: no source_type -> default monolithic, routes to model."""
    flow = _fresh_flow()
    result = await flow.async_step_user({"family": "ERGA"})
    assert result["step_id"] == "model", "monolithic path unchanged"
    assert flow._data.get(CONF_SOURCE_TYPE) == SOURCE_TYPE_MONOLITHIC, (
        "default source_type must be persisted as monolithic"
    )


@pytest.mark.asyncio
async def test_user_monolithic_routes_to_model() -> None:
    flow = _fresh_flow()
    result = await flow.async_step_user(
        {"family": "ERGA", "source_type": SOURCE_TYPE_MONOLITHIC}
    )
    assert result["step_id"] == "model"


@pytest.mark.asyncio
async def test_user_auto_routes_to_model() -> None:
    """Auto uses runtime dispatch; no prefix step in config_flow."""
    flow = _fresh_flow()
    result = await flow.async_step_user(
        {"family": "ERGA", "source_type": SOURCE_TYPE_AUTO}
    )
    assert result["step_id"] == "model"


@pytest.mark.asyncio
async def test_user_individual_routes_to_prefix() -> None:
    """RED: current flow routes individual to model."""
    flow = _fresh_flow()
    result = await flow.async_step_user(
        {"family": "ERGA", "source_type": SOURCE_TYPE_INDIVIDUAL}
    )
    assert result["step_id"] == "individual_prefix", (
        f"individual must route to prefix step, got {result['step_id']!r}"
    )


@pytest.mark.asyncio
async def test_legacy_shim_routes_to_model() -> None:
    """Existing tests submit `source_sensor` (legacy) — must not break."""
    flow = _fresh_flow()
    result = await flow.async_step_user(
        {"source_sensor": "sensor.x", "model": "epra12eav3"}
    )
    assert result["step_id"] == "model"


# ---------- individual_prefix step ----------


@pytest.mark.asyncio
async def test_individual_prefix_form_defaults_to_default_value() -> None:
    """RED: step does not exist yet."""
    flow = _fresh_flow()
    flow._data = {CONF_SOURCE_TYPE: SOURCE_TYPE_INDIVIDUAL}
    result = await flow.async_step_individual_prefix()
    assert result["type"] == "form"
    assert result["step_id"] == "individual_prefix"
    keys = _schema_keys(result["data_schema"])
    assert "individual_prefix" in keys


@pytest.mark.asyncio
async def test_individual_prefix_submit_to_review() -> None:
    """RED: step does not exist yet."""
    flow = _fresh_flow()
    flow._data = {CONF_SOURCE_TYPE: SOURCE_TYPE_INDIVIDUAL}
    result = await flow.async_step_individual_prefix(
        {"individual_prefix": "sensor.custom_"}
    )
    assert result["step_id"] == "individual_review"
    assert flow._data.get(CONF_INDIVIDUAL_PREFIX) == "sensor.custom_"


@pytest.mark.asyncio
async def test_individual_prefix_stores_default_when_blank() -> None:
    """Empty submit -> stores DEFAULT_INDIVIDUAL_PREFIX."""
    flow = _fresh_flow()
    flow._data = {CONF_SOURCE_TYPE: SOURCE_TYPE_INDIVIDUAL}
    await flow.async_step_individual_prefix({"individual_prefix": ""})
    assert flow._data.get(CONF_INDIVIDUAL_PREFIX) == DEFAULT_INDIVIDUAL_PREFIX


# ---------- individual_review step ----------


@pytest.mark.asyncio
async def test_individual_review_returns_form_with_placeholders() -> None:
    """RED: step does not exist yet."""
    flow = _fresh_flow()
    flow._data = {
        CONF_SOURCE_TYPE: SOURCE_TYPE_INDIVIDUAL,
        CONF_INDIVIDUAL_PREFIX: "sensor.espaltherma_",
    }
    result = await flow.async_step_individual_review()
    assert result["type"] == "form"
    assert result["step_id"] == "individual_review"
    placeholders = result.get("description_placeholders", {})
    assert "matched" in placeholders
    assert "total" in placeholders
    assert placeholders["total"] == str(len(REQUIRED_ATTRIBUTES))


@pytest.mark.asyncio
async def test_individual_review_shows_matched_equals_total_on_full_payload() -> None:
    """When all required entities are present, matched == total == 12."""
    flow = _fresh_flow()
    flow._data = {
        CONF_SOURCE_TYPE: SOURCE_TYPE_INDIVIDUAL,
        CONF_INDIVIDUAL_PREFIX: "sensor.espaltherma_",
    }
    # Simulate a full v2 install: every required label resolves.
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
    )
    from custom_components.daikin_cycle_ml.engine.espaltherma_v2.slug import (
        make_json_key,
    )
    values = {
        ATTR_OPERATION_MODE: "Heating", ATTR_IU_OPERATION_MODE: "Heating",
        ATTR_3WAY_VALVE: "Off:Space", ATTR_DEFROST_OPERATION: "OFF",
        ATTR_LEAVING_WATER_AFTER_BUH: "35.0", ATTR_INLET_WATER_R4T: "30.0",
        ATTR_OUTDOOR_AIR_R1T: "8.5", ATTR_FLOW_SENSOR: "15.0",
        ATTR_WATER_PUMP_OPERATION: "ON", ATTR_BUH_STEP1: "OFF",
        ATTR_BUH_STEP2: "OFF", ATTR_LW_SETPOINT: "40.0",
    }
    states = []
    for label, val in values.items():
        s = MagicMock()
        s.entity_id = f"sensor.espaltherma_{make_json_key(label)}"
        s.state = val
        states.append(s)

    def async_all(domain: str) -> list[MagicMock]:
        return states if domain == "sensor" else []

    def get(eid: str) -> MagicMock | None:
        for s in states:
            if s.entity_id == eid:
                return s
        return None

    flow.hass.states.async_all = MagicMock(side_effect=async_all)
    flow.hass.states.get = MagicMock(side_effect=get)

    result = await flow.async_step_individual_review()
    ph = result["description_placeholders"]
    assert ph["matched"] == ph["total"] == str(len(REQUIRED_ATTRIBUTES))


@pytest.mark.asyncio
async def test_individual_review_submit_continues_to_model() -> None:
    """RED: step does not exist yet."""
    flow = _fresh_flow()
    flow._data = {
        CONF_SOURCE_TYPE: SOURCE_TYPE_INDIVIDUAL,
        CONF_INDIVIDUAL_PREFIX: "sensor.espaltherma_",
    }
    result = await flow.async_step_individual_review({})
    assert result["step_id"] == "model"


# ---------- full chain ----------


@pytest.mark.asyncio
async def test_full_chain_individual_creates_entry() -> None:
    """End-to-end individual flow ends in create_entry with the new fields.

    RED: current flow ignores source_type end-to-end, so `create_entry` data
    will lack both source_type and individual_prefix.
    """
    flow = _fresh_flow()
    # user
    await flow.async_step_user(
        {"family": "ERGA", "source_type": SOURCE_TYPE_INDIVIDUAL}
    )
    # prefix
    await flow.async_step_individual_prefix(
        {"individual_prefix": "sensor.espaltherma_"}
    )
    # review (submit)
    await flow.async_step_individual_review({})
    # Skip async_step_model: it requires a valid source_sensor entity in
    # hass.states, but the individual path doesn't use source_sensor at all.
    # Pre-set the model state directly, then call finalize.
    flow._selected_family = "ERGA"
    flow._selected_model = "epra12eav3"
    flow._data.setdefault("model", "epra12eav3")
    flow._data.setdefault("source_sensor", "sensor.althermasensors")
    result = await flow.async_step_finalize({})
    assert result["type"] == "create_entry"
    assert result["data"].get(CONF_SOURCE_TYPE) == SOURCE_TYPE_INDIVIDUAL
    assert (
        result["data"].get(CONF_INDIVIDUAL_PREFIX) == "sensor.espaltherma_"
    )
