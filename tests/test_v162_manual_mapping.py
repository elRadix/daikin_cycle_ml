"""v1.6.2 -- attribute-mode + manual mapping tests (issue #25)."""
from __future__ import annotations

import json
from pathlib import Path

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.daikin_cycle_ml.const import (
    ATTRIBUTE_MODE_AUTO,
    ATTRIBUTE_MODE_MANUAL,
    DOMAIN,
    MODEL_EPRA12EAV3,
    OPTIONAL_ATTRIBUTES,
    REQUIRED_ATTRIBUTES,
    SOURCE_SENSOR_ENTITY,
)


def _set_state(hass: HomeAssistant, attrs: dict | None = None) -> None:
    if attrs is None:
        attrs = dict.fromkeys(REQUIRED_ATTRIBUTES, 0)
    hass.states.async_set(SOURCE_SENSOR_ENTITY, "ok", attrs)


async def _start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER},
    )


async def test_auto_mode_passes_and_routes_to_attributes(hass: HomeAssistant):
    _set_state(hass)
    r = await _start(hass)
    r2 = await hass.config_entries.flow.async_configure(
        r["flow_id"],
        {
            "source_sensor": SOURCE_SENSOR_ENTITY,
            "model": MODEL_EPRA12EAV3,
            "attribute_mode": ATTRIBUTE_MODE_AUTO,
        },
    )
    assert r2["type"] == FlowResultType.FORM
    assert r2["step_id"] == "attributes"


async def test_auto_mode_missing_lists_keys(hass: HomeAssistant):
    _set_state(hass, {"foo": 1})
    r = await _start(hass)
    r2 = await hass.config_entries.flow.async_configure(
        r["flow_id"],
        {
            "source_sensor": SOURCE_SENSOR_ENTITY,
            "model": MODEL_EPRA12EAV3,
            "attribute_mode": ATTRIBUTE_MODE_AUTO,
        },
    )
    assert r2["type"] == FlowResultType.FORM
    assert r2["step_id"] == "user"
    assert r2["errors"]["source_sensor"] == "missing_attributes"


async def test_manual_mode_routes_to_map_step(hass: HomeAssistant):
    _set_state(hass)
    r = await _start(hass)
    r2 = await hass.config_entries.flow.async_configure(
        r["flow_id"],
        {
            "source_sensor": SOURCE_SENSOR_ENTITY,
            "model": MODEL_EPRA12EAV3,
            "attribute_mode": ATTRIBUTE_MODE_MANUAL,
        },
    )
    assert r2["type"] == FlowResultType.FORM
    assert r2["step_id"] == "map_attributes"
    schema = r2["data_schema"].schema
    keys = {str(k) for k in schema}
    assert all(canonical in keys for canonical in REQUIRED_ATTRIBUTES)


async def test_manual_mode_correct_mapping_saves(hass: HomeAssistant):
    # Sensor exposes non-canonical keys; user maps canonical -> custom key.
    sensor_keys = {f"custom.{c}": 0 for c in REQUIRED_ATTRIBUTES}
    _set_state(hass, sensor_keys)
    user_input = {c: f"custom.{c}" for c in REQUIRED_ATTRIBUTES}
    r = await _start(hass)
    r2 = await hass.config_entries.flow.async_configure(
        r["flow_id"],
        {
            "source_sensor": SOURCE_SENSOR_ENTITY,
            "model": MODEL_EPRA12EAV3,
            "attribute_mode": ATTRIBUTE_MODE_MANUAL,
        },
    )
    r3 = await hass.config_entries.flow.async_configure(
        r2["flow_id"], user_input=user_input,
    )
    assert r3["type"] == FlowResultType.FORM
    assert r3["step_id"] == "attributes"


async def test_manual_mode_empty_fields_use_canonical(hass: HomeAssistant):
    _set_state(hass)
    r = await _start(hass)
    r2 = await hass.config_entries.flow.async_configure(
        r["flow_id"],
        {
            "source_sensor": SOURCE_SENSOR_ENTITY,
            "model": MODEL_EPRA12EAV3,
            "attribute_mode": ATTRIBUTE_MODE_MANUAL,
        },
    )
    r3 = await hass.config_entries.flow.async_configure(
        r2["flow_id"], user_input={c: "" for c in REQUIRED_ATTRIBUTES},
    )
    assert r3["type"] == FlowResultType.FORM
    assert r3["step_id"] == "attributes"


async def test_manual_mode_bad_user_key_errors(hass: HomeAssistant):
    _set_state(hass)
    r = await _start(hass)
    r2 = await hass.config_entries.flow.async_configure(
        r["flow_id"],
        {
            "source_sensor": SOURCE_SENSOR_ENTITY,
            "model": MODEL_EPRA12EAV3,
            "attribute_mode": ATTRIBUTE_MODE_MANUAL,
        },
    )
    user_input = {c: "" for c in REQUIRED_ATTRIBUTES}
    user_input[REQUIRED_ATTRIBUTES[0]] = "does.not.exist"
    r3 = await hass.config_entries.flow.async_configure(
        r2["flow_id"], user_input=user_input,
    )
    assert r3["type"] == FlowResultType.FORM
    assert r3["step_id"] == "map_attributes"
    assert r3["errors"]["base"] == "attribute_not_found"


async def test_manual_mode_unmapped_required_errors(hass: HomeAssistant):
    _set_state(hass, {"only.one": 1})
    r = await _start(hass)
    r2 = await hass.config_entries.flow.async_configure(
        r["flow_id"],
        {
            "source_sensor": SOURCE_SENSOR_ENTITY,
            "model": MODEL_EPRA12EAV3,
            "attribute_mode": ATTRIBUTE_MODE_MANUAL,
        },
    )
    r3 = await hass.config_entries.flow.async_configure(
        r2["flow_id"], user_input={c: "" for c in REQUIRED_ATTRIBUTES},
    )
    assert r3["type"] == FlowResultType.FORM
    assert r3["errors"]["base"] == "required_attrs_unmapped"


async def test_manual_mode_optional_can_be_mapped(hass: HomeAssistant):
    attrs = dict.fromkeys(REQUIRED_ATTRIBUTES, 0)
    attrs["my_rps"] = 42
    _set_state(hass, attrs)
    r = await _start(hass)
    r2 = await hass.config_entries.flow.async_configure(
        r["flow_id"],
        {
            "source_sensor": SOURCE_SENSOR_ENTITY,
            "model": MODEL_EPRA12EAV3,
            "attribute_mode": ATTRIBUTE_MODE_MANUAL,
        },
    )
    user_input = {c: "" for c in REQUIRED_ATTRIBUTES}
    for opt in OPTIONAL_ATTRIBUTES:
        user_input[opt] = "my_rps"
    r3 = await hass.config_entries.flow.async_configure(
        r2["flow_id"], user_input=user_input,
    )
    assert r3["type"] == FlowResultType.FORM
    assert r3["step_id"] == "attributes"


async def test_map_step_shows_all_attributes(hass: HomeAssistant):
    _set_state(hass)
    r = await _start(hass)
    r2 = await hass.config_entries.flow.async_configure(
        r["flow_id"],
        {
            "source_sensor": SOURCE_SENSOR_ENTITY,
            "model": MODEL_EPRA12EAV3,
            "attribute_mode": ATTRIBUTE_MODE_MANUAL,
        },
    )
    schema = r2["data_schema"].schema
    keys = {str(k) for k in schema}
    for canonical in REQUIRED_ATTRIBUTES + OPTIONAL_ATTRIBUTES:
        assert canonical in keys


async def test_user_step_shows_attribute_mode_field(hass: HomeAssistant):
    r = await _start(hass)
    schema = r["data_schema"].schema
    keys = {str(k) for k in schema}
    assert "attribute_mode" in keys


def test_strings_has_map_step_and_errors():
    base = Path("custom_components/daikin_cycle_ml")
    for fname in ("strings.json", "translations/en.json", "translations/nl.json"):
        d = json.loads((base / fname).read_text())
        step = d["config"]["step"]
        assert "map_attributes" in step, fname
        data = step["map_attributes"]["data"]
        for canonical in REQUIRED_ATTRIBUTES + OPTIONAL_ATTRIBUTES:
            assert canonical in data, f"{fname}: {canonical}"
        err = d["config"]["error"]
        for key in ("missing_attributes", "attribute_not_found",
                    "required_attrs_unmapped"):
            assert key in err, f"{fname}: {key}"


def test_const_splits_required_from_optional():
    assert len(REQUIRED_ATTRIBUTES) == 12
    assert len(OPTIONAL_ATTRIBUTES) == 1
    assert OPTIONAL_ATTRIBUTES[0] == "INV frequency (rps)"
    assert not set(REQUIRED_ATTRIBUTES) & set(OPTIONAL_ATTRIBUTES)
