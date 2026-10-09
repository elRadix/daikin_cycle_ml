"""v1.9.0 PR D — config-flow coverage for notifications_dedup step.

Covers async_step_notifications_dedup (form render + submit).
Follows the canonical OptionsFlow test pattern from
tests/test_18_options_menu.py.

Refs #66.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daikin_cycle_ml import const
from custom_components.daikin_cycle_ml.const import DOMAIN


@pytest.fixture(autouse=True)
def _disable_options_reload(hass):
    """OptionsFlowWithReload triggers reload; skip in unit tests."""
    with patch.object(
        hass.config_entries, "async_reload",
        new=AsyncMock(return_value=True),
    ), patch.object(
        hass.config_entries, "async_schedule_reload",
        new=lambda *a, **k: None,
    ):
        yield


async def _start(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"source_sensor": "sensor.x", "model": "epra12eav3"},
        options={},
    )
    entry.add_to_hass(hass)
    return await hass.config_entries.options.async_init(entry.entry_id)


async def test_notifications_dedup_renders_form(hass):
    """Step renders a form with all 8 alert_agg_*_min fields."""
    r = await _start(hass)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "notifications"}
    )
    assert r["type"] == "menu"
    assert "notifications_dedup" in r["menu_options"]

    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "notifications_dedup"}
    )
    assert r["type"] == "form"
    assert r["step_id"] == "notifications_dedup"
    schema = r["data_schema"].schema
    field_names = {str(k) for k in schema}
    for alert_type in const.ALERT_DEDUP_DEFAULTS:
        expected = f"alert_agg_{alert_type}_min"
        assert expected in field_names, f"missing field {expected}"
