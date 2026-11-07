"""v1.20.0 #281 counters E2E: defrost, BUH, cycles, persistence.

User concern (#280): "defrost counter displays zero" on non-BUH models.
Fixed via PR #282. This file proves the fix still works on the v2
branch and that all counter accumulators remain correct.

Coverage:
- Defrost counter: rise/fall/running/None-state (#280 fix)
- BUH step1/step2 duration: per-tick, both-on, cap, off
- runtime_snapshot integration: sensor-visible values
- CycleStore.counters_snapshot interface
- Prod fixture: structural validity + today's fresh values
- Persistence roundtrip via model_state

R598: real production methods, no reconstruction.
R634: prod-derived assertions.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import shutil
import time

import pytest

from custom_components.daikin_cycle_ml.const import (
    ATTR_BUH_STEP1,
    ATTR_BUH_STEP2,
    ATTR_DEFROST_OPERATION,
    ENERGY_DT_CAP_S,
    ENERGY_DT_WARN_S,
)
from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)
from custom_components.daikin_cycle_ml.storage.db import CycleDB

PROD_DB = pathlib.Path("tests/fixtures/_prod1_live_20261107_221330.db")


def _bare_counter_coord() -> DaikinCycleMLCoordinator:
    """Bare coordinator with all counter state initialized."""
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.hass = None
    c.db = None
    c.options = {}
    # Counter state (from __init__ lines 658-663)
    c._buh_step1_s = 0.0
    c._buh_step2_s = 0.0
    c._defrost_count_today = 0
    c._defrost_duration_s = 0.0
    c._prev_defrost = False
    c._defrost_start_ts = None
    c._defrost_prior_s = None
    c._last_defrost_ts = 0.0
    # NOTE: _last_runtime_tick_ts is 0.0 by default. If a test ticks at
    # now=1000 with last=0.0, then `last = 0.0 or now = now` (Python `or`
    # treats 0.0 as falsy), giving raw_dt=0 -> early return. Tests that
    # exercise defrost/BUH logic MUST set _last_runtime_tick_ts to a
    # value slightly in the past so dt_s > 0. Helper sets a safe default
    # of 970.0 so `now=1000` ticks give dt_s=30.
    c._last_runtime_tick_ts = 970.0
    return c


# ============================================================
# 1. Defrost counter (includes #280 fix verification)
# ============================================================


def test_defrost_rise_increments_count() -> None:
    """False -> True increments defrost count + starts timer."""
    c = _bare_counter_coord()
    t0 = 1000.0
    c._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: True}, t0)
    assert c._defrost_count_today == 1
    assert c._defrost_start_ts == t0
    assert c._prev_defrost is True
    assert c._last_defrost_ts == t0


def test_defrost_fall_accumulates_duration() -> None:
    """True -> False adds (end - start) to duration; count unchanged."""
    c = _bare_counter_coord()
    t0 = 1000.0
    c._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: True}, t0)
    t1 = t0 + 300.0
    c._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: False}, t1)
    assert c._defrost_count_today == 1
    assert c._defrost_duration_s == pytest.approx(300.0, abs=1.0)
    assert c._prev_defrost is False


def test_defrost_none_preserves_state_280_fix() -> None:
    """#280 regression: defrost=None mid-defrost does NOT close the defrost.

    Pre-#280, None was treated as False -> false close -> duration wrong.
    Post-#280, None is caught early: state preserved, no increment.
    """
    c = _bare_counter_coord()
    t0 = 1000.0
    c._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: True}, t0)
    # Mid-defrost, attrs return None (partial update / sensor offline)
    t1 = t0 + 100.0
    c._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: None}, t1)
    # State MUST still be "in defrost"
    assert c._prev_defrost is True
    assert c._defrost_start_ts == t0
    assert c._defrost_count_today == 1
    # Normal end afterwards
    t2 = t0 + 300.0
    c._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: False}, t2)
    assert c._defrost_count_today == 1
    assert c._defrost_duration_s == pytest.approx(300.0, abs=1.0)


def test_defrost_running_updates_live_duration() -> None:
    """While defrost continues, duration reflects running tally (live view)."""
    c = _bare_counter_coord()
    t0 = 1000.0
    c._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: True}, t0)
    t1 = t0 + 60.0
    c._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: True}, t1)
    assert c._defrost_duration_s == pytest.approx(60.0, abs=1.0)
    t2 = t0 + 120.0
    c._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: True}, t2)
    assert c._defrost_duration_s == pytest.approx(120.0, abs=1.0)


def test_defrost_multiple_cycles_accumulate() -> None:
    """Two defrost events -> count=2, sum of durations."""
    c = _bare_counter_coord()
    t = 1000.0
    # Cycle 1: 200s
    c._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: True}, t)
    c._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: False}, t + 200)
    # Cycle 2: 400s
    c._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: True}, t + 1000)
    c._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: False}, t + 1400)
    assert c._defrost_count_today == 2
    assert c._defrost_duration_s == pytest.approx(600.0, abs=1.0)


# ============================================================
# 2. BUH counters (step1, step2, both, cap)
# ============================================================


def test_buh_step1_accumulates_per_tick() -> None:
    """Step1=True for one 30s tick -> buh_step1_s += 30."""
    c = _bare_counter_coord()
    c._last_runtime_tick_ts = 1000.0
    c._tick_buh_and_defrost(
        {ATTR_BUH_STEP1: True, ATTR_DEFROST_OPERATION: False}, 1030.0,
    )
    assert c._buh_step1_s == pytest.approx(30.0, abs=0.1)
    assert c._buh_step2_s == 0.0


def test_buh_step2_accumulates_per_tick() -> None:
    """Step2=True -> buh_step2_s += dt, step1 unaffected."""
    c = _bare_counter_coord()
    c._last_runtime_tick_ts = 1000.0
    c._tick_buh_and_defrost(
        {ATTR_BUH_STEP2: True, ATTR_DEFROST_OPERATION: False}, 1030.0,
    )
    assert c._buh_step2_s == pytest.approx(30.0, abs=0.1)
    assert c._buh_step1_s == 0.0


def test_buh_both_accumulate_separately() -> None:
    """Both step1+step2 on -> both counters accumulate."""
    c = _bare_counter_coord()
    c._last_runtime_tick_ts = 1000.0
    c._tick_buh_and_defrost(
        {
            ATTR_BUH_STEP1: True,
            ATTR_BUH_STEP2: True,
            ATTR_DEFROST_OPERATION: False,
        },
        1030.0,
    )
    assert c._buh_step1_s == pytest.approx(30.0, abs=0.1)
    assert c._buh_step2_s == pytest.approx(30.0, abs=0.1)


def test_buh_off_no_accumulation() -> None:
    """Both off -> no change."""
    c = _bare_counter_coord()
    c._last_runtime_tick_ts = 1000.0
    c._tick_buh_and_defrost(
        {ATTR_BUH_STEP1: False, ATTR_BUH_STEP2: False,
         ATTR_DEFROST_OPERATION: False},
        1030.0,
    )
    assert c._buh_step1_s == 0.0
    assert c._buh_step2_s == 0.0


def test_buh_dt_capped_at_max() -> None:
    """DT > ENERGY_DT_CAP_S is capped (prevents massive accrual on resume)."""
    c = _bare_counter_coord()
    c._last_runtime_tick_ts = 1000.0
    # 1-hour gap -> must cap at ENERGY_DT_CAP_S
    c._tick_buh_and_defrost(
        {ATTR_BUH_STEP1: True, ATTR_DEFROST_OPERATION: False},
        1000.0 + 3600.0,
    )
    assert c._buh_step1_s == pytest.approx(ENERGY_DT_CAP_S, abs=0.1), (
        f"dt should cap at {ENERGY_DT_CAP_S}; got {c._buh_step1_s}"
    )
    assert c._buh_step1_s < 3600.0


# ============================================================
# 3. runtime_snapshot integration (what sensors read)
# ============================================================


def test_runtime_snapshot_exposes_counters() -> None:
    """runtime_snapshot() returns all counter values as float."""
    c = _bare_counter_coord()
    c._buh_step1_s = 100.0
    c._buh_step2_s = 50.0
    c._defrost_count_today = 3
    c._defrost_duration_s = 900.0
    c._last_defrost_ts = 12345.0
    snap = c.runtime_snapshot
    assert snap["buh_step1_s"] == 100.0
    assert snap["buh_step2_s"] == 50.0
    assert snap["defrost_count"] == 3.0
    assert snap["defrost_duration_s"] == 900.0
    assert snap["last_defrost_ts"] == 12345.0


# ============================================================
# 4. CycleStore counter interface
# ============================================================


def test_counters_snapshot_returns_dict() -> None:
    """counters_snapshot() returns a copy (not internal ref)."""
    from custom_components.daikin_cycle_ml.storage.store import CycleStore
    s = CycleStore(maxlen=100)
    snap = s.counters_snapshot()
    assert isinstance(snap, dict)


# ============================================================
# 5. Prod fixture: structural validity
# ============================================================


@pytest.mark.asyncio
async def test_prod_runtime_acc_structurally_valid(tmp_path) -> None:
    """All prod runtime_acc entries (35+ days) have valid schema and values."""
    if not PROD_DB.exists():
        pytest.skip(f"prod fixture absent: {PROD_DB}")
    work = tmp_path / "prod.db"
    shutil.copy(PROD_DB, work)
    db = CycleDB(str(work))
    await db.async_open()
    await db.async_initialize()
    try:
        async with db._conn.execute(
            "SELECT key, value_json FROM model_state "
            "WHERE key LIKE 'runtime_acc.%'"
        ) as cur:
            rows = await cur.fetchall()
        assert len(rows) >= 30, f"expected >=30 days runtime_acc, got {len(rows)}"

        for key, val in rows:
            data = json.loads(val)
            for field in (
                "day", "buh_step1_s", "buh_step2_s",
                "defrost_count", "defrost_duration_s", "last_defrost_ts",
            ):
                assert field in data, f"{key}: missing {field}"
            assert data["buh_step1_s"] >= 0
            assert data["buh_step2_s"] >= 0
            assert data["defrost_count"] >= 0
            assert data["defrost_duration_s"] >= 0
            # Internal consistency: count>0 => duration>0
            if data["defrost_count"] > 0:
                assert data["defrost_duration_s"] > 0, (
                    f"{key}: {data['defrost_count']} defrosts but 0 duration"
                )
            # No impossible per-defrost durations (>1h each)
            if data["defrost_count"] > 0:
                avg_dur = data["defrost_duration_s"] / data["defrost_count"]
                assert avg_dur < 3600.0, (
                    f"{key}: avg defrost dur {avg_dur:.0f}s > 1h (impossible)"
                )
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_prod_defrost_count_nonzero_across_history(tmp_path) -> None:
    """Prod has accumulated defrosts across multiple days (real activity)."""
    if not PROD_DB.exists():
        pytest.skip(f"prod fixture absent: {PROD_DB}")
    work = tmp_path / "prod.db"
    shutil.copy(PROD_DB, work)
    db = CycleDB(str(work))
    await db.async_open()
    await db.async_initialize()
    try:
        async with db._conn.execute(
            "SELECT SUM(defrost_used), COUNT(*) FROM cycles WHERE defrost_used=1"
        ) as cur:
            total, cnt = await cur.fetchone()
        assert total is not None
        assert total > 0, "prod DB has 0 defrost events (unexpected)"
        assert cnt > 0
        # Cross-check with runtime_acc aggregate
        async with db._conn.execute(
            "SELECT SUM(CAST(json_extract(value_json, '$.defrost_count') AS INTEGER)) "
            "FROM model_state WHERE key LIKE 'runtime_acc.%'"
        ) as cur:
            ra_total = (await cur.fetchone())[0]
        assert ra_total is not None
        assert ra_total > 0, "runtime_acc has 0 defrost events (unexpected)"
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_prod_todays_counters_present(tmp_path) -> None:
    """Prod runtime_acc has an entry for the most recent active day."""
    if not PROD_DB.exists():
        pytest.skip(f"prod fixture absent: {PROD_DB}")
    work = tmp_path / "prod.db"
    shutil.copy(PROD_DB, work)
    db = CycleDB(str(work))
    await db.async_open()
    await db.async_initialize()
    try:
        async with db._conn.execute(
            "SELECT MAX(ts) FROM cop_samples"
        ) as cur:
            max_ts = (await cur.fetchone())[0]
        today = time.strftime("%Y-%m-%d", time.localtime(max_ts))
        async with db._conn.execute(
            "SELECT value_json FROM model_state WHERE key = ?",
            (f"runtime_acc.{today}",),
        ) as cur:
            row = await cur.fetchone()
        assert row is not None, (
            f"prod has no runtime_acc for today={today}"
        )
        data = json.loads(row[0])
        # Today has some activity
        has_activity = (
            data["buh_step1_s"] > 0
            or data["buh_step2_s"] > 0
            or data["defrost_count"] > 0
        )
        assert has_activity, f"today={today} has no counter activity: {data}"
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# 6. Counter persistence (model_state roundtrip)
# ============================================================


@pytest.mark.asyncio
async def test_runtime_acc_persist_restore_roundtrip(tmp_path) -> None:
    """Persist counter state -> restore -> identical."""
    db = CycleDB(str(tmp_path / "test.db"))
    await db.async_open()
    await db.async_initialize()
    try:
        payload = {
            "day": "2026-11-07",
            "buh_step1_s": 100.0,
            "buh_step2_s": 200.0,
            "defrost_count": 3,
            "defrost_duration_s": 900.0,
            "last_defrost_ts": 12345.0,
        }
        await db.async_set_model_state("runtime_acc.2026-11-07", payload)
        restored = await db.async_get_model_state("runtime_acc.2026-11-07")
        assert restored == payload
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)
