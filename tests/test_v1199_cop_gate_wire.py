"""v1.19.9 #123: classifier wired into COP sample collection.

Proves Model 2 end-to-end:
- reject class: sample NOT inserted into cop_samples
- flag class: inserted with is_transition_artifact=1
- accept class: inserted with is_transition_artifact=0
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)
from tests.test_rollup_concurrency import _mk_db


@pytest.mark.asyncio
async def test_insert_accepts_flag_field(tmp_path):
    """DB-layer: INSERT accepts is_transition_artifact, default 0."""
    db = await _mk_db(tmp_path)
    try:
        ok = await db.async_insert_cop_sample({
            "ts": time.time(), "cop": 5.0,
            "lwt": 30.0, "outdoor": 10.0,
            "mode": "heating", "source": "interval",
            "power_stable": True,
        })
        assert ok is True
        # Default 0
        import aiosqlite
        async with db._conn.execute(
            "SELECT is_transition_artifact FROM cop_samples LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
        assert row[0] == 0

        # Explicit 1
        ok = await db.async_insert_cop_sample({
            "ts": time.time() + 1, "cop": 8.0,
            "lwt": 30.0, "outdoor": 10.0,
            "mode": "heating", "source": "interval",
            "power_stable": True,
            "is_transition_artifact": 1,
        })
        assert ok is True
        async with db._conn.execute(
            "SELECT is_transition_artifact FROM cop_samples "
            "ORDER BY ts DESC LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
        assert row[0] == 1
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


def _make_coord_for_gate(db):
    """Minimal coordinator with all _maybe_collect_cop_sample deps."""
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.db = db
    c.options = {}
    c.hass = MagicMock()
    c._cop_sample_seed_done = True
    c._last_cop_sample_ts = 0.0
    c.cop_sensor_entity = "sensor.cop"
    # Simulate source attrs (heating mode, lwt=30, outdoor=10)
    compat = {
        "Leaving water temp. before BUH (R1T)": 30.5,
        "Leaving water temp. after BUH (R2T)": 30.5,
        "Inlet water temp.(R4T)": 25.0,
        "Outdoor air temp.(R1T)": 10.0,
        "Flow sensor (l/min)": 15.0,
        "Defrost Operation": False,
    }
    c.data = SimpleNamespace(
        attrs={"raw": True},
        mode="heating",
        state="running",
        boiler_active=False,
        is_hybrid=False,
        boiler_heat_active=False,
        boiler_dhw_active=False,
        cop=None,
    )
    # Mock build_compat_view to return fixed attrs (simplification)
    import custom_components.daikin_cycle_ml.coordinator as coord_mod
    c._test_compat = compat
    return c


@pytest.mark.asyncio
async def test_reject_class_does_not_insert(tmp_path, monkeypatch):
    """cop=100 at lwt=30/out=5: reject -> row absent from DB."""
    db = await _mk_db(tmp_path)
    try:
        c = _make_coord_for_gate(db)
        # Override cop sensor to return impossible value
        st = MagicMock()
        st.state = "100.0"
        st.attributes = {"leaving_temp": 30.0, "outdoor_temperature": 5.0}
        c.hass.states.get.return_value = st

        # Patch build_compat_view to return attrs consistent with test
        import custom_components.daikin_cycle_ml.coordinator as coord_mod
        monkeypatch.setattr(
            coord_mod, "build_compat_view",
            lambda a: {
                "Leaving water temp. before BUH (R1T)": 30.0,
                "Leaving water temp. after BUH (R2T)": 30.0,
                "Inlet water temp.(R4T)": 25.0,
                "Outdoor air temp.(R1T)": 5.0,
                "Flow sensor (l/min)": 15.0,
                "Defrost Operation": False,
            },
        )
        # Force mode resolution
        c._resolve_cop_sample_mode = lambda: "heating"

        await c._maybe_collect_cop_sample(time.time())
        # No insert expected
        async with db._conn.execute(
            "SELECT COUNT(*) FROM cop_samples"
        ) as cur:
            count = (await cur.fetchone())[0]
        assert count == 0, f"reject class should not insert, got {count} rows"
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_flag_class_inserts_with_marker(tmp_path, monkeypatch):
    """cop=10.05 at lwt=38.5/out=14.7: flag -> row with is_transition_artifact=1."""
    db = await _mk_db(tmp_path)
    try:
        c = _make_coord_for_gate(db)
        st = MagicMock()
        st.state = "10.05"
        st.attributes = {
            "leaving_temp": 38.5, "outdoor_temperature": 14.7,
        }
        c.hass.states.get.return_value = st

        import custom_components.daikin_cycle_ml.coordinator as coord_mod
        monkeypatch.setattr(
            coord_mod, "build_compat_view",
            lambda a: {
                "Leaving water temp. before BUH (R1T)": 38.5,
                "Leaving water temp. after BUH (R2T)": 38.5,
                "Inlet water temp.(R4T)": 33.0,
                "Outdoor air temp.(R1T)": 14.7,
                "Flow sensor (l/min)": 15.0,
                "Defrost Operation": False,
            },
        )
        c._resolve_cop_sample_mode = lambda: "heating"

        await c._maybe_collect_cop_sample(time.time())
        async with db._conn.execute(
            "SELECT is_transition_artifact FROM cop_samples"
        ) as cur:
            rows = await cur.fetchall()
        assert len(rows) == 1, f"expected 1 row, got {len(rows)}"
        assert rows[0][0] == 1, f"expected flag=1, got {rows[0][0]}"
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_accept_class_inserts_unflagged(tmp_path, monkeypatch):
    """cop=5.0 at lwt=30/out=10: accept -> row with is_transition_artifact=0."""
    db = await _mk_db(tmp_path)
    try:
        c = _make_coord_for_gate(db)
        st = MagicMock()
        st.state = "5.0"
        st.attributes = {"leaving_temp": 30.0, "outdoor_temperature": 10.0}
        c.hass.states.get.return_value = st

        import custom_components.daikin_cycle_ml.coordinator as coord_mod
        monkeypatch.setattr(
            coord_mod, "build_compat_view",
            lambda a: {
                "Leaving water temp. before BUH (R1T)": 30.0,
                "Leaving water temp. after BUH (R2T)": 30.0,
                "Inlet water temp.(R4T)": 25.0,
                "Outdoor air temp.(R1T)": 10.0,
                "Flow sensor (l/min)": 15.0,
                "Defrost Operation": False,
            },
        )
        c._resolve_cop_sample_mode = lambda: "heating"

        await c._maybe_collect_cop_sample(time.time())
        async with db._conn.execute(
            "SELECT is_transition_artifact FROM cop_samples"
        ) as cur:
            rows = await cur.fetchall()
        assert len(rows) == 1
        assert rows[0][0] == 0
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)

# ============================================================
# R634: Real-world reproduction tests
# Source: prod-1 2026-11-05 (DB snapshot _prod1_20261105.db)
# + RFI #127 Q4 sample id=148 + edge cases observed in prod
# ============================================================


@pytest.fixture
def patched_compat(monkeypatch):
    """Route build_compat_view to read c.data.attrs['__test_attrs__']."""
    import custom_components.daikin_cycle_ml.coordinator as coord_mod
    def _fake_build_compat(a):
        if isinstance(a, dict):
            return a.get("__test_attrs__", a)
        return {}
    monkeypatch.setattr(coord_mod, "build_compat_view", _fake_build_compat)


def _mk_gate_coord(db, *, cop, lwt, outdoor, mode="heating", defrost=False):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.db = db
    c.options = {}
    c.hass = MagicMock()
    c._cop_sample_seed_done = True
    c._last_cop_sample_ts = 0.0
    c.cop_sensor_entity = "sensor.cop"
    st = MagicMock()
    st.state = str(cop)
    st.attributes = {}
    c.hass.states.get.return_value = st
    attrs = {
        "__test_attrs__": {
            "Leaving water temp. before BUH (R1T)": lwt,
            "Leaving water temp. after BUH (R2T)": lwt,
            "Inlet water temp.(R4T)": (lwt - 5.0) if lwt is not None else None,
            "Outdoor air temp.(R1T)": outdoor,
            "Flow sensor (l/min)": 15.0,
            "Defrost Operation": defrost,
        }
    }
    c.data = SimpleNamespace(
        attrs=attrs, mode=mode, state="running",
        boiler_active=False, is_hybrid=False,
        boiler_heat_active=False, boiler_dhw_active=False, cop=None,
    )
    c._resolve_cop_sample_mode = lambda: mode
    return c


@pytest.mark.parametrize("case", [
    # prod-1 2026-11-05 (real observed samples, source: prod DB)
    dict(name="prod_10_05", cop=10.05, lwt=38.5, out=14.7, mode="heating", rows=1, flag=1),
    dict(name="prod_8_48_borderline", cop=8.48, lwt=31.4, out=8.0, mode="heating", rows=1, flag=0),
    dict(name="prod_7_99", cop=7.99, lwt=32.3, out=4.7, mode="heating", rows=1, flag=1),
    dict(name="prod_dhw_8_01", cop=8.01, lwt=62.2, out=12.5, mode="dhw", rows=1, flag=1),
    # RFI #127 Q4 sample id=148 (legacy impossible COP)
    dict(name="rfi_legacy_19_5", cop=19.5, lwt=27.0, out=9.7, mode="heating", rows=1, flag=1),
    # Synthetic class coverage
    dict(name="typical_dhw_3_5", cop=3.5, lwt=55.0, out=10.0, mode="dhw", rows=1, flag=0),
    # cop=11.0 at lwt=30/out=10: Carnot=15.16, ceiling=9.85, accept<=10.34,
    # reject>22.74. 11.0 in (10.34, 22.74] -> flag
    dict(name="moderate_flag_11_0", cop=11.0, lwt=30.0, out=10.0, mode="heating", rows=1, flag=1),
    dict(name="just_beyond_reject_19_0", cop=19.0, lwt=30.0, out=5.0, mode="heating", rows=0, flag=None),
    dict(name="extreme_100_0", cop=100.0, lwt=30.0, out=5.0, mode="heating", rows=0, flag=None),
    # Cooling (not_applicable path)
    dict(name="cooling_4_0", cop=4.0, lwt=12.0, out=35.0, mode="cooling", rows=1, flag=0),
])
@pytest.mark.asyncio
async def test_wire_real_world_observations(tmp_path, patched_compat, case):
    """R634: reproduce observed production samples + edge cases."""
    db = await _mk_db(tmp_path)
    try:
        c = _mk_gate_coord(db, cop=case["cop"], lwt=case["lwt"],
                           outdoor=case["out"], mode=case["mode"])
        await c._maybe_collect_cop_sample(time.time())
        async with db._conn.execute(
            "SELECT is_transition_artifact FROM cop_samples"
        ) as cur:
            rows = await cur.fetchall()
        assert len(rows) == case["rows"], (
            f"{case['name']}: expected {case['rows']} rows, got {len(rows)}"
        )
        if case["flag"] is not None:
            assert rows[0][0] == case["flag"], (
                f"{case['name']}: expected flag={case['flag']}, got {rows[0][0]}"
            )
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)



@pytest.mark.asyncio
async def test_negative_cop_blocked_upstream(tmp_path, patched_compat):
    """Negative COP blocked upstream (existing sample.cop <= 0 guard)."""
    db = await _mk_db(tmp_path)
    try:
        c = _mk_gate_coord(db, cop=-1.0, lwt=30.0, outdoor=10.0)
        await c._maybe_collect_cop_sample(time.time())
        async with db._conn.execute("SELECT COUNT(*) FROM cop_samples") as cur:
            n = (await cur.fetchone())[0]
        assert n == 0
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_boiler_active_marker_preserved_when_flagged(tmp_path, patched_compat):
    """Hybrid co-fire: boiler_active=1 preserved; classifier still applies."""
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


@pytest.mark.asyncio
async def test_reject_does_not_update_last_ts(tmp_path, patched_compat):
    """Rejected samples do not advance _last_cop_sample_ts (retry sooner)."""
    db = await _mk_db(tmp_path)
    try:
        c = _mk_gate_coord(db, cop=100.0, lwt=30.0, outdoor=5.0)
        assert c._last_cop_sample_ts == 0.0
        await c._maybe_collect_cop_sample(time.time())
        assert c._last_cop_sample_ts == 0.0
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_flag_updates_last_ts(tmp_path, patched_compat):
    """Flagged samples are stored -> timer advances."""
    db = await _mk_db(tmp_path)
    try:
        c = _mk_gate_coord(db, cop=10.05, lwt=38.5, outdoor=14.7)
        t0 = time.time()
        await c._maybe_collect_cop_sample(t0)
        assert c._last_cop_sample_ts == t0
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_accept_updates_last_ts(tmp_path, patched_compat):
    """Accepted samples advance _last_cop_sample_ts (normal throttle)."""
    db = await _mk_db(tmp_path)
    try:
        c = _mk_gate_coord(db, cop=5.0, lwt=30.0, outdoor=10.0)
        t0 = time.time()
        await c._maybe_collect_cop_sample(t0)
        assert c._last_cop_sample_ts == t0
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)
