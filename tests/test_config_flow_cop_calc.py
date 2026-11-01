"""Tests for OptionsFlow.async_step_cop_calc (v1.14.0, #206)."""

import asyncio
from unittest.mock import MagicMock

from custom_components.daikin_cycle_ml.config_flow import (
    DaikinCycleMLOptionsFlow,
)


def _flow(options=None):
    flow = DaikinCycleMLOptionsFlow()
    flow.hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "x"
    entry.options = options or {}
    entry.data = {}
    entry.runtime_data = None
    type(flow).config_entry = property(lambda self: entry)
    flow.async_create_entry = MagicMock(
        return_value={"type": "create_entry", "data": options or {}}
    )
    return flow


def test_cop_calc_form_renders():
    f = _flow({"supply_phases": "3", "buh_step1_kw": 3.0})
    r = asyncio.run(f.async_step_cop_calc())
    assert r["type"] == "form"
    assert r["step_id"] == "cop_calc"
    assert "data_schema" in r


def test_cop_calc_submit_calls_save():
    """cop_calc merges its own fields without touching sensor mappings (#244)."""
    f = _flow({
        "existing": "keep",
        "power_sensor_entity": "sensor.power",
        "cop_sensor_entity": "sensor.cop",
        "indoor_temp_sensor": "sensor.indoor",
    })
    payload = {
        "electrical": {
            "supply_phases": "3",
            "buh_step1_kw": 3.0,
            "buh_step2_kw": 6.0,
        }
    }
    asyncio.run(f.async_step_cop_calc(payload))
    f.async_create_entry.assert_called_once()
    merged = f.async_create_entry.call_args.kwargs["data"]
    assert merged["supply_phases"] == "3"
    assert merged["buh_step2_kw"] == 6.0
    assert merged["existing"] == "keep"
    # #244: sensor mappings preserved (was: wiped to None before fix)
    assert merged["power_sensor_entity"] == "sensor.power"
    assert merged["cop_sensor_entity"] == "sensor.cop"
    assert merged["indoor_temp_sensor"] == "sensor.indoor"
