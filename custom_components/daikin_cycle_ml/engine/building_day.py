"""#495 PR 1: the building's day data, accumulated tick by tick.

What the heat-loss engine (#495 PR 4) and the energy balance (#368 / #438)
need per local day, next to the #508 day totals:

- room temperature, time-weighted, with its first and last value (drift)
  and its source (``sensor``: the configured room sensor, ``controller``:
  the indoor unit's own reading);
- space heat as **signed** flow x (leaving - return): a defrost pulls heat
  out of the loop and counts negative; hot water, cooling and boiler time
  are left out. Seconds with a measurement give the coverage;
- the sun: the integral of max(0, sin(elevation)) over the day, in hours
  (one hour of sun at the zenith = 1.0), from Home Assistant's ``sun``.

The accumulator is a plain dict: it is persisted with ``runtime_acc.<day>``
and restored after a restart. Pure module: no Home Assistant imports.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from ..const import (
    ATTR_3WAY_VALVE,
    ATTR_DEFROST_OPERATION,
    ATTR_INLET_WATER_R4T,
    ATTR_LEAVING_WATER_AFTER_BUH,
    ATTR_LEAVING_WATER_BEFORE_BUH,
    tolerant_on,
)
from .cycle_detector import classify_mode
from .thermal import _flow_dt_kw, flow_from_attrs

INDOOR_RANGE = (0.0, 40.0)
MAX_WATER_DT_K = 20.0     # a larger leaving - return difference is a bad reading
MAX_FLOW_LMIN = 150.0

_NUMERIC = ("indoor_sum", "indoor_s", "heat_sh_kwh", "heat_sh_s", "sun_h", "sun_s")


def new_acc() -> dict[str, Any]:
    acc: dict[str, Any] = dict.fromkeys(_NUMERIC, 0.0)
    acc.update(indoor_first=None, indoor_last=None, indoor_src=None)
    return acc


def restore(payload: Mapping[str, Any]) -> dict[str, Any]:
    """The accumulator from a persisted ``runtime_acc`` payload (missing keys = 0)."""
    acc = new_acc()
    raw = payload.get("building")
    src: Mapping[str, Any] = raw if isinstance(raw, Mapping) else {}
    for k in _NUMERIC:
        acc[k] = _num(src.get(k)) or 0.0
    for k in ("indoor_first", "indoor_last"):
        acc[k] = _num(src.get(k))
    acc["indoor_src"] = src.get("indoor_src") if src.get("indoor_src") in ("sensor", "controller") else None
    return acc


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def space_heat_kw(view: Mapping[str, Any]) -> float | None:
    """Signed space-heat power (kW) now, or None when it is not space heating
    or not measurable. Negative during a defrost."""
    if tolerant_on(view.get(ATTR_3WAY_VALVE)):
        return None  # the water goes to the tank
    defrost = tolerant_on(view.get(ATTR_DEFROST_OPERATION))
    if not defrost and classify_mode(view) != "heating":
        return None
    flow = flow_from_attrs(dict(view))
    lwt = _num(view.get(ATTR_LEAVING_WATER_AFTER_BUH))
    if lwt is None:
        lwt = _num(view.get(ATTR_LEAVING_WATER_BEFORE_BUH))
    rwt = _num(view.get(ATTR_INLET_WATER_R4T))
    if flow is None or lwt is None or rwt is None or not 0.0 < flow <= MAX_FLOW_LMIN:
        return None
    dt = lwt - rwt
    if abs(dt) > MAX_WATER_DT_K:
        return None
    return _flow_dt_kw(flow, dt)  # the integration's own flow x dT formula, signed


def tick(acc: dict[str, Any], view: Mapping[str, Any], *, dt_s: float,
         indoor: float | None, indoor_src: str | None,
         sun_elevation: float | None, boiler: bool = False) -> None:
    """Add one tick of ``dt_s`` seconds."""
    if dt_s <= 0:
        return
    t_in = _num(indoor)
    if t_in is not None and INDOOR_RANGE[0] <= t_in <= INDOOR_RANGE[1]:
        acc["indoor_sum"] += t_in * dt_s
        acc["indoor_s"] += dt_s
        if acc["indoor_first"] is None:
            acc["indoor_first"] = t_in
        acc["indoor_last"] = t_in
        if acc["indoor_src"] != "sensor":  # a sensor seen once wins for the day
            acc["indoor_src"] = indoor_src
    if not boiler:
        p = space_heat_kw(view)
        if p is not None:
            acc["heat_sh_kwh"] += p * dt_s / 3600.0
            acc["heat_sh_s"] += dt_s
    elev = _num(sun_elevation)
    if elev is not None and elev > 0:
        acc["sun_h"] += math.sin(math.radians(min(elev, 90.0))) * dt_s / 3600.0
        acc["sun_s"] += dt_s


def day_fields(payload: Mapping[str, Any]) -> dict[str, Any]:
    """The day-row fields from a persisted ``runtime_acc`` payload."""
    acc = restore(payload)
    s = acc["indoor_s"]
    first, last = acc["indoor_first"], acc["indoor_last"]
    return {
        "indoor_mean": round(acc["indoor_sum"] / s, 2) if s else None,
        "indoor_source": acc["indoor_src"] if s else None,
        "indoor_s": int(s),
        "indoor_drift": round(last - first, 2) if s and first is not None and last is not None else None,
        "heat_sh_signed_kwh": round(acc["heat_sh_kwh"], 3) if acc["heat_sh_s"] else None,
        "heat_sh_s": int(acc["heat_sh_s"]),
        "sun_h": round(acc["sun_h"], 3),
        "sun_s": int(acc["sun_s"]),
    }
