"""Verify help texts (data_description) are present in strings + translations."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

FILES = [
    ROOT / "strings.json",
    ROOT / "translations" / "en.json",
    ROOT / "translations" / "nl.json",
]

EXPECTED = {
    "user": ["source_sensor", "model"],
    "model_custom": ["custom_attribute_map"],
    "cycle": [
        "compressor_rps_threshold",
        "power_sensor_entity",
        "fallback_power_threshold_w",
    ],
    "pendulum": [
        "short_run_threshold_min",
        "short_off_threshold_min",
        "pendulum_cycles_per_day",
        "dhw_pendulum_cycles_per_hour",
    ],
    "quality": [
        "good_run_threshold_min",
        "good_dt_threshold_k",
        "good_off_threshold_min",
        "target_cycles_per_day",
    ],
    "notifications": [
        "persistent_enabled",
        "notify_service",
        "quiet_hours_enabled",
        "quiet_hours_start",
        "quiet_hours_end",
    ],
}

OPTIONS_EXPECTED = [
    "compressor_rps_threshold",
    "short_run_threshold_min",
    "pendulum_cycles_per_day",
    "good_run_threshold_min",
    "persistent_enabled",
]


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_config_steps_have_data_description(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    steps = data["config"]["step"]
    for step_id, fields in EXPECTED.items():
        assert step_id in steps, f"{path.name}: missing step {step_id}"
        dd = steps[step_id].get("data_description", {})
        for field in fields:
            assert field in dd, f"{path.name}: {step_id}.{field} no data_description"


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_reconfigure_menu_present(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    steps = data["config"]["step"]
    assert "reconfigure" in steps
    menu = steps["reconfigure"].get("menu_options", {})
    assert "reconfigure_basic" in menu
    assert "reconfigure_full" in menu


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_reconfigure_basic_step_has_descriptions(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    step = data["config"]["step"]["reconfigure_basic"]
    assert "source_sensor" in step["data_description"]
    assert "model" in step["data_description"]


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_options_step_has_data_description(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    init = data["options"]["step"]["init"]
    dd = init.get("data_description", {})
    for field in OPTIONS_EXPECTED:
        assert field in dd, f"{path.name}: options.{field} no data_description"
