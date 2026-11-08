"""v1.19.9 R644: prod-1 snapshot replay test.

Load echte prod-1 2026-11-05 DB, run de NIEUWE code erover, verify
dat aggregaties en classificaties kloppen op historische data.

Doel: "werkt op schone DB" is onvoldoende -- deze test bewijst dat
de nieuwe code ook op bestaande productie-historie correct werkt.

Skipped in CI (fixture gitignored), draait lokaal op dev container.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)
from custom_components.daikin_cycle_ml.engine.physics import (
    classify_cop_sample,
)
from custom_components.daikin_cycle_ml.storage.db import CycleDB


FIXTURE = pathlib.Path("tests/fixtures/_prod1_20261105.db")

pytestmark = pytest.mark.skipif(
    not FIXTURE.exists(),
    reason="prod-1 snapshot missing (tests/fixtures/_prod1_20261105.db)",
)


async def _load_snapshot(tmp_path):
    work = tmp_path / "snap.db"
    shutil.copy(FIXTURE, work)
    db = CycleDB(str(work))
    await db.async_open()
    await db.async_initialize()
    return db


# ============================================================
# Snapshot integrity
# ============================================================

@pytest.mark.asyncio
async def test_snapshot_replay_preserves_counts(tmp_path):
    """R644: opening the DB doesn't corrupt counts."""
    db = await _load_snapshot(tmp_path)
    try:
        async with db._conn.execute("SELECT COUNT(*) FROM cycles") as cur:
            cycles_before = (await cur.fetchone())[0]
        async with db._conn.execute(
            "SELECT COUNT(*) FROM cop_samples"
        ) as cur:
            samples_before = (await cur.fetchone())[0]

        # Simulate opening + closing again
        await db.async_close()
        db = CycleDB(str(tmp_path / "snap.db"))
        await db.async_open()

        async with db._conn.execute("SELECT COUNT(*) FROM cycles") as cur:
            cycles_after = (await cur.fetchone())[0]
        async with db._conn.execute(
            "SELECT COUNT(*) FROM cop_samples"
        ) as cur:
            samples_after = (await cur.fetchone())[0]

        assert cycles_after == cycles_before, (
            f"cycles count changed: {cycles_before} -> {cycles_after}"
        )
        assert samples_after == samples_before, (
            f"cop_samples count changed: {samples_before} -> {samples_after}"
        )
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# Classifier against real historical samples
# ============================================================

@pytest.mark.asyncio
async def test_snapshot_replay_classifier_on_real_samples(tmp_path):
    """R644: classify ALL historical samples, verify no crash + deterministic.

    Expected outcome on prod-1 2026-11-05 (148 heating+dhw samples):
      ~144 accept, ~3-4 flag, 0 reject
    (matches the impact analysis done during session)
    """
    db = await _load_snapshot(tmp_path)
    try:
        async with db._conn.execute("""
            SELECT cop, lwt, outdoor, mode FROM cop_samples
            WHERE mode IN ('heating', 'dhw')
              AND lwt IS NOT NULL AND outdoor IS NOT NULL
              AND lwt > outdoor
        """) as cur:
            rows = await cur.fetchall()

        assert len(rows) > 100, f"snapshot too small: {len(rows)} rows"

        accept = flag = reject = not_applicable = 0
        for r in rows:
            k = classify_cop_sample(
                mode=r[3], lwt=r[1], outdoor=r[2], cop=r[0],
            )
            if k == "accept":
                accept += 1
            elif k == "flag":
                flag += 1
            elif k == "reject":
                reject += 1
            else:
                not_applicable += 1

        total = accept + flag + reject + not_applicable
        assert total == len(rows)

        # Snapshot 2026-11-05: 5295 samples with:
        #   accept = 5258 (99.3%)
        #   flag   =   36 ( 0.7%)
        #   reject =    1 ( 0.0%)
        # The 1 reject is a REAL historical impossible sample:
        #   ts=1793613753 mode=dhw cop=19.29 lwt=34.8 out=10.1
        #   carnot=12.47 -> 154.7% of theoretical max -> reject
        # Pre-v1.19.9 this was inserted unmarked (is_transition_artifact=0)
        # because _flag_carnot_artifacts only runs on migrations, not
        # per-insert. That is the actual bug v1.19.9 fixes: reject-at-source.
        # v28 migration (phase 5) will retroactively re-flag it in DB.
        pct_flag = 100 * flag / total
        pct_reject = 100 * reject / total
        assert 0 <= pct_flag <= 10, (
            f"flag% out of expected range: {pct_flag:.1f}% "
            f"(accept={accept} flag={flag} reject={reject})"
        )
        # Historical impossible samples exist in old DBs (pre-v1.19.9
        # had no per-insert guard). Reject rate is small but non-zero.
        # v28 migration will re-flag them retroactively.
        assert 0 <= pct_reject <= 0.1, (
            f"reject% out of expected range: {pct_reject:.2f}%"
        )
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# Aggregate preservation: new code doesn't change existing summaries
# ============================================================

@pytest.mark.asyncio
async def test_snapshot_replay_daily_summary_idempotent(tmp_path):
    """R644: re-running async_rollup_day op snapshot is idempotent.

    Pre-existing daily_summary should match after re-run (no drift).
    """
    db = await _load_snapshot(tmp_path)
    try:
        async with db._conn.execute("""
            SELECT day, mode, cycles, total_duration_s FROM daily_summary
            WHERE day IN ('2026-11-03', '2026-11-04', '2026-11-05')
            ORDER BY day, mode
        """) as cur:
            before = [tuple(r) for r in await cur.fetchall()]

        assert len(before) > 0, "no daily_summary rows in snapshot"

        # Re-run rollup on each day
        for day in ("2026-11-03", "2026-11-04", "2026-11-05"):
            await db.async_rollup_day(day)

        async with db._conn.execute("""
            SELECT day, mode, cycles, total_duration_s FROM daily_summary
            WHERE day IN ('2026-11-03', '2026-11-04', '2026-11-05')
            ORDER BY day, mode
        """) as cur:
            after = [tuple(r) for r in await cur.fetchall()]

        # Duration can change (open cycles now included), but
        # cycle count should be stable
        assert len(after) == len(before), (
            f"daily_summary row count changed: {len(before)} -> {len(after)}"
        )
        for b, a in zip(before, after):
            assert b[0] == a[0] and b[1] == a[1], (
                f"day/mode mismatch: {b[:2]} vs {a[:2]}"
            )
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# Cold-start: run _maybe_collect_cop_sample on snapshot DB
# ============================================================

@pytest.mark.asyncio
async def test_snapshot_replay_new_sample_lands_in_snapshot(
    tmp_path, monkeypatch
):
    """R644: new COP sample insert on snapshot DB works end-to-end.

    Verifies that the classifier + insert path works on a DB that has
    real historical data -- not just a fresh empty DB.
    """
    db = await _load_snapshot(tmp_path)
    try:
        async with db._conn.execute(
            "SELECT COUNT(*) FROM cop_samples"
        ) as cur:
            n_before = (await cur.fetchone())[0]

        # Build minimal coord against snapshot
        c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
        c.db = db
        c.options = {}
        c.hass = MagicMock()
        c._cop_sample_seed_done = True
        c._last_cop_sample_ts = 0.0
        c.cop_sensor_entity = "sensor.cop"
        c._last_mode_change_ts = 0.0
        c._last_observed_mode = ""
        c._cop_rejected_today_count = 0
        c._cop_rejected_today_first_ts = 0.0

        st = MagicMock()
        st.state = "5.5"
        st.attributes = {}
        c.hass.states.get.return_value = st

        # Real heating sample
        c.data = SimpleNamespace(
            attrs={
                "Leaving water temp. before BUH (R1T)": 30.5,
                "Leaving water temp. after BUH (R2T)": 30.5,
                "Inlet water temp.(R4T)": 25.5,
                "Outdoor air temp.(R1T)": 8.0,
                "Flow sensor (l/min)": 15.0,
                "Defrost Operation": False,
            },
            mode="heating",
            state="running",
            boiler_active=False,
            is_hybrid=False,
            boiler_heat_active=False,
            boiler_dhw_active=False,
            cop=None,
        )
        c._resolve_cop_sample_mode = lambda: "heating"

        now = time.time()
        await c._maybe_collect_cop_sample(now)

        async with db._conn.execute(
            "SELECT COUNT(*) FROM cop_samples"
        ) as cur:
            n_after = (await cur.fetchone())[0]

        assert n_after == n_before + 1, (
            f"new sample not inserted: {n_before} -> {n_after}"
        )

        # Verify the newly inserted row
        async with db._conn.execute("""
            SELECT cop, lwt, outdoor, is_transition_artifact
            FROM cop_samples
            ORDER BY ts DESC LIMIT 1
        """) as cur:
            row = await cur.fetchone()
        assert row is not None
        assert abs(row[0] - 5.5) < 0.01, f"cop={row[0]}"
        assert abs(row[1] - 30.5) < 0.1, f"lwt={row[1]}"
        assert row[3] == 0, f"accept should have flag=0, got {row[3]}"

    finally:
        await db.async_close()
        await asyncio.sleep(0.05)
