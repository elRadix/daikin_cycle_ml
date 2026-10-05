"""C4: weather-normalized COP degradation analysis.

Pure helpers, no HA/coordinator dependencies. Input: cop_hourly rows
(dicts) + cycles rows (dicts). Output: analysis dicts ready for
DataSnapshot.

Marker: C4_COP_DEGRADATION_v1
"""
from __future__ import annotations

from typing import Any

from ..const import (
    DEGRADATION_CRITICAL_PCT,
    DEGRADATION_LWT_SHIFT_C,
    DEGRADATION_THRESHOLD_PCT,
    OUTDOOR_BINS,
)


SEVERITY_NONE = "none"
SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"


def bin_for_outdoor(outdoor: float | None) -> str | None:
    """Return bin label for outdoor temp, or None if out of range."""
    if outdoor is None:
        return None
    for lo, hi, label in OUTDOOR_BINS:
        if lo <= outdoor < hi:
            return label
    return None


def weighted_mean(values: list[float], weights: list[float]) -> float | None:
    """Weighted mean; None if empty, mismatched, or zero total weight."""
    if not values or len(values) != len(weights):
        return None
    total_w = 0.0
    total_v = 0.0
    for v, w in zip(values, weights):
        if w <= 0:
            continue
        total_v += v * w
        total_w += w
    if total_w <= 0.0:
        return None
    return total_v / total_w


def weighted_linear_fit(
    xs: list[float], ys: list[float], ws: list[float],
) -> tuple[float, float, float] | None:
    """Weighted least-squares. Returns (slope, intercept, r2) or None.

    None if degenerate: n < 2, mismatched lengths, zero total weight,
    or zero x-variance.
    """
    n = len(xs)
    if n < 2 or n != len(ys) or n != len(ws):
        return None
    total_w = sum(w for w in ws if w > 0)
    if total_w <= 0.0:
        return None
    mean_x = sum(x * w for x, w in zip(xs, ws)) / total_w
    mean_y = sum(y * w for y, w in zip(ys, ws)) / total_w
    sxx = sum(w * (x - mean_x) ** 2 for x, w in zip(xs, ws))
    if sxx <= 0.0:
        return None
    sxy = sum(
        w * (x - mean_x) * (y - mean_y) for x, y, w in zip(xs, ys, ws)
    )
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    ss_res = sum(
        w * (y - (slope * x + intercept)) ** 2
        for x, y, w in zip(xs, ys, ws)
    )
    ss_tot = sum(w * (y - mean_y) ** 2 for y, w in zip(ys, ws))
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0.0 else 0.0
    return slope, intercept, r2


def severity_for_pct(
    week_pct: float | None,
    *,
    threshold: float = DEGRADATION_THRESHOLD_PCT,
    critical: float = DEGRADATION_CRITICAL_PCT,
) -> str:
    """Map week_pct to base severity tier (before LWT downgrade)."""
    if week_pct is None:
        return SEVERITY_NONE
    if week_pct < critical:
        return SEVERITY_CRITICAL
    if week_pct < threshold:
        return SEVERITY_WARNING
    return SEVERITY_NONE


def downgrade_for_lwt(
    severity: str, lwt_shift: bool,
    *, shift_c: float = DEGRADATION_LWT_SHIFT_C,
) -> tuple[str, bool]:
    """Return (downgraded_severity, was_downgraded).

    Only downgrades critical->warning and warning->info when lwt_shift
    is True. none and info are unaffected. shift_c reserved for future
    graduated downgrade logic.
    """
    _ = shift_c
    if not lwt_shift:
        return severity, False
    if severity == SEVERITY_CRITICAL:
        return SEVERITY_WARNING, True
    if severity == SEVERITY_WARNING:
        return SEVERITY_INFO, True
    return severity, False


def build_dirty_hours(cycles: list[dict[str, Any]]) -> set[int]:
    """Return set of hour-buckets that overlap BUH/defrost cycles.

    A cycle with buh_used or defrost_used marks all hours between its
    start_ts and end_ts (inclusive) as dirty. end_ts falls back to
    start_ts + duration_s when None.
    """
    dirty: set[int] = set()
    for c in cycles:
        if not (c.get("buh_used") or c.get("defrost_used")):
            continue
        start = c.get("start_ts")
        if start is None:
            continue
        end = c.get("end_ts")
        if end is None:
            dur = c.get("duration_s")
            if isinstance(dur, (int, float)) and dur > 0:
                end = float(start) + float(dur)
            else:
                end = start
        try:
            h0 = int(float(start) // 3600)
            h1 = int(float(end) // 3600)
        except (TypeError, ValueError):
            continue
        if h1 < h0:
            h0, h1 = h1, h0
        for h in range(h0, h1 + 1):
            dirty.add(h)
    return dirty


def filter_dirty_hours(
    rows: list[dict[str, Any]], dirty: set[int],
) -> list[dict[str, Any]]:
    """Drop hourly rows whose hour-bucket is in dirty set."""
    return [r for r in rows if int(r.get("ts_hour", 0)) not in dirty]


def aggregate_by_bin(
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Aggregate hourly rows per outdoor bin.

    Returns {label: {hours, n_samples, cop_mean, lwt_mean}}.
    Rows without outdoor_mean, cop_mean, or n_samples>0 are skipped.
    """
    acc: dict[str, dict[str, float]] = {}
    for r in rows:
        outdoor = r.get("outdoor_mean")
        if outdoor is None:
            continue
        label = bin_for_outdoor(float(outdoor))
        if label is None:
            continue
        n = int(r.get("n_samples") or 0)
        if n <= 0:
            continue
        cop = r.get("cop_mean")
        if cop is None:
            continue
        b = acc.setdefault(label, {
            "hours": 0.0, "n_samples": 0.0,
            "cop_sum": 0.0, "cop_w": 0.0,
            "lwt_sum": 0.0, "lwt_w": 0.0,
        })
        b["hours"] += 1
        b["n_samples"] += n
        b["cop_sum"] += float(cop) * n
        b["cop_w"] += n
        lwt = r.get("lwt_mean")
        if lwt is not None:
            b["lwt_sum"] += float(lwt) * n
            b["lwt_w"] += n
    out: dict[str, dict[str, Any]] = {}
    for label, b in acc.items():
        out[label] = {
            "hours": int(b["hours"]),
            "n_samples": int(b["n_samples"]),
            "cop_mean": (
                b["cop_sum"] / b["cop_w"] if b["cop_w"] > 0 else None
            ),
            "lwt_mean": (
                b["lwt_sum"] / b["lwt_w"] if b["lwt_w"] > 0 else None
            ),
        }
    return out


def merge_bins(
    recent_bins: dict[str, dict[str, Any]],
    prev_bins: dict[str, dict[str, Any]],
    *, min_hours: int,
) -> list[dict[str, Any]]:
    """Return bins present in both windows with >= min_hours each.

    Bins ordered by OUTDOOR_BINS_ORDER. Each entry contains ratio and
    weight (min of hours_recent, hours_prev). Skips bins where prev
    cop_mean <= 0 (invalid baseline).
    """
    order = tuple(b[2] for b in OUTDOOR_BINS)
    used: list[dict[str, Any]] = []
    for label in order:
        r = recent_bins.get(label)
        p = prev_bins.get(label)
        if r is None or p is None:
            continue
        if r["hours"] < min_hours or p["hours"] < min_hours:
            continue
        cop_r = r["cop_mean"]
        cop_p = p["cop_mean"]
        if cop_r is None or cop_p is None or cop_p <= 0:
            continue
        used.append({
            "range": label,
            "hours_recent": int(r["hours"]),
            "hours_prev": int(p["hours"]),
            "cop_recent": float(cop_r),
            "cop_prev": float(cop_p),
            "ratio": float(cop_r) / float(cop_p),
            "weight": min(int(r["hours"]), int(p["hours"])),
        })
    return used

def _distinct_days(rows: list[dict[str, Any]]) -> int:
    """Count distinct UTC days present in hourly rows."""
    return len({int(r["ts_hour"]) // 24 for r in rows if "ts_hour" in r})


def _weighted_lwt(rows: list[dict[str, Any]]) -> float | None:
    """n_samples-weighted mean of lwt_mean across hourly rows."""
    vals: list[float] = []
    ws: list[float] = []
    for r in rows:
        lwt = r.get("lwt_mean")
        n = r.get("n_samples")
        if lwt is None or n is None or float(n) <= 0:
            continue
        vals.append(float(lwt))
        ws.append(float(n))
    return weighted_mean(vals, ws)


def _dynamic_min_samples(n_bins: int) -> int:
    """Sample floor based on bin coverage: fewer bins -> higher floor."""
    from ..const import (
        DEGRADATION_MIN_SAMPLES_1BIN,
        DEGRADATION_MIN_SAMPLES_2BIN,
        DEGRADATION_MIN_SAMPLES_3BIN,
    )
    if n_bins >= 3:
        return DEGRADATION_MIN_SAMPLES_3BIN
    if n_bins == 2:
        return DEGRADATION_MIN_SAMPLES_2BIN
    if n_bins == 1:
        return DEGRADATION_MIN_SAMPLES_1BIN
    return 0


def analyze_degradation(
    recent_rows: list[dict[str, Any]],
    prev_rows: list[dict[str, Any]],
    dirty_hours: set[int],
    *,
    window_days: int = 7,
    threshold: float = DEGRADATION_THRESHOLD_PCT,
    critical: float = DEGRADATION_CRITICAL_PCT,
    min_hours_per_bin: int = 6,
    min_days: int = 3,
    skew_max: float = 0.15,
    lwt_shift_c: float = DEGRADATION_LWT_SHIFT_C,
    now: float | None = None,
) -> dict[str, Any]:
    """Compute weather-normalized 7d-vs-7d degradation + severity.

    Steps: filter dirty hours -> aggregate per outdoor bin -> merge
    bins present in both windows -> weighted mean of ratios. Returns
    a dict ready for DataSnapshot / attrs.

    week_pct is None when: no bins survive, samples below dynamic
    floor, or distinct days below min_days. severity_raw reflects
    base tier; severity applies LWT downgrade.
    """
    recent_clean = filter_dirty_hours(recent_rows, dirty_hours)
    prev_clean = filter_dirty_hours(prev_rows, dirty_hours)

    recent_bins = aggregate_by_bin(recent_clean)
    prev_bins = aggregate_by_bin(prev_clean)
    merged = merge_bins(
        recent_bins, prev_bins, min_hours=min_hours_per_bin,
    )

    n_samples_recent = sum(
        int(r.get("n_samples") or 0) for r in recent_clean
    )
    n_samples_prev = sum(
        int(r.get("n_samples") or 0) for r in prev_clean
    )
    n_days_recent = _distinct_days(recent_clean)
    n_days_prev = _distinct_days(prev_clean)

    n_bins_used = len(merged)
    dyn_min = _dynamic_min_samples(n_bins_used)

    week_pct: float | None = None
    if merged:
        total_w = sum(b["weight"] for b in merged)
        if total_w > 0:  # pragma: no cover
            ratio_mean = sum(
                b["ratio"] * b["weight"] for b in merged
            ) / total_w
            week_pct = (ratio_mean - 1.0) * 100.0

    # exclusion skew: asymmetry in dirty-hour contamination
    n_recent_all = len(recent_rows)
    n_prev_all = len(prev_rows)
    excluded_recent = n_recent_all - len(recent_clean)
    excluded_prev = n_prev_all - len(prev_clean)
    ratio_recent = (
        excluded_recent / n_recent_all if n_recent_all > 0 else 0.0
    )
    ratio_prev = (
        excluded_prev / n_prev_all if n_prev_all > 0 else 0.0
    )
    exclusion_skew = abs(ratio_recent - ratio_prev)

    # LWT shift detection
    lwt_recent = _weighted_lwt(recent_clean)
    lwt_prev = _weighted_lwt(prev_clean)
    lwt_shift_c_val = 0.0
    if lwt_recent is not None and lwt_prev is not None:
        lwt_shift_c_val = abs(lwt_recent - lwt_prev)
    lwt_shift_detected = lwt_shift_c_val > lwt_shift_c

    # validity gate
    valid = (
        week_pct is not None
        and n_samples_recent >= dyn_min
        and n_days_recent >= min_days
        and exclusion_skew < skew_max
    )
    if not valid:
        week_pct_out: float | None = week_pct if week_pct is not None else None
    else:
        week_pct_out = week_pct

    severity_raw = severity_for_pct(
        week_pct_out if valid else None,
        threshold=threshold, critical=critical,
    )
    severity, downgraded = downgrade_for_lwt(
        severity_raw, lwt_shift_detected,
    )

    return {
        "mode": "heating",
        "window_days": window_days,
        "week_pct": week_pct_out if valid else None,
        "week_pct_raw": week_pct,
        "severity": severity,
        "severity_raw": severity_raw,
        "severity_downgraded": downgraded,
        "threshold_pct": threshold,
        "critical_pct": critical,
        "n_samples_recent": n_samples_recent,
        "n_samples_prev": n_samples_prev,
        "n_days_recent": n_days_recent,
        "n_days_prev": n_days_prev,
        "n_bins_used": n_bins_used,
        "dynamic_min_samples": dyn_min,
        "bins_used": merged,
        "excluded_hours_recent": excluded_recent,
        "excluded_hours_prev": excluded_prev,
        "exclusion_skew": exclusion_skew,
        "lwt_mean_recent": lwt_recent,
        "lwt_mean_prev": lwt_prev,
        "lwt_shift_detected": lwt_shift_detected,
        "lwt_shift_c": lwt_shift_c_val,
        "valid": valid,
        "updated_ts": float(now) if now is not None else None,
    }

def _outdoor_spread(rows: list[dict[str, Any]]) -> float:
    """max - min outdoor_mean across rows with valid outdoor value."""
    vals = [
        float(r["outdoor_mean"])
        for r in rows
        if r.get("outdoor_mean") is not None
    ]
    if len(vals) < 2:
        return 0.0
    return max(vals) - min(vals)


def analyze_trend(
    baseline_rows: list[dict[str, Any]],
    recent_rows: list[dict[str, Any]],
    dirty_hours: set[int],
    *,
    window_days: int = 30,
    baseline_days: int = 30,
    recent_days: int = 7,
    threshold: float = DEGRADATION_THRESHOLD_PCT,
    critical: float = DEGRADATION_CRITICAL_PCT,
    min_hours_fit: int = 10,
    min_spread_c: float = 5.0,
    now: float | None = None,
) -> dict[str, Any]:
    """Regression-based 30d trend: COP ~ a + b * T_outdoor.

    Fits weighted least-squares on baseline window, then compares
    recent observed COP to the baseline-predicted COP at recent
    outdoor conditions. trend_pct is relative to predicted mean, so
    positive = better than expected, negative = degradation.
    """
    base_clean = filter_dirty_hours(baseline_rows, dirty_hours)
    recent_clean = filter_dirty_hours(recent_rows, dirty_hours)

    xs = [
        float(r["outdoor_mean"])
        for r in base_clean
        if r.get("outdoor_mean") is not None
        and r.get("cop_mean") is not None
        and (r.get("n_samples") or 0) > 0
    ]
    ys = [
        float(r["cop_mean"])
        for r in base_clean
        if r.get("outdoor_mean") is not None
        and r.get("cop_mean") is not None
        and (r.get("n_samples") or 0) > 0
    ]
    ws = [
        float(r["n_samples"])
        for r in base_clean
        if r.get("outdoor_mean") is not None
        and r.get("cop_mean") is not None
        and (r.get("n_samples") or 0) > 0
    ]

    n_hours_baseline = len(xs)
    n_hours_recent = len(recent_clean)
    spread = _outdoor_spread(base_clean)

    fit_result = None
    if (
        n_hours_baseline >= min_hours_fit
        and spread >= min_spread_c
    ):
        fit_result = weighted_linear_fit(xs, ys, ws)

    slope: float | None = None
    intercept: float | None = None
    r2: float | None = None
    trend_pct: float | None = None
    cop_predicted_recent: float | None = None
    cop_observed_recent: float | None = None
    valid = False

    if fit_result is not None:
        slope, intercept, r2 = fit_result
        pred_vals: list[float] = []
        obs_vals: list[float] = []
        pw: list[float] = []
        for r in recent_clean:
            out = r.get("outdoor_mean")
            cop = r.get("cop_mean")
            n = r.get("n_samples") or 0
            if out is None or cop is None or n <= 0:
                continue
            pred = slope * float(out) + intercept
            pred_vals.append(pred)
            obs_vals.append(float(cop))
            pw.append(float(n))
        if pred_vals and pw:
            cop_predicted_recent = weighted_mean(pred_vals, pw)
            cop_observed_recent = weighted_mean(obs_vals, pw)
            if (
                cop_predicted_recent is not None
                and cop_predicted_recent > 0.0
                and cop_observed_recent is not None
            ):
                trend_pct = (
                    (cop_observed_recent - cop_predicted_recent)
                    / cop_predicted_recent
                ) * 100.0
                valid = True

    severity = severity_for_pct(
        trend_pct if valid else None,
        threshold=threshold, critical=critical,
    )

    return {
        "mode": "heating",
        "window_days": window_days,
        "baseline_days": baseline_days,
        "recent_days": recent_days,
        "trend_30d": trend_pct if valid else None,
        "trend_30d_raw": trend_pct,
        "severity": severity,
        "threshold_pct": threshold,
        "critical_pct": critical,
        "n_hours_baseline": n_hours_baseline,
        "n_hours_recent": n_hours_recent,
        "outdoor_spread_baseline_c": spread,
        "fit_slope": slope,
        "fit_intercept": intercept,
        "fit_r2": r2,
        "cop_predicted_recent": cop_predicted_recent,
        "cop_observed_recent": cop_observed_recent,
        "valid": valid,
        "updated_ts": float(now) if now is not None else None,
    }

