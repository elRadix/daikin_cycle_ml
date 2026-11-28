"""Build the period reports (#508): days from their sources, then the weeks,
months, years and heating seasons those days belong to.

Days are frozen (``finalised``) two days after they end, once late cycle
closes and rollups have landed; a period is frozen once all its days are.
A frozen row is never rewritten except by a rebuild that clears it.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Any

from ..engine import period_reports as pr
from . import reports as store

REPORTS_STATE_KEY = "reports_state"
FINALISE_AFTER_DAYS = 2
OUTLIER_HISTORY_DAYS = 120


def _shift(day: str, days: int) -> str:
    return (dt.date.fromisoformat(day) + dt.timedelta(days=days)).isoformat()


async def build_reports(db: Any, *, today: str, full: bool = False, season_start_month: int = 10,
                        sample_interval_s: float = 300.0) -> dict[str, Any]:
    """Build or refresh the reports; returns what was built."""
    await db.async_ensure_cop_samples_table()  # self-healing columns (buh_active)
    await db.async_create_cop_hourly_v14()
    conn = db._require()
    state = await db.async_get_model_state(REPORTS_STATE_KEY) or {}
    oldest = await store.first_source_day(conn)
    if oldest is None:
        return {"days": 0, "periods": 0}
    if full:
        await store.clear(conn)
    if full or not state.get("last_final_day"):
        first = oldest
    else:
        first = max(oldest, _shift(str(state["last_final_day"]), 1))
    first = min(first, _shift(today, -FINALISE_AFTER_DAYS))
    first = max(first, oldest)
    days = pr.day_range(first, today)
    done = set() if full else await store.finalised_days(conn, first, today)
    sources = await store.fetch_sources(conn, _shift(first, -2), today, sample_interval_s=sample_interval_s)
    temps = {d: s.get("temps") or {} for d, s in sources.items()}

    history: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for row in await store.fetch_days(conn, _shift(first, -OUTLIER_HISTORY_DAYS), _shift(first, -1)):
        data = row["data"]
        if row["mode"] in pr.MODES and not set(row["checks"]) & pr.ENERGY_CHECKS:
            if data.get("cop") is not None and data.get("outdoor_run_mean") is not None:
                history[row["mode"]].append((float(data["cop"]), float(data["outdoor_run_mean"])))

    final_limit = _shift(today, -FINALISE_AFTER_DAYS)
    rows: list[tuple[str, str, dict[str, Any], list[str], bool]] = []
    built: list[str] = []
    for day in days:
        if day in done:
            continue
        src = sources.get(day) or {}
        day_len = store.day_length_s(day)
        modes: dict[str, dict[str, Any]] = {}
        for mode in pr.MODES:
            msrc = (src.get("modes") or {}).get(mode) or {}
            row = pr.build_mode_row(msrc, sample_interval_s=sample_interval_s)
            if not (row["runtime_s"] or row["el_kwh"] or row["samples"]):
                continue
            checks = pr.check_mode_row(row, day_len)
            if not checks and pr.check_outlier(row["cop"], row["outdoor_run_mean"], history[mode][-OUTLIER_HISTORY_DAYS:]):
                checks.append("outlier")
            if not set(checks) & pr.ENERGY_CHECKS and row["cop"] is not None and row["outdoor_run_mean"] is not None:
                history[mode].append((row["cop"], row["outdoor_run_mean"]))
            row["checks"] = checks
            modes[mode] = row
        all_row = pr.build_all_row(day, modes, src, temps, day_len)
        all_checks = pr.check_all_row(all_row, modes)
        if not modes and all_row["outdoor_mean"] is None:
            continue
        final = day <= final_limit
        for mode, row in modes.items():
            checks = row.pop("checks")
            rows.append((day, mode, row, checks, final))
        rows.append((day, pr.ALL, all_row, all_checks, final))
        built.append(day)
    if rows:
        await store.upsert_days(conn, rows)

    periods = {p for day in built for p in pr.periods_of_day(day, season_start_month)}
    for ptype, key in sorted(periods):
        p_first, p_last = pr.period_bounds(ptype, key, season_start_month)
        n_days = len(pr.day_range(p_first, min(p_last, today)))
        by_mode: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in await store.fetch_days(conn, p_first, p_last):
            by_mode[row["mode"]].append(row)
        final = p_last <= final_limit and all(r["finalised"] for r in by_mode.get(pr.ALL, []))
        for mode, mrows in by_mode.items():
            data = pr.aggregate(mrows, n_days_in_period=n_days)
            await store.upsert_period(conn, ptype, key, mode, p_first, p_last, data, final)
    await conn.commit()

    # Every day up to final_limit has been looked at (a day without any
    # source has nothing to store); the next build starts after it.
    out = {"days": len(built), "periods": len(periods), "first_day": first, "last_day": today,
           "last_final_day": final_limit}
    await db.async_set_model_state(REPORTS_STATE_KEY, out)
    return out
