"""Sensor platform for Daikin Cycle ML (Batch 31c).

9 container sensors. Detail values exposed as attributes.
Example:
    sensor.daikin_cycle_ml_last_cycle         = 85       (quality_score)
    state_attr(..., "mode")                    = "heating"
    state_attr(..., "cluster")                 = "normal"
    state_attr(..., "thermal_kw_avg")          = 3.48
"""
from __future__ import annotations

import contextlib
import json
import logging
import math
import time
from collections.abc import Callable
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    DEFAULT_GOOD_DT_K,
    DOMAIN,
    UPDATE_INTERVAL_SECONDS,
)
from .const import buh_step_kw_for_model as _buh_step_kw_for_model
from .coordinator import DaikinCycleMLConfigEntry, DaikinCycleMLCoordinator, DataSnapshot
from .engine.runtime_source import (
    compressor_starts_today,
    daily_attrs,
    defrost_count_today,
    native_today_is_daily,
    read_native_buh_minutes,
    read_native_compressor_minutes,
    read_native_compressor_starts,
    read_native_defrost_count,
)  # v1.22.8
from .engine.thermal import (
    compute_thermal_power_live as _compute_thermal_power_live,
)
from .engine.thermal import (
    dt_from_attrs as _dt_from_attrs,
)
from .engine.thermal import (
    flow_from_attrs as _flow_from_attrs,
)
from .engine.thermal import (
    rps_from_attrs as _rps_from_attrs,
)
from .engine.thermal import (
    safe_float as _safe_float,
)
from .engine.alert_texts import resolve_language as _resolve_language
from .engine.attribute_compat import build_compat_view as _build_compat_view
from .engine.thermal import live_temps_from_view as _live_temps_from_view
from .engine.timer_health import is_stale
from .entity import DaikinCycleMLEntity, async_remove_stale_entities

_ALERTS_ATTR_MAX_ITEMS = 10
_ALERTS_ATTR_BYTE_LIMIT = 14 * 1024  # 14 KB safety margin under HA's 16384

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










def _value_cop_normalized_a7w35(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> float | None:
    """C3a: Carnot-normalized COP at reference A7/W35."""
    if getattr(s, "state", "running") != "running":
        return None
    return s.cop_normalized_a7w35


def _value_hp_specs(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> str | None:
    """C3a: configured heat pump model key (specs sensor)."""
    return s.datasheet_model


def _target_dt_k(c: DaikinCycleMLCoordinator | None) -> float:
    opts = getattr(c, "options", None)
    raw = opts.get("good_dt_threshold_k") if isinstance(opts, dict) else None
    val = _safe_float_text(raw) if isinstance(raw, str) else raw
    if isinstance(val, (int, float)) and not isinstance(val, bool) and 2.0 <= val <= 15.0:
        return float(val)
    return DEFAULT_GOOD_DT_K


def _attrs_hp_specs(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> dict[str, Any]:
    """C3a: full datasheet of the configured model (static specs)."""
    ds = s.datasheet
    # #492: the ΔT target set in the integration (good_dt_threshold_k), so
    # the efficiency card judges flow and ΔT against the same value
    target_dt = _target_dt_k(c)
    if not ds:
        return {
            "configured": False,
            "model": s.datasheet_model,
            "reason": "no datasheet for this model",
            "target_dt_k": target_dt,
        }
    installer = dict(getattr(c, "installer_settings", None) or {})
    return {
        "configured": True,
        "target_dt_k": target_dt,
        # #512: the ΔT the installer set on the unit ([9-09]), read by the
        # P1/P2 bridge, shown next to the integration's own target
        "installer_target_dt_k": installer.get("target_dt"),
        "installer_settings": installer,
        "model": ds.get("model"),
        "source": ds.get("source"),
        "family": ds.get("family"),
        "kw": ds.get("kw"),
        "lwt_min": ds.get("lwt_min"),
        "lwt_max": ds.get("lwt_max"),
        "outdoor_min_c": ds.get("outdoor_min_c"),
        "outdoor_max_c": ds.get("outdoor_max_c"),
        "nom_cop": ds.get("nom_cop"),
        "scop_w35": ds.get("scop_w35"),
        "scop_w55": ds.get("scop_w55"),
        "refrigerant": ds.get("refrigerant"),
        "gwp": ds.get("gwp"),
        "charge_kg": ds.get("charge_kg"),
        "buh_above_c": ds.get("buh_above_c"),
        "defrost_below_c": ds.get("defrost_below_c"),
        "off_above_c": ds.get("off_above_c"),
        "points": list(ds.get("points") or []),
        "datasheet_sources": (
            dict(c.datasheet_sources) if c is not None else {}
        ),
        # #467: model profile (user values per value) + learned compressor range
        "rps_min": ds.get("rps_min"),
        "rps_max": ds.get("rps_max"),
        "value_sources": dict(ds.get("value_sources") or {}),
        "hmax_basis": ds.get("hmax_basis"),
        # #478: product-table maximum at A7/W35 and maximum power input
        # (Daikin), the A7/W35 anchor of the maximum-heat estimate
        "hc_max_a7": ds.get("hc_max_a7"),
        "max_input_kw": ds.get("max_input_kw"),
        "hmax_anchor": ds.get("hmax_anchor"),
        "profile": dict(ds.get("profile") or {}),
        "rps_learned": dict(getattr(c, "rps_learned", None) or {}) if c is not None else {},
        # #473: maximum heat learned per band, with sample counts
        "hmax_learned": dict(getattr(c, "hmax_learned", None) or {}) if c is not None else {},
    }


def _attrs_cop_normalized_a7w35(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> dict[str, Any]:
    """Attributes for cop_normalized_a7w35 sensor (C3a)."""
    ds = s.datasheet or {}
    ref_cop = next(
        (pt.get("cop") for pt in (ds.get("points") or [])
         if pt.get("label") == "A7/W35"),
        None,
    )
    return {
        "model": s.datasheet_model,
        "family": ds.get("family"),
        "kw": ds.get("kw"),
        "lwt_min": ds.get("lwt_min"),
        "lwt_max": ds.get("lwt_max"),
        "nom_cop": ds.get("nom_cop"),
        "scop_w35": ds.get("scop_w35"),
        "scop_w55": ds.get("scop_w55"),
        "ref_cop_a7w35": ref_cop,
        "source": ds.get("source"),
        "cop_normalized_a7w35": s.cop_normalized_a7w35,
        "cop_measured": s.cop,
    }


def _attrs_degree_days(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> dict[str, Any]:
    """#495: every scheme today, yesterday and the season (degree days)."""
    d = getattr(c, "degree_days", None) or {}
    return {
        "scheme": d.get("scheme"), "today_all": d.get("today_all"),
        "outdoor_mean_today": d.get("outdoor_mean_today"), "yesterday": d.get("yesterday"),
        "season_dd": (d.get("season") or {}).get("dd"), "season_since": d.get("season_since"),
    }


def _attrs_heat_per_dd(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> dict[str, Any]:
    """#495: heating kWh per degree day over 7 / 30 days and the season."""
    d = getattr(c, "degree_days", None) or {}
    return {"scheme": d.get("scheme"), **{k: d.get(k) for k in ("week", "month", "season")}}


def _value_cop_vs_datasheet_pct(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> float | None:
    """C3a: live COP deviation (%) vs the datasheet at the live point (#175).

    #515: space heating only. The datasheet points are space-heating points;
    hot water compared with them read -48 % "critical" on a sound unit."""
    if getattr(s, "state", "running") != "running":
        return None
    return _ds_pct_space_heating(s)


def _ds_pct_space_heating(s: DataSnapshot) -> float | None:
    if str(getattr(s, "mode", "heating") or "heating") not in ("heating", "unknown"):
        return None
    return s.cop_vs_datasheet_pct


def _attrs_cop_vs_datasheet_pct(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> dict[str, Any]:
    """Attributes for cop_vs_datasheet_pct sensor (C3a)."""
    ds = s.datasheet or {}
    ref_cop = next(
        (pt.get("cop") for pt in (ds.get("points") or [])
         if pt.get("label") == "A7/W35"),
        None,
    )
    pct = _ds_pct_space_heating(s)
    ref = getattr(s, "cop_datasheet_ref", None) or {}
    if pct is None:
        band = None
    elif pct >= 0:
        band = "on_spec"
    elif pct >= -20:
        band = "below_spec"
    else:
        band = "critical"
    return {
        "model": s.datasheet_model,
        "ref_cop_a7w35": ref_cop,
        "cop_normalized_a7w35": s.cop_normalized_a7w35,
        # #175: datasheet COP expected at the live outdoor / water point
        "cop_datasheet_live": ref.get("cop_datasheet_live"),
        "reference_point": ref.get("reference_point"),
        "reference_distance_k": ref.get("reference_distance_k"),
        "cop_measured": s.cop,
        "deviation_pct": pct,
        "band": band,
    }


def _value_thermal_power_live(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> float | None:
    if getattr(s, "state", "running") != "running":
        return 0.0
    kw, _ = _compute_thermal_power_live(
        power_w=s.power_w,
        cop=s.cop,
        flow_lmin=_flow_from_attrs(s.attrs),
        dt_k=_dt_from_attrs(s.attrs),
        rps=_rps_from_attrs(s.attrs),
        mode=s.mode,
    )
    return kw


def _attrs_thermal_power_live(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> dict[str, Any]:
    power_w = s.power_w
    cop = s.cop
    flow_lmin = _flow_from_attrs(s.attrs)
    dt_k = _dt_from_attrs(s.attrs)
    rps = _rps_from_attrs(s.attrs)
    _, source = _compute_thermal_power_live(
        power_w=power_w, cop=cop, flow_lmin=flow_lmin,
        dt_k=dt_k, rps=rps,
        mode=s.mode,
    )
    return {
        "input_power_w": power_w,
        "input_cop": cop,
        "input_flow_lmin": flow_lmin,
        "input_dt_k": dt_k,
        "input_rps": rps,
        "calculation_source": source,
        **_live_temps(s, c),
    }


def _live_temps(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> dict[str, Any]:
    """Live temperatures for the native efficiency card.

    The room temperature of the configured indoor sensor wins over the
    controller's own room sensor.
    """
    temps: dict[str, Any] = dict(
        _live_temps_from_view(_build_compat_view(getattr(s, "attrs", None) or {}))
    )
    ent = getattr(c, "indoor_temp_entity", None)
    hass = getattr(c, "hass", None)
    if isinstance(ent, str) and ent and hass is not None:
        st = hass.states.get(ent)
        room = _safe_float_text(st.state) if st is not None else None
        if room is not None:
            temps["room_c"] = room
    return temps


def _safe_float_text(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


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
        "configured_buh_power_sensor": opts.get("buh_power_sensor_entity"),
        "configured_cop_sensor": opts.get("cop_sensor_entity"),
        "configured_indoor_sensor": opts.get("indoor_temp_sensor"),
        "configured_model": data.get("model"),
        "configured_language": _alert_language(opts, c),
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
        "rps": _rps_from_attrs(s.attrs) if getattr(s, "state", "running") == "running" else 0,
        "started_at": s.cycle_start_ts or None,
    }


def _attrs_alerts_today(
    s: DataSnapshot, c: DaikinCycleMLCoordinator,
) -> dict[str, Any]:
    """Alerts list for today, size-capped to fit HA Recorder 16KB limit.

    v1.22.10: busy days (27 alerts, 24.3KB) exceeded HA's 16384-byte
    Recorder cap -> HA silently dropped all attributes from history.
    Keep aggregates; progressively truncate the alerts list only when
    the serialized payload exceeds _ALERTS_ATTR_BYTE_LIMIT.
    Full history remains in SQLite and via services.get_alerts.
    """
    data = s.alerts_today or {}
    alerts = data.get("alerts") or []
    total_alerts = len(alerts)

    def _build(alerts_list: list[dict[str, Any]]) -> dict[str, Any]:
        shown = len(alerts_list)
        return {
            "since": data.get("since"),
            "total": data.get("total", 0),
            "by_type": data.get("by_type", {}),
            "by_severity": data.get("by_severity", {}),
            "alerts": alerts_list,
            "alerts_shown": shown,
            "alerts_total": total_alerts,
            "truncated": (
                data.get("truncated", False) or shown < total_alerts
            ),
        }

    def _size(d: dict[str, Any]) -> int:
        return len(json.dumps(d, separators=(",", ":")))

    # Branch 1: full list fits
    out = _build(alerts)
    if _size(out) <= _ALERTS_ATTR_BYTE_LIMIT:
        return out

    # Branch 2: cap to last N items
    capped = _build(alerts[-_ALERTS_ATTR_MAX_ITEMS:])
    if _size(capped) <= _ALERTS_ATTR_BYTE_LIMIT:
        capped["truncated_reason"] = "attr_size_limit"
        return capped

    # Branch 3: even N items too big -> drop list (aggregates preserved)
    out = _build([])
    out["truncated_reason"] = "attr_size_limit"
    return out


def _round_min(seconds: Any) -> float | None:
    v = _safe_float(seconds)
    return round(v / 60.0, 1) if v is not None else None


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
        # #421: what the quality score lost, per criterion
        "buh_min": _round_min(r.get("buh_s")),
        "defrost_min": _round_min(r.get("defrost_s")),
        "quality_penalties": (
            dict(r["quality_penalties"])
            if isinstance(r.get("quality_penalties"), dict) else None
        ),
        "start_ts": _safe_float(r.get("start_ts")),
        "end_ts": _safe_float(r.get("end_ts")),
        "cluster": _cluster_label(s, c),
        "thermal_kw_avg": _safe_float(r.get("thermal_kw_avg")),
    }


def _attrs_today(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> dict[str, Any]:
    cycles = c.store.cycles_today(_now())
    durations = [cy.get("duration_s") for cy in cycles]
    short_runs = c.store.get("short_runs_today", 0)
    transient = [cy for cy in cycles if cy.get("is_transient")]
    non_transient = [cy for cy in cycles if not cy.get("is_transient")]
    avg_dur = _avg(durations)
    avg_off = _avg_off_time(cycles)
    max_dur = _max_or_none(durations)
    min_dur = _min_or_none(durations)
    return {
        "cycles_last_hour": c.store.cycles_in_window(_now(), 3600),
        "short_runs": short_runs,
        "short_offs": c.store.get("short_offs_today", 0),
        "short_ratio_pct": _ratio(short_runs, len(cycles)),
        "transient_cycles_today": len(transient),
        "non_transient_cycles_today": len(non_transient),
        "transient_ratio_pct": _ratio(len(transient), len(cycles)),
        "avg_duration_min": round(avg_dur / 60.0, 2) if avg_dur else None,
        "avg_off_time_min": round(avg_off / 60.0, 2) if avg_off else None,
        "longest_cycle_min": round(max_dur / 60.0, 2) if max_dur else None,
        "shortest_cycle_min": round(min_dur / 60.0, 2) if min_dur else None,
    }


def _compute_quality_today(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> float | None:
    """Average of closed cycle scores + live score for open cycle (#316)."""
    cycles = c.store.cycles_today(_now())
    closed = [
        cy.get("quality_score") for cy in cycles
        if cy.get("quality_score") is not None
    ]
    live = getattr(s, "quality_live", None)
    scores = list(closed)
    if live is not None:
        scores.append(live)
    return _avg(scores)


def _attrs_quality_today(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> dict[str, Any]:
    good = c.store.get("good_cycles_today", 0)
    bad = c.store.get("bad_cycles_today", 0)
    return {
        "good_cycles": good,
        "bad_cycles": bad,
        "good_ratio_pct": _ratio(good, good + bad),
        "live_score": getattr(s, "quality_live", None),
        "is_cycle_open": getattr(c.detector, "state", "idle") == "running",
        "live_cycle_duration_s": getattr(s, "quality_live_duration_s", None),
    }


def _attrs_source_health(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> dict[str, Any]:
    stale = False
    if s.last_success_ts > 0:
        stale = is_stale(
            s.last_success_ts, _now(),
            2.0 * UPDATE_INTERVAL_SECONDS,
        )
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


def _value_learned(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> int | None:
    """#423: the short-run threshold in use (learned, floored at half the
    configured value, or the configured value). The raw learned value is
    the attribute ``short_run_learned_min``; showing it as the state (2
    while 10 was used) was confusing on a card."""
    try:
        value: int | None = c._effective_threshold(
            "short_run_threshold_min",
            int(c.options.get("short_run_threshold_min", 20)),
        )
        return value
    except Exception:
        return None


def _attrs_learned(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> dict[str, Any]:
    try:
        good_off = c.adaptive.learn_good_off_min(c._resolve_adaptive_mode())
    except Exception:
        good_off = None
    try:
        target_cpd = c.adaptive.learn_target_cycles_per_day()
    except Exception:
        target_cpd = None
    try:
        # #408 A: the threshold actually used (learned, bounded at half
        # of the configured short-run threshold).
        short_eff: int | None = c._effective_threshold(
            "short_run_threshold_min",
            int(c.options.get("short_run_threshold_min", 20)),
        )
    except Exception:
        short_eff = None
    try:
        short_learned = c.adaptive.learn_short_run_min(c._resolve_adaptive_mode())
    except Exception:
        short_learned = None
    return {
        "short_run_learned_min": short_learned,
        "good_off_min": good_off,
        "target_cycles_per_day": target_cpd,
        "adaptive_enabled": bool(c.options.get("adaptive_thresholds_enabled", False)),
        "short_run_effective_min": short_eff,
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
            # #515: samples taken before the mode was known (startup) count in
            # the totals above but are not a mode of their own
            "by_mode": {
                m: v for m, v in (data.get("by_mode") or {}).items() if m != "unknown"
            },
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
            # #515: no other modes on a mode's own sensor (cop_mean_* has them)
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
        STOOKLIJN_STATE_LABEL_FR,
        STOOKLIJN_STATE_LABEL_NL,
    )
    tbl = {
        'nl': STOOKLIJN_STATE_LABEL_NL, 'fr': STOOKLIJN_STATE_LABEL_FR,
    }.get(lang, STOOKLIJN_STATE_LABEL_EN)
    tmpl = tbl.get(state) or state
    try:
        return str(tmpl).format(step=step_c)
    except (KeyError, IndexError, ValueError):
        return str(tmpl)


def _alert_language(options: Any, c: Any) -> str:
    """#463: notification language, English unless chosen ("auto" = HA language)."""
    ha_lang = getattr(getattr(getattr(c, "hass", None), "config", None), "language", None)
    return _resolve_language(
        options if isinstance(options, dict) else None,
        ha_lang if isinstance(ha_lang, str) else None,
    )


def _attrs_stooklijn(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> dict[str, Any]:
    data = s.stooklijn_advies or {}
    _lang = 'en'
    with contextlib.suppress(Exception):
        _lang = _alert_language(c.options, c)
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
        "offset_delta_c": data.get("offset_delta_c"),
        "slope_delta": data.get("slope_delta"),
        # #427: DHW too; the measured data stays (buckets, LWT)
        "suppressed_by": (
            data.get("reason")
            if data.get("reason") in ("buh_active", "dhw_active") else None
        ),
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
        entity_category: str | None = None,
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
        if entity_category == "diagnostic":
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        elif entity_category == "config":
            self._attr_entity_category = EntityCategory.CONFIG

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


def _value_cop_degradation_status(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> Any:
    return s.cop_degradation_status


def _attrs_cop_degradation_status(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> dict[str, Any]:
    d = s.cop_degradation_detail or {}
    return {
        "severity_raw": d.get("severity_raw", "none"),
        "severity_downgraded": d.get("severity_downgraded", False),
        "week_pct": d.get("week_pct"),
        "week_pct_raw": d.get("week_pct_raw"),
        "lwt_shift_detected": d.get("lwt_shift_detected", False),
        "lwt_shift_c": d.get("lwt_shift_c"),
        "threshold_pct": d.get("threshold_pct"),
        "critical_pct": d.get("critical_pct"),
        "valid": d.get("valid", False),
        "updated_ts": d.get("updated_ts"),
    }


def _value_cop_degradation_week_pct(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> Any:
    return s.cop_degradation_week_pct


def _attrs_cop_degradation_week_pct(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> dict[str, Any]:
    d = s.cop_degradation_detail or {}
    return {
        "mode": d.get("mode"),
        "window_days": d.get("window_days"),
        "n_samples_recent": d.get("n_samples_recent"),
        "n_samples_prev": d.get("n_samples_prev"),
        "n_days_recent": d.get("n_days_recent"),
        "n_days_prev": d.get("n_days_prev"),
        "n_bins_used": d.get("n_bins_used"),
        "dynamic_min_samples": d.get("dynamic_min_samples"),
        "bins_used": d.get("bins_used", []),
        "excluded_hours_recent": d.get("excluded_hours_recent"),
        "excluded_hours_prev": d.get("excluded_hours_prev"),
        "exclusion_skew": d.get("exclusion_skew"),
        "lwt_mean_recent": d.get("lwt_mean_recent"),
        "lwt_mean_prev": d.get("lwt_mean_prev"),
        "updated_ts": d.get("updated_ts"),
    }


def _value_cop_trend_30d(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> Any:
    return s.cop_trend_30d


def _attrs_cop_trend_30d(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> dict[str, Any]:
    d = s.cop_trend_detail or {}
    return {
        "mode": d.get("mode"),
        "window_days": d.get("window_days"),
        "baseline_days": d.get("baseline_days"),
        "recent_days": d.get("recent_days"),
        "n_hours_baseline": d.get("n_hours_baseline"),
        "n_hours_recent": d.get("n_hours_recent"),
        "outdoor_spread_baseline_c": d.get("outdoor_spread_baseline_c"),
        "fit_slope": d.get("fit_slope"),
        "fit_intercept": d.get("fit_intercept"),
        "fit_r2": d.get("fit_r2"),
        "cop_predicted_recent": d.get("cop_predicted_recent"),
        "cop_observed_recent": d.get("cop_observed_recent"),
        "threshold_pct": d.get("threshold_pct"),
        "critical_pct": d.get("critical_pct"),
        "valid": d.get("valid", False),
        "updated_ts": d.get("updated_ts"),
    }


# ---------- v1.6.0-C5: runtime/BUH/defrost/duty helpers ----------


def _resolve_attrs(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> dict[str, Any]:
    """v1.22.8: pick the non-empty attrs dict from snapshot or coordinator.

    Pre-v1.22.8 code used ``s.attrs if isinstance(s.attrs, dict) else
    c.last_attrs`` — an EMPTY dict on s.attrs blocked the populated
    ``c.last_attrs`` fallback, causing native-first resolvers to miss
    firmware counters whenever a snapshot was captured with attrs={}.

    This helper prefers whichever side carries data. When both are
    populated (normal steady-state) s.attrs wins (fresh from last tick).
    """
    _s_attrs = getattr(s, "attrs", None)
    _c_attrs = getattr(c, "last_attrs", None)
    if isinstance(_s_attrs, dict) and _s_attrs:
        return _s_attrs
    if isinstance(_c_attrs, dict) and _c_attrs:
        return _c_attrs
    return _s_attrs if isinstance(_s_attrs, dict) else {}


def _today_attrs(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> dict[str, Any]:
    """#466: attributes for the today sensors, without the native ESPAltherma
    today counters when they do not reset at midnight (no clock on the ESP)."""
    now = _now()
    return daily_attrs(_resolve_attrs(s, c), (now - _local_midnight(now)) / 60.0)


def _native_daily(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> bool:
    """#466: False when the ESP's today counters do not reset at midnight."""
    now = _now()
    return native_today_is_daily(_resolve_attrs(s, c), (now - _local_midnight(now)) / 60.0)


def _local_midnight(now: float) -> float:
    lt = time.localtime(float(now))
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))


def _value_runtime_compressor_today_s(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> int:
    """v1.22.8 native-first + cross-midnight-aware computed fallback.

    Pre-v1.22.8 summed only ``store.cycles_today()`` (start_ts-day filter),
    missing two things: (a) cross-midnight cycle tails, (b) any open cycle
    whose row is not yet in the DB (row is created on close, not start).

    ESPAltherma v2 exposes ``Stats: Compressor run today (min)`` as the
    firmware's own wall-clock counter — correct by definition. Fallback
    uses ``cycles_intersecting`` (overlap-window sum) + open-cycle portion.
    """
    attrs = _today_attrs(s, c)
    native_min = read_native_compressor_minutes(attrs)
    if native_min is not None:
        return int(round(native_min * 60.0))
    now = _now()
    midnight = _local_midnight(now)
    total = 0.0
    try:  # v1.22.8 D5: iterate defensively (store may raise, return None, or yield garbage)
        for cy in (c.store.cycles_intersecting(midnight, now) or ()):
            try:
                st = float(cy.get("start_ts") or 0.0)
                en = float(cy.get("end_ts") or 0.0)
            except (TypeError, ValueError):
                continue
            ov = min(en, now) - max(st, midnight)
            if ov > 0:
                total += ov
    except Exception:
        pass
    if s.state == "running" and s.cycle_start_ts > 0:
        open_start = max(float(s.cycle_start_ts), midnight)
        total += max(0.0, now - open_start)
    return int(total)


def _value_runtime_buh_today_s(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> int:
    snap = c.runtime_snapshot
    attrs = _today_attrs(s, c)
    native_min = read_native_buh_minutes(attrs)
    if native_min is not None:
        return int(round(native_min * 60.0))
    _snap = snap if isinstance(snap, dict) else {}
    return int(_snap.get("buh_total_s", max(
        _snap.get("buh_step1_s", 0.0), _snap.get("buh_step2_s", 0.0)
    )))


def _value_compressor_starts_today(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> int:
    attrs = _today_attrs(s, c)
    try:
        cycles = c.store.cycles_today(_now())
        computed = len(cycles) if cycles else 0
    except Exception:
        computed = 0
    value, _src = compressor_starts_today(attrs, computed)
    return value


def _value_defrost_count_today(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> int:
    attrs = _today_attrs(s, c)
    snap = c.runtime_snapshot
    _snap = snap if isinstance(snap, dict) else {}
    try:
        computed = int(_snap.get("defrost_count", 0) or 0)
    except (TypeError, ValueError):
        computed = 0
    value, _src = defrost_count_today(attrs, computed)
    return value


def _value_defrost_duration_today_s(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> int:
    return int(c.runtime_snapshot["defrost_duration_s"])


def _value_duty_cycle_today_pct(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> float:
    now = _now()
    runtime = _value_runtime_compressor_today_s(s, c)
    elapsed = max(1.0, now - _local_midnight(now))
    raw = 100.0 * runtime / elapsed
    return round(max(0.0, min(100.0, raw)), 2)


def _buh_energy_kwh_est(
    c: DaikinCycleMLCoordinator, step1_s: float, step2_s: float
) -> float | None:
    try:
        model = c.entry.data.get("model") if c.entry else None
        s1_kw, s2_kw = _buh_step_kw_for_model(model)
        # #515: the step powers set in Configure win over the model's default
        opts = getattr(c, "options", None)
        if isinstance(opts, dict):
            s1_kw = float(opts.get("buh_step1_kw") or s1_kw)
            s2_kw = float(opts.get("buh_step2_kw") or s2_kw)
        return round(step1_s * s1_kw / 3600.0 + step2_s * s2_kw / 3600.0, 3)
    except Exception:
        return None


_ENERGY_MODES = ("heating", "dhw", "cooling")


def _value_energy_kwh(
    mode: str, kind: str
) -> Callable[[DataSnapshot, DaikinCycleMLCoordinator], float]:
    def _fn(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> float:
        snap = c.energy_snapshot or {}
        mode_data = snap.get(mode) or {}
        return round(float(mode_data.get(kind, 0.0)), 3)
    return _fn


def _value_energy_total_kwh(
    kind: str,
) -> Callable[[DataSnapshot, DaikinCycleMLCoordinator], float]:
    def _fn(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> float:
        snap = c.energy_snapshot or {}
        return round(
            sum(
                float((snap.get(m) or {}).get(kind, 0.0))
                for m in _ENERGY_MODES
            ),
            3,
        )
    return _fn


def _attrs_energy_snapshot(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> dict[str, Any]:
    snap = c.energy_snapshot or {}
    out: dict[str, Any] = {}
    for mode in _ENERGY_MODES:
        m = snap.get(mode) or {}
        out[f"{mode}_th_kwh"] = round(float(m.get("th", 0.0)), 3)
        out[f"{mode}_el_kwh"] = round(float(m.get("el", 0.0)), 3)
    out["total_th_kwh"] = round(
        sum(float((snap.get(m) or {}).get("th", 0.0)) for m in _ENERGY_MODES),
        3,
    )
    out["total_el_kwh"] = round(
        sum(float((snap.get(m) or {}).get("el", 0.0)) for m in _ENERGY_MODES),
        3,
    )
    return out


def _attrs_runtime_compressor_today_s(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> dict[str, Any]:
    """v1.22.8: per-mode attribution with cross-midnight overlap + native source.

    Removes the pre-v1.22.8 BUH attribute leak (buh_step1_s / buh_step2_s /
    buh_total_s belonged on runtime_buh_today, not runtime_compressor_today).
    Adds ``source`` (native/computed) and ``native_min`` for transparency.
    ``cycle_count`` counts only cycles whose START_TS falls inside today
    (mirrors rollup attribution rule in async_rollup_day).
    """
    attrs = _today_attrs(s, c)
    native_min = read_native_compressor_minutes(attrs)
    now = _now()
    midnight = _local_midnight(now)
    by_mode: dict[str, float] = {"heating": 0.0, "dhw": 0.0, "cooling": 0.0}
    cycle_count = 0
    try:  # v1.22.8 D5: iterate defensively
        for cy in (c.store.cycles_intersecting(midnight, now) or ()):
            try:
                st = float(cy.get("start_ts") or 0.0)
                en = float(cy.get("end_ts") or 0.0)
            except (TypeError, ValueError):
                continue
            ov = min(en, now) - max(st, midnight)
            if ov > 0:
                mode = cy.get("mode") or "unknown"
                if mode in by_mode:
                    by_mode[mode] += ov
            if midnight <= st < now:
                cycle_count += 1
    except Exception:
        pass
    # the open run counts like in the state (its row is written on close);
    # a run open since yesterday was missing from the split (state 9.9 h,
    # heating_s 0)
    if s.state == "running" and s.cycle_start_ts > 0 and s.mode in by_mode:
        by_mode[s.mode] += max(0.0, now - max(float(s.cycle_start_ts), midnight))
    total = sum(by_mode.values())
    return {
        "native_daily": _native_daily(s, c),  # #466
        "source": "native" if native_min is not None else "computed",
        "native_min": native_min,
        "heating_s": int(by_mode["heating"]),
        "dhw_s": int(by_mode["dhw"]),
        "cooling_s": int(by_mode["cooling"]),
        "cycle_count": cycle_count,
        "avg_cycle_s": int(total / cycle_count) if cycle_count else None,
    }


def _attrs_runtime_buh_today_s(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> dict[str, Any]:
    snap = c.runtime_snapshot
    attrs = _today_attrs(s, c)
    native_min = read_native_buh_minutes(attrs)
    _snap = snap if isinstance(snap, dict) else {}
    s1 = float(_snap.get("buh_step1_s", 0.0) or 0.0)
    s2 = float(_snap.get("buh_step2_s", 0.0) or 0.0)
    computed_total = int(_snap.get("buh_total_s", max(s1, s2)))
    # v1.22.8: total_s matches entity state (= _value_runtime_buh_today_s)
    if native_min is not None:
        entity_total = int(round(native_min * 60.0))
        source = "native"
    else:
        entity_total = computed_total
        source = "computed"
    return {
        "native_daily": _native_daily(s, c),  # #466
        "source": source,
        "native_min": native_min,
        "total_s": entity_total,
        "computed_total_s": computed_total,
        "step1_s": int(s1),
        "step2_s": int(s2),
        "step_split_source": "computed",
        **_buh_energy(c, _snap, s1, s2),
    }


def _buh_energy(
    c: DaikinCycleMLCoordinator, snap: dict[str, Any], s1: float, s2: float
) -> dict[str, Any]:
    """#515: the backup heater's own meter when one is set, else step time x kW."""
    if getattr(c, "buh_power_sensor", None) and "buh_meter_kwh" in snap:
        return {
            "buh_energy_kwh_est": round(float(snap.get("buh_meter_kwh") or 0.0), 3),
            "buh_energy_source": "power_meter",
        }
    return {"buh_energy_kwh_est": _buh_energy_kwh_est(c, s1, s2), "buh_energy_source": "computed"}


def _attrs_compressor_starts_today(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> dict[str, Any]:
    """v1.22.8: source-honest attrs. Entity state may be native; per-mode/
    last-hour splits remain computed because firmware exposes no split."""
    attrs = _today_attrs(s, c)
    try:
        cycles = c.store.cycles_today(_now())
    except Exception:
        cycles = []
    per_mode: dict[str, int] = {"heating": 0, "dhw": 0, "cooling": 0}
    for cy in cycles:
        mode = cy.get("mode") or "unknown"
        if mode in per_mode:
            per_mode[mode] += 1
    hour_ago = _now() - 3600.0
    recent = sum(
        1 for cy in cycles
        if float(cy.get("start_ts") or 0.0) >= hour_ago
    )
    computed_count = len(cycles)
    native_count = read_native_compressor_starts(attrs)
    return {
        "native_daily": _native_daily(s, c),  # #466
        "source": "native" if native_count is not None else "computed",
        "native_count": int(native_count) if native_count is not None else None,
        "computed_count": computed_count,
        "per_mode": per_mode,
        "per_mode_source": "computed",
        "starts_last_hour": recent,
        "starts_last_hour_source": "computed",
    }


def _attrs_defrost_count_today(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> dict[str, Any]:
    """v1.22.8: source-honest attrs. Firmware exposes count but not duration."""
    snap = c.runtime_snapshot
    attrs = _today_attrs(s, c)
    _snap = snap if isinstance(snap, dict) else {}
    computed_count = int(_snap.get("defrost_count", 0) or 0)
    dur = float(_snap.get("defrost_duration_s", 0.0) or 0.0)
    native_count = read_native_defrost_count(attrs)
    return {
        "native_daily": _native_daily(s, c),  # #466
        "source": "native" if native_count is not None else "computed",
        "native_count": int(native_count) if native_count is not None else None,
        "computed_count": computed_count,
        "avg_duration_s": round(dur / computed_count, 1) if computed_count > 0 else None,
        "avg_duration_source": "computed",
        "last_defrost_ts": _snap.get("last_defrost_ts") or None,
    }


def _attrs_defrost_duration_today_s(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> dict[str, Any]:
    """v1.22.8: computed-only source (ESPAltherma v2 exposes no native duration)."""
    snap = c.runtime_snapshot
    attrs = _today_attrs(s, c)
    _snap = snap if isinstance(snap, dict) else {}
    computed_count = int(_snap.get("defrost_count", 0) or 0)
    dur = float(_snap.get("defrost_duration_s", 0.0) or 0.0)
    native_count = read_native_defrost_count(attrs)
    return {
        "source": "computed",
        "native_available": False,
        "computed_count": computed_count,
        "native_count": int(native_count) if native_count is not None else None,
        "defrost_count": computed_count,
        "avg_duration_s": round(dur / computed_count, 1) if computed_count > 0 else None,
    }


def _attrs_duty_cycle_today_pct(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> dict[str, Any]:
    now = _now()
    runtime = _value_runtime_compressor_today_s(s, c)
    elapsed = max(1.0, now - _local_midnight(now))
    pct = 100.0 * runtime / elapsed
    if pct < 15.0:
        band = "low"
    elif pct < 60.0:
        band = "nominal"
    elif pct < 85.0:
        band = "high"
    else:
        band = "saturated"
    return {
        "runtime_s": runtime,
        "elapsed_s": int(elapsed),
        "band": band,
    }


def _attrs_daily_summary_recent(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> dict[str, Any]:
    """v1.7.1: attribute payload for the daily_summary_recent sensor.

    #427: ``events_by_day`` (real BUH minutes + defrost events per day,
    #400) was built by the coordinator but never exposed, so the event
    charts of the cards fell back to cycle counts. Only the days of the
    summary window are exposed (runtime_acc keeps one key per day).
    """
    payload = c.daily_summary_recent or {}
    oldest = payload.get("oldest_day")
    events = payload.get("events_by_day") or {}
    return {
        "days_available": payload.get("days_available", 0),
        "days_count": payload.get("days_count", 0),
        "latest_day": payload.get("latest_day"),
        "oldest_day": oldest,
        "days": payload.get("days", []),
        "totals_by_mode": payload.get("totals_by_mode", {}),
        "events_by_day": {
            day: ev for day, ev in sorted(events.items())
            if oldest is None or str(day) >= str(oldest)
        },
    }


def _value_electrical_power_estimated(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> float | None:
    """v1.14.0: electrical input estimate (raomin cascade)."""
    return getattr(s, "electrical_power_w", None)


def _attrs_electrical_power_estimated(
    s: DataSnapshot, c: DaikinCycleMLCoordinator
) -> dict[str, Any]:
    """v1.14.0: source + config context for electrical estimate."""
    from .const import (
        BUH_STEP1_KEY,
        BUH_STEP1_KW_DEFAULT,
        BUH_STEP2_KEY,
        BUH_STEP2_KW_DEFAULT,
        INV_PRIMARY_CURRENT_KEY,
        SUPPLY_PHASES_DEFAULT,
        V2_STATS_KEY,
    )
    attrs = s.attrs or {}
    opts = getattr(c, "options", {}) or {}
    phases = int(opts.get("supply_phases", SUPPLY_PHASES_DEFAULT))
    buh1_kw = float(opts.get("buh_step1_kw", BUH_STEP1_KW_DEFAULT))
    buh2_kw = float(opts.get("buh_step2_kw", BUH_STEP2_KW_DEFAULT))
    return {
        "source": getattr(s, "electrical_power_source", "none"),
        "supply_phases": phases,
        "buh_step1_kw": buh1_kw,
        "buh_step2_kw": buh2_kw,
        "v2_stats_present": V2_STATS_KEY in attrs,
        "inv_current_a": attrs.get(INV_PRIMARY_CURRENT_KEY),
        "buh_step1_on": str(attrs.get(BUH_STEP1_KEY, "")).strip().upper() == "ON",
        "buh_step2_on": str(attrs.get(BUH_STEP2_KEY, "")).strip().upper() == "ON",
        # optional backup-heater meter, included in the state when set
        "buh_power_sensor": opts.get("buh_power_sensor_entity"),
        "buh_meter_w": getattr(c, "_last_buh_meter_w", None),
    }


SENSOR_DEFS: list[dict[str, Any]] = [
    {
        "key": "thermal_power_live", "name": "Thermal power live",
        "state_class": SensorStateClass.MEASUREMENT,
        "device_class": SensorDeviceClass.POWER,
        "unit": "kW",
        "value_fn": _value_thermal_power_live,
        "attr_fn": _attrs_thermal_power_live,
    },
    {
        "key": "electrical_power_estimated",
        "name": "Electrical power estimated",
        "state_class": SensorStateClass.MEASUREMENT,
        "device_class": SensorDeviceClass.POWER,
        "unit": "W",
        "entity_category": "diagnostic",
        "value_fn": _value_electrical_power_estimated,
        "attr_fn": _attrs_electrical_power_estimated,
    },
    {
        "key": "hp_specs", "name": "HP specs",
        "entity_category": "diagnostic",
        "value_fn": _value_hp_specs,
        "attr_fn": _attrs_hp_specs,
    },
    {
        "key": "cop_normalized_a7w35", "name": "COP normalized A7W35",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP",
        "value_fn": _value_cop_normalized_a7w35,
        "attr_fn": _attrs_cop_normalized_a7w35,
    },
    {
        "key": "cop_vs_datasheet_pct", "name": "COP vs datasheet pct",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "%",
        "value_fn": _value_cop_vs_datasheet_pct,
        "attr_fn": _attrs_cop_vs_datasheet_pct,
    },
    {
        "key": "cop_degradation_status", "name": "COP degradation status",
        "device_class": SensorDeviceClass.ENUM,
        "options": ["none", "info", "warning", "critical"],
        "value_fn": _value_cop_degradation_status,
        "attr_fn": _attrs_cop_degradation_status,
    },
    {
        "key": "cop_degradation_week_pct", "name": "COP degradation week pct",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "%",
        "value_fn": _value_cop_degradation_week_pct,
        "attr_fn": _attrs_cop_degradation_week_pct,
    },
    {
        "key": "cop_trend_30d", "name": "COP trend 30d",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "%",
        "value_fn": _value_cop_trend_30d,
        "attr_fn": _attrs_cop_trend_30d,
    },
    {
        "key": "cycle_state", "name": "Cycle state",
        "value_fn": lambda s, c: s.state,
        "attr_fn": _attrs_cycle_state,
    },
    {
        "key": "current_cycle", "name": "Current cycle",
        "value_fn": lambda s, c: s.mode if s.state == "running" else "idle",
        "attr_fn": _attrs_current_cycle,
    },
    {
        "key": "last_cycle", "name": "Last cycle",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "score",
        "value_fn": lambda s, c: _last(c).get("quality_score"),
        "attr_fn": _attrs_last_cycle,
    },
    {
        "key": "alerts_today", "name": "Alerts today",
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda s, c: (s.alerts_today or {}).get("total", 0),
        "attr_fn": _attrs_alerts_today,
    },
    {
        "key": "cycles_today", "name": "Cycles today",
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "value_fn": lambda s, c: len(c.store.cycles_today(_now())),
        "attr_fn": _attrs_today,
    },
    {
        "key": "quality_today", "name": "Quality today",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "score",
        "value_fn": _compute_quality_today,
        "attr_fn": _attrs_quality_today,
    },
    {
        "key": "runtime_compressor_today",
        "name": "Runtime compressor today",
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "device_class": SensorDeviceClass.DURATION,
        "unit": "s",
        "value_fn": _value_runtime_compressor_today_s,
        "attr_fn": _attrs_runtime_compressor_today_s,
    },
    {
        "key": "runtime_buh_today",
        "name": "Runtime BUH today",
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "device_class": SensorDeviceClass.DURATION,
        "unit": "s",
        "value_fn": _value_runtime_buh_today_s,
        "attr_fn": _attrs_runtime_buh_today_s,
    },
    {
        "key": "compressor_starts_today",
        "name": "Compressor starts today",
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "value_fn": _value_compressor_starts_today,
        "attr_fn": _attrs_compressor_starts_today,
    },
    {
        "key": "defrost_count_today",
        "name": "Defrost count today",
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "value_fn": _value_defrost_count_today,
        "attr_fn": _attrs_defrost_count_today,
    },
    {
        "key": "defrost_duration_today",
        "name": "Defrost duration today",
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "device_class": SensorDeviceClass.DURATION,
        "unit": "s",
        "value_fn": _value_defrost_duration_today_s,
        "attr_fn": _attrs_defrost_duration_today_s,
    },
    {
        "key": "duty_cycle_today",
        "name": "Duty cycle today",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "%",
        "value_fn": _value_duty_cycle_today_pct,
        "attr_fn": _attrs_duty_cycle_today_pct,
    },
    {
        "key": "electrical_energy_heating_today",
        "name": "Electrical energy heating today",
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "device_class": SensorDeviceClass.ENERGY,
        "unit": "kWh",
        "value_fn": _value_energy_kwh("heating", "el"),
        "attr_fn": _attrs_energy_snapshot,
    },
    {
        "key": "electrical_energy_dhw_today",
        "name": "Electrical energy dhw today",
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "device_class": SensorDeviceClass.ENERGY,
        "unit": "kWh",
        "value_fn": _value_energy_kwh("dhw", "el"),
        "attr_fn": _attrs_energy_snapshot,
    },
    {
        "key": "electrical_energy_cooling_today",
        "name": "Electrical energy cooling today",
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "device_class": SensorDeviceClass.ENERGY,
        "unit": "kWh",
        "value_fn": _value_energy_kwh("cooling", "el"),
        "attr_fn": _attrs_energy_snapshot,
    },
    {
        "key": "electrical_energy_total_today",
        "name": "Electrical energy total today",
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "device_class": SensorDeviceClass.ENERGY,
        "unit": "kWh",
        "value_fn": _value_energy_total_kwh("el"),
        "attr_fn": _attrs_energy_snapshot,
    },
    {
        "key": "thermal_energy_heating_today",
        "name": "Thermal energy heating today",
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "device_class": SensorDeviceClass.ENERGY,
        "unit": "kWh",
        "value_fn": _value_energy_kwh("heating", "th"),
        "attr_fn": _attrs_energy_snapshot,
    },
    {
        "key": "thermal_energy_cooling_today",
        "name": "Thermal energy cooling today",
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "device_class": SensorDeviceClass.ENERGY,
        "unit": "kWh",
        "value_fn": _value_energy_kwh("cooling", "th"),
        "attr_fn": _attrs_energy_snapshot,
    },
    {
        "key": "source_health", "name": "Source health",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTime.SECONDS,
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
        "value_fn": _value_learned,
        "attr_fn": _attrs_learned,
    },
    {
        "key": "cop_today", "name": "COP today",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP",
        # #523: a day value: it stays when the compressor stops (the running
        # gate of #285 is for live values only: thermal power, vs datasheet)
        "value_fn": lambda s, c: (s.cop_today or {}).get("cop"),
        "attr_fn": _attrs_cop_today,
    },
    {
        "key": "cop_combined_today", "name": "COP combined today",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP",
        "value_fn": lambda s, c: (s.cop_combined_today or {}).get("cop"),
        "attr_fn": _attrs_cop_combined_today,
    },
    {
        "key": "spf_season", "name": "SPF season",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "SPF",
        "value_fn": lambda s, c: (s.spf_state or {}).get("spf_season"),
        "attr_fn": _attrs_spf_state,
    },
    {
        "key": "spf_ytd", "name": "SPF YTD",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "SPF",
        "value_fn": lambda s, c: (s.spf_state or {}).get("spf_ytd"),
        "attr_fn": _attrs_spf_state,
    },
    {
        "key": "scop_running_365d", "name": "SCOP running 365d",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "SPF",
        "value_fn": lambda s, c: (s.spf_state or {}).get("scop_365d"),
        "attr_fn": _attrs_spf_state,
    },
    {
        # #508: headline of the last finished month (COP, kWh, change)
        "key": "last_month_report", "name": "Last month report",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP",
        "value_fn": lambda s, c: (getattr(c, "last_month_report", None) or {}).get("cop"),
        "attr_fn": lambda s, c: dict(getattr(c, "last_month_report", None) or {}),
    },
    {
        # #495: degree days so far today (configured scheme), season and yesterday
        "key": "degree_days_today", "name": "Degree days today",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "DD",
        "value_fn": lambda s, c: (getattr(c, "degree_days", None) or {}).get("today"),
        "attr_fn": _attrs_degree_days,
    },
    {
        # #495: heating kWh per degree day, last 7 complete days
        "key": "heat_per_degree_day", "name": "Heat per degree day",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "kWh/DD",
        "value_fn": lambda s, c: ((getattr(c, "degree_days", None) or {}).get("week") or {}).get("kwh_per_dd"),
        "attr_fn": _attrs_heat_per_dd,
    },
    {
        "key": "heating_curve_advice", "name": "Heating curve advice",
        "value_fn": lambda s, c: (s.stooklijn_advies or {}).get("state", "unknown"),
        "attr_fn": _attrs_stooklijn,
    },
    {
        "key": "cop_mean_day", "name": "COP mean (24h)",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP",
        "value_fn": _cop_hourly_heating_mean("day"),
        "attr_fn": _attrs_cop_hourly("day"),
    },
    {
        "key": "cop_mean_week", "name": "COP mean (7d)",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP",
        "value_fn": _cop_hourly_heating_mean("week"),
        "attr_fn": _attrs_cop_hourly("week"),
    },
    {
        "key": "cop_mean_month", "name": "COP mean (30d)",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP",
        "value_fn": _cop_hourly_heating_mean("month"),
        "attr_fn": _attrs_cop_hourly("month"),
    },
    {
        "key": "cop_curve_recent", "name": "COP curve (48h)",
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda s, c: (s.cop_curve_recent or {}).get(
            "n_points"
        ),
        "attr_fn": _attrs_cop_curve_recent,
    },
    {
        "key": "cop_heating_day", "name": "COP heating (day)",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP",
        "value_fn": _cop_hourly_mode_mean("heating", "day"),
        "attr_fn": _attrs_cop_hourly_mode("heating", "day"),
    },
    {
        "key": "cop_heating_week", "name": "COP heating (week)",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP",
        "value_fn": _cop_hourly_mode_mean("heating", "week"),
        "attr_fn": _attrs_cop_hourly_mode("heating", "week"),
    },
    {
        "key": "cop_heating_month", "name": "COP heating (month)",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP",
        "value_fn": _cop_hourly_mode_mean("heating", "month"),
        "attr_fn": _attrs_cop_hourly_mode("heating", "month"),
    },
    {
        "key": "cop_dhw_day", "name": "COP DHW (day)",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP",
        "value_fn": _cop_hourly_mode_mean("dhw", "day"),
        "attr_fn": _attrs_cop_hourly_mode("dhw", "day"),
    },
    {
        "key": "cop_dhw_week", "name": "COP DHW (week)",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP",
        "value_fn": _cop_hourly_mode_mean("dhw", "week"),
        "attr_fn": _attrs_cop_hourly_mode("dhw", "week"),
    },
    {
        "key": "cop_dhw_month", "name": "COP DHW (month)",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP",
        "value_fn": _cop_hourly_mode_mean("dhw", "month"),
        "attr_fn": _attrs_cop_hourly_mode("dhw", "month"),
    },
    {
        "key": "cop_cooling_day", "name": "COP cooling (day)",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP",
        "value_fn": _cop_hourly_mode_mean("cooling", "day"),
        "attr_fn": _attrs_cop_hourly_mode("cooling", "day"),
    },
    {
        "key": "cop_cooling_week", "name": "COP cooling (week)",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP",
        "value_fn": _cop_hourly_mode_mean("cooling", "week"),
        "attr_fn": _attrs_cop_hourly_mode("cooling", "week"),
    },
    {
        "key": "cop_cooling_month", "name": "COP cooling (month)",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP",
        "value_fn": _cop_hourly_mode_mean("cooling", "month"),
        "attr_fn": _attrs_cop_hourly_mode("cooling", "month"),
    },
    {
        "key": "daily_summary_recent", "name": "Daily summary recent",
        "state_class": SensorStateClass.MEASUREMENT,
        "value_fn": lambda s, c: (c.daily_summary_recent or {}).get("state"),
        "attr_fn": _attrs_daily_summary_recent,
    },
    {
        "key": "hybrid_mode",
        "requires_hybrid": True, "name": "Hybrid mode",
        "device_class": SensorDeviceClass.ENUM,
        "options": ["H/P only", "Hybrid", "Boiler only", "unknown"],
        "entity_category": EntityCategory.DIAGNOSTIC,
        "value_fn": lambda s, c: (s.hybrid_mode or "unknown") if s.is_hybrid else None,
        "attr_fn": lambda s, c: (
            {"raw": s.hybrid_mode or "", "install_type": "hybrid"}
            if s.is_hybrid
            else {"install_type": "non_hybrid"}
        ),
    },
    {
        "key": "boiler_efficiency_cop",
        "requires_hybrid": True, "name": "Boiler efficiency COP",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "COP",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "value_fn": lambda s, c: s.boiler_efficiency_cop if s.is_hybrid else None,
        "attr_fn": lambda s, c: (
            {"source": "BE COP", "info_only": True}
            if s.is_hybrid
            else {"info_only": True, "note": "hybrid install only"}
        ),
    },
    {
        "key": "boiler_contribution_today_pct",
        "requires_hybrid": True,
        "name": "Boiler contribution today pct",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "%",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "value_fn": lambda s, c: (
            (s.cop_today or {}).get("boiler_pct") if s.is_hybrid else None
        ),
        "attr_fn": lambda s, c: (
            {
                "hint": "Percentage of today's HP samples taken during boiler "
                        "co-fire; excluded from cop_today to keep HP-COP pure",
            }
            if s.is_hybrid
            else {"hint": "hybrid install only"}
        ),
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
    entry_id = entry.entry_id
    entry_domain = entry.domain
    owned = {
        e.entity_id
        for e in er.async_entries_for_config_entry(
            registry, entry_id
        )
        if e.platform == DOMAIN
    }

    # v1.3.1 slug-only fixes (unique_id unchanged).
    slug_fixes = {
        "sensor.daikin_cycle_ml":               "sensor.daikin_cycle_ml_cop_mean_day",
        "sensor.daikin_cycle_ml_2":             "sensor.daikin_cycle_ml_cop_mean_week",
        "sensor.daikin_cycle_ml_3":             "sensor.daikin_cycle_ml_cop_mean_month",
        "sensor.daikin_cycle_ml_cop_curve_48h": "sensor.daikin_cycle_ml_cop_curve_recent",
    }
    for old_eid, new_eid in slug_fixes.items():
        if old_eid in owned and registry.async_get(new_eid) is None:
            registry.async_update_entity(old_eid, new_entity_id=new_eid)

    # v1.4.0 key renames: entity_id + unique_id + translation_key.
    #
    # Idempotency (issue #141): a prior run may have already updated the
    # unique_id but not the entity_id (partial migration, or user reverted
    # the entity_id by hand). In that case async_update_entity with
    # new_unique_id raises "Unique id ... is already in use" because the
    # target unique_id is owned by the very entity we are renaming.
    # Detect that case and update only entity_id + translation_key.
    key_fixes = {
        "today": "cycles_today",
        "cop_vandaag": "cop_today",
        "stooklijn_advies": "heating_curve_advice",
    }
    for old_key, new_key in key_fixes.items():
        old_eid = "sensor.daikin_cycle_ml_" + old_key
        new_eid = "sensor.daikin_cycle_ml_" + new_key
        new_uid = f"{entry_domain}_{entry_id}_{new_key}"
        old_entry = registry.async_get(old_eid)
        if old_entry is None or old_entry.entity_id not in owned:
            continue
        if registry.async_get(new_eid) is not None:
            # entity_id target occupied by a different entity -> skip
            continue
        if old_entry.unique_id == new_uid:
            # unique_id already migrated, only entity_id + translation_key
            registry.async_update_entity(
                old_eid,
                new_entity_id=new_eid,
                translation_key=new_key,
            )
        else:
            registry.async_update_entity(
                old_eid,
                new_entity_id=new_eid,
                new_unique_id=new_uid,
                translation_key=new_key,
            )

async def async_setup_entry(
    hass: HomeAssistant,
    entry: DaikinCycleMLConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coord = getattr(entry, "runtime_data", None)
    if coord is None:
        _LOGGER.error("Coordinator not found for %s", entry.entry_id)
        return
    _migrate_entity_ids(hass, entry)
    is_hybrid = bool(coord.data and getattr(coord.data, "is_hybrid", False))
    if not is_hybrid:
        hk = frozenset(d["key"] for d in SENSOR_DEFS if d.get("requires_hybrid"))
        async_remove_stale_entities(hass, entry.entry_id, hk)
    entities = [
        (DaikinCycleMLLargeSensor if spec["key"] in LARGE_ATTR_SENSORS else DaikinCycleMLSensor)(
            coord,
            key=spec["key"],
            name=spec["name"],
            value_fn=spec["value_fn"],
            attr_fn=spec.get("attr_fn"),
            device_class=spec.get("device_class"),
            state_class=spec.get("state_class"),
            unit=spec.get("unit"),
            entity_category=spec.get("entity_category"),
        )
        for spec in SENSOR_DEFS
        if not (spec.get("requires_hybrid") and not is_hybrid)
    ]
    async_add_entities(entities)


# Sensors with attributes that can pass the recorder's 16 KB limit (31 days
# x modes, 48 h of hourly points, every alert of the day). The recorder then
# drops all their attributes and logs a warning on every update. The cards
# read the current state only, so these attributes stay out of the recorder.
LARGE_ATTR_SENSORS = frozenset({
    "daily_summary_recent", "cop_curve_recent", "alerts_today",
    "hp_specs", "heating_curve_advice",
})


class DaikinCycleMLLargeSensor(DaikinCycleMLSensor):
    """Sensor whose large attributes are not written to the recorder."""

    _unrecorded_attributes = frozenset({
        "days", "events_by_day", "totals_by_mode",   # daily_summary_recent
        "points",                                    # cop_curve_recent, hp_specs
        "alerts", "by_type",                         # alerts_today
        "datasheet_sources",                         # hp_specs
        "buckets",                                   # heating_curve_advice
    })


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
