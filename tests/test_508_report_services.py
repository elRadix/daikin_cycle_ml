"""#508 period reports, read side: get_report / export_reports /
rebuild_reports, the last-month summary (sensor) and the diagnostics
section. The reports are built by the real builder from day sources."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import voluptuous as vol

from custom_components.daikin_cycle_ml import diagnostics as diag
from custom_components.daikin_cycle_ml import services_reports as sr
from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
from custom_components.daikin_cycle_ml.sensor import SENSOR_DEFS
from custom_components.daikin_cycle_ml.storage import report_builder as rb
from custom_components.daikin_cycle_ml.storage import report_query as rq
from custom_components.daikin_cycle_ml.storage.db import CycleDB
from homeassistant.exceptions import HomeAssistantError

pytestmark = pytest.mark.usefixtures("at_noon")


def _day(n: int) -> str:
    return (dt.date.today() - dt.timedelta(days=n)).isoformat()


async def _db_with_history(tmp_path, days: int = 75) -> CycleDB:
    """Heating every day (10 kWh in, 40 kWh out) at a falling outdoor temperature."""
    db = CycleDB(str(tmp_path / "r508.db"))
    await db.async_open()
    await db.async_initialize()
    for n in range(1, days + 1):
        day = _day(n)
        t_out = 2.0 + n * 0.1
        await db.async_set_model_state(f"energy_acc.{day}", {
            "day": day, "heating_el_kwh": 10.0, "heating_th_kwh": 40.0 if n > 40 else 36.0})
        await db.async_set_model_state(f"runtime_acc.{day}", {
            "day": day, "outdoor_sum": t_out * 86400, "outdoor_s": 86400.0, "outdoor_min": t_out - 3,
            "outdoor_max": t_out + 3, "source_fresh_s": 86400.0, "buh_total_s": 0.0})
    await rb.build_reports(db, today=_day(0), full=True)
    return db


def _coord(db) -> DaikinCycleMLCoordinator:
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.db = db
    c.options = {}
    c.hass = SimpleNamespace(config=SimpleNamespace(country="BE"))
    return c


def _hass(coord):
    entry = SimpleNamespace(entry_id="e1", runtime_data=coord)
    hass = MagicMock()
    hass.config_entries.async_get_entry = MagicMock(return_value=entry)
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    return hass


def _call(data):
    return SimpleNamespace(data=data)


async def _close(db):
    await db.async_close()
    await asyncio.sleep(0.05)


async def test_get_report_month_with_comparison_trend_and_days(tmp_path):
    db = await _db_with_history(tmp_path)
    try:
        conn = db._require()
        months = await rq.available_keys(conn, "month")
        assert months == sorted(months, reverse=True) and len(months) >= 3
        prev_month = months[1]
        rep = await rq.get_report(conn, period_type="month", key=prev_month, include_days=True,
                                  scheme="nl18", history=6)
        assert rep["found"] and rep["key"] == prev_month and rep["first_day"].endswith("-01")
        assert rep["reference"]["key"] == months[2] and rep["reference"]["found"]
        assert 3.6 <= rep["data"]["cop"] <= 4.0
        assert rep["by_mode"]["heating"]["el_kwh"] == rep["data"]["el_kwh"]
        assert len(rep["days"]) == rep["data"]["n_days_recorded"]
        assert rep["first_day"] <= rep["days"][0]["day"] <= rep["days"][-1]["day"] <= rep["last_day"]
        assert [h["key"] for h in rep["history"]][-1] == prev_month
        assert set(rep["trend"]) == set(rq.TREND_METRICS)
        cmp = rep["compare"]
        assert cmp["available"] and "cop" in cmp["metrics"]

        # the newest period by default; a week; heating only; nothing to compare
        newest = await rq.get_report(conn, period_type="month")
        assert newest["key"] == months[0]
        week = await rq.get_report(conn, period_type="week", mode="heating", against="none")
        assert week["found"] and "by_mode" not in week and week["reference"]["key"] is None
        assert week["compare"]["available"] is False
        last_year = await rq.get_report(conn, period_type="month", against="last_year")
        assert last_year["reference"]["found"] is False
        missing = await rq.get_report(conn, period_type="year", key="1999")
        assert missing["found"] is False and "data" not in missing
        empty = await rq.get_report(conn, period_type="season", mode="cooling")
        assert empty == {"period_type": "season", "key": None, "mode": "cooling", "scheme": "nl18",
                         "against": "previous", "available": [], "found": False}
    finally:
        await _close(db)


async def test_last_month_summary_and_sensor(tmp_path):
    db = await _db_with_history(tmp_path)
    try:
        c = _coord(db)
        assert c.degree_day_scheme == "be1515"                 # follows the HA country
        c.options = {"degree_day_scheme": "fr18"}
        assert c.degree_day_scheme == "fr18"
        c.options = {"degree_day_scheme": "nonsense"}
        c.hass = None
        assert c.degree_day_scheme == "nl18"
        await c.async_refresh_report_summary()
        s = c.last_month_report
        assert s["period"] == (dt.date.today().replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")
        assert s["cop"] is not None and s["scheme"] == "nl18"
        assert "cop_vs_previous_pct" in s and s["cop_vs_last_year_pct"] is None
        assert s["verdict_vs_last_year"] is None
        spec = next(d for d in SENSOR_DEFS if d["key"] == "last_month_report")
        assert spec["value_fn"](None, c) == s["cop"]
        assert spec["attr_fn"](None, c)["period"] == s["period"]
        assert len(json.dumps(spec["attr_fn"](None, c))) < 1024       # recorder-safe (R401)
        assert spec["value_fn"](None, SimpleNamespace()) is None
        assert await rq.last_month_summary(db._require(), "nl18", "1990-01-01") is None
    finally:
        await _close(db)


async def test_summary_never_raises():
    c = _coord(None)
    await c.async_refresh_report_summary()
    assert c.last_month_report is None
    db = MagicMock()
    db._require = MagicMock(side_effect=RuntimeError("closed"))
    c = _coord(db)
    await c.async_refresh_report_summary()
    assert c.last_month_report is None


async def test_export_reports_json_and_csv(tmp_path):
    db = await _db_with_history(tmp_path, days=20)
    try:
        conn = db._require()
        out = await rq.export(conn, table="periods", period_type="month", mode="all")
        assert out["count"] >= 1 and out["rows"][0]["period_type"] == "month"
        out = await rq.export(conn, table="periods", first_day=_day(3), last_day=_day(1))
        assert {r["period_type"] for r in out["rows"]} <= {"week", "month", "year", "season"}
        assert all(r["last_day"] >= _day(3) and r["first_day"] <= _day(1) for r in out["rows"])
        days = await rq.export(conn, table="days", mode="heating", fmt="csv")
        lines = days["content"].splitlines()
        assert days["count"] == 20 and len(lines) == 21
        assert "checks" in lines[0] and "el_kwh" in lines[0]
        all_days = await rq.export(conn, table="days", fmt="csv")
        assert "degree_days.nl18" in all_days["content"].splitlines()[0]
        assert rq._flat({"a": {"b": [1], "c": 2}, "l": [1, 2]}) == {"a.b": "[1]", "a.c": 2, "l": "1,2"}
    finally:
        await _close(db)


async def test_services_end_to_end(tmp_path):
    db = await _db_with_history(tmp_path, days=40)
    try:
        c = _coord(db)
        hass = _hass(c)
        rep = await sr._handle_get_report(hass, _call(sr.SCHEMA_GET_REPORT({"period_type": "week"})))
        assert rep["found"] and rep["scheme"] == "be1515"
        exp = await sr._handle_export_reports(hass, _call(sr.SCHEMA_EXPORT_REPORTS({"table": "days"})))
        assert exp["count"] > 0
        out = await sr._handle_rebuild_reports(hass, _call(sr.SCHEMA_REBUILD_REPORTS({"entry_id": "e1"})))
        assert out["full"] is False and out["last_final_day"] == _day(2)
        out = await sr._handle_rebuild_reports(hass, _call(sr.SCHEMA_REBUILD_REPORTS({"full": True})))
        assert out["full"] is True and out["days"] == 40
        assert c.last_month_report is not None

        c.async_build_reports = AsyncMock(return_value=None)
        with pytest.raises(HomeAssistantError):
            await sr._handle_rebuild_reports(hass, _call({}))
        c.db = None
        with pytest.raises(HomeAssistantError):
            await sr._handle_get_report(hass, _call({}))
    finally:
        await _close(db)


def test_service_schemas():
    assert sr.SCHEMA_GET_REPORT({}) == {"period_type": "month", "mode": "all", "compare": "previous",
                                        "history": 12, "include_days": False}
    for period in ("2026-W48", "2026-11", "2026", "2026/27"):
        sr.SCHEMA_GET_REPORT({"period": period})
    for bad in ({"period": "Nov"}, {"mode": "boiler"}, {"history": 0}, {"period_type": "day"}):
        with pytest.raises(vol.Invalid):
            sr.SCHEMA_GET_REPORT(bad)
    with pytest.raises(vol.Invalid):
        sr.SCHEMA_EXPORT_REPORTS({"first_day": "28-11-2026"})


def test_register_report_services():
    hass = MagicMock()
    sr.async_register_report_services(hass)
    names = [c.args[1] for c in hass.services.async_register.call_args_list]
    assert names == list(sr.REPORT_SERVICES)


async def test_diagnostics_section(tmp_path):
    db = await _db_with_history(tmp_path, days=10)
    try:
        c = _coord(db)
        out = await diag._reports_summary(c)
        assert out["counts"]["daily_stats"] == 20 and out["state"]["days"] == 10
        assert out["degree_day_scheme"] == "be1515" and "backfill" in out
        c.db = SimpleNamespace(is_open=True, async_get_model_state=AsyncMock(side_effect=RuntimeError()))
        out = await diag._reports_summary(c)
        assert "counts" not in out
        c.db = None
        assert set(await diag._reports_summary(c)) == {"degree_day_scheme", "last_month"}
    finally:
        await _close(db)
