"""Issue #313: backfill must re-score cycles with quality_score=0.

Prod-1 evidence (2026-11-02): #263 (663.6min heating, dT=3.0, buh=1) and
#261 (2min heating, dT=1.4, buh=1, transient) had quality_score=0 while
the current score_cycle() returns 70 and 40.

Root cause: async_backfill_quality_scores only matched `quality_score IS NULL`.
Fix: WHERE now includes `quality_score = 0`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.engine.quality_scorer import score_cycle

PROD1_OPTIONS = {
    "good_run_threshold_min": 45,
    "good_dt_threshold_k": 5.0,
    "good_off_threshold_min": 20,
    "short_cycle_ratio_threshold": 50,
}


def _prod1_cycle_263() -> dict:
    return {
        "id": 263, "start_ts": 1793660357.71422, "end_ts": 1793700175.7143743,
        "duration_s": 39818, "mode": "heating", "dT_max": 3.0,
        "dT_avg": 1.925, "rps_max": 41, "rps_avg": 21.25,
        "outdoor_temp": 8.3, "buh_used": 1, "defrost_used": 1,
        "is_transient": 0, "dhw_tank_temp": None,
    }


def _prod1_cycle_261() -> dict:
    return {
        "id": 261, "start_ts": 1793639618.0, "end_ts": 1793639738.0,
        "duration_s": 120, "mode": "heating", "dT_max": 1.4,
        "dT_avg": 1.0, "rps_max": 18, "rps_avg": 12.0,
        "outdoor_temp": 8.5, "buh_used": 1, "defrost_used": 1,
        "is_transient": 1, "dhw_tank_temp": None,
    }


def test_cycle_263_current_score_is_70_not_zero():
    assert score_cycle(_prod1_cycle_263(), PROD1_OPTIONS) == 70


def test_cycle_261_current_score_is_40_not_zero():
    assert score_cycle(_prod1_cycle_261(), PROD1_OPTIONS) == 40


# --- backfill integration ---

@pytest.mark.asyncio
async def test_backfill_rescores_zero_quality_cycles(tmp_path: Path) -> None:
    """Backfill must re-score cycles with quality_score=0, not only NULL."""
    from custom_components.daikin_cycle_ml.storage.db import CycleDB

    db_path = tmp_path / "test.db"
    db = CycleDB(str(db_path))
    await db.async_open()
    await db.async_initialize()
    try:
        # Insert cycle #263 and #261 (matching prod-1). id is AUTOINCREMENT,
        # so capture the real assigned IDs after insert.
        for rec in (_prod1_cycle_263(), _prod1_cycle_261()):
            await db.async_insert_cycle(rec)
        async with db._conn.execute(
            "SELECT id FROM cycles ORDER BY start_ts"
        ) as cur:
            real_ids = [r[0] for r in await cur.fetchall()]
        assert len(real_ids) == 2
        id_263, id_261 = real_ids  # start_ts order: 261 before 263
        # #261 has start_ts 1793639618 < #263 1793660357, so id_263=second
        id_261, id_263 = real_ids  # chronological order

        # Simulate stale 0
        await db._conn.execute("UPDATE cycles SET quality_score = 0")
        await db._conn.commit()

        def scorer(r: dict) -> int:
            return score_cycle(r, PROD1_OPTIONS)

        updated = await db.async_backfill_quality_scores(scorer)
        assert updated == 2, f"expected 2 re-scores, got {updated}"

        async with db._conn.execute(
            "SELECT id, quality_score FROM cycles ORDER BY id"
        ) as cur:
            rows = await cur.fetchall()
        scores = dict(rows)
        assert scores[id_263] == 70, f"cycle #263 (db id={id_263}) expected 70, got {scores[id_263]}"
        assert scores[id_261] == 40, f"cycle #261 (db id={id_261}) expected 40, got {scores[id_261]}"
    finally:
        await db.async_close()
