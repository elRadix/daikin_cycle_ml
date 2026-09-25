"""Tests for translation files (Batch 10a)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FILES = {
    "en": ROOT / "translations" / "en.json",
    "nl": ROOT / "translations" / "nl.json",
}

SENSOR_KEYS = [
    "cycle_state", "current_cycle_duration", "current_cycle_mode",
    "current_dt", "current_rps", "last_cycle_duration", "last_cycle_mode",
    "last_cycle_dt_max", "last_cycle_quality", "cycles_today",
    "cycles_last_hour", "short_runs_today", "short_offs_today",
    "short_cycle_ratio", "avg_cycle_duration_today", "avg_off_time_today",
    "longest_cycle_today", "shortest_cycle_today", "avg_quality_today",
    "good_cycles_today", "bad_cycles_today", "good_cycle_ratio",
    "source_age", "missing_attrs_count", "last_sample_age",
    "coordinator_errors",
]

BINARY_KEYS = [
    "compressor_running", "pendulum_hourly", "pendulum_daily",
    "short_run", "short_off", "defrost_active", "buh_step1_active",
    "buh_step2_active", "dhw_active", "heating_active", "cooling_active",
    "source_stale", "missing_attrs", "setpoint_oscillating",
    "dhw_pendulum", "high_cycle_rate",
]


@pytest.mark.parametrize("lang,path", FILES.items(), ids=list(FILES))
def test_entity_sensor_names_present(lang, path):
    data = json.loads(path.read_text(encoding="utf-8"))
    sensor = data["entity"]["sensor"]
    for key in SENSOR_KEYS:
        assert key in sensor, f"{lang}: missing entity.sensor.{key}"
        assert sensor[key]["name"], f"{lang}: empty name for {key}"


@pytest.mark.parametrize("lang,path", FILES.items(), ids=list(FILES))
def test_entity_binary_names_present(lang, path):
    data = json.loads(path.read_text(encoding="utf-8"))
    bs = data["entity"]["binary_sensor"]
    for key in BINARY_KEYS:
        assert key in bs, f"{lang}: missing entity.binary_sensor.{key}"
        assert bs[key]["name"], f"{lang}: empty name for {key}"


@pytest.mark.parametrize("lang,path", FILES.items(), ids=list(FILES))
def test_issues_present(lang, path):
    data = json.loads(path.read_text(encoding="utf-8"))
    issues = data["issues"]
    assert "source_stale" in issues
    assert "missing_attrs" in issues
    for key in ("source_stale", "missing_attrs"):
        assert issues[key]["title"]
        assert issues[key]["description"]


def test_nl_sensor_names_localized():
    en = json.loads(FILES["en"].read_text(encoding="utf-8"))
    nl = json.loads(FILES["nl"].read_text(encoding="utf-8"))
    # At least half the sensor names differ between EN and NL
    diffs = sum(
        1 for k in SENSOR_KEYS
        if en["entity"]["sensor"][k]["name"] != nl["entity"]["sensor"][k]["name"]
    )
    assert diffs >= 15, f"only {diffs} sensor names localized"


def test_nl_issues_localized():
    en = json.loads(FILES["en"].read_text(encoding="utf-8"))
    nl = json.loads(FILES["nl"].read_text(encoding="utf-8"))
    assert en["issues"]["source_stale"]["title"] != nl["issues"]["source_stale"]["title"]
    assert en["issues"]["missing_attrs"]["title"] != nl["issues"]["missing_attrs"]["title"]


def test_strings_json_has_entity_section():
    data = json.loads((ROOT / "strings.json").read_text(encoding="utf-8"))
    assert "entity" in data
    assert "sensor" in data["entity"]
    assert "binary_sensor" in data["entity"]
    assert "issues" in data
