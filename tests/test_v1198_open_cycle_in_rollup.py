"""v1.19.8 #262: open cycles in daily_summary + startup backfill."""
from __future__ import annotations

import asyncio
import time

from tests.test_rollup_concurrency import _mk_db


async def test_rollup_includes_open_cycle(tmp_path):
    """v1.19.8 #262: open cycles (end_ts=NULL) contribute pro-rata runtime.

    Real prod 2026-11-05 08:17: closed cycle 280 (Nov4 13:13 -> Nov5 07:03)
    + open cycle since 07:05. Pre-fix daily_summary=0.98h; actual=7.06h.
    """
    db = await _mk_db(tmp_path)
    try:
        now = time.time()
        lt = time.localtime(now)
        today_start = time.mktime(
            (lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)
        )
        today_str = time.strftime("%Y-%m-%d", lt)

        await db.async_insert_cycle({
            "start_ts": today_start + 3600,
            "end_ts": today_start + 7200,
            "duration_s": 3600,
            "mode": "heating", "outdoor_temp": 8.0,
            "dT_max": 5.0, "dT_avg": 4.0, "rps_max": 40.0, "rps_avg": 30.0,
            "buh_used": 0, "defrost_used": 0, "quality_score": 90,
        })
        await db.async_insert_cycle({
            "start_ts": now - 3600,
            "end_ts": None,
            "duration_s": None,
            "mode": "heating", "outdoor_temp": 8.0,
            "dT_max": 5.0, "dT_avg": 4.0, "rps_max": 40.0, "rps_avg": 30.0,
            "buh_used": 0, "defrost_used": 0, "quality_score": 90,
        })

        await db.async_rollup_day(today_str)
        rows = await db.async_daily_summary(days=1)
        heating = next(
            (r for r in rows if r["mode"] == "heating"), None
        )
        assert heating is not None, "no heating row"
        assert heating["total_duration_s"] >= 7000, (
            f"open cycle NOT included: total={heating['total_duration_s']}s, "
            f"expected >=7000 (3600 closed + ~3600 open)"
        )
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


async def test_backfill_rolls_last_7_days(tmp_path):
    """v1.19.8 #262: startup backfill re-rolls recent days."""
    db = await _mk_db(tmp_path)
    try:
        now = time.time()
        lt = time.localtime(now)
        today_start = time.mktime(
            (lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)
        )
        expected_days = []
        for off in [0, 2 * 86400, 5 * 86400]:
            day_start = today_start - off
            day_str = time.strftime(
                "%Y-%m-%d", time.localtime(day_start)
            )
            expected_days.append(day_str)
            await db.async_insert_cycle({
                "start_ts": day_start + 3600,
                "end_ts": day_start + 7200,
                "duration_s": 3600,
                "mode": "heating", "outdoor_temp": 8.0,
                "dT_max": 5.0, "dT_avg": 4.0,
                "rps_max": 40.0, "rps_avg": 30.0,
                "buh_used": 0, "defrost_used": 0,
                "quality_score": 90,
            })

        rebuilt = await db.async_backfill_daily_summary_recent(days=7)
        assert rebuilt == 7, f"expected 7, got {rebuilt}"

        all_rows = await db.async_daily_summary(days=7)
        by_key = {(r["day"], r["mode"]): r for r in all_rows}
        for day_str in expected_days:
            key = (day_str, "heating")
            assert key in by_key, f"missing daily_summary for {day_str}"
            assert by_key[key]["total_duration_s"] == 3600, (
                f"{day_str} total={by_key[key]['total_duration_s']}s"
            )
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


def test_merge_block_contains_rollup_call():
    """v1.19.8 #262 regression guard.

    Any early return inside the forward-merge block must be preceded by
    _maybe_rollup_day. Prevents re-introducing the bug that left
    daily_summary frozen on the pre-merge snapshot for 7.5h.
    """
    import inspect
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
    )
    src = inspect.getsource(DaikinCycleMLCoordinator._process_new_cycle)
    lines = src.split("\n")
    merge_ln = next(
        (i for i, ln in enumerate(lines) if "forward-merged" in ln), None
    )
    assert merge_ln is not None, "forward-merged debug log not found"
    window = "\n".join(lines[merge_ln:merge_ln + 20])
    assert "_maybe_rollup_day" in window, (
        f"forward-merge block (lines {merge_ln}-{merge_ln + 20}) does NOT "
        f"call _maybe_rollup_day. v1.19.8 #262 regression."
    )
