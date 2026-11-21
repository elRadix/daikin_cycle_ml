"""Weather-aware weekly defrost limit (#463).

A fixed weekly count (30) is crossed most winter weeks in a humid
climate and says nothing in summer. The limit here follows the weather
and the running time of the last 7 days: for every day, the compressor
running hours (heating and hot water; the outdoor coil frosts in any
heating mode) times the highest plausible defrost rate for that day's
outdoor temperature, plus a margin.

Rates: defrosts per compressor running hour, conservative upper bounds
for humid worst-case-normal weather on a Daikin Altherma 3 (R / H / HT /
M) in NW Europe. Reviewed by an HVAC engineer; Daikin does not publish
its defrost interval logic, so these are bounds, not exact figures.

The outdoor temperature per hour comes from cop_hourly (mean while the
compressor ran, weighted by samples), so a mild day with a cold night
gets the rate of its cold hours. The outdoor sensor of the unit reads
1-3 degrees below the air while the fan runs: that only moves hours to a
colder, more lenient band.

Pure module: no Home Assistant imports.
"""
from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterable, Mapping
from typing import Any

# (upper bound exclusive in degC, max defrosts per running hour)
RATE_BANDS: tuple[tuple[float, float], ...] = (
    (-7.0, 1.0),    # < -7: drier air, slower frost
    (-2.0, 1.5),    # -7 .. -2
    (3.0, 2.0),     # -2 .. 3: peak frost formation
    (7.0, 1.5),     # 3 .. 7
    (10.0, 0.5),    # 7 .. 10
    (math.inf, 0.1),  # >= 10: almost none
)
RATE_UNKNOWN = 2.0      # a day without outdoor data: the most lenient band
MARGIN = 1.5
FLOOR = 10              # never fire below 10 defrosts a week
WARM_C = 10.0           # defrosts on days this warm point to a problem
WARM_DAY_EVENTS = 2     # more than 2 defrosts on such a day ...
WARM_DAYS = 2           # ... on 2 days or more
NO_FROST_MODES = frozenset({"cooling", "cool", "auto cool"})


def rate_for(outdoor_c: float) -> float:
    """Highest plausible defrosts per running hour at this outdoor temperature."""
    for upper, rate in RATE_BANDS:
        if outdoor_c < upper:
            return rate
    return RATE_BANDS[-1][1]  # pragma: no cover - inf bound always matches


def _day_of(ts_hour: int, localtime: Callable[[float], time.struct_time]) -> str:
    return time.strftime("%Y-%m-%d", localtime(float(ts_hour) * 3600.0))


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    f = float(value)
    return f if math.isfinite(f) else None


def compute(
    daily_rows: Iterable[Mapping[str, Any]],
    events_by_day: Mapping[str, Mapping[str, Any]],
    hourly_rows: Iterable[Mapping[str, Any]],
    *,
    cutoff_day: str,
    localtime: Callable[[float], time.struct_time] = time.localtime,
) -> dict[str, Any]:
    """Defrost events, running hours and the weather-aware limit of the
    last 7 days, plus the warm-weather pattern.

    daily_rows: daily_summary rows (day, mode, total_duration_s,
    defrost_count). events_by_day: async_runtime_events_by_day()
    (defrost_events per day, rising edges of Defrost Operation).
    hourly_rows: cop_hourly rows (ts_hour, n_samples, outdoor_mean).
    """
    run_s: dict[str, float] = {}
    cycles_with_defrost: dict[str, int] = {}
    for r in daily_rows:
        day = str(r.get("day") or "")
        if not day or day < cutoff_day:
            continue
        cycles_with_defrost[day] = cycles_with_defrost.get(day, 0) + int(_num(r.get("defrost_count")) or 0)
        if str(r.get("mode") or "").lower() in NO_FROST_MODES:
            continue
        run_s[day] = run_s.get(day, 0.0) + max(0.0, _num(r.get("total_duration_s")) or 0.0)

    # Per-day weighted rate and mean outdoor from the hourly rows.
    rate_w: dict[str, float] = {}
    temp_w: dict[str, float] = {}
    weight: dict[str, float] = {}
    for h in hourly_rows:
        ts_hour, temp = _num(h.get("ts_hour")), _num(h.get("outdoor_mean"))
        if ts_hour is None or temp is None:
            continue
        if str(h.get("mode") or "").lower() in NO_FROST_MODES:
            continue
        day = _day_of(int(ts_hour), localtime)
        if day < cutoff_day:
            continue
        w = max(1.0, _num(h.get("n_samples")) or 1.0)
        rate_w[day] = rate_w.get(day, 0.0) + w * rate_for(temp)
        temp_w[day] = temp_w.get(day, 0.0) + w * temp
        weight[day] = weight.get(day, 0.0) + w

    days = sorted(set(run_s) | set(cycles_with_defrost)
                  | {d for d in events_by_day if str(d) >= cutoff_day})
    per_day: list[dict[str, Any]] = []
    expected = 0.0
    events_total = 0
    warm_days = 0
    for day in days:
        ev_raw = (events_by_day.get(day) or {}).get("defrost_events")
        ev_num = _num(ev_raw)
        # Real events when stored; before #400 only cycles with a defrost.
        events = int(ev_num) if ev_num is not None else cycles_with_defrost.get(day, 0)
        hours = run_s.get(day, 0.0) / 3600.0
        if weight.get(day):
            day_rate = rate_w[day] / weight[day]
            outdoor: float | None = round(temp_w[day] / weight[day], 1)
        else:
            day_rate, outdoor = RATE_UNKNOWN, None
        expected += hours * day_rate
        events_total += events
        if outdoor is not None and outdoor >= WARM_C and events > WARM_DAY_EVENTS:
            warm_days += 1
        per_day.append({"day": day, "events": events, "run_h": round(hours, 1),
                        "outdoor": outdoor, "rate": round(day_rate, 2)})

    limit = max(FLOOR, math.ceil(expected * MARGIN))
    return {
        "events_7d": events_total,
        "limit_7d": limit,
        "run_h_7d": round(sum(run_s.values()) / 3600.0, 1),
        "warm_days": warm_days,
        "excessive": events_total > limit or warm_days >= WARM_DAYS,
        "per_day": per_day,
    }
