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
from ..const import DAILY_SUMMARY_BACKFILL_KEY

_LOGGER = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")

def _time_now() -> float:
    return time.time()

_MIN_SPLIT_DURATION_S = 60.0  # v18: skip split if first DHW sample too early
_R446_RUN_GAP_S = 900.0  # v18 R446: samples within 900s = same run
_R446_MIN_RUN_S = 900.0  # v18 R446: minimum run duration to synthesize
_R446B_MERGE_GAP_S = 120.0  # v18 R446b: gap < 2x MODE_DEBOUNCE_S
_R446B_MERGE_GAP_S = 120.0  # v18 R446b: gap < 2x MODE_DEBOUNCE_S


class CycleDB:
    """Thin async wrapper around aiosqlite with schema bootstrap."""

    def __init__(
        self,
        path: str | Path,
        *,
        journal_mode: str = "delete",
    ) -> None:
        self._path = str(path)
        self._journal_mode: str = journal_mode
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
        if self._journal_mode == "wal":
            # v1.12.2 (#113): WAL for prod durability + concurrent reads.
            # busy_timeout=5000 matches Python sqlite3 default; external
            # readers get up to 5s to acquire lock before OperationalError.
            await self._conn.execute("PRAGMA journal_mode = WAL")
            await self._conn.execute("PRAGMA synchronous = NORMAL")
            await self._conn.execute("PRAGMA busy_timeout = 5000")

    async def async_initialize(self) -> None:
        if self._conn is None:
            await self.async_open()
        conn = self._require()
        # Read schema off the event loop (HA blocking-I/O check).
        schema = await asyncio.to_thread(_SCHEMA_PATH.read_text)
        await conn.executescript(schema)
        await conn.commit()

        # v1.12.0 (#105, #107): schema v16 migration. Idempotent.
        # - is_transient: adds column + backfills historical transients
        # - thermal_kw_avg: adds column (NULL for historical, populated
        #   going forward via INSERT in async_insert_cycle)
        from ..const import (
            TRANSIENT_MAX_DURATION_S,
            TRANSIENT_NEAR_MAX_DURATION_S,
            TRANSIENT_NEAR_MAX_DT_K,
            TRANSIENT_NEAR_MIN_RPS,
        )
        cursor = await conn.execute("PRAGMA table_info(cycles)")
        existing_cols = {row[1] for row in await cursor.fetchall()}
        await cursor.close()
        if "is_transient" not in existing_cols:
            await conn.execute(
                "ALTER TABLE cycles ADD COLUMN "
                "is_transient INTEGER DEFAULT 0"
            )
        if "thermal_kw_avg" not in existing_cols:
            await conn.execute(
                "ALTER TABLE cycles ADD COLUMN thermal_kw_avg REAL"
            )

        # v1.12.4 (v18): DHW backfill columns + indices.
        # Idempotent via PRAGMA table_info guard; fresh installs
        # get these from schema.sql, so this returns 0 on new DBs.
        await self.async_migrate_schema_to_v18()

        # Idempotent backfill: only touches is_transient=0 rows
        # matching the classification rule. Zero rows after first run.
        await conn.execute(
            f"""UPDATE cycles SET is_transient = 1
                WHERE is_transient = 0
                  AND (
                    (duration_s IS NOT NULL
                     AND duration_s < {TRANSIENT_MAX_DURATION_S})
                    OR (duration_s IS NOT NULL
                        AND duration_s < {TRANSIENT_NEAR_MAX_DURATION_S}
                        AND dT_max IS NOT NULL
                        AND dT_max < {TRANSIENT_NEAR_MAX_DT_K}
                        AND rps_max IS NOT NULL
                        AND rps_max >= {TRANSIENT_NEAR_MIN_RPS})
                  )"""
        )
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
            "cop_sample_count, cop_sample_stdev, cop_confidence, "
            "thermal_kw_avg, is_transient "
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
            "thermal_kw_avg", "is_transient",
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
        cutoff = int((time.time() - float(retention_days) * 86400.0) // 3600)
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
                cop_avg, cop_sample_count, cop_sample_stdev,
                cop_confidence, thermal_kw_avg, is_transient)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                record.get("thermal_kw_avg"),
                int(bool(record.get("is_transient", 0))),
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

    async def async_migrate_to_v17(self) -> dict[str, int]:
        """v1.12.2 data migration: reclassify unknown-mode cycles with
        valid compressor data (#112) and backfill thermal_kw_avg from
        features.vector_json[11] (#114). Idempotent (marker-guarded).

        Runs from _async_setup_database AFTER v11-v15 migrations, so
        vector_json is guaranteed current (12-dim). Do NOT call from
        async_initialize — that runs before v11-v15.
        """
        conn = self._require()
        cur = await conn.execute(
            "SELECT 1 FROM model_state "
            "WHERE key='data_migration_v1_12_2'"
        )
        try:
            already = await cur.fetchone()
        finally:
            await cur.close()
        if already:
            return {"skipped": 1}

        # #112: reclassify unknown-mode cycles with real compressor data
        cur = await conn.execute(
            "UPDATE cycles SET mode='heating' "
            "WHERE mode='unknown' "
            "AND rps_max IS NOT NULL AND rps_max > 0 "
            "AND dT_max IS NOT NULL AND dT_max > 0 "
            "AND duration_s IS NOT NULL AND duration_s > 300"
        )
        try:
            mode_fixed = int(cur.rowcount or 0)
        finally:
            await cur.close()

        # #114: backfill thermal_kw_avg from features.vector_json[11]
        cur = await conn.execute(
            "UPDATE cycles SET thermal_kw_avg = ("
            "  SELECT CAST(json_extract(f.vector_json, '$[11]') AS REAL) "
            "  FROM features f WHERE f.cycle_id = cycles.id"
            ") WHERE thermal_kw_avg IS NULL "
            "AND EXISTS (SELECT 1 FROM features f "
            "            WHERE f.cycle_id = cycles.id) "
            "AND json_valid((SELECT f.vector_json FROM features f "
            "                WHERE f.cycle_id = cycles.id)) "
            "AND json_array_length((SELECT f.vector_json FROM features f "
            "                      WHERE f.cycle_id = cycles.id)) > 11"
        )
        try:
            thermal_filled = int(cur.rowcount or 0)
        finally:
            await cur.close()

        # #112b: rebuild daily_summary for days with mode='unknown'
        cur = await conn.execute(
            "SELECT DISTINCT day FROM daily_summary WHERE mode='unknown'"
        )
        try:
            affected_days = [r[0] for r in await cur.fetchall()]
        finally:
            await cur.close()
        for day in affected_days:
            try:
                await conn.execute(
                    "DELETE FROM daily_summary "
                    "WHERE day=? AND mode='unknown'",
                    (day,),
                )
            except Exception:
                _LOGGER.exception(
                    "v17 DS unknown-delete failed for day=%s", day
                )
            try:
                await self.async_rollup_day(day)
            except Exception:
                _LOGGER.exception(
                    "v17 DS rebuild failed for day=%s", day
                )

        # Marker prevents re-run
        await conn.execute(
            "INSERT OR REPLACE INTO model_state "
            "(key, value_json, updated_ts) "
            "VALUES ('data_migration_v1_12_2', ?, ?)",
            (
                '{"completed": true, "mode_fixed": '
                + str(mode_fixed)
                + ', "thermal_filled": '
                + str(thermal_filled)
                + "}",
                time.time(),
            ),
        )
        await conn.commit()
        return {
            "mode_reclassified": mode_fixed,
            "thermal_backfilled": thermal_filled,
            "ds_days_rebuilt": len(affected_days),
        }

    async def async_migrate_schema_to_v18(self) -> dict[str, int]:
        """v1.12.4 (v18): add DHW backfill columns + indices.

        Idempotent (PRAGMA-guarded). Called from async_initialize() so
        pre-v1.12.4 DBs get columns on next startup. Fresh installs get
        them from schema.sql directly, so this returns 0 counts.
        """
        conn = self._require()
        added: dict[str, int] = {"cycles": 0, "cop_samples": 0}

        async with conn.execute("PRAGMA table_info(cycles)") as cur:
            existing = {r[1] for r in await cur.fetchall()}
        for name, decl in (
            ("mode_original", "TEXT"),
            ("parent_cycle_id", "INTEGER"),
            ("is_dhw_tail", "INTEGER DEFAULT 0"),
            ("is_reconstructed", "INTEGER DEFAULT 0"),
        ):
            if name in existing:
                continue
            await conn.execute(
                f"ALTER TABLE cycles ADD COLUMN {name} {decl}"
            )
            added["cycles"] += 1

        async with conn.execute("PRAGMA table_info(cop_samples)") as cur:
            existing = {r[1] for r in await cur.fetchall()}
        for name, decl in (
            ("mode_original", "TEXT"),
            ("is_transition_artifact", "INTEGER DEFAULT 0"),
        ):
            if name in existing:
                continue
            await conn.execute(
                f"ALTER TABLE cop_samples ADD COLUMN {name} {decl}"
            )
            added["cop_samples"] += 1

        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cop_samples_artifact "
            "ON cop_samples(is_transition_artifact)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cycles_reconstructed "
            "ON cycles(is_reconstructed)"
        )

        if added["cycles"] or added["cop_samples"]:
            await conn.commit()
        return added

    async def async_migrate_to_v18(self) -> dict[str, Any]:
        """v1.12.4 (v18): DHW historical backfill + aggregate rebuild.

        Marker-guarded idempotent. Called from _async_setup_database
        AFTER v17. Each step fills in per-phase; skeleton returns all-zero
        stats until Phase 9 flips completed=True and adds marker write.

        Step plan:
          1. R445a-c  -- 3-shape classifier (relabel/split/tail)
          2. R445d    -- in-cycle unknown samples relabel
          3. R445e    -- dynamic Carnot artifact flag
          4. R446     -- synthesize orphan DHW runs
          5. R446b    -- merge adjacent same-mode splits
          6. Amend 7  -- aggregate backfill (NULL -> COUNT(*))
          7. R447     -- DELETE+rebuild cop_hourly (exclude artifacts)
          8. R448     -- daily_summary rebuild from corrected cycles

        R449 energy_acc rebuild DEFERRED (preserve HWM chain).
        """
        marker = await self.async_get_model_state(
            "data_migration_v1_12_4"
        )
        if marker and marker.get("completed"):
            return {"skipped": 1}

        stats: dict[str, Any] = {
            "shape_a_relabelled": 0,
            "shape_b_split": 0,
            "shape_c_tail_marked": 0,
            "unknown_in_dhw_fixed": 0,
            "artifacts_flagged": 0,
            "cycles_synthesized": 0,
            "splits_merged": 0,
            "cop_aggregates_backfilled": 0,
            "hours_rebuilt": 0,
            "days_rebuilt": 0,
            "energy_acc_rebuilt": False,
            "completed": True,
        }

        # Phase 4 FIRST (R445e): flag artifacts so R445a-c can exclude them
        stats["artifacts_flagged"] = await self._flag_carnot_artifacts()

        # Phase 2 (R445a-c): 3-shape classifier (artifact-filtered)
        r445abc = await self._classify_and_fix_cycle_shapes()
        stats["shape_a_relabelled"] = r445abc["shape_a_relabelled"]
        stats["shape_b_split"] = r445abc["shape_b_split"]
        stats["shape_c_tail_marked"] = r445abc["shape_c_tail_marked"]

        # Phase 3 (R445d): in-cycle unknown relabel
        stats["unknown_in_dhw_fixed"] = await self._relabel_in_cycle_unknowns()
        # Phase 5: R446 orphan DHW synthesis
        stats["cycles_synthesized"] = await self._synthesize_orphan_dhw_runs()
        # Phase 6: R446b merge adjacent same-mode splits
        stats["splits_merged"] = await self._merge_adjacent_same_mode_cycles()
        # Phase 7: Amend 7 aggregate backfill
        stats["cop_aggregates_backfilled"] = await self._backfill_null_aggregates()
        # Phase 8: R447 cop_hourly DELETE+rebuild
        stats["hours_rebuilt"] = await self._rebuild_cop_hourly_for_affected_hours()
        # Phase 9: R448 daily_summary rebuild
        stats["days_rebuilt"] = await self._rebuild_daily_summary_for_affected_days()

        # v1.12.4 Phase 9b: write marker (idempotent, marker-guarded)
        await self.async_set_model_state(
            "data_migration_v1_12_4", stats
        )
        return stats

    async def _classify_and_fix_cycle_shapes(self) -> dict[str, int]:
        """R445a-c: 3-shape classifier for DHW contamination in cycles.

        For each non-dhw, non-transient cycle:
          ratio = dhw_samples / total_samples
          - ratio == 1.0    -> Shape A: relabel to dhw
          - 0.30 <= r < 1.0 -> Shape B: split at first dhw sample
          - 0 < r < 0.30    -> Shape C: mark is_dhw_tail=1
          - r == 0          -> skip

        #133 constraint: aggregates use COUNT(*) from cop_samples.
        """
        conn = self._require()
        stats = {
            "shape_a_relabelled": 0,
            "shape_b_split": 0,
            "shape_c_tail_marked": 0,
        }
        cur = await conn.execute(
            "SELECT id, start_ts, end_ts, mode FROM cycles "
            "WHERE is_transient = 0 "
            "AND end_ts IS NOT NULL "
            "AND start_ts IS NOT NULL "
            "AND parent_cycle_id IS NULL "
            "AND mode != 'dhw' "
            "ORDER BY start_ts"
        )
        try:
            rows = await cur.fetchall()
        finally:
            await cur.close()

        for cycle_id, start_ts, end_ts, mode in rows:
            cur = await conn.execute(
                "SELECT COUNT(*), "
                "SUM(CASE WHEN mode='dhw' THEN 1 ELSE 0 END) "
                "FROM cop_samples WHERE ts BETWEEN ? AND ? "
                "AND is_transition_artifact = 0",
                (start_ts, end_ts),
            )
            try:
                row = await cur.fetchone()
                total, dhw_n = row if row else (0, 0)
            finally:
                await cur.close()
            total, dhw_n = int(total or 0), int(dhw_n or 0)
            if total == 0 or dhw_n == 0:
                continue
            ratio = dhw_n / total
            if ratio >= 1.0:
                await self._relabel_cycle_to_dhw(cycle_id, mode)
                stats["shape_a_relabelled"] += 1
            elif ratio >= 0.30:
                cur = await conn.execute(
                    "SELECT MIN(ts) FROM cop_samples "
                    "WHERE ts BETWEEN ? AND ? AND mode='dhw' "
                    "AND is_transition_artifact = 0",
                    (start_ts, end_ts),
                )
                try:
                    srow = await cur.fetchone()
                    split_ts = srow[0] if srow else None
                finally:
                    await cur.close()
                if split_ts is None:  # pragma: no cover - dhw_n > 0 guarantees value
                    continue
                if split_ts <= start_ts + _MIN_SPLIT_DURATION_S:
                    continue
                await self._split_cycle_at_dhw_start(
                    cycle_id, start_ts, end_ts, split_ts, mode
                )
                stats["shape_b_split"] += 1
            else:
                await self._mark_cycle_dhw_tail(cycle_id)
                stats["shape_c_tail_marked"] += 1
        await conn.commit()
        return stats

    async def _sample_aggregates(
        self, start_ts: float, end_ts: float
    ) -> tuple[float | None, int]:
        """Compute (cop_avg, sample_count) from cop_samples in a window.

        #133: uses COUNT(*) from cop_samples, not cycles.cop_sample_count.
        """
        conn = self._require()
        cur = await conn.execute(
            "SELECT AVG(cop), COUNT(cop) FROM cop_samples "
            "WHERE ts BETWEEN ? AND ? AND cop IS NOT NULL",
            (start_ts, end_ts),
        )
        try:
            row = await cur.fetchone()
        finally:
            await cur.close()
        if row is None:  # pragma: no cover - AVG/COUNT always returns a row
            return (None, 0)
        return (row[0], int(row[1] or 0))

    async def _relabel_cycle_to_dhw(
        self, cycle_id: int, original_mode: str
    ) -> None:
        """Shape A: pure relabel with aggregate recompute."""
        conn = self._require()
        cur = await conn.execute(
            "SELECT start_ts, end_ts FROM cycles WHERE id=?", (cycle_id,)
        )
        try:
            row = await cur.fetchone()
        finally:
            await cur.close()
        if row is None:  # pragma: no cover - cycle_id from prior SELECT loop
            return
        cop_avg, cop_count = await self._sample_aggregates(row[0], row[1])
        await conn.execute(
            "UPDATE cycles SET "
            "mode_original = COALESCE(mode_original, ?), "
            "mode = 'dhw', "
            "cop_avg = ?, "
            "cop_sample_count = ? "
            "WHERE id = ?",
            (original_mode, cop_avg, cop_count, cycle_id),
        )

    async def _split_cycle_at_dhw_start(
        self,
        parent_id: int,
        start_ts: float,
        end_ts: float,
        split_ts: float,
        original_mode: str,
    ) -> None:
        """Shape B: split at first DHW sample into parent + child."""
        conn = self._require()
        parent_avg, parent_count = await self._sample_aggregates(
            start_ts, split_ts
        )
        parent_duration = int(split_ts - start_ts)
        await conn.execute(
            "UPDATE cycles SET "
            "mode_original = COALESCE(mode_original, ?), "
            "end_ts = ?, "
            "duration_s = ?, "
            "cop_avg = ?, "
            "cop_sample_count = ?, "
            "is_reconstructed = 1 "
            "WHERE id = ?",
            (
                original_mode, split_ts, parent_duration,
                parent_avg, parent_count, parent_id,
            ),
        )
        child_avg, child_count = await self._sample_aggregates(
            split_ts, end_ts
        )
        child_duration = int(end_ts - split_ts)
        await conn.execute(
            "INSERT INTO cycles "
            "(start_ts, end_ts, duration_s, mode, mode_original, "
            "parent_cycle_id, cop_avg, cop_sample_count, "
            "is_reconstructed) "
            "VALUES (?, ?, ?, 'dhw', 'dhw', ?, ?, ?, 1)",
            (
                split_ts, end_ts, child_duration,
                parent_id, child_avg, child_count,
            ),
        )

    async def _mark_cycle_dhw_tail(self, cycle_id: int) -> None:
        """Shape C: mark tail, no split."""
        conn = self._require()
        await conn.execute(
            "UPDATE cycles SET is_dhw_tail = 1 WHERE id = ?",
            (cycle_id,),
        )

    async def _relabel_in_cycle_unknowns(self) -> int:
        """R445d: relabel unknown samples that fall inside a cycle window.

        Uses cycle.mode as ground truth. Skips if no cycle covers the
        sample, or if the covering cycle's mode is NULL/'unknown'.

        Runs AFTER R445a-c (Phase 2) so cycles are already corrected.
        Uses single UPDATE-with-EXISTS for O(1) SQL passes (fleet has
        ~83 unknowns all-time; per-sample loop unnecessary).
        """
        conn = self._require()
        cur = await conn.execute(
            """
            UPDATE cop_samples
            SET mode_original = COALESCE(mode_original, mode),
                mode = (
                    SELECT cycles.mode FROM cycles
                    WHERE cycles.start_ts <= cop_samples.ts
                      AND cycles.end_ts >= cop_samples.ts
                      AND cycles.mode IS NOT NULL
                      AND cycles.mode != 'unknown'
                    ORDER BY cycles.start_ts DESC
                    LIMIT 1
                )
            WHERE mode = 'unknown'
              AND EXISTS (
                  SELECT 1 FROM cycles
                  WHERE cycles.start_ts <= cop_samples.ts
                    AND cycles.end_ts >= cop_samples.ts
                    AND cycles.mode IS NOT NULL
                    AND cycles.mode != 'unknown'
              )
            """
        )
        try:
            updated = int(cur.rowcount or 0)
        finally:
            await cur.close()
        await conn.commit()
        return updated

    async def _flag_carnot_artifacts(self) -> int:
        """R445e: flag physically impossible COP values as transition artifacts.

        Carnot = (lwt + 273.15) / (lwt - outdoor).
        Flag when:
          - cop < 0.05 * Carnot (below realistic floor)
          - cop > 0.55 * Carnot (above datasheet-derived ceiling, k=0.447 max)
          - lwt <= outdoor (negative/zero delta-T, division guard -> always flag)
          - lwt or outdoor is NULL (cannot evaluate, flag conservatively)

        Live evidence: sample 2712, lwt=30.9, out=8.8 -> Carnot=13.76,
        cop=16.486, ratio=1.198 >> 0.55 bound. Confirms threshold.
        """
        conn = self._require()
        cur = await conn.execute(
            """
            UPDATE cop_samples
            SET is_transition_artifact = 1
            WHERE is_transition_artifact = 0
              AND cop IS NOT NULL
              AND (
                lwt IS NULL
                OR outdoor IS NULL
                OR lwt <= outdoor
                OR cop < 0.05 * ((lwt + 273.15) / (lwt - outdoor))
                OR cop > 0.55 * ((lwt + 273.15) / (lwt - outdoor))
              )
            """
        )
        try:
            flagged = int(cur.rowcount or 0)
        finally:
            await cur.close()
        await conn.commit()
        return flagged

    async def _synthesize_orphan_dhw_runs(self) -> int:
        """R446: synthesize missing DHW cycles from orphan sample runs.

        Finds dhw samples not covered by any existing cycle window, groups
        them into runs (gap <= _R446_RUN_GAP_S), filters runs >= _R446_MIN_RUN_S,
        and INSERTs synthetic cycles with is_reconstructed=1.

        thermal_kw_avg is set to NULL: cop_samples has no R4T/R5T column,
        so cold-side temperature (needed for thermal formula) is unavailable.
        Deferred to v1.13.0 #129 (features rewrite).

        Runs AFTER R445d/R445e (samples clean + artifact-filtered).
        Uses INSERT OR IGNORE (UNIQUE(start_ts) -> idempotent).
        """
        conn = self._require()
        cur = await conn.execute(
            "SELECT ts FROM cop_samples s "
            "WHERE s.mode = 'dhw' "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM cycles c "
            "  WHERE c.start_ts <= s.ts AND c.end_ts >= s.ts"
            ") "
            "ORDER BY s.ts"
        )
        try:
            timestamps = [float(r[0]) for r in await cur.fetchall()]
        finally:
            await cur.close()
        if not timestamps:
            return 0

        runs: list[tuple[float, float]] = []
        run_start = timestamps[0]
        run_last = timestamps[0]
        for ts in timestamps[1:]:
            if ts - run_last <= _R446_RUN_GAP_S:
                run_last = ts
            else:
                runs.append((run_start, run_last))
                run_start = ts
                run_last = ts
        runs.append((run_start, run_last))

        synthesized = 0
        for r_start, r_end in runs:
            if r_end - r_start < _R446_MIN_RUN_S:
                continue
            cur = await conn.execute(
                "SELECT AVG(cop), COUNT(cop) FROM cop_samples "
                "WHERE ts BETWEEN ? AND ? AND cop IS NOT NULL "
                "AND is_transition_artifact = 0",
                (r_start, r_end),
            )
            try:
                agg = await cur.fetchone()
            finally:
                await cur.close()
            cop_avg = agg[0] if agg is not None else None
            cop_count = int(agg[1] or 0) if agg is not None else 0
            duration = int(r_end - r_start)
            cur = await conn.execute(
                "INSERT OR IGNORE INTO cycles "
                "(start_ts, end_ts, duration_s, mode, mode_original, "
                "cop_avg, cop_sample_count, is_reconstructed) "
                "VALUES (?, ?, ?, 'dhw', 'dhw', ?, ?, 1)",
                (r_start, r_end, duration, cop_avg, cop_count),
            )
            try:
                inserted = cur.rowcount
            finally:
                await cur.close()
            synthesized += int(inserted or 0)
        await conn.commit()
        return synthesized

    async def _merge_adjacent_same_mode_cycles(self) -> int:
        """R446b: merge adjacent same-mode cycles split by transients.

        Criteria (pair must satisfy ALL):
          - (next.start_ts - prev.end_ts) < _R446B_MERGE_GAP_S (120s)
          - same mode
          - both is_transient = 0
          - is_reconstructed: any (0/1/mixed OK)

        Merge: keep prev.id, extend end_ts to last.end_ts,
        recompute aggregates from samples (R133), set is_reconstructed=1,
        DELETE next cycle + its features row (explicit, no CASCADE).

        Iterative within one pass (chains collapse). Idempotent.
        """
        conn = self._require()
        cur = await conn.execute(
            "SELECT id, start_ts, end_ts, mode, is_transient "
            "FROM cycles WHERE end_ts IS NOT NULL ORDER BY start_ts"
        )
        try:
            rows = await cur.fetchall()
        finally:
            await cur.close()

        merge_ops: list[tuple[int, float, float, list[int]]] = []
        keep_id: int | None = None
        keep_start: float = 0.0
        keep_end: float = 0.0
        keep_mode: str | None = None
        pending_deletes: list[int] = []

        def _flush() -> None:
            if pending_deletes and keep_id is not None:
                merge_ops.append(
                    (keep_id, keep_start, keep_end, list(pending_deletes))
                )

        for cid, s, e, m, trans in rows:
            if trans:
                _flush()
                keep_id = None
                pending_deletes = []
                continue
            if keep_id is None:
                keep_id, keep_start, keep_end, keep_mode = cid, s, e, m
                pending_deletes = []
            elif m == keep_mode and (s - keep_end) < _R446B_MERGE_GAP_S:
                pending_deletes.append(cid)
                keep_end = e
            else:
                _flush()
                keep_id, keep_start, keep_end, keep_mode = cid, s, e, m
                pending_deletes = []
        _flush()

        if not merge_ops:
            return 0

        merged_count = 0
        for kid, kstart, kend, deletes in merge_ops:
            cop_avg, cop_count = await self._sample_aggregates(
                kstart, kend
            )
            await conn.execute(
                "UPDATE cycles SET end_ts = ?, duration_s = ?, "
                "cop_avg = ?, cop_sample_count = ?, "
                "is_reconstructed = 1 WHERE id = ?",
                (kend, int(kend - kstart), cop_avg, cop_count, kid),
            )
            for did in deletes:
                await conn.execute(
                    "DELETE FROM features WHERE cycle_id = ?", (did,)
                )
                await conn.execute(
                    "DELETE FROM cycles WHERE id = ?", (did,)
                )
                merged_count += 1
        await conn.commit()
        return merged_count

    async def _backfill_null_aggregates(self) -> int:
        """Amend 7: backfill cop_avg/cop_sample_count from samples.

        Targets cycles where cop_sample_count IS NULL or 0 (aggregation
        never ran or partial). Recomputes from cop_samples excluding
        artifacts (#133: COUNT/AVG from samples, never cached value).

        Skips cycles with 0 valid samples (leave NULL).
        """
        conn = self._require()
        cur = await conn.execute(
            "SELECT id, start_ts, end_ts FROM cycles "
            "WHERE (cop_sample_count IS NULL OR cop_sample_count = 0) "
            "AND start_ts IS NOT NULL AND end_ts IS NOT NULL"
        )
        try:
            rows = await cur.fetchall()
        finally:
            await cur.close()
        if not rows:
            return 0
        backfilled = 0
        for cid, s, e in rows:
            cur = await conn.execute(
                "SELECT AVG(cop), COUNT(cop) FROM cop_samples "
                "WHERE ts BETWEEN ? AND ? AND cop IS NOT NULL "
                "AND is_transition_artifact = 0",
                (s, e),
            )
            try:
                agg = await cur.fetchone()
            finally:
                await cur.close()
            avg = agg[0] if agg is not None else None
            cnt = int(agg[1] or 0) if agg is not None else 0
            if cnt < 1:
                continue
            await conn.execute(
                "UPDATE cycles SET cop_avg = ?, cop_sample_count = ? "
                "WHERE id = ?",
                (avg, cnt, cid),
            )
            backfilled += 1
        await conn.commit()
        return backfilled

    async def _rebuild_cop_hourly_for_affected_hours(self) -> int:
        """R447: DELETE + rebuild cop_hourly buckets touched by migration.

        Only rebuilds hours spanned by cycles that migration changed
        (non-artifact + is_reconstructed + is_transient + all cycle
        modifications made so far). Excludes is_transition_artifact=1.
        n_samples = COUNT(*) from samples (#133).
        """
        conn = self._require()
        cur = await conn.execute(
            "SELECT DISTINCT CAST(cop_samples.ts / 3600 AS INTEGER) AS h "
            "FROM cop_samples "
            "WHERE is_transition_artifact = 1 "
            "   OR mode_original IS NOT NULL"
        )
        try:
            hours = [int(r[0]) for r in await cur.fetchall()]
        finally:
            await cur.close()
        if not hours:
            return 0
        rebuilt = 0
        for h in hours:
            await conn.execute(
                "DELETE FROM cop_hourly WHERE ts_hour = ?", (h,)
            )
            cur = await conn.execute(
                "SELECT mode, COUNT(*) AS n, AVG(cop) AS avg "
                "FROM cop_samples "
                "WHERE CAST(ts / 3600 AS INTEGER) = ? "
                "AND is_transition_artifact = 0 "
                "AND cop IS NOT NULL AND mode IS NOT NULL "
                "GROUP BY mode",
                (h,),
            )
            try:
                rows = await cur.fetchall()
            finally:
                await cur.close()
            for mode, n, avg in rows:
                await conn.execute(
                    "INSERT INTO cop_hourly "
                    "(ts_hour, mode, n_samples, cop_mean, updated_ts) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (h, mode, int(n), avg, _time_now()),
                )
            rebuilt += 1
        await conn.commit()
        return rebuilt

    async def _rebuild_daily_summary_for_affected_days(self) -> int:
        """R448: DELETE + rebuild daily_summary rows for touched days.

        Rebuilds from corrected cycles (after all prior modifications).
        Uses existing async_rollup_day logic.
        """
        conn = self._require()
        cur = await conn.execute(
            "SELECT DISTINCT date(start_ts, 'unixepoch') AS d "
            "FROM cycles "
            "WHERE is_reconstructed = 1 "
            "   OR mode_original IS NOT NULL "
            "   OR is_dhw_tail = 1"
        )
        try:
            days = [r[0] for r in await cur.fetchall() if r[0]]
        finally:
            await cur.close()
        if not days:
            return 0
        for day in days:
            await conn.execute(
                "DELETE FROM daily_summary WHERE day = ?", (day,)
            )
        await conn.commit()
        for day in days:
            try:
                await self.async_rollup_day(day)
            except Exception:  # pragma: no cover - defensive, rollup idempotent
                _LOGGER.exception(
                    "v18 R448 rebuild failed for day=%s", day
                )
        return len(days)

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

    async def async_rollup_day(
        self, day: str, *, modes: tuple[str, ...] | None = None
    ) -> int:
        """Full-recompute daily_summary for one local day (idempotent)."""
        conn = self._require()
        try:
            start_ts = time.mktime(time.strptime(day, "%Y-%m-%d"))
        except (ValueError, TypeError):
            return 0
        end_ts = start_ts + 86400.0
        sql = (
            "SELECT end_ts, duration_s, mode, dT_max, rps_avg, quality_score, "
            "buh_used, defrost_used FROM cycles "
            "WHERE end_ts IS NOT NULL AND end_ts >= ? AND end_ts < ?"
        )
        params: list[Any] = [start_ts, end_ts]
        if modes:
            sql += " AND COALESCE(mode,'unknown') IN ("
            sql += ",".join("?" * len(modes)) + ")"
            params.extend(modes)
        async with conn.execute(sql, params) as cur:
            rows = await cur.fetchall()
        if not rows:
            return 0
        agg: dict[str, dict[str, Any]] = {}
        for r in rows:
            mode = r["mode"] or "unknown"
            a = agg.setdefault(mode, {
                "cycles": 0, "total_duration_s": 0,
                "duration_min": None, "duration_max": None,
                "quality_sum": 0, "dt_max_sum": 0.0, "rps_sum": 0.0,
                "buh_count": 0, "defrost_count": 0,
            })
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
        now = time.time()
        for mode, a in agg.items():
            await conn.execute(
                """INSERT INTO daily_summary
                   (day, mode, cycles, total_duration_s, duration_min,
                    duration_max, quality_sum, dt_max_sum, rps_sum,
                    buh_count, defrost_count, updated_ts)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(day, mode) DO UPDATE SET
                     cycles = excluded.cycles,
                     total_duration_s = excluded.total_duration_s,
                     duration_min = excluded.duration_min,
                     duration_max = excluded.duration_max,
                     quality_sum = excluded.quality_sum,
                     dt_max_sum = excluded.dt_max_sum,
                     rps_sum = excluded.rps_sum,
                     buh_count = excluded.buh_count,
                     defrost_count = excluded.defrost_count,
                     updated_ts = excluded.updated_ts""",
                (
                    day, mode, a["cycles"], a["total_duration_s"],
                    a["duration_min"], a["duration_max"],
                    a["quality_sum"], a["dt_max_sum"], a["rps_sum"],
                    a["buh_count"], a["defrost_count"], now,
                ),
            )
        await conn.commit()
        return len(agg)

    async def async_backfill_daily_summary(self) -> int:
        """One-time backfill: populate daily_summary from existing cycles.

        Guarded by model_state[DAILY_SUMMARY_BACKFILL_KEY]. Returns number
        of distinct days written. Silent no-op if already run.
        """
        try:
            done = await self.async_get_model_state(
                DAILY_SUMMARY_BACKFILL_KEY
            )
        except Exception:
            done = None
        if done:
            return 0
        conn = self._require()
        async with conn.execute(
            "SELECT DISTINCT end_ts FROM cycles WHERE end_ts IS NOT NULL"
        ) as cur:
            rows = await cur.fetchall()
        days = sorted({
            time.strftime("%Y-%m-%d", time.localtime(float(r["end_ts"])))
            for r in rows
        })
        written = 0
        for day in days:
            try:
                n = await self.async_rollup_day(day)
                if n > 0:
                    written += 1
            except Exception:
                _LOGGER.exception("backfill rollup failed for day=%s", day)
        try:
            await self.async_set_model_state(
                DAILY_SUMMARY_BACKFILL_KEY,
                {"done": True, "days": written},
            )
        except Exception:
            _LOGGER.exception("backfill flag persist failed")
        return written

    async def async_prune_model_state(
        self, *, retention_days: int = 400,
    ) -> int:
        """Prune energy_acc.<day> / runtime_acc.<day> older than cutoff.

        v1.12.0 (#106): keys use the ISO date suffix for retention
        (not updated_ts) because every persist tick re-touches the key.
        Date-suffix compare is immutable. Returns rows deleted.
        """
        conn = self._require()
        cutoff_ts = time.time() - float(retention_days) * 86400.0
        cutoff_day = time.strftime(
            "%Y-%m-%d", time.localtime(cutoff_ts)
        )
        cur = await conn.execute(
            "DELETE FROM model_state "
            "WHERE (key LIKE 'energy_acc.%' "
            "       AND substr(key, 12) < ?) "
            "   OR (key LIKE 'runtime_acc.%' "
            "       AND substr(key, 13) < ?)",
            (cutoff_day, cutoff_day),
        )
        try:
            n = cur.rowcount or 0
        finally:
            await cur.close()
        return n

    async def async_run_maintenance(
        self,
        *,
        cycle_retention_days: int = 90,
        alert_retention_days: int = 90,  # matches const.DEFAULT_ALERT_RETENTION_DAYS
        cop_retention_days: int = 365,
        model_state_retention_days: int = 400,
        vacuum: bool = True,
    ) -> dict[str, int]:
        """Aggregate old cycles, prune, optionally vacuum. Atomic rollup+prune."""
        conn = self._require()
        cutoff = time.time() - float(cycle_retention_days) * 86400.0
        alert_cutoff = time.time() - float(alert_retention_days) * 86400.0

        # 1. Roll up each affected day (idempotent replace)
        async with conn.execute(
            "SELECT end_ts FROM cycles "
            "WHERE end_ts IS NOT NULL AND end_ts < ?",
            (cutoff,),
        ) as cur:
            rows = await cur.fetchall()

        per_day: dict[str, int] = {}
        for r in rows:
            day = time.strftime(
                "%Y-%m-%d", time.localtime(float(r["end_ts"]))
            )
            per_day[day] = per_day.get(day, 0) + 1

        days_rolled_up = 0
        for day in sorted(per_day):
            try:
                n_modes = await self.async_rollup_day(day)
                days_rolled_up += n_modes
            except Exception:
                _LOGGER.exception("rollup failed for day=%s", day)

        cycles_rolled_up = sum(per_day.values())

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

        # v1.12.0 (#106): prune old energy/runtime accumulator keys.
        # model_state table otherwise grows ~2 keys/day forever.
        model_state_deleted = 0
        try:
            model_state_deleted = await self.async_prune_model_state(
                retention_days=int(model_state_retention_days),
            )
        except Exception:
            _LOGGER.exception("model_state prune failed")

        await conn.commit()

        # 5. VACUUM outside any transaction
        if vacuum:
            await self.async_vacuum()

        return {
            "days_rolled_up": days_rolled_up,
            "cycles_rolled_up": cycles_rolled_up,
            "cycles_deleted": cycles_deleted,
            "features_deleted": features_deleted,
            "alerts_deleted": alerts_deleted,
            "cop_deleted": cop_deleted,
            "model_state_deleted": model_state_deleted,
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

    async def async_defrost_duration_since(
        self, since_ts: float
    ) -> float | None:
        """Sum duration_s of defrost cycles with end_ts >= since_ts, or None."""
        if self._conn is None:
            return None
        try:
            cur = await self._conn.execute(
                "SELECT SUM(duration_s) FROM cycles "
                "WHERE defrost_used = 1 AND end_ts >= ?",
                (float(since_ts),),
            )
            row = await cur.fetchone()
            await cur.close()
            if not row or row[0] is None:
                return None
            return float(row[0])
        except Exception:
            return None


    async def async_count_alerts_before(self, cutoff_ts: float) -> int:
        """Count alert rows with ts < cutoff_ts (retention candidates)."""
        if self._conn is None:
            return 0
        try:
            cur = await self._conn.execute(
                "SELECT COUNT(*) FROM alerts WHERE ts < ?", (float(cutoff_ts),)
            )
            row = await cur.fetchone()
            await cur.close()
            return int(row[0]) if row else 0
        except Exception:
            return 0

    async def async_count_cycles_before(self, cutoff_ts: float) -> int:
        """Count cycle rows past retention (end_ts not null and < cutoff)."""
        if self._conn is None:
            return 0
        try:
            cur = await self._conn.execute(
                "SELECT COUNT(*) FROM cycles "
                "WHERE end_ts IS NOT NULL AND end_ts < ?",
                (float(cutoff_ts),),
            )
            row = await cur.fetchone()
            await cur.close()
            return int(row[0]) if row else 0
        except Exception:
            return 0
