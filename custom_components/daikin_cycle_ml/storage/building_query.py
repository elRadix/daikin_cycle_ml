"""#495 PR 3: degree days and heat per degree day from the #508 day rows.

Everything comes from ``daily_stats``: the "all" rows hold the degree days
of every scheme, the "heating" rows the space-heating heat. Today is not in
the table yet (rows are built at night), so today's degree days are worked
out live from the coordinator's outdoor accumulator with :func:`today_dd`.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any

from ..engine import period_reports as pr
from . import reports as store

WINDOWS = (("week", 7), ("month", 30))


def _dd(row: Mapping[str, Any] | None, scheme: str) -> float | None:
    v = ((row or {}).get("degree_days") or {}).get(scheme)
    return float(v) if isinstance(v, (int, float)) else None


def _per_dd(days: list[tuple[float | None, float | None]]) -> dict[str, Any]:
    """Heat and degree days summed over days that have both."""
    pairs = [(h, d) for h, d in days if h is not None and d is not None]
    heat = sum(h for h, _ in pairs)
    dd = sum(d for _, d in pairs)
    return {"kwh": round(heat, 1), "dd": round(dd, 1), "days": len(pairs),
            "kwh_per_dd": round(heat / dd, 2) if dd >= 1.0 else None}


async def summary(conn: Any, scheme: str, today: str, season_start_month: int = 10) -> dict[str, Any]:
    """Yesterday, the last 7 / 30 complete days and the season so far."""
    first = pr.period_bounds("season", pr.period_key("season", today, season_start_month),
                             season_start_month)[0]
    t = dt.date.fromisoformat(today)
    first = min(first, (t - dt.timedelta(days=30)).isoformat())
    yday = (t - dt.timedelta(days=1)).isoformat()
    rows = await store.fetch_days(conn, first, yday)
    all_rows = {r["day"]: r["data"] for r in rows if r["mode"] == pr.ALL}
    heat = {r["day"]: r["data"].get("th_kwh") for r in rows if r["mode"] == "heating"}
    season_first = pr.period_bounds("season", pr.period_key("season", today, season_start_month),
                                    season_start_month)[0]

    def window(since: str) -> dict[str, Any]:
        return _per_dd([(heat.get(d), _dd(all_rows.get(d), scheme))
                        for d in sorted(all_rows) if d >= since])

    out: dict[str, Any] = {
        "scheme": scheme,
        "yesterday": _dd(all_rows.get(yday), scheme),
        "season_since": season_first,
        "season": window(season_first),
        # outdoor means of the two days before today (Belgian schemes use them)
        "prev_means": {d: (all_rows.get(d) or {}).get("outdoor_mean")
                       for d in ((t - dt.timedelta(days=i)).isoformat() for i in (1, 2))},
    }
    for name, n in WINDOWS:
        out[name] = window((t - dt.timedelta(days=n)).isoformat())
    return out


def today_dd(today: str, mean: float | None, tmin: float | None, tmax: float | None,
             prev_means: Mapping[str, Any] | None) -> dict[str, float] | None:
    """Every scheme for today, from today's outdoor values so far."""
    temps: dict[str, dict[str, Any]] = {today: {"mean": mean, "min": tmin, "max": tmax}}
    for day, m in (prev_means or {}).items():
        temps[day] = {"mean": m}
    return pr.degree_days(today, temps)
