"""Binary sensor platform for Daikin Cycle ML (Batch 31d).

15 binary sensors. BUH step1/2 merged into buh_active with step attribute.
Cluster binaries removed (see sensor.last_cycle attribute "cluster").
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_3WAY_VALVE,
    ATTR_BUH_STEP1,
    ATTR_BUH_STEP2,
    ATTR_DEFROST_OPERATION,
    ATTR_IU_OPERATION_MODE,
    MODE_COOLING,
    MODE_DHW,
    MODE_HEATING,
    UPDATE_INTERVAL_SECONDS,
)
from .coordinator import DaikinCycleMLCoordinator, DataSnapshot
from .entity import DaikinCycleMLEntity

_LOGGER = logging.getLogger(__name__)

SOURCE_STALE_FACTOR = 2.0


def _now() -> float:
    return time.time()


def _attr_on(attrs: dict[str, Any], key: str) -> bool:
    v = attrs.get(key)
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().upper() == "ON"
    return False


def _attr_is_mode(attrs: dict[str, Any], key: str, mode_lower: str) -> bool:
    raw = attrs.get(key)
    if isinstance(raw, str):
        return raw.strip().lower() == mode_lower
    return False


def _is_short_run(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> bool:
    last = c.store.last_cycle()
    if not last:
        return False
    dur = last.get("duration_s")
    if not isinstance(dur, (int, float)):
        return False
    return float(dur) < int(c.options.get("short_run_threshold_min", 20)) * 60


def _is_short_off(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> bool:
    off = c.store.off_time_since_last(_now())
    if off is None:
        return False
    return off < int(c.options.get("short_off_threshold_min", 5)) * 60


def _is_source_stale(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> bool:
    if s.last_success_ts <= 0:
        return False
    return (_now() - s.last_success_ts) > SOURCE_STALE_FACTOR * UPDATE_INTERVAL_SECONDS


def _is_pendulum_hourly(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> bool:
    threshold = int(c.options.get("pendulum_cycles_per_hour", 4))
    return c.store.cycles_in_window(_now(), 3600) >= threshold


def _is_pendulum_daily(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> bool:
    threshold = int(c.options.get("pendulum_cycles_per_day", 40))
    return len(c.store.cycles_today(_now())) >= threshold


def _is_dhw_pendulum(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> bool:
    threshold = int(c.options.get("dhw_pendulum_cycles_per_hour", 3))
    return c.store.cycles_in_window_mode(_now(), 3600, MODE_DHW) >= threshold


def _is_high_cycle_rate(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> bool:
    base = int(c.options.get("pendulum_cycles_per_hour", 4))
    return c.store.cycles_in_window(_now(), 3600) > base * 1.5


def _is_dhw_active(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> bool:
    if _attr_is_mode(s.attrs, ATTR_IU_OPERATION_MODE, MODE_DHW):
        return True
    return _attr_on(s.attrs, ATTR_3WAY_VALVE)


def _is_buh_active(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> bool:
    return _attr_on(s.attrs, ATTR_BUH_STEP1) or _attr_on(s.attrs, ATTR_BUH_STEP2)


def _buh_step(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> int:
    if _attr_on(s.attrs, ATTR_BUH_STEP2):
        return 2
    if _attr_on(s.attrs, ATTR_BUH_STEP1):
        return 1
    return 0


def _buh_attrs(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> dict:
    return {"step": _buh_step(s, c)}


StateFn = Callable[[DataSnapshot, DaikinCycleMLCoordinator], bool]
AttrFn = Callable[[DataSnapshot, DaikinCycleMLCoordinator], dict]


class DaikinCycleMLBinarySensor(DaikinCycleMLEntity, BinarySensorEntity):
    """Binary sensor backed by coordinator snapshot + cycle store."""

    def __init__(
        self,
        coordinator: DaikinCycleMLCoordinator,
        key: str,
        name: str,
        state_fn: StateFn,
        *,
        attr_fn: AttrFn | None = None,
        device_class: BinarySensorDeviceClass | None = None,
        icon: str | None = None,
    ) -> None:
        super().__init__(coordinator, key, name)
        self._state_fn = state_fn
        self._attr_fn = attr_fn
        if device_class is not None:
            self._attr_device_class = device_class
        if icon is not None:
            self._attr_icon = icon

    @property
    def is_on(self) -> bool:
        snap = self.snapshot()
        if snap is None:
            return False
        try:
            return bool(self._state_fn(snap, self.coordinator))
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Binary sensor %s state_fn failed", self._key)
            return False

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self._attr_fn is None:
            return None
        snap = self.snapshot()
        if snap is None:
            return None
        try:
            return self._attr_fn(snap, self.coordinator)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Binary sensor %s attr_fn failed", self._key)
            return None


BINARY_SENSOR_DEFS: list[dict[str, Any]] = [
    {"key": "compressor_running", "name": "Compressor running",
     "device_class": BinarySensorDeviceClass.RUNNING,
     "icon": "mdi:heat-pump",
     "state_fn": lambda s, c: s.state == "running"},
    {"key": "pendulum_hourly", "name": "Pendulum hourly",
     "device_class": BinarySensorDeviceClass.PROBLEM,
     "state_fn": _is_pendulum_hourly},
    {"key": "pendulum_daily", "name": "Pendulum daily",
     "device_class": BinarySensorDeviceClass.PROBLEM,
     "state_fn": _is_pendulum_daily},
    {"key": "short_run", "name": "Short run",
     "device_class": BinarySensorDeviceClass.PROBLEM,
     "icon": "mdi:timer-alert-outline",
     "state_fn": _is_short_run},
    {"key": "short_off", "name": "Short off",
     "device_class": BinarySensorDeviceClass.PROBLEM,
     "icon": "mdi:timer-alert-outline",
     "state_fn": _is_short_off},
    {"key": "defrost_active", "name": "Defrost active",
     "device_class": BinarySensorDeviceClass.RUNNING,
     "state_fn": lambda s, c: _attr_on(s.attrs, ATTR_DEFROST_OPERATION)},
    {"key": "buh_active", "name": "BUH active",
     "device_class": BinarySensorDeviceClass.HEAT,
     "icon": "mdi:fire",
     "state_fn": _is_buh_active,
     "attr_fn": _buh_attrs},
    {"key": "dhw_active", "name": "DHW active",
     "icon": "mdi:water-boiler",
     "state_fn": _is_dhw_active},
    {"key": "heating_active", "name": "Heating active",
     "device_class": BinarySensorDeviceClass.HEAT,
     "state_fn": lambda s, c: s.mode == MODE_HEATING},
    {"key": "cooling_active", "name": "Cooling active",
     "device_class": BinarySensorDeviceClass.COLD,
     "state_fn": lambda s, c: s.mode == MODE_COOLING},
    {"key": "source_stale", "name": "Source stale",
     "device_class": BinarySensorDeviceClass.PROBLEM,
     "state_fn": _is_source_stale},
    {"key": "missing_attrs", "name": "Missing attributes",
     "device_class": BinarySensorDeviceClass.PROBLEM,
     "state_fn": lambda s, c: len(s.missing_attrs) > 0},
    {"key": "setpoint_oscillating", "name": "Setpoint oscillating",
     "device_class": BinarySensorDeviceClass.PROBLEM,
     "icon": "mdi:sine-wave",
     "state_fn": lambda s, c: c._compute_setpoint_oscillating()},
    {"key": "dhw_pendulum", "name": "DHW pendulum",
     "device_class": BinarySensorDeviceClass.PROBLEM,
     "icon": "mdi:water-boiler-alert",
     "state_fn": _is_dhw_pendulum},
    {"key": "high_cycle_rate", "name": "High cycle rate",
     "device_class": BinarySensorDeviceClass.PROBLEM,
     "icon": "mdi:speedometer",
     "state_fn": _is_high_cycle_rate},
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coord = getattr(entry, "runtime_data", None)
    if coord is None:
        _LOGGER.error("Coordinator not found for %s", entry.entry_id)
        return
    entities = [
        DaikinCycleMLBinarySensor(
            coord,
            key=spec["key"],
            name=spec["name"],
            state_fn=spec["state_fn"],
            attr_fn=spec.get("attr_fn"),
            device_class=spec.get("device_class"),
            icon=spec.get("icon"),
        )
        for spec in BINARY_SENSOR_DEFS
    ]
    async_add_entities(entities)
