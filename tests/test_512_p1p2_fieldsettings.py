"""#512 PR3: hybrid boiler and the installer's field settings from the bridge.

On the EVLQ08CV3 hybrid dump: no Daikin tank (R5T -40.7 °C, E-06 off), so
the 3-way valve on the bus is not a hot-water signal; the boiler flag
splits into heat / hot water by the valve; C-02 (external backup) makes a
non-hybrid unit bivalent (#288); 239 field settings are read.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daikin_cycle_ml import async_remove_entry, async_setup_entry, async_unload_entry
from custom_components.daikin_cycle_ml import sensor as sensor_mod
from custom_components.daikin_cycle_ml.const import (
    ATTR_3WAY_VALVE,
    ATTR_BIVALENT_OPERATION,
    ATTR_BOILER_DHW_DEMAND,
    ATTR_BOILER_OPERATION_DEMAND,
    CONF_SOURCE_TYPE,
    DOMAIN,
    SOURCE_TYPE_P1P2,
)
from custom_components.daikin_cycle_ml.engine import p1p2
from homeassistant.config_entries import ConfigEntryState

FIX = Path(__file__).parent / "fixtures" / "p1p2"


def _dump(name):
    return {k: v["state"] for k, v in json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))["states"].items()}


HYB, EPRA = _dump("evlq08cv3_hybrid_hc"), _dump("epra12eav3_bridge0")


def _res(states, **override):
    st = {**states, **override}
    return p1p2.resolve(p1p2.detect(st).mapping, st.get)


def test_hybrid_without_tank_drops_the_valve():
    r = _res(HYB)
    assert ATTR_3WAY_VALVE not in r.attrs and r.rejected["threeway_valve"] == "no hot-water tank"
    # E-06 alone (tank sensor not mapped) is enough
    st = {k: v for k, v in HYB.items() if "r5t" not in k}
    assert ATTR_3WAY_VALVE not in _res(st).attrs
    # the monobloc has a tank: the valve stays
    assert _res(EPRA).attrs[ATTR_3WAY_VALVE] == "OFF"


def test_boiler_heat_or_hot_water_and_bivalent():
    on = {"binary_sensor.bridge0_mode_gasboiler_active": "on"}
    r = _res(EPRA, **on)
    assert r.attrs[ATTR_BOILER_OPERATION_DEMAND] == "ON" and r.attrs[ATTR_BOILER_DHW_DEMAND] == "OFF"
    assert ATTR_BIVALENT_OPERATION not in r.attrs                     # no C-02 read: not bivalent
    r = _res(EPRA, **on, **{"binary_sensor.bridge0_dhw_valve_dhw_tank": "on"})
    assert r.attrs[ATTR_BOILER_OPERATION_DEMAND] == "OFF" and r.attrs[ATTR_BOILER_DHW_DEMAND] == "ON"
    r = _res(EPRA, **on, **{"sensor.bridge0_fieldsettings_c_02_external_backup": "1"})
    assert r.attrs[ATTR_BIVALENT_OPERATION] == "ON"
    assert ATTR_BIVALENT_OPERATION not in _res(HYB).attrs           # hybrid: C-02 = 0


def test_field_settings_of_the_hybrid():
    fs = p1p2.field_settings(HYB)
    assert len(fs) == 239
    assert fs["9-09"] == {"name": "delta_t", "value": 5.0}
    assert fs["E-06"]["value"] == "OFF" and fs["1-02"]["value"] == 33.0
    s = p1p2.field_summary(fs)
    assert s["target_dt"] == 5.0 and s["curve_heating_low_outdoor"] == -10.0
    assert s["curve_heating_high_outdoor_lwt"] == 25.0 and s["dhw_tank_installed"] == "OFF"
    assert s["external_backup"] == 0.0
    # text values (select entities) stay text; another bridge is not read
    fs = p1p2.field_settings({"select.hc_fieldsettings_7_02_number_of_zones": "1 LWT zone",
                              "sensor.bridge1_fieldsettings_9_09_delta_t": "8"}, "hc_")
    assert fs == {"7-02": {"name": "number_of_zones", "value": "1 LWT zone"}}
    # the monobloc's bridge has not read them yet (counters off): nothing
    assert p1p2.field_settings(EPRA) == {}


@pytest.mark.asyncio
async def test_hybrid_entry_no_tank_and_installer_settings(hass) -> None:
    raw = json.loads((FIX / "evlq08cv3_hybrid_hc.json").read_text(encoding="utf-8"))["states"]
    for eid, s in raw.items():
        hass.states.async_set(eid, s["state"])
    entry = MockConfigEntry(domain=DOMAIN, entry_id="p1p2_fs", version=1, options={},
                            data={"model": "evlq08cv3", CONF_SOURCE_TYPE: SOURCE_TYPE_P1P2})
    entry.add_to_hass(hass)
    object.__setattr__(entry, "state", ConfigEntryState.SETUP_IN_PROGRESS)
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    try:
        await async_setup_entry(hass, entry)
        coord = entry.runtime_data
        snap = await coord._async_update_data()
        assert coord.dhw_present is False                         # the Intergas makes hot water
        res = coord._source_resolution
        assert res["field_settings_read"] == 239 and res["field_settings"]["target_dt"] == 5.0
        assert coord.installer_settings["dhw_tank_installed"] == "OFF"
        attrs = sensor_mod._attrs_hp_specs(snap, coord)
        assert attrs["installer_target_dt_k"] == 5.0 and attrs["installer_settings"]["lwt_heating_max"] == 45.0
    finally:
        for fn in (async_unload_entry, async_remove_entry):
            try:
                await fn(hass, entry)
            except Exception:
                pass


def test_installer_settings_only_for_the_bridge():
    c = SimpleNamespace(source_type="monolithic", _p1p2_fields={"9-09": {"name": "delta_t", "value": 5.0}})
    from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
    assert DaikinCycleMLCoordinator.installer_settings.fget(c) == {}
