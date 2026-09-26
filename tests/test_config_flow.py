"""Tests for config_flow."""
from __future__ import annotations

import pytest

from custom_components.daikin_cycle_ml.const import (
    DOMAIN,
    MODEL_CUSTOM,
    MODEL_EPRA12EAV3,
    REQUIRED_ATTRIBUTES,
    SOURCE_SENSOR_ENTITY,
)


def _set_valid_state(hass):
    hass.states.async_set(
        SOURCE_SENSOR_ENTITY,
        "ok",
        {k: 0 for k in REQUIRED_ATTRIBUTES},
    )


async def test_user_step_shows_form(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"


async def test_user_step_entity_not_found(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"source_sensor": "sensor.does_not_exist", "model": MODEL_EPRA12EAV3},
    )
    assert result["type"] == "form"
    assert result["errors"]["source_sensor"] == "entity_not_found"


async def test_user_step_missing_attributes(hass):
    hass.states.async_set(SOURCE_SENSOR_ENTITY, "ok", {"foo": 1})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"source_sensor": SOURCE_SENSOR_ENTITY, "model": MODEL_EPRA12EAV3},
    )
    assert result["errors"]["source_sensor"] == "missing_attributes"


async def test_full_flow_creates_entry(hass):
    _set_valid_state(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"source_sensor": SOURCE_SENSOR_ENTITY, "model": MODEL_EPRA12EAV3},
    )
    assert result["step_id"] == "attributes"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"selected_attributes": []}
    )
    assert result["step_id"] == "cycle"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"compressor_rps_threshold": 3, "fallback_power_threshold_w": 200},
    )
    assert result["step_id"] == "pendulum"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"short_run_threshold_min": 20, "short_off_threshold_min": 5,
         "pendulum_cycles_per_day": 35, "dhw_pendulum_cycles_per_hour": 3},
    )
    assert result["step_id"] == "quality"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"good_run_threshold_min": 45, "good_dt_threshold_k": 5.0,
         "good_off_threshold_min": 20, "target_cycles_per_day": 8},
    )
    assert result["step_id"] == "notifications"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"persistent_enabled": True, "quiet_hours_enabled": False},
    )
    assert result["step_id"] == "finalize"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {}
    )
    assert result["type"] == "create_entry"
    assert result["data"]["model"] == MODEL_EPRA12EAV3
    assert result["data"]["source_sensor"] == SOURCE_SENSOR_ENTITY
    assert result["options"]["pendulum_cycles_per_day"] == 35


async def test_custom_model_step_valid(hass):
    _set_valid_state(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"source_sensor": SOURCE_SENSOR_ENTITY, "model": MODEL_CUSTOM},
    )
    assert result["step_id"] == "model_custom"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"custom_attribute_map": '{"INV frequency (rps)": "my_rps"}'}
    )
    assert result["step_id"] == "attributes"


async def test_custom_model_step_invalid_json(hass):
    _set_valid_state(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"source_sensor": SOURCE_SENSOR_ENTITY, "model": MODEL_CUSTOM},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"custom_attribute_map": "not json {"}
    )
    assert result["errors"]["custom_attribute_map"] == "invalid_json"


async def test_options_flow_shows_form(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    entry = MockConfigEntry(
        domain=DOMAIN, data={"source_sensor": SOURCE_SENSOR_ENTITY, "model": MODEL_EPRA12EAV3},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    # Batch 18: OptionsFlow is now a menu, not a single form
    assert result["type"] == "menu"
    assert "device" in result["menu_options"]
    assert result["step_id"] == "init"


async def test_options_flow_saves(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    entry = MockConfigEntry(
        domain=DOMAIN, data={"source_sensor": SOURCE_SENSOR_ENTITY, "model": MODEL_EPRA12EAV3},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "device"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"compressor_rps_threshold": 5},
    )
    assert result["type"] == "create_entry"
    assert result["data"]["compressor_rps_threshold"] == 5
