"""Config-flow integration tests for smart auto-import (issue #51).

Covers the diagnose-step wiring added in commit 2:

- Laag 1-3 smart fallback in async_step_user (missing exact attrs but
  >= 3 canonicals resolvable via alias/fuzzy)
- Laag 4 diagnose step shows report + warnings placeholders
- Internal _smart_available key is popped before finalize
- Backward compat: default sensor.althermasensors without aliases still
  follows the original AUTO path
"""
from __future__ import annotations

from typing import Any

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daikin_cycle_ml.const import (
    ATTR_3WAY_VALVE,
    ATTR_LEAVING_WATER_AFTER_BUH,
    ATTR_LW_SETPOINT,
    ATTR_OPERATION_MODE,
    DOMAIN,
    MODEL_CUSTOM,
    MODEL_EPRA12EAV3,
    SOURCE_SENSOR_ENTITY,
)


def _alias_attrs() -> dict[str, Any]:
    """11 canonical keys via alias-variants (no exact canonical)."""
    return {
        # alias variant of ATTR_3WAY_VALVE
        "3way valve (On:DHW_Off:Space)": 0.0,
        # exact
        ATTR_OPERATION_MODE: "Heating",
        # exact
        "I/U operation mode": "Heating",
        # exact
        "Defrost Operation": 0.0,
        # exact
        ATTR_LEAVING_WATER_AFTER_BUH: 30.0,
        # exact
        "Inlet water temp.(R4T)": 25.0,
        # exact
        "Outdoor air temp.(R1T)": 5.0,
        # exact
        "Flow sensor (l/min)": 12.0,
        # exact
        "Water pump operation": 1.0,
        # alias variant
        "LW setpoint": 35.0,
        # extra so we have >= 3 resolvable
        "BUH Step1": 0.0,
    }


async def _start_user_step(hass: HomeAssistant) -> dict[str, Any]:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    return result


# =========================================================================
# Smart fallback path (Laag 1-3)
# =========================================================================

async def test_smart_fallback_routes_to_diagnose(hass: HomeAssistant) -> None:
    """Missing exact attrs, but >=3 resolvable -> diagnose step."""
    hass.states.async_set("sensor.altherma", "ok", _alias_attrs())
    result = await _start_user_step(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "source_sensor": "sensor.altherma",
            "model": MODEL_EPRA12EAV3,
            "attribute_mode": "auto",
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "diagnose"
    # Placeholders present
    ph = result.get("description_placeholders") or {}
    assert "report_lines" in ph
    assert "warnings" in ph
    assert "missing_count" in ph


async def test_smart_fallback_inv_hz_alias(hass: HomeAssistant) -> None:
    """benthouse variant: INV frequency (Hz) resolves via alias table."""
    attrs = dict(_alias_attrs())
    attrs["INV frequency (Hz)"] = 30.0
    hass.states.async_set("sensor.altherma", "ok", attrs)
    result = await _start_user_step(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "source_sensor": "sensor.altherma",
            "model": MODEL_EPRA12EAV3,
            "attribute_mode": "auto",
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "diagnose"


async def test_smart_fallback_insufficient_routes_to_error(
    hass: HomeAssistant,
) -> None:
    """<3 resolvable canonicals -> fall through to missing_attributes error."""
    hass.states.async_set("sensor.altherma", "ok", {"random_attr": 1})
    result = await _start_user_step(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "source_sensor": "sensor.altherma",
            "model": MODEL_EPRA12EAV3,
            "attribute_mode": "auto",
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"source_sensor": "missing_attributes"}


# =========================================================================
# Diagnose submit -> attributes, internal key popped
# =========================================================================

async def test_diagnose_submit_advances_to_attributes(
    hass: HomeAssistant,
) -> None:
    hass.states.async_set("sensor.altherma", "ok", _alias_attrs())
    result = await _start_user_step(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "source_sensor": "sensor.altherma",
            "model": MODEL_EPRA12EAV3,
            "attribute_mode": "auto",
        },
    )
    assert result["step_id"] == "diagnose"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "attributes"


async def test_diagnose_submit_pops_internal_key(
    hass: HomeAssistant,
) -> None:
    """_smart_available must not leak into the config entry."""
    hass.states.async_set("sensor.altherma", "ok", _alias_attrs())
    result = await _start_user_step(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "source_sensor": "sensor.altherma",
            "model": MODEL_EPRA12EAV3,
            "attribute_mode": "auto",
        },
    )
    handler = hass.config_entries.flow._progress[result["flow_id"]]
    # Before submit: _smart_available is in handler._data
    assert "_smart_available" in handler._data
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {}
    )
    assert result["step_id"] == "attributes"
    # After submit: popped
    assert "_smart_available" not in handler._data


# =========================================================================
# Diagnose -> custom model (issue #51, L286 branch)
# =========================================================================

async def test_diagnose_submit_custom_model_routes_to_model_custom(
    hass: HomeAssistant,
) -> None:
    """Smart fallback + MODEL_CUSTOM -> diagnose submit hits custom branch."""
    hass.states.async_set("sensor.altherma", "ok", _alias_attrs())
    result = await _start_user_step(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "source_sensor": "sensor.altherma",
            "model": MODEL_CUSTOM,
            "attribute_mode": "auto",
        },
    )
    assert result["step_id"] == "diagnose"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "model_custom_info"


# =========================================================================
# Backward compat: exact-match path unchanged
# =========================================================================

async def test_backward_compat_exact_default_sensor(
    hass: HomeAssistant,
) -> None:
    """Legacy path: exact canonical attrs -> no diagnose step."""
    attrs = {
        "INV frequency (rps)": 30.0,
        "Operation Mode": "Heating",
        "I/U operation mode": "Heating",
        "3way valve(On:DHW_Off:Space)": 0.0,
        "Defrost Operation": 0.0,
        "Leaving water temp. after BUH (R2T)": 30.0,
        "Inlet water temp.(R4T)": 25.0,
        "Outdoor air temp.(R1T)": 5.0,
        "Flow sensor (l/min)": 12.0,
        "Water pump operation": 1.0,
        "BUH Step1": 0.0,
        "BUH Step2": 0.0,
        "LW setpoint (main)": 35.0,
    }
    hass.states.async_set(SOURCE_SENSOR_ENTITY, "ok", attrs)
    result = await _start_user_step(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "source_sensor": SOURCE_SENSOR_ENTITY,
            "model": MODEL_EPRA12EAV3,
            "attribute_mode": "auto",
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "attributes"
    # No diagnose detour on the exact-match path
    assert result["step_id"] != "diagnose"


# =========================================================================
# Anti-alias regression in config-flow context (julG COP~11)
# =========================================================================

async def test_anti_alias_r2t_not_resolved_to_r1t(
    hass: HomeAssistant,
) -> None:
    """R2T canonical must not silently map to R1T variant.

    Only 2 canonicals resolvable (Operation Mode + I/U), R2T stays missing
    despite R1T being present -> falls through to error, not diagnose.
    """
    attrs = {
        ATTR_OPERATION_MODE: "Heating",
        "I/U operation mode": "Heating",
        # R1T variant, must NOT match R2T canonical
        "Hydro Module LWT (R1T)": 30.0,
    }
    hass.states.async_set("sensor.hybrid", "ok", attrs)
    result = await _start_user_step(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "source_sensor": "sensor.hybrid",
            "model": MODEL_EPRA12EAV3,
            "attribute_mode": "auto",
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"source_sensor": "missing_attributes"}


