"""SQLite persistence for Daikin Cycle ML (Batch 6a). Pure Python."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

import aiosqlite

from ..ml.features import VECTOR_LEN

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


    async def async_fetch_recent_cycles_for_hydration(
        self, limit: int = 500,
    ) -> list[dict[str, Any]]:
        # v1.4.2: newest cycles, chronological.
        conn = self._require()
        cur = await conn.execute(
            "SELECT start_ts, end_ts, duration_s, mode, dT_max, dT_avg, "
            "rps_max, rps_avg, outdoor_temp, buh_used, defrost_used, "
            "quality_score, label, cluster_id, cop_avg, "
            "cop_sample_count, cop_sample_stdev, cop_confidence "
            "FROM cycles ORDER BY start_ts DESC LIMIT ?",
            (limit,),
        )
        raw = await cur.fetchall()
        await cur.close()
        raw_list = list(raw)
        cols = (
            "start_ts", "end_ts", "duration_s", "mode", "dT_max",
            "dT_avg", "rps_max", "rps_avg", "outdoor_temp",
            "buh_used", "defrost_used", "quality_score", "label",
            "cluster_id", "cop_avg", "cop_sample_count",
            "cop_sample_stdev", "cop_confidence",
        )
        return [dict(zip(cols, r)) for r in reversed(raw_list)]

    async def async_backfill_quality_scores(self, scorer: Any) -> int:
        # v1.4.2: backfill NULL quality_score.
        conn = self._require()
        cur = await conn.execute(
            "SELECT id, start_ts, end_ts, duration_s, mode, dT_max, "
            "dT_avg, rps_max, rps_avg, outdoor_temp, buh_used, "
            "defrost_used FROM cycles WHERE quality_score IS NULL"
        )
        rows = await cur.fetchall()
        await cur.close()
        if not rows:
            return 0
        cols = (
            "id", "start_ts", "end_ts", "duration_s", "mode",
            "dT_max", "dT_avg", "rps_max", "rps_avg", "outdoor_temp",
            "buh_used", "defrost_used",
        )
        updates = 0
        for r in rows:
            rec = dict(zip(cols, r))
            try:
                score = scorer(rec)
            except Exception:
                _LOGGER.debug("scorer failed", exc_info=True)
                continue
            if isinstance(score, bool) or not isinstance(score, int):
                continue
            cur2 = await conn.execute(
                "UPDATE cycles SET quality_score = ? WHERE id = ?",
                (score, rec["id"]),
            )
            await cur2.close()
            updates += 1
        if updates:
            await conn.commit()
        return updates

    async def async_prune_cop_hourly(
        self, retention_days: int = 365,
    ) -> int:
        # v1.4.2: prune cop_hourly older than retention_days.
        conn = self._require()
        cutoff = int(time.time() - float(retention_days) * 86400.0)
        cur = await conn.execute(
            "DELETE FROM cop_hourly WHERE ts_hour < ?",
            (cutoff,),
        )
        try:
            deleted = int(cur.rowcount or 0)
        finally:
            await cur.close()
        await conn.commit()
        return deleted

    async def async_insert_cycle(self, record: dict[str, Any]) -> int | None:
        conn = self._require()
        cur = await conn.execute(
            """INSERT OR IGNORE INTO cycles
               (start_ts, end_ts, duration_s, mode, dT_max, dT_avg,
                rps_max, rps_avg, outdoor_temp, buh_used, defrost_used,
                quality_score, label,
                cop_avg, cop_sample_count, cop_sample_stdev, cop_confidence)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                record.get("cop_avg"),
                record.get("cop_sample_count"),
                record.get("cop_sample_stdev"),
                record.get("cop_confidence"),
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


    async def async_migrate_features_to_v12(self) -> int:
        """Add v11 column if absent and backfill 0.0. Idempotent."""
        conn = self._require()
        cur = await conn.execute("PRAGMA table_info(features)")
        cols = {row[1] for row in await cur.fetchall()}
        await cur.close()
        if "v11" not in cols:
            await conn.execute(
                "ALTER TABLE features ADD COLUMN v11 REAL DEFAULT 0.0"
            )
        await conn.execute("UPDATE features SET v11 = 0.0 WHERE v11 IS NULL")
        await conn.commit()
        return 0

    async def async_migrate_cop_samples_to_v13(self) -> int:
        """Add mode column to cop_samples if absent. Idempotent."""
        conn = self._require()
        cur = await conn.execute("PRAGMA table_info(cop_samples)")
        cols = {row[1] for row in await cur.fetchall()}
        await cur.close()
        if "mode" not in cols:
            await conn.execute(
                "ALTER TABLE cop_samples ADD COLUMN mode TEXT DEFAULT NULL"
            )
            await conn.commit()
        return 0

    async def async_integrity_check(self) -> bool:
        """Run PRAGMA integrity_check + foreign_key_check. True if healthy."""
        try:
            conn = self._require()
            cur = await conn.execute("PRAGMA integrity_check")
            rows = list(await cur.fetchall())
            await cur.close()
            if not rows or rows[0][0] != "ok":
                return False
            cur = await conn.execute("PRAGMA foreign_key_check")
            fk_rows = list(await cur.fetchall())
            await cur.close()
            return len(fk_rows) == 0
        except Exception:
            _LOGGER.warning("integrity_check failed", exc_info=True)
            return False

    async def async_migrate_features_to_v11(self) -> int:
        """Pad 8-dim feature vectors with [0.0, 0.0, 0.0]. Idempotent."""
        conn = self._require()
        async with conn.execute(
            "SELECT cycle_id, vector_json FROM features"
        ) as cur:
            rows = await cur.fetchall()
        changed = 0
        for row in rows:
            cycle_id = int(row[0])
            try:
                vec = json.loads(row[1])
            except (TypeError, ValueError):
                continue
            if not isinstance(vec, list) or len(vec) != 8:
                continue
            padded = list(vec) + [0.0] * (VECTOR_LEN - len(vec))
            await conn.execute(
                "UPDATE features SET vector_json=? WHERE cycle_id=?",
                (json.dumps(padded), cycle_id),
            )
            changed += 1
        if changed:
            await conn.commit()
        return changed

    async def async_migrate_cycles_to_v14(self) -> int:
        """Add cop_avg/cop_sample_count/cop_sample_stdev/cop_confidence to cycles."""
        conn = self._require()
        async with conn.execute("PRAGMA table_info(cycles)") as cur:
            rows = await cur.fetchall()
        existing = {r[1] for r in rows}
        added = 0
        for name, decl in (
            ("cop_avg", "REAL"),
            ("cop_sample_count", "INTEGER"),
            ("cop_sample_stdev", "REAL"),
            ("cop_confidence", "TEXT"),
        ):
            if name in existing:
                continue
            await conn.execute(
                f"ALTER TABLE cycles ADD COLUMN {name} {decl}"
            )
            added += 1
        if added:
            await conn.commit()
        return added

    async def async_migrate_cop_samples_source_v14(self) -> bool:
        """Add source column to cop_samples (interval / tick / cycle_close)."""
        conn = self._require()
        async with conn.execute("PRAGMA table_info(cop_samples)") as cur:
            rows = await cur.fetchall()
        existing = {r[1] for r in rows}
        if "source" in existing:
            return True
        await conn.execute(
            "ALTER TABLE cop_samples ADD COLUMN source TEXT DEFAULT 'interval'"
        )
        await conn.commit()
        return True

    async def async_create_cop_hourly_v14(self) -> bool:
        """Create cop_hourly rollup table for long-horizon stooklijn (T3)."""
        conn = self._require()
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cop_hourly (
                ts_hour INTEGER NOT NULL,
                mode TEXT NOT NULL,
                n_samples INTEGER NOT NULL,
                cop_mean REAL,
                cop_p10 REAL,
                cop_p50 REAL,
                cop_p90 REAL,
                cop_std REAL,
                lwt_mean REAL,
                outdoor_mean REAL,
                outdoor_min REAL,
                outdoor_max REAL,
                flow_mean REAL,
                updated_ts REAL NOT NULL,
                PRIMARY KEY (ts_hour, mode)
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cop_hourly_ts ON cop_hourly(ts_hour)"
        )
        await conn.commit()
        return True

    async def async_migrate_to_v14(self) -> tuple[int, bool, bool]:
        """Orchestrate v14. Returns (cycles_cols_added, source_ok, hourly_ok)."""
        cycles_added = await self.async_migrate_cycles_to_v14()
        source_ok = await self.async_migrate_cop_samples_source_v14()
        hourly_ok = await self.async_create_cop_hourly_v14()
        return cycles_added, source_ok, hourly_ok

    async def async_migrate_cop_samples_mode_default_v15(self) -> int:
        # v1.6.5 R298: NULL mode -> 'unknown'. Idempotent.
        await self.async_ensure_cop_samples_table()
        conn = self._require()
        cur = await conn.execute(
            "UPDATE cop_samples SET mode = 'unknown' WHERE mode IS NULL"
        )
        try:
            updated = int(cur.rowcount or 0)
        finally:
            await cur.close()
        await conn.commit()
        return updated

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
            rowcount = int(cur.rowcount)
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
            a: dict[str, Any] | None = agg.get(key)
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
        except Exception:
            _LOGGER.exception("cop_samples prune failed")

        try:
            await self.async_prune_cop_hourly(
                retention_days=int(cop_retention_days),
            )
        except Exception:
            _LOGGER.exception("cop_hourly prune failed")

        await conn.commit()

        # 5. VACUUM outside any transaction
        if vacuum:
            await self.async_vacuum()

        return {
            "days_rolled_up": len(agg),
            "cycles_rolled_up": len(list(rows)),
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
        except Exception as err:
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
            params: tuple[Any, ...] = (cutoff_day, mode)
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
                except Exception:
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
        except Exception:
            _LOGGER.warning("update_cycle_cluster failed", exc_info=True)
            return False

    async def async_count_by_cluster(self) -> dict[int, int]:  # pragma: no cover
        """Return {cluster_id: count} for cycles with cluster assigned."""
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
        except Exception:
            return {}

    async def async_ensure_cluster_column(self) -> bool:  # pragma: no cover
        """Ensure cycles.cluster_id exists (idempotent migration)."""
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
        except Exception:
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

    @staticmethod
    def _percentile(sorted_values: list[float], q: float) -> float:
        """Linear-interpolation percentile. q in [0,1]."""
        if not sorted_values:  # pragma: no cover - callers pass n>=1
            return 0.0
        n = len(sorted_values)
        if n == 1:
            return sorted_values[0]
        idx = q * (n - 1)
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        frac = idx - lo
        return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac

    @staticmethod
    def _std(values: list[float], mean: float) -> float:
        """Population std. n<2 -> 0.0."""
        if len(values) < 2:
            return 0.0
        var = sum((v - mean) ** 2 for v in values) / len(values)
        return float(var ** 0.5)

    @staticmethod
    def _mean_or_none(values: list[float]) -> float | None:
        if not values:
            return None
        return sum(values) / len(values)

    async def async_rollup_cop_hourly(self, window_hours: int = 6) -> int:
        """Roll up cop_samples into cop_hourly. Idempotent UPSERT."""
        await self.async_ensure_cop_samples_table()
        await self.async_create_cop_hourly_v14()
        conn = self._require()
        now = time.time()
        cutoff = now - float(window_hours) * 3600.0

        async with conn.execute(
            "SELECT ts, cop, lwt, outdoor, flow_lmin, mode "
            "FROM cop_samples WHERE ts >= ?",
            (cutoff,),
        ) as cur:
            rows = await cur.fetchall()

        if not rows:
            return 0

        buckets: dict[tuple[int, str], list[Any]] = {}
        for r in rows:
            ts_hour = int(float(r["ts"]) // 3600)
            mode = r["mode"] or "unknown"
            buckets.setdefault((ts_hour, mode), []).append(r)

        upserted = 0
        for (ts_hour, mode), samples in buckets.items():
            cops = sorted(float(s["cop"]) for s in samples)
            n = len(cops)
            mean = sum(cops) / n
            lwts = [
                float(s["lwt"]) for s in samples if s["lwt"] is not None
            ]
            outdoors = [
                float(s["outdoor"]) for s in samples
                if s["outdoor"] is not None
            ]
            flows = [
                float(s["flow_lmin"]) for s in samples
                if s["flow_lmin"] is not None
            ]
            await conn.execute(
                "INSERT INTO cop_hourly ("
                "ts_hour, mode, n_samples, cop_mean, cop_p10, cop_p50, "
                "cop_p90, cop_std, lwt_mean, outdoor_mean, outdoor_min, "
                "outdoor_max, flow_mean, updated_ts) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(ts_hour, mode) DO UPDATE SET "
                "n_samples=excluded.n_samples, "
                "cop_mean=excluded.cop_mean, "
                "cop_p10=excluded.cop_p10, "
                "cop_p50=excluded.cop_p50, "
                "cop_p90=excluded.cop_p90, "
                "cop_std=excluded.cop_std, "
                "lwt_mean=excluded.lwt_mean, "
                "outdoor_mean=excluded.outdoor_mean, "
                "outdoor_min=excluded.outdoor_min, "
                "outdoor_max=excluded.outdoor_max, "
                "flow_mean=excluded.flow_mean, "
                "updated_ts=excluded.updated_ts",
                (
                    ts_hour,
                    mode,
                    n,
                    mean,
                    self._percentile(cops, 0.10),
                    self._percentile(cops, 0.50),
                    self._percentile(cops, 0.90),
                    self._std(cops, mean),
                    self._mean_or_none(lwts),
                    self._mean_or_none(outdoors),
                    min(outdoors) if outdoors else None,
                    max(outdoors) if outdoors else None,
                    self._mean_or_none(flows),
                    now,
                ),
            )
            upserted += 1
        await conn.commit()
        return upserted

    async def async_insert_cop_sample(
        self, sample: dict[str, Any]
    ) -> bool:
        try:
            await self.async_ensure_cop_samples_table()
            conn = self._require()
            await conn.execute(
                "INSERT INTO cop_samples "
                "(ts, cop, lwt, outdoor, flow_lmin, power_stable, mode, source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    float(sample["ts"]),
                    float(sample["cop"]),
                    sample.get("lwt"),
                    sample.get("outdoor"),
                    sample.get("flow_lmin"),
                    1 if sample.get("power_stable") else 0,
                    sample.get("mode") or "unknown",
                    sample.get("source", "interval"),
                ),
            )
            await conn.commit()
            return True
        except Exception:
            _LOGGER.exception("cop_sample insert failed")
            return False

    async def async_fetch_cop_samples(
        self, days: int = 30
    ) -> list[dict[str, Any]]:
        await self.async_ensure_cop_samples_table()
        conn = self._require()
        cutoff = time.time() - float(days) * 86400.0
        async with conn.execute(
            "SELECT ts, cop, lwt, outdoor, flow_lmin, power_stable, mode "
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
        cops: list[float] = []
        for r in rows:
            c = r.get("cop")
            if isinstance(c, (int, float)):
                cops.append(float(c))
        if not cops:
            return None
        return sum(cops) / float(len(cops))

    async def async_query_cop_hourly(
        self, *, since_ts: float, until_ts: float | None = None,
        mode: str | None = None, limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Query cop_hourly rows in [since_ts, until_ts] window."""
        await self.async_create_cop_hourly_v14()
        conn = self._require()
        sql = (
            "SELECT ts_hour, mode, n_samples, cop_mean, cop_p10, "
            "cop_p50, cop_p90, cop_std, lwt_mean, outdoor_mean, "
            "outdoor_min, outdoor_max, flow_mean, updated_ts "
            "FROM cop_hourly WHERE ts_hour >= ?"
        )
        params: list[Any] = [int(since_ts) // 3600]
        if until_ts is not None:
            sql += " AND ts_hour <= ?"
            params.append(int(until_ts) // 3600)
        if mode is not None:
            sql += " AND mode = ?"
            params.append(mode)
        sql += " ORDER BY ts_hour ASC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        async with conn.execute(sql, tuple(params)) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def async_cop_hourly_stats(
        self, *, since_ts: float, mode: str | None = None,
    ) -> dict[str, Any]:
        """Bucket-weighted aggregate stats over window."""
        rows = await self.async_query_cop_hourly(
            since_ts=since_ts, mode=mode
        )
        n_hours = len(rows)
        if n_hours == 0:
            return {
                "n_hours": 0, "n_samples": 0,
                "cop_mean": None, "cop_p10": None, "cop_p90": None,
                "cop_min": None, "cop_max": None,
            }
        n_samples = sum(int(r["n_samples"]) for r in rows)
        weighted_sum = 0.0
        for r in rows:
            weighted_sum += float(r["cop_mean"]) * int(r["n_samples"])
        cop_mean = weighted_sum / float(n_samples)
        p10_values = [float(r["cop_p10"]) for r in rows]
        p90_values = [float(r["cop_p90"]) for r in rows]
        means = [float(r["cop_mean"]) for r in rows]
        return {
            "n_hours": n_hours,
            "n_samples": n_samples,
            "cop_mean": cop_mean,
            "cop_p10": min(p10_values),
            "cop_p90": max(p90_values),
            "cop_min": min(means),
            "cop_max": max(means),
        }

    async def async_cop_hourly_by_mode(
        self, *, since_ts: float,
    ) -> dict[str, dict[str, Any]]:
        """Per-mode stats dict over window."""
        rows = await self.async_query_cop_hourly(since_ts=since_ts)
        modes = sorted({r["mode"] for r in rows})
        out: dict[str, dict[str, Any]] = {}
        for m in modes:
            out[m] = await self.async_cop_hourly_stats(
                since_ts=since_ts, mode=m
            )
        return out

    async def async_count_cop_samples(self) -> int:
        await self.async_ensure_cop_samples_table()
        conn = self._require()
        async with conn.execute(
            "SELECT COUNT(*) FROM cop_samples"
        ) as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def async_count_cycles_since(self, since_ts: float) -> int:
        """Count cycles with end_ts >= since_ts."""
        if self._conn is None:
            return 0
        try:
            cur = await self._conn.execute(
                "SELECT COUNT(*) FROM cycles WHERE end_ts >= ?", (float(since_ts),)
            )
            row = await cur.fetchone()
            await cur.close()
            return int(row[0]) if row else 0
        except Exception:
            return 0

    async def async_avg_duration_since(self, since_ts: float) -> float | None:
        """Average duration_s of cycles with end_ts >= since_ts, or None."""
        if self._conn is None:
            return None
        try:
            cur = await self._conn.execute(
                "SELECT AVG(duration_s) FROM cycles WHERE end_ts >= ?",
                (float(since_ts),),
            )
            row = await cur.fetchone()
            await cur.close()
            if not row or row[0] is None:
                return None
            return float(row[0])
        except Exception:
            return None
