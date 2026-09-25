"""Tests for coordinator.DaikinCycleMLCoordinator."""
from __future__ import annotations

from custom_components.daikin_cycle_ml.const import (
    ATTR_INV_FREQUENCY_RPS,
    ATTR_IU_OPERATION_MODE,
    ATTR_LEAVING_WATER_AFTER_BUH,
    ATTR_INLET_WATER_R4T,
    DOMAIN,
    MODEL_EPRA12EAV3,
    OP_MODE_HEATING,
    REQUIRED_ATTRIBUTES,
    SOURCE_SENSOR_ENTITY,
)
from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)


def _make_entry(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"source_sensor": SOURCE_SENSOR_ENTITY, "model": MODEL_EPRA12EAV3},
        options={},
    )
    entry.add_to_hass(hass)
    return entry


def _valid_attrs(rps=0.0, mode=OP_MODE_HEATING):
    return {
        **{k: 0.0 for k in REQUIRED_ATTRIBUTES},
        ATTR_INV_FREQUENCY_RPS: rps,
        ATTR_IU_OPERATION_MODE: mode,
        ATTR_LEAVING_WATER_AFTER_BUH: 35.0,
        ATTR_INLET_WATER_R4T: 30.0,
    }


async def test_update_no_source_state(hass):
    entry = _make_entry(hass)
    coord = DaikinCycleMLCoordinator(hass, entry)
    data = await coord._async_update_data()
    assert data.missing_attrs == []
    assert data.state == "idle"
    assert data.errors == 0


async def test_update_with_valid_attrs_idle(hass):
    entry = _make_entry(hass)
    coord = DaikinCycleMLCoordinator(hass, entry)
    hass.states.async_set(SOURCE_SENSOR_ENTITY, "ok", _valid_attrs(rps=0.0))
    data = await coord._async_update_data()
    assert data.state == "idle"
    assert data.missing_attrs == []
    assert data.attrs[ATTR_INV_FREQUENCY_RPS] == 0.0


async def test_update_cycle_opens_and_closes(hass):
    entry = _make_entry(hass)
    coord = DaikinCycleMLCoordinator(hass, entry)
    hass.states.async_set(SOURCE_SENSOR_ENTITY, "ok", _valid_attrs(rps=30.0))
    await coord._async_update_data()
    assert coord.detector.state == "running"
    hass.states.async_set(SOURCE_SENSOR_ENTITY, "ok", _valid_attrs(rps=0.0))
    data = await coord._async_update_data()
    assert data.state == "idle"
    assert data.last_record is not None
    assert data.last_record["mode"] == "heating"
    assert coord.store.count() == 1


async def test_missing_attrs_reported(hass):
    entry = _make_entry(hass)
    coord = DaikinCycleMLCoordinator(hass, entry)
    hass.states.async_set(SOURCE_SENSOR_ENTITY, "ok", {"foo": 1})
    data = await coord._async_update_data()
    assert len(data.missing_attrs) == len(REQUIRED_ATTRIBUTES)


async def test_power_sensor_fallback(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"source_sensor": SOURCE_SENSOR_ENTITY, "model": MODEL_EPRA12EAV3},
        options={"power_sensor_entity": "sensor.hp_power"},
    )
    entry.add_to_hass(hass)
    coord = DaikinCycleMLCoordinator(hass, entry)
    hass.states.async_set(SOURCE_SENSOR_ENTITY, "ok", _valid_attrs(rps=0.0))
    hass.states.async_set("sensor.hp_power", "1500")
    data = await coord._async_update_data()
    assert data.state == "running"


async def test_options_override_defaults(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"source_sensor": SOURCE_SENSOR_ENTITY, "model": MODEL_EPRA12EAV3},
        options={"compressor_rps_threshold": 50},
    )
    entry.add_to_hass(hass)
    coord = DaikinCycleMLCoordinator(hass, entry)
    assert coord.options["compressor_rps_threshold"] == 50
    hass.states.async_set(SOURCE_SENSOR_ENTITY, "ok", _valid_attrs(rps=30.0))
    data = await coord._async_update_data()
    assert data.state == "idle"
