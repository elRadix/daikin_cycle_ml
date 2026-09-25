"""Sensor platform for Daikin Cycle ML (Batch 5b-1)."""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_INV_FREQUENCY_RPS,
    ATTR_INLET_WATER_R4T,
    ATTR_LEAVING_WATER_AFTER_BUH,
    DOMAIN,
)
from .coordinator import DataSnapshot, DaikinCycleMLCoordinator
from .entity import DaikinCycleMLEntity

_LOGGER = logging.getLogger(__name__)


def _now() -> float:
    return time.time()


def _dt_from_attrs(attrs: dict[str, Any]) -> float | None:
    lw = attrs.get(ATTR_LEAVING_WATER_AFTER_BUH)
    inl = attrs.get(ATTR_INLET_WATER_R4T)
    if isinstance(lw, (int, float)) and isinstance(inl, (int, float)):
        return round(abs(float(lw) - float(inl)), 2)
    return None


def _rps_from_attrs(attrs: dict[str, Any]) -> float | None:
    v = attrs.get(ATTR_INV_FREQUENCY_RPS)
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _ratio(num: int, den: int) -> float | None:
    if den <= 0:
        return 0.0
    return round(100.0 * num / den, 1)


def _avg(values: list[Any]) -> float | None:
    nums = [float(v) for v in values if isinstance(v, (int, float))]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 2)


def _max_or_none(values: list[Any]) -> float | None:
    nums = [float(v) for v in values if isinstance(v, (int, float))]
    return round(max(nums), 2) if nums else None


def _min_or_none(values: list[Any]) -> float | None:
    nums = [float(v) for v in values if isinstance(v, (int, float))]
    return round(min(nums), 2) if nums else None


def _avg_off_time(cycles: list[dict[str, Any]]) -> float | None:
    ordered = sorted(
        [c for c in cycles if isinstance(c.get("start_ts"), (int, float))],
        key=lambda c: c["start_ts"],
    )
    gaps: list[float] = []
    for prev, curr in zip(ordered, ordered[1:]):
        end_ts = prev.get("end_ts")
        start_next = curr.get("start_ts")
        if (
            isinstance(end_ts, (int, float))
            and isinstance(start_next, (int, float))
            and start_next > end_ts
        ):
            gaps.append(float(start_next) - float(end_ts))
    return _avg(gaps)


ValueFn = Callable[[DataSnapshot, DaikinCycleMLCoordinator], Any]
AttrFn = Callable[
    [DataSnapshot, DaikinCycleMLCoordinator], dict[str, Any] | None
]


class DaikinCycleMLSensor(DaikinCycleMLEntity, SensorEntity):
    """Generic sensor backed by coordinator snapshot + cycle store."""

    def __init__(
        self,
        coordinator: DaikinCycleMLCoordinator,
        key: str,
        name: str,
        value_fn: ValueFn,
        *,
        attr_fn: AttrFn | None = None,
        device_class: SensorDeviceClass | None = None,
        state_class: SensorStateClass | None = None,
        unit: str | None = None,
        icon: str | None = None,
    ) -> None:
        super().__init__(coordinator, key, name)
        self._value_fn = value_fn
        self._attr_fn = attr_fn
        if device_class is not None:
            self._attr_device_class = device_class
        if state_class is not None:
            self._attr_state_class = state_class
        if unit is not None:
            self._attr_native_unit_of_measurement = unit
        if icon is not None:
            self._attr_icon = icon

    @property
    def native_value(self) -> Any:
        snap = self.snapshot()
        if snap is None:
            return None
        try:
            value = self._value_fn(snap, self.coordinator)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Sensor %s value_fn failed", self._key)
            return None
        if isinstance(value, float):
            return round(value, 2)
        return value

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
            _LOGGER.exception(
                'Sensor %s attr_fn failed', self._key
            )
            return None


def _last(c) -> dict[str, Any]:
    return c.store.last_cycle() or {}


def _stooklijn_attrs(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or not data:
        return {}
    return {
        'optimale_lwt': data.get('optimale_lwt'),
        'huidige_lwt': data.get('huidige_lwt'),
        'besparing_cop_pct': data.get('besparing_cop_pct'),
        'comfort_impact': data.get('comfort_impact'),
        'betrouwbaarheid': data.get('betrouwbaarheid'),
        'bucket': data.get('bucket'),
        'samples': data.get('samples'),
        'buckets': data.get('buckets') or {},
    }


def _cop_today_attrs(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or not data:
        return {}
    return {
        'samples_today': data.get('samples_today'),
        'cop_min': data.get('cop_min'),
        'cop_max': data.get('cop_max'),
        'baseline_cop_verlies_pct': data.get(
            'baseline_cop_verlies_pct'
        ),
    }


SENSOR_DEFS: list[dict[str, Any]] = [
    {"key": "cycle_state", "name": "Cycle state",
     "icon": "mdi:state-machine",
     "value_fn": lambda s, c: s.state},
    {"key": "current_cycle_duration", "name": "Current cycle duration",
     "device_class": SensorDeviceClass.DURATION,
     "state_class": SensorStateClass.MEASUREMENT,
     "unit": UnitOfTime.SECONDS,
     "value_fn": lambda s, c: (
         round(max(0.0, _now() - s.cycle_start_ts), 2)
         if s.state == "running" and s.cycle_start_ts > 0 else 0
     )},
    {"key": "current_cycle_mode", "name": "Current cycle mode",
     "icon": "mdi:hvac", "value_fn": lambda s, c: s.mode},
    {"key": "current_dt", "name": "Current dT",
     "device_class": SensorDeviceClass.TEMPERATURE,
     "state_class": SensorStateClass.MEASUREMENT,
     "unit": UnitOfTemperature.KELVIN,
     "value_fn": lambda s, c: _dt_from_attrs(s.attrs)},
    {"key": "current_rps", "name": "Current RPS",
     "state_class": SensorStateClass.MEASUREMENT, "unit": "rps",
     "icon": "mdi:speedometer",
     "value_fn": lambda s, c: _rps_from_attrs(s.attrs)},
    {"key": "last_cycle_duration", "name": "Last cycle duration",
     "device_class": SensorDeviceClass.DURATION,
     "state_class": SensorStateClass.MEASUREMENT,
     "unit": UnitOfTime.SECONDS,
     "value_fn": lambda s, c: _last(c).get("duration_s")},
    {"key": "last_cycle_mode", "name": "Last cycle mode",
     "icon": "mdi:hvac",
     "value_fn": lambda s, c: _last(c).get("mode")},
    {"key": "last_cycle_dt_max", "name": "Last cycle dT max",
     "device_class": SensorDeviceClass.TEMPERATURE,
     "state_class": SensorStateClass.MEASUREMENT,
     "unit": UnitOfTemperature.KELVIN,
     "value_fn": lambda s, c: _last(c).get("dT_max")},
    {"key": "last_cycle_quality", "name": "Last cycle quality",
     "state_class": SensorStateClass.MEASUREMENT, "unit": "score",
     "icon": "mdi:star-outline",
     "value_fn": lambda s, c: _last(c).get("quality_score")},
    {"key": "cycles_today", "name": "Cycles today",
     "state_class": SensorStateClass.TOTAL_INCREASING,
     "icon": "mdi:counter",
     "value_fn": lambda s, c: len(c.store.cycles_today(_now()))},
    {"key": "cycles_last_hour", "name": "Cycles last hour",
     "state_class": SensorStateClass.MEASUREMENT,
     "icon": "mdi:counter",
     "value_fn": lambda s, c: c.store.cycles_in_window(_now(), 3600)},
    {"key": "short_runs_today", "name": "Short runs today",
     "state_class": SensorStateClass.TOTAL_INCREASING,
     "icon": "mdi:timer-alert-outline",
     "value_fn": lambda s, c: c.store.get("short_runs_today", 0)},
    {"key": "short_offs_today", "name": "Short offs today",
     "state_class": SensorStateClass.TOTAL_INCREASING,
     "icon": "mdi:timer-alert-outline",
     "value_fn": lambda s, c: c.store.get("short_offs_today", 0)},
    {"key": "short_cycle_ratio", "name": "Short cycle ratio",
     "state_class": SensorStateClass.MEASUREMENT, "unit": PERCENTAGE,
     "icon": "mdi:percent",
     "value_fn": lambda s, c: _ratio(
         c.store.get("short_runs_today", 0),
         len(c.store.cycles_today(_now())),
     )},
    {"key": "avg_cycle_duration_today", "name": "Average cycle duration today",
     "device_class": SensorDeviceClass.DURATION,
     "state_class": SensorStateClass.MEASUREMENT,
     "unit": UnitOfTime.SECONDS,
     "value_fn": lambda s, c: _avg(
         [cy.get("duration_s") for cy in c.store.cycles_today(_now())])},
    {"key": "avg_off_time_today", "name": "Average off time today",
     "device_class": SensorDeviceClass.DURATION,
     "state_class": SensorStateClass.MEASUREMENT,
     "unit": UnitOfTime.SECONDS,
     "value_fn": lambda s, c: _avg_off_time(c.store.cycles_today(_now()))},
    {"key": "longest_cycle_today", "name": "Longest cycle today",
     "device_class": SensorDeviceClass.DURATION,
     "state_class": SensorStateClass.MEASUREMENT,
     "unit": UnitOfTime.SECONDS,
     "value_fn": lambda s, c: _max_or_none(
         [cy.get("duration_s") for cy in c.store.cycles_today(_now())])},
    {"key": "shortest_cycle_today", "name": "Shortest cycle today",
     "device_class": SensorDeviceClass.DURATION,
     "state_class": SensorStateClass.MEASUREMENT,
     "unit": UnitOfTime.SECONDS,
     "value_fn": lambda s, c: _min_or_none(
         [cy.get("duration_s") for cy in c.store.cycles_today(_now())])},
    {"key": "avg_quality_today", "name": "Average quality today",
     "state_class": SensorStateClass.MEASUREMENT, "unit": "score",
     "icon": "mdi:star-outline",
     "value_fn": lambda s, c: _avg(
         [cy.get("quality_score") for cy in c.store.cycles_today(_now())])},
    {"key": "good_cycles_today", "name": "Good cycles today",
     "state_class": SensorStateClass.TOTAL_INCREASING,
     "icon": "mdi:check-circle-outline",
     "value_fn": lambda s, c: c.store.get("good_cycles_today", 0)},
    {"key": "bad_cycles_today", "name": "Bad cycles today",
     "state_class": SensorStateClass.TOTAL_INCREASING,
     "icon": "mdi:alert-circle-outline",
     "value_fn": lambda s, c: c.store.get("bad_cycles_today", 0)},
    {"key": "good_cycle_ratio", "name": "Good cycle ratio",
     "state_class": SensorStateClass.MEASUREMENT, "unit": PERCENTAGE,
     "icon": "mdi:percent",
     "value_fn": lambda s, c: _ratio(
         c.store.get("good_cycles_today", 0),
         c.store.get("good_cycles_today", 0)
         + c.store.get("bad_cycles_today", 0),
     )},
    {"key": "source_age", "name": "Source age",
     "device_class": SensorDeviceClass.DURATION,
     "state_class": SensorStateClass.MEASUREMENT,
     "unit": UnitOfTime.SECONDS,
     "value_fn": lambda s, c: (
         round(max(0.0, _now() - s.last_success_ts), 2)
         if s.last_success_ts > 0 else None)},
    {"key": "missing_attrs_count", "name": "Missing attributes",
     "state_class": SensorStateClass.MEASUREMENT,
     "icon": "mdi:alert-outline",
     "value_fn": lambda s, c: len(s.missing_attrs)},
    {"key": "last_sample_age", "name": "Last sample age",
     "device_class": SensorDeviceClass.DURATION,
     "state_class": SensorStateClass.MEASUREMENT,
     "unit": UnitOfTime.SECONDS,
     "value_fn": lambda s, c: (
         round(max(0.0, _now() - s.last_sample_ts), 2)
         if s.last_sample_ts > 0 else None)},
    {"key": "coordinator_errors", "name": "Coordinator errors",
     "state_class": SensorStateClass.TOTAL_INCREASING,
     "icon": "mdi:alert-octagon-outline",
     "value_fn": lambda s, c: s.errors_total},
    {"key": "stooklijn_advies", "name": "Stooklijn advies",
     "icon": "mdi:chart-line",
     "value_fn": lambda s, c: (
         (s.stooklijn_advies or {}).get("state", "unknown")
     ),
     "attr_fn": lambda s, c: _stooklijn_attrs(s.stooklijn_advies)},
    {"key": "cop_vandaag", "name": "COP vandaag",
     "state_class": SensorStateClass.MEASUREMENT, "unit": "COP",
     "icon": "mdi:heat-pump",
     "value_fn": lambda s, c: (s.cop_today or {}).get("cop"),
     "attr_fn": lambda s, c: _cop_today_attrs(s.cop_today)},
]


ADAPTIVE_SENSOR_DEFS: list[dict[str, Any]] = [
    {"key": "learned_short_run_min", "name": "Learned short run",
     "device_class": SensorDeviceClass.DURATION,
     "state_class": SensorStateClass.MEASUREMENT,
     "unit": UnitOfTime.MINUTES,
     "icon": "mdi:brain",
     "value_fn": lambda s, c: c.adaptive.learn_short_run_min(s.mode)},
    {"key": "learned_good_off_min", "name": "Learned good off",
     "device_class": SensorDeviceClass.DURATION,
     "state_class": SensorStateClass.MEASUREMENT,
     "unit": UnitOfTime.MINUTES,
     "icon": "mdi:brain",
     "value_fn": lambda s, c: c.adaptive.learn_good_off_min(s.mode)},
    {"key": "learned_target_cycles_per_day",
     "name": "Learned target cycles/day",
     "state_class": SensorStateClass.MEASUREMENT,
     "icon": "mdi:brain",
     "value_fn": lambda s, c: c.adaptive.learn_target_cycles_per_day()},
]
SENSOR_DEFS.extend(ADAPTIVE_SENSOR_DEFS)


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
        DaikinCycleMLSensor(
            coord,
            key=spec["key"],
            name=spec["name"],
            value_fn=spec["value_fn"],
            device_class=spec.get("device_class"),
            state_class=spec.get("state_class"),
            unit=spec.get("unit"),
            icon=spec.get("icon"),
        )
        for spec in SENSOR_DEFS
    ]
    async_add_entities(entities)
