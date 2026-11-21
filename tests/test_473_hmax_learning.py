"""#473: maximum heat learned from this installation's own samples.

- cop_samples gets thermal_kw / power_w / rps / is_reconstructed; new
  samples carry the live values, the v34 migration back-fills older ones
  (thermal_kw = flow / 60 x (R1T - R4T) x 4.186, power_w = thermal_kw /
  COP x 1000, rps = rps_avg of the containing run).
- Per 5 K band of outdoor and water temperature, the p95 heat of samples
  at >= 90 % of rps_max is the learned maximum, only with >= 30 samples
  over >= 3 days.
- model_profile.apply_profile: manual > datasheet > learned.
"""
from __future__ import annotations

import sqlite3
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import _read_power_safe, _sample_heat_fields
from custom_components.daikin_cycle_ml.engine import hmax_learning as hl
from custom_components.daikin_cycle_ml.engine import model_profile as mp
from custom_components.daikin_cycle_ml.storage.db import CycleDB

DAY = 86400.0
T0 = time.mktime((2026, 1, 10, 6, 0, 0, 0, 0, -1))


def _rows(n, outdoor, water, kw, rps, days=3, rec=0, start=T0):
    """n full-speed samples spread over `days` days."""
    return [(start + (i % days) * DAY + i * 60, outdoor, water, kw if not callable(kw) else kw(i), rps, rec)
            for i in range(n)]


# ---------- bands and learning ----------

@pytest.mark.parametrize(("o", "w", "band"), [
    (-7.3, 34.0, (-7.0, 35.0)), (-4.6, 32.4, (-7.0, 30.0)), (-4.4, 37.6, (-2.0, 40.0)),
    (3.0, 35.0, (3.0, 35.0)), (13.1, 30.2, (13.0, 30.0)), (-12.0, 55.0, (-12.0, 55.0)),
])
def test_bands_are_5_k_around_the_anchors(o, w, band):
    assert hl.band_of(o, w) == band


def test_learns_p95_per_band_with_enough_samples_and_days():
    rows = _rows(412, -7.2, 34.5, lambda i: 8.0 + (i % 20) * 0.08, 60)
    res = hl.learn_hmax(rows, 64)
    assert res["rps_threshold"] == 57.6
    b = res["bands"][0]
    assert (b["t_out"], b["t_lwc"], b["n"], b["days"]) == (-7.0, 35.0, 412, 3)
    kws = sorted(8.0 + (i % 20) * 0.08 for i in range(412))
    pos = (len(kws) - 1) * 0.95
    expect = kws[int(pos)] + (kws[int(pos) + 1] - kws[int(pos)]) * (pos - int(pos))
    assert b["hmax"] == pytest.approx(round(expect, 2))


def test_too_few_samples_or_days_leaves_the_band_empty():
    assert hl.learn_hmax(_rows(29, -7, 35, 9.0, 60), 64)["bands"] == []
    res = hl.learn_hmax(_rows(40, -7, 35, 9.0, 60, days=2), 64)
    assert res["bands"] == [] and res["skipped_bands"] == 1


def test_only_full_speed_samples_count():
    slow = _rows(200, 13, 30, 3.0, 25)                 # mild weather: demand, not maximum
    fast = _rows(40, -7, 35, 9.4, 60)
    res = hl.learn_hmax(slow + fast, 64)
    assert [(b["t_out"], b["hmax"]) for b in res["bands"]] == [(-7.0, 9.4)]
    assert res["full_speed_samples"] == 40


def test_odd_samples_do_not_move_the_maximum():
    rows = _rows(100, -2, 40, 8.5, 62) + _rows(2, -2, 40, 30.0, 62)   # two spikes
    assert hl.learn_hmax(rows, 64)["bands"][0]["hmax"] == pytest.approx(8.5)


def test_reconstructed_samples_can_be_left_out_and_bad_rows_skipped():
    rows = _rows(40, -7, 35, 9.0, 60, rec=1) + [("x", -7, 35, 9, 60, 0), (T0, None, 35, 9, 60, 0),
                                               (T0, -7, 35, -1, 60, 0), (T0, -7, 35, 9, 60)]
    assert hl.learn_hmax(rows, 64)["bands"][0]["reconstructed"] == 40
    assert hl.learn_hmax(rows, 64, include_reconstructed=False)["bands"] == []
    assert hl.learn_hmax(rows, None) == {"bands": [], "full_speed_samples": 0, "rps_threshold": None, "skipped_bands": 0}
    assert hl.learn_hmax(rows, 0)["rps_threshold"] is None
    assert hl._num(True) is None and hl._num("nan") is None and hl._num("z") is None


# ---------- merge order: manual > datasheet > learned ----------

ERLA11 = {"kw": 11, "nom_cop": 4.83, "points": [
    {"label": "A7/W35", "t_out": 7, "t_lwc": 35, "cop": 4.83, "hc": 10.6},
    {"label": "A-7/W55", "t_out": -7, "t_lwc": 55, "cop": 1.82, "hc": 7.89}]}
EPRA12 = {"kw": 12, "nom_cop": 4.92, "points": [
    {"label": "A7/W35", "t_out": 7, "t_lwc": 35, "cop": 4.92, "hc": 6.17},
    {"label": "A-7/W35", "t_out": -7, "t_lwc": 35, "cop": 3.04, "hc": 4.8}]}
LEARNED = {"bands": [{"t_out": -7.0, "t_lwc": 35.0, "hmax": 9.4, "n": 412, "days": 9},
                     {"t_out": 7.0, "t_lwc": 35.0, "hmax": 8.8, "n": 300, "days": 5},
                     {"t_out": -7.0, "t_lwc": 55.0, "hmax": 7.0, "n": 50, "days": 3},
                     {"t_out": -12.0, "t_lwc": 45.0, "hmax": 8.1, "n": 31, "days": 3},
                     {"t_out": None, "t_lwc": 35, "hmax": 1}, {"t_out": 1, "t_lwc": 35, "hmax": 99}]}


def _pts(out):
    return {(p["t_out"], p["t_lwc"]): p for p in out["points"]}


def test_erla11_datasheet_stays_learned_only_adds_new_conditions():
    pts = _pts(mp.apply_profile(ERLA11, None, "erla11dav3", None, LEARNED))
    assert pts[(7.0, 35.0)]["hmax"] == 10.6 and pts[(7.0, 35.0)]["src"]["hmax"] == "datasheet"
    assert pts[(-7.0, 55.0)]["hmax"] == 7.89 and pts[(-7.0, 55.0)]["src"]["hmax"] == "datasheet"
    assert pts[(-7.0, 35.0)]["hmax"] == 9.4 and pts[(-7.0, 35.0)]["src"]["hmax"] == "learned"
    assert pts[(-7.0, 35.0)]["hmax_n"] == 412 and pts[(-7.0, 35.0)]["label"] == "A-7/W35"
    assert pts[(-12.0, 45.0)]["src"] == {"hmax": "learned"}
    assert (1.0, 35.0) not in pts                      # out-of-range learned value ignored


def test_epra12_keeps_its_datasheet_points_learned_fills_the_rest():
    """Maintainer decision: EPRA keeps every datasheet point like all models;
    learned values fill only conditions the datasheet does not list."""
    pts = _pts(mp.apply_profile(EPRA12, None, "epra12eav3", None, LEARNED))
    assert pts[(7.0, 35.0)]["hmax"] == 6.17 and pts[(7.0, 35.0)]["src"]["hmax"] == "datasheet"
    assert pts[(-7.0, 35.0)]["hmax"] == 4.8 and pts[(-7.0, 35.0)]["src"]["hmax"] == "datasheet"
    assert pts[(-7.0, 55.0)]["hmax"] == 7.0 and pts[(-7.0, 55.0)]["src"]["hmax"] == "learned"
    assert pts[(-12.0, 45.0)]["src"] == {"hmax": "learned"}


def test_manual_beats_learned():
    prof = mp.edit({}, "epra12eav3", points=[{"t_out": -7, "t_lwc": 55, "hmax": 7.5}])
    pts = _pts(mp.apply_profile(EPRA12, prof, "epra12eav3", None, LEARNED))
    assert pts[(-7.0, 55.0)]["hmax"] == 7.5 and pts[(-7.0, 55.0)]["src"]["hmax"] == "manual"
    assert "hmax_n" not in pts[(-7.0, 55.0)]


# ---------- live sample fields ----------

def test_sample_heat_fields_formula_and_fallbacks():
    f = _sample_heat_fields(18, 34.5, 29.5, 4.8, None, 58)
    assert f["thermal_kw"] == pytest.approx(6.279, abs=1e-3)       # 18/60 x 5.0 x 4.186
    assert f["power_w"] == pytest.approx(1308.1, abs=0.1)           # 6.279 / 4.8 x 1000
    assert f["rps"] == 58
    assert _sample_heat_fields(18, 34.5, 29.5, 4.8, 1250.0, "0")["power_w"] == 1250.0   # the meter wins
    assert _sample_heat_fields(0, 34.5, 29.5, 4.8, None, None) == {"thermal_kw": None, "power_w": None, "rps": None}
    assert _sample_heat_fields(18, 29.0, 30.0, None, "x", float("inf"))["thermal_kw"] is None


def test_read_power_safe():
    assert _read_power_safe(SimpleNamespace(hass=None, _read_power_w=lambda: 900.0)) is None
    assert _read_power_safe(SimpleNamespace(hass=1, _read_power_w=lambda: 900.0)) == 900.0
    assert _read_power_safe(SimpleNamespace(hass=1, _read_power_w=lambda: 0)) is None
    assert _read_power_safe(SimpleNamespace(hass=1, _read_power_w=lambda: True)) is None

    def boom():
        raise TypeError("no meter")

    assert _read_power_safe(SimpleNamespace(hass=1, _read_power_w=boom)) is None
    assert _read_power_safe(SimpleNamespace(hass=1)) is None


# ---------- DB: migration v34 and the learning query on the real schema ----------

async def _db(tmp_path):
    db = CycleDB(str(tmp_path / "t.db"))
    await db.async_initialize()
    return db


async def _insert_old(db, ts, cop, flow, r1t, r4t, mode="heating", artifact=0, boiler=0, outdoor=-7.0):
    await db._conn.execute(
        "INSERT INTO cop_samples (ts, cop, lwt, outdoor, r1t, r4t, flow_lmin, mode, is_transition_artifact, boiler_active) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)", (ts, cop, r1t, outdoor, r1t, r4t, flow, mode, artifact, boiler))


async def test_v34_reconstructs_old_samples_once(tmp_path):
    db = await _db(tmp_path)
    try:
        await db._conn.execute("INSERT INTO cycles (start_ts, end_ts, duration_s, mode, rps_avg) VALUES (1000, 5000, 4000, 'heating', 41.5)")
        await _insert_old(db, 2000, 4.8, 18, 34.5, 29.5)             # the example
        await _insert_old(db, 9000, 4.0, 12, 30.0, 27.0)             # outside any run: rps NULL
        await _insert_old(db, 2100, 4.8, 0, 34.5, 29.5)              # no flow
        await _insert_old(db, 2200, 4.8, 18, 29.0, 30.0)             # R1T <= R4T
        await _insert_old(db, 2300, 4.8, 18, 34.5, 29.5, artifact=1)
        await _insert_old(db, 2400, 4.8, 18, 34.5, 29.5, boiler=1)
        await _insert_old(db, 2500, 0.0, 18, 34.5, 29.5)             # no COP
        await db._conn.commit()
        stats = await db.async_migrate_to_v34()
        assert stats == {"samples_reconstructed": 2, "completed": True}
        cur = await db._conn.execute("SELECT ts, thermal_kw, power_w, rps, is_reconstructed FROM cop_samples ORDER BY ts")
        rows = {r[0]: r[1:] for r in await cur.fetchall()}
        await cur.close()
        assert rows[2000][0] == pytest.approx(6.279, abs=1e-3) and rows[2000][1] == pytest.approx(1308.1, abs=0.1)
        assert rows[2000][2] == 41.5 and rows[2000][3] == 1
        assert rows[9000][2] is None and rows[9000][3] == 1
        for ts in (2100, 2200, 2300, 2400, 2500):
            assert rows[ts] == (None, None, None, 0), ts
        assert await db.async_migrate_to_v34() == {"skipped": 1}
    finally:
        await db.async_close()


async def test_new_samples_store_heat_power_speed_and_feed_the_learning(tmp_path):
    db = await _db(tmp_path)
    try:
        assert await db.async_insert_cop_sample({"ts": 3000.0, "cop": 3.1, "lwt": 35.0, "outdoor": -7.0, "mode": "heating",
                                                 "thermal_kw": 9.2, "power_w": 2970.0, "rps": 61.0})
        assert await db.async_insert_cop_sample({"ts": 3100.0, "cop": 3.1, "mode": "dhw", "thermal_kw": 9.0, "rps": 61.0})
        assert await db.async_insert_cop_sample({"ts": 3200.0, "cop": 3.1, "mode": "heating"})
        rows = await db.async_hmax_samples(0.0)
        assert rows == [(3000.0, -7.0, 35.0, 9.2, 61.0, 0)]
        assert await db.async_hmax_samples(4000.0) == []
    finally:
        await db.async_close()
    none = CycleDB.__new__(CycleDB)
    none._conn = None
    assert await none.async_hmax_samples(0.0) == []
    bad = CycleDB.__new__(CycleDB)
    bad._conn = MagicMock()
    bad._conn.execute = AsyncMock(side_effect=sqlite3.OperationalError("locked"))
    assert await bad.async_hmax_samples(0.0) == []


async def test_existing_table_gets_the_new_columns(tmp_path):
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE cop_samples (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, cop REAL NOT NULL, "
                "lwt REAL, outdoor REAL, r1t REAL, r4t REAL, flow_lmin REAL, power_stable INTEGER DEFAULT 0, "
                "mode TEXT DEFAULT 'unknown', source TEXT DEFAULT 'interval', mode_original TEXT, "
                "is_transition_artifact INTEGER DEFAULT 0)")
    con.commit()
    con.close()
    db = CycleDB(str(path))
    await db.async_initialize()
    try:
        await db.async_ensure_cop_samples_table()
        cur = await db._conn.execute("PRAGMA table_info(cop_samples)")
        cols = {r[1] for r in await cur.fetchall()}
        await cur.close()
        assert {"thermal_kw", "power_w", "rps", "is_reconstructed", "boiler_active"} <= cols
    finally:
        await db.async_close()


# ---------- coordinator wiring ----------

def _coord(profile=None, learned=None):
    from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator

    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.entry = SimpleNamespace(entry_id="e1", data={"model": "epra12eav3"})
    c._model_profile = profile or mp.empty_profile()
    c._rps_learned = learned or {}
    c._hmax_learned = {}
    c._hmax_learned_ts = 0.0
    return c


async def test_refresh_learns_stores_and_throttles():
    rows = _rows(40, -7, 35, 9.4, 60)
    db = SimpleNamespace(async_hmax_samples=AsyncMock(return_value=rows), async_set_model_state=AsyncMock())
    c = _coord(learned={"rps_max": 64.0})
    await c._refresh_hmax_learned(db)
    assert c.hmax_learned["bands"][0]["hmax"] == pytest.approx(9.4)
    key, value = db.async_set_model_state.await_args.args
    assert key == "hmax_learned" and value["bands"] == c.hmax_learned["bands"] and value["updated_ts"] > 0
    await c._refresh_hmax_learned(db)                  # within 6 h: not again
    assert db.async_hmax_samples.await_count == 1


async def test_refresh_uses_the_manual_speed_range_and_tolerates_old_dbs():
    rows = _rows(40, -7, 35, 9.4, 50)
    db = SimpleNamespace(async_hmax_samples=AsyncMock(return_value=rows))
    c = _coord(profile=mp.edit({}, "epra12eav3", fields={"rps_max": 55}), learned={"rps_max": 90.0})
    await c._refresh_hmax_learned(db)                  # 50 >= 0.9 x 55, not >= 0.9 x 90
    assert c.hmax_learned["rps_threshold"] == 49.5 and c.hmax_learned["bands"]
    c2 = _coord()
    await c2._refresh_hmax_learned(SimpleNamespace())  # no learning query: nothing
    assert c2.hmax_learned == {}
    c3 = _coord()
    c3.entry = None
    await c3._refresh_hmax_learned(db)
    assert c3.hmax_learned["bands"] == []              # no speed range known yet


async def test_coordinator_sample_carries_heat_power_and_speed():
    """The real sample path (_maybe_collect_cop_sample) writes the new fields."""
    from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
    from tests.test_218_evlq_hybrid import _cop_coord

    c = _cop_coord(state="running", boiler_active=False)
    c.data.attrs["INV frequency (rps)"] = 58.0
    c.hass = None                                     # no power meter: power from heat / COP
    await DaikinCycleMLCoordinator._maybe_collect_cop_sample(c, now=10000.0)
    row = c.db.async_insert_cop_sample.await_args.args[0]
    assert row["thermal_kw"] == pytest.approx(15 / 60 * 5.0 * 4.186, abs=1e-3)   # R1T 30, R4T 25
    assert row["rps"] == 58.0
    assert row["power_w"] == pytest.approx(row["thermal_kw"] / row["cop"] * 1000, abs=0.2)
