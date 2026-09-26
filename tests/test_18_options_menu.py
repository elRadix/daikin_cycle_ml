"""Batch 18: options menu + action_advice wiring."""
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daikin_cycle_ml.const import (
    DOMAIN,
    DEFAULT_ACTION_ADVICE_ENABLED,
    DEFAULT_ADAPTIVE_MIN_SAMPLES,
    VERSION,
)


STEPS = (
    "device", "pendulum", "quality",
    "notifications", "ml", "maintenance",
)


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
    assert set(r["menu_options"]) == set(STEPS)


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


async def test_notifications_submit_creates_entry(hass):
    r = await _start(hass)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "notifications"}
    )
    r = await hass.config_entries.options.async_configure(
        r["flow_id"],
        user_input={
            "persistent_enabled": True,
            "notify_service": "notify.telegram_bot_x",
            "notify_emoji_enabled": True,
            "action_advice_enabled": True,
            "quiet_hours_enabled": False,
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "07:00",
            "alert_aggregation_minutes": 30,
            "status_update_enabled": False,
            "status_update_interval_hours": 24,
        },
    )
    assert r["type"] == "create_entry"
    assert r["data"]["notify_service"] == "notify.telegram_bot_x"
    assert r["data"]["compressor_rps_threshold"] == 4  # preserved


async def test_pendulum_submit_preserves_other_keys(hass):
    r = await _start(hass)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], user_input={"next_step_id": "pendulum"}
    )
    r = await hass.config_entries.options.async_configure(
        r["flow_id"],
        user_input={
            "short_run_threshold_min": 25,
            "short_off_threshold_min": 6,
            "pendulum_cycles_per_hour": 5,
            "pendulum_cycles_per_day": 35,
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
            "good_run_threshold_min": 50,
            "good_dt_threshold_k": 5.5,
            "good_off_threshold_min": 22,
            "target_cycles_per_day": 9,
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
            "adaptive_thresholds_enabled": True,
            "adaptive_min_samples": 25,
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
            "retention_enabled": True,
            "cycle_retention_days": 120,
            "alert_retention_days": 45,
            "vacuum_enabled": True,
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
    from custom_components.daikin_cycle_ml.const import VERSION
    # VERSION must be a parseable semver-ish string
    parts = VERSION.split(".")
    assert len(parts) >= 2, f"unexpected VERSION: {VERSION!r}"
    major, minor = int(parts[0]), int(parts[1])
    # Never go below the last known release
    assert (major, minor) >= (0, 5), f"VERSION regressed: {VERSION!r}"
