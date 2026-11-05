"""v1.19.9 #122/#123 R634: SETTLE_S + dT>=1.5K gates.

RFI #127 Q3: Daikin compressor needs ~300s to reach steady-state
after mode change. Samples within that window are transition
artifacts (id=148 cop=19.5 was one such sample).

RFI #127 Q3/dT: ESPAltherma sensors have +/-0.3K tolerance. Below
1.5K delta-T the relative error makes COP unreliable (>/= 20%).

Source: prod-1 2026-11-05 measurements + RFI #127 Q4 sample id=148.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from tests.test_rollup_concurrency import _mk_db
from tests.test_v1199_cop_gate_wire import (  # noqa: F401
    _mk_gate_coord)


# ============================================================
# SETTLE_S gate -- inside _maybe_collect_cop_sample
# ============================================================

@pytest.mark.asyncio
async def test_settle_window_blocks_sample(tmp_path, patched_compat):
    """R634: mode changed 100s ago -> sample blocked (was accepted)."""
    db = await _mk_db(tmp_path)
    try:
        c = _mk_gate_coord(db, cop=5.0, lwt=30.0, outdoor=10.0)
        now = time.time()
        c._last_mode_change_ts = now - 100.0  # within 300s window
        await c._maybe_collect_cop_sample(now)
        async with db._conn.execute("SELECT COUNT(*) FROM cop_samples") as cur:
            n = (await cur.fetchone())[0]
        assert n == 0, f"sample not blocked by settle gate: got {n}"
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_settle_window_allows_after_300s(tmp_path, patched_compat):
    """R634: mode changed 400s ago -> sample accepted."""
    db = await _mk_db(tmp_path)
    try:
        c = _mk_gate_coord(db, cop=5.0, lwt=30.0, outdoor=10.0)
        now = time.time()
        c._last_mode_change_ts = now - 400.0  # outside 300s window
        await c._maybe_collect_cop_sample(now)
        async with db._conn.execute("SELECT COUNT(*) FROM cop_samples") as cur:
            n = (await cur.fetchone())[0]
        assert n == 1, f"sample should be accepted after settle: got {n}"
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_settle_window_bootstrap(tmp_path, patched_compat):
    """R634: cold start, no prior mode change -> accepted."""
    db = await _mk_db(tmp_path)
    try:
        c = _mk_gate_coord(db, cop=5.0, lwt=30.0, outdoor=10.0)
        now = time.time()
        c._last_mode_change_ts = 0.0  # bootstrap
        await c._maybe_collect_cop_sample(now)
        async with db._conn.execute("SELECT COUNT(*) FROM cop_samples") as cur:
            n = (await cur.fetchone())[0]
        assert n == 1
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_settle_window_configurable(tmp_path, patched_compat):
    """R634: custom cop_settle_time_s option respected."""
    db = await _mk_db(tmp_path)
    try:
        c = _mk_gate_coord(db, cop=5.0, lwt=30.0, outdoor=10.0)
        c.options = {"cop_settle_time_s": 60.0}
        now = time.time()
        c._last_mode_change_ts = now - 100.0  # > 60s custom -> accept
        await c._maybe_collect_cop_sample(now)
        async with db._conn.execute("SELECT COUNT(*) FROM cop_samples") as cur:
            n = (await cur.fetchone())[0]
        assert n == 1, f"custom 60s settle should allow at age 100: got {n}"
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# dT >= 1.5K gate -- inside dt_from_attrs
# ============================================================

def test_dt_gate_rejects_below_1_5():
    """R634: dT=1.0 -> None (was accepted at 0.5 threshold)."""
    from custom_components.daikin_cycle_ml.const import ATTR_INLET_WATER_R4T
    from custom_components.daikin_cycle_ml.engine.thermal import dt_from_attrs
    v = dt_from_attrs({
        "Leaving water temp. before BUH (R1T)": 25.0,
        ATTR_INLET_WATER_R4T: 24.0,
    })
    assert v is None, f"dT=1.0 should be rejected, got {v}"


def test_dt_gate_accepts_at_1_5():
    """R634: dT=1.5 accepted (threshold is >=, not >)."""
    from custom_components.daikin_cycle_ml.const import ATTR_INLET_WATER_R4T
    from custom_components.daikin_cycle_ml.engine.thermal import dt_from_attrs
    v = dt_from_attrs({
        "Leaving water temp. before BUH (R1T)": 25.0,
        ATTR_INLET_WATER_R4T: 23.5,
    })
    assert v == 1.5, f"dT=1.5 should be accepted, got {v}"


def test_dt_gate_fallback_below_1_5_rejected():
    """R634: fallback path (no R1T, using R2T) also >= 1.5 enforced."""
    from custom_components.daikin_cycle_ml.const import (
        ATTR_INLET_WATER_R4T,
        ATTR_LEAVING_WATER_AFTER_BUH)
    from custom_components.daikin_cycle_ml.engine.thermal import dt_from_attrs
    v = dt_from_attrs({
        ATTR_LEAVING_WATER_AFTER_BUH: 25.0,
        ATTR_INLET_WATER_R4T: 24.0,
    })
    assert v is None, f"fallback dT=1.0 should be rejected, got {v}"
