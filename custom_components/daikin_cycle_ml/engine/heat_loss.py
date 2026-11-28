"""#495 PR 4: the house's heat loss (UA) from its day rows.

Each valid day gives one point: the mean space-heat power (signed flow x dT
over the day) against the mean indoor - outdoor difference and the sun.
A weighted least-squares fit of

    P [W] = UA * (Tin - Tout) - G - S * sun

gives the heat-loss coefficient UA (W/K), the internal gains G (W) and the
solar gain S (W at the sun's full height all day). Recent days weigh more
(60-day half-life), so the value follows insulation work. The sun term is
only fitted when the sun varies enough between the days.

A day is valid when the space heat was measured for most of it, the room
held steady (else the floor stored or released heat), defrost took little
of it and the house actually needed heat. The result is published once the
gate passes: enough days, enough outdoor spread and a fit that explains the
data. Pure module: no Home Assistant imports.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

MIN_HEAT_COVERAGE = 0.9      # share of the day with a space-heat measurement
MAX_ROOM_DRIFT_K = 0.5
MAX_DEFROST_SHARE = 0.10
MIN_DT_K = 3.0               # indoor - outdoor: below it gains dominate
MIN_DAYS = 14
MIN_SPREAD_K = 6.0
MIN_R2 = 0.4
HALF_LIFE_D = 60.0
MIN_SUN_SPREAD = 0.02        # spread of the daily sun fraction before S is fitted
CLASS_MAX_REL_SIGMA = 0.15
DEFAULT_DESIGN_C = -7.0
DEFAULT_REF_INDOOR_C = 20.0

# W/m² at the design temperature -> class (#368 profiles)
CLASSES = ((15.0, "passive"), (30.0, "very_good"), (50.0, "good"), (80.0, "moderate"))


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def day_point(day: Mapping[str, Any]) -> tuple[dict[str, float] | None, str | None]:
    """One regression point from a day row, or (None, reason)."""
    t_in, t_out = _num(day.get("indoor_mean")), _num(day.get("outdoor_mean"))
    heat, heat_s = _num(day.get("heat_sh_signed_kwh")), _num(day.get("heat_sh_s")) or 0.0
    day_s = _num(day.get("day_len_s")) or 86400.0
    if t_in is None or t_out is None:
        return None, "no_temperature"
    if heat is None or heat_s < MIN_HEAT_COVERAGE * day_s:
        return None, "low_coverage"
    drift = _num(day.get("indoor_drift"))
    if drift is not None and abs(drift) > MAX_ROOM_DRIFT_K:
        return None, "room_drift"
    if (_num(day.get("defrost_min")) or 0.0) * 60.0 > MAX_DEFROST_SHARE * day_s:
        return None, "defrost"
    if t_in - t_out < MIN_DT_K or heat <= 0:
        return None, "no_heating_need"
    return {
        "p_w": heat * 1000.0 * 3600.0 / day_s,
        "dt_k": t_in - t_out,
        "sun": (_num(day.get("sun_h")) or 0.0) * 3600.0 / day_s,
        "t_in": t_in, "t_out": t_out,
    }, None


def _solve(a: list[list[float]], b: list[float]) -> list[float] | None:
    """Gauss-Jordan for a small square system; None when singular."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[piv][c]) < 1e-12:
            return None
        m[c], m[piv] = m[piv], m[c]
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                m[r] = [x - f * y for x, y in zip(m[r], m[c], strict=True)]
    return [m[i][n] / m[i][i] for i in range(n)]


def _inverse_diag(a: list[list[float]]) -> list[float] | None:
    n = len(a)
    out = []
    for i in range(n):
        e = [1.0 if j == i else 0.0 for j in range(n)]
        col = _solve(a, e)
        if col is None:  # pragma: no cover - the fit itself was solvable
            return None
        out.append(col[i])
    return out


def fit(days: Iterable[tuple[int, Mapping[str, Any]]]) -> dict[str, Any]:
    """``days``: (age in days, day row). Returns the fit and the gate."""
    pts: list[tuple[float, dict[str, float]]] = []
    rejected: dict[str, int] = {}
    reconstructed = 0
    for age, row in days:
        p, why = day_point(row)
        if p is None:
            rejected[why or "?"] = rejected.get(why or "?", 0) + 1
            continue
        reconstructed += 1 if row.get("building_reconstructed") else 0
        pts.append((0.5 ** (max(0, age) / HALF_LIFE_D), p))
    out: dict[str, Any] = {"valid_days": len(pts), "rejected": rejected,
                           "reconstructed_days": reconstructed, "published": False}
    if len(pts) < 3:
        out["reason"] = "too_few_days"
        return out
    suns = [p["sun"] for _, p in pts]
    use_sun = max(suns) - min(suns) >= MIN_SUN_SPREAD
    rows = [[p["dt_k"], -1.0] + ([-p["sun"]] if use_sun else []) for _, p in pts]
    ys = [p["p_w"] for _, p in pts]
    raw_w = [w for w, _ in pts]
    ws = [w * len(raw_w) / sum(raw_w) for w in raw_w]  # mean weight 1
    k = len(rows[0])
    xtx = [[sum(w * r[i] * r[j] for w, r in zip(ws, rows, strict=True)) for j in range(k)] for i in range(k)]
    xty = [sum(w * r[i] * y for w, r, y in zip(ws, rows, ys, strict=True)) for i in range(k)]
    beta = _solve(xtx, xty)
    if beta is None:
        out["reason"] = "no_spread"
        return out
    pred = [sum(b * x for b, x in zip(beta, r, strict=True)) for r in rows]
    wsum = sum(ws)
    ybar = sum(w * y for w, y in zip(ws, ys, strict=True)) / wsum
    ss_res = sum(w * (y - f) ** 2 for w, y, f in zip(ws, ys, pred, strict=True))
    ss_tot = sum(w * (y - ybar) ** 2 for w, y in zip(ws, ys, strict=True))
    diag = _inverse_diag(xtx) or [0.0] * k
    s2 = ss_res / max(1, len(ys) - k)
    ua, gains = beta[0], beta[1]
    t_outs = [p["t_out"] for _, p in pts]
    t_in_mean = sum(w * p["t_in"] for w, (_, p) in zip(ws, pts, strict=True)) / wsum
    out.update({
        "ua_w_k": round(ua, 1),
        "sigma_w_k": round(math.sqrt(max(0.0, s2 * diag[0])), 1),
        "gains_w": round(gains, 0),
        "solar_w": round(beta[2], 0) if use_sun else None,
        "r2": round(1.0 - ss_res / ss_tot, 3) if ss_tot > 0 else None,
        "t_out_range": [round(min(t_outs), 1), round(max(t_outs), 1)],
        "t_in_mean": round(t_in_mean, 2),
        "balance_point_c": round(t_in_mean - gains / ua, 1) if ua > 0 else None,
        "method": "flow_dt",
    })
    spread = max(t_outs) - min(t_outs)
    r2 = out["r2"] or 0.0
    if len(pts) < MIN_DAYS:
        out["reason"] = "too_few_days"
    elif spread < MIN_SPREAD_K:
        out["reason"] = "small_outdoor_spread"
    elif r2 < MIN_R2 or ua <= 0:
        out["reason"] = "poor_fit"
    else:
        out["published"] = True
        out["reason"] = None
    return out


def peak_load(res: Mapping[str, Any], *, design_c: float = DEFAULT_DESIGN_C,
              ref_indoor_c: float = DEFAULT_REF_INDOOR_C) -> dict[str, Any] | None:
    """Heat needed at the design temperature, at the reference and the real indoor."""
    ua = _num(res.get("ua_w_k"))
    if not res.get("published") or ua is None:
        return None
    t_in = _num(res.get("t_in_mean")) or ref_indoor_c
    return {
        "kw": round(ua * (ref_indoor_c - design_c) / 1000.0, 2),
        "at_comfort_kw": round(ua * (t_in - design_c) / 1000.0, 2),
        "design_temp_c": design_c, "ref_indoor_c": ref_indoor_c,
    }


def specific_load(res: Mapping[str, Any], peak: Mapping[str, Any] | None,
                  floor_area_m2: float | None) -> dict[str, Any] | None:
    """W/m² at the design temperature and the class (when confident)."""
    area = _num(floor_area_m2)
    if not peak or not area or area <= 0:
        return None
    wm2 = float(peak["kw"]) * 1000.0 / area
    ua, sigma = _num(res.get("ua_w_k")) or 0.0, _num(res.get("sigma_w_k"))
    confident = ua > 0 and sigma is not None and sigma / ua <= CLASS_MAX_REL_SIGMA
    cls = next((name for lim, name in CLASSES if wm2 <= lim), "poor") if confident else None
    return {"w_m2": round(wm2, 1), "class": cls, "floor_area_m2": area}
