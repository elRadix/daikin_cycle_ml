"""Maximum heat learned from this installation's own samples (#473).

The datasheet often lacks the maximum heat at cold conditions (Hydrosplit
EPRA lists part-load rating points only). The heat pump shows its own
maximum whenever it runs at (near) full compressor speed: per band of
outdoor and water temperature, the 95th percentile of the heat output of
those samples is a measured maximum.

Rules (never guess):
- bands of 5 K: outdoor centred on ..., -7, -2, 3, 8, ...; water on
  30, 35, 40, ...;
- heating samples only, at rps >= 90 % of the compressor's maximum speed
  (manual, datasheet or learned rps_max);
- a band gets a value only with >= 30 such samples over >= 3 days.

Learned values rank below the datasheet and the user's values
(model_profile.apply_profile). In mild weather the unit rarely runs at
full speed, so those bands mostly stay empty. Precision follows the flow
sensor and R1T / R4T.

Pure module: no Home Assistant imports.
"""
from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterable
from typing import Any

BAND_K = 5.0
OUT_ANCHOR = -7.0      # outdoor band centres: -7 + 5 k
WATER_ANCHOR = 30.0    # water band centres: 30 + 5 k
FULL_SPEED = 0.90      # share of rps_max that counts as full speed
MIN_SAMPLES = 30
MIN_DAYS = 3
PCT = 0.95
LEARN_DAYS = 365


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def band_of(outdoor: float, water: float) -> tuple[float, float]:
    """Centre of the 5 K band of an outdoor and a water temperature."""
    o = OUT_ANCHOR + BAND_K * round((outdoor - OUT_ANCHOR) / BAND_K)
    w = WATER_ANCHOR + BAND_K * round((water - WATER_ANCHOR) / BAND_K)
    return (round(o, 1) + 0.0, round(w, 1) + 0.0)


def _pct(values: list[float], q: float) -> float:
    v = sorted(values)
    pos = (len(v) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def learn_hmax(
    rows: Iterable[tuple[Any, ...]],
    rps_max: float | None,
    *,
    include_reconstructed: bool = True,
    localtime: Callable[[float], time.struct_time] = time.localtime,
) -> dict[str, Any]:
    """Learned maximum heat per band.

    rows: (ts, outdoor, water, thermal_kw, rps, is_reconstructed).
    Returns {"bands": [{t_out, t_lwc, hmax, n, days, reconstructed}],
    "full_speed_samples", "rps_threshold", "skipped_bands"}; empty bands
    are counted, never filled.
    """
    top = _num(rps_max)
    out: dict[str, Any] = {"bands": [], "full_speed_samples": 0, "rps_threshold": None, "skipped_bands": 0}
    if top is None or top <= 0:
        return out
    thr = round(top * FULL_SPEED, 1)
    out["rps_threshold"] = thr
    groups: dict[tuple[float, float], dict[str, Any]] = {}
    for row in rows:
        ts, o, w, kw, rps, rec = (list(row) + [None] * 6)[:6]
        o, w, kw, rps, ts_f = _num(o), _num(w), _num(kw), _num(rps), _num(ts)
        if None in (o, w, kw, rps, ts_f) or kw <= 0 or rps < thr:  # type: ignore[operator]
            continue
        if rec and not include_reconstructed:
            continue
        g = groups.setdefault(band_of(o, w), {"kw": [], "days": set(), "rec": 0})  # type: ignore[arg-type]
        g["kw"].append(kw)
        g["days"].add(time.strftime("%Y-%m-%d", localtime(ts_f)))  # type: ignore[arg-type]
        g["rec"] += 1 if rec else 0
        out["full_speed_samples"] += 1
    for (o, w), g in sorted(groups.items()):
        if len(g["kw"]) < MIN_SAMPLES or len(g["days"]) < MIN_DAYS:
            out["skipped_bands"] += 1
            continue
        out["bands"].append({"t_out": o, "t_lwc": w, "hmax": round(_pct(g["kw"], PCT), 2),
                             "n": len(g["kw"]), "days": len(g["days"]), "reconstructed": g["rec"]})
    return out
