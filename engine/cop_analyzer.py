"""Batch 14a: COP / stooklijn analysis from global_cop attributes."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


_NUM_RE = re.compile(r'-?\d+(?:\.\d+)?')


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
    return '%d-%d' % (lo, lo + 2)


def _group_by_bucket(samples: list[CopSample]) -> dict[str, list[CopSample]]:
    out: dict[str, list[CopSample]] = {}
    for s in samples:
        if not s.valid:
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
) -> StooklijnAdvies:
    advies = StooklijnAdvies()
    grouped = _group_by_bucket(samples)
    if not grouped:
        return advies
    # huidige bucket = de bucket met meeste recente sample
    recent = samples[-1]
    if not recent.valid:
        for s in reversed(samples):
            if s.valid:
                recent = s
                break
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
    diff = recent.lwt - avg_lwt
    # Comfort-guard
    projected_indoor = None
    if indoor_avg is not None:
        projected_indoor = indoor_avg - diff * 0.3
        if projected_indoor < comfort_min:
            advies.comfort_impact = projected_indoor - indoor_avg
            advies.state = 'behoud'
            return advies
    if diff > 1.5:
        advies.state = 'verlaag_lwt_2c'
    elif diff < -1.5:
        advies.state = 'verhoog_lwt_2c'
    else:
        advies.state = 'behoud'
    # Besparing schatting: ~2% COP-winst per 1C LWT-daling (koud water)
    if advies.state == 'verlaag_lwt_2c':
        advies.besparing_cop_pct = min(abs(diff) * 2.0, 15.0)
    if indoor_avg is not None:
        advies.comfort_impact = round(-abs(diff) * 0.3, 2)
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

