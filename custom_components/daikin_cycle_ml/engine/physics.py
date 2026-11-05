"""engine/physics.py - Carnot-derived physical COP ceilings (R452).

Sanity gate for COP values. Shipped as standalone primitive in v1.12.9
as part of #132 companion testing. Wired into thermal cascade in v1.19.9
(#123) with a 3-tier classifier per RFI #127 Q1 answer.
"""
from __future__ import annotations

from typing import Literal

# v1.19.9 #123/#127-Q1: Daikin expert confirmed 0.65 as the practical
# derating factor. Was 0.55 (R445e empirical guess) pre-RFI answer.
CARNOT_EFFICIENCY_FACTOR = 0.65

# v1.19.9 #123: accept-margin for sensor noise. Daikin sensors have
# +/-0.3K tolerance. At typical operating points this translates to
# ~5% variation on the ceiling. Samples within ceiling * 1.05 are
# accepted as normal operating data.
ACCEPT_MARGIN = 1.05

# v1.19.9 #123: reject multiplier vs pure Carnot. Anything above 150%
# of the theoretical maximum is a sensor or firmware error under any
# physical interpretation. Rejected at source (not stored).
REJECT_MULTIPLIER = 1.50

CopClass = Literal["accept", "flag", "reject", "not_applicable"]


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

def classify_cop_sample(
    mode: str,
    lwt: float | None,
    outdoor: float | None,
    cop: float | None,
) -> CopClass:
    """v1.19.9 #123: 3-tier classifier for a single COP sample.

    Returns:
      - not_applicable: cooling/unknown mode, missing lwt/outdoor/cop,
        or lwt <= outdoor (no lift, division guard)
      - accept: cop <= ceiling * ACCEPT_MARGIN  (normal operation)
      - flag: ceiling*margin < cop <= Carnot * REJECT_MULTIPLIER
        (suspicious; caller stores with is_transition_artifact=1)
      - reject: cop > Carnot * REJECT_MULTIPLIER
        (physically impossible; caller does not store)

    The flag class is deliberately wide (0.68x to 1.5x Carnot) because
    the sensors have +/-0.3K tolerance and legitimate high-COP events
    (defrost recovery, mild-weather low-lift heating) can reach ~90%
    of Carnot for brief periods.
    """
    if mode not in ("heating", "dhw"):
        return "not_applicable"
    if lwt is None or outdoor is None or cop is None:
        return "not_applicable"
    th = lwt + 273.15
    tc = outdoor + 273.15
    if th <= tc:
        return "not_applicable"
    carnot = th / (th - tc)
    ceiling = carnot * CARNOT_EFFICIENCY_FACTOR
    accept_thr = ceiling * ACCEPT_MARGIN
    reject_thr = carnot * REJECT_MULTIPLIER
    if cop <= accept_thr:
        return "accept"
    if cop > reject_thr:
        return "reject"
    return "flag"
