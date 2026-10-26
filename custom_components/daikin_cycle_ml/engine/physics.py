"""engine/physics.py - Carnot-derived physical COP ceilings (R452).

Sanity gate for COP values. Shipped as standalone primitive in v1.12.9
as part of #132 companion testing; wired into thermal cascade in #123
(v1.13.0, blocked by #127 derating-factor RFI).
"""
from __future__ import annotations

CARNOT_EFFICIENCY_FACTOR = 0.55  # R445e -- empirical derating


def get_physical_cop_ceiling(
    mode: str, lwt: float, outdoor: float
) -> float | None:
    """Return Carnot COP ceiling for given LWT and outdoor temp.

    COP_max = (Th / (Th - Tc)) * efficiency_factor
    where Th = lwt + 273.15, Tc = outdoor + 273.15.

    Returns None if lwt <= outdoor (no lift) or mode is not heat-pump
    (heating/dhw only).
    """
    if mode not in ("heating", "dhw"):
        return None
    th = lwt + 273.15
    tc = outdoor + 273.15
    if th <= tc:
        return None
    return round(th / (th - tc) * CARNOT_EFFICIENCY_FACTOR, 2)
