"""Tests for 12a-3: learned threshold sensors + translations."""
from __future__ import annotations

import json
from pathlib import Path

from custom_components.daikin_cycle_ml import sensor as smod

ROOT = Path(__file__).resolve().parent.parent


def test_adaptive_sensor_defs_exist():
    assert hasattr(smod, "ADAPTIVE_SENSOR_DEFS")
    assert len(smod.ADAPTIVE_SENSOR_DEFS) == 3


def test_sensor_defs_contains_adaptive_keys():
    keys = {d["key"] for d in smod.SENSOR_DEFS}
    for k in (
        "learned_short_run_min",
        "learned_good_off_min",
        "learned_target_cycles_per_day",
    ):
        assert k in keys


def test_adaptive_defs_have_value_fn():
    for d in smod.ADAPTIVE_SENSOR_DEFS:
        assert callable(d.get("value_fn"))


def test_adaptive_run_off_have_duration_unit():
    by_key = {d["key"]: d for d in smod.ADAPTIVE_SENSOR_DEFS}
    for k in ("learned_short_run_min", "learned_good_off_min"):
        d = by_key[k]
        assert d.get("unit") is not None
        assert d.get("device_class") is not None


def test_en_translations_have_adaptive_sensor_keys():
    data = json.loads((ROOT / "translations" / "en.json").read_text())
    keys = data["entity"]["sensor"]
    for k in (
        "learned_short_run_min",
        "learned_good_off_min",
        "learned_target_cycles_per_day",
    ):
        assert k in keys


def test_nl_translations_have_adaptive_sensor_keys():
    data = json.loads((ROOT / "translations" / "nl.json").read_text())
    keys = data["entity"]["sensor"]
    for k in (
        "learned_short_run_min",
        "learned_good_off_min",
        "learned_target_cycles_per_day",
    ):
        assert k in keys

