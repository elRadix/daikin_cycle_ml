"""#512: the P1/P2 MQTT bridge as the source of a real config entry.

The two real dumps (tests/fixtures/p1p2) are loaded as Home Assistant
states, the entry is set up with source type ``p1p2`` (no ESPAltherma at
all), and the coordinator ticks: attributes, compressor detection, COP from
the bridge's own power against its COP_Realtime, hybrid boiler fields and
diagnostics.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daikin_cycle_ml import async_remove_entry, async_setup_entry, async_unload_entry
from custom_components.daikin_cycle_ml.const import (
    CONF_P1P2_MAP,
    CONF_SOURCE_TYPE,
    DOMAIN,
    SOURCE_TYPE_P1P2,
)
from custom_components.daikin_cycle_ml.engine import p1p2
from homeassistant.config_entries import ConfigEntryState

FIX = Path(__file__).parent / "fixtures" / "p1p2"


def _load(hass, name: str) -> dict:
    dump = json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))["states"]
    for eid, s in dump.items():
        attrs = {"unit_of_measurement": s["unit"]} if s.get("unit") else {}
        hass.states.async_set(eid, s["state"], attrs)
    return dump


def _entry(hass, entry_id: str, model: str, data: dict | None = None):
    entry = MockConfigEntry(domain=DOMAIN, entry_id=entry_id, version=1, options={},
                            data={"model": model, CONF_SOURCE_TYPE: SOURCE_TYPE_P1P2, **(data or {})})
    entry.add_to_hass(hass)
    object.__setattr__(entry, "state", ConfigEntryState.SETUP_IN_PROGRESS)
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    return entry


async def _teardown(hass, entry):
    for fn in (async_unload_entry, async_remove_entry):
        try:
            await fn(hass, entry)
        except Exception:
            pass


@pytest.mark.asyncio
async def test_epra12_monobloc_from_the_bridge(hass) -> None:
    dump = _load(hass, "epra12eav3_bridge0")
    entry = _entry(hass, "p1p2_epra", "epra12eav3")
    try:
        assert await async_setup_entry(hass, entry) is True
        coord = entry.runtime_data
        for _ in range(3):
            snap = await coord._async_update_data()
        assert snap.errors_total == 0
        assert snap.missing_attrs == []
        assert snap.state == "running" and snap.mode == "heating"
        assert snap.electrical_power_source == "espaltherma_v2_stats"
        assert snap.electrical_power_w == pytest.approx(1242.0)
        own = float(dump["sensor.bridge0_cop_cop_realtime"]["state"])
        assert snap.cop == pytest.approx(own, rel=0.20)                 # #512: within 20 %
        assert snap.cop == pytest.approx(7.621 / 1.242, rel=0.01)
        res = coord._source_resolution
        assert res["mode"] == "p1p2" and res["saved_map"] is False and res["read"] >= 20
        assert res["cop_bridge"] == own and res["unmapped_required"] == []
        assert snap.is_hybrid is False and snap.boiler_active is False
    finally:
        await _teardown(hass, entry)


@pytest.mark.asyncio
async def test_evlq08_hybrid_from_the_bridge(hass) -> None:
    _load(hass, "evlq08cv3_hybrid_hc")
    entry = _entry(hass, "p1p2_evlq", "evlq08cv3")
    try:
        assert await async_setup_entry(hass, entry) is True
        coord = entry.runtime_data
        for _ in range(3):
            snap = await coord._async_update_data()
        assert snap.errors_total == 0 and snap.missing_attrs == []
        assert snap.is_hybrid is True
        assert snap.boiler_active is False                      # mode_gasboiler_active off, -97 W ignored
        assert snap.state == "running" and snap.mode == "heating"
        assert snap.cop == pytest.approx(2.027 / 0.46, rel=0.01)
        assert "dhw_tank" in coord._source_resolution["rejected"]
        # the boiler starts: its flag reaches the hybrid logic
        hass.states.async_set("binary_sensor.hc_mode_gasboiler_active", "on")
        snap = await coord._async_update_data()
        assert snap.boiler_active is True
    finally:
        await _teardown(hass, entry)


@pytest.mark.asyncio
async def test_saved_map_and_bridge_offline(hass) -> None:
    dump = _load(hass, "epra12eav3_bridge0")
    mapping = p1p2.detect(dump).mapping
    mapping["outdoor"] = "sensor.bridge0_sensors_temperature_outside"   # the user picked the external sensor
    entry = _entry(hass, "p1p2_saved", "epra12eav3", {CONF_P1P2_MAP: mapping})
    try:
        await async_setup_entry(hass, entry)
        coord = entry.runtime_data
        snap = await coord._async_update_data()
        assert snap.attrs["Outdoor air temp.(R1T)"] == -3.176
        assert coord._source_resolution["saved_map"] is True
        # MQTT availability: every bridge entity becomes unavailable
        for eid in dump:
            hass.states.async_set(eid, "unavailable")
        before = snap.last_success_ts
        snap = await coord._async_update_data()
        assert snap.attrs == {} and len(snap.missing_attrs) >= 10
        assert snap.last_success_ts == before or snap.last_success_ts == 0.0
    finally:
        await _teardown(hass, entry)


@pytest.mark.asyncio
async def test_detection_is_cached_without_saved_map(hass) -> None:
    _load(hass, "epra12eav3_bridge0")
    entry = _entry(hass, "p1p2_cache", "epra12eav3")
    try:
        await async_setup_entry(hass, entry)
        coord = entry.runtime_data
        first = coord._p1p2_mapping(1000.0)
        hass.states.async_set("sensor.zzz_sensors_flow", "99")       # appears later
        assert coord._p1p2_mapping(1100.0) is first                    # within 10 min: cached
        assert coord._p1p2_mapping(1000.0 + 601.0)["flow"] == "sensor.bridge0_sensors_flow"
    finally:
        await _teardown(hass, entry)
