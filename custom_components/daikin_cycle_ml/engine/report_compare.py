"""Period comparison, trends and verdicts (#508). Pure Python.

A period is compared with the previous period or with the same period a
year earlier. Energy is weather-normalised per degree day, and the COP is
compared over the outdoor bands both periods share, so a colder month does
not read as a worse heat pump. A period with too little data is compared
all the same, but every verdict says ``incomplete`` (#508 decision 5).
"""
from __future__ import annotations

import datetime as dt
import math
from collections.abc import Mapping, Sequence
from typing import Any

from .period_reports import COVERAGE_MIN, period_bounds, period_key

GOOD, WATCH, ACT, INCOMPLETE = "good", "watch", "act", "incomplete"
_RANK = {GOOD: 0, WATCH: 1, ACT: 2}

# Metrics shown in a comparison: key -> True when higher is better,
# False when lower is better, None when it only describes the period.
METRICS: dict[str, bool | None] = {
    "cop": True, "cop_matched": True,
    "el_kwh": None, "th_kwh": None, "el_per_dd": False, "th_per_dd": None,
    "runtime_h": None, "cycles": None, "runs": None, "run_mean_min": True,
    "starts_per_h": False, "quality_mean": True,
    "lwt_mean": None, "return_mean": None, "dt_mean": None, "flow_mean": None,
    "rps_mean": None, "outdoor_mean": None, "dd": None,
    "buh_min": False, "buh_share_pct": False, "defrost_count": None, "defrost_min": None,
    "alerts_total": False, "ml_anomalies": False,
}
MIN_DD = 10.0          # below this a period is too mild to normalise per degree day
MIN_MATCHED_BANDS = 2  # weather-matched COP needs at least two shared outdoor bands


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    return f if math.isfinite(f) else None


def derived(data: Mapping[str, Any], scheme: str) -> dict[str, Any]:
    """The period's values plus the derived ones a comparison needs."""
    out = {k: data.get(k) for k in METRICS if k in data}
    dd = _num((data.get("degree_days") or {}).get(scheme))
    out["dd"] = dd
    el, th = _num(data.get("cop_el_kwh")), _num(data.get("th_kwh"))
    out["el_per_dd"] = round(el / dd, 3) if el is not None and dd and dd >= MIN_DD else None
    out["th_per_dd"] = round(th / dd, 3) if th is not None and dd and dd >= MIN_DD else None
    runtime_h = _num(data.get("runtime_h"))
    cycles = _num(data.get("cycles"))
    out["starts_per_h"] = round(cycles / runtime_h, 2) if cycles is not None and runtime_h else None
    buh = _num(data.get("buh_min"))
    out["buh_share_pct"] = round(100.0 * buh / (runtime_h * 60.0), 1) if buh is not None and runtime_h else None
    out["alerts_total"] = sum(int(v) for v in (data.get("alerts") or {}).values())
    return out


def matched_cop(cur_bands: Mapping[str, Sequence[float]],
                ref_bands: Mapping[str, Sequence[float]]) -> dict[str, Any] | None:
    """COP of both periods over the outdoor bands they share."""
    shared = sorted(set(cur_bands) & set(ref_bands), key=float)
    if len(shared) < MIN_MATCHED_BANDS:
        return None
    c_th = sum(float(cur_bands[b][0]) for b in shared)
    c_el = sum(float(cur_bands[b][1]) for b in shared)
    r_th = sum(float(ref_bands[b][0]) for b in shared)
    r_el = sum(float(ref_bands[b][1]) for b in shared)
    if c_el <= 0 or r_el <= 0:
        return None
    return {"cur": round(c_th / c_el, 2), "ref": round(r_th / r_el, 2), "bands": shared}


def is_partial(data: Mapping[str, Any] | None) -> bool:
    cov = _num((data or {}).get("coverage_days"))
    return cov is None or cov < COVERAGE_MIN


def _delta(cur: Any, ref: Any) -> dict[str, Any]:
    c, r = _num(cur), _num(ref)
    d = round(c - r, 3) if c is not None and r is not None else None
    pct = round(100.0 * (c - r) / abs(r), 1) if c is not None and r else None
    return {"cur": cur, "ref": ref, "delta": d, "delta_pct": pct}


def _grade(value: float | None, good: float, watch: float) -> str | None:
    """Grade a change where higher is better: >= good, >= watch, else act."""
    if value is None:
        return None
    if value >= good:
        return GOOD
    return WATCH if value >= watch else ACT


def verdicts(metrics: Mapping[str, Mapping[str, Any]], partial: bool) -> dict[str, str]:
    """good / watch / act per judged metric, plus ``overall``."""
    def m(key: str, field: str) -> float | None:
        return _num((metrics.get(key) or {}).get(field))

    cop_pct = m("cop_matched", "delta_pct")
    if cop_pct is None:
        cop_pct = m("cop", "delta_pct")
    el_dd = m("el_per_dd", "delta_pct")
    out: dict[str, str | None] = {
        "cop": _grade(cop_pct, -3.0, -10.0),
        "el_per_dd": _grade(-el_dd if el_dd is not None else None, -5.0, -15.0),
        "quality_mean": _grade(m("quality_mean", "delta"), -3.0, -10.0),
        "run_mean_min": _grade(m("run_mean_min", "delta_pct"), -10.0, -30.0),
        "starts_per_h": _grade(-(m("starts_per_h", "delta_pct") or 0.0)
                               if m("starts_per_h", "delta_pct") is not None else None, -20.0, -50.0),
        "buh_share_pct": _grade(-(m("buh_share_pct", "delta") or 0.0)
                                if m("buh_share_pct", "delta") is not None else None, -1.0, -5.0),
    }
    graded = {k: v for k, v in out.items() if v is not None}
    if partial:
        return {**{k: INCOMPLETE for k in graded}, "overall": INCOMPLETE}
    worst = max(graded.values(), key=lambda v: _RANK[v], default=None)
    return {**graded, "overall": worst or INCOMPLETE}


def compare(cur: Mapping[str, Any] | None, ref: Mapping[str, Any] | None, scheme: str) -> dict[str, Any]:
    """Every metric with its change, the weather-matched COP and the verdicts."""
    if not cur or not ref:
        return {"metrics": {}, "verdicts": {}, "partial": True, "available": False}
    a, b = derived(cur, scheme), derived(ref, scheme)
    metrics = {k: _delta(a.get(k), b.get(k)) for k in METRICS if k != "cop_matched"}
    mc = matched_cop(cur.get("cop_bands") or {}, ref.get("cop_bands") or {})
    if mc:
        metrics["cop_matched"] = {**_delta(mc["cur"], mc["ref"]), "bands": mc["bands"]}
    partial = is_partial(cur) or is_partial(ref)
    return {"metrics": metrics, "verdicts": verdicts(metrics, partial),
            "partial": partial, "available": True}


def trend(values: Sequence[float | None]) -> dict[str, Any] | None:
    """Least-squares slope per period over the values that exist (oldest first)."""
    pts = [(i, f) for i, v in enumerate(values) if (f := _num(v)) is not None]
    if len(pts) < 3:
        return None
    n = len(pts)
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    den = sum((x - mx) ** 2 for x, _ in pts)
    slope = sum((x - mx) * (y - my) for x, y in pts) / den
    pct = 100.0 * slope / abs(my) if my else None
    direction = "flat" if pct is None or abs(pct) < 1.0 else ("up" if slope > 0 else "down")
    return {"slope": round(slope, 4), "slope_pct": round(pct, 2) if pct is not None else None,
            "n": n, "direction": direction}


# ---------- which period to compare with ----------

def previous_key(period_type: str, key: str, season_start_month: int = 10) -> str:
    first, _ = period_bounds(period_type, key, season_start_month)
    day = (dt.date.fromisoformat(first) - dt.timedelta(days=1)).isoformat()
    return period_key(period_type, day, season_start_month)


def last_year_key(period_type: str, key: str) -> str:
    if period_type == "week":
        y, w = (int(x) for x in key.split("-W"))
        weeks = dt.date(y - 1, 12, 28).isocalendar()[1]   # 52 or 53
        return f"{y - 1}-W{min(w, weeks):02d}"
    if period_type == "month":
        y, m = (int(x) for x in key.split("-"))
        return f"{y - 1}-{m:02d}"
    if period_type == "year":
        return str(int(key) - 1)
    if period_type == "season":
        y = int(key.split("/")[0]) - 1
        return f"{y}/{(y + 1) % 100:02d}"
    raise ValueError(period_type)


def reference_key(period_type: str, key: str, against: str, season_start_month: int = 10) -> str | None:
    if against == "previous":
        return previous_key(period_type, key, season_start_month)
    if against == "last_year":
        return last_year_key(period_type, key)
    return None
