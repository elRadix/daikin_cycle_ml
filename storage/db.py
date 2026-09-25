"""SQLite persistence for Daikin Cycle ML (Batch 6a). Pure Python."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

import aiosqlite

_LOGGER = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class CycleDB:
    """Thin async wrapper around aiosqlite with schema bootstrap."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._conn: aiosqlite.Connection | None = None

    @property
    def path(self) -> str:
        return self._path

    @property
    def is_open(self) -> bool:
        return self._conn is not None

    def _require(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("CycleDB not opened — call async_open() first")
        return self._conn

    async def async_open(self) -> None:
        if self._conn is not None:
            return
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys=ON")

    async def async_initialize(self) -> None:
        if self._conn is None:
            await self.async_open()
        conn = self._require()
        # Read schema off the event loop (HA blocking-I/O check).
        schema = await asyncio.to_thread(_SCHEMA_PATH.read_text)
        await conn.executescript(schema)
        await conn.commit()

    async def async_close(self) -> None:
        if self._conn is None:
            return
        await self._conn.close()
        self._conn = None

    async def async_insert_cycle(self, record: dict[str, Any]) -> int | None:
        conn = self._require()
        cur = await conn.execute(
            """INSERT OR IGNORE INTO cycles
               (start_ts, end_ts, duration_s, mode, dT_max, dT_avg,
                rps_max, rps_avg, outdoor_temp, buh_used, defrost_used,
                quality_score, label)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                record.get("start_ts"),
                record.get("end_ts"),
                record.get("duration_s"),
                record.get("mode"),
                record.get("dT_max"),
                record.get("dT_avg"),
                record.get("rps_max"),
                record.get("rps_avg"),
                record.get("outdoor_temp"),
                int(bool(record.get("buh_used", 0))),
                int(bool(record.get("defrost_used", 0))),
                record.get("quality_score"),
                record.get("label"),
            ),
        )
        try:
            await conn.commit()
            rowcount = cur.rowcount
            lastrowid = cur.lastrowid
        finally:
            await cur.close()
        if rowcount == 0:
            return None
        return int(lastrowid) if lastrowid else None

    async def async_insert_features(
        self, cycle_id: int, vector: list[float]
    ) -> None:
        conn = self._require()
        await conn.execute(
            "INSERT OR REPLACE INTO features (cycle_id, vector_json) VALUES (?,?)",
            (int(cycle_id), json.dumps(list(vector))),
        )
        await conn.commit()

    async def async_set_model_state(self, key: str, value: Any) -> None:
        conn = self._require()
        await conn.execute(
            """INSERT OR REPLACE INTO model_state
               (key, value_json, updated_ts) VALUES (?,?,?)""",
            (key, json.dumps(value), time.time()),
        )
        await conn.commit()

    async def async_get_model_state(self, key: str, default: Any = None) -> Any:
        conn = self._require()
        async with conn.execute(
            "SELECT value_json FROM model_state WHERE key=?", (key,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return default
        try:
            return json.loads(row[0])
        except (TypeError, ValueError):
            return default

    async def async_insert_alert(
        self,
        alert_type: str,
        severity: str,
        message: str,
        *,
        ts: float | None = None,
    ) -> int | None:
        conn = self._require()
        ts_val = float(ts) if ts is not None else time.time()
        cur = await conn.execute(
            """INSERT OR IGNORE INTO alerts
               (ts, alert_type, severity, message, aggregated_count)
               VALUES (?,?,?,?,1)""",
            (ts_val, alert_type, severity, message),
        )
        try:
            await conn.commit()
            rowcount = cur.rowcount
            lastrowid = cur.lastrowid
        finally:
            await cur.close()
        if rowcount == 0:
            return None
        return int(lastrowid) if lastrowid else None

    async def async_fetch_cycles(self, days: int = 30) -> list[dict[str, Any]]:
        conn = self._require()
        cutoff = time.time() - float(days) * 86400.0
        async with conn.execute(
            "SELECT * FROM cycles WHERE start_ts >= ? ORDER BY start_ts ASC",
            (cutoff,),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def async_label_cycle(self, cycle_id: int, label: str) -> bool:
        conn = self._require()
        cur = await conn.execute(
            "UPDATE cycles SET label=? WHERE id=?", (label, int(cycle_id))
        )
        try:
            await conn.commit()
            rowcount = cur.rowcount
        finally:
            await cur.close()
        return rowcount > 0

    # ---------- Batch 11b-1: retention + rollup ----------

    async def async_run_maintenance(
        self,
        *,
        cycle_retention_days: int = 90,
        alert_retention_days: int = 30,
        cop_retention_days: int = 365,
        vacuum: bool = True,
    ) -> dict[str, int]:
        """Aggregate old cycles, prune, optionally vacuum. Atomic rollup+prune."""
        conn = self._require()
        cutoff = time.time() - float(cycle_retention_days) * 86400.0
        alert_cutoff = time.time() - float(alert_retention_days) * 86400.0

        # 1. Read cycles that will be rolled up + pruned
        async with conn.execute(
            "SELECT start_ts, end_ts, duration_s, mode, dT_max, rps_avg, "
            "quality_score, buh_used, defrost_used FROM cycles "
            "WHERE end_ts IS NOT NULL AND end_ts < ? "
            "ORDER BY end_ts ASC",
            (cutoff,),
        ) as cur:
            rows = await cur.fetchall()

        # 2. Aggregate in Python (local time matches daily_reset_if_needed)
        agg: dict[tuple[str, str], dict[str, float]] = {}
        for r in rows:
            end_ts = r["end_ts"]
            if not isinstance(end_ts, (int, float)):
                continue  # pragma: no cover
            day = time.strftime("%Y-%m-%d", time.localtime(float(end_ts)))
            mode = r["mode"] or "unknown"
            key = (day, mode)
            a = agg.get(key)
            if a is None:
                a = {
                    "cycles": 0,
                    "total_duration_s": 0,
                    "duration_min": None,
                    "duration_max": None,
                    "quality_sum": 0,
                    "dt_max_sum": 0.0,
                    "rps_sum": 0.0,
                    "buh_count": 0,
                    "defrost_count": 0,
                }
                agg[key] = a
            a["cycles"] += 1
            dur = r["duration_s"]
            if isinstance(dur, (int, float)):
                a["total_duration_s"] += int(dur)
                if a["duration_min"] is None or dur < a["duration_min"]:
                    a["duration_min"] = int(dur)
                if a["duration_max"] is None or dur > a["duration_max"]:
                    a["duration_max"] = int(dur)
            q = r["quality_score"]
            if isinstance(q, (int, float)):
                a["quality_sum"] += int(q)
            dt = r["dT_max"]
            if isinstance(dt, (int, float)):
                a["dt_max_sum"] += float(dt)
            rps = r["rps_avg"]
            if isinstance(rps, (int, float)):
                a["rps_sum"] += float(rps)
            if r["buh_used"]:
                a["buh_count"] += 1
            if r["defrost_used"]:
                a["defrost_count"] += 1

        # 3. Upsert aggregates
        now = time.time()
        for (day, mode), a in agg.items():
            await conn.execute(
                """INSERT INTO daily_summary
                   (day, mode, cycles, total_duration_s, duration_min,
                    duration_max, quality_sum, dt_max_sum, rps_sum,
                    buh_count, defrost_count, updated_ts)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(day, mode) DO UPDATE SET
                     cycles = cycles + excluded.cycles,
                     total_duration_s = total_duration_s
                       + excluded.total_duration_s,
                     duration_min = MIN(duration_min, excluded.duration_min),
                     duration_max = MAX(duration_max, excluded.duration_max),
                     quality_sum = quality_sum + excluded.quality_sum,
                     dt_max_sum = dt_max_sum + excluded.dt_max_sum,
                     rps_sum = rps_sum + excluded.rps_sum,
                     buh_count = buh_count + excluded.buh_count,
                     defrost_count = defrost_count + excluded.defrost_count,
                     updated_ts = excluded.updated_ts""",
                (
                    day, mode,
                    a["cycles"], a["total_duration_s"],
                    a["duration_min"], a["duration_max"],
                    a["quality_sum"], a["dt_max_sum"], a["rps_sum"],
                    a["buh_count"], a["defrost_count"], now,
                ),
            )

        # 4. Prune (features first: FK from features.cycle_id to cycles.id)
        cur = await conn.execute(
            "DELETE FROM features WHERE cycle_id IN "
            "(SELECT id FROM cycles WHERE end_ts IS NOT NULL "
            "AND end_ts < ?)",
            (cutoff,),
        )
        features_deleted = cur.rowcount or 0
        await cur.close()

        cur = await conn.execute(
            "DELETE FROM cycles WHERE end_ts IS NOT NULL AND end_ts < ?",
            (cutoff,),
        )
        cycles_deleted = cur.rowcount or 0
        await cur.close()

        # Defensive: catch manually-removed cycle rows
        cur = await conn.execute(
            "DELETE FROM features WHERE cycle_id NOT IN "
            "(SELECT id FROM cycles)"
        )
        features_deleted += cur.rowcount or 0
        await cur.close()

        cur = await conn.execute(
            "DELETE FROM alerts WHERE ts < ?", (alert_cutoff,)
        )
        alerts_deleted = cur.rowcount or 0
        await cur.close()

        cop_cutoff = time.time() - float(cop_retention_days) * 86400.0
        cop_deleted = 0
        try:
            await self.async_ensure_cop_samples_table()
            cur = await conn.execute(
                "DELETE FROM cop_samples WHERE ts < ?", (cop_cutoff,)
            )
            cop_deleted = cur.rowcount or 0
            await cur.close()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("cop_samples prune failed")

        await conn.commit()

        # 5. VACUUM outside any transaction
        if vacuum:
            await self.async_vacuum()

        return {
            "days_rolled_up": len(agg),
            "cycles_rolled_up": len(rows),
            "cycles_deleted": cycles_deleted,
            "features_deleted": features_deleted,
            "alerts_deleted": alerts_deleted,
            "cop_deleted": cop_deleted,
        }

    async def async_vacuum(self) -> bool:
        """Best-effort VACUUM via a fresh connection.

        VACUUM cannot run inside a transaction. Manipulating the
        main connection isolation_level corrupts aiosqlite state,
        so we open a short-lived autocommit connection instead.
        """
        if self._conn is None:
            return False
        try:
            async with aiosqlite.connect(
                self._path, isolation_level=None
            ) as vac:
                await vac.execute("VACUUM")
            return True
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("VACUUM skipped (best-effort): %s", err)
            return False

    async def async_daily_summary(
        self, days: int = 30, mode: str | None = None
    ) -> list[dict[str, Any]]:
        conn = self._require()
        cutoff_day = time.strftime(
            "%Y-%m-%d",
            time.localtime(time.time() - float(days) * 86400.0),
        )
        if mode:
            sql = (
                "SELECT * FROM daily_summary WHERE day >= ? AND mode = ? "
                "ORDER BY day ASC"
            )
            params = (cutoff_day, mode)
        else:
            sql = (
                "SELECT * FROM daily_summary WHERE day >= ? "
                "ORDER BY day ASC, mode ASC"
            )
            params = (cutoff_day,)
        async with conn.execute(sql, params) as cur:
            rows = await cur.fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            n = d.get("cycles") or 0
            if n > 0:
                d["duration_avg"] = round(
                    d["total_duration_s"] / n, 2
                )
                d["quality_avg"] = round(d["quality_sum"] / n, 2)
                d["dt_max_avg"] = round(d["dt_max_sum"] / n, 3)
                d["rps_avg"] = round(d["rps_sum"] / n, 3)
            else:
                d["duration_avg"] = None
                d["quality_avg"] = None
                d["dt_max_avg"] = None
                d["rps_avg"] = None
            out.append(d)
        return out

    async def async_update_cycle_cluster(  # pragma: no cover
        self, cycle_id: int, cluster_id: int
    ) -> bool:
        """Update cluster_id for a cycle. Lazy-migrates schema if needed."""
        import aiosqlite
        path = getattr(self, "path", None)
        if path is None:
            return False
        try:
            async with aiosqlite.connect(path) as conn:
                try:
                    await conn.execute(
                        "UPDATE cycles SET cluster_id = ? WHERE id = ?",
                        (int(cluster_id), int(cycle_id)),
                    )
                except Exception:  # noqa: BLE001
                    # column missing -> migrate then retry
                    await conn.execute(
                        "ALTER TABLE cycles ADD COLUMN cluster_id INTEGER"
                    )
                    await conn.execute(
                        "UPDATE cycles SET cluster_id = ? WHERE id = ?",
                        (int(cluster_id), int(cycle_id)),
                    )
                await conn.commit()
            return True
        except Exception:  # noqa: BLE001
            _LOGGER.debug("update_cycle_cluster failed", exc_info=True)
            return False

    async def async_count_by_cluster(self) -> dict[int, int]:  # pragma: no cover
        """Return {cluster_id: count} for cycles with cluster assigned."""
        import aiosqlite
        path = getattr(self, "path", None)
        if path is None:
            return {}
        try:
            async with aiosqlite.connect(path) as conn:
                cur = await conn.execute(
                    "SELECT cluster_id, COUNT(*) FROM cycles "
                    "WHERE cluster_id IS NOT NULL GROUP BY cluster_id"
                )
                rows = await cur.fetchall()
                return {int(r[0]): int(r[1]) for r in rows}
        except Exception:  # noqa: BLE001
            return {}

    async def async_ensure_cluster_column(self) -> bool:  # pragma: no cover
        """Ensure cycles.cluster_id exists (idempotent migration)."""
        import aiosqlite
        path = getattr(self, "path", None)
        if path is None:
            return False
        try:
            async with aiosqlite.connect(path) as conn:
                cur = await conn.execute("PRAGMA table_info(cycles)")
                rows = await cur.fetchall()
                cols = {r[1] for r in rows}
                if "cluster_id" in cols:
                    return False
                await conn.execute(
                    "ALTER TABLE cycles ADD COLUMN cluster_id INTEGER"
                )
                await conn.commit()
                return True
        except Exception:  # noqa: BLE001
            return False

    async def async_count(self, table: str = "cycles") -> int:
        conn = self._require()
        allowed = (
            "cycles", "features", "model_state", "alerts",
            "daily_summary", "cop_samples",
        )
        if table not in allowed:
            raise ValueError(f"unknown table: {table}")
        async with conn.execute(f"SELECT COUNT(*) FROM {table}") as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def async_ensure_cop_samples_table(self) -> None:
        conn = self._require()
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS cop_samples ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "ts REAL NOT NULL,"
            "cop REAL NOT NULL,"
            "lwt REAL,"
            "outdoor REAL,"
            "flow_lmin REAL,"
            "power_stable INTEGER DEFAULT 0)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cop_samples_ts "
            "ON cop_samples(ts)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cop_samples_outdoor "
            "ON cop_samples(outdoor)"
        )
        await conn.commit()

    async def async_insert_cop_sample(
        self, sample: dict[str, Any]
    ) -> bool:
        try:
            await self.async_ensure_cop_samples_table()
            conn = self._require()
            await conn.execute(
                "INSERT INTO cop_samples "
                "(ts, cop, lwt, outdoor, flow_lmin, power_stable) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    float(sample["ts"]),
                    float(sample["cop"]),
                    sample.get("lwt"),
                    sample.get("outdoor"),
                    sample.get("flow_lmin"),
                    1 if sample.get("power_stable") else 0,
                ),
            )
            await conn.commit()
            return True
        except Exception:  # noqa: BLE001
            _LOGGER.exception("cop_sample insert failed")
            return False

    async def async_fetch_cop_samples(
        self, days: int = 30
    ) -> list[dict[str, Any]]:
        await self.async_ensure_cop_samples_table()
        conn = self._require()
        cutoff = time.time() - float(days) * 86400.0
        async with conn.execute(
            "SELECT ts, cop, lwt, outdoor, flow_lmin, power_stable "
            "FROM cop_samples WHERE ts >= ? ORDER BY ts ASC",
            (cutoff,),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]


    async def async_fetch_cop_samples_between(
        self, start_ts: float, end_ts: float
    ) -> list[dict[str, Any]]:
        """Return cop_samples with start_ts <= ts <= end_ts."""
        await self.async_ensure_cop_samples_table()
        conn = self._require()
        async with conn.execute(
            "SELECT ts, cop, lwt, outdoor, flow_lmin, power_stable "
            "FROM cop_samples WHERE ts >= ? AND ts <= ? "
            "ORDER BY ts ASC",
            (float(start_ts), float(end_ts)),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def async_avg_cop_between(
        self, start_ts: float, end_ts: float
    ) -> float | None:
        """Return mean cop over [start_ts, end_ts], or None if empty."""
        rows = await self.async_fetch_cop_samples_between(start_ts, end_ts)
        cops = [r.get("cop") for r in rows if isinstance(r.get("cop"), (int, float))]
        if not cops:
            return None
        return sum(cops) / float(len(cops))

    async def async_count_cop_samples(self) -> int:
        await self.async_ensure_cop_samples_table()
        conn = self._require()
        async with conn.execute(
            "SELECT COUNT(*) FROM cop_samples"
        ) as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0
