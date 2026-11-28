"""Storage of the period reports (#508): reading the day sources in bulk and
writing / reading ``daily_stats`` and ``period_reports``.

The sources are read per date range (not per day), so a backfill over a
year of history stays a handful of queries. Local days follow the Home
Assistant time zone through ``time.localtime``.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from typing import Any

from ..engine.period_reports import CP_WATER, MODES

_DAY = "%Y-%m-%d"


def _local_day(ts: float) -> str:
    return time.strftime(_DAY, time.localtime(float(ts)))


def day_start_ts(day: str) -> float:
    return time.mktime(time.strptime(day, _DAY))


def day_length_s(day: str) -> float:
    """23, 24 or 25 h around a DST change."""
    y, m, d = (int(x) for x in day.split("-"))
    nxt = time.strftime(_DAY, time.localtime(time.mktime((y, m, d, 12, 0, 0, 0, 0, -1)) + 86400))
    return day_start_ts(nxt) - day_start_ts(day)


async def fetch_sources(conn: Any, first_day: str, last_day: str,
                        *, sample_interval_s: float) -> dict[str, dict[str, Any]]:
    """Every source value per day (and per mode) between two local days."""
    t0, t1 = day_start_ts(first_day), day_start_ts(last_day) + day_length_s(last_day)
    out: dict[str, dict[str, Any]] = defaultdict(lambda: {"modes": defaultdict(dict)})

    async with conn.execute(
        "SELECT day, mode, cycles, runs, total_duration_s, duration_min, duration_max, "
        "quality_sum, dt_max_sum, rps_sum, buh_count, defrost_count, transient_count "
        "FROM daily_summary WHERE day >= ? AND day <= ?", (first_day, last_day),
    ) as cur:
        for r in await cur.fetchall():
            row = dict(r)
            out[row.pop("day")]["modes"][row.pop("mode")]["daily_summary"] = row

    async with conn.execute(
        "SELECT key, value_json FROM model_state WHERE (key >= ? AND key <= ?) OR (key >= ? AND key <= ?)",
        (f"energy_acc.{first_day}", f"energy_acc.{last_day}",
         f"runtime_acc.{first_day}", f"runtime_acc.{last_day}"),
    ) as cur:
        for r in await cur.fetchall():
            kind, day = r["key"].split(".", 1)
            try:
                val = json.loads(r["value_json"])
            except (TypeError, ValueError):
                continue
            if not isinstance(val, dict):
                continue
            if kind == "energy_acc":
                for m in MODES:
                    out[day]["modes"][m]["el_kwh"] = val.get(f"{m}_el_kwh")
                    out[day]["modes"][m]["th_kwh"] = val.get(f"{m}_th_kwh")
            else:
                out[day]["runtime_acc"] = val

    hourly: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    temps_run: dict[str, dict[str, Any]] = defaultdict(lambda: {"n": 0.0, "sum": 0.0, "min": None, "max": None})
    async with conn.execute(
        "SELECT ts_hour, mode, n_samples, lwt_mean, flow_mean, outdoor_mean, outdoor_min, outdoor_max "
        "FROM cop_hourly WHERE ts_hour >= ? AND ts_hour < ?", (int(t0 // 3600), int(t1 // 3600) + 1),
    ) as cur:
        for r in await cur.fetchall():
            day = _local_day(r["ts_hour"] * 3600)
            n = float(r["n_samples"] or 0)
            if n <= 0:
                continue
            h = hourly[(day, r["mode"])]
            for k in ("lwt_mean", "flow_mean", "outdoor_mean"):
                if r[k] is not None:
                    h[k + "_sum"] += float(r[k]) * n
                    h[k + "_n"] += n
            tr = temps_run[day]
            if r["outdoor_mean"] is not None:
                tr["sum"] += float(r["outdoor_mean"]) * n
                tr["n"] += n
            for k, fn in (("outdoor_min", min), ("outdoor_max", max)):
                if r[k] is not None:
                    key = k.split("_")[1]
                    tr[key] = float(r[k]) if tr[key] is None else fn(tr[key], float(r[k]))
    for (day, mode), h in hourly.items():
        out[day]["modes"][mode]["hourly"] = {
            k: h[k + "_sum"] / h[k + "_n"] for k in ("lwt_mean", "flow_mean", "outdoor_mean") if h[k + "_n"]
        }

    smp: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    async with conn.execute(
        "SELECT ts, mode, r1t, lwt, r4t, flow_lmin, power_w, COALESCE(buh_active, 0) AS buh "
        "FROM cop_samples WHERE ts >= ? AND ts < ? AND COALESCE(is_transition_artifact, 0) = 0 "
        "AND COALESCE(boiler_active, 0) = 0", (t0, t1),
    ) as cur:
        for r in await cur.fetchall():
            s = smp[(_local_day(r["ts"]), r["mode"] or "unknown")]
            s["n"] += 1
            s["buh_n"] += 1 if r["buh"] else 0
            leave = r["r1t"] if r["r1t"] is not None else r["lwt"]
            if r["r4t"] is not None:
                s["r4t_sum"] += float(r["r4t"])
                s["r4t_n"] += 1
                if leave is not None:
                    s["dt_sum"] += float(leave) - float(r["r4t"])
                    s["dt_n"] += 1
                    if r["flow_lmin"] is not None:
                        kw = float(r["flow_lmin"]) / 60.0 * CP_WATER * (float(leave) - float(r["r4t"]))
                        s["heat_kwh"] += max(0.0, kw) * sample_interval_s / 3600.0
            if r["power_w"] is not None:
                s["power_kwh"] += float(r["power_w"]) / 1000.0 * sample_interval_s / 3600.0
    for (day, mode), s in smp.items():
        out[day]["modes"][mode]["samples"] = {
            "n": s["n"], "buh_n": s["buh_n"],
            "r4t_mean": s["r4t_sum"] / s["r4t_n"] if s["r4t_n"] else None,
            "dt_mean": s["dt_sum"] / s["dt_n"] if s["dt_n"] else None,
            "heat_kwh": s["heat_kwh"] if s["dt_n"] else None,
            "power_kwh": s["power_kwh"] or None,
        }

    async with conn.execute(
        "SELECT ts, alert_type FROM alerts WHERE ts >= ? AND ts < ?", (t0, t1),
    ) as cur:
        for r in await cur.fetchall():
            a = out[_local_day(r["ts"])].setdefault("alerts", {})
            a[r["alert_type"]] = a.get(r["alert_type"], 0) + 1

    for day in list(out):
        rt = out[day].get("runtime_acc") or {}
        if rt.get("outdoor_s"):
            out[day]["temps"] = {
                "mean": float(rt["outdoor_sum"]) / float(rt["outdoor_s"]),
                "min": rt.get("outdoor_min"), "max": rt.get("outdoor_max"), "source": "all_day",
            }
        elif temps_run[day]["n"]:
            tr = temps_run[day]
            out[day]["temps"] = {"mean": tr["sum"] / tr["n"], "min": tr["min"], "max": tr["max"],
                                 "source": "running_hours"}
    return out


async def first_source_day(conn: Any) -> str | None:
    """The oldest local day any source still covers."""
    days: list[str] = []
    for sql in ("SELECT MIN(day) FROM daily_summary",
                "SELECT MIN(substr(key, 12)) FROM model_state WHERE key LIKE 'energy_acc.%'"):
        async with conn.execute(sql) as cur:
            row = await cur.fetchone()
            if row and row[0]:
                days.append(str(row[0]))
    async with conn.execute("SELECT MIN(ts_hour) FROM cop_hourly") as cur:
        row = await cur.fetchone()
        if row and row[0] is not None:
            days.append(_local_day(int(row[0]) * 3600))
    return min(days) if days else None


async def upsert_days(conn: Any, rows: list[tuple[str, str, dict[str, Any], list[str], bool]]) -> None:
    now = time.time()
    await conn.executemany(
        "INSERT INTO daily_stats (day, mode, data_json, checks, finalised, updated_ts) VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(day, mode) DO UPDATE SET data_json=excluded.data_json, checks=excluded.checks, "
        "finalised=excluded.finalised, updated_ts=excluded.updated_ts WHERE daily_stats.finalised = 0",
        [(d, m, json.dumps(data, separators=(",", ":")), ",".join(c), int(f), now) for d, m, data, c, f in rows],
    )
    await conn.commit()


async def fetch_days(conn: Any, first_day: str, last_day: str, mode: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT day, mode, data_json, checks, finalised FROM daily_stats WHERE day >= ? AND day <= ?"
    args: list[Any] = [first_day, last_day]
    if mode:
        sql += " AND mode = ?"
        args.append(mode)
    async with conn.execute(sql + " ORDER BY day", args) as cur:
        rows = await cur.fetchall()
    return [{"day": r["day"], "mode": r["mode"], "data": json.loads(r["data_json"]),
             "checks": [c for c in (r["checks"] or "").split(",") if c], "finalised": bool(r["finalised"])}
            for r in rows]


async def finalised_days(conn: Any, first_day: str, last_day: str) -> set[str]:
    async with conn.execute(
        "SELECT DISTINCT day FROM daily_stats WHERE finalised = 1 AND day >= ? AND day <= ?",
        (first_day, last_day),
    ) as cur:
        return {r[0] for r in await cur.fetchall()}


async def upsert_period(conn: Any, period_type: str, key: str, mode: str, first_day: str,
                        last_day: str, data: dict[str, Any], finalised: bool) -> None:
    await conn.execute(
        "INSERT INTO period_reports (period_type, period_key, mode, first_day, last_day, data_json, "
        "finalised, updated_ts) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(period_type, period_key, mode) "
        "DO UPDATE SET data_json=excluded.data_json, finalised=excluded.finalised, "
        "updated_ts=excluded.updated_ts WHERE period_reports.finalised = 0",
        (period_type, key, mode, first_day, last_day, json.dumps(data, separators=(",", ":")),
         int(finalised), time.time()),
    )


async def fetch_periods(conn: Any, period_type: str, keys: list[str] | None = None,
                        mode: str | None = None) -> list[dict[str, Any]]:
    sql = ("SELECT period_type, period_key, mode, first_day, last_day, data_json, finalised "
           "FROM period_reports WHERE period_type = ?")
    args: list[Any] = [period_type]
    if keys:
        sql += f" AND period_key IN ({','.join('?' * len(keys))})"
        args += keys
    if mode:
        sql += " AND mode = ?"
        args.append(mode)
    async with conn.execute(sql + " ORDER BY first_day, mode", args) as cur:
        rows = await cur.fetchall()
    return [{"period_type": r["period_type"], "period_key": r["period_key"], "mode": r["mode"],
             "first_day": r["first_day"], "last_day": r["last_day"],
             "data": json.loads(r["data_json"]), "finalised": bool(r["finalised"])} for r in rows]


async def clear(conn: Any) -> None:
    """Drop every stored day and period (rebuild)."""
    await conn.execute("DELETE FROM daily_stats")
    await conn.execute("DELETE FROM period_reports")


async def counts(conn: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in ("daily_stats", "period_reports"):
        async with conn.execute(f"SELECT COUNT(*) FROM {t}") as cur:
            row = await cur.fetchone()
            out[t] = int(row[0]) if row else 0
    return out
