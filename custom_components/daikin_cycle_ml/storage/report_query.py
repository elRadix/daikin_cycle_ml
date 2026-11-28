"""Read the period reports (#508): one period with its comparison, trend,
history and days, the summary of the last finished month, and exports.
"""
from __future__ import annotations

import csv
import io
from typing import Any

from ..engine import period_reports as pr
from ..engine import report_compare as rc
from . import reports as store

HISTORY_DEFAULT = 12
TREND_METRICS = ("cop", "el_per_dd", "quality_mean", "run_mean_min", "starts_per_h")
_HISTORY_FIELDS = ("cop", "el_kwh", "th_kwh", "runtime_h", "cycles", "quality_mean",
                   "outdoor_mean", "lwt_mean", "buh_min", "defrost_count", "coverage_days")


async def available_keys(conn: Any, period_type: str, mode: str = pr.ALL) -> list[str]:
    """Period keys with a stored report, newest first."""
    async with conn.execute(
        "SELECT period_key FROM period_reports WHERE period_type = ? AND mode = ? "
        "ORDER BY first_day DESC", (period_type, mode),
    ) as cur:
        return [r[0] for r in await cur.fetchall()]


async def _period(conn: Any, period_type: str, key: str | None, mode: str) -> dict[str, Any] | None:
    if not key:
        return None
    rows = await store.fetch_periods(conn, period_type, [key], mode=mode)
    return rows[0] if rows else None


def _history_row(row: dict[str, Any], scheme: str) -> dict[str, Any]:
    data = row["data"]
    d = rc.derived(data, scheme)
    out = {"key": row["period_key"], "first_day": row["first_day"], "last_day": row["last_day"],
           "finalised": row["finalised"]}
    out.update({k: data.get(k) for k in _HISTORY_FIELDS})
    out.update({k: d.get(k) for k in ("dd", "el_per_dd", "starts_per_h", "buh_share_pct")})
    return out


async def get_report(conn: Any, *, period_type: str, key: str | None = None, mode: str = pr.ALL,
                     against: str = "previous", history: int = HISTORY_DEFAULT,
                     include_days: bool = False, scheme: str = "nl18",
                     season_start_month: int = 10) -> dict[str, Any]:
    """Everything the Reports card shows for one period."""
    keys = await available_keys(conn, period_type, mode)
    key = key or (keys[0] if keys else None)
    cur = await _period(conn, period_type, key, mode)
    out: dict[str, Any] = {
        "period_type": period_type, "key": key, "mode": mode, "scheme": scheme,
        "against": against, "available": keys, "found": cur is not None,
    }
    if cur is None:
        return out
    out.update({"first_day": cur["first_day"], "last_day": cur["last_day"],
                "finalised": cur["finalised"], "data": cur["data"],
                "derived": rc.derived(cur["data"], scheme)})
    ref_key = rc.reference_key(period_type, cur["period_key"], against, season_start_month)
    ref = await _period(conn, period_type, ref_key, mode)
    out["reference"] = {"key": ref_key, "found": ref is not None,
                        "first_day": ref["first_day"] if ref else None,
                        "last_day": ref["last_day"] if ref else None}
    out["compare"] = rc.compare(cur["data"], ref["data"] if ref else None, scheme)

    rows = [r for r in await store.fetch_periods(conn, period_type, mode=mode)
            if r["first_day"] <= cur["first_day"]][-max(1, history):]
    hist = [_history_row(r, scheme) for r in rows]
    out["history"] = hist
    out["trend"] = {m: rc.trend([h.get(m) for h in hist]) for m in TREND_METRICS}

    if mode == pr.ALL:
        by_mode = {}
        for r in await store.fetch_periods(conn, period_type, [cur["period_key"]]):
            if r["mode"] != pr.ALL:
                d = r["data"]
                by_mode[r["mode"]] = {k: d.get(k) for k in ("el_kwh", "th_kwh", "cop", "runtime_h",
                                                            "cycles", "quality_mean")}
        out["by_mode"] = by_mode
    if include_days:
        out["days"] = [{"day": r["day"], "checks": r["checks"], "finalised": r["finalised"], **r["data"]}
                       for r in await store.fetch_days(conn, cur["first_day"], cur["last_day"], mode)]
    return out


async def last_month_summary(conn: Any, scheme: str, today: str) -> dict[str, Any] | None:
    """Headline of the newest finished month, for the sensor and automations."""
    finished = [r for r in await store.fetch_periods(conn, "month", mode=pr.ALL) if r["last_day"] < today]
    if not finished:
        return None
    row = finished[-1]
    data = row["data"]
    out: dict[str, Any] = {
        "period": row["period_key"], "finalised": row["finalised"],
        "cop": data.get("cop"), "el_kwh": data.get("el_kwh"), "th_kwh": data.get("th_kwh"),
        "runtime_h": data.get("runtime_h"), "outdoor_mean": data.get("outdoor_mean"),
        "coverage_days": data.get("coverage_days"),
        "el_per_dd": rc.derived(data, scheme).get("el_per_dd"), "scheme": scheme,
    }
    for against in ("previous", "last_year"):
        ref = await _period(conn, "month", rc.reference_key("month", row["period_key"], against), pr.ALL)
        cmp = rc.compare(data, ref["data"] if ref else None, scheme)
        metrics = cmp["metrics"]
        out[f"cop_vs_{against}_pct"] = (metrics.get("cop") or {}).get("delta_pct")
        out[f"el_per_dd_vs_{against}_pct"] = (metrics.get("el_per_dd") or {}).get("delta_pct")
        out[f"verdict_vs_{against}"] = cmp["verdicts"].get("overall")
    return out


def _flat(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, dict):
            for k2, v2 in v.items():
                out[f"{k}.{k2}"] = v2 if not isinstance(v2, (dict, list)) else str(v2)
        elif isinstance(v, list):
            out[k] = ",".join(str(x) for x in v)
        else:
            out[k] = v
    return out


async def export(conn: Any, *, table: str, period_type: str | None = None, mode: str | None = None,
                 first_day: str | None = None, last_day: str | None = None,
                 fmt: str = "json") -> dict[str, Any]:
    """``daily_stats`` (``table="days"``) or ``period_reports`` as JSON or CSV."""
    if table == "days":
        rows = [{"day": r["day"], "mode": r["mode"], "finalised": r["finalised"], "checks": r["checks"],
                 **r["data"]}
                for r in await store.fetch_days(conn, first_day or "0000-00-00", last_day or "9999-12-31", mode)]
    else:
        rows = []
        for ptype in ([period_type] if period_type else list(pr.PERIOD_TYPES)):
            for r in await store.fetch_periods(conn, ptype, mode=mode):
                if (first_day and r["last_day"] < first_day) or (last_day and r["first_day"] > last_day):
                    continue
                rows.append({"period_type": r["period_type"], "period_key": r["period_key"],
                             "mode": r["mode"], "first_day": r["first_day"], "last_day": r["last_day"],
                             "finalised": r["finalised"], **r["data"]})
    out: dict[str, Any] = {"table": table, "format": fmt, "count": len(rows)}
    if fmt == "csv":
        flat = [_flat(r) for r in rows]
        cols: list[str] = []
        for r in flat:
            cols += [k for k in r if k not in cols]
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=cols)
        writer.writeheader()
        writer.writerows(flat)
        out["content"] = buf.getvalue()
    else:
        out["rows"] = rows
    return out
