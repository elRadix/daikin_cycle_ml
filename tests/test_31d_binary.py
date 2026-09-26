"""Batch 31d tests: 15 binary sensors."""
from __future__ import annotations

import inspect

from custom_components.daikin_cycle_ml import binary_sensor as bs_mod


def test_binary_defs_has_15():
    keys = [spec["key"] for spec in bs_mod.BINARY_SENSOR_DEFS]
    assert len(keys) == 15
    assert set(keys) == {
        "compressor_running", "pendulum_hourly", "pendulum_daily",
        "short_run", "short_off", "defrost_active", "buh_active",
        "dhw_active", "heating_active", "cooling_active",
        "source_stale", "missing_attrs", "setpoint_oscillating",
        "dhw_pendulum", "high_cycle_rate",
    }


def test_no_cluster_binaries():
    keys = {spec["key"] for spec in bs_mod.BINARY_SENSOR_DEFS}
    for old in ("cluster_pendulum", "cluster_normal", "cluster_dhw_like"):
        assert old not in keys


def test_no_buh_step_binaries():
    keys = {spec["key"] for spec in bs_mod.BINARY_SENSOR_DEFS}
    assert "buh_step1_active" not in keys
    assert "buh_step2_active" not in keys


def test_buh_active_has_step_attr():
    spec = next(s for s in bs_mod.BINARY_SENSOR_DEFS if s["key"] == "buh_active")
    assert "attr_fn" in spec


def test_buh_helpers():
    assert hasattr(bs_mod, "_is_buh_active")
    assert hasattr(bs_mod, "_buh_step")
    assert hasattr(bs_mod, "_buh_attrs")


def test_buh_step_logic_bool_attrs():
    class Snap:
        attrs = {"BUH Step1": True, "BUH Step2": False}
    assert bs_mod._buh_step(Snap(), None) == 1
    class Snap2:
        attrs = {"BUH Step1": True, "BUH Step2": True}
    assert bs_mod._buh_step(Snap2(), None) == 2
    class Snap3:
        attrs = {}
    assert bs_mod._buh_step(Snap3(), None) == 0


def test_no_cluster_class_in_module():
    src = inspect.getsource(bs_mod)
    assert "ClusterBinary" not in src
    assert "_build_cluster_binaries" not in src
