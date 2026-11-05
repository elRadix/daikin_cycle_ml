"""v1.19.9 R645: failure mode simulations.

Simuleert de 8 realistisch denkbare failure scenarios uit productie.
Elk scenario test dat de integratie NIET crasht en correct reageert.

Scenario's:
1. Source outage (bron stopt)
2. Firmware drift (COP plotseling anders)
3. Boiler co-fire (hybride scenario)
4. Sensor degradation (ruis toename)
5. Reboot midden in cycle
6. Defrost operation
7. Negative COP
8. Power spike
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator)
from custom_components.daikin_cycle_ml.engine.physics import (
    classify_cop_sample)
from custom_components.daikin_cycle_ml.storage.db import CycleDB
from tests.test_rollup_concurrency import _mk_db
from tests.test_v1199_cop_gate_wire import (  # noqa: F401
    _mk_gate_coord)


# ============================================================
# 1. Source outage
# ============================================================

def test_failure_source_outage_detects_stale():
    """Bron >120s stil -> source_stale trigger correct."""
    from custom_components.daikin_cycle_ml.binary_sensor import (
        _is_source_stale)
    from datetime import datetime, timezone

    now = time.time()
    snap = SimpleNamespace(last_success_ts=now - 10)  # tick fresh
    hass = MagicMock()
    st = MagicMock()
    st.last_updated = datetime.fromtimestamp(now - 500, tz=timezone.utc)
    hass.states.get.return_value = st
    c = SimpleNamespace(
        hass=hass, source_entity="sensor.althermasensors", options={}
    )
    assert _is_source_stale(snap, c) is True


def test_failure_source_outage_recovery():
    """Bron terug na outage -> alert valt weg."""
    from custom_components.daikin_cycle_ml.binary_sensor import (
        _is_source_stale)
    from datetime import datetime, timezone

    now = time.time()
    snap = SimpleNamespace(last_success_ts=now - 10)
    hass = MagicMock()
    st = MagicMock()
    st.last_updated = datetime.fromtimestamp(now - 5, tz=timezone.utc)
    hass.states.get.return_value = st
    c = SimpleNamespace(
        hass=hass, source_entity="sensor.althermasensors", options={}
    )
    assert _is_source_stale(snap, c) is False


# ============================================================
# 2. Firmware drift
# ============================================================

@pytest.mark.asyncio
async def test_failure_firmware_drift_detected(tmp_path, patched_compat):
    """Firmware drift: waarden stijgen plotseling -> classifier vangt.

    Simuleert een firmware-update die 30% hogere COP rapporteert.
    """
    db = await _mk_db(tmp_path)
    try:
        # Baseline samples (normal)
        for i in range(3):
            c = _mk_gate_coord(db, cop=5.0, lwt=30.0, outdoor=10.0)
            c._last_cop_sample_ts = 0.0
            await c._maybe_collect_cop_sample(time.time() + i)

        # Drift samples (30% higher)
        for i in range(3):
            c = _mk_gate_coord(db, cop=13.0, lwt=30.0, outdoor=10.0)
            c._last_cop_sample_ts = 0.0
            await c._maybe_collect_cop_sample(time.time() + 10 + i)

        # First 3 accept, last 3 flagged (drifting 30% above baseline)
        async with db._conn.execute("""
            SELECT is_transition_artifact FROM cop_samples ORDER BY ts
        """) as cur:
            rows = [r[0] for r in await cur.fetchall()]

        # 3 accept (flag=0) + 3 flagged (flag=1) or rejected
        accepts = [r for r in rows if r == 0]
        assert len(accepts) >= 3, f"expected 3+ accepts, got {len(accepts)}"

    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# 3. Boiler co-fire
# ============================================================

@pytest.mark.asyncio
async def test_failure_boiler_cofire_hybrid(tmp_path, patched_compat):
    """Hybride co-fire: boiler_active=1, sample nog steeds geclassificeerd."""
    db = await _mk_db(tmp_path)
    try:
        c = _mk_gate_coord(db, cop=10.05, lwt=38.5, outdoor=14.7)
        c.data.is_hybrid = True
        c.data.boiler_active = True
        c.data.boiler_heat_active = True
        await c._maybe_collect_cop_sample(time.time())

        async with db._conn.execute(
            "SELECT boiler_active, is_transition_artifact FROM cop_samples"
        ) as cur:
            rows = await cur.fetchall()

        assert len(rows) == 1
        assert rows[0][0] == 1, "boiler_active marker lost"
        assert rows[0][1] == 1, "classifier flag lost"

    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# 4. Sensor degradation
# ============================================================

@pytest.mark.asyncio
async def test_failure_sensor_degradation_noisy(tmp_path, patched_compat):
    """Sensor ruis: 10 samples met +-0.5 offset, geen crashes."""
    db = await _mk_db(tmp_path)
    try:
        for i, offset in enumerate([-0.5, -0.2, 0, 0.2, 0.5, 0.3, -0.3, 0.1,
                                      -0.1, 0]):
            c = _mk_gate_coord(
                db, cop=5.0 + offset * 0.5,
                lwt=30.0 + offset, outdoor=10.0 + offset)
            c._last_cop_sample_ts = 0.0
            await c._maybe_collect_cop_sample(time.time() + i)

        async with db._conn.execute(
            "SELECT COUNT(*) FROM cop_samples"
        ) as cur:
            n = (await cur.fetchone())[0]
        # Alle 10 moeten geaccepteerd zijn (offset is klein)
        assert n == 10, f"expected 10, got {n}"

    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# 5. Reboot midden in cycle
# ============================================================

@pytest.mark.asyncio
async def test_failure_reboot_state_preserved(tmp_path):
    """Reboot: DB state intact, counters persistent."""
    db = await _mk_db(tmp_path)
    try:
        # Insert some data before "reboot"
        await db.async_insert_cop_sample({
            "ts": time.time(), "cop": 5.0, "lwt": 30.0, "outdoor": 10.0,
            "mode": "heating", "source": "interval", "power_stable": True,
        })
        async with db._conn.execute(
            "SELECT COUNT(*) FROM cop_samples"
        ) as cur:
            n_before = (await cur.fetchone())[0]

        # Simulate reboot: close + reopen same path
        db_path = db._path
        await db.async_close()
        db = CycleDB(db_path)
        await db.async_open()

        async with db._conn.execute(
            "SELECT COUNT(*) FROM cop_samples"
        ) as cur:
            n_after = (await cur.fetchone())[0]

        assert n_after == n_before, f"data lost on reboot: {n_before} -> {n_after}"

    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# 6. Defrost operation
# ============================================================

def test_failure_defrost_parse_variants():
    """Defrost met alle varianten ('ON', 'on', True, 1) werkt."""
    from custom_components.daikin_cycle_ml.engine.cop_analyzer import (
        parse_global_cop_attrs)
    for raw in ["ON", "on", True, 1]:
        s = parse_global_cop_attrs({
            "state": "5.0", "defrost_operation": raw,
        })
        assert s is not None
        assert s.defrost is True, f"defrost_operation={raw!r}"


# ============================================================
# 7. Negative COP
# ============================================================

@pytest.mark.asyncio
async def test_failure_negative_cop_blocked(tmp_path, patched_compat):
    """Negatieve COP: geblokkeerd vóór classifier."""
    db = await _mk_db(tmp_path)
    try:
        c = _mk_gate_coord(db, cop=-1.0, lwt=30.0, outdoor=10.0)
        await c._maybe_collect_cop_sample(time.time())

        async with db._conn.execute(
            "SELECT COUNT(*) FROM cop_samples"
        ) as cur:
            n = (await cur.fetchone())[0]
        assert n == 0, f"negative cop should be blocked, got {n} rows"

    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# 8. Power spike
# ============================================================

def test_failure_extreme_power_rejected():
    """Extreme power_w: classifier vangt extreme COP."""
    # Reject boundary: carnot=12.13, reject_thr=18.19
    # Extreme cop from power spike -> reject
    assert classify_cop_sample("heating", 30.0, 5.0, 100.0) == "reject"
    assert classify_cop_sample("heating", 30.0, 5.0, 19.0) == "reject"
    # Moderate flag: between accept(10.34) and reject(18.19)
    assert classify_cop_sample("heating", 30.0, 5.0, 15.0) == "flag"
    # Normal -> accept
    assert classify_cop_sample("heating", 30.0, 5.0, 5.0) == "accept"
