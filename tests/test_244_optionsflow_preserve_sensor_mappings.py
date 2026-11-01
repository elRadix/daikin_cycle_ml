"""#244 — _save() must preserve sensor mappings outside the device step.

Regression: notifications/pendulum/advanced steps wiped
power_sensor_entity / cop_sensor_entity / indoor_temp_sensor because
_save() ran setdefault(None) for every step, not just the device step.
"""
from __future__ import annotations

from typing import Any

from custom_components.daikin_cycle_ml.config_flow import (
    DaikinCycleMLOptionsFlow as OF,
)


class _E:
    def __init__(self, o: dict[str, Any]) -> None:
        self.options = o


class _F(OF):
    def __init__(self, e: _E) -> None:
        self._e = e

    @property
    def config_entry(self) -> _E:  # type: ignore[override]
        return self._e

    def async_create_entry(self, data: dict[str, Any]) -> Any:  # type: ignore[override]
        return ("c", data)


def _r(
    existing: dict[str, Any],
    user_input: dict[str, Any],
    *,
    sensor_step: bool = False,
) -> dict[str, Any]:
    return _F(_E(existing))._save(user_input, sensor_step=sensor_step)[1]


_EXISTING = {
    "power_sensor_entity": "sensor.power_abc",
    "cop_sensor_entity": "sensor.cop_abc",
    "indoor_temp_sensor": "sensor.indoor_abc",
    "notify_service": "notify.old",
    "compressor_rps_threshold": 2.5,
}


def test_non_device_step_preserves_sensor_mappings() -> None:
    """Notifications-style save must NOT wipe sensor mappings."""
    result = _r(_EXISTING, {"notify_service": "notify.new"})
    assert result["power_sensor_entity"] == "sensor.power_abc"
    assert result["cop_sensor_entity"] == "sensor.cop_abc"
    assert result["indoor_temp_sensor"] == "sensor.indoor_abc"
    assert result["notify_service"] == "notify.new"
    assert result["compressor_rps_threshold"] == 2.5


def test_device_step_still_clears_empty_sensors() -> None:
    """Device step: empty sensors section still clears (preserves #201)."""
    result = _r(_EXISTING, {"sensors": {}}, sensor_step=True)
    assert result["power_sensor_entity"] is None
    assert result["cop_sensor_entity"] is None
    assert result["indoor_temp_sensor"] is None


def test_device_step_sets_explicit_values() -> None:
    """Device step: explicit sensor values still win."""
    result = _r(
        _EXISTING,
        {"sensors": {"power_sensor_entity": "sensor.new_pwr"}},
        sensor_step=True,
    )
    assert result["power_sensor_entity"] == "sensor.new_pwr"
    assert result["cop_sensor_entity"] is None
    assert result["indoor_temp_sensor"] is None


def test_non_device_step_explicit_none_still_clears() -> None:
    """Explicit None in user_input clears even without sensor_step (user intent)."""
    result = _r(_EXISTING, {"power_sensor_entity": None})
    assert result["power_sensor_entity"] is None
    assert result["cop_sensor_entity"] == "sensor.cop_abc"
