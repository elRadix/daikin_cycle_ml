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
from collections.abc import Callable
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_FLOW_SENSOR,
    ATTR_INLET_WATER_R4T,
    ATTR_INV_FREQUENCY_RPS,
    ATTR_LEAVING_WATER_AFTER_BUH,
    DOMAIN,
    RPS_KW_FACTOR,
    UPDATE_INTERVAL_SECONDS,
    WATER_DENSITY_KG_L,
    WATER_SPECIFIC_HEAT_KJ_KG_K,
)
from .coordinator import DaikinCycleMLCoordinator, DataSnapshot
from .entity import DaikinCycleMLEntity
from .engine.thermal import (  # noqa: F401
    compute_thermal_power_live as _compute_thermal_power_live,
    dt_from_attrs as _dt_from_attrs,
    flow_from_attrs as _flow_from_attrs,
    rps_from_attrs as _rps_from_attrs,
    safe_float as _safe_float,
)


PARALLEL_UPDATES = 0  # read-only platform, HA serializes updates


_LOGGER = logging.getLogger(__name__)


def _now() -> float:
    return time.time()




def _avg(values: list[Any]) -> float | None:
    xs = [v for v in (_safe_float(x) for x in values) if v is not None]
    return sum(xs) / len(xs) if xs else None


def _max_or_none(values: list[Any]) -> float | None:
    xs = [v for v in (_safe_float(x) for x in values) if v is not None]
    return max(xs) if xs else None


def _min_or_none(values: list[Any]) -> float | None:
    xs = [v for v in (_safe_float(x) for x in values) if v is not None]
    return min(xs) if xs else None


def _ratio(num: float, denom: float) -> float | None:
    try:
        if denom <= 0:
            return None
        return round(100.0 * num / denom, 2)
    except (TypeError, ValueError):
        return None










def _value_thermal_power_live(
    s: "DataSnapshot", c: "DaikinCycleMLCoordinator"
) -> float | None:
    kw, _ = _compute_thermal_power_live(
        power_w=s.power_w,
        cop=s.cop,
        flow_lmin=_flow_from_attrs(s.attrs),
        dt_k=_dt_from_attrs(s.attrs),
        rps=_rps_from_attrs(s.attrs),
    )
    return kw


def _attrs_thermal_power_live(
    s: "DataSnapshot", c: "DaikinCycleMLCoordinator"
) -> dict[str, Any]:
    power_w = s.power_w
    cop = s.cop
    flow_lmin = _flow_from_attrs(s.attrs)
    dt_k = _dt_from_attrs(s.attrs)
    rps = _rps_from_attrs(s.attrs)
    _, source = _compute_thermal_power_live(
        power_w=power_w, cop=cop, flow_lmin=flow_lmin,
        dt_k=dt_k, rps=rps,
    )
    return {
        "input_power_w": power_w,
        "input_cop": cop,
        "input_flow_lmin": flow_lmin,
        "input_dt_k": dt_k,
        "input_rps": rps,
        "calculation_source": source,
    }


def _avg_off_time(cycles: list[Any]) -> float | None:
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


def _cluster_label(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> str | None:
    cid = getattr(s, "cluster_id", None)
    if cid is None:
        return None
    try:
        return c.cluster_label(cid) or None
    except Exception:
        return None


# --- attr builders -----------------------------------------------------

def _attrs_cycle_state(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> dict[str, Any]:
    """FEAT-1: expose configured entity_ids for cards/automations.

    Values come live from entry.data + entry.options. OptionsFlowWithReload
    ensures these refresh on every OptionsFlow submit. Only entity_ids,
    model and language are exposed; notify_service is intentionally omitted
    (could leak target names).
    """
    entry = getattr(c, "entry", None)
    if entry is None:
        return {}
    data = dict(entry.data or {})
    opts = dict(entry.options or {})
    return {
        "configured_source_sensor": data.get("source_sensor"),
        "configured_power_sensor": opts.get("power_sensor_entity"),
        "configured_cop_sensor": opts.get("cop_sensor_entity"),
        "configured_indoor_sensor": opts.get("indoor_temp_sensor"),
        "configured_model": data.get("model"),
        "configured_language": opts.get("notification_language", "en"),
        "configured_entry_id": entry.entry_id,
    }


def _attrs_current_cycle(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> dict[str, Any]:
    running = s.state == "running"
    dur_min = None
    if running and s.cycle_start_ts > 0:
        dur_min = round(max(0.0, _now() - s.cycle_start_ts) / 60.0, 2)
    return {
        "duration_min": dur_min,
        "dt_k": _dt_from_attrs(s.attrs) if running else None,
        "rps": _rps_from_attrs(s.attrs),
        "started_at": s.cycle_start_ts or None,
    }


def _attrs_last_cycle(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> dict[str, Any]:
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


def _attrs_today(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> dict[str, Any]:
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


def _attrs_quality_today(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> dict[str, Any]:
    good = c.store.get("good_cycles_today", 0)
    bad = c.store.get("bad_cycles_today", 0)
    return {
        "good_cycles": good,
        "bad_cycles": bad,
        "good_ratio_pct": _ratio(good, good + bad),
    }


def _attrs_source_health(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> dict[str, Any]:
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


def _attrs_learned(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> dict[str, Any]:
    try:
        good_off = c.adaptive.learn_good_off_min(s.mode)
    except Exception:
        good_off = None
    try:
        target_cpd = c.adaptive.learn_target_cycles_per_day()
    except Exception:
        target_cpd = None
    return {
        "good_off_min": good_off,
        "target_cycles_per_day": target_cpd,
        "adaptive_enabled": bool(c.options.get("adaptive_thresholds_enabled", False)),
    }


def _attrs_cop_today(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> dict[str, Any]:
    data = s.cop_today or {}
    return {
        "samples_today": data.get("samples_today"),
        "cop_min": data.get("cop_min"),
        "cop_max": data.get("cop_max"),
        "baseline_cop_verlies_pct": data.get("baseline_cop_verlies_pct"),
    }


def _attrs_cop_combined_today(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> dict[str, Any]:
    data = s.cop_combined_today or {}
    return {
        "samples_today": data.get("samples_today"),
        "cop_min": data.get("cop_min"),
        "cop_max": data.get("cop_max"),
        "baseline_cop_verlies_pct": data.get("baseline_cop_verlies_pct"),
    }


def _attrs_spf_state(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> dict[str, Any]:
    data = s.spf_state or {}
    return {
        "season_start_month": data.get("season_start_month"),
        "spf_season_n": data.get("spf_season_n"),
        "spf_ytd": data.get("spf_ytd"),
        "spf_ytd_n": data.get("spf_ytd_n"),
        "scop_365d": data.get("scop_365d"),
        "scop_365d_n": data.get("scop_365d_n"),
        "updated_ts": data.get("updated_ts"),
    }


def _cop_hourly_heating_mean(
    period: str,
) -> Callable[[DataSnapshot, DaikinCycleMLCoordinator], Any]:
    """Return value_fn: heating cop_mean for a period label."""
    def _fn(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> Any:
        data = getattr(s, f"cop_hourly_{period}", None) or {}
        hm = (data.get("by_mode") or {}).get("heating") or {}
        return hm.get("cop_mean")
    return _fn


def _cop_hourly_mode_mean(
    mode: str, period: str,
) -> Callable[[DataSnapshot, DaikinCycleMLCoordinator], Any]:
    """Return value_fn: cop_mean for a specific mode + period (C1a)."""
    def _fn(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> Any:
        data = getattr(s, f"cop_hourly_{period}", None) or {}
        bm = (data.get("by_mode") or {}).get(mode) or {}
        return bm.get("cop_mean")
    return _fn


def _attrs_cop_hourly(
    period: str,
) -> Callable[[DataSnapshot, DaikinCycleMLCoordinator], dict[str, Any]]:
    """Return attr_fn: full period breakdown."""
    def _fn(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> dict[str, Any]:
        data = getattr(s, f"cop_hourly_{period}", None) or {}
        return {
            "period": period,
            "n_hours": data.get("n_hours"),
            "n_samples": data.get("n_samples"),
            "cop_p10": data.get("cop_p10"),
            "cop_p90": data.get("cop_p90"),
            "cop_min": data.get("cop_min"),
            "cop_max": data.get("cop_max"),
            "by_mode": data.get("by_mode") or {},
        }
    return _fn


def _attrs_cop_hourly_mode(
    mode: str, period: str,
) -> Callable[[DataSnapshot, DaikinCycleMLCoordinator], dict[str, Any]]:
    """Return attr_fn: mode-specific COP breakdown (C1a)."""
    def _fn(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> dict[str, Any]:
        data = getattr(s, f"cop_hourly_{period}", None) or {}
        bm = (data.get("by_mode") or {}).get(mode) or {}
        return {
            "period": period, "mode": mode,
            "n_hours": bm.get("n_hours"),
            "n_samples": bm.get("n_samples"),
            "cop_mean": bm.get("cop_mean"),
            "cop_p10": bm.get("cop_p10"),
            "cop_p90": bm.get("cop_p90"),
            "cop_min": bm.get("cop_min"),
            "cop_max": bm.get("cop_max"),
            "by_mode": data.get("by_mode") or {},
        }
    return _fn

def _attrs_cop_curve_recent(
    s: DataSnapshot, c: DaikinCycleMLCoordinator,
) -> dict[str, Any]:
    data = s.cop_curve_recent or {}
    return {
        "window_hours": data.get("window_hours"),
        "n_points": data.get("n_points"),
        "modes_present": data.get("modes_present") or [],
        "updated_ts": data.get("updated_ts"),
        "points": data.get("points") or [],
    }

def _state_label(state: str, step_c: int, lang: str) -> str:
    """Localized state label (B11/B13)."""
    from .const import (
        STOOKLIJN_STATE_LABEL_EN,
        STOOKLIJN_STATE_LABEL_NL,
    )
    tbl = STOOKLIJN_STATE_LABEL_NL if lang == 'nl' else STOOKLIJN_STATE_LABEL_EN
    tmpl = tbl.get(state) or state
    try:
        return str(tmpl).format(step=step_c)
    except (KeyError, IndexError, ValueError):
        return str(tmpl)


def _attrs_stooklijn(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> dict[str, Any]:
    data = s.stooklijn_advies or {}
    _lang = 'en'
    try:
        _lang = (c.options or {}).get('notification_language', 'en') or 'en'
    except Exception:
        pass
    _state = str(data.get('state', 'unknown'))
    _step = int(data.get('step_c') or 0)
    return {
        'state_label': _state_label(_state, _step, _lang),
        'step_c': _step,
        'delta_c': data.get('delta_c'),
        'huidige_setpoint': data.get('setpoint_lwt'),
        'doel_setpoint': data.get('doel_setpoint'),
        'tracking_error': data.get('tracking_error'),
        'comfort_cap': data.get('comfort_cap'),
        "optimale_lwt": data.get("optimale_lwt"),
        "reason": data.get("reason", ""),
        "huidige_lwt": data.get("huidige_lwt"),
        "besparing_cop_pct": data.get("besparing_cop_pct"),
        "comfort_impact": data.get("comfort_impact"),
        "betrouwbaarheid": data.get("betrouwbaarheid"),
        "bucket": data.get("bucket"),
        "samples": data.get("samples"),
        "buckets": data.get("buckets") or {},
    }


ValueFn = Callable[[DataSnapshot, DaikinCycleMLCoordinator], Any]
AttrFn = Callable[[DataSnapshot, DaikinCycleMLCoordinator], dict[str, Any]]


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
        except Exception:
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
        except Exception:
            _LOGGER.exception("Sensor %s attr_fn failed", self._key)
            return None


SENSOR_DEFS: list[dict[str, Any]] = [
    {
        "key": "thermal_power_live", "name": "Thermal power live",
        "state_class": SensorStateClass.MEASUREMENT,
        "device_class": SensorDeviceClass.POWER,
        "unit": "kW",
        "icon": "mdi:fire",
        "value_fn": _value_thermal_power_live,
        "attr_fn": _attrs_thermal_power_live,
    },
    {
        "key": "cycle_state", "name": "Cycle state",
        "icon": "mdi:state-machine",
        "value_fn": lambda s, c: s.state,
        "attr_fn": _attrs_cycle_state,
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
        "key": "cycles_today", "name": "Cycles today",
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
        "key": "cop_today", "name": "COP today",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP",
        "icon": "mdi:heat-pump",
        "value_fn": lambda s, c: (s.cop_today or {}).get("cop"),
        "attr_fn": _attrs_cop_today,
    },
    {
        "key": "cop_combined_today", "name": "COP combined today",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP",
        "icon": "mdi:heat-pump-outline",
        "value_fn": lambda s, c: (s.cop_combined_today or {}).get("cop"),
        "attr_fn": _attrs_cop_combined_today,
    },
    {
        "key": "spf_season", "name": "SPF season",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "SPF",
        "icon": "mdi:calendar-star",
        "value_fn": lambda s, c: (s.spf_state or {}).get("spf_season"),
        "attr_fn": _attrs_spf_state,
    },
    {
        "key": "spf_ytd", "name": "SPF YTD",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "SPF",
        "icon": "mdi:calendar-today",
        "value_fn": lambda s, c: (s.spf_state or {}).get("spf_ytd"),
        "attr_fn": _attrs_spf_state,
    },
    {
        "key": "scop_running_365d", "name": "SCOP running 365d",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "SPF",
        "icon": "mdi:chart-timeline-variant",
        "value_fn": lambda s, c: (s.spf_state or {}).get("scop_365d"),
        "attr_fn": _attrs_spf_state,
    },
    {
        "key": "heating_curve_advice", "name": "Heating curve advice",
        "icon": "mdi:chart-line",
        "value_fn": lambda s, c: (s.stooklijn_advies or {}).get("state", "unknown"),
        "attr_fn": _attrs_stooklijn,
    },
    {
        "key": "cop_mean_day", "name": "COP mean (24h)",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP",
        "icon": "mdi:calendar-today",
        "value_fn": _cop_hourly_heating_mean("day"),
        "attr_fn": _attrs_cop_hourly("day"),
    },
    {
        "key": "cop_mean_week", "name": "COP mean (7d)",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP",
        "icon": "mdi:calendar-week",
        "value_fn": _cop_hourly_heating_mean("week"),
        "attr_fn": _attrs_cop_hourly("week"),
    },
    {
        "key": "cop_mean_month", "name": "COP mean (30d)",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP",
        "icon": "mdi:calendar-month",
        "value_fn": _cop_hourly_heating_mean("month"),
        "attr_fn": _attrs_cop_hourly("month"),
    },
    {
        "key": "cop_curve_recent", "name": "COP curve (48h)",
        "state_class": SensorStateClass.MEASUREMENT,
        "icon": "mdi:chart-scatter-plot",
        "value_fn": lambda s, c: (s.cop_curve_recent or {}).get(
            "n_points"
        ),
        "attr_fn": _attrs_cop_curve_recent,
    },
    {
        "key": "cop_heating_day", "name": "COP heating (day)",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP", "icon": "mdi:radiator",
        "value_fn": _cop_hourly_mode_mean("heating", "day"),
        "attr_fn": _attrs_cop_hourly_mode("heating", "day"),
    },
    {
        "key": "cop_heating_week", "name": "COP heating (week)",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP", "icon": "mdi:radiator",
        "value_fn": _cop_hourly_mode_mean("heating", "week"),
        "attr_fn": _attrs_cop_hourly_mode("heating", "week"),
    },
    {
        "key": "cop_heating_month", "name": "COP heating (month)",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP", "icon": "mdi:radiator",
        "value_fn": _cop_hourly_mode_mean("heating", "month"),
        "attr_fn": _attrs_cop_hourly_mode("heating", "month"),
    },
    {
        "key": "cop_dhw_day", "name": "COP DHW (day)",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP", "icon": "mdi:water-boiler",
        "value_fn": _cop_hourly_mode_mean("dhw", "day"),
        "attr_fn": _attrs_cop_hourly_mode("dhw", "day"),
    },
    {
        "key": "cop_dhw_week", "name": "COP DHW (week)",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP", "icon": "mdi:water-boiler",
        "value_fn": _cop_hourly_mode_mean("dhw", "week"),
        "attr_fn": _attrs_cop_hourly_mode("dhw", "week"),
    },
    {
        "key": "cop_dhw_month", "name": "COP DHW (month)",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP", "icon": "mdi:water-boiler",
        "value_fn": _cop_hourly_mode_mean("dhw", "month"),
        "attr_fn": _attrs_cop_hourly_mode("dhw", "month"),
    },
    {
        "key": "cop_cooling_day", "name": "COP cooling (day)",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP", "icon": "mdi:snowflake",
        "value_fn": _cop_hourly_mode_mean("cooling", "day"),
        "attr_fn": _attrs_cop_hourly_mode("cooling", "day"),
    },
    {
        "key": "cop_cooling_week", "name": "COP cooling (week)",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP", "icon": "mdi:snowflake",
        "value_fn": _cop_hourly_mode_mean("cooling", "week"),
        "attr_fn": _attrs_cop_hourly_mode("cooling", "week"),
    },
    {
        "key": "cop_cooling_month", "name": "COP cooling (month)",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP", "icon": "mdi:snowflake",
        "value_fn": _cop_hourly_mode_mean("cooling", "month"),
        "attr_fn": _attrs_cop_hourly_mode("cooling", "month"),
    },
]



def _migrate_entity_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Entity-ID migrations (idempotent).

    v1.3.1: fix entity_ids from v1.3.0 translation bug.
    v1.4.0: BREAKING rename NL/vague SENSOR_DEFS keys -> EN slugs.
      Update entity_id + unique_id + translation_key in one call so
      the entity created on this same setup pass reconciles to the
      same registry row (no orphan).
    """
    registry = er.async_get(hass)

    # v1.3.1 slug-only fixes (unique_id unchanged).
    slug_fixes = {
        "sensor.daikin_cycle_ml":               "sensor.daikin_cycle_ml_cop_mean_day",
        "sensor.daikin_cycle_ml_2":             "sensor.daikin_cycle_ml_cop_mean_week",
        "sensor.daikin_cycle_ml_3":             "sensor.daikin_cycle_ml_cop_mean_month",
        "sensor.daikin_cycle_ml_cop_curve_48h": "sensor.daikin_cycle_ml_cop_curve_recent",
    }
    for old_eid, new_eid in slug_fixes.items():
        if registry.async_get(old_eid) and not registry.async_get(new_eid):
            registry.async_update_entity(old_eid, new_entity_id=new_eid)

    # v1.4.0 key renames: entity_id + unique_id + translation_key.
    entry_id = entry.entry_id
    entry_domain = entry.domain
    key_fixes = {
        "today": "cycles_today",
        "cop_vandaag": "cop_today",
        "stooklijn_advies": "heating_curve_advice",
    }
    for old_key, new_key in key_fixes.items():
        old_eid = "sensor.daikin_cycle_ml_" + old_key
        new_eid = "sensor.daikin_cycle_ml_" + new_key
        if registry.async_get(old_eid) and not registry.async_get(new_eid):
            registry.async_update_entity(
                old_eid,
                new_entity_id=new_eid,
                new_unique_id="%s_%s_%s" % (entry_domain, entry_id, new_key),
                translation_key=new_key,
            )

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coord = getattr(entry, "runtime_data", None)
    if coord is None:
        _LOGGER.error("Coordinator not found for %s", entry.entry_id)
        return
    _migrate_entity_ids(hass, entry)
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
        "reason": data.get("reason", ""),
        "huidige_lwt": data.get("huidige_lwt"),
        "besparing_cop_pct": data.get("besparing_cop_pct"),
        "comfort_impact": data.get("comfort_impact"),
        "betrouwbaarheid": data.get("betrouwbaarheid"),
        "bucket": data.get("bucket"),
        "samples": data.get("samples"),
        "buckets": data.get("buckets") or {},
    }
