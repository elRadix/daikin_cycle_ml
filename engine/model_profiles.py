"""Model-specific default profiles for Daikin Cycle ML."""
from __future__ import annotations

import logging
from typing import Any

from ..const import (
    DEFAULT_COMPRESSOR_RPS_THRESHOLD,
    DEFAULT_DEFROST_INTERVAL_MIN,
    DEFAULT_DHW_PENDULUM_CPH,
    DEFAULT_FALLBACK_POWER_THRESHOLD_W,
    DEFAULT_GOOD_CYCLE_RATIO,
    DEFAULT_GOOD_DT_K,
    DEFAULT_GOOD_OFF_MIN,
    DEFAULT_GOOD_RUN_MIN,
    DEFAULT_MAX_CYCLE_DURATION_MIN,
    DEFAULT_PENDULUM_CPD,
    DEFAULT_PENDULUM_CPH,
    DEFAULT_SETPOINT_OSC_THRESHOLD,
    DEFAULT_SHORT_CYCLE_RATIO,
    DEFAULT_SHORT_OFF_MIN,
    DEFAULT_SHORT_RUN_MIN,
    DEFAULT_TARGET_CYCLES_PER_DAY,
    MODEL_BASISPROFIEL,
    MODEL_CHOICES,
    MODEL_CUSTOM,
    MODEL_EPRA08EAV3,
    MODEL_EPRA12EAV3,
    MODEL_ERLA11DAV3,
    RECOMMENDED_ATTRIBUTES,
    REQUIRED_ATTRIBUTES,
)

_LOGGER = logging.getLogger(__name__)

_BASE: dict[str, Any] = {
    "expects_brine": False,
    "compressor_rps_threshold": DEFAULT_COMPRESSOR_RPS_THRESHOLD,
    "fallback_power_threshold_w": DEFAULT_FALLBACK_POWER_THRESHOLD_W,
    "max_cycle_duration_min": DEFAULT_MAX_CYCLE_DURATION_MIN,
    "timer_reconcile_on_start": True,
    "short_run_threshold_min": DEFAULT_SHORT_RUN_MIN,
    "short_off_threshold_min": DEFAULT_SHORT_OFF_MIN,
    "short_cycle_ratio_threshold": DEFAULT_SHORT_CYCLE_RATIO,
    "pendulum_cycles_per_hour": DEFAULT_PENDULUM_CPH,
    "pendulum_cycles_per_day": DEFAULT_PENDULUM_CPD,
    "dhw_pendulum_cycles_per_hour": DEFAULT_DHW_PENDULUM_CPH,
    "defrost_interval_min": DEFAULT_DEFROST_INTERVAL_MIN,
    "setpoint_oscillation_threshold": DEFAULT_SETPOINT_OSC_THRESHOLD,
    "good_run_threshold_min": DEFAULT_GOOD_RUN_MIN,
    "good_dt_threshold_k": DEFAULT_GOOD_DT_K,
    "good_off_threshold_min": DEFAULT_GOOD_OFF_MIN,
    "target_cycles_per_day": DEFAULT_TARGET_CYCLES_PER_DAY,
    "good_cycle_min_ratio": DEFAULT_GOOD_CYCLE_RATIO,
}

MODEL_PROFILES: dict[str, dict[str, Any]] = {
    MODEL_BASISPROFIEL: {**_BASE},
    MODEL_EPRA12EAV3: {**_BASE, "pendulum_cycles_per_day": 35},
    MODEL_EPRA08EAV3: {**_BASE},
    MODEL_ERLA11DAV3: {**_BASE},
    MODEL_CUSTOM: {**_BASE},
}


def get_profile(model: str) -> dict[str, Any]:
    """Return a copy of the profile for model (fallback: basisprofiel)."""
    profile = MODEL_PROFILES.get(model)
    if profile is None:
        _LOGGER.debug("Unknown model %r - using basisprofiel", model)
        profile = MODEL_PROFILES[MODEL_BASISPROFIEL]
    return dict(profile)


def expected_attributes(model: str) -> list[str]:
    """Required + recommended attribute keys for this model."""
    _ = get_profile(model)
    return list(REQUIRED_ATTRIBUTES) + list(RECOMMENDED_ATTRIBUTES)


def defaults_for(model: str) -> dict[str, Any]:
    """Return option defaults dict (without the expects_brine flag)."""
    profile = get_profile(model)
    profile.pop("expects_brine", None)
    return profile
