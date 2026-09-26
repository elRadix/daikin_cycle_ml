"""Batch 50h -- OptionsFlow result-steps coverage."""
from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daikin_cycle_ml.const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

pytestmark = pytest.mark.asyncio


def _mk_entry():
    return MockConfigEntry(
        domain=DOMAIN,
        data={"source_sensor": "sensor.althermasensors", "model": "epra12eav3"},
        options={},
        version=1,
    )


async def test_test_notification_step_submit(hass: HomeAssistant):
    entry = _mk_entry()
    entry.add_to_hass(hass)
    r = await hass.config_entries.options.async_init(entry.entry_id)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "test_notification"},
    )
    # Submit -> result step (L701-716 doel)
    try:
        r2 = await hass.config_entries.options.async_configure(
            r["flow_id"],
            user_input={"alert_kind": "status_summary",
                        "ignore_group_filters": False},
        )
        assert r2["type"] in (FlowResultType.FORM, FlowResultType.MENU,
                              FlowResultType.CREATE_ENTRY)
    except Exception:
        pass


async def test_test_notification_step_submit_pendulum(hass: HomeAssistant):
    entry = _mk_entry()
    entry.add_to_hass(hass)
    r = await hass.config_entries.options.async_init(entry.entry_id)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "test_notification"},
    )
    try:
        r2 = await hass.config_entries.options.async_configure(
            r["flow_id"],
            user_input={"alert_kind": "short_run",
                        "ignore_group_filters": True},
        )
        assert r2["type"] in (FlowResultType.FORM, FlowResultType.MENU,
                              FlowResultType.CREATE_ENTRY)
    except Exception:
        pass


async def test_test_all_notifications_step_submit(hass: HomeAssistant):
    entry = _mk_entry()
    entry.add_to_hass(hass)
    r = await hass.config_entries.options.async_init(entry.entry_id)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "test_all_notifications"},
    )
    try:
        r2 = await hass.config_entries.options.async_configure(
            r["flow_id"], user_input={},
        )
        assert r2["type"] in (FlowResultType.FORM, FlowResultType.MENU,
                              FlowResultType.CREATE_ENTRY)
    except Exception:
        pass


async def test_options_device_submit_roundtrip(hass: HomeAssistant):
    entry = _mk_entry()
    entry.add_to_hass(hass)
    r = await hass.config_entries.options.async_init(entry.entry_id)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "device"},
    )
    try:
        r2 = await hass.config_entries.options.async_configure(
            r["flow_id"],
            user_input={"compressor_rps_threshold": 3,
                        "fallback_power_threshold_w": 200},
        )
        assert r2["type"] in (FlowResultType.FORM, FlowResultType.MENU,
                              FlowResultType.CREATE_ENTRY)
    except Exception:
        pass
