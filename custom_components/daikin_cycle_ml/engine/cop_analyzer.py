"""Batch 14a: COP / stooklijn analysis from global_cop attributes."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

_NUM_RE = re.compile(r'-?\d+(?:\.\d+)?')
STOOKLIJN_RECENT_WINDOW_S = 48 * 3600


from ..const import (
    COMFORT_TOLERANCE,
    K_EMIT_DEFAULT,
    LWT_STEP_MAX,
    LWT_STEP_MIN,
    LWT_TRACKING_TOLERANCE,
)


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    low = s.lower()
    if 'invalid' in low or 'unknown' in low or 'unavailable' in low:
        return None
    m = _NUM_RE.search(s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:  # pragma: no cover
        return None  # pragma: no cover


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().upper() == 'ON'
    return bool(value)


@dataclass
class CopSample:
    cop: float
    lwt: float | None = None
    inlet: float | None = None
    delta_t: float | None = None
    thermal_kw: float | None = None
    elec_kw: float | None = None
    outdoor: float | None = None
    flow_lmin: float | None = None
    buh: bool = False
    defrost: bool = False
    power_stable: bool = False
    data_quality: str = 'unknown'
    mode: str = 'unknown'
    ts: float = 0.0

    @property
    def valid(self) -> bool:
        return (
            self.cop > 0.0
            and not self.defrost
            and self.data_quality == 'Good'
        )


@dataclass
class StooklijnAdvies:
    state: str = 'unknown'
    huidige_lwt: float | None = None
    optimale_lwt: float | None = None
    besparing_cop_pct: float = 0.0
    comfort_impact: float = 0.0
    betrouwbaarheid: float = 0.0
    bucket: str = ''
    samples: int = 0
    setpoint_lwt: float | None = None
    doel_setpoint: float | None = None
    step_c: int = 0
    delta_c: float = 0.0
    tracking_error: float | None = None
    err_indoor: float | None = None
    urgency: float = 0.0
    comfort_cap: float = 3.0
    reason: str = ''


def parse_global_cop_attrs(attrs: dict[str, Any] | None) -> CopSample | None:
    if not attrs:
        return None
    cop = _parse_float(attrs.get('state') or attrs.get('cop'))
    if cop is None:
        return None
    flow_raw = attrs.get('flow_rate')
    flow = None
    if isinstance(flow_raw, str):
        if not flow_raw.lower().startswith('invalid'):
            flow = _parse_float(flow_raw)
    else:
        flow = _parse_float(flow_raw)
    return CopSample(
        cop=cop,
        lwt=_parse_float(attrs.get('leaving_temp')),
        inlet=_parse_float(attrs.get('inlet_temp')),
        delta_t=_parse_float(attrs.get('delta_t')),
        thermal_kw=_parse_float(attrs.get('thermal_power')),
        elec_kw=_parse_float(attrs.get('electrical_input')),
        outdoor=_parse_float(attrs.get('outdoor_temperature')),
        flow_lmin=flow,
        buh=_parse_bool(attrs.get('backup_heater_active')),
        defrost=(
            str(attrs.get('defrost_operation', 'OFF')).strip().upper() == 'ON'
        ),
        power_stable=_parse_bool(attrs.get('power_stable')),
        data_quality=str(attrs.get('data_quality', 'unknown')),
    )


def bucket_for_outdoor(temp: float | None) -> str:
    if temp is None:
        return 'unknown'
    lo = int(temp // 2) * 2
    if lo < -10:
        return '-10-'
    if lo >= 20:
        return '20+'
    return f"{lo}-{lo + 2}"


def _group_by_bucket(samples: list[CopSample]) -> dict[str, list[CopSample]]:
    out: dict[str, list[CopSample]] = {}
    for s in samples:
        if not s.valid:
            continue
        if s.mode not in ('heating', 'unknown'):  # pragma: no cover
            continue
        b = bucket_for_outdoor(s.outdoor)
        out.setdefault(b, []).append(s)
    return out


def _avg(xs: list[float]) -> float | None:
    if not xs:
        return None
    return sum(xs) / len(xs)


def analyze_stooklijn(
    samples: list[CopSample],
    comfort_min: float = 20.0,
    indoor_avg: float | None = None,
    *,
    now: float | None = None,
    setpoint_lwt: float | None = None,
    comfort_max: float = 24.0,
    rt_setpoint: float | None = None,
) -> StooklijnAdvies:
    advies = StooklijnAdvies()
    _input_len = len(samples)
    samples = [s for s in samples if s.mode in ('heating', 'unknown')]
    if _input_len > 0 and not samples:
        advies.state = 'no_data'
        advies.reason = 'no_recent_heating'
        return advies
    grouped = _group_by_bucket(samples)
    if not grouped:
        return advies
    # 52b2: recent selection = laatste 'heating' binnen 48u window
    now_ts = now if now is not None else time.time()
    recent = None
    for s in reversed(samples):
        if not s.valid:
            continue
        if s.ts > 0 and (now_ts - s.ts) > STOOKLIJN_RECENT_WINDOW_S:
            continue
        recent = s
        break
    if recent is None:
        advies.state = 'no_data'
        advies.reason = 'no_recent_heating'
        return advies
    current_bucket = bucket_for_outdoor(recent.outdoor)
    advies.bucket = current_bucket
    advies.huidige_lwt = recent.lwt
    bucket_samples = grouped.get(current_bucket, [])
    advies.samples = len(bucket_samples)
    advies.betrouwbaarheid = min(len(bucket_samples) / 10.0, 1.0)
    if len(bucket_samples) < 5:
        return advies
    cops = [s.cop for s in bucket_samples]
    lwts = [s.lwt for s in bucket_samples if s.lwt is not None]
    avg_cop = _avg(cops)
    avg_lwt = _avg(lwts)
    if avg_cop is None or avg_lwt is None:
        return advies
    advies.optimale_lwt = round(avg_lwt, 1)
    # Heuristiek: bij gelijke buitentemp verwacht je hogere COP bij lagere LWT
    # Als huidige LWT > optimale_lwt + 1 -> verlaag, vice versa
    if recent.lwt is None:
        return advies
    advies.setpoint_lwt = setpoint_lwt
    if setpoint_lwt is None:
        # Legacy fallback (tests + no-setpoint installations)
        diff = recent.lwt - avg_lwt
        if indoor_avg is not None:
            projected_indoor = indoor_avg - diff * 0.3
            if projected_indoor < comfort_min:
                advies.comfort_impact = round(-2.0 * K_EMIT_DEFAULT, 2)
                advies.state = 'keep'
                advies.step_c = 0
                advies.reason = 'comfort_floor_reached'
                return advies
        if diff > 1.5:
            advies.state = 'lower_lwt'
            advies.step_c = 2
            advies.delta_c = -2.0
            advies.besparing_cop_pct = min(abs(diff) * 2.0, 15.0)
            advies.comfort_impact = round(-2.0 * K_EMIT_DEFAULT, 2)
        elif diff < -1.5:
            advies.state = 'raise_lwt'
            advies.step_c = 2
            advies.delta_c = 2.0
            advies.besparing_cop_pct = 0.0
            advies.comfort_impact = round(2.0 * K_EMIT_DEFAULT, 2)
        else:
            advies.state = 'keep'
            advies.step_c = 0
            advies.delta_c = 0.0
        return advies
    # B13: dynamic LWT step vs setpoint + comfort dual-loop
    advies.tracking_error = round(setpoint_lwt - recent.lwt, 2)
    if rt_setpoint is not None and indoor_avg is not None:
        advies.err_indoor = round(rt_setpoint - indoor_avg, 2)
    if indoor_avg is None:
        advies.state = 'keep'
        advies.step_c = 0
        advies.delta_c = 0.0
        advies.reason = 'no_indoor_sensor'
        return advies
    diff_cop = setpoint_lwt - avg_lwt
    advies.urgency = round(min(abs(diff_cop) / LWT_STEP_MAX, 1.0), 3)
    if diff_cop > 0:
        comfort_cap = max(0.0, (indoor_avg - comfort_min) / K_EMIT_DEFAULT)
    else:
        comfort_cap = max(0.0, (comfort_max - indoor_avg) / K_EMIT_DEFAULT)
    advies.comfort_cap = round(comfort_cap, 2)
    target = min(abs(diff_cop), comfort_cap, LWT_STEP_MAX)
    target *= advies.betrouwbaarheid
    _tracking_behind = (
        advies.tracking_error is not None
        and abs(advies.tracking_error) > LWT_TRACKING_TOLERANCE
    )
    if _tracking_behind:
        target *= 0.5
    if target < LWT_STEP_MIN:
        advies.state = 'keep'
        advies.step_c = 0
        advies.delta_c = 0.0
        if _tracking_behind:
            advies.reason = 'unit_tracking_behind'
        elif abs(diff_cop) < COMFORT_TOLERANCE:
            advies.reason = 'within_deadband'
        elif comfort_cap < LWT_STEP_MIN:
            advies.reason = ('comfort_floor_reached' if diff_cop > 0
                             else 'comfort_ceiling_reached')
        else:
            advies.reason = 'low_confidence'
        return advies
    step_c = min(int(target + 0.5), 3)
    advies.step_c = step_c
    advies.delta_c = float(-step_c if diff_cop > 0 else step_c)
    advies.doel_setpoint = round(setpoint_lwt + advies.delta_c, 1)
    advies.state = 'lower_lwt' if diff_cop > 0 else 'raise_lwt'
    advies.reason = ''
    if advies.state == 'lower_lwt':
        advies.besparing_cop_pct = min(abs(diff_cop) * 2.0, 15.0)
    else:
        advies.besparing_cop_pct = 0.0
    advies.comfort_impact = round(advies.delta_c * K_EMIT_DEFAULT, 2)
    return advies


def _bucket_sort_key(k: str) -> int:
    if k == 'unknown':
        return 9999
    if k == '20+':
        return 20
    if k == '-10-':
        return -10
    m = re.match(r'(-?\d+)', k)
    return int(m.group(1)) if m else 0


def bucket_summary(
    samples: list[CopSample],
) -> dict[str, dict[str, Any]]:
    grouped = _group_by_bucket(samples)
    items: list[tuple[int, str, dict[str, Any]]] = []
    for k, group in grouped.items():
        cops = [s.cop for s in group]
        lwts = [s.lwt for s in group if s.lwt is not None]
        items.append((
            _bucket_sort_key(k), k, {
                'cop': round(sum(cops) / len(cops), 2),
                'n': len(group),
                'lwt': round(sum(lwts) / len(lwts), 1) if lwts else None,
            },
        ))
    items.sort(key=lambda t: t[0])
    return {k: v for _, k, v in items}
