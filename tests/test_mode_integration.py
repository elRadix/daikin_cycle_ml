"""Batch 27a: mode-case integration — detector → snapshot → binary_sensor.

Regression tests for the lowercase/capital mismatch bug where
classify_mode() returned lowercase but binary_sensor compared against
capitalized OP_MODE_* constants, causing heating/cooling/dhw binary
sensors to be permanently off.
"""
from __future__ import annotations

from collections import deque
from unittest.mock import MagicMock

from custom_components.daikin_cycle_ml.const import (
    ATTR_INV_FREQUENCY_RPS,
    ATTR_IU_OPERATION_MODE,
    ATTR_OUTDOOR_AIR_R1T,
    MODE_COOLING,
    MODE_DHW,
    MODE_HEATING,
    MODE_UNKNOWN,
    OP_MODE_COOLING,
    OP_MODE_DHW,
    OP_MODE_HEATING,
)
from custom_components.daikin_cycle_ml.engine.cycle_detector import (
    CycleDetector,
    classify_mode,
)
from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    DataSnapshot,
)


def test_constants_lowercase_match_classify_output():
    """MODE_* constants equal classify_mode outputs."""
    assert classify_mode({ATTR_IU_OPERATION_MODE: OP_MODE_HEATING}) == MODE_HEATING
    assert classify_mode({ATTR_IU_OPERATION_MODE: OP_MODE_COOLING}) == MODE_COOLING
    assert classify_mode({ATTR_IU_OPERATION_MODE: OP_MODE_DHW}) == MODE_DHW
    assert classify_mode({}) == MODE_UNKNOWN


def test_detector_snapshot_mode_is_lowercase():
    det = CycleDetector({})
    det.update(
        {
            ATTR_INV_FREQUENCY_RPS: 40.0,
            ATTR_IU_OPERATION_MODE: OP_MODE_HEATING,
            ATTR_OUTDOOR_AIR_R1T: 8.0,
        },
        now=1000.0,
    )
    snap = det.snapshot()
    assert snap["mode"] == MODE_HEATING  # "heating"


def test_snap_mode_matches_binary_sensor_comparison():
    """The bug: s.mode was lowercase, OP_MODE_* was capital, comparison was False."""
    det = CycleDetector({})
    det.update(
        {
            ATTR_INV_FREQUENCY_RPS: 40.0,
            ATTR_IU_OPERATION_MODE: OP_MODE_HEATING,
        },
        now=1000.0,
    )
    mode = det.snapshot().get("mode", "unknown")

    # Simulate binary_sensor state_fn logic (was buggy):
    old_broken = (mode == OP_MODE_HEATING)      # "heating" == "Heating" → False
    new_fixed = (mode == MODE_HEATING)          # "heating" == "heating" → True

    assert old_broken is False, "sanity: old code truly broken"
    assert new_fixed is True, "new code must match"


def test_binary_sensor_module_uses_MODE_constants():
    """Static check: binary_sensor.py must not compare against OP_MODE_*."""
    import inspect
    from custom_components.daikin_cycle_ml import binary_sensor as bs_mod
    src = inspect.getsource(bs_mod)
    # OP_MODE_* imports should be absent
    assert "OP_MODE_HEATING" not in src
    assert "OP_MODE_COOLING" not in src
    assert "OP_MODE_DHW" not in src
    # MODE_* should be present
    assert "MODE_HEATING" in src
    assert "MODE_COOLING" in src
    assert "MODE_DHW" in src


def test_coordinator_mode_propagation_lowercase():
    """Coordinator snap.mode ends up lowercase end-to-end."""
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = {}
    c._setpoint_history = deque()
    c._last_setpoint = None
    c._status_update_unsub = None
    c._kmeans_centroids = []
    c._cluster_labels = []
    c.detector = CycleDetector({})
    c.detector.update(
        {
            ATTR_INV_FREQUENCY_RPS: 40.0,
            ATTR_IU_OPERATION_MODE: OP_MODE_DHW,
        },
        now=1000.0,
    )
    snap_mode = c.detector.snapshot().get("mode", "unknown")
    # Verify it matches what binary_sensor now compares against
    assert snap_mode == MODE_DHW


def test_all_modes_have_matching_constants():
    """Every classify_mode output has a matching MODE_* constant."""
    for attr, expected in (
        (OP_MODE_HEATING, MODE_HEATING),
        (OP_MODE_COOLING, MODE_COOLING),
        (OP_MODE_DHW, MODE_DHW),
    ):
        assert classify_mode({ATTR_IU_OPERATION_MODE: attr}) == expected
