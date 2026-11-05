"""v1.19.9 R641: real-live factor matrix over alle assen + boundaries.

Test elke drempel op (drempel-epsilon, drempel, drempel+epsilon):
- CARNOT_EFFICIENCY_FACTOR 0.65 (accept vs flag grens)
- ACCEPT_MARGIN 1.05 (margin absorbeert sensorruis)
- REJECT_MULTIPLIER 1.50 (flag vs reject grens)
- SETTLE_S 300 (block vs allow)
- dT >= 1.5K (accept vs None)

Cross-product assen: mode (heating/dhw) x lwt x outdoor x cop x dT.
Pairwise-reduced maar elke as op alle 3 boundaries.
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from custom_components.daikin_cycle_ml.const import (
    ATTR_INLET_WATER_R4T,
    ATTR_LEAVING_WATER_AFTER_BUH)
from custom_components.daikin_cycle_ml.engine.physics import (
    ACCEPT_MARGIN,
    CARNOT_EFFICIENCY_FACTOR,
    REJECT_MULTIPLIER,
    classify_cop_sample)
from custom_components.daikin_cycle_ml.engine.thermal import dt_from_attrs
from tests.test_rollup_concurrency import _mk_db
from tests.test_v1199_cop_gate_wire import (  # noqa: F401
    _mk_gate_coord)


# ============================================================
# Carnot factor boundaries: 0.65 * 1.05 * carnot
# ============================================================

def _carnot(lwt: float, outdoor: float) -> float:
    th = lwt + 273.15
    tc = outdoor + 273.15
    return th / (th - tc)


@pytest.mark.parametrize("mode", ["heating", "dhw"])
@pytest.mark.parametrize("lwt,outdoor", [
    (30.0, 10.0), (35.0, 5.0), (45.0, -15.0), (55.0, 10.0), (27.0, 9.7)
])
def test_matrix_accept_boundary(mode, lwt, outdoor):
    """R641: cop = accept_thr-eps -> accept; accept_thr+eps -> flag."""
    c = _carnot(lwt, outdoor)
    accept_thr = c * CARNOT_EFFICIENCY_FACTOR * ACCEPT_MARGIN
    eps = 0.01
    assert classify_cop_sample(mode, lwt, outdoor, accept_thr - eps) == "accept"
    assert classify_cop_sample(mode, lwt, outdoor, accept_thr) == "accept"
    assert classify_cop_sample(mode, lwt, outdoor, accept_thr + eps) == "flag"


@pytest.mark.parametrize("mode", ["heating", "dhw"])
@pytest.mark.parametrize("lwt,outdoor", [
    (30.0, 5.0), (45.0, -15.0), (55.0, 10.0)
])
def test_matrix_reject_boundary(mode, lwt, outdoor):
    """R641: cop = reject_thr -> flag; +eps -> reject."""
    c = _carnot(lwt, outdoor)
    reject_thr = c * REJECT_MULTIPLIER
    eps = 0.01
    assert classify_cop_sample(mode, lwt, outdoor, reject_thr - eps) == "flag"
    assert classify_cop_sample(mode, lwt, outdoor, reject_thr) == "flag"
    assert classify_cop_sample(mode, lwt, outdoor, reject_thr + eps) == "reject"


@pytest.mark.parametrize("lwt,outdoor", [
    (5.0, 5.0), (4.999, 5.0), (0.0, 5.0), (-10.0, 5.0)
])
def test_matrix_no_lift_not_applicable(lwt, outdoor):
    """R641: lwt <= outdoor -> not_applicable (elke mode)."""
    for mode in ("heating", "dhw"):
        assert classify_cop_sample(mode, lwt, outdoor, 3.0) == "not_applicable"


# ============================================================
# dT >= 1.5K boundaries (primary + fallback pad)
# ============================================================

@pytest.mark.parametrize("dt_value,expected", [
    (0.0, None),
    (0.5, None),
    (1.0, None),
    (1.499, None),
    (1.5, 1.5),     # exact grens: accept (>=)
    (1.51, 1.51),
    (2.0, 2.0),
    (5.0, 5.0),
    (7.0, 7.0),
])
def test_matrix_dt_primary_boundary(dt_value, expected):
    """R641: primary path (R1T-R4T) grens exact op 1.5."""
    r1t = 25.0 + dt_value
    v = dt_from_attrs({
        "Leaving water temp. before BUH (R1T)": r1t,
        ATTR_INLET_WATER_R4T: 25.0,
    })
    if expected is None:
        assert v is None, f"dT={dt_value} should be None, got {v}"
    else:
        assert v == pytest.approx(expected, abs=0.01)


@pytest.mark.parametrize("dt_value,expected", [
    (0.0, None),
    (1.0, None),
    (1.499, None),
    (1.5, 1.5),
    (3.0, 3.0),
])
def test_matrix_dt_fallback_boundary(dt_value, expected):
    """R641: fallback path (R2T-R4T) grens exact op 1.5."""
    a = 25.0 + dt_value
    v = dt_from_attrs({
        ATTR_LEAVING_WATER_AFTER_BUH: a,
        ATTR_INLET_WATER_R4T: 25.0,
    })
    if expected is None:
        assert v is None
    else:
        assert v == pytest.approx(expected, abs=0.01)


# ============================================================
# SETTLE_S boundaries (default 300)
# ============================================================

@pytest.mark.asyncio
@pytest.mark.parametrize("age,expected_rows", [
    (0.0, 0),
    (100.0, 0),
    (299.0, 0),
    (299.999, 0),
    (300.0, 1),     # exact grens: allowed (>=)
    (300.001, 1),
    (500.0, 1),
])
async def test_matrix_settle_boundary(
    tmp_path, patched_compat, age, expected_rows
):
    """R641: settle window exact op 300s (>= allowed)."""
    db = await _mk_db(tmp_path)
    try:
        c = _mk_gate_coord(db, cop=5.0, lwt=30.0, outdoor=10.0)
        now = time.time()
        c._last_mode_change_ts = now - age
        c._last_cop_sample_ts = 0.0
        await c._maybe_collect_cop_sample(now)
        async with db._conn.execute(
            "SELECT COUNT(*) FROM cop_samples"
        ) as cur:
            n = (await cur.fetchone())[0]
        assert n == expected_rows, (
            f"age={age}s expected {expected_rows} rows, got {n}"
        )
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)
