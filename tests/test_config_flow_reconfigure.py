"""Tests for reconfigure flow (Batch 9e)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daikin_cycle_ml.const import (
    DOMAIN,
    MODEL_EPRA08EAV3,
    MODEL_EPRA12EAV3,
    REQUIRED_ATTRIBUTES,
    SOURCE_SENSOR_ENTITY,
)

ALT_SOURCE = "sensor.alt_source"
DB_PATCH = "custom_components.daikin_cycle_ml._async_setup_database"


def _valid_attrs():
    return {k: 0 for k in REQUIRED_ATTRIBUTES}


def _add_entry(hass, options=None):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "source_sensor": SOURCE_SENSOR_ENTITY,
            "model": MODEL_EPRA12EAV3,
        },
        options=options or {},
    )
    entry.add_to_hass(hass)
    return entry


async def _init_reconfigure(hass, entry):
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reconfigure", "entry_id": entry.entry_id},
    )


@pytest.fixture
def no_db():
    with patch(DB_PATCH, new=AsyncMock()):
        yield


async def test_reconfigure_shows_menu(hass):
    entry = _add_entry(hass)
    result = await _init_reconfigure(hass, entry)
    assert result["type"] == "menu"
    assert result["step_id"] == "reconfigure"
    assert set(result["menu_options"]) == {
        "reconfigure_basic", "reconfigure_full"
    }


async def test_reconfigure_basic_shows_form(hass):
    hass.states.async_set(SOURCE_SENSOR_ENTITY, "ok", _valid_attrs())
    entry = _add_entry(hass)
    result = await _init_reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "reconfigure_basic"}
    )
    assert result["step_id"] == "reconfigure_basic"


async def test_reconfigure_basic_source_change(hass, no_db):
    hass.states.async_set(SOURCE_SENSOR_ENTITY, "ok", _valid_attrs())
    hass.states.async_set(ALT_SOURCE, "ok", _valid_attrs())
    entry = _add_entry(hass)
    result = await _init_reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "reconfigure_basic"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"source_sensor": ALT_SOURCE, "model": MODEL_EPRA12EAV3},
    )
    await hass.async_block_till_done()
    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    refreshed = hass.config_entries.async_get_entry(entry.entry_id)
    assert refreshed.data["source_sensor"] == ALT_SOURCE


async def test_reconfigure_basic_entity_not_found(hass):
    entry = _add_entry(hass)
    result = await _init_reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "reconfigure_basic"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"source_sensor": "sensor.missing", "model": MODEL_EPRA12EAV3},
    )
    assert result["type"] == "form"
    assert result["errors"]["source_sensor"] == "entity_not_found"


async def test_reconfigure_basic_missing_attrs(hass):
    hass.states.async_set(SOURCE_SENSOR_ENTITY, "ok", {"foo": 1})
    entry = _add_entry(hass)
    result = await _init_reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "reconfigure_basic"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"source_sensor": SOURCE_SENSOR_ENTITY, "model": MODEL_EPRA12EAV3},
    )
    assert result["errors"]["source_sensor"] == "missing_attributes"


async def test_reconfigure_full_lands_on_user(hass):
    hass.states.async_set(SOURCE_SENSOR_ENTITY, "ok", _valid_attrs())
    entry = _add_entry(hass)
    result = await _init_reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "reconfigure_full"}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"


async def test_reconfigure_full_completes(hass, no_db):
    hass.states.async_set(SOURCE_SENSOR_ENTITY, "ok", _valid_attrs())
    entry = _add_entry(hass, options={"short_run_threshold_min": 15})
    result = await _init_reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "reconfigure_full"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"source_sensor": SOURCE_SENSOR_ENTITY, "model": MODEL_EPRA12EAV3},
    )
    assert result["step_id"] == "attributes"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {}
    )
    assert result["step_id"] == "cycle"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"compressor_rps_threshold": 5, "fallback_power_threshold_w": 200},
    )
    assert result["step_id"] == "pendulum"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "short_run_threshold_min": 15,
            "short_off_threshold_min": 5,
            "pendulum_cycles_per_day": 35,
            "dhw_pendulum_cycles_per_hour": 3,
        },
    )
    assert result["step_id"] == "quality"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "good_run_threshold_min": 45,
            "good_dt_threshold_k": 5.0,
            "good_off_threshold_min": 20,
            "target_cycles_per_day": 8,
        },
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
    await hass.async_block_till_done()
    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    refreshed = hass.config_entries.async_get_entry(entry.entry_id)
    assert refreshed.options["short_run_threshold_min"] == 15
    assert refreshed.options["compressor_rps_threshold"] == 5


async def test_reconfigure_full_preserves_options(hass, no_db):
    hass.states.async_set(SOURCE_SENSOR_ENTITY, "ok", _valid_attrs())
    entry = _add_entry(hass, options={"pendulum_cycles_per_day": 30})
    result = await _init_reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "reconfigure_full"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"source_sensor": SOURCE_SENSOR_ENTITY, "model": MODEL_EPRA08EAV3},
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"], {}
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"compressor_rps_threshold": 3, "fallback_power_threshold_w": 200},
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "short_run_threshold_min": 20,
            "short_off_threshold_min": 5,
            "pendulum_cycles_per_day": 30,
            "dhw_pendulum_cycles_per_hour": 3,
        },
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "good_run_threshold_min": 45,
            "good_dt_threshold_k": 5.0,
            "good_off_threshold_min": 20,
            "target_cycles_per_day": 8,
        },
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"persistent_enabled": True, "quiet_hours_enabled": False},
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"], {}
    )
    await hass.async_block_till_done()
    refreshed = hass.config_entries.async_get_entry(entry.entry_id)
    assert refreshed.options["pendulum_cycles_per_day"] == 30
    assert refreshed.data["model"] == MODEL_EPRA08EAV3
