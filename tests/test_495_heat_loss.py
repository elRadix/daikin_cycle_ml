"""#495 PR 4: heat-loss fit (UA, gains, sun), gate, peak and specific load.

Two simulated houses from the #368 / #495 simulation: A (260 W/K, 220 W
gains, underfloor) and B (158 W/K near-passive). Days carry the noise of
the real data (room +-0.3 K, 120 W on the daily mean).
"""
from __future__ import annotations

import random
from types import SimpleNamespace

import pytest

from custom_components.daikin_cycle_ml import sensor as s_mod
from custom_components.daikin_cycle_ml.engine import heat_loss as hl
from custom_components.daikin_cycle_ml.storage import building_query as bq
from custom_components.daikin_cycle_ml.storage import reports as rs
from tests.test_508_period_reports_coordinator import _coord, _mk_db


def _house(ua, gains, solar, n=40, seed=1, t_lo=-4.0, t_hi=12.0, noise=120.0):
    rnd = random.Random(seed)
    days = []
    for i in range(n):
        t_out, t_in, sun = rnd.uniform(t_lo, t_hi), 21 + rnd.uniform(-0.3, 0.3), rnd.uniform(0, 0.15)
        p = ua * (t_in - t_out) - gains - solar * sun + rnd.gauss(0, noise)
        days.append((i, {"indoor_mean": t_in, "outdoor_mean": t_out, "heat_sh_signed_kwh": p * 24 / 1000,
                         "heat_sh_s": 86000, "day_len_s": 86400, "sun_h": sun * 24, "indoor_drift": 0.1}))
    return days


@pytest.mark.parametrize(("ua", "gains"), [(260.0, 220.0), (158.0, 150.0)])
def test_fit_recovers_the_house(ua, gains):
    r = hl.fit(_house(ua, gains, 2000.0))
    assert r["published"] and r["reason"] is None and r["method"] == "flow_dt"
    assert r["ua_w_k"] == pytest.approx(ua, rel=0.03)
    assert r["gains_w"] == pytest.approx(gains, abs=60)
    assert r["solar_w"] == pytest.approx(2000.0, rel=0.2)
    assert r["sigma_w_k"] < 0.05 * ua and r["r2"] > 0.95
    assert r["t_in_mean"] == pytest.approx(21.0, abs=0.1)
    assert r["balance_point_c"] == pytest.approx(21.0 - gains / ua, abs=0.5)


def test_without_sun_spread_the_sun_term_is_left_out():
    days = [(a, {**d, "sun_h": 0.0}) for a, d in _house(260.0, 220.0, 0.0)]
    r = hl.fit(days)
    assert r["solar_w"] is None and r["ua_w_k"] == pytest.approx(260.0, rel=0.03)


@pytest.mark.parametrize(("change", "reason"), [
    ({"indoor_mean": None}, "no_temperature"),
    ({"outdoor_mean": "unavailable"}, "no_temperature"),
    ({"indoor_mean": True}, "no_temperature"),
    ({"heat_sh_s": 40000}, "low_coverage"),
    ({"heat_sh_signed_kwh": None}, "low_coverage"),
    ({"indoor_drift": 0.9}, "room_drift"),
    ({"defrost_min": 200.0}, "defrost"),
    ({"outdoor_mean": 19.5}, "no_heating_need"),
])
def test_invalid_days(change, reason):
    _, row = _house(260.0, 220.0, 0.0, n=1)[0]
    pt, why = hl.day_point({**row, **change})
    assert pt is None and why == reason


@pytest.mark.parametrize(("kw", "reason"), [
    ({"n": 2}, "too_few_days"),
    ({"n": 10}, "too_few_days"),
    ({"t_lo": 4.0, "t_hi": 8.0}, "small_outdoor_spread"),
    ({"noise": 3000.0}, "poor_fit"),
])
def test_gate(kw, reason):
    r = hl.fit(_house(260.0, 220.0, 0.0, **kw))
    assert r["published"] is False and r["reason"] == reason
    assert hl.peak_load(r) is None


def test_identical_days_cannot_be_fitted():
    _, row = _house(260.0, 220.0, 0.0, n=1)[0]
    r = hl.fit([(i, row) for i in range(5)])
    assert r["reason"] == "no_spread" and r["published"] is False


def test_peak_and_specific_load():
    r = hl.fit(_house(260.0, 220.0, 2000.0))
    peak = hl.peak_load(r)
    assert peak["kw"] == pytest.approx(7.0, abs=0.25) and peak["design_temp_c"] == -7.0
    assert peak["at_comfort_kw"] > peak["kw"]
    spec = hl.specific_load(r, peak, 210)
    assert spec["w_m2"] == pytest.approx(33.4, abs=1.5) and spec["class"] == "good"
    assert hl.specific_load(r, peak, None) is None and hl.specific_load(r, None, 210) is None
    # an uncertain fit shows W/m² but no class
    unsure = {**r, "sigma_w_k": r["ua_w_k"] * 0.3}
    assert hl.specific_load(unsure, peak, 210)["class"] is None
    assert hl.specific_load(r, {"kw": 1.0}, 210)["class"] == "passive"
    assert hl.specific_load(r, {"kw": 30.0}, 210)["class"] == "poor"


async def test_fit_on_the_day_rows(tmp_path):
    import datetime as dt
    db = await _mk_db(tmp_path)
    try:
        today = "2026-11-28"
        t = dt.date.fromisoformat(today)
        rows = [((t - dt.timedelta(days=age + 1)).isoformat(), "all", data, [], True)
                for age, data in _house(260.0, 220.0, 2000.0)]
        await rs.upsert_days(db._require(), rows)
        r = await bq.heat_loss(db._require(), today)
        assert r["published"] and r["ua_w_k"] == pytest.approx(260.0, rel=0.03)
    finally:
        await db.async_close()


def test_coordinator_and_sensors():
    c = _coord()
    c.options = {"floor_area_m2": 210, "design_temp_c": -8, "ref_indoor_c": 20}
    c._heat_loss = hl.fit(_house(260.0, 220.0, 2000.0))
    defs = {x["key"]: x for x in s_mod.SENSOR_DEFS}
    snap = SimpleNamespace()
    assert defs["building_heat_loss"]["value_fn"](snap, c) == pytest.approx(260.0, rel=0.03)
    attrs = defs["building_heat_loss"]["attr_fn"](snap, c)
    assert attrs["published"] and attrs["ua_w_k_learning"] is None and attrs["valid_days"] == 40
    peak = defs["building_peak_load"]["value_fn"](snap, c)
    assert peak == pytest.approx(0.26 * 28, abs=0.25)
    assert defs["building_peak_load"]["attr_fn"](snap, c)["design_temp_c"] == -8
    assert defs["building_specific_load"]["value_fn"](snap, c) > 0
    assert defs["building_specific_load"]["attr_fn"](snap, c)["floor_area_m2"] == 210
    # still learning: no state, the provisional value as an attribute
    c._heat_loss = hl.fit(_house(260.0, 220.0, 0.0, n=8))
    assert defs["building_heat_loss"]["value_fn"](snap, c) is None
    assert defs["building_heat_loss"]["attr_fn"](snap, c)["ua_w_k_learning"] is not None
    assert defs["building_peak_load"]["value_fn"](snap, c) is None
    c2 = _coord()
    c2.options = {}
    assert defs["building_specific_load"]["value_fn"](snap, c2) is None
