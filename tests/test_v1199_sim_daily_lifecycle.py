"""v1.19.9 R645: 48h daily-lifecycle simulation.

Simuleert een volledige dagcyclus zoals productie die ziet:
- Ochtend heating opstart
- Middag DHW run
- Namiddag heating herstart
- Nacht idle
- Volgende ochtend herstart
- Cross-midnight cycle (heating loopt over 00:00)

Vangt bugs die enkel snapshot-metingen niet zien: mode-detectie
ketens, dag-grens reset, SETTLE-blokkades over uren.
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator)
from tests.test_rollup_concurrency import _mk_db
from tests.test_v1199_cop_gate_wire import (  # noqa: F401
    _mk_gate_coord)


# Vaste dag voor reproduceerbaarheid: 2026-11-05 00:00 LOCAL (Brussels).
# mktime interprets 9-tuple as local time, so this is container-local
# midnight. Ensures day boundaries match async_rollup_day's
# time.strptime(day, "%Y-%m-%d") with mktime (also local).
DAY_START_TS = time.mktime((2026, 11, 5, 0, 0, 0, 0, 0, -1))


@pytest.mark.asyncio
async def test_sim_48h_mode_transitions_block_settle(tmp_path, patched_compat):
    """48h met 6 mode-transitions, verify SETTLE blokkeert consistent."""
    db = await _mk_db(tmp_path)
    try:
        c = _mk_gate_coord(db, cop=5.0, lwt=30.0, outdoor=10.0)
        c._last_mode_change_ts = 0.0
        c._last_observed_mode = ""
        c._last_cop_sample_ts = 0.0

        # Timeline: t=0 heating, t=6h dhw, t=7h heating, t=24h dhw, t=25h heating
        timeline = [
            (0, "heating"),
            (6 * 3600, "dhw"),
            (7 * 3600, "heating"),
            (24 * 3600, "dhw"),
            (25 * 3600, "heating"),
        ]
        now_base = DAY_START_TS

        blocked = 0
        accepted = 0
        for dt, mode in timeline:
            t = now_base + dt
            snap = SimpleNamespace(mode=mode)
            c._track_mode_transition(snap, now=t)

        # Na alle transities: laagste ts van mode_change
        # = laatste transitie = t=25h
        last_change = now_base + 25 * 3600
        assert c._last_mode_change_ts == last_change

        # COP-sample binnen 100s van laatste transitie -> blocked
        c._last_cop_sample_ts = 0.0
        await c._maybe_collect_cop_sample(last_change + 100)
        async with db._conn.execute(
            "SELECT COUNT(*) FROM cop_samples"
        ) as cur:
            n = (await cur.fetchone())[0]
        assert n == 0, f"SETTLE should block, got {n} rows"

        # COP-sample na 400s -> accepted
        c._last_cop_sample_ts = 0.0
        await c._maybe_collect_cop_sample(last_change + 400)
        async with db._conn.execute(
            "SELECT COUNT(*) FROM cop_samples"
        ) as cur:
            n = (await cur.fetchone())[0]
        assert n == 1, f"SETTLE should allow, got {n} rows"

    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_sim_48h_alert_once_per_day(tmp_path, patched_compat):
    """2 dagen: reject-counter reset om middernacht -> alert 2x."""
    db = await _mk_db(tmp_path)
    try:
        c = _mk_gate_coord(db, cop=100.0, lwt=30.0, outdoor=5.0)
        c._runtime_day_key = "2026-11-05"
        c._energy_day_key = "2026-11-05"
        c._cop_rejected_today_count = 0
        c._cop_rejected_today_first_ts = 0.0
        c._cop_rejected_day_key = "2026-11-05"
        c._buh_step1_s = 0.0
        c._buh_step2_s = 0.0
        c._prev_defrost = False
        c._defrost_start_ts = None
        c._defrost_count_today = 0
        c._defrost_duration_s = 0.0
        c._energy_acc = {}
        c._energy_hwm = {}

        # Dag 1: 2 rejects
        for i in range(2):
            c._last_cop_sample_ts = 0.0
            await c._maybe_collect_cop_sample(DAY_START_TS + 3600 + i * 100)
        assert c._cop_rejected_today_count == 2

        # Dag-grens: ga naar volgende dag
        next_day = time.mktime((2026, 11, 6, 1, 0, 0, 0, 0, -1))
        c._maybe_reset_daily_accumulators(next_day)
        assert c._cop_rejected_today_count == 0
        assert c._cop_rejected_day_key == "2026-11-06"

        # Dag 2: 1 reject
        c._last_cop_sample_ts = 0.0
        await c._maybe_collect_cop_sample(next_day + 3600)
        assert c._cop_rejected_today_count == 1

    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_sim_cross_midnight_heating_cycle(tmp_path):
    """Cross-midnight cycle: 22:00 → 04:00, no duplicate cycle counts."""
    db = await _mk_db(tmp_path)
    try:
        # Cycle start 22:00 day 1, ends 04:00 day 2
        # DAY_START_TS = local midnight, so +22h = 22:00, +6h = next day 04:00
        start = DAY_START_TS + 22 * 3600
        end = start + 6 * 3600

        await db.async_insert_cycle({
            "start_ts": start, "end_ts": end,
            "duration_s": 6 * 3600,
            "mode": "heating", "outdoor_temp": 5.0,
            "dT_max": 5.0, "dT_avg": 4.0,
            "rps_max": 40.0, "rps_avg": 30.0,
            "buh_used": 0, "defrost_used": 0, "quality_score": 85,
        })

        # Rollup both days
        await db.async_rollup_day("2026-11-05")
        await db.async_rollup_day("2026-11-06")

        rows = await db.async_daily_summary(days=7)
        by = {(r["day"], r["mode"]): r for r in rows}

        # Both days should have heating entries
        assert ("2026-11-05", "heating") in by
        assert ("2026-11-06", "heating") in by

        # Pro-rata: 2h on day1 (22:00-00:00), 4h on day2 (00:00-04:00)
        d1_h = by[("2026-11-05", "heating")]["total_duration_s"] / 3600
        d2_h = by[("2026-11-06", "heating")]["total_duration_s"] / 3600
        assert abs(d1_h - 2.0) < 0.01, f"day1 = {d1_h}h, expected 2h"
        assert abs(d2_h - 4.0) < 0.01, f"day2 = {d2_h}h, expected 4h"
        # Total = 6h (nothing lost)
        assert abs((d1_h + d2_h) - 6.0) < 0.01

    finally:
        await db.async_close()
        await asyncio.sleep(0.05)
