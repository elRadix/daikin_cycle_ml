"""#512: the setup wizard with the P1/P2 MQTT bridge as the only source.

Real Home Assistant flow manager, the two real bridge dumps as states, no
ESPAltherma entity at all: the bridge is suggested, the map step is filled
in from the detection, the model step asks no ESPAltherma sensor, the
attribute check reads the bridge, and the entry stores the map.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from custom_components.daikin_cycle_ml import config_flow_p1p2 as p1
from custom_components.daikin_cycle_ml.const import (
    CONF_P1P2_MAP,
    CONF_P1P2_PREFIX,
    CONF_SOURCE_TYPE,
    DOMAIN,
    SOURCE_TYPE_P1P2,
)
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

FIX = Path(__file__).parent / "fixtures" / "p1p2"


def _load(hass, name: str) -> dict:
    dump = json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))["states"]
    for eid, s in dump.items():
        hass.states.async_set(eid, s["state"], {"unit_of_measurement": s["unit"]} if s.get("unit") else {})
    return dump


def _suggested(result, key):
    for k in result["data_schema"].schema:
        if str(k) == key:
            return (k.description or {}).get("suggested_value")
    raise KeyError(key)


async def _run(hass, family: str, model: str | None, edit=None):
    with patch("custom_components.daikin_cycle_ml.async_setup_entry", return_value=True):
        r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        assert r["step_id"] == "user"
        assert r["description_placeholders"]["suggestion"] == SOURCE_TYPE_P1P2
        r = await hass.config_entries.flow.async_configure(
            r["flow_id"], {"family": family, CONF_SOURCE_TYPE: SOURCE_TYPE_P1P2})
        assert r["step_id"] == "p1p2_map"
        first = r
        data = {k: _suggested(r, k) for k in p1.FORM_ROLES if _suggested(r, k)}
        if edit:
            data = edit(data)
        r = await hass.config_entries.flow.async_configure(r["flow_id"], data)
        if r.get("errors"):
            return first, r, None
        assert r["step_id"] == "model"
        assert "source_sensor" not in {str(k) for k in r["data_schema"].schema}
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"model": model} if model else {})
        assert r["step_id"] == "attributes"
        attrs = r
        for _ in range(8):
            if r["type"] != FlowResultType.FORM:
                break
            r = await hass.config_entries.flow.async_configure(r["flow_id"], {})
        assert r["type"] == FlowResultType.CREATE_ENTRY, r
        return first, attrs, r


@pytest.mark.asyncio
async def test_monobloc_wizard_without_espaltherma(hass) -> None:
    _load(hass, "epra12eav3_bridge0")
    first, attrs, done = await _run(hass, "epra", "epra12eav3")
    ph = first["description_placeholders"]
    assert ph["prefix"] == "bridge0_" and int(ph["found"]) >= 30
    assert "✓ `sensor.bridge0_mode_compressor_rpm`: 41.0 Hz" in ph["preview"]
    assert "sensor.bridge0_sensors_temperature_outside_unit" in ph["preview"]
    assert attrs["description_placeholders"]["missing_list"] == "—"
    data = done["data"]
    assert data[CONF_SOURCE_TYPE] == SOURCE_TYPE_P1P2 and data[CONF_P1P2_PREFIX] == "bridge0_"
    m = data[CONF_P1P2_MAP]
    assert m["compressor_hz"] == "sensor.bridge0_mode_compressor_rpm"
    assert m["energy_produced_total"] == "sensor.bridge0_meters_energy_produced_compressor_total"  # kept, not asked
    assert "P1/P2 bridge0_" in done["title"]


@pytest.mark.asyncio
async def test_hybrid_wizard_with_three_prefixes(hass) -> None:
    _load(hass, "evlq08cv3_hybrid_hc")
    first, attrs, done = await _run(hass, "evlq", "evlq08cv3")
    assert "⚠ `sensor.hc_dhw_temperature_r5t_dhw_tank`" in first["description_placeholders"]["preview"]
    assert attrs["description_placeholders"]["hybrid_hint"] == ""      # boiler flag found
    m = done["data"][CONF_P1P2_MAP]
    assert m["compressor_hz"] == "sensor.wamtepomp_mode_compressor_rpm"
    assert m["gasboiler_active"] == "binary_sensor.hc_mode_gasboiler_active"


@pytest.mark.asyncio
async def test_wizard_refuses_r1t_as_outdoor_and_missing_roles(hass) -> None:
    _load(hass, "evlq08cv3_hybrid_hc")

    def wrong(d):
        d = dict(d, outdoor="sensor.hc_sensors_temperature_r1t_hp2gas_water")
        d.pop("flow")
        d["pump"] = "binary_sensor.hc_gone"
        return d
    _, r, _ = await _run(hass, "evlq", "evlq08cv3", edit=wrong)
    assert r["step_id"] == "p1p2_map"
    assert r["errors"] == {"outdoor": "p1p2_r1t_is_water", "flow": "p1p2_role_required",
                           "pump": "entity_not_found"}
    assert _suggested(r, "flow") is None and _suggested(r, "defrost")      # what was typed stays


@pytest.mark.asyncio
async def test_no_bridge_no_suggestion(hass) -> None:
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert r["description_placeholders"]["suggestion"] == "auto"
    assert r["description_placeholders"]["p1p2_count"] == "0"
