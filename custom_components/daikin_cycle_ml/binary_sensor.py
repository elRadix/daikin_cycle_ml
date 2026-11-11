"""Binary sensor platform for Daikin Cycle ML (Batch 31d).

17 binary sensors. BUH step1/2 merged into buh_active with step attribute.
Cluster binaries removed (see sensor.last_cycle attribute "cluster").
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_BUH_STEP1,
    ATTR_BUH_STEP2,
    ATTR_DEFROST_OPERATION,
    ATTR_IU_OPERATION_MODE,
    MODE_COOLING,
    MODE_DHW,
    MODE_HEATING,
    UPDATE_INTERVAL_SECONDS,
    tolerant_on,
)
from .coordinator import DaikinCycleMLCoordinator, DataSnapshot
from .engine.timer_health import is_stale
from .entity import DaikinCycleMLEntity, async_remove_stale_entities
from .storage.store import _is_transient_int

PARALLEL_UPDATES = 0  # read-only platform, HA serializes updates


_LOGGER = logging.getLogger(__name__)

SOURCE_STALE_FACTOR = 4.0  # v1.19.8: tolerate single missed tick (was 2.0=60s, now 4.0=120s)


def _now() -> float:
    return time.time()


def _attr_on(attrs: dict[str, Any], key: str) -> bool:
    """#308: delegate to tolerant_on."""
    return tolerant_on(attrs.get(key))


def _attr_is_mode(attrs: dict[str, Any], key: str, mode_lower: str) -> bool:
    raw = attrs.get(key)
    if isinstance(raw, str):
        return raw.strip().lower() == mode_lower
    return False


def _attr_contains_mode(
    attrs: dict[str, Any], key: str, mode_lower: str,
) -> bool:
    """True if the attr string contains mode_lower as a token.

    Handles compound modes like "Heating + DHW" and "Cooling/DHW".
    Reference: issue #116, handoff v91.0 R441/R442.
    """
    raw = attrs.get(key)
    if not isinstance(raw, str):
        return False
    s = raw.strip().lower().replace("/", "+")
    tokens = {t.strip() for t in s.split("+") if t.strip()}
    return mode_lower in tokens


def _is_short_run(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> bool:
    last = c.store.last_cycle()
    if not last:
        return False
    # v1.19.6 FASE 5B: last may be corrupt (non-dict) after hydration.
    if not isinstance(last, dict):
        return False
    # 52b5: skip DHW cycles -- short bursts are normal during DHW
    if str(last.get("mode", "")).strip().lower() == "dhw":
        return False
    # #246: skip transient pump-only LWT sampling pulses (same class as #245)
    # v1.19.6 FASE 5B: numeric parse (was truthy check; string "0"/"false"
    # silently disabled short_run -> false negative).
    if _is_transient_int(last.get("is_transient")):
        return False
    dur = last.get("duration_s")
    if not isinstance(dur, (int, float)):
        return False
    # v1.19.7 #259: a stale cycle (end_ts > 1h ago) is not a live
    # short-run. Prevents false positives after HA restart when the
    # store hydrates a cycle from a previous day/session.
    end_ts = last.get("end_ts")
    if isinstance(end_ts, (int, float)) and (_now() - end_ts) > 3600.0:
        return False
    return float(dur) < int(c.options.get("short_run_threshold_min", 20)) * 60


def _is_short_cycling_pattern(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> bool:
    """v1.19.7 #11: 3+ short runs within window = structural cycling pattern."""
    try:
        mc = int(c.options.get("short_cycling_min_cycles", 3))
        wm = int(c.options.get("short_cycling_window_min", 60))
        thr = int(c.options.get("short_run_threshold_min", 20)) * 60
        n = c.store.count_short_in_window_mode(_now(), wm * 60, thr, MODE_HEATING)
        return int(n) >= mc
    except (TypeError, ValueError, AttributeError):
        return False


def _short_cycling_pattern_attrs(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> dict[str, Any] | None:
    """v1.19.7 #11: diagnostic attributes for the short_cycling_pattern sensor."""
    try:
        wm = int(c.options.get("short_cycling_window_min", 60))
        mc = int(c.options.get("short_cycling_min_cycles", 3))
        thr_min = int(c.options.get("short_run_threshold_min", 20))
        now = _now()
        n = int(c.store.count_short_in_window_mode(
            now, wm * 60, thr_min * 60, MODE_HEATING))
        recent = c.store.short_runs_in_window_mode(
            now, wm * 60, thr_min * 60, MODE_HEATING, limit=10)
        return {
            "window_min": wm,
            "min_cycles_threshold": mc,
            "short_run_threshold_min": thr_min,
            "pattern_count_60min": n,
            "recent_short_runs": recent,
        }
    except (TypeError, ValueError, AttributeError):
        return None


def _is_short_off(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> bool:
    # 52b5: skip DHW -- off-times during DHW are not meaningful
    # v1.19.6 FASE 5B: guard against corrupt non-dict last_cycle.
    last = c.store.last_cycle()
    if last and not isinstance(last, dict):
        return False
    # v1.19.7: pump-only LWT pulses are not real off-times. Skip transient
    # predecessor -- same principle as #246 (short_run) and v1.19.6 (#257).
    if last and _is_transient_int(last.get("is_transient")):
        return False
    if last and str(last.get("mode", "")).strip().lower() == "dhw":
        return False
    if str(getattr(s, "mode", "")).strip().lower() == "dhw":
        return False
    # #245: use the completed gap from the cycle record, not the live
    # off_time_since_last(now). Live off-time resets to ~0 when a cycle
    # ends, which would fire the alert immediately after EVERY cycle
    # regardless of the actual gap before it.
    off = (last or {}).get("off_s")
    if not isinstance(off, (int, float)):
        return False
    # v1.19.7 #259: a stale cycle (end_ts > 1h ago) is not a live off-time.
    end_ts_off = (last or {}).get("end_ts")
    if isinstance(end_ts_off, (int, float)) and (_now() - end_ts_off) > 3600.0:
        return False
    threshold = int(c.options.get("short_off_threshold_min", 5)) * 60
    if off >= threshold:
        return False
    # v1.19.7 fix #10: short_off requires at least one short run in the pair.
    # A short gap between two long runs (e.g. 264min -> 60s -> 84min) is
    # normal hysteresis restart, not short-cycling. Short-cycling is
    # short-run -> short-off -> short-run.
    cycles = c.store.cycles()
    if len(cycles) < 2:
        return True  # no prev cycle to compare, preserve old behavior
    prev_max_s = int(c.options.get("short_run_threshold_min", 20)) * 60
    # (last or {}) idiom: mypy can't prove `last` is not None here even
    # though the off_s check above guarantees it. Behavior identical.
    last_dur = (last or {}).get("duration_s")
    prev_dur = cycles[-2].get("duration_s")
    last_is_short = isinstance(last_dur, (int, float)) and last_dur < prev_max_s
    prev_is_short = isinstance(prev_dur, (int, float)) and prev_dur < prev_max_s
    return bool(last_is_short or prev_is_short)


def _is_source_stale(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> bool:
    # v1.19.9: normalize last_success_ts -- coordinator delegates to
    # this function for the alert path, and partial mocks or pre-tick
    # snaps can carry None or non-numeric values. Coerce safely.
    try:
        _last_ok = float(getattr(s, "last_success_ts", 0.0) or 0.0)
    except (TypeError, ValueError):
        _last_ok = 0.0
    if _last_ok <= 0:
        return False
    thr = SOURCE_STALE_FACTOR * UPDATE_INTERVAL_SECONDS
    # v1.19.9: check the SOURCE entity last_updated, not our own tick.
    # Pre-fix a slow tick (ML pipeline / rollup / datasheet refresh)
    # made this fire critical alerts even though the source was
    # updating every 22-33s. Real prod 2026-11-05: alerts at 09:15,
    # 10:16, 11:18 (61-62 min apart) with healthy source throughout.
    hass = getattr(c, "hass", None)
    src_entity = getattr(c, "source_entity", None)
    if hass is not None and src_entity:
        st = hass.states.get(src_entity)
        if st is not None:
            # v1.19.9: isinstance gate -- MagicMock/None/broken state
            # falls through to tick-based fallback instead of raising
            # TypeError on `MagicMock > float` comparisons.
            from datetime import datetime as _dt
            lu = getattr(st, "last_updated", None)
            if isinstance(lu, _dt):
                return (_now() - lu.timestamp()) > thr
    # Fallback: no hass handle (unit test) or source missing -> tick.
    return is_stale(_last_ok, _now(), thr)


def _is_pendulum_hourly(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> bool:
    """v1.19.6 (scope A): HEATING-only pendulum detection.

    Previous logic (all_non_dhw) counted cooling and defrost as heating,
    inflating the count and producing false positives during shoulder
    seasons. Strict mode-counting is also cheaper and removes the
    silent-except fallback (R580) that turned a failed query into dhw_n=0.
    """
    threshold = int(c.options.get("pendulum_cycles_per_hour", 4))
    return c.store.cycles_in_window_mode(_now(), 3600, MODE_HEATING) >= threshold


def _is_pendulum_daily(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> bool:
    """v1.19.6: transient-aware daily pendulum detection.

    Companion fix to #245/#246 (short_off/short_run) and v1.19.6 FIX A
    (pendulum_hourly). Pre-fix, cycles_today() included pump-only LWT
    sampling pulses (is_transient=1), inflating the daily count and
    firing false pendulum_daily alerts. non_transient_today() has existed
    since v1.12.0 (#105) but was never wired here.
    """
    threshold = int(c.options.get("pendulum_cycles_per_day", 40))
    return len(c.store.non_transient_today(_now())) >= threshold


def _is_dhw_pendulum(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> bool:
    threshold = int(c.options.get("dhw_pendulum_cycles_per_hour", 3))
    return c.store.cycles_in_window_mode(_now(), 3600, MODE_DHW) >= threshold


def _is_high_cycle_rate(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> bool:
    base = int(c.options.get("pendulum_cycles_per_hour", 4))
    return c.store.cycles_in_window(_now(), 3600) > base * 1.5


def _is_dhw_active(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> bool:
    """DHW active requires I/U mode == DHW AND (compressor or BUH).

    The 3-way valve default-rests in DHW position on Daikin units
    (fail-safe for boiler priority on power loss). Valve state alone
    is therefore NOT a valid DHW signal.
    """
    if not _attr_contains_mode(s.attrs, ATTR_IU_OPERATION_MODE, MODE_DHW):
        return False
    if s.state == "running":
        return True
    return _is_buh_active(s, c)


def _is_buh_active(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> bool:
    return _attr_on(s.attrs, ATTR_BUH_STEP1) or _attr_on(s.attrs, ATTR_BUH_STEP2)


def _buh_step(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> int:
    if _attr_on(s.attrs, ATTR_BUH_STEP2):
        return 2
    if _attr_on(s.attrs, ATTR_BUH_STEP1):
        return 1
    return 0


def _buh_attrs(s: DataSnapshot, c: DaikinCycleMLCoordinator) -> dict[str, Any]:
    return {"step": _buh_step(s, c)}


StateFn = Callable[[DataSnapshot, DaikinCycleMLCoordinator], bool]
AttrFn = Callable[[DataSnapshot, DaikinCycleMLCoordinator], dict[str, Any]]


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
        except Exception:
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
        except Exception:
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
    {"key": "short_cycling_pattern", "name": "Short cycling pattern",
     "device_class": BinarySensorDeviceClass.PROBLEM,
     "icon": "mdi:repeat-variant",
     "state_fn": _is_short_cycling_pattern,
     "attr_fn": _short_cycling_pattern_attrs},
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
    {"key": "cop_physically_impossible",
     "name": "COP physically impossible",
     "device_class": BinarySensorDeviceClass.PROBLEM,
     "state_fn": lambda s, c: int(
         getattr(c, "_cop_rejected_today_count", 0) or 0
     ) > 0},
    {"key": "missing_attrs", "name": "Missing attributes",
     "device_class": BinarySensorDeviceClass.PROBLEM,
     "state_fn": lambda s, c: len(s.missing_attrs) > 0},
    {"key": "setpoint_oscillating", "name": "Setpoint oscillating",
     "device_class": BinarySensorDeviceClass.PROBLEM,
     "icon": "mdi:sine-wave",
     "state_fn": lambda s, c: s.setpoint_oscillating},
    {"key": "dhw_pendulum", "name": "DHW pendulum",
     "device_class": BinarySensorDeviceClass.PROBLEM,
     "icon": "mdi:water-boiler-alert",
     "state_fn": _is_dhw_pendulum},
    {"key": "dhw_installed", "name": "DHW installed",
     "icon": "mdi:water-boiler",
     "state_fn": lambda s, c: bool(getattr(c, "dhw_present", True))},
    {"key": "high_cycle_rate", "name": "High cycle rate",
     "device_class": BinarySensorDeviceClass.PROBLEM,
     "icon": "mdi:speedometer",
     "state_fn": _is_high_cycle_rate},
    {"key": "boiler_operation_demand", "requires_hybrid": True, "name": "Boiler operation demand",
     "device_class": BinarySensorDeviceClass.RUNNING,
     "icon": "mdi:fire",
     "entity_category": EntityCategory.DIAGNOSTIC,
     "state_fn": lambda s, c: s.boiler_active if s.is_hybrid else None},
    {"key": "boiler_dhw_demand", "requires_hybrid": True, "name": "Boiler DHW demand",
     "device_class": BinarySensorDeviceClass.RUNNING,
     "icon": "mdi:water-boiler",
     "entity_category": EntityCategory.DIAGNOSTIC,
     "state_fn": lambda s, c: s.boiler_dhw_active if s.is_hybrid else None},
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
    is_hybrid = bool(coord.data and getattr(coord.data, "is_hybrid", False))
    if not is_hybrid:
        hk = frozenset(d["key"] for d in BINARY_SENSOR_DEFS if d.get("requires_hybrid"))
        async_remove_stale_entities(hass, entry.entry_id, hk)
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
        if not (spec.get("requires_hybrid") and not is_hybrid)
    ]
    async_add_entities(entities)
