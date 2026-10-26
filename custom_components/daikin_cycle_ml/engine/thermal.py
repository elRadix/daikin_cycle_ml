"""engine/thermal.py - thermal cascade helpers (B0).

Extracted from sensor.py so coordinator can reuse the FEAT-2 cascade
without importing the sensor platform (platform-layer smell).
"""
from __future__ import annotations

from typing import (
    Any,
)

from ..const import (
    ATTR_FLOW_SENSOR,
    ATTR_INLET_WATER_R4T,
    ATTR_INV_FREQUENCY_RPS,
    ATTR_LEAVING_WATER_AFTER_BUH,
    RPS_KW_FACTOR,
    WATER_DENSITY_KG_L,
    WATER_SPECIFIC_HEAT_KJ_KG_K,
)

def safe_float(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def dt_from_attrs(attrs: dict[str, Any]) -> float | None:
    a = safe_float(attrs.get(ATTR_LEAVING_WATER_AFTER_BUH))
    b = safe_float(attrs.get(ATTR_INLET_WATER_R4T))
    if a is None or b is None:
        return None
    return round(abs(a - b), 2)


def rps_from_attrs(attrs: dict[str, Any]) -> float | None:
    return safe_float(attrs.get(ATTR_INV_FREQUENCY_RPS))


def flow_from_attrs(attrs: dict[str, Any]) -> float | None:
    return safe_float(attrs.get(ATTR_FLOW_SENSOR))


def _flow_dt_kw(flow_lmin: float, dt_k: float) -> float:
    """Q [kW] = flow[L/min] * rho[kg/L] * cp[kJ/kg/K] * dT[K] / 60."""
    return round(
        flow_lmin * WATER_DENSITY_KG_L
        * WATER_SPECIFIC_HEAT_KJ_KG_K * dt_k / 60.0,
        3,
    )


def compute_thermal_power_live(
    *,
    power_w: float | None,
    cop: float | None,
    flow_lmin: float | None,
    dt_k: float | None,
    rps: float | None,
    mode: str = "heating",
) -> tuple[float | None, str]:
    """FEAT-2 cascade: power*COP -> flow*dT -> rps_heuristic -> idle.

    R486: DHW prefers flow_dt (R4T is physical cold side; user-configured
    COP is heating-biased and overestimates DHW thermal). All other modes
    keep the original order (power_cop first).

    Returns (thermal_kw, calculation_source).
    """
    if (mode == "dhw" and flow_lmin is not None and dt_k is not None
            and flow_lmin > 0 and dt_k > 0):
        return _flow_dt_kw(flow_lmin, dt_k), "flow_dt"
    if power_w is not None and cop is not None and power_w > 0 and cop > 0:
        return round(power_w * cop / 1000.0, 3), "power_cop"
    if flow_lmin is not None and dt_k is not None and flow_lmin > 0 and dt_k > 0:
        return _flow_dt_kw(flow_lmin, dt_k), "flow_dt"
    if rps is not None and rps > 0:
        return round(rps * RPS_KW_FACTOR, 3), "rps_heuristic"
    return None, "idle"
