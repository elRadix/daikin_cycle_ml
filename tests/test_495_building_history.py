"""#495 PR 2: building day values rebuilt from cop_samples and cycle features."""
from __future__ import annotations

import json
import time

import pytest

from custom_components.daikin_cycle_ml.const import BUILDING_REBUILD_MARKER
from custom_components.daikin_cycle_ml.storage import building_history as bh
from custom_components.daikin_cycle_ml.storage import reports as rs
from tests.test_508_period_reports_coordinator import _coord, _mk_db

DAY = "2026-11-21"
T0 = rs.day_start_ts(DAY)


async def _sample(conn, ts, *, mode="heating", flow=18.0, r1t=30.0, r4t=26.0, boiler=0):
    await conn.execute(
        "INSERT INTO cop_samples (ts, cop, mode, boiler_active, flow_lmin, r1t, r4t) VALUES (?,?,?,?,?,?,?)",
        (ts, 5.0, mode, boiler, flow, r1t, r4t))


async def _cycle(conn, start, end, indoor):
    cur = await conn.execute("INSERT INTO cycles (start_ts, end_ts, duration_s, mode) VALUES (?,?,?,?)",
                             (start, end, int(end - start), "heating"))
    vec = [0.0] * 12
    vec[10] = indoor
    await conn.execute("INSERT INTO features (cycle_id, vector_json) VALUES (?,?)",
                       (cur.lastrowid, json.dumps(vec)))


async def test_rebuild_fills_old_days_only(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        # one hour of heating samples every 300 s: 5.02 kW for 12 x 300 s = 1 h
        for i in range(12):
            await _sample(conn, T0 + 3600 + i * 300)
        await _sample(conn, T0 + 7200, mode="dhw")                 # hot water: out
        await _sample(conn, T0 + 7500, boiler=1)                    # boiler: out
        await _sample(conn, T0 + 7800, flow=None)                   # no flow: out
        await _sample(conn, T0 + 8100, r1t=70.0)                    # dT 44 K: bad reading
        # a run from 18:00 on DAY to 06:00 the next day at 21 °C, one at 20 °C on DAY
        await _cycle(conn, T0 + 18 * 3600, T0 + 30 * 3600, 21.0)
        await _cycle(conn, T0 + 3600, T0 + 3 * 3600, 20.0)
        await _cycle(conn, T0 + 10, T0 + 600, 0.0)                  # no room sensor: out
        await conn.execute("INSERT INTO cycles (start_ts, end_ts, duration_s, mode) VALUES (?,?,?,?)",
                           (T0 + 20, T0 + 60, 40, "heating"))
        await conn.execute("INSERT INTO features (cycle_id, vector_json) VALUES (last_insert_rowid(), 'x')")
        nxt = time.strftime("%Y-%m-%d", time.localtime(T0 + 30 * 3600))
        await rs.upsert_days(conn, [
            (DAY, "all", {"el_kwh": 10.0}, [], True),               # finalised: still filled
            (nxt, "all", {"el_kwh": 9.0}, [], True),
            ("2026-11-25", "all", {"indoor_s": 100, "indoor_mean": 22.0}, [], True),   # live: kept
            ("2026-11-26", "all", {"el_kwh": 1.0}, [], False),      # no history: untouched
        ])
        stats = await bh.rebuild(conn)
        assert stats["days"] == 2
        rows = {r["day"]: r["data"] for r in await rs.fetch_days(conn, "2026-11-01", "2026-11-30", mode="all")}
        d = rows[DAY]
        assert d["building_reconstructed"] is True and d["el_kwh"] == 10.0
        assert d["heat_sh_signed_kwh"] == pytest.approx(18.0 * 4.186 * 4.0 / 60.0, abs=0.01)
        # last heating sample is followed by a dropped one 300 s later: 12 x 300 s
        assert d["heat_sh_s"] == 3600
        # DAY: 2 h at 20 °C + 6 h at 21 °C (18:00-24:00) -> 20.75
        assert d["indoor_mean"] == pytest.approx(20.75) and d["indoor_source"] == "cycles"
        assert rows[nxt]["indoor_mean"] == 21.0 and rows[nxt]["heat_sh_signed_kwh"] is None
        assert rows["2026-11-25"] == {"indoor_s": 100, "indoor_mean": 22.0}
        assert "building_reconstructed" not in rows["2026-11-26"]
    finally:
        await db.async_close()


async def test_coordinator_runs_it_once(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        c = _coord(db)
        await _sample(db._require(), T0 + 3600)
        await rs.upsert_days(db._require(), [(DAY, "all", {}, [], True)])
        assert await c._maybe_rebuild_building() is True
        marker = await db.async_get_model_state(BUILDING_REBUILD_MARKER)
        assert marker["completed"] is True and marker["days"] == 1
        assert await c._maybe_rebuild_building() is False
    finally:
        await db.async_close()


async def test_coordinator_no_db_and_failure(tmp_path):
    c = _coord(None)
    assert await c._maybe_rebuild_building() is False
    db = await _mk_db(tmp_path)
    await db.async_close()                      # closed: the rebuild fails, never raises
    c = _coord(db)
    assert await c._maybe_rebuild_building() is False


async def test_mocked_database_is_skipped():
    from unittest.mock import AsyncMock
    c = _coord(AsyncMock())
    c.db.async_get_model_state.return_value = None
    assert await c._maybe_rebuild_building() is False
