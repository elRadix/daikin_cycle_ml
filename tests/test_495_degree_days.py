"""#495 PR 3: degree-day sensors on the #508 day rows."""
from __future__ import annotations

import datetime as dt
import time
from types import SimpleNamespace

import pytest

from custom_components.daikin_cycle_ml import sensor as s_mod
from custom_components.daikin_cycle_ml.storage import building_query as bq
from custom_components.daikin_cycle_ml.storage import reports as rs
from tests.test_508_period_reports_coordinator import _coord, _mk_db

TODAY = "2026-11-28"


def _d(n: int) -> str:
    return (dt.date.fromisoformat(TODAY) - dt.timedelta(days=n)).isoformat()


async def _seed(conn):
    rows = []
    for n in range(1, 41):            # 40 days back, inside the season from 1 Oct
        rows.append((_d(n), "all", {"degree_days": {"nl18": 10.0, "be165": 8.0}, "outdoor_mean": 8.0 - n * 0.01},
                     [], True))
        rows.append((_d(n), "heating", {"th_kwh": 80.0}, [], True))
    rows.append((_d(41), "all", {"degree_days": None}, [], True))           # no temps: left out
    rows.append((_d(42), "heating", {"th_kwh": None}, [], True))
    await rs.upsert_days(conn, rows)


async def test_summary_windows(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        await _seed(db._require())
        out = await bq.summary(db._require(), "nl18", TODAY, 10)
        assert out["yesterday"] == 10.0 and out["season_since"] == "2026-10-01"
        assert out["week"] == {"kwh": 560.0, "dd": 70.0, "days": 7, "kwh_per_dd": 8.0}
        assert out["month"]["days"] == 30 and out["month"]["kwh_per_dd"] == 8.0
        assert out["season"]["days"] == 40 and out["season"]["dd"] == 400.0
        assert set(out["prev_means"]) == {_d(1), _d(2)}
        empty = await bq.summary(db._require(), "nl18", "2026-01-15", 10)
        assert empty["week"]["kwh_per_dd"] is None and empty["yesterday"] is None
    finally:
        await db.async_close()


def test_per_dd_needs_one_degree_day():
    assert bq._per_dd([(5.0, 0.5)])["kwh_per_dd"] is None
    assert bq._per_dd([(None, 3.0), (6.0, None)])["days"] == 0


def test_today_dd_uses_the_days_before_for_belgium():
    out = bq.today_dd(TODAY, 4.0, 1.0, 9.0, {_d(1): 6.0, _d(2): None})
    assert out["nl18"] == 14.0 and out["fr18"] == 13.0
    # 0.6 x 4 + 0.3 x 6 + 0.1 x 4 (missing -> today) = 4.6 -> 16.5 - 4.6
    assert out["be165"] == pytest.approx(11.9)
    assert bq.today_dd(TODAY, None, None, None, None) is None


def test_coordinator_live_today_and_sensors():
    c = _coord()
    c.options = {"degree_day_scheme": "nl18"}
    c._degree_day_summary = {"yesterday": 10.0, "week": {"kwh_per_dd": 8.0}, "season": {"dd": 400.0},
                             "season_since": "2026-10-01", "prev_means": {}}
    c._outdoor_sum, c._outdoor_s, c._outdoor_min, c._outdoor_max = 30.0, 10.0, 1.0, 5.0
    d = c.degree_days
    assert d["scheme"] == "nl18" and d["today"] == 15.0 and d["outdoor_mean_today"] == 3.0
    defs = {x["key"]: x for x in s_mod.SENSOR_DEFS}
    snap = SimpleNamespace()
    assert defs["degree_days_today"]["value_fn"](snap, c) == 15.0
    attrs = defs["degree_days_today"]["attr_fn"](snap, c)
    assert attrs["yesterday"] == 10.0 and attrs["season_dd"] == 400.0 and attrs["today_all"]["nl18"] == 15.0
    assert defs["heat_per_degree_day"]["value_fn"](snap, c) == 8.0
    assert defs["heat_per_degree_day"]["attr_fn"](snap, c)["week"] == {"kwh_per_dd": 8.0}
    # nothing yet: unknown, never raises
    c2 = _coord()
    c2.options = {}
    assert c2.degree_days["today"] is None
    assert defs["heat_per_degree_day"]["value_fn"](snap, c2) is None


async def test_refresh_fills_the_summary(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        today = time.strftime("%Y-%m-%d")
        y = (dt.date.fromisoformat(today) - dt.timedelta(days=1)).isoformat()
        await rs.upsert_days(db._require(), [(y, "all", {"degree_days": {"nl18": 9.0}}, [], True)])
        c = _coord(db)
        c.options = {"degree_day_scheme": "nl18"}
        await c.async_refresh_report_summary()
        assert c.degree_days["yesterday"] == 9.0
    finally:
        await db.async_close()
