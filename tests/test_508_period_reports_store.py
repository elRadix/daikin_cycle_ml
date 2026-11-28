"""#508 period reports: sources read through the real write paths, the
builder (finalising, never rewriting a frozen row, rebuild) and maintenance
never pruning the report tables."""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import time

import pytest

from custom_components.daikin_cycle_ml.storage import report_builder as rb
from custom_components.daikin_cycle_ml.storage import reports as store
from custom_components.daikin_cycle_ml.storage.db import CycleDB

pytestmark = pytest.mark.usefixtures("at_noon")


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.localtime())


def _shift(day: str, n: int) -> str:
    return (dt.date.fromisoformat(day) + dt.timedelta(days=n)).isoformat()


def _ts(day: str, h: int, mi: int = 0) -> float:
    return time.mktime(time.strptime(f"{day} {h:02d}:{mi:02d}", "%Y-%m-%d %H:%M"))


async def _mk_db(tmp_path) -> CycleDB:
    db = CycleDB(str(tmp_path / "t508.db"))
    await db.async_open()
    await db.async_initialize()
    return db


async def _close(db: CycleDB) -> None:
    await db.async_close()
    await asyncio.sleep(0.05)


async def _cycle(db: CycleDB, start: float, end: float, mode: str = "heating", q: int = 80) -> None:
    conn = db._require()
    await conn.execute(
        "INSERT INTO cycles (start_ts, end_ts, duration_s, mode, is_transient, quality_score, "
        "dT_max, rps_avg, buh_used, defrost_used) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (start, end, int(end - start), mode, 0, q, 5.0, 40.0, 0, 1),
    )
    await conn.commit()


def _sample(ts: float, mode: str = "heating", **kw) -> dict:
    s = {"ts": ts, "cop": 4.0, "lwt": 32.0, "outdoor": 5.0, "r1t": 32.0, "r4t": 28.0,
         "flow_lmin": 15.0, "power_stable": True, "mode": mode, "source": "interval",
         "boiler_active": 0, "boiler_mode": "", "power_w": 1000.0}
    s.update(kw)
    return s


async def _seed_day(db: CycleDB, day: str, *, el: float = 2.0, th: float = 8.0) -> None:
    """One heating day as the coordinator writes it: two 1 h runs, energy,
    runtime / outdoor accumulators, a COP sample every 5 min, an alert."""
    for h in (8, 14):
        await _cycle(db, _ts(day, h), _ts(day, h + 1))
        for i in range(12):
            await db.async_insert_cop_sample(_sample(_ts(day, h) + i * 300.0))
    await db.async_insert_cop_sample(_sample(_ts(day, 10), is_transition_artifact=1, r4t=10.0))
    await db.async_insert_cop_sample(_sample(_ts(day, 11), boiler_active=1, r4t=10.0))
    await db.async_insert_cop_sample(_sample(_ts(day, 12), mode=None, buh_active=1))
    await db.async_rollup_day(day)
    await db.async_set_model_state(f"energy_acc.{day}", {
        "day": day, "heating_el_kwh": el, "heating_th_kwh": th,
        "dhw_el_kwh": 0.0, "dhw_th_kwh": 0.0, "cooling_el_kwh": 0.0, "cooling_th_kwh": 0.0})
    await db.async_set_model_state(f"runtime_acc.{day}", {
        "day": day, "buh_total_s": 600.0, "defrost_count": 2, "defrost_duration_s": 300.0,
        "outdoor_sum": 3.0 * 86400, "outdoor_s": 86400.0, "outdoor_min": -2.0, "outdoor_max": 8.0,
        "source_fresh_s": 86400.0})
    await db.async_insert_alert("ml_anomaly", "warning", "x", ts=_ts(day, 9))
    await db.async_rollup_cop_hourly(window_hours=24 * 40)


async def test_fetch_sources_from_real_writes(tmp_path):
    db = await _mk_db(tmp_path)
    day = _shift(_today(), -5)
    try:
        await _seed_day(db, day)
        await db.async_set_model_state(f"energy_acc.{_shift(day, 1)}", "corrupt")
        conn = db._require()
        await conn.execute("INSERT INTO model_state (key, value_json, updated_ts) VALUES (?, ?, 0)",
                           (f"runtime_acc.{_shift(day, 2)}", "{not json"))
        await conn.commit()
        src = await store.fetch_sources(conn, day, _shift(day, 2), sample_interval_s=300.0)
        heat = src[day]["modes"]["heating"]
        assert heat["daily_summary"]["cycles"] == 2
        assert heat["daily_summary"]["total_duration_s"] == 7200
        assert heat["el_kwh"] == 2.0 and heat["th_kwh"] == 8.0
        assert heat["hourly"]["lwt_mean"] == pytest.approx(32.0)
        # 24 clean samples: artifact and boiler samples left out
        smp = heat["samples"]
        assert smp["n"] == 24 and smp["r4t_mean"] == pytest.approx(28.0)
        # 15 l/min x 4 K = 4.19 kW for 2 h
        assert smp["heat_kwh"] == pytest.approx(15 / 60 * 4.186 * 4 * 2, rel=1e-6)
        assert smp["power_kwh"] == pytest.approx(2.0)
        assert src[day]["modes"]["unknown"]["samples"]["buh_n"] == 1
        assert src[day]["alerts"] == {"ml_anomaly": 1}
        assert src[day]["temps"] == {"mean": 3.0, "min": -2.0, "max": 8.0, "source": "all_day"}
        assert await store.first_source_day(conn) == day
    finally:
        await _close(db)


async def test_temps_fall_back_to_running_hours(tmp_path):
    db = await _mk_db(tmp_path)
    day = _shift(_today(), -3)
    try:
        await _seed_day(db, day)
        await db.async_set_model_state(f"runtime_acc.{day}", {"day": day, "buh_total_s": 0.0})
        src = await store.fetch_sources(db._require(), day, day, sample_interval_s=300.0)
        assert src[day]["temps"]["source"] == "running_hours"
        assert src[day]["temps"]["mean"] == pytest.approx(5.0)
        assert src[day]["temps"]["min"] == pytest.approx(5.0)
    finally:
        await _close(db)


async def test_build_reports_days_periods_and_freeze(tmp_path):
    db = await _mk_db(tmp_path)
    today = _today()
    old, recent = _shift(today, -6), _shift(today, -1)
    try:
        assert await rb.build_reports(db, today=today) == {"days": 0, "periods": 0}
        await _seed_day(db, old)
        await _seed_day(db, recent, el=1.0, th=1.5)        # COP 1.5 at 5 °C / 32 °C: valid
        out = await rb.build_reports(db, today=today)
        assert out["first_day"] == old and out["last_final_day"] == _shift(today, -2)
        conn = db._require()
        days = {(r["day"], r["mode"]): r for r in await store.fetch_days(conn, old, today)}
        heat = days[(old, "heating")]
        assert heat["finalised"] and heat["checks"] == []
        assert heat["data"]["cop"] == 4.0 and heat["data"]["runs"] == 2
        assert heat["data"]["defrost_cycles"] == 2
        all_old = days[(old, "all")]["data"]
        assert all_old["outdoor_mean"] == 3.0 and all_old["coverage"] == 1.0
        assert all_old["degree_days"]["nl18"] == 15.0 and all_old["ml_anomalies"] == 1
        assert days[(recent, "all")]["finalised"] is False          # yesterday stays open
        # The days between have no source: no rows.
        assert (_shift(old, 1), "all") not in days

        month = await store.fetch_periods(conn, "month", [old[:7]], mode="all")
        assert month and month[0]["data"]["n_days_recorded"] >= 1
        weeks = await store.fetch_periods(conn, "week")
        assert {w["mode"] for w in weeks} == {"heating", "all"}
        assert all(not w["finalised"] or w["last_day"] <= _shift(today, -2) for w in weeks)

        # A frozen day is never rewritten by a later build ...
        await db.async_set_model_state(f"energy_acc.{old}", {"day": old, "heating_el_kwh": 4.0,
                                                             "heating_th_kwh": 8.0})
        await rb.build_reports(db, today=today)
        again = await store.fetch_days(conn, old, old, mode="heating")
        assert again[0]["data"]["cop"] == 4.0
        # ... only a rebuild clears it.
        out = await rb.build_reports(db, today=today, full=True)
        rebuilt = await store.fetch_days(conn, old, old, mode="heating")
        assert rebuilt[0]["data"]["cop"] == 2.0
        assert out["last_final_day"] == _shift(today, -2)
        counts = await store.counts(conn)
        assert counts["daily_stats"] >= 4 and counts["period_reports"] >= 8
    finally:
        await _close(db)


async def test_incremental_build_starts_after_last_frozen_day(tmp_path):
    db = await _mk_db(tmp_path)
    today = _today()
    try:
        await _seed_day(db, _shift(today, -20))
        await rb.build_reports(db, today=today)
        await db.async_set_model_state(rb.REPORTS_STATE_KEY, {"last_final_day": _shift(today, -5)})
        out = await rb.build_reports(db, today=today)
        assert out["first_day"] == _shift(today, -4)
        assert out["days"] == 0
        assert out["last_final_day"] == _shift(today, -2)
        # A state ahead of the clock still rebuilds the open days.
        await db.async_set_model_state(rb.REPORTS_STATE_KEY, {"last_final_day": today})
        out = await rb.build_reports(db, today=today)
        assert out["first_day"] == _shift(today, -2)
    finally:
        await _close(db)


async def test_failing_day_flagged_and_outlier_history(tmp_path):
    db = await _mk_db(tmp_path)
    today = _today()
    bad = _shift(today, -4)
    try:
        await _seed_day(db, bad, el=2.0, th=1.0)            # COP 0.5
        # Heat and power match the samples (COP 4.19), but 30 days in this band read 6.0.
        await _seed_day(db, _shift(today, -3), el=2.0, th=8.37)
        conn = db._require()
        # 30 earlier days at COP 4 in the same outdoor band feed the outlier check.
        hist = [(_shift(bad, -i), "heating", {"cop": 6.0, "outdoor_run_mean": 5.0}, [], True)
                for i in range(1, 31)]
        hist.append((_shift(bad, -31), "heating", {"cop": 9.0, "outdoor_run_mean": 5.0},
                     ["cop_out_of_range"], True))
        await store.upsert_days(conn, hist)
        await db.async_set_model_state(rb.REPORTS_STATE_KEY, {"last_final_day": _shift(bad, -1)})
        await rb.build_reports(db, today=today)
        row = (await store.fetch_days(conn, bad, bad, mode="heating"))[0]
        # COP 0.5, and the samples measured 8.4 kWh of heat, not 1.0
        assert row["checks"] == ["cop_out_of_range", "heat_mismatch"]
        all_row = (await store.fetch_days(conn, bad, bad, mode="all"))[0]
        assert all_row["data"]["cop"] is None and "cop_out_of_range" in all_row["checks"]

        row = (await store.fetch_days(conn, _shift(today, -3), _shift(today, -3), mode="heating"))[0]
        assert row["checks"] == ["outlier"]
    finally:
        await _close(db)


async def test_maintenance_never_prunes_reports(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        conn = db._require()
        await store.upsert_days(conn, [("2001-01-01", "all", {"el_kwh": 1.0}, [], True)])
        await store.upsert_period(conn, "year", "2001", "all", "2001-01-01", "2001-12-31", {}, True)
        await conn.commit()
        await db.async_run_maintenance(vacuum=False)
        assert await store.counts(conn) == {"daily_stats": 1, "period_reports": 1}
        # A frozen period is never rewritten either.
        await store.upsert_period(conn, "year", "2001", "all", "2001-01-01", "2001-12-31",
                                  {"el_kwh": 9.0}, False)
        assert (await store.fetch_periods(conn, "year", ["2001"]))[0]["data"] == {}
    finally:
        await _close(db)


def test_day_length_follows_dst(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Brussels")
    time.tzset()
    try:
        assert store.day_length_s("2026-03-29") == 23 * 3600
        assert store.day_length_s("2026-10-25") == 25 * 3600
        assert store.day_length_s("2026-11-28") == 24 * 3600
        assert store._local_day(store.day_start_ts("2026-03-29") + 3600) == "2026-03-29"
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()


async def test_sources_with_missing_values(tmp_path):
    """Sparse rows (older versions, sensors without a value) never break a day."""
    db = await _mk_db(tmp_path)
    day = _shift(_today(), -3)
    try:
        await db.async_create_cop_hourly_v14()
        conn = db._require()
        h = int(_ts(day, 6) // 3600)
        await conn.executemany(
            "INSERT INTO cop_hourly (ts_hour, mode, n_samples, lwt_mean, outdoor_mean, outdoor_min, "
            "outdoor_max, flow_mean, updated_ts) VALUES (?,?,?,?,?,?,?,?,0)",
            [(h, "heating", 0, 30.0, 5.0, 4.0, 6.0, 15.0),          # empty hour: skipped
             (h + 1, "heating", 6, None, None, None, None, None),   # no temperatures
             (h + 2, "heating", 6, 30.0, 4.0, None, 7.0, 15.0)],
        )
        await conn.commit()
        t = _ts(day, 7)
        await db.async_insert_cop_sample(_sample(t, r4t=None))                  # no return temp
        await db.async_insert_cop_sample(_sample(t + 300, r1t=None, lwt=None))  # no leaving temp
        await db.async_insert_cop_sample(_sample(t + 600, flow_lmin=None, power_w=None))
        src = await store.fetch_sources(conn, day, day, sample_interval_s=300.0)
        heat = src[day]["modes"]["heating"]
        assert heat["hourly"] == {"lwt_mean": 30.0, "flow_mean": 15.0, "outdoor_mean": 4.0}
        assert src[day]["temps"] == {"mean": 4.0, "min": None, "max": 7.0, "source": "running_hours"}
        smp = heat["samples"]
        assert smp["n"] == 3 and smp["r4t_mean"] == 28.0 and smp["dt_mean"] == 4.0
        assert smp["heat_kwh"] == 0.0 and smp["power_kwh"] == pytest.approx(1 / 6)
    finally:
        await _close(db)


async def test_frozen_days_skipped_and_history_without_cop(tmp_path):
    db = await _mk_db(tmp_path)
    today = _today()
    try:
        await _seed_day(db, _shift(today, -4))
        await _seed_day(db, _shift(today, -3))
        conn = db._require()
        await store.upsert_days(conn, [
            (_shift(today, -10), "heating", {"cop": None, "outdoor_run_mean": 5.0}, [], True),
            (_shift(today, -9), "all", {"cop": 4.0, "outdoor_run_mean": 5.0}, [], True),
        ])
        await rb.build_reports(db, today=today)
        # The state is lost: the next build starts at the oldest source again
        # and leaves the frozen days as they are.
        await db.async_set_model_state(rb.REPORTS_STATE_KEY, {})
        out = await rb.build_reports(db, today=today)
        assert out["first_day"] == _shift(today, -4)
        assert out["days"] == 0                       # both seeded days are frozen
        assert len(await store.fetch_days(conn, _shift(today, -4), _shift(today, -3))) == 4
    finally:
        await _close(db)
