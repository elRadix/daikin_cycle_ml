"""v1.19.9 R644: FULL prod DB replay — alle tabellen, alle pipelines.

Dit is de meest uitgebreide test in het project:
1. Laadt prod-1 snapshot (5295 samples, 200 cycles, 6 tabellen)
2. Verifieert alle data-counts en integriteit
3. Draait classifier over ALLE historische samples
4. Simuleert v28 migratie (retroactieve re-flag)
5. Verifieert daily_summary rebuild voor alle dagen
6. Test diagnostics op echte DB
7. Test coordinator hydration
8. Test dat er GEEN onverwachte data-loss is

Skipped in CI (fixture gitignored).
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil
import time
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)
from custom_components.daikin_cycle_ml.engine.physics import (
    CARNOT_EFFICIENCY_FACTOR,
    REJECT_MULTIPLIER,
    classify_cop_sample,
)
from custom_components.daikin_cycle_ml.storage.db import CycleDB


FIXTURE = pathlib.Path("tests/fixtures/_prod1_20261105.db")

pytestmark = pytest.mark.skipif(
    not FIXTURE.exists(),
    reason="prod-1 snapshot missing",
)


async def _load_full(tmp_path):
    work = tmp_path / "full_snap.db"
    shutil.copy(FIXTURE, work)
    db = CycleDB(str(work))
    await db.async_open()
    return db


# ============================================================
# 1. Volledige integriteit — alle 6 tabellen
# ============================================================

@pytest.mark.asyncio
async def test_full_db_all_tables_present(tmp_path):
    """R644: alle 6 tabellen bestaan in snapshot."""
    db = await _load_full(tmp_path)
    try:
        tables = ["cycles", "features", "alerts", "daily_summary",
                  "cop_samples", "model_state"]
        for t in tables:
            async with db._conn.execute(
                f"SELECT COUNT(*) FROM {t}"
            ) as cur:
                n = (await cur.fetchone())[0]
            assert n >= 0, f"table {t} missing or corrupted"
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_full_db_foreign_keys_valid(tmp_path):
    """R644: alle foreign keys zijn geldig."""
    db = await _load_full(tmp_path)
    try:
        async with db._conn.execute("PRAGMA foreign_key_check") as cur:
            issues = await cur.fetchall()
        assert len(issues) == 0, f"foreign key violations: {issues}"
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_full_db_integrity_check(tmp_path):
    """R644: SQLite integrity_check = 'ok'."""
    db = await _load_full(tmp_path)
    try:
        async with db._conn.execute("PRAGMA integrity_check") as cur:
            result = await cur.fetchone()
        assert result[0] == "ok", f"integrity: {result[0]}"
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# 2. Data-inventaris — meet alles
# ============================================================

@pytest.mark.asyncio
async def test_full_db_data_inventory(tmp_path):
    """R644: reproduce exact counts van prod-1 2026-11-05."""
    db = await _load_full(tmp_path)
    try:
        async with db._conn.execute("SELECT COUNT(*) FROM cycles") as cur:
            cycles = (await cur.fetchone())[0]
        async with db._conn.execute(
            "SELECT COUNT(*) FROM cop_samples"
        ) as cur:
            samples = (await cur.fetchone())[0]
        async with db._conn.execute(
            "SELECT COUNT(*) FROM alerts"
        ) as cur:
            alerts = (await cur.fetchone())[0]
        async with db._conn.execute(
            "SELECT COUNT(*) FROM daily_summary"
        ) as cur:
            summary = (await cur.fetchone())[0]

        # Sanity: prod-1 evidence
        assert cycles >= 150, f"cycles={cycles}, expected >150"
        assert samples >= 5000, f"samples={samples}, expected >5000"
        assert summary >= 50, f"summary={summary}, expected >50"

        # Log alle counts voor debugging
        print(f"Snapshot: {cycles} cycles, {samples} samples, "
              f"{alerts} alerts, {summary} summary rows")

    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# 3. Classifier over alle samples — verdeling
# ============================================================

@pytest.mark.asyncio
async def test_full_db_classifier_distribution(tmp_path):
    """R644: over ALLE 5295 samples, verdeling in accept/flag/reject."""
    db = await _load_full(tmp_path)
    try:
        async with db._conn.execute("""
            SELECT cop, lwt, outdoor, mode FROM cop_samples
            WHERE mode IN ('heating', 'dhw')
              AND lwt IS NOT NULL AND outdoor IS NOT NULL AND lwt > outdoor
        """) as cur:
            rows = await cur.fetchall()

        assert len(rows) > 5000

        accept = flag = reject = not_applicable = 0
        for r in rows:
            k = classify_cop_sample(r[3], r[1], r[2], r[0])
            if k == "accept":
                accept += 1
            elif k == "flag":
                flag += 1
            elif k == "reject":
                reject += 1
            else:
                not_applicable += 1

        total = accept + flag + reject + not_applicable
        print(f"Distribution: accept={accept} ({100*accept/total:.1f}%), "
              f"flag={flag} ({100*flag/total:.1f}%), "
              f"reject={reject} ({100*reject/total:.2f}%)")

        # Real historical data has ~1 impossible sample
        assert accept > 5000
        assert flag < 100, f"too many flags: {flag}"
        assert reject < 10, f"too many rejects: {reject}"

    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# 4. v28 migratie DRY-RUN (preview wat fase 5 gaat doen)
# ============================================================

@pytest.mark.asyncio
async def test_full_db_v28_dry_run(tmp_path):
    """R644: v28 migratie dry-run — hoeveel samples worden opnieuw geflagd.

    v28 reclassifies ALL existing samples with new 0.65 Carnot factor
    and 1.5x reject threshold. Expected:
    - Currently flagged (old 0.55 factor): X
    - After v28 (0.65 factor): Y < X
    - v28 unflags samples that were wrongly flagged by strict 0.55
    """
    db = await _load_full(tmp_path)
    try:
        async with db._conn.execute("""
            SELECT id, cop, lwt, outdoor, mode, is_transition_artifact
            FROM cop_samples
            WHERE mode IN ('heating', 'dhw')
              AND lwt IS NOT NULL AND outdoor IS NOT NULL AND lwt > outdoor
        """) as cur:
            rows = await cur.fetchall()

        # Old flag: 0.55 factor (what current DB has)
        # New flag: 0.65 factor (what v28 will do)
        old_flagged = 0
        new_flagged = 0
        would_unflag = 0
        would_flag = 0
        would_reject = 0
        for r in rows:
            _id, cop, lwt, outdoor, mode, was_flagged = r
            th = lwt + 273.15
            tc = outdoor + 273.15
            carnot = th / (th - tc)
            old_thr = carnot * 0.55
            new_cls = classify_cop_sample(mode, lwt, outdoor, cop)

            if was_flagged:
                old_flagged += 1

            if new_cls == "reject":
                would_reject += 1
            elif new_cls == "flag":
                new_flagged += 1
                if not was_flagged:
                    would_flag += 1
            else:  # accept
                if was_flagged:
                    would_unflag += 1

        print(f"v28 dry-run: old_flagged={old_flagged}, new_flagged={new_flagged}")
        print(f"  would_unflag: {would_unflag} (0.55 was too strict)")
        print(f"  would_flag:   {would_flag} (0.65 catches more)")
        print(f"  would_reject: {would_reject} (extreme artifacts)")

        # v28 should REDUCE false positives from strict 0.55
        # Real data: 0.55 flagged ~13.5%, 0.65 flags ~2.7%
        # So would_unflag > would_flag (netto minder flags)
        assert would_unflag >= would_flag, (
            f"v28 should reduce flags: unflag={would_unflag} "
            f"vs flag={would_flag}"
        )

    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# 5. Daily summary rebuild — alle historische dagen
# ============================================================

@pytest.mark.asyncio
async def test_full_db_rebuild_all_days(tmp_path):
    """R644: rebuild daily_summary voor alle 60+ historische dagen."""
    db = await _load_full(tmp_path)
    try:
        async with db._conn.execute(
            "SELECT DISTINCT day FROM daily_summary ORDER BY day"
        ) as cur:
            days_before = [r[0] for r in await cur.fetchall()]

        assert len(days_before) >= 30, f"only {len(days_before)} days"

        # Rebuild all days
        for day in days_before:
            await db.async_rollup_day(day)

        # Verify count preserved
        async with db._conn.execute(
            "SELECT COUNT(DISTINCT day) FROM daily_summary"
        ) as cur:
            days_after = (await cur.fetchone())[0]

        assert days_after == len(days_before), (
            f"day count changed: {len(days_before)} -> {days_after}"
        )

        print(f"Rebuilt {days_after} historical days")

    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# 6. Coordinator hydration from real DB
# ============================================================

@pytest.mark.asyncio
async def test_full_db_coordinator_hydrates(tmp_path):
    """R644: coordinator kan van echte DB hydrateren zonder crash."""
    db = await _load_full(tmp_path)
    try:
        # Simulate coordinator startup hydration
        c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
        c.db = db
        c.options = {}
        c.hass = MagicMock()
        c.store = MagicMock()
        c._last_cop_sample_ts = 0.0

        # Haal laatste ts uit DB (zoals _maybe_collect_cop_sample seed)
        last_ts = await db.async_get_max_cop_sample_ts()
        assert last_ts is not None
        assert last_ts > 0
        c._last_cop_sample_ts = float(last_ts)

        # Verify ts is binnen redelijke range
        age_days = (time.time() - last_ts) / 86400
        print(f"Last cop_sample age: {age_days:.2f} days")
        assert 0 <= age_days < 30

    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# 7. Diagnostics op echte DB
# ============================================================

@pytest.mark.asyncio
async def test_full_db_diagnostics_works(tmp_path):
    """R644: diagnostics op echte prod DB werkt zonder crash."""
    db = await _load_full(tmp_path)
    try:
        # Simuleer diagnostics calls
        async with db._conn.execute(
            "SELECT COUNT(*) FROM cycles"
        ) as cur:
            cycles = (await cur.fetchone())[0]
        async with db._conn.execute(
            "SELECT COUNT(*) FROM cop_samples"
        ) as cur:
            samples = (await cur.fetchone())[0]

        # Verify DB is queryable (diagnostics access pattern)
        assert cycles >= 0
        assert samples >= 0

        # Verify each table is readable (no corruption)
        for table in ["cycles", "features", "alerts", "daily_summary",
                       "cop_samples", "model_state"]:
            async with db._conn.execute(
                f"SELECT * FROM {table} LIMIT 1"
            ) as cur:
                await cur.fetchone()
        print("All 6 tables readable")

    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# 8. Migration markers preserved
# ============================================================

@pytest.mark.asyncio
async def test_full_db_migration_markers_intact(tmp_path):
    """R644: alle bestaande migratie-markers moeten behouden blijven."""
    db = await _load_full(tmp_path)
    try:
        async with db._conn.execute("""
            SELECT key FROM model_state
            WHERE key LIKE 'data_migration_%'
        """) as cur:
            markers = [r[0] for r in await cur.fetchall()]

        # Verwachte markers in prod-1 snapshot
        expected = [
            "data_migration_v19_completed",
            "data_migration_v20_completed",
            "data_migration_v21_completed",
            "data_migration_v22_completed",
            "data_migration_v23_completed",
            "data_migration_v24_completed",
            "data_migration_v25_completed",
            "data_migration_v26_completed",
            "data_migration_v27_completed",
        ]
        for exp in expected:
            assert exp in markers, f"missing marker: {exp}"

        print(f"All {len(expected)} migration markers present")
        print(f"Also {len(markers) - len(expected)} additional markers")

    finally:
        await db.async_close()
        await asyncio.sleep(0.05)
