"""#495 PR 1: the building's day data (room, signed space heat, sun).

Values come from what the integration already reads: the configured room
sensor (else the unit's own reading), the source attributes and HA's sun.
"""
from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from custom_components.daikin_cycle_ml.const import (
    ATTR_3WAY_VALVE,
    ATTR_DEFROST_OPERATION,
    ATTR_FLOW_SENSOR,
    ATTR_INDOOR_AMBIENT_R1T,
    ATTR_INLET_WATER_R4T,
    ATTR_IU_OPERATION_MODE,
    ATTR_LEAVING_WATER_AFTER_BUH,
    ATTR_LEAVING_WATER_BEFORE_BUH,
    ATTR_OPERATION_MODE,
)
from custom_components.daikin_cycle_ml.engine import building_day as bd
from custom_components.daikin_cycle_ml.engine import period_reports as pr
from tests.test_c5_coordinator_methods import _bare

HEAT = {ATTR_OPERATION_MODE: "Heating", ATTR_IU_OPERATION_MODE: "Heating",
        ATTR_FLOW_SENSOR: 18.0, ATTR_LEAVING_WATER_AFTER_BUH: 30.0, ATTR_INLET_WATER_R4T: 26.0}


def test_space_heat_signed_flow_dt():
    # 18 l/min x 4 K = 5.02 kW, the integration's own flow x dT formula
    assert bd.space_heat_kw(HEAT) == pytest.approx(18.0 * 4.186 * 4.0 / 60.0, abs=0.01)
    # defrost: the loop gives heat to the outdoor unit -> negative
    defrost = {**HEAT, ATTR_DEFROST_OPERATION: "ON", ATTR_LEAVING_WATER_AFTER_BUH: 22.0}
    assert bd.space_heat_kw(defrost) < 0
    # R2T missing: R1T before the backup heater
    r1 = {k: v for k, v in HEAT.items() if k != ATTR_LEAVING_WATER_AFTER_BUH}
    assert bd.space_heat_kw({**r1, ATTR_LEAVING_WATER_BEFORE_BUH: 31.0}) == pytest.approx(6.28, abs=0.01)


@pytest.mark.parametrize("change", [
    {ATTR_3WAY_VALVE: "ON"},                                    # hot water
    {ATTR_OPERATION_MODE: "Cooling", ATTR_IU_OPERATION_MODE: "Cooling"},
    {ATTR_FLOW_SENSOR: 0.0}, {ATTR_FLOW_SENSOR: None}, {ATTR_FLOW_SENSOR: 500.0},
    {ATTR_INLET_WATER_R4T: None}, {ATTR_LEAVING_WATER_AFTER_BUH: 60.0},   # dT 34 K: bad reading
])
def test_not_space_heat(change):
    assert bd.space_heat_kw({**HEAT, **change}) is None


def test_tick_and_day_fields():
    acc = bd.new_acc()
    bd.tick(acc, HEAT, dt_s=1800, indoor=20.0, indoor_src="controller", sun_elevation=30.0)
    bd.tick(acc, HEAT, dt_s=1800, indoor=21.0, indoor_src="sensor", sun_elevation=-5.0)
    bd.tick(acc, HEAT, dt_s=1800, indoor=22.0, indoor_src="controller", sun_elevation=None, boiler=True)
    bd.tick(acc, HEAT, dt_s=0, indoor=50.0, indoor_src="sensor", sun_elevation=90.0)        # ignored
    bd.tick(acc, HEAT, dt_s=60, indoor=99.0, indoor_src="sensor", sun_elevation="x")        # bad room
    f = bd.day_fields({"building": acc})
    assert f["indoor_mean"] == 21.0 and f["indoor_drift"] == 2.0 and f["indoor_s"] == 5400
    assert f["indoor_source"] == "sensor"              # a sensor seen once wins
    p = 18.0 * 4.186 * 4.0 / 60.0
    assert f["heat_sh_signed_kwh"] == pytest.approx(p * (3600 + 60) / 3600, abs=0.01)   # boiler tick left out
    assert f["heat_sh_s"] == 3660
    assert f["sun_h"] == pytest.approx(0.5 * math.sin(math.radians(30)), abs=1e-3) and f["sun_s"] == 1800


def test_day_fields_empty_and_old_payload():
    empty = bd.day_fields({})
    assert empty["indoor_mean"] is None and empty["indoor_source"] is None
    assert empty["heat_sh_signed_kwh"] is None and empty["sun_h"] == 0.0
    bad = bd.restore({"building": {"indoor_s": "x", "indoor_src": "nonsense", "indoor_first": True}})
    assert bad["indoor_s"] == 0.0 and bad["indoor_src"] is None and bad["indoor_first"] is None


def test_all_row_carries_the_building_fields():
    acc = bd.new_acc()
    bd.tick(acc, HEAT, dt_s=3600, indoor=21.5, indoor_src="sensor", sun_elevation=None)
    row = pr.build_all_row("2026-11-28", {}, {"runtime_acc": {"building": acc}}, {}, 86400)
    assert row["indoor_mean"] == 21.5 and row["heat_sh_signed_kwh"] == pytest.approx(5.02, abs=0.01)
    agg = pr.aggregate([{"data": {"indoor_mean": 20.0}}, {"data": {"indoor_mean": 22.0}}], n_days_in_period=2)
    assert agg["indoor_mean"] == 21.0


def _hass(states):
    objs = {k: SimpleNamespace(state=v[0], attributes=v[1]) for k, v in states.items()}
    return SimpleNamespace(states=SimpleNamespace(get=objs.get))


@pytest.mark.parametrize(("entity", "states", "src", "mean"), [
    ("sensor.room", {"sensor.room": ("21.3", {})}, "sensor", 21.3),
    ("sensor.room", {"sensor.room": ("unavailable", {})}, "controller", 20.0),   # falls back
    (None, {}, "controller", 20.0),
])
def test_coordinator_reads_existing_room_and_sun(entity, states, src, mean):
    c = _bare()
    c.indoor_temp_entity = entity
    c.hass = _hass({**states, "sun.sun": ("above_horizon", {"elevation": 90.0})})
    c.data = SimpleNamespace(boiler_heat_active=False)
    c._tick_building({**HEAT, ATTR_INDOOR_AMBIENT_R1T: 20}, 3600)
    f = bd.day_fields({"building": c._building_acc})
    assert f["indoor_source"] == src and f["indoor_mean"] == mean
    assert f["sun_h"] == pytest.approx(1.0) and f["heat_sh_s"] == 3600


def test_coordinator_without_hass_and_persisted():
    c = _bare()
    c.hass = None
    c.__dict__.pop("_building_acc", None)
    c._tick_building(HEAT, 60)
    assert c._building_acc["heat_sh_s"] == 60
    payload = c._report_acc_payload()
    assert payload["building"]["heat_sh_s"] == 60
    c2 = _bare()
    c2._restore_report_acc(payload)
    assert c2._building_acc["heat_sh_s"] == 60


async def test_diagnostics_last7(tmp_path):
    import time
    from custom_components.daikin_cycle_ml.diagnostics import _building_last7
    from custom_components.daikin_cycle_ml.storage import reports as rs
    from tests.test_508_period_reports_coordinator import _mk_db
    db = await _mk_db(tmp_path)
    try:
        today = time.strftime("%Y-%m-%d")
        await rs.upsert_days(db._require(), [
            (today, "all", {"indoor_mean": 21.2, "heat_sh_signed_kwh": 80.5, "outdoor_mean": 3.3}, [], False),
            (today, "heating", {"el_kwh": 1.0}, [], False),
            ("2000-01-01", "all", {"indoor_mean": 1.0}, [], True),
        ])
        out = await _building_last7(db._require())
        assert out == [{"day": today, "outdoor_mean": 3.3, "indoor_mean": 21.2, "indoor_source": None,
                        "indoor_drift": None, "heat_sh_signed_kwh": 80.5, "heat_sh_s": None,
                        "sun_h": None, "coverage": None, "degree_days": None}]
    finally:
        await db.async_close()
