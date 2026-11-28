"""#508 period reports in the coordinator: the whole-day outdoor and data
coverage accumulators (tick, persist, restore, day reset), the nightly
build and the one-time backfill."""
from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.daikin_cycle_ml import coordinator as coord_mod
from custom_components.daikin_cycle_ml.const import REPORTS_BACKFILL_MARKER
from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
from custom_components.daikin_cycle_ml.storage import reports as store
from custom_components.daikin_cycle_ml.storage.db import CycleDB

OUT = "Outdoor air temp.(R1T)"


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.localtime(time.time()))


def _coord(db: Any = None) -> Any:
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.db = db
    c.options = {}
    return c


async def _mk_db(tmp_path) -> CycleDB:
    db = CycleDB(str(tmp_path / "c508.db"))
    await db.async_open()
    await db.async_initialize()
    return db


def test_tick_accumulates_time_weighted_outdoor_and_coverage():
    c = _coord()
    now = 1_000_000.0
    c._last_runtime_tick_ts = now
    for i, t in enumerate((4.0, 6.0, 2.0, "unavailable", 99.0), start=1):
        c._tick_buh_and_defrost({OUT: t}, now + 30.0 * i)
    c._tick_buh_and_defrost({}, now + 180.0)              # source gone: no coverage
    assert c._source_fresh_s == 150.0
    assert c._outdoor_s == 90.0
    assert c._outdoor_sum / c._outdoor_s == pytest.approx(4.0)
    assert (c._outdoor_min, c._outdoor_max) == (2.0, 6.0)


def test_day_reset_clears_report_accumulators():
    c = _coord()
    c._outdoor_sum, c._outdoor_s, c._outdoor_min, c._outdoor_max = 10.0, 5.0, 1.0, 3.0
    c._source_fresh_s = 5.0
    c._runtime_day_key = "2000-01-01"
    c._maybe_reset_daily_accumulators(time.time())
    assert c._report_acc_payload() == {"outdoor_sum": 0.0, "outdoor_s": 0.0, "outdoor_min": None,
                                       "outdoor_max": None, "source_fresh_s": 0.0,
                                       "building": coord_mod._building_day.new_acc()}  # #495


async def test_persist_and_restore_report_accumulators(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        c = _coord(db)
        c._runtime_day_key = _today()
        c._outdoor_sum, c._outdoor_s, c._outdoor_min, c._outdoor_max = 120.0, 30.0, 3.5, 4.5
        c._source_fresh_s = 60.0
        await c._persist_runtime_acc()
        saved = await db.async_get_model_state(f"runtime_acc.{_today()}")
        assert saved["outdoor_s"] == 30.0 and saved["source_fresh_s"] == 60.0

        fresh = _coord(db)
        assert await fresh._restore_runtime_acc() is True
        assert fresh._report_acc_payload() == c._report_acc_payload()

        # Self-healing restore (DB ahead of memory) brings them back too.
        await db.async_set_model_state(f"runtime_acc.{_today()}", {**saved, "buh_step1_s": 500.0})
        healed = _coord(db)
        healed._runtime_day_key = _today()
        await healed._persist_runtime_acc()
        assert healed._outdoor_s == 30.0 and healed._outdoor_min == 3.5
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


def test_restore_old_payload_without_report_keys():
    c = _coord()
    c._restore_report_acc({"buh_step1_s": 1.0, "outdoor_min": "bad"})
    assert c._report_acc_payload() == {"outdoor_sum": 0.0, "outdoor_s": 0.0, "outdoor_min": None,
                                       "outdoor_max": None, "source_fresh_s": 0.0,
                                       "building": coord_mod._building_day.new_acc()}  # #495


@pytest.mark.parametrize(("opts", "month"), [
    ({}, 10), (None, 10), ({"season_start_month": 9}, 9),
    ({"season_start_month": 13}, 10), ({"season_start_month": "x"}, 10),
])
def test_season_start_month(opts, month):
    assert coord_mod._period_reports.season_start_month(opts) == month


async def test_build_reports_and_backfill_once(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        c = _coord(db)
        c.options = {"season_start_month": 9}
        day = time.strftime("%Y-%m-%d", time.localtime(time.time() - 5 * 86400))
        await db.async_set_model_state(f"energy_acc.{day}", {"day": day, "heating_el_kwh": 1.0,
                                                             "heating_th_kwh": 4.0})
        with patch.object(coord_mod._report_builder, "build_reports",
                          wraps=coord_mod._report_builder.build_reports) as spy:
            assert await c._maybe_backfill_reports() is True
            assert spy.call_args.kwargs["full"] is True
            assert spy.call_args.kwargs["season_start_month"] == 9
            assert spy.call_args.kwargs["sample_interval_s"] == 300.0
        marker = await db.async_get_model_state(REPORTS_BACKFILL_MARKER)
        assert marker["completed"] is True and marker["days"] == 1
        seasons = await store.fetch_periods(db._require(), "season")
        assert seasons and all(s["first_day"][5:7] == "09" for s in seasons)
        assert await c._maybe_backfill_reports() is False      # once only
    finally:
        await db.async_close()
        await asyncio.sleep(0.05)


async def test_build_reports_never_raises():
    assert await _coord()._maybe_backfill_reports() is False
    assert await _coord().async_build_reports() is None
    db = MagicMock()
    db.async_get_model_state = AsyncMock(side_effect=RuntimeError("locked"))
    assert await _coord(db)._maybe_backfill_reports() is False
    db.async_get_model_state = AsyncMock(return_value=None)
    db.async_ensure_cop_samples_table = AsyncMock(side_effect=RuntimeError("locked"))
    c = _coord(db)
    assert await c._maybe_backfill_reports() is False     # failed build: marker stays unset
    db.async_set_model_state.assert_not_called()


async def test_maintenance_callback_builds_reports():
    c = _coord(MagicMock())
    c.db.async_daily_summary = AsyncMock(return_value=[])
    c.async_run_maintenance = AsyncMock(side_effect=RuntimeError("boom"))
    c.async_build_reports = AsyncMock(return_value={"days": 1})
    await c._async_maintenance_callback(None)
    c.async_build_reports.assert_awaited_once_with()
