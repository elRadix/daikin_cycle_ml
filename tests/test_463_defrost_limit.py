"""#463: weather-aware weekly defrost limit (engine/defrost_limit).

The old alert compared the 7-day count of runs with a defrost to a fixed
30. A humid NL/BE winter week crosses that while the unit is healthy, and
a run that lasts days counts as one "defrost". The limit now follows the
running hours and the outdoor temperature per hour, and counts real
defrost events (rising edges, runtime_acc.<day>.defrost_count).
"""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    _defrost_limit_value,
)
from custom_components.daikin_cycle_ml.engine import defrost_limit as dl

BASE_H = int(time.mktime(time.strptime("2026-11-14 00:00", "%Y-%m-%d %H:%M"))) // 3600


def _day(i: int) -> str:
    return time.strftime("%Y-%m-%d", time.localtime((BASE_H + 24 * i) * 3600))


def _hours(day_i: int, temps: list[float], mode: str = "heating") -> list[dict]:
    return [{"ts_hour": BASE_H + 24 * day_i + h, "n_samples": 12, "outdoor_mean": t, "mode": mode}
            for h, t in enumerate(temps)]


def _week(run_h: float, temp: float, events: int, days: int = 7):
    rows = [{"day": _day(i), "mode": "heating", "total_duration_s": run_h * 3600, "defrost_count": 1}
            for i in range(days)]
    ev = {_day(i): {"defrost_events": events, "buh_min": 0} for i in range(days)}
    hourly = [h for i in range(days) for h in _hours(i, [temp] * 24)]
    return rows, ev, hourly


@pytest.mark.parametrize(("temp", "rate"), [
    (-10, 1.0), (-7, 1.5), (-3, 1.5), (-2, 2.0), (0, 2.0), (2.9, 2.0), (3, 1.5),
    (6.9, 1.5), (7, 0.5), (9.9, 0.5), (10, 0.1), (25, 0.1),
])
def test_rate_bands(temp: float, rate: float) -> None:
    assert dl.rate_for(temp) == rate


def test_humid_winter_week_is_normal_where_the_fixed_30_fired() -> None:
    # 0 degC, 20 h running a day, 1.5 defrosts per running hour: 210 events.
    rows, ev, hourly = _week(20, 0.0, 30)
    res = dl.compute(rows, ev, hourly, cutoff_day=_day(0))
    assert res["events_7d"] == 210
    assert res["events_7d"] > 30            # the old fixed limit fired
    assert res["limit_7d"] == 420           # 140 h x 2.0 x 1.5
    assert res["excessive"] is False
    assert res["run_h_7d"] == 140.0


def test_too_many_for_the_weather_fires() -> None:
    # 5 degC, 10 h a day, 4 defrosts per running hour (> 3/h physical max).
    rows, ev, hourly = _week(10, 5.0, 40)
    res = dl.compute(rows, ev, hourly, cutoff_day=_day(0))
    assert res["limit_7d"] == 158           # ceil(70 h x 1.5 x 1.5)
    assert res["excessive"] is True


def test_warm_days_with_defrosts_fire_below_the_limit() -> None:
    # 12 degC, 3 defrosts a day on two days: not normal, whatever the count.
    rows, ev, hourly = _week(2, 12.0, 0)
    ev[_day(0)]["defrost_events"] = 3
    ev[_day(1)]["defrost_events"] = 3
    res = dl.compute(rows, ev, hourly, cutoff_day=_day(0))
    assert res["events_7d"] == 6 < res["limit_7d"] == dl.FLOOR
    assert res["warm_days"] == 2
    assert res["excessive"] is True


def test_one_warm_day_is_not_enough() -> None:
    rows, ev, hourly = _week(2, 12.0, 0)
    ev[_day(0)]["defrost_events"] = 3
    assert dl.compute(rows, ev, hourly, cutoff_day=_day(0))["excessive"] is False


def test_mild_day_with_cold_night_uses_the_cold_hours() -> None:
    temps = [1.0] * 8 + [12.0] * 16           # day mean ~8.3 degC, cold night
    rows = [{"day": _day(0), "mode": "heating", "total_duration_s": 24 * 3600, "defrost_count": 0}]
    res = dl.compute(rows, {}, _hours(0, temps), cutoff_day=_day(0))
    day = res["per_day"][0]
    assert day["rate"] == pytest.approx((8 * 2.0 + 16 * 0.1) / 24, abs=0.01)
    assert day["rate"] > dl.rate_for(day["outdoor"])  # daily mean would be stricter


def test_cooling_runtime_and_hours_are_ignored() -> None:
    rows = [{"day": _day(0), "mode": "cooling", "total_duration_s": 10 * 3600, "defrost_count": 0},
            {"day": _day(0), "mode": "dhw", "total_duration_s": 3600, "defrost_count": 0}]
    hourly = _hours(0, [0.0]) + _hours(0, [30.0], mode="cooling")
    res = dl.compute(rows, {}, hourly, cutoff_day=_day(0))
    assert res["run_h_7d"] == 1.0
    assert res["per_day"][0]["outdoor"] == 0.0


def test_day_without_outdoor_data_is_lenient() -> None:
    rows = [{"day": _day(0), "mode": "heating", "total_duration_s": 10 * 3600, "defrost_count": 0}]
    res = dl.compute(rows, {}, [], cutoff_day=_day(0))
    assert res["per_day"][0]["rate"] == dl.RATE_UNKNOWN
    assert res["limit_7d"] == 30


def test_days_before_runtime_events_fall_back_to_cycles_with_defrost() -> None:
    rows = [{"day": _day(0), "mode": "heating", "total_duration_s": 3600, "defrost_count": 4},
            {"day": _day(0), "mode": "dhw", "total_duration_s": 0, "defrost_count": 1}]
    assert dl.compute(rows, {}, [], cutoff_day=_day(0))["events_7d"] == 5


def test_old_days_and_bad_values_are_skipped() -> None:
    old = time.strftime("%Y-%m-%d", time.localtime((BASE_H - 48) * 3600))
    rows = [{"day": old, "mode": "heating", "total_duration_s": 99 * 3600, "defrost_count": 9},
            {"day": "", "mode": "heating"},
            {"day": _day(0), "mode": "heating", "total_duration_s": "x", "defrost_count": None}]
    ev = {old: {"defrost_events": 50}, _day(0): {"defrost_events": True}}
    hourly = [{"ts_hour": BASE_H - 48, "outdoor_mean": 0.0},
              {"ts_hour": None, "outdoor_mean": 1.0},
              {"ts_hour": BASE_H, "outdoor_mean": float("nan")}]
    res = dl.compute(rows, ev, hourly, cutoff_day=_day(0))
    assert res["events_7d"] == 0
    assert res["run_h_7d"] == 0.0
    assert res["limit_7d"] == dl.FLOOR


# ---------- coordinator wiring ----------

def _coord(options=None):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = dict(options or {})
    c._defrost_7d = {}
    c._defrost_7d_sum = 0
    return c


async def test_refresh_stores_the_limit() -> None:
    rows, ev, hourly = _week(20, 0.0, 30)
    c = _coord()
    db = SimpleNamespace(async_query_cop_hourly=AsyncMock(return_value=hourly))
    await c._refresh_defrost_limit(db, rows, ev)
    assert c._defrost_7d_sum == c._defrost_7d["events_7d"]
    assert c._defrost_7d["limit_7d"] >= dl.FLOOR


async def test_refresh_keeps_previous_result_on_db_error() -> None:
    c = _coord()
    c._defrost_7d = {"limit_7d": 77}
    db = SimpleNamespace(async_query_cop_hourly=AsyncMock(side_effect=OSError("db")))
    await c._refresh_defrost_limit(db, [], {})
    assert c._defrost_7d == {"limit_7d": 77}


def test_limit_value_option_wins_then_dynamic_then_default() -> None:
    c = _coord()
    assert _defrost_limit_value(c, {}) == 30
    c._defrost_7d = {"limit_7d": 420}
    assert _defrost_limit_value(c, {}) == 420
    assert _defrost_limit_value(c, {"defrost_7d_count_threshold": 50}) == 50


def _states(c):
    snap = MagicMock()
    snap.anomaly = None
    return c._alert_binary_states(snap)


@pytest.mark.parametrize(("options", "dyn", "count", "expected"), [
    ({}, {"excessive": False, "limit_7d": 420}, 210, False),   # dynamic: normal week
    ({}, {"excessive": True, "limit_7d": 10}, 6, True),        # dynamic: warm days
    ({}, {}, 31, True),                                         # no result yet: default 30
    ({"defrost_7d_count_threshold": 300}, {"excessive": True}, 210, False),  # option wins
])
def test_binary_state_uses_dynamic_limit(options, dyn, count, expected) -> None:
    from tests.test_v1225_dhw_tail_alert import _mock_coord, _mock_store

    c = _mock_coord(_mock_store(None))
    c.options.update(options)
    c._defrost_7d = dyn
    c._defrost_7d_sum = count
    assert _states(c)["defrost_excessive"] is expected
