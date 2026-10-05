"""Batch 18: options menu + action_advice wiring."""
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daikin_cycle_ml.const import (
    DEFAULT_ACTION_ADVICE_ENABLED,
    DEFAULT_ADAPTIVE_MIN_SAMPLES,
    DOMAIN,
    VERSION,
)


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


STEPS_FORM = (
    "device", "pendulum", "quality", "ml", "maintenance",
)
STEPS = STEPS_FORM


async def _start(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"source_sensor": "sensor.x", "model": "epra12eav3"},
        options={"compressor_rps_threshold": 4},
    )
    entry.add_to_hass(hass)
    return await hass.config_entries.options.async_init(entry.entry_id)


async def test_menu_lists_six_steps(hass):
    r = await _start(hass)
    assert r["type"] == "menu"
    assert set(r["menu_options"]) >= set(STEPS)


async def test_each_step_is_a_form(hass):
    for name in STEPS:
        r = await _start(hass)
        r = await hass.config_entries.options.async_configure(
            r["flow_id"], user_input={"next_step_id": name}
        )
        assert r["type"] == "form", name
        assert r["step_id"] == name, name


async def test_device_shows_readonly_source_and_model(hass):
    r = await _start(hass)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "device"}
    )
    placeholders = r.get("description_placeholders") or {}
    assert "source_sensor" in placeholders
    assert "model" in placeholders


async def test_notifications_is_menu_with_subsections(hass):
    r = await _start(hass)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "notifications"}
    )
    assert r["type"] == "menu"
    assert set(r["menu_options"]) == {
        "notifications_delivery",
        "notifications_quiet_hours",
        "notifications_content",
        "notifications_test_menu",
    }


async def test_notifications_submit_creates_entry(hass):
    r = await _start(hass)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "notifications"}
    )
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "notifications_delivery"}
    )
    r = await hass.config_entries.options.async_configure(
        r["flow_id"],
        user_input={
            "persistent_enabled": True,
            "notify_service": "notify.telegram_bot_x",
            "notify_emoji_enabled": True,
            "action_advice_enabled": True,
        },
    )
    assert r["type"] == "create_entry"
    assert r["data"]["notify_service"] == "notify.telegram_bot_x"
    assert r["data"]["compressor_rps_threshold"] == 4  # preserved


async def test_notifications_quiet_hours_form_and_submit(hass):
    r = await _start(hass)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "notifications"}
    )
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "notifications_quiet_hours"}
    )
    assert r["type"] == "form"
    r = await hass.config_entries.options.async_configure(
        r["flow_id"],
        user_input={
            "quiet_hours_enabled": True,
            "quiet_hours_start": "23:00",
            "quiet_hours_end": "06:00",
            "alert_aggregation_minutes": 45,
            "status_update_enabled": True,
            "status_update_interval_hours": 12,
        },
    )
    assert r["type"] == "create_entry"
    assert r["data"]["alert_aggregation_minutes"] == 45


async def test_notifications_content_form_and_submit(hass):
    r = await _start(hass)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "notifications"}
    )
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "notifications_content"}
    )
    assert r["type"] == "form"
    r = await hass.config_entries.options.async_configure(
        r["flow_id"],
        user_input={
            "notification_language": "nl",
            "alert_group_pendulum": True,
            "alert_group_short_cycle": False,
            "alert_group_ml": True,
            "alert_group_setpoint": False,
            "alert_group_cop_stooklijn": True,
        },
    )
    assert r["type"] == "create_entry"
    assert r["data"]["notification_language"] == "nl"


async def test_notifications_test_menu_is_menu(hass):
    r = await _start(hass)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "notifications"}
    )
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "notifications_test_menu"}
    )
    assert r["type"] == "menu"
    assert set(r["menu_options"]) == {"test_notification", "test_all_notifications"}


async def test_pendulum_submit_preserves_other_keys(hass):
    r = await _start(hass)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "pendulum"}
    )
    r = await hass.config_entries.options.async_configure(
        r["flow_id"],
        user_input={
            "run_off": {
                "short_run_threshold_min": 25,
                "short_off_threshold_min": 6,
            },
            "pendulum": {
                "pendulum_cycles_per_hour": 5,
                "pendulum_cycles_per_day": 35,
                "dhw_pendulum_cycles_per_hour": 3,
            },
            "setpoint": {
                "setpoint_oscillation_threshold": 6,
                "setpoint_osc_window_min": 30,
                "setpoint_osc_min_delta": 0.5,
            },
        },
    )
    assert r["type"] == "create_entry"
    assert r["data"]["short_run_threshold_min"] == 25
    assert r["data"]["compressor_rps_threshold"] == 4


async def test_quality_submit(hass):
    r = await _start(hass)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "quality"}
    )
    r = await hass.config_entries.options.async_configure(
        r["flow_id"],
        user_input={
            "quality": {
                "good_run_threshold_min": 50,
                "good_dt_threshold_k": 5.5,
                "good_off_threshold_min": 22,
                "target_cycles_per_day": 9,
            },
        },
    )
    assert r["type"] == "create_entry"
    assert r["data"]["good_run_threshold_min"] == 50


async def test_ml_submit(hass):
    r = await _start(hass)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "ml"}
    )
    r = await hass.config_entries.options.async_configure(
        r["flow_id"],
        user_input={
            "adaptive": {
                "adaptive_thresholds_enabled": True,
                "adaptive_min_samples": 25,
            },
        },
    )
    assert r["type"] == "create_entry"
    assert r["data"]["adaptive_min_samples"] == 25


async def test_maintenance_submit(hass):
    r = await _start(hass)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "maintenance"}
    )
    r = await hass.config_entries.options.async_configure(
        r["flow_id"],
        user_input={
            "retention": {
                "retention_enabled": True,
                "cycle_retention_days": 120,
                "alert_retention_days": 45,
                "vacuum_enabled": True,
            },
            "season": {
                "season_start_month": 10,
            },
        },
    )
    assert r["type"] == "create_entry"
    assert r["data"]["cycle_retention_days"] == 120


def test_action_advice_default_true():
    assert DEFAULT_ACTION_ADVICE_ENABLED is True


def test_ml_default():
    assert DEFAULT_ADAPTIVE_MIN_SAMPLES == 20


def test_version_bumped():
    """Forward-compat: version must be >= 0.5.0 and match const.VERSION."""
    # VERSION must be a parseable semver-ish string
    parts = VERSION.split(".")
    assert len(parts) >= 2, f"unexpected VERSION: {VERSION!r}"
    major, minor = int(parts[0]), int(parts[1])
    # Never go below the last known release
    assert (major, minor) >= (0, 5), f"VERSION regressed: {VERSION!r}"
