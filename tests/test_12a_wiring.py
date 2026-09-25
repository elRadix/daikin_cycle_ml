"""Tests for 12a-2 wiring: coordinator adaptive threshold integration."""
from __future__ import annotations

import inspect

from custom_components.daikin_cycle_ml import coordinator as cmod
from custom_components.daikin_cycle_ml.const import (
    DEFAULT_ADAPTIVE_THRESHOLDS_ENABLED,
    MODEL_STATE_ADAPTIVE,
)


def test_default_disabled():
    assert DEFAULT_ADAPTIVE_THRESHOLDS_ENABLED is False


def test_model_state_key_format():
    assert MODEL_STATE_ADAPTIVE == "adaptive_thresholds"


def test_coordinator_has_effective_threshold():
    assert hasattr(cmod.DaikinCycleMLCoordinator, "_effective_threshold")


def test_coordinator_has_save_adaptive():
    assert hasattr(cmod.DaikinCycleMLCoordinator, "async_save_adaptive_state")


def test_coordinator_has_load_adaptive():
    assert hasattr(cmod.DaikinCycleMLCoordinator, "async_load_adaptive_state")


def test_effective_threshold_signature():
    sig = inspect.signature(
        cmod.DaikinCycleMLCoordinator._effective_threshold
    )
    assert "key" in sig.parameters
    assert "default" in sig.parameters

