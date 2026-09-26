"""Sensor platform for Daikin Cycle ML (Batch 31c).

9 container sensors. Detail values exposed as attributes.
Example:
    sensor.daikin_cycle_ml_last_cycle         = 85       (quality_score)
    state_attr(..., "mode")                    = "heating"
    state_attr(..., "cluster")                 = "normal"
    state_attr(..., "thermal_kw_avg")          = 3.48
"""
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
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_INLET_WATER_R4T,
    ATTR_INV_FREQUENCY_RPS,
    ATTR_LEAVING_WATER_AFTER_BUH,
    UPDATE_INTERVAL_SECONDS,
)
from .coordinator import DaikinCycleMLCoordinator, DataSnapshot
from .entity import DaikinCycleMLEntity

_LOGGER = logging.getLogger(__name__)


def _now() -> float:
    return time.time()


def _safe_float(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _avg(values: list) -> float | None:
    xs = [v for v in (_safe_float(x) for x in values) if v is not None]
    return sum(xs) / len(xs) if xs else None


def _max_or_none(values: list) -> float | None:
    xs = [v for v in (_safe_float(x) for x in values) if v is not None]
    return max(xs) if xs else None


def _min_or_none(values: list) -> float | None:
    xs = [v for v in (_safe_float(x) for x in values) if v is not None]
    return min(xs) if xs else None


def _ratio(num: float, denom: float) -> float | None:
    try:
        if denom <= 0:
            return None
        return round(100.0 * num / denom, 2)
    except (TypeError, ValueError):
        return None


def _dt_from_attrs(attrs: dict[str, Any]) -> float | None:
    a = _safe_float(attrs.get(ATTR_LEAVING_WATER_AFTER_BUH))
    b = _safe_float(attrs.get(ATTR_INLET_WATER_R4T))
    if a is None or b is None:
        return None
    return round(abs(a - b), 2)


def _rps_from_attrs(attrs: dict[str, Any]) -> float | None:
    return _safe_float(attrs.get(ATTR_INV_FREQUENCY_RPS))


def _avg_off_time(cycles: list) -> float | None:
    if len(cycles) < 2:
        return None
    sorted_cycles = sorted(cycles, key=lambda c: c.get("end_ts") or 0)
    offs = []
    for i in range(1, len(sorted_cycles)):
        pe = _safe_float(sorted_cycles[i - 1].get("end_ts"))
        cs = _safe_float(sorted_cycles[i].get("start_ts"))
        if pe is not None and cs is not None and cs >= pe:
            offs.append(cs - pe)
    return sum(offs) / len(offs) if offs else None


def _last(c: DaikinCycleMLCoordinator) -> dict[str, Any]:
    return c.store.last_cycle() or {}


def _cluster_label(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> str:
    cid = getattr(s, "cluster_id", None)
    if cid is None:
        return "unknown"
    try:
        return c.cluster_label(cid) or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


# --- attr builders -----------------------------------------------------

def _attrs_current_cycle(s, c):
    dur_min = None
    if s.state == "running" and s.cycle_start_ts > 0:
        dur_min = round(max(0.0, _now() - s.cycle_start_ts) / 60.0, 2)
    return {
        "duration_min": dur_min,
        "dt_k": _dt_from_attrs(s.attrs),
        "rps": _rps_from_attrs(s.attrs),
        "started_at": s.cycle_start_ts or None,
    }


def _attrs_last_cycle(s, c):
    r = _last(c)
    dur = _safe_float(r.get("duration_s"))
    return {
        "duration_min": round(dur / 60.0, 2) if dur is not None else None,
        "mode": r.get("mode"),
        "dt_max_k": _safe_float(r.get("dT_max")),
        "dt_avg_k": _safe_float(r.get("dT_avg")),
        "rps_max": _safe_float(r.get("rps_max")),
        "rps_avg": _safe_float(r.get("rps_avg")),
        "outdoor_temp": _safe_float(r.get("outdoor_temp")),
        "buh_used": bool(r.get("buh_used")),
        "defrost_used": bool(r.get("defrost_used")),
        "start_ts": _safe_float(r.get("start_ts")),
        "end_ts": _safe_float(r.get("end_ts")),
        "cluster": _cluster_label(s, c),
        "thermal_kw_avg": _safe_float(r.get("thermal_kw_avg")),
    }


def _attrs_today(s, c):
    cycles = c.store.cycles_today(_now())
    durations = [cy.get("duration_s") for cy in cycles]
    short_runs = c.store.get("short_runs_today", 0)
    avg_dur = _avg(durations)
    avg_off = _avg_off_time(cycles)
    max_dur = _max_or_none(durations)
    min_dur = _min_or_none(durations)
    return {
        "cycles_last_hour": c.store.cycles_in_window(_now(), 3600),
        "short_runs": short_runs,
        "short_offs": c.store.get("short_offs_today", 0),
        "short_ratio_pct": _ratio(short_runs, len(cycles)),
        "avg_duration_min": round(avg_dur / 60.0, 2) if avg_dur else None,
        "avg_off_time_min": round(avg_off / 60.0, 2) if avg_off else None,
        "longest_cycle_min": round(max_dur / 60.0, 2) if max_dur else None,
        "shortest_cycle_min": round(min_dur / 60.0, 2) if min_dur else None,
    }


def _attrs_quality_today(s, c):
    good = c.store.get("good_cycles_today", 0)
    bad = c.store.get("bad_cycles_today", 0)
    return {
        "good_cycles": good,
        "bad_cycles": bad,
        "good_ratio_pct": _ratio(good, good + bad),
    }


def _attrs_source_health(s, c):
    stale = False
    if s.last_success_ts > 0:
        stale = (_now() - s.last_success_ts) > 2.0 * UPDATE_INTERVAL_SECONDS
    return {
        "missing_attrs_count": len(s.missing_attrs),
        "missing_attrs_list": list(s.missing_attrs),
        "last_sample_age_s": (
            round(max(0.0, _now() - s.last_sample_ts), 2)
            if s.last_sample_ts > 0 else None
        ),
        "coordinator_errors": s.errors_total,
        "is_stale": stale,
    }


def _attrs_learned(s, c):
    try:
        good_off = c.adaptive.learn_good_off_min(s.mode)
    except Exception:  # noqa: BLE001
        good_off = None
    try:
        target_cpd = c.adaptive.learn_target_cycles_per_day()
    except Exception:  # noqa: BLE001
        target_cpd = None
    return {
        "good_off_min": good_off,
        "target_cycles_per_day": target_cpd,
        "adaptive_enabled": bool(c.options.get("adaptive_thresholds_enabled", False)),
    }


def _attrs_cop_today(s, c):
    data = s.cop_today or {}
    return {
        "samples_today": data.get("samples_today"),
        "cop_min": data.get("cop_min"),
        "cop_max": data.get("cop_max"),
        "baseline_cop_verlies_pct": data.get("baseline_cop_verlies_pct"),
    }


def _attrs_stooklijn(s, c):
    data = s.stooklijn_advies or {}
    return {
        "optimale_lwt": data.get("optimale_lwt"),
        "huidige_lwt": data.get("huidige_lwt"),
        "besparing_cop_pct": data.get("besparing_cop_pct"),
        "comfort_impact": data.get("comfort_impact"),
        "betrouwbaarheid": data.get("betrouwbaarheid"),
        "bucket": data.get("bucket"),
        "samples": data.get("samples"),
        "buckets": data.get("buckets") or {},
    }


ValueFn = Callable[[DataSnapshot, DaikinCycleMLCoordinator], Any]
AttrFn = Callable[[DataSnapshot, DaikinCycleMLCoordinator], dict]


class DaikinCycleMLSensor(DaikinCycleMLEntity, SensorEntity):
    """Sensor backed by coordinator snapshot + cycle store."""

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
            _LOGGER.exception("Sensor %s attr_fn failed", self._key)
            return None


SENSOR_DEFS: list[dict[str, Any]] = [
    {
        "key": "cycle_state", "name": "Cycle state",
        "icon": "mdi:state-machine",
        "value_fn": lambda s, c: s.state,
    },
    {
        "key": "current_cycle", "name": "Current cycle",
        "icon": "mdi:hvac",
        "value_fn": lambda s, c: s.mode if s.state == "running" else "idle",
        "attr_fn": _attrs_current_cycle,
    },
    {
        "key": "last_cycle", "name": "Last cycle",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "score",
        "icon": "mdi:star-outline",
        "value_fn": lambda s, c: _last(c).get("quality_score"),
        "attr_fn": _attrs_last_cycle,
    },
    {
        "key": "today", "name": "Today",
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "icon": "mdi:counter",
        "value_fn": lambda s, c: len(c.store.cycles_today(_now())),
        "attr_fn": _attrs_today,
    },
    {
        "key": "quality_today", "name": "Quality today",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "score",
        "icon": "mdi:star-outline",
        "value_fn": lambda s, c: _avg(
            [cy.get("quality_score") for cy in c.store.cycles_today(_now())]
        ),
        "attr_fn": _attrs_quality_today,
    },
    {
        "key": "source_health", "name": "Source health",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTime.SECONDS,
        "icon": "mdi:heart-pulse",
        "value_fn": lambda s, c: (
            round(max(0.0, _now() - s.last_success_ts), 2)
            if s.last_success_ts > 0 else None
        ),
        "attr_fn": _attrs_source_health,
    },
    {
        "key": "learned_thresholds", "name": "Learned thresholds",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTime.MINUTES,
        "icon": "mdi:brain",
        "value_fn": lambda s, c: c.adaptive.learn_short_run_min(s.mode),
        "attr_fn": _attrs_learned,
    },
    {
        "key": "cop_vandaag", "name": "COP vandaag",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP",
        "icon": "mdi:heat-pump",
        "value_fn": lambda s, c: (s.cop_today or {}).get("cop"),
        "attr_fn": _attrs_cop_today,
    },
    {
        "key": "stooklijn_advies", "name": "Stooklijn advies",
        "icon": "mdi:chart-line",
        "value_fn": lambda s, c: (s.stooklijn_advies or {}).get("state", "unknown"),
        "attr_fn": _attrs_stooklijn,
    },
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
        DaikinCycleMLSensor(
            coord,
            key=spec["key"],
            name=spec["name"],
            value_fn=spec["value_fn"],
            attr_fn=spec.get("attr_fn"),
            device_class=spec.get("device_class"),
            state_class=spec.get("state_class"),
            unit=spec.get("unit"),
            icon=spec.get("icon"),
        )
        for spec in SENSOR_DEFS
    ]
    async_add_entities(entities)


# --- backwards-compat wrappers (Batch 31cd) ---
# Original signature: (data: dict) -> dict
# Legacy tests call these with a plain data dict, not (snap, coordinator).
def _cop_today_attrs(data: Any) -> dict[str, Any]:
    """Legacy helper: extract COP today attributes from raw dict."""
    if not isinstance(data, dict) or not data:
        return {}
    return {
        "samples_today": data.get("samples_today"),
        "cop_min": data.get("cop_min"),
        "cop_max": data.get("cop_max"),
        "baseline_cop_verlies_pct": data.get("baseline_cop_verlies_pct"),
    }


def _stooklijn_attrs(data: Any) -> dict[str, Any]:
    """Legacy helper: extract stooklijn attributes from raw dict."""
    if not isinstance(data, dict) or not data:
        return {}
    return {
        "optimale_lwt": data.get("optimale_lwt"),
        "huidige_lwt": data.get("huidige_lwt"),
        "besparing_cop_pct": data.get("besparing_cop_pct"),
        "comfort_impact": data.get("comfort_impact"),
        "betrouwbaarheid": data.get("betrouwbaarheid"),
        "bucket": data.get("bucket"),
        "samples": data.get("samples"),
        "buckets": data.get("buckets") or {},
    }
