"""Batch 31c tests: 9 container sensors."""
from __future__ import annotations

import inspect

from custom_components.daikin_cycle_ml import sensor as s_mod


def test_sensor_defs_has_9_containers():
    keys = [spec["key"] for spec in s_mod.SENSOR_DEFS]
    assert len(keys) == 9
    assert set(keys) == {
        "cycle_state", "current_cycle", "last_cycle", "today",
        "quality_today", "source_health", "learned_thresholds",
        "cop_vandaag", "stooklijn_advies",
    }


def test_container_sensors_have_attr_fn():
    containers_with_attrs = {
        "current_cycle", "last_cycle", "today", "quality_today",
        "source_health", "learned_thresholds", "cop_vandaag",
        "stooklijn_advies",
    }
    for spec in s_mod.SENSOR_DEFS:
        if spec["key"] in containers_with_attrs:
            assert "attr_fn" in spec, f"{spec['key']} missing attr_fn"


def test_sensor_class_has_extra_state_attributes():
    src = inspect.getsource(s_mod.DaikinCycleMLSensor)
    assert "extra_state_attributes" in src
    assert "_attr_fn" in src


def test_no_old_sensor_keys():
    keys = {spec["key"] for spec in s_mod.SENSOR_DEFS}
    for old in (
        "current_cycle_duration", "current_cycle_mode", "current_dt", "current_rps",
        "last_cycle_duration", "last_cycle_mode", "last_cycle_dt_max",
        "cycles_today", "cycles_last_hour", "short_runs_today",
        "buh_step1_active", "buh_step2_active",
        "cluster_pendulum", "cluster_normal", "cluster_dhw_like",
    ):
        assert old not in keys, f"old key still present: {old}"


def test_helpers_present():
    for fn in ("_avg", "_max_or_none", "_min_or_none", "_ratio",
               "_dt_from_attrs", "_rps_from_attrs", "_avg_off_time"):
        assert hasattr(s_mod, fn), f"missing helper {fn}"
