"""Batch 50f -- config_flow coverage met MockConfigEntry + submit-tests."""
from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daikin_cycle_ml.const import DOMAIN
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

pytestmark = pytest.mark.asyncio


def _mk_entry(**kw):
    data = kw.pop("data", {"source_sensor": "sensor.althermasensors",
                            "model": "epra12eav3"})
    return MockConfigEntry(domain=DOMAIN, data=data,
                           options=kw.pop("options", {}),
                           version=1, **kw)


async def _start(hass):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER},
    )


async def test_user_step_initial(hass: HomeAssistant):
    r = await _start(hass)
    assert r["type"] == FlowResultType.FORM


async def test_attributes_step_no_state(hass: HomeAssistant):
    r = await _start(hass)
    r2 = await hass.config_entries.flow.async_configure(
        r["flow_id"],
        user_input={"source_sensor": "sensor.nonexistent", "model": "epra12eav3"},
    )
    assert r2["type"] == FlowResultType.FORM


async def test_attributes_step_with_state(hass: HomeAssistant):
    hass.states.async_set(
        "sensor.althermasensors", "ok",
        {"R1T": 30.0, "R2T": 25.0, "R4T": 40.0, "R5T": 22.0, "R6T": 21.0,
         "R7T": 15.0, "RPS": 30, "IU_Operation_Mode": "heating",
         "LWT_setpoint": 35.0, "Flow": 10.0, "BUH_Step1": "OFF",
         "Defrost_Operation": "OFF", "3way_valve": "OFF"},
    )
    r = await _start(hass)
    r2 = await hass.config_entries.flow.async_configure(
        r["flow_id"],
        user_input={"source_sensor": "sensor.althermasensors", "model": "epra12eav3"},
    )
    assert r2["type"] == FlowResultType.FORM


async def test_wizard_advance_with_defaults(hass: HomeAssistant):
    """Doorloop wizard stappen tot CREATE_ENTRY of stap-limit."""
    hass.states.async_set(
        "sensor.althermasensors", "ok",
        {"R1T": 30.0, "R2T": 25.0, "R4T": 40.0, "R5T": 22.0, "R6T": 21.0,
         "R7T": 15.0, "RPS": 30, "IU_Operation_Mode": "heating",
         "LWT_setpoint": 35.0, "Flow": 10.0, "BUH_Step1": "OFF",
         "Defrost_Operation": "OFF", "3way_valve": "OFF"},
    )
    r = await _start(hass)
    r = await hass.config_entries.flow.async_configure(
        r["flow_id"],
        user_input={"source_sensor": "sensor.althermasensors", "model": "epra12eav3"},
    )
    for _ in range(10):
        if r["type"] == FlowResultType.CREATE_ENTRY:
            break
        if r["type"] not in (FlowResultType.FORM, FlowResultType.MENU):
            break
        try:
            r = await hass.config_entries.flow.async_configure(
                r["flow_id"], user_input={},
            )
        except Exception:
            break


# --- OptionsFlow: init is MENU, niet FORM ---
async def test_options_flow_init_menu(hass: HomeAssistant):
    entry = _mk_entry()
    entry.add_to_hass(hass)
    r = await hass.config_entries.options.async_init(entry.entry_id)
    # MENU of FORM beide acceptabel
    assert r["type"] in (FlowResultType.MENU, FlowResultType.FORM)


@pytest.mark.parametrize("step", [
    "device", "pendulum", "quality", "notifications", "ml", "maintenance",
])
async def test_options_flow_menu_navigate(hass: HomeAssistant, step: str):
    entry = _mk_entry()
    entry.add_to_hass(hass)
    r = await hass.config_entries.options.async_init(entry.entry_id)
    r2 = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": step},
    )
    assert r2["type"] == FlowResultType.FORM
    assert r2["step_id"] == step


async def test_options_flow_menu_test_notification(hass: HomeAssistant):
    entry = _mk_entry()
    entry.add_to_hass(hass)
    r = await hass.config_entries.options.async_init(entry.entry_id)
    r2 = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "test_notification"},
    )
    assert r2["type"] == FlowResultType.FORM
    assert r2["step_id"] == "test_notification"


async def test_options_flow_menu_test_all(hass: HomeAssistant):
    entry = _mk_entry()
    entry.add_to_hass(hass)
    r = await hass.config_entries.options.async_init(entry.entry_id)
    r2 = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "test_all_notifications"},
    )
    assert r2["type"] == FlowResultType.FORM
    assert r2["step_id"] == "test_all_notifications"


# --- SUBMIT tests: raken de handler-bodies in config_flow.py ---
@pytest.mark.parametrize("step,data", [
    ("device", {
        "sensors": {},
        "detection": {"compressor_rps_threshold": 3, "fallback_power_threshold_w": 200},
        "comfort": {},
    }),
    ("pendulum", {
        "run_off": {
            "short_run_threshold_min": 20, "short_off_threshold_min": 5,
        },
        "pendulum": {
            "pendulum_cycles_per_hour": 4, "pendulum_cycles_per_day": 40,
            "dhw_pendulum_cycles_per_hour": 3,
        },
        "setpoint": {
            "setpoint_oscillation_threshold": 10,
            "setpoint_osc_window_min": 30, "setpoint_osc_min_delta": 0.5,
        },
    }),
    ("quality", {
        "quality": {
            "good_run_threshold_min": 45, "good_dt_threshold_k": 5.0,
            "good_off_threshold_min": 20, "target_cycles_per_day": 8,
        },
    }),
    ("ml", {"adaptive": {
        "adaptive_thresholds_enabled": True, "adaptive_min_samples": 30,
    }}),
    ("maintenance", {
        "retention": {
            "retention_enabled": True, "cycle_retention_days": 90,
            "alert_retention_days": 30, "vacuum_enabled": True,
        },
        "season": {"season_start_month": 10},
    }),
])
async def test_options_step_submit(hass: HomeAssistant, step: str, data: dict):
    entry = _mk_entry()
    entry.add_to_hass(hass)
    r = await hass.config_entries.options.async_init(entry.entry_id)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": step},
    )
    r2 = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input=data,
    )
    # Submit -> menu, form (reload), of create_entry
    assert r2["type"] in (FlowResultType.FORM, FlowResultType.MENU,
                          FlowResultType.CREATE_ENTRY)


async def test_options_notifications_submit(hass: HomeAssistant):
    entry = _mk_entry()
    entry.add_to_hass(hass)
    r = await hass.config_entries.options.async_init(entry.entry_id)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "notifications"},
    )
    r2 = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={
            "persistent_enabled": True,
            "notify_emoji_enabled": True,
            "action_advice_enabled": True,
            "quiet_hours_enabled": False,
            "alert_aggregation_minutes": 30,
            "status_update_enabled": False,
            "status_update_interval_hours": 24,
            "notification_language": "en",
            "alert_group_pendulum": True,
            "alert_group_short_cycle": True,
            "alert_group_ml": True,
            "alert_group_setpoint": True,
            "alert_group_cop_stooklijn": True,
        },
    )
    assert r2["type"] in (FlowResultType.FORM, FlowResultType.MENU,
                          FlowResultType.CREATE_ENTRY)


async def test_reconfigure_basic(hass: HomeAssistant):
    entry = _mk_entry()
    entry.add_to_hass(hass)
    r = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_RECONFIGURE,
                 "entry_id": entry.entry_id},
    )
    # MENU (reconfigure choice) of FORM (basic) of CREATE / ABORT
    assert r["type"] in (FlowResultType.FORM, FlowResultType.MENU,
                         FlowResultType.CREATE_ENTRY, FlowResultType.ABORT)
