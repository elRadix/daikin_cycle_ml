"""v1.20.1: Options reload listener (#286) + waiver UI (#289).

Root cause (cycle-321 fingerprint 60/5.0):
- coordinator.options is a snapshot at __init__, never refreshed
- OptionsFlow saves to entry.options via async_update_entry
- Running coordinator keeps stale options until HA restart

Fix: standard HA pattern — entry.add_update_listener triggers
config_entries.async_reload, which rebuilds coordinator with fresh
entry.options and refreshes every dependent (detector, scoring,
alerts, notify).

Also covers #289: OptionsFlow quality_ml step exposes
buh_penalty_legionella_waived checkbox (behavioral test via _save).

Note: imports at module level (not in-function) — phcc plugin rewrites
sys.path after collection; in-function imports of custom_components
would fail with ModuleNotFoundError.
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml import _async_options_updated
from custom_components.daikin_cycle_ml.config_flow import (
    DaikinCycleMLConfigFlow,
    DaikinCycleMLOptionsFlow,
)

# --- #286: reload listener ------------------------------------------------


@pytest.mark.asyncio
async def test_options_update_triggers_reload():
    """_async_options_updated calls config_entries.async_reload(entry_id)."""
    hass = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_reload = AsyncMock()
    entry = MagicMock()
    entry.entry_id = "test_entry_123"

    await _async_options_updated(hass, entry)

    hass.config_entries.async_reload.assert_awaited_once_with(
        "test_entry_123"
    )


def test_options_updated_function_exists():
    """Module exports _async_options_updated (callable)."""
    assert callable(_async_options_updated)


def test_setup_entry_registers_options_listener():
    """Structural: async_setup_entry wires listener via the helper.

    #311: the listener is now registered through
    _maybe_register_options_listener() so the conditional can be tested
    independently of HA's OptionsFlowWithReload behaviour.
    """
    src = Path(
        "custom_components/daikin_cycle_ml/__init__.py"
    ).read_text()
    tree = ast.parse(src)
    lines = src.splitlines()

    setup_calls_helper = False
    helper_registers = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AsyncFunctionDef)
            and node.name == "async_setup_entry"
        ):
            body = "\n".join(lines[node.lineno - 1 : node.end_lineno])
            if "_maybe_register_options_listener(entry)" in body:
                setup_calls_helper = True
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == "_maybe_register_options_listener"
        ):
            body = "\n".join(lines[node.lineno - 1 : node.end_lineno])
            if (
                "add_update_listener" in body
                and "_async_options_updated" in body
            ):
                helper_registers = True

    assert setup_calls_helper, (
        "async_setup_entry does not call _maybe_register_options_listener"
    )
    assert helper_registers, (
        "_maybe_register_options_listener does not register "
        "_async_options_updated via entry.add_update_listener"
    )


# --- #289: waiver checkbox in both flows ---------------------------------


@pytest.mark.asyncio
async def test_options_flow_quality_ml_waiver_in_section(hass):
    """OptionsFlow quality_ml: waiver field inside 'quality' section."""
    flow = DaikinCycleMLOptionsFlow()
    flow.hass = hass
    entry = MagicMock()
    entry.options = {}
    entry.data = {}
    entry.entry_id = "test_entry"
    flow.handler = "test_entry"
    flow.context = {"entry_id": "test_entry"}
    hass.config_entries.async_get_entry = MagicMock(return_value=entry)

    result = await flow.async_step_quality_ml()
    assert result["type"] == "form"
    assert result["step_id"] == "quality_ml"

    schema = result["data_schema"].schema
    quality_section = None
    for k in schema:
        if hasattr(k, "schema") and str(k) == "quality":
            quality_section = schema[k]
            break

    assert quality_section is not None, "quality section not found"
    # Section value is voluptuous.Schema; .schema attribute is the raw dict
    inner_schema = quality_section.schema.schema
    inner_keys = [str(ik) for ik in inner_schema]
    assert any("buh_penalty_legionella_waived" in ik for ik in inner_keys), (
        f"waiver not in quality section; inner keys={inner_keys}"
    )


@pytest.mark.asyncio
async def test_options_flow_save_persists_waiver_false(hass):
    """Behavioral: user disables waiver -> async_create_entry receives False.

    _save flattens the section input and calls async_create_entry(data=merged).
    We capture the ConfigFlowResult's 'data' dict to verify the waiver
    value made it through flattening + merge with existing entry.options.
    """
    flow = DaikinCycleMLOptionsFlow()
    flow.hass = hass
    entry = MagicMock()
    entry.options = {}
    entry.data = {}
    entry.entry_id = "test_entry"
    flow.handler = "test_entry"
    flow.context = {"entry_id": "test_entry"}
    hass.config_entries.async_get_entry = MagicMock(return_value=entry)

    user_input = {
        "quality": {
            "good_run_threshold_min": 45,
            "good_dt_threshold_k": 5.0,
            "good_off_threshold_min": 20,
            "target_cycles_per_day": 8,
            "buh_penalty_legionella_waived": False,
        },
        "adaptive": {
            "adaptive_thresholds_enabled": True,
            "adaptive_min_samples": 20,
        },
    }

    result = await flow.async_step_quality_ml(user_input)
    assert result["type"] == "create_entry"
    data = result.get("data") or {}
    assert data.get("buh_penalty_legionella_waived") is False, (
        f"waiver not in create_entry data; got={data}"
    )


@pytest.mark.asyncio
async def test_wizard_quality_step_has_waiver_checkbox(hass):
    """ConfigFlow (wizard) quality step exposes waiver checkbox."""
    flow = DaikinCycleMLConfigFlow()
    flow.hass = hass
    flow._options = {}

    result = await flow.async_step_quality()
    assert result["type"] == "form"
    assert result["step_id"] == "quality"
    schema = result["data_schema"].schema
    keys = [str(k) for k in schema]
    assert any("buh_penalty_legionella_waived" in k for k in keys), (
        f"wizard quality step missing waiver; keys={keys}"
    )
