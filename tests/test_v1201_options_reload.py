"""v1.20.1: Options reload listener (#286).

Fixes stale self.options fingerprint causing cycle-321 quality drift.
Coordinator options loaded at setup must refresh when user changes them
via OptionsFlow. Standard HA pattern: entry.add_update_listener triggers
config_entries.async_reload.
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# --- RED tests -------------------------------------------------------------


@pytest.mark.asyncio
async def test_options_update_triggers_reload():
    """RED: _async_options_updated calls config_entries.async_reload."""
    from custom_components.daikin_cycle_ml import _async_options_updated

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
    """RED: module exports _async_options_updated."""
    from custom_components.daikin_cycle_ml import _async_options_updated

    assert callable(_async_options_updated)


def test_setup_entry_registers_options_listener():
    """RED: async_setup_entry wires entry.add_update_listener."""
    src = Path(
        "custom_components/daikin_cycle_ml/__init__.py"
    ).read_text()
    tree = ast.parse(src)
    lines = src.splitlines()
    found = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AsyncFunctionDef)
            and node.name == "async_setup_entry"
        ):
            body = "\n".join(lines[node.lineno - 1 : node.end_lineno])
            if (
                "add_update_listener" in body
                and "_async_options_updated" in body
            ):
                found = True
            break
    assert found, (
        "async_setup_entry does not register _async_options_updated "
        "via entry.add_update_listener"
    )
