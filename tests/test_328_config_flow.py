"""#328 Phase 4: ConfigFlow UI for dhw_present option.

HA 2024.12+ API: OptionsFlow takes no __init__ args.
HA 2026.x: vol.Required wraps static defaults in a default_factory lambda,
so `.default` returns a callable — resolve via _resolve_default().
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from custom_components.daikin_cycle_ml.const import (
    CONF_DHW_PRESENT, DHW_PRESENT_AUTO, DHW_PRESENT_ALWAYS,
    DHW_PRESENT_NEVER,
)
from custom_components.daikin_cycle_ml.config_flow import (
    DaikinCycleMLOptionsFlow,
)


def _find_dhw_key(schema):
    for k in schema.schema.keys():
        if "dhw_present" in str(k):
            return k
    return None


def _resolve_default(key):
    """HA 2026.x wraps defaults in a factory lambda — resolve it."""
    raw = getattr(key, "default", None)
    if callable(raw):
        return raw()
    if raw is not None:
        return raw
    df = getattr(key, "default_factory", None)
    if df is not None and callable(df):
        return df()
    return df


def _ce(entry):
    return patch.object(
        DaikinCycleMLOptionsFlow, "config_entry",
        new_callable=PropertyMock, return_value=entry,
    )


# === Schema exposure ===

@pytest.mark.asyncio
async def test_advanced_schema_has_dhw_present(hass):
    entry = MagicMock(); entry.options = {}; entry.data = {}
    with _ce(entry):
        flow = DaikinCycleMLOptionsFlow(); flow.hass = hass
        res = await flow.async_step_advanced()
    assert _find_dhw_key(res["data_schema"]) is not None


@pytest.mark.asyncio
async def test_advanced_schema_dhw_present_default_is_auto(hass):
    entry = MagicMock(); entry.options = {}; entry.data = {}
    with _ce(entry):
        flow = DaikinCycleMLOptionsFlow(); flow.hass = hass
        res = await flow.async_step_advanced()
    key = _find_dhw_key(res["data_schema"])
    assert _resolve_default(key) == DHW_PRESENT_AUTO, \
        f"resolved={_resolve_default(key)!r}"


@pytest.mark.asyncio
async def test_advanced_schema_dhw_present_respects_existing(hass):
    entry = MagicMock()
    entry.options = {CONF_DHW_PRESENT: DHW_PRESENT_NEVER}
    entry.data = {}
    with _ce(entry):
        flow = DaikinCycleMLOptionsFlow(); flow.hass = hass
        res = await flow.async_step_advanced()
    key = _find_dhw_key(res["data_schema"])
    assert _resolve_default(key) == DHW_PRESENT_NEVER, \
        f"resolved={_resolve_default(key)!r}"


# === Save routes dhw_present into create_entry payload ===

@pytest.mark.asyncio
async def test_options_save_routes_dhw_present(hass):
    entry = MagicMock(); entry.options = {}; entry.data = {}
    with _ce(entry), \
         patch.object(DaikinCycleMLOptionsFlow, "async_create_entry") as ace:
        ace.return_value = {"type": "create_entry"}
        flow = DaikinCycleMLOptionsFlow(); flow.hass = hass
        flow._save({CONF_DHW_PRESENT: DHW_PRESENT_NEVER})
    ace.assert_called_once()
    data = ace.call_args.kwargs.get("data", {})
    assert data.get(CONF_DHW_PRESENT) == DHW_PRESENT_NEVER, f"payload={data}"


# === Reload listener wired ===

def test_options_update_listener_is_wired():
    from pathlib import Path
    src = Path("custom_components/daikin_cycle_ml/__init__.py").read_text()
    assert "add_update_listener(_async_options_updated)" in src
    assert "async_reload(entry.entry_id)" in src


# === Reconfigure path exists ===

@pytest.mark.asyncio
async def test_reconfigure_full_exists(hass):
    from custom_components.daikin_cycle_ml.config_flow import (
        DaikinCycleMLConfigFlow,
    )
    assert hasattr(DaikinCycleMLConfigFlow, "async_step_reconfigure")
    assert hasattr(DaikinCycleMLConfigFlow, "async_step_reconfigure_full")
    assert hasattr(DaikinCycleMLConfigFlow, "async_step_reconfigure_basic")


@pytest.mark.asyncio
async def test_reconfigure_preserves_options(hass):
    from pathlib import Path
    src = Path("custom_components/daikin_cycle_ml/config_flow.py").read_text()
    assert "config_entry.options" in src
