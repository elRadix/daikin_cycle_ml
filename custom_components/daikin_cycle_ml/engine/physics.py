"""engine/physics.py - Carnot-derived physical COP ceilings (R452).

Sanity gate for COP values. Shipped as standalone primitive in v1.12.9
as part of #132 companion testing. Wired into thermal cascade in v1.19.9
(#123) with a 3-tier classifier per RFI #127 Q1 answer.
"""
from __future__ import annotations

from typing import Any, Literal

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

# #369: a running heat pump cannot deliver less heat than the electricity it
# draws. Heating/DHW samples below this floor are start-up / ramp transients
# (#369 prod data: 0.35 .. 0.99 at compressor start). Kept separate from the
# Carnot classifier so its contract (None/no-lift -> not_applicable,
# monotonic in cop) is unchanged; the caller flags, never rejects.
COP_FLOOR = 1.0

CopClass = Literal["accept", "flag", "reject", "not_applicable"]


def below_cop_floor(mode: str, cop: float | None) -> bool:
    """True for a heating/DHW COP sample below COP_FLOOR (transient)."""
    return mode in ("heating", "dhw") and cop is not None and cop < COP_FLOOR


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

    Float-precision note (R640): for extremely close lwt and outdoor
    values (< ~5e-14 apart), the +273.15 offset in the th/tc calculation
    can make th == tc due to IEEE 754 rounding, returning not_applicable
    even when lwt > outdoor. This is conservative (safe) behavior.
    Real sensor data has 0.1 C resolution and never hits this case;
    the dT >= 1.5K gate upstream already prevents such samples from
    reaching this function. Documented here for future maintainers.
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


# #175: datasheet reference at the live operating point. The Carnot ratio
# between A7/W35 and the live point assumes a constant Carnot efficiency,
# which a real heat pump does not have: a unit exactly on its datasheet read
# -17 % at A-7/W35 and -26 % at A-2/W45 (LT), +12..+20 % at W65 (HT). The
# reference is now taken from the nearest datasheet points; the Carnot ratio
# only bridges the remaining distance to each of them.
REF_POINTS_USED = 3


def carnot_lift_factor(t_out: float, lwt: float) -> float | None:
    """Ideal heating COP with the same condensing / evaporating offsets as #388."""
    t_cond = lwt + 5.0 + 273.15
    lift = t_cond - (t_out - 8.0 + 273.15)
    return t_cond / lift if lift > 0 else None


def datasheet_cop_at(
    points: list[dict[str, Any]], t_out: float, lwt: float,
) -> dict[str, Any] | None:
    """Datasheet COP expected at (t_out, lwt), or None without a usable point.

    Each datasheet point is carried to the live point with the Carnot ratio;
    the up to REF_POINTS_USED nearest points (distance in K over outdoor and
    water temperature) are averaged with inverse-square-distance weights. On
    a datasheet point the result is that point's COP; a model with only
    A7/W35 gets exactly the previous Carnot normalisation.
    """
    live = carnot_lift_factor(t_out, lwt)
    if live is None:
        return None
    cands: list[tuple[float, str, float]] = []
    for p in points or []:
        try:
            cop, po, pw = float(p["cop"]), float(p["t_out"]), float(p["t_lwc"])
        except (KeyError, TypeError, ValueError):
            continue
        ref = carnot_lift_factor(po, pw)
        if cop <= 0 or ref is None:
            continue
        dist = ((t_out - po) ** 2 + (lwt - pw) ** 2) ** 0.5
        cands.append((dist, str(p.get("label") or f"A{po:g}/W{pw:g}"), cop * live / ref))
    if not cands:
        return None
    cands.sort(key=lambda c: c[0])
    near = cands[:REF_POINTS_USED]
    if near[0][0] < 0.05:
        cop_ref = near[0][2]
    else:
        weights = [1.0 / (d * d) for d, _, _ in near]
        cop_ref = sum(w * c[2] for w, c in zip(weights, near)) / sum(weights)
    return {
        "cop": cop_ref,
        "point": near[0][1],
        "distance_k": round(near[0][0], 1),
        "points_used": len(near),
    }
