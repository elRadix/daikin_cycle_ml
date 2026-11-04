"""v1.19.7: cross-midnight attribution + full-week 24/7 E2E."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta

import pytest

from custom_components.daikin_cycle_ml.storage.db import CycleDB

DAY = 86400.0


async def _mk_db(tmp_path, name="test.db"):
    db = CycleDB(str(tmp_path / name))
    await db.async_open()
    await db.async_initialize()
    return db


def _ts(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp()


async def _ins(conn, start, end, mode="heating", **kw):
    dur = int(end - start)
    await conn.execute(
        "INSERT INTO cycles "
        "(start_ts, end_ts, duration_s, mode, is_transient, "
        " is_reconstructed, quality_score, dT_max, rps_avg, "
        " buh_used, defrost_used, thermal_kw_avg) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (start, end, dur, mode, kw.get("is_transient", 0),
         kw.get("is_reconstructed", 0), kw.get("quality_score", 80),
         kw.get("dT_max", 4.0), kw.get("rps_avg", 25.0),
         kw.get("buh_used", 0), kw.get("defrost_used", 0),
         kw.get("thermal_kw_avg", 3.0)),
    )


# ===== CROSS-MIDNIGHT PRO-RATA =====

@pytest.mark.asyncio
async def test_cross_midnight_split_pro_rata(tmp_path):
    """16.25h cycle Oct26 13:31 -> Oct27 05:46 attributes pro-rata."""
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        start = _ts(2026, 10, 26, 13, 31)
        end = _ts(2026, 10, 27, 5, 46)
        await _ins(conn, start, end, mode="heating")
        await conn.commit()

        await db.async_rollup_day("2026-10-26")
        await db.async_rollup_day("2026-10-27")

        rows = dict(
            (r[0], r[1]) for r in await (await conn.execute(
                "SELECT day, total_duration_s FROM daily_summary WHERE mode='heating'"
            )).fetchall()
        )
        oct26 = rows.get("2026-10-26", 0)
        oct27 = rows.get("2026-10-27", 0)

        assert 9.5*3600 <= oct26 <= 11.5*3600, f"Oct26 {oct26/3600:.2f}h != ~10.5h"
        assert 5.0*3600 <= oct27 <= 6.5*3600, f"Oct27 {oct27/3600:.2f}h != ~5.75h"
        assert 15.5*3600 <= oct26+oct27 <= 17.0*3600, f"Sum {(oct26+oct27)/3600:.2f}h != 16.25h"
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_single_day_cycle_attributed_fully(tmp_path):
    """8h cycle fully on one day -> all 8h to that day."""
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        await _ins(conn, _ts(2026,10,20,10), _ts(2026,10,20,18))
        await conn.commit()
        await db.async_rollup_day("2026-10-20")
        r = await (await conn.execute(
            "SELECT total_duration_s FROM daily_summary "
            "WHERE day='2026-10-20' AND mode='heating'"
        )).fetchone()
        assert r is not None
        assert abs(r[0] - 8*3600) < 60, f"got {r[0]/3600:.2f}h"
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_mixed_cross_midnight_sum_preserved(tmp_path):
    """Mix of same-day + cross-midnight: grand total preserved."""
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        d1 = _ts(2026,10,26)
        await _ins(conn, d1, d1 + 6*3600)              # 6h Oct 26
        await _ins(conn, d1 + 22*3600, d1 + 28*3600)   # 22-24 Oct26 (2h) + 0-4 Oct27 (4h)
        await conn.commit()
        await db.async_rollup_day("2026-10-26")
        await db.async_rollup_day("2026-10-27")
        rows = dict(
            (r[0], r[1]) for r in await (await conn.execute(
                "SELECT day, total_duration_s FROM daily_summary WHERE mode='heating'"
            )).fetchall()
        )
        assert abs(rows.get("2026-10-26", 0) - 8*3600) < 60, f"Oct26 {rows.get('2026-10-26')/3600:.2f}h != 8"
        assert abs(rows.get("2026-10-27", 0) - 4*3600) < 60, f"Oct27 {rows.get('2026-10-27')/3600:.2f}h != 4"
        assert abs(sum(rows.values()) - 12*3600) < 60
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ===== FULL-WEEK 24/7 — COLD (5°C avg, 22-24h/day) =====

@pytest.mark.asyncio
async def test_cold_week_24_7_22_to_24h(tmp_path):
    """7 days continuous heating, 1 DHW 90min/day, 2 defrost splits/day.
    Assert each day heating in [20h, 24h]."""
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        base = datetime(2026, 11, 4, tzinfo=timezone.utc)
        for off in range(7):
            ds = (base + timedelta(days=off)).timestamp()
            de = ds + DAY
            # DHW 08:00-09:30
            await _ins(conn, ds+8*3600, ds+9.5*3600, mode="dhw")
            # Heating segments with realistic gaps (defrost + DHW)
            await _ins(conn, ds, ds+8*3600, mode="heating")
            await _ins(conn, ds+9.5*3600, ds+14*3600, mode="heating")
            await _ins(conn, ds+14.2*3600, ds+18*3600, mode="heating")
            # Last segment crosses midnight (ends at exactly 24:00 -> next day 00:00)
            await _ins(conn, ds+18*3600, de, mode="heating")
        await conn.commit()

        for off in range(7):
            day_str = (base + timedelta(days=off)).strftime("%Y-%m-%d")
            await db.async_rollup_day(day_str)

        rows = await (await conn.execute(
            "SELECT day, mode, ROUND(total_duration_s/3600.0, 2) "
            "FROM daily_summary ORDER BY day, mode"
        )).fetchall()
        heat = {d: h for d, m, h in rows if m == "heating"}
        dhw  = {d: h for d, m, h in rows if m == "dhw"}
        assert len(heat) == 7, f"expected 7 days, got {len(heat)}"
        for d, h in heat.items():
            assert 20.0 <= h <= 24.0, f"{d} heating {h}h outside [20,24]"
        for d, h in dhw.items():
            assert 1.3 <= h <= 1.7, f"{d} dhw {h}h outside [1.3,1.7]"
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ===== FULL-WEEK MILD (14°C, modulated, 10-18h/day) =====

@pytest.mark.asyncio
async def test_mild_week_modulated_10_to_18h(tmp_path):
    """Mild day: multiple short cycles, ~12.5h active total. Proves we
    don't over-attribute when the WP is actually modulated."""
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        ds = _ts(2026, 10, 28)
        # Realistic Oct-28-like: 5h + 1.5h DHW + 1.5h + 3h + 1.5h
        await _ins(conn, ds+5*3600, ds+10*3600, mode="heating")
        await _ins(conn, ds+10*3600, ds+11.5*3600, mode="dhw")
        await _ins(conn, ds+12*3600, ds+13.5*3600, mode="heating")
        await _ins(conn, ds+17.5*3600, ds+20.5*3600, mode="heating")
        await _ins(conn, ds+21*3600, ds+22.5*3600, mode="heating")
        await conn.commit()

        await db.async_rollup_day("2026-10-28")

        rows = dict(
            (r[0], r[1]) for r in await (await conn.execute(
                "SELECT mode, ROUND(total_duration_s/3600.0, 2) "
                "FROM daily_summary WHERE day='2026-10-28'"
            )).fetchall()
        )
        assert 10.0 <= rows.get("heating", 0) <= 12.0, f"heating {rows.get('heating')}h"
        assert 1.3 <= rows.get("dhw", 0) <= 1.7, f"dhw {rows.get('dhw')}h"
        total = rows.get("heating", 0) + rows.get("dhw", 0)
        assert 11.5 <= total <= 13.5, f"total {total}h != ~12.5h"
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


# ===== COORDINATOR _maybe_rollup_day CROSS-MIDNIGHT =====

@pytest.mark.asyncio
async def test_maybe_rollup_day_crosses_midnight(tmp_path):
    """Coordinator's live rollup path must rebuild both days on cross-midnight."""
    from types import SimpleNamespace
    from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator

    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        start = _ts(2026, 11, 2, 22, 0)
        end = _ts(2026, 11, 3, 10, 0)
        await _ins(conn, start, end, mode="heating")
        await conn.commit()

        c = SimpleNamespace(
            db=db,
            options={"daily_summary_live_enabled": True},
        )
        async def _noop():
            return None
        c._refresh_daily_summary_recent = _noop

        record = {"start_ts": start, "end_ts": end, "mode": "heating"}
        await DaikinCycleMLCoordinator._maybe_rollup_day(c, record)

        rows = dict(
            (r[0], r[1]) for r in await (await conn.execute(
                "SELECT day, total_duration_s FROM daily_summary WHERE mode='heating'"
            )).fetchall()
        )
        assert abs(rows.get("2026-11-02", 0) - 2*3600) < 60, f"Nov2 {rows.get('2026-11-02')/3600:.2f}h != 2"
        assert abs(rows.get("2026-11-03", 0) - 10*3600) < 60, f"Nov3 {rows.get('2026-11-03')/3600:.2f}h != 10"
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)

