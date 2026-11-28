"""Period reports (#508): one row per local day and mode, aggregated into
weeks (ISO, Monday-Sunday), months, years and heating seasons. Pure Python.

A day row is built from the sources the integration already keeps
(daily_summary, energy_acc / runtime_acc, cop_hourly, cop_samples, alerts)
while they still exist; the report tables keep the result for good.
Every day carries the checks it failed; a failing day is stored but left
out of the COP and of comparisons (decision 2 of #508).
"""
from __future__ import annotations

import datetime as dt
import math
import statistics
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .physics import CARNOT_EFFICIENCY_FACTOR, carnot_lift_factor

MODES: tuple[str, ...] = ("heating", "dhw", "cooling")
ALL = "all"
PERIOD_TYPES: tuple[str, ...] = ("week", "month", "year", "season")

ACCEPT_MARGIN = 1.05          # same margin as the per-sample physics gate
CROSS_TOLERANCE = 0.15        # heat / power cross-checks
CROSS_MIN_SHARE = 0.7         # samples must cover 70 % of the runtime
COVERAGE_MIN = 0.8            # source data for 80 % of the day
OUTLIER_MAD = 3.0
OUTLIER_MIN_DAYS = 30
BAND_K = 2.0                  # outdoor band for the outlier check
MIN_EL_KWH = 0.05             # below this the COP of a day is noise
CP_WATER = 4.186              # kJ / (kg K)

# Checks that make a day's energy unusable for COP and comparisons.
ENERGY_CHECKS = frozenset({
    "no_energy", "cop_out_of_range", "heat_mismatch", "power_mismatch", "outlier",
})

# Degree-day schemes stored per day (#508 decision 3).
DD_SCHEMES: dict[str, str] = {
    "nl18": "NL: base 18 °C on the daily mean",
    "nl18w": "NL: base 18 °C, weighted (x1.1 Nov-Feb, x0.8 Apr-Sep)",
    "be1515": "BE: equivalent temperature 0.6/0.3/0.1, base 15 °C",
    "be165": "BE: equivalent temperature 0.6/0.3/0.1, base 16.5 °C (Synergrid)",
    "fr18": "FR: DJU base 18 °C on (Tmin + Tmax) / 2",
    "fr17": "FR: base 17 °C on (Tmin + Tmax) / 2 (SDES 2024)",
    "fr15": "FR: base 15 °C on (Tmin + Tmax) / 2 (SDES 2024)",
    "cdd18": "Cooling degree days, base 18 °C on the daily mean",
}
COUNTRY_SCHEME = {"NL": "nl18", "BE": "be1515", "FR": "fr18"}


def default_scheme(country: str | None) -> str:
    return COUNTRY_SCHEME.get((country or "").upper(), "nl18")


def season_start_month(opts: Mapping[str, Any] | None) -> int:
    """Heating-season start month from the options (1-12, else 10)."""
    try:
        month = int((opts or {}).get("season_start_month", 10))
    except (TypeError, ValueError):
        return 10
    return month if 1 <= month <= 12 else 10


# ---------- periods ----------

def _date(day: str) -> dt.date:
    return dt.date.fromisoformat(day)


def period_key(period_type: str, day: str, season_start_month: int = 10) -> str:
    d = _date(day)
    if period_type == "week":
        y, w, _ = d.isocalendar()
        return f"{y}-W{w:02d}"
    if period_type == "month":
        return f"{d.year}-{d.month:02d}"
    if period_type == "year":
        return str(d.year)
    if period_type == "season":
        y = d.year if d.month >= season_start_month else d.year - 1
        return f"{y}/{(y + 1) % 100:02d}"
    raise ValueError(period_type)


def period_bounds(period_type: str, key: str, season_start_month: int = 10) -> tuple[str, str]:
    """First and last day (ISO) of a period."""
    if period_type == "week":
        ys, ws = key.split("-W")
        first = dt.date.fromisocalendar(int(ys), int(ws), 1)
        last = first + dt.timedelta(days=6)
    elif period_type == "month":
        yy, mm = (int(x) for x in key.split("-"))
        first = dt.date(yy, mm, 1)
        nxt = dt.date(yy + (mm == 12), mm % 12 + 1, 1)
        last = nxt - dt.timedelta(days=1)
    elif period_type == "year":
        first, last = dt.date(int(key), 1, 1), dt.date(int(key), 12, 31)
    elif period_type == "season":
        ys0 = int(key.split("/")[0])
        first = dt.date(ys0, season_start_month, 1)
        last = dt.date(ys0 + 1, season_start_month, 1) - dt.timedelta(days=1)
    else:
        raise ValueError(period_type)
    return first.isoformat(), last.isoformat()


def periods_of_day(day: str, season_start_month: int = 10) -> list[tuple[str, str]]:
    return [(t, period_key(t, day, season_start_month)) for t in PERIOD_TYPES]


def day_range(first: str, last: str) -> list[str]:
    a, b = _date(first), _date(last)
    return [(a + dt.timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


# ---------- degree days ----------

def _nl_weight(month: int) -> float:
    if month in (11, 12, 1, 2):
        return 1.1
    if 4 <= month <= 9:
        return 0.8
    return 1.0


def degree_days(day: str, temps: Mapping[str, Mapping[str, Any]]) -> dict[str, float] | None:
    """All schemes for one day. ``temps`` maps day -> {mean, min, max}."""
    t = temps.get(day) or {}
    mean, tmin, tmax = _num(t.get("mean")), _num(t.get("min")), _num(t.get("max"))
    if mean is None:
        return None
    out: dict[str, float] = {}
    out["nl18"] = max(0.0, 18.0 - mean)
    out["nl18w"] = out["nl18"] * _nl_weight(_date(day).month)
    d1 = _num((temps.get((_date(day) - dt.timedelta(days=1)).isoformat()) or {}).get("mean"))
    d2 = _num((temps.get((_date(day) - dt.timedelta(days=2)).isoformat()) or {}).get("mean"))
    teq = 0.6 * mean + 0.3 * (d1 if d1 is not None else mean) + 0.1 * (d2 if d2 is not None else mean)
    out["be1515"] = max(0.0, 15.0 - teq)
    out["be165"] = max(0.0, 16.5 - teq)
    mid = (tmin + tmax) / 2.0 if tmin is not None and tmax is not None else mean
    for key, base in (("fr18", 18.0), ("fr17", 17.0), ("fr15", 15.0)):
        out[key] = max(0.0, base - mid)
    out["cdd18"] = max(0.0, mean - 18.0)
    return {k: round(v, 2) for k, v in out.items()}


# ---------- one day ----------

def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    return f if math.isfinite(f) else None


def _div(a: float | None, b: float | None) -> float | None:
    return a / b if a is not None and b else None


def _r(v: float | None, n: int = 2) -> float | None:
    return round(v, n) if v is not None else None


def build_mode_row(src: Mapping[str, Any], *, sample_interval_s: float) -> dict[str, Any]:
    """Metrics of one mode for one day from its source values."""
    ds = src.get("daily_summary") or {}
    el, th = _num(src.get("el_kwh")) or 0.0, _num(src.get("th_kwh")) or 0.0
    runtime = float(ds.get("total_duration_s") or 0)
    cycles, runs = int(ds.get("cycles") or 0), int(ds.get("runs") or 0)
    hourly = src.get("hourly") or {}
    samples = src.get("samples") or {}
    n_s = int(samples.get("n") or 0)
    row: dict[str, Any] = {
        "el_kwh": _r(el, 3), "th_kwh": _r(th, 3),
        "cop": _r(th / el) if el >= MIN_EL_KWH else None,
        "runtime_s": int(runtime), "cycles": cycles, "runs": runs,
        "run_mean_min": _r(_div(runtime / 60.0, float(runs)), 1),
        "run_max_min": _r(_div(float(ds.get("duration_max") or 0), 60.0), 1),
        "run_min_min": _r(_div(float(ds.get("duration_min") or 0), 60.0), 1),
        "quality_mean": _r(_div(float(ds.get("quality_sum") or 0), float(cycles)), 1),
        "dt_max_mean": _r(_div(float(ds.get("dt_max_sum") or 0), float(cycles)), 2),
        "rps_mean": _r(_div(float(ds.get("rps_sum") or 0), float(cycles)), 1),
        "buh_cycles": int(ds.get("buh_count") or 0),
        "defrost_cycles": int(ds.get("defrost_count") or 0),
        "transient_cycles": int(ds.get("transient_count") or 0),
        "lwt_mean": _r(_num(hourly.get("lwt_mean")), 1),
        "flow_mean": _r(_num(hourly.get("flow_mean")), 1),
        "outdoor_run_mean": _r(_num(hourly.get("outdoor_mean")), 1),
        "return_mean": _r(_num(samples.get("r4t_mean")), 1),
        "dt_mean": _r(_num(samples.get("dt_mean")), 2),
        "samples": n_s,
        "buh_samples": int(samples.get("buh_n") or 0),
        "heat_est_kwh": _r(_num(samples.get("heat_kwh")), 3),
        "power_est_kwh": _r(_num(samples.get("power_kwh")), 3),
        "sample_s": int(n_s * sample_interval_s),
    }
    return row


def check_mode_row(row: Mapping[str, Any], day_len_s: float) -> list[str]:
    """#508 decision 2: the energy and runtime checks of one mode-day."""
    out: list[str] = []
    el, th, runtime = row.get("el_kwh") or 0.0, row.get("th_kwh") or 0.0, row.get("runtime_s") or 0
    if runtime > 600 and el < MIN_EL_KWH:
        out.append("no_energy")
    cop = row.get("cop")
    lwt, t_out = row.get("lwt_mean"), row.get("outdoor_run_mean")
    if cop is not None:
        ceiling = None
        if lwt is not None and t_out is not None:
            ideal = carnot_lift_factor(float(t_out), float(lwt))
            ceiling = ideal * CARNOT_EFFICIENCY_FACTOR * ACCEPT_MARGIN if ideal else None
        if cop < 1.0 or (ceiling is not None and cop > ceiling):
            out.append("cop_out_of_range")
    share = (row.get("sample_s") or 0) / runtime if runtime else 0.0
    if share >= CROSS_MIN_SHARE and th > 0.5:
        for key, ref, flag in (("heat_est_kwh", th, "heat_mismatch"), ("power_est_kwh", el, "power_mismatch")):
            est = row.get(key)
            if est and ref and abs(est / share - ref) / ref > CROSS_TOLERANCE:
                out.append(flag)
    if runtime > day_len_s + 60:
        out.append("runtime_bounds")
    return out


def check_outlier(cop: float | None, t_out: float | None,
                  history: Iterable[tuple[float, float]]) -> bool:
    """COP more than 3 MAD from the median of its outdoor band."""
    if cop is None or t_out is None:
        return False
    band = math.floor(t_out / BAND_K)
    same = [c for c, t in history if math.floor(t / BAND_K) == band]
    if len(same) < OUTLIER_MIN_DAYS:
        return False
    med = statistics.median(same)
    mad = statistics.median(abs(c - med) for c in same) or 0.05
    return abs(cop - med) > OUTLIER_MAD * mad * 1.4826


def build_all_row(day: str, modes: Mapping[str, Mapping[str, Any]], day_src: Mapping[str, Any],
                  temps: Mapping[str, Mapping[str, Any]], day_len_s: float) -> dict[str, Any]:
    """The whole-day row: sums of the modes plus weather, events, coverage."""
    def tot(k: str) -> float:
        return sum(float(m.get(k) or 0) for m in modes.values())
    el, th = tot("el_kwh"), tot("th_kwh")
    valid = [m for m in modes.values() if not set(m.get("checks") or ()) & ENERGY_CHECKS]
    v_el = sum(float(m.get("el_kwh") or 0) for m in valid)
    v_th = sum(float(m.get("th_kwh") or 0) for m in valid)
    runtime = tot("runtime_s")
    t = temps.get(day) or {}
    rt = day_src.get("runtime_acc") or {}
    fresh = _num(rt.get("source_fresh_s"))
    row: dict[str, Any] = {
        "el_kwh": _r(el, 3), "th_kwh": _r(th, 3),
        "cop": _r(v_th / v_el) if v_el >= MIN_EL_KWH else None,
        "cop_el_kwh": _r(v_el, 3), "cop_th_kwh": _r(v_th, 3),
        "runtime_s": int(runtime), "cycles": int(tot("cycles")), "runs": int(tot("runs")),
        "duty_pct": _r(100.0 * runtime / day_len_s, 1) if day_len_s else None,
        "outdoor_mean": _r(_num(t.get("mean")), 1),
        "outdoor_min": _r(_num(t.get("min")), 1),
        "outdoor_max": _r(_num(t.get("max")), 1),
        "outdoor_source": t.get("source"),
        "degree_days": degree_days(day, temps),
        "buh_min": _r((_num(rt.get("buh_total_s")) or 0.0) / 60.0, 1),
        "defrost_count": int(rt.get("defrost_count") or 0),
        "defrost_min": _r((_num(rt.get("defrost_duration_s")) or 0.0) / 60.0, 1),
        "alerts": dict(day_src.get("alerts") or {}),
        "ml_anomalies": int((day_src.get("alerts") or {}).get("ml_anomaly", 0)),
        "coverage": _r(min(1.0, fresh / day_len_s), 3) if fresh is not None and day_len_s else None,
        "day_len_s": int(day_len_s),
    }
    return row


def check_all_row(row: Mapping[str, Any], modes: Mapping[str, Mapping[str, Any]]) -> list[str]:
    out = sorted({c for m in modes.values() for c in (m.get("checks") or ())})
    cov = row.get("coverage")
    if cov is not None and cov < COVERAGE_MIN:
        out.append("low_coverage")
    if row.get("day_len_s") not in (82800, 86400, 90000):
        out.append("clock")
    if (row.get("duty_pct") or 0) > 100.5:
        out.append("runtime_bounds")
    return sorted(set(out))


# ---------- periods from days ----------

def aggregate(days: Sequence[Mapping[str, Any]], *, n_days_in_period: int) -> dict[str, Any]:
    """One period from its day rows of one mode (``data`` + ``checks``)."""
    with_data = [d for d in days if (d.get("data") or {}).get("runtime_s") or (d.get("data") or {}).get("el_kwh")]
    valid = [d for d in with_data if not set(d.get("checks") or ()) & ENERGY_CHECKS]

    def s(rows: Iterable[Mapping[str, Any]], k: str) -> float:
        return sum(float((r.get("data") or {}).get(k) or 0) for r in rows)

    def wmean(k: str, w: str) -> float | None:
        num = den = 0.0
        for r in with_data:
            data = r.get("data") or {}
            v, wt = _num(data.get(k)), float(data.get(w) or 0)
            if v is not None and wt > 0:
                num += v * wt
                den += wt
        return num / den if den else None

    def mean(k: str) -> float | None:
        vals = [v for r in days if (v := _num((r.get("data") or {}).get(k))) is not None]
        return sum(vals) / len(vals) if vals else None

    v_el = v_th = 0.0
    bands: dict[str, list[float]] = {}
    for r in with_data:
        data = r.get("data") or {}
        if "cop_el_kwh" in data:  # whole-day row: the valid modes of the day
            d_el, d_th = float(data.get("cop_el_kwh") or 0), float(data.get("cop_th_kwh") or 0)
        elif r in valid:
            d_el, d_th = float(data.get("el_kwh") or 0), float(data.get("th_kwh") or 0)
        else:
            continue
        v_el += d_el
        v_th += d_th
        t_band = _num(data.get("outdoor_run_mean"))
        t_band = t_band if t_band is not None else _num(data.get("outdoor_mean"))
        if t_band is not None and d_el > 0:
            b = bands.setdefault(str(int(math.floor(t_band / BAND_K) * BAND_K)), [0.0, 0.0, 0])
            b[0] = round(b[0] + d_th, 3)
            b[1] = round(b[1] + d_el, 3)
            b[2] += 1
    runtime, runs = s(with_data, "runtime_s"), s(with_data, "runs")
    dd: dict[str, float] = {}
    for r in days:
        for k, v in ((r.get("data") or {}).get("degree_days") or {}).items():
            dd[k] = round(dd.get(k, 0.0) + float(v), 2)
    flags: dict[str, int] = {}
    for r in days:
        for c in r.get("checks") or ():
            flags[c] = flags.get(c, 0) + 1
    alerts: dict[str, int] = {}
    for r in days:
        for k, v in ((r.get("data") or {}).get("alerts") or {}).items():
            alerts[k] = alerts.get(k, 0) + int(v)
    mins = [v for r in days if (v := _num((r.get("data") or {}).get("outdoor_min"))) is not None]
    maxs = [v for r in days if (v := _num((r.get("data") or {}).get("outdoor_max"))) is not None]
    return {
        "el_kwh": _r(s(with_data, "el_kwh"), 2), "th_kwh": _r(s(with_data, "th_kwh"), 2),
        "cop": _r(v_th / v_el) if v_el >= MIN_EL_KWH else None,
        "cop_el_kwh": _r(v_el, 2),
        "runtime_h": _r(runtime / 3600.0, 1), "cycles": int(s(with_data, "cycles")), "runs": int(runs),
        "run_mean_min": _r(runtime / 60.0 / runs, 1) if runs else None,
        "quality_mean": _r(wmean("quality_mean", "cycles"), 1),
        "lwt_mean": _r(wmean("lwt_mean", "runtime_s"), 1),
        "return_mean": _r(wmean("return_mean", "runtime_s"), 1),
        "dt_mean": _r(wmean("dt_mean", "runtime_s"), 2),
        "flow_mean": _r(wmean("flow_mean", "runtime_s"), 1),
        "rps_mean": _r(wmean("rps_mean", "cycles"), 1),
        "outdoor_mean": _r(mean("outdoor_mean"), 1),
        "outdoor_min": min(mins) if mins else None,
        "outdoor_max": max(maxs) if maxs else None,
        "degree_days": dd,
        "buh_min": _r(s(days, "buh_min"), 1),
        "buh_cycles": int(s(days, "buh_cycles")),
        "defrost_count": int(s(days, "defrost_count")),
        "defrost_min": _r(s(days, "defrost_min"), 1),
        "alerts": alerts, "ml_anomalies": int(s(days, "ml_anomalies")),
        "n_days": n_days_in_period, "n_days_recorded": len(days), "n_days_data": len(with_data), "n_days_valid": len(valid),
        "coverage_days": _r(len(with_data) / n_days_in_period, 3) if n_days_in_period else None,
        "checks": flags,
        "cop_bands": bands,  # outdoor band (2 K, lower edge) -> [th kWh, el kWh, days]
    }
