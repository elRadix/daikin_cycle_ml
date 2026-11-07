"""v1.20.0 #281 T8c: COP -> daily-report E2E chain for v2-source data.

Proves for v2-derived COP values that the full pipeline works:

  tick -> _maybe_collect_cop_sample
      -> parse_global_cop_attrs -> classify_cop_sample (Carnot gate)
      -> async_insert_cop_sample (source='interval', COP value v2-derived)
  -> async_rollup_cop_hourly (cop_hourly table)
  -> cycle close -> _maybe_rollup_day -> async_rollup_day (daily_summary)
  -> _refresh_cop_today -> _cop_today_heating_cache
  -> sensor cop_today value_fn

R598: every test calls the REAL production methods. Only the hass.states
boundary and hand-crafted COP source data are fixtures.

R634: prod DB `_prod1_20261106.db` (gitignored, skipped when absent) used
for the migration-idempotency test.
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
from custom_components.daikin_cycle_ml.storage.db import CycleDB

PROD_DB = pathlib.Path("tests/fixtures/_prod1_20261106.db")


# ============================================================
# Fixtures / helpers
# ============================================================


async def _mk_fresh_db(tmp_path) -> CycleDB:
    """Fresh CycleDB in tmp, no fixtures. Reusable across tests."""
    db = CycleDB(str(tmp_path / "test.db"))
    await db.async_open()
    await db.async_initialize()  # schema + all migrations
    return db


def _v2_source_attrs(*, lwt: float = 35.0, outdoor: float = 10.0) -> dict:
    """v2-source attrs dict (compat_view will read these)."""
    return {
        "Leaving water temp. after BUH (R2T)": lwt,
        "Inlet water temp.(R4T)": lwt - 5.0,
        "Outdoor air temp.(R1T)": outdoor,
        "Flow sensor (l/min)": 15.0,
        "Defrost Operation": False,
    }


def _make_coord_for_cop(
    db,
    *,
    cop_value: float = 4.5,
    lwt: float = 35.0,
    outdoor: float = 10.0,
    mode: str = "heating",
    is_hybrid: bool = False,
    boiler_active: bool = False,
) -> DaikinCycleMLCoordinator:
    """Coordinator with all _maybe_collect_cop_sample + _refresh deps."""
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.db = db
    c.options = {}
    c.hass = MagicMock()
    c.hass.states.get = MagicMock(return_value=None)  # no cop sensor
    c.cop_sensor_entity = None  # force fallback to data.cop
    c._cop_sample_seed_done = True
    c._last_cop_sample_ts = 0.0
    c._last_mode_change_ts = 0.0
    c._cop_today_cache = {}
    c._cop_today_heating_cache = {}
    c._cop_rejected_today_count = 0
    c._cop_rejected_today_first_ts = 0.0
    c.data = SimpleNamespace(
        attrs=_v2_source_attrs(lwt=lwt, outdoor=outdoor),
        cop=cop_value,
        boiler_active=boiler_active,
        is_hybrid=is_hybrid,
        state="running",
        mode=mode,
        boiler_heat_active=False,
        boiler_dhw_active=False,
    )
    c._is_hybrid_install = MagicMock(return_value=is_hybrid)
    c._resolve_cop_sample_mode = MagicMock(return_value=mode)
    return c


# ============================================================
# 1. v2 COP source tag propagates through _read_cop_effective
# ============================================================


def test_read_cop_effective_uses_v2_heat_output() -> None:
    """v2 heat output key -> source tag 'espaltherma_heat_output'."""
    from custom_components.daikin_cycle_ml.const import V2_STATS_HEAT_KEY
    c = _make_coord_for_cop(None)
    c._read_cop = MagicMock(return_value=None)
    c._compute_electrical_power = MagicMock(return_value=(1500.0, "power"))
    cop, src = c._read_cop_effective(time.time(), {V2_STATS_HEAT_KEY: 6.0})
    assert src == "espaltherma_heat_output", (
        f"v2 heat output must tag source; got {src!r}"
    )
    assert cop is not None and cop > 0


# ============================================================
# 2. v2 sample inserted with correct COP value
# ============================================================


@pytest.mark.asyncio
async def test_v2_sample_inserted_with_correct_value(tmp_path) -> None:
    """v2 attrs -> _maybe_collect_cop_sample -> DB row with COP value."""
    db = await _mk_fresh_db(tmp_path)
    try:
        c = _make_coord_for_cop(db, cop_value=4.5, lwt=35.0, outdoor=10.0)
        await c._maybe_collect_cop_sample(time.time())
        import aiosqlite
        async with db._conn.execute(
            "SELECT cop, source, is_transition_artifact, boiler_active "
            "FROM cop_samples"
        ) as cur:
            rows = await cur.fetchall()
        assert len(rows) == 1, f"expected 1 sample, got {len(rows)}"
        assert rows[0][0] == pytest.approx(4.5, abs=0.05)
        assert rows[0][1] == "interval"  # source tag is 'interval' by convention
        assert rows[0][2] == 0  # accept class -> not artifact
        assert rows[0][3] == 0  # not boiler
        # last_ts updated
        assert c._last_cop_sample_ts > 0
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# 3. Carnot reject -> not persisted, counter incremented
# ============================================================


@pytest.mark.asyncio
async def test_v2_sample_carnot_reject_not_persisted(tmp_path) -> None:
    """COP=100 with lwt=35/outdoor=10 -> reject class, no DB row."""
    db = await _mk_fresh_db(tmp_path)
    try:
        # lwt=35 outdoor=10: carnot=12.3, reject_thr=18.5 -> cop=100 rejected
        c = _make_coord_for_cop(db, cop_value=100.0, lwt=35.0, outdoor=10.0)
        await c._maybe_collect_cop_sample(time.time())
        import aiosqlite
        async with db._conn.execute(
            "SELECT COUNT(*) FROM cop_samples"
        ) as cur:
            n = (await cur.fetchone())[0]
        assert n == 0, f"rejected sample must not persist; got {n} rows"
        assert c._cop_rejected_today_count == 1
        assert c._cop_rejected_today_first_ts > 0
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# 4. Settle gate blocks sample
# ============================================================


@pytest.mark.asyncio
async def test_v2_sample_settle_gate_blocked(tmp_path) -> None:
    """Mode changed <300s ago -> sample blocked."""
    db = await _mk_fresh_db(tmp_path)
    try:
        c = _make_coord_for_cop(db, cop_value=4.5)
        now = time.time()
        c._last_mode_change_ts = now - 100.0  # 100s < 300s settle
        await c._maybe_collect_cop_sample(now)
        import aiosqlite
        async with db._conn.execute(
            "SELECT COUNT(*) FROM cop_samples"
        ) as cur:
            n = (await cur.fetchone())[0]
        assert n == 0, f"settle gate must block; got {n} rows"
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# 5. Interval gate blocks sample
# ============================================================


@pytest.mark.asyncio
async def test_v2_sample_interval_gate_blocked(tmp_path) -> None:
    """Last sample <300s ago -> sample blocked (interval=300s)."""
    db = await _mk_fresh_db(tmp_path)
    try:
        c = _make_coord_for_cop(db, cop_value=4.5)
        now = time.time()
        c._last_cop_sample_ts = now - 100.0  # 100s < 300s interval
        await c._maybe_collect_cop_sample(now)
        import aiosqlite
        async with db._conn.execute(
            "SELECT COUNT(*) FROM cop_samples"
        ) as cur:
            n = (await cur.fetchone())[0]
        assert n == 0
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# 6. Samples roll up to cop_hourly
# ============================================================


@pytest.mark.asyncio
async def test_v2_samples_roll_up_to_hourly(tmp_path) -> None:
    """6 samples in one hour -> 1 cop_hourly row with correct mean."""
    db = await _mk_fresh_db(tmp_path)
    try:
        now = time.time()
        hour_floor = int(now) - (int(now) % 3600)
        cops = [4.0, 4.2, 4.4, 4.6, 4.8, 5.0]
        for i, c_val in enumerate(cops):
            await db.async_insert_cop_sample({
                "ts": hour_floor + 300 + i * 300,
                "cop": c_val,
                "lwt": 35.0, "outdoor": 10.0,
                "mode": "heating", "source": "interval",
                "power_stable": True,
                "boiler_active": 0,
            })
        n = await db.async_rollup_cop_hourly(window_hours=2)
        assert n == 1, f"expected 1 hourly row, got {n}"
        import aiosqlite
        async with db._conn.execute(
            "SELECT n_samples, cop_mean FROM cop_hourly"
        ) as cur:
            rows = await cur.fetchall()
        assert len(rows) == 1
        assert rows[0][0] == 6
        assert rows[0][1] == pytest.approx(4.5, abs=0.01)
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# 7. Cycle close triggers daily rollup
# ============================================================


@pytest.mark.asyncio
async def test_cycle_close_triggers_daily_rollup(tmp_path) -> None:
    """Insert cycle -> _maybe_rollup_day -> daily_summary updated."""
    db = await _mk_fresh_db(tmp_path)
    try:
        c = _make_coord_for_cop(db)
        c.options = {"daily_summary_live_enabled": True}
        c._daily_summary_recent = None

        now = time.time()
        record = {
            "start_ts": now - 3600,
            "end_ts": now,
            "duration_s": 3600,
            "mode": "heating",
            "dT_max": 5.0, "dT_avg": 4.0,
            "rps_max": 40, "rps_avg": 30,
            "buh_used": 0, "defrost_used": 0,
            "quality_score": 90,
            "outdoor_temp": 10.0,
        }
        cid = await db.async_insert_cycle(record)
        assert cid is not None
        await c._maybe_rollup_day(record)

        rows = await db.async_daily_summary(days=7)
        heating = next((r for r in rows if r["mode"] == "heating"), None)
        assert heating is not None, "no heating daily_summary row"
        assert heating["cycles"] >= 1
        assert heating["total_duration_s"] >= 3600
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# 8. _refresh_cop_today populates cache
# ============================================================


@pytest.mark.asyncio
async def test_daily_summary_feeds_cop_today_cache(tmp_path) -> None:
    """3 today-samples -> _refresh_cop_today -> cache with avg cop."""
    db = await _mk_fresh_db(tmp_path)
    try:
        c = _make_coord_for_cop(db)
        now = time.time()
        for i, cv in enumerate([4.0, 4.5, 5.0]):
            await db.async_insert_cop_sample({
                "ts": now - 1000 + i * 100,
                "cop": cv,
                "lwt": 35.0, "outdoor": 10.0,
                "mode": "heating", "source": "interval",
                "power_stable": True,
                "boiler_active": 0,
            })
        await c._refresh_cop_today(now)
        assert c._cop_today_heating_cache is not None
        cache = c._cop_today_heating_cache
        assert cache.get("cop") == pytest.approx(4.5, abs=0.01)
        assert cache.get("samples_today") == 3
        assert cache.get("cop_min") == pytest.approx(4.0, abs=0.01)
        assert cache.get("cop_max") == pytest.approx(5.0, abs=0.01)
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# 9. Cross-midnight pro-rata
# ============================================================


@pytest.mark.asyncio
async def test_cross_midnight_pro_rata(tmp_path) -> None:
    """Cycle 23:00 -> 00:30 next day -> both days get pro-rata share."""
    db = await _mk_fresh_db(tmp_path)
    try:
        # Use a specific day for determinism
        lt = time.localtime()
        day1_start = time.mktime(
            (lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)
        )
        day1_str = time.strftime("%Y-%m-%d", time.localtime(day1_start))
        day2_start = day1_start + 86400
        day2_str = time.strftime("%Y-%m-%d", time.localtime(day2_start))

        # Cycle from 23:00 day1 to 00:30 day2 (1.5h total)
        await db.async_insert_cycle({
            "start_ts": day1_start + 23 * 3600,  # 23:00
            "end_ts": day1_start + 86400 + 1800,  # 00:30 next day
            "duration_s": 5400,  # 1.5h
            "mode": "heating",
            "dT_max": 5.0, "dT_avg": 4.0,
            "rps_max": 40, "rps_avg": 30,
            "buh_used": 0, "defrost_used": 0,
            "quality_score": 90,
        })
        await db.async_rollup_day(day1_str)
        await db.async_rollup_day(day2_str)

        rows = await db.async_daily_summary(days=7)
        d1 = next((r for r in rows if r["day"] == day1_str and r["mode"] == "heating"), None)
        d2 = next((r for r in rows if r["day"] == day2_str and r["mode"] == "heating"), None)
        assert d1 is not None, f"day1={day1_str} missing"
        assert d2 is not None, f"day2={day2_str} missing"
        # day1 gets 23:00-00:00 = 3600s; day2 gets 00:00-00:30 = 1800s
        assert d1["total_duration_s"] == pytest.approx(3600, abs=60), (
            f"day1 must be ~3600s (1h of 1.5h cycle), got {d1['total_duration_s']}"
        )
        assert d2["total_duration_s"] == pytest.approx(1800, abs=60), (
            f"day2 must be ~1800s (0.5h of 1.5h cycle), got {d2['total_duration_s']}"
        )
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# 10. Boiler-only samples excluded from hourly rollup
# ============================================================


@pytest.mark.asyncio
async def test_boiler_sample_excluded_from_rollup(tmp_path) -> None:
    """boiler_active=1 -> excluded from cop_hourly aggregate."""
    db = await _mk_fresh_db(tmp_path)
    try:
        now = time.time()
        hour_floor = int(now) - (int(now) % 3600)
        # Two pure HP + one boiler sample
        for cv, ba in [(4.0, 0), (4.5, 0), (8.0, 1)]:
            await db.async_insert_cop_sample({
                "ts": hour_floor + 300,
                "cop": cv, "lwt": 35.0, "outdoor": 10.0,
                "mode": "heating", "source": "interval",
                "power_stable": True, "boiler_active": ba,
            })
        n = await db.async_rollup_cop_hourly(window_hours=2)
        assert n == 1
        import aiosqlite
        async with db._conn.execute(
            "SELECT n_samples, cop_mean FROM cop_hourly"
        ) as cur:
            row = await cur.fetchone()
        # Only the 2 pure-HP samples counted
        assert row[0] == 2, f"boiler sample not excluded: n={row[0]}"
        assert row[1] == pytest.approx(4.25, abs=0.01)
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# 11. Artifact flag included in cop_hourly (documented behaviour)
# ============================================================


@pytest.mark.asyncio
async def test_artifact_sample_included_in_rollup(tmp_path) -> None:
    """is_transition_artifact=1 is NOT excluded from cop_hourly.

    Documents existing behaviour: artifacts only affect the v28 flag,
    not the hourly aggregation. Boiler exclusion is the only filter.
    """
    db = await _mk_fresh_db(tmp_path)
    try:
        now = time.time()
        hour_floor = int(now) - (int(now) % 3600)
        for cv, art in [(4.0, 0), (10.0, 1)]:
            await db.async_insert_cop_sample({
                "ts": hour_floor + 300,
                "cop": cv, "lwt": 35.0, "outdoor": 10.0,
                "mode": "heating", "source": "interval",
                "power_stable": True, "boiler_active": 0,
                "is_transition_artifact": art,
            })
        n = await db.async_rollup_cop_hourly(window_hours=2)
        assert n == 1
        import aiosqlite
        async with db._conn.execute(
            "SELECT n_samples FROM cop_hourly"
        ) as cur:
            n_s = (await cur.fetchone())[0]
        assert n_s == 2, (
            f"existing behaviour includes artifacts; got n={n_s} — "
            "if this changes, update the test AND the v28 design"
        )
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ============================================================
# 12. Prod DB migration idempotent
# ============================================================


@pytest.mark.asyncio
async def test_prod_db_migration_idempotent(tmp_path) -> None:
    """Load prod DB copy -> run v28 migration twice -> state unchanged."""
    if not PROD_DB.exists():
        pytest.skip(f"prod fixture absent: {PROD_DB}")
    work = tmp_path / "prod_copy.db"
    shutil.copy(PROD_DB, work)
    db = CycleDB(str(work))
    await db.async_open()
    try:
        marker1 = await db.async_get_model_state("data_migration_v28_completed")
        assert marker1 is not None, "prod DB must have v28 marker"
        assert marker1.get("completed") is True
        # Get counts before
        async with db._conn.execute(
            "SELECT COUNT(*), SUM(is_transition_artifact) FROM cop_samples"
        ) as cur:
            before_total, before_flag = await cur.fetchone()
        # Re-run migration — should be no-op (idempotent)
        await db.async_migrate_to_v28()
        marker2 = await db.async_get_model_state("data_migration_v28_completed")
        assert marker2 is not None
        assert marker2.get("completed") is True
        async with db._conn.execute(
            "SELECT COUNT(*), SUM(is_transition_artifact) FROM cop_samples"
        ) as cur:
            after_total, after_flag = await cur.fetchone()
        assert after_total == before_total, (
            f"row count changed: {before_total} -> {after_total}"
        )
        assert after_flag == before_flag, (
            f"artifact count changed: {before_flag} -> {after_flag}"
        )
        ok = await db.async_integrity_check()
        assert ok is True
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)



# ============================================================
# 13. Diagnostics exposes cop_source (v1.20.0 transparency)
# ============================================================


@pytest.mark.asyncio
async def test_diagnostics_exposes_cop_source(tmp_path) -> None:
    """v2 heat output -> snap.cop_source='espaltherma_heat_output' ->
    diagnostics output shows the correct source tag (no hidden fallback).
    """
    import json
    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry,
    )
    from custom_components.daikin_cycle_ml.const import DOMAIN

    db = await _mk_fresh_db(tmp_path)
    try:
        c = _make_coord_for_cop(db, cop_value=4.5, lwt=35.0, outdoor=10.0)
        # Set snap.cop_source as if _read_cop_effective returned the tag
        from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
        snap = DataSnapshot(last_sample_ts=time.time())
        snap.cop_source = "espaltherma_heat_output"
        snap.attrs = {}
        c.data = snap
        c._cop_today_cache = {}
        c._cop_today_heating_cache = {}
        c._stooklijn_cache = None
        c._baseline = None
        c._adaptive = None
        c._clusters = None
        c.store = MagicMock()
        c.store.count = MagicMock(return_value=0)
        c.store.last_cycle = MagicMock(return_value=None)
        c.store.counters = MagicMock(return_value={})

        entry = MockConfigEntry(
            domain=DOMAIN,
            entry_id="test_entry",
            data={"model": "epra12eav3"},
            options={},
        )
        entry.runtime_data = c

        from custom_components.daikin_cycle_ml.diagnostics import (
            async_get_config_entry_diagnostics,
        )
        c.hass = MagicMock()
        c.hass.config = MagicMock()
        result = await async_get_config_entry_diagnostics(c.hass, entry)
        # "coordinator" is a top-level key in diagnostics output (not nested
        # under "data" — that's entry.data config, which has no coordinator).
        coord_section = result.get("coordinator", {})
        assert coord_section.get("cop_source") == "espaltherma_heat_output", (
            f"diagnostics must expose cop_source in coordinator section; "
            f"got: {coord_section.get('cop_source')!r}; "
            f"available keys: {list(coord_section.keys())[:10]}"
        )
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)
