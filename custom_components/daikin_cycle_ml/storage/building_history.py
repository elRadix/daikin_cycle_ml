"""#495 PR 2: rebuild the building's day values for days before PR 1.

Days recorded before the live accumulator (``engine/building_day.py``)
have no room temperature and no signed space heat. They are rebuilt once
from history the integration already keeps:

- **space heat** from ``cop_samples``: flow x (R1T - R4T) of each heating
  sample (no boiler), weighted by the time to the next sample, capped at
  ``SAMPLE_CAP_S``. Samples are only written while the compressor runs, so
  the coverage is the measured share of the day and defrosts are missing:
  the heat-loss engine treats these days as ``reconstructed``;
- **room temperature** from each run's ``indoor_temp_avg`` (cycle features,
  the configured room sensor), spread over every day the run overlaps and
  weighted by the overlap.

The fields are merged into the existing ``daily_stats`` "all" rows (also
finalised ones: they never had these values) with ``building_reconstructed``
set. Days that already have live values are left alone.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from typing import Any

from ..engine.building_day import INDOOR_RANGE, MAX_FLOW_LMIN, MAX_WATER_DT_K
from ..engine.thermal import _flow_dt_kw
from ..ml.features import FEATURE_NAMES
from .reports import _local_day, day_length_s, day_start_ts

SAMPLE_CAP_S = 900.0
_I_INDOOR = FEATURE_NAMES.index("indoor_temp_avg")


async def _space_heat(conn: Any) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = defaultdict(lambda: {"kwh": 0.0, "s": 0.0})
    async with conn.execute(
        "SELECT ts, mode, boiler_active, flow_lmin, r1t, r4t FROM cop_samples ORDER BY ts"
    ) as cur:
        rows = await cur.fetchall()
    for i, r in enumerate(rows):
        if r["mode"] != "heating" or r["boiler_active"]:
            continue
        flow, lwt, rwt = r["flow_lmin"], r["r1t"], r["r4t"]
        if flow is None or lwt is None or rwt is None or not 0 < flow <= MAX_FLOW_LMIN:
            continue
        if abs(lwt - rwt) > MAX_WATER_DT_K:
            continue
        nxt = rows[i + 1]["ts"] if i + 1 < len(rows) else r["ts"] + SAMPLE_CAP_S
        dt_s = min(max(0.0, float(nxt) - float(r["ts"])), SAMPLE_CAP_S)
        d = out[_local_day(float(r["ts"]))]
        d["kwh"] += _flow_dt_kw(float(flow), float(lwt) - float(rwt)) * dt_s / 3600.0
        d["s"] += dt_s
    return out


async def _room(conn: Any) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = defaultdict(lambda: {"sum": 0.0, "s": 0.0})
    async with conn.execute(
        "SELECT c.start_ts, c.end_ts, f.vector_json FROM cycles c "
        "JOIN features f ON f.cycle_id = c.id WHERE c.end_ts IS NOT NULL"
    ) as cur:
        rows = await cur.fetchall()
    for r in rows:
        try:
            vec = json.loads(r["vector_json"])
            t_in = float(vec[_I_INDOOR])
        except (TypeError, ValueError, IndexError):
            continue
        if not INDOOR_RANGE[0] < t_in <= INDOOR_RANGE[1]:  # 0.0 = no room sensor
            continue
        t0, t1 = float(r["start_ts"]), float(r["end_ts"])
        while t0 < t1:  # spread the run over the days it covers
            day = _local_day(t0)
            end = min(t1, day_start_ts(day) + day_length_s(day))
            if end <= t0:  # pragma: no cover - guard against a clock edge
                break
            out[day]["sum"] += t_in * (end - t0)
            out[day]["s"] += end - t0
            t0 = end
    return out


async def rebuild(conn: Any) -> dict[str, int]:
    """Merge rebuilt fields into the "all" day rows that have none yet."""
    heat, room = await _space_heat(conn), await _room(conn)
    async with conn.execute("SELECT day, data_json FROM daily_stats WHERE mode = 'all'") as cur:
        rows = await cur.fetchall()
    updates: list[tuple[str, float, str]] = []
    for r in rows:
        data = json.loads(r["data_json"])
        if data.get("indoor_s") or data.get("heat_sh_s"):
            continue  # live values from the accumulator
        day = r["day"]
        h, t = heat.get(day), room.get(day)
        if not h and not t:
            continue
        data.update({
            "indoor_mean": round(t["sum"] / t["s"], 2) if t else None,
            "indoor_source": "cycles" if t else None,
            "indoor_s": int(t["s"]) if t else 0,
            "indoor_drift": None,
            "heat_sh_signed_kwh": round(h["kwh"], 3) if h else None,
            "heat_sh_s": int(h["s"]) if h else 0,
            "building_reconstructed": True,
        })
        updates.append((json.dumps(data, separators=(",", ":")), time.time(), day))
    await conn.executemany(
        "UPDATE daily_stats SET data_json = ?, updated_ts = ? WHERE day = ? AND mode = 'all'", updates
    )
    await conn.commit()
    return {"days": len(updates), "heat_days": len(heat), "room_days": len(room)}
