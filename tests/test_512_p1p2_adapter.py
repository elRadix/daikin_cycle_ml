"""#512: the P1/P2 MQTT bridge adapter on the two real entity dumps.

Fixtures (tests/fixtures/p1p2): an Altherma 3 R monobloc EPRA12EAV3 with a
tank (prefix bridge0_, template-editor dump) and the EVLQ08CV3 hybrid with
an Intergas boiler and no tank (prefixes hc_ / wamtepomp_ / warmtepomp_,
the reporter's spreadsheet of #309).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.const import (
    ATTR_3WAY_VALVE,
    ATTR_BOILER_OPERATION_DEMAND,
    ATTR_DHW_TANK_TEMP,
    ATTR_INLET_WATER_R4T,
    ATTR_INV_FREQUENCY_RPS,
    ATTR_IU_OPERATION_MODE,
    ATTR_LEAVING_WATER_BEFORE_BUH,
    ATTR_OPERATION_MODE,
    ATTR_OUTDOOR_AIR_R1T,
    REQUIRED_ATTRIBUTES,
    V2_STATS_HEAT_KEY,
    V2_STATS_KEY,
)
from custom_components.daikin_cycle_ml.engine import p1p2

FIX = Path(__file__).parent / "fixtures" / "p1p2"


def _dump(name: str) -> dict[str, dict]:
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))["states"]


EPRA, HYBRID = _dump("epra12eav3_bridge0"), _dump("evlq08cv3_hybrid_hc")


def _resolve(dump: dict, mapping: dict | None = None) -> p1p2.Resolved:
    mapping = mapping if mapping is not None else p1p2.detect(dump).mapping
    return p1p2.resolve(mapping, lambda eid: (dump.get(eid) or {}).get("state"))


def test_monobloc_maps_every_role_and_matches_the_bridge_cop():
    det = p1p2.detect(EPRA)
    assert det.prefix == "bridge0_" and det.missing_required == []
    assert set(p1p2.REQUIRED_ROLES) <= set(det.mapping)
    res = _resolve(EPRA)
    a = res.attrs
    assert a[ATTR_OUTDOOR_AIR_R1T] == -3.266                 # outdoor unit, not the external sensor
    assert a[ATTR_LEAVING_WATER_BEFORE_BUH] == 29.5           # r1t_hp2gas_water = water
    assert a[ATTR_INV_FREQUENCY_RPS] == 41.0                  # "rpm" entity in Hz
    assert a[ATTR_OPERATION_MODE] == "Heating" and a[ATTR_3WAY_VALVE] == "OFF"
    assert a[ATTR_DHW_TANK_TEMP] == 53.984
    assert a[V2_STATS_HEAT_KEY] == 7.621 and a[V2_STATS_KEY] == 1.242     # W -> kW
    # the bridge's own COP_Realtime is 6.136
    assert a[V2_STATS_HEAT_KEY] / a[V2_STATS_KEY] == pytest.approx(6.136, rel=0.01)
    assert res.missing_required == [] and res.rejected == {}
    assert ATTR_IU_OPERATION_MODE not in a                    # not on the bridge: not "missing"
    assert set(REQUIRED_ATTRIBUTES) - set(a) == {ATTR_IU_OPERATION_MODE}


def test_hybrid_with_three_prefixes():
    det = p1p2.detect(HYBRID)
    assert det.prefix == "hc_" and det.missing_required == []
    assert det.prefixes == {"hc_": 31, "warmtepomp_": 4, "wamtepomp_": 1}
    assert det.mapping["compressor_hz"] == "sensor.wamtepomp_mode_compressor_rpm"
    assert det.mapping["outdoor"] == "sensor.hc_sensors_temperature_outside_unit"
    res = _resolve(HYBRID)
    a = res.attrs
    assert a[ATTR_OUTDOOR_AIR_R1T] == 8.0 and a[ATTR_INV_FREQUENCY_RPS] == 18.0
    assert a[ATTR_BOILER_OPERATION_DEMAND] == "OFF"
    # heat 2.027 kW agrees with flow x dT (18 l/min x 1.625 K = 2.04 kW)
    flow_kw = 18.0 / 60 * 4.186 * (a["Leaving water temp. after BUH (R2T)"] - a[ATTR_INLET_WATER_R4T])
    assert a[V2_STATS_HEAT_KEY] == pytest.approx(flow_kw, rel=0.02)
    assert a[V2_STATS_HEAT_KEY] / a[V2_STATS_KEY] == pytest.approx(4.41, abs=0.01)
    # R5T/DHW guard: no tank (-40.742 °C) is left out
    assert ATTR_DHW_TANK_TEMP not in a and "no tank" in res.rejected["dhw_tank"]
    assert res.missing_required == []


def test_r1t_guard_outdoor_never_from_water():
    # without any outdoor entity the role stays empty: R1T water is never taken
    dump = {k: v for k, v in HYBRID.items() if "temperature_outside" not in k}
    det = p1p2.detect(dump)
    assert "outdoor" not in det.mapping and "outdoor" in det.missing_required
    # a wrong manual pick is refused
    res = _resolve(HYBRID, {"outdoor": "sensor.hc_sensors_temperature_r1t_hp2gas_water"})
    assert ATTR_OUTDOOR_AIR_R1T not in res.attrs and "water" in res.rejected["outdoor"]
    # the external outdoor sensor is the second choice
    dump = {k: v for k, v in HYBRID.items() if "outside_unit" not in k}
    assert p1p2.detect(dump).mapping["outdoor"] == "sensor.hc_sensors_temperature_outside"


def test_r9t_guard():
    # monobloc R9T reads 0.000: never used while R4T exists, rejected when picked
    assert p1p2.detect(EPRA).mapping["inlet_r4t"].endswith("_r4t_return_water")
    dump = {k: v for k, v in EPRA.items() if "r4t" not in k}
    det = p1p2.detect(dump)
    assert det.mapping["inlet_r4t"].endswith("_r9t_return_water")
    res = _resolve(dump, det.mapping)
    assert ATTR_INLET_WATER_R4T not in res.attrs and "not connected" in res.rejected["inlet_r4t"]
    assert ATTR_INLET_WATER_R4T in res.missing_required


def test_values_and_states():
    dump = {
        "binary_sensor.x_mode_climate_heating": {"state": "off"},
        "binary_sensor.x_mode_climate_cooling": {"state": "on"},
        "binary_sensor.x_mode_buh": {"state": "on"},
        "sensor.x_power_consumption_heatpump": {"state": "900"},
        "sensor.x_power_consumption_buh": {"state": "3000"},
        "sensor.x_power_production_heatpump": {"state": "-12"},
        "sensor.x_meters_starts_compressor": {"state": "4294967250"},   # raw bus value
        "sensor.x_sensors_flow": {"state": "unavailable"},
        "sensor.x_mode_compressor_rpm": {"state": "n/a"},
    }
    res = _resolve(dump)
    a = res.attrs
    assert a[ATTR_OPERATION_MODE] == "Cooling" and a["BUH Step1"] == "ON"
    assert a[V2_STATS_KEY] == 3.9                         # heat pump + backup heater
    assert a[V2_STATS_HEAT_KEY] == 0.0                    # negative production -> 0
    assert "compressor_starts" in res.rejected and "flow" not in res.rejected
    assert "compressor_hz" in res.rejected
    assert "Flow sensor (l/min)" in res.missing_required
    off = _resolve({"binary_sensor.x_mode_climate_heating": {"state": "off"}})
    assert off.attrs[ATTR_OPERATION_MODE] == "Off"
    assert ATTR_OPERATION_MODE not in _resolve({}).attrs
    assert _resolve({}).unmapped == list(p1p2.REQUIRED_ROLES)
    assert p1p2.resolve({"nope": "sensor.x", "flow": ""}, lambda e: "1").values == {}


def test_two_bridges_and_prefix_choice():
    two = dict(EPRA)
    for k, v in EPRA.items():
        two[k.replace("bridge0_", "bridge1_")] = v
    det = p1p2.detect(two, "bridge1_")
    assert all("bridge1_" in e for e in det.mapping.values())
    det = p1p2.detect(two, "sensor.bridge0_")
    assert all("bridge0_" in e for e in det.mapping.values())
    # a prefix that does not exist (typo) falls back to the bridge that is there
    assert p1p2.detect(EPRA, "bridge7_").mapping["flow"] == "sensor.bridge0_sensors_flow"
    # a bare entity (no prefix) and an empty list
    assert p1p2.detect(["sensor.sensors_flow"]).mapping == {"flow": "sensor.sensors_flow"}
    assert p1p2.detect([]).prefix is None


def test_expected_units_are_fixed():
    units = p1p2.expected_units()
    assert units["compressor_hz"] == "Hz" and units["flow"] == "L/min"
    assert units["heat_power"] == "W" and units["outdoor"] == "°C" and units["pump"] == ""
    assert set(units) == set(p1p2.ROLE_BY_KEY)


def test_second_bridge_missing_a_role_is_not_filled_from_the_first():
    two = dict(EPRA)
    for k, v in EPRA.items():
        if "sensors_flow" not in k:
            two[k.replace("bridge0_", "bridge1_")] = v
    det = p1p2.detect(two, "bridge1_")
    assert "flow" not in det.mapping and "flow" in det.missing_required
    assert det.mapping["outdoor"].startswith("sensor.bridge1_")


def test_entity_gone_or_not_a_string():
    res = p1p2.resolve({"flow": "sensor.gone", "outdoor": "sensor.x"},
                       lambda eid: None if eid == "sensor.gone" else True)
    assert res.values == {} and res.rejected == {"outdoor": "out of range or not a number: True"}
