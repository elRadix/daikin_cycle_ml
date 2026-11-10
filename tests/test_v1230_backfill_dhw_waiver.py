"""Issue #313: backfill must apply #289 legionella BUH waiver for
historical DHW cycles with tank_temp >= 60C. Pre-fix SELECT omitted
`dhw_tank_temp` so the waiver silently failed and applied -10.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.engine.quality_scorer import score_cycle

OPTIONS = {
    "good_run_threshold_min": 45, "good_dt_threshold_k": 5.0,
    "good_off_threshold_min": 20, "short_cycle_ratio_threshold": 50,
    "buh_penalty_legionella_waived": 1.0,
}


def _dhw(tank_temp):
    return {
        "duration_s": 3600, "mode": "dhw", "dT_max": 8.0,
        "buh_used": 1, "defrost_used": 0, "dhw_tank_temp": tank_temp,
    }


def test_dhw_legionella_waiver_applies_with_tank_62c():
    assert score_cycle(_dhw(62.0), OPTIONS) == 100


def test_dhw_buh_penalty_applies_with_tank_55c():
    assert score_cycle(_dhw(55.0), OPTIONS) == 90


def test_dhw_buh_penalty_applies_when_tank_temp_missing():
    assert score_cycle(_dhw(None), OPTIONS) == 90


def test_dhw_legionella_waiver_disabled():
    opts = dict(OPTIONS, buh_penalty_legionella_waived=0.0)
    assert score_cycle(_dhw(62.0), opts) == 90


# --- backfill integration: dhw_tank_temp is passed through ---

@pytest.mark.asyncio
async def test_backfill_applies_legionella_waiver_from_db(tmp_path: Path) -> None:
    """Cycle with buh=1 + dhw_tank_temp=62 must NOT lose -10 on backfill."""
    from custom_components.daikin_cycle_ml.storage.db import CycleDB

    db_path = tmp_path / "test.db"
    db = CycleDB(str(db_path))
    await db.async_open()
    await db.async_initialize()
    try:
        rec = _dhw(62.0)
        rec["start_ts"] = 1793660357.0
        rec["end_ts"] = 1793663957.0
        await db.async_insert_cycle(rec)

        await db._conn.execute("UPDATE cycles SET quality_score = 0")
        await db._conn.commit()

        def scorer(r: dict) -> int:
            return score_cycle(r, OPTIONS)
        updated = await db.async_backfill_quality_scores(scorer)
        assert updated == 1

        async with db._conn.execute("SELECT quality_score FROM cycles") as cur:
            row = await cur.fetchone()
        assert row[0] == 100, f"waiver failed: got {row[0]}, expected 100"
    finally:
        await db.async_close()
