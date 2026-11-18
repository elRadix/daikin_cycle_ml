"""#392: config-flow E2E through HA's real flow manager, for EVERY model.

For each wizard model (MODEL_CHOICES minus 'custom', which has its own
JSON path covered elsewhere):
  user (family) -> model -> attributes -> cycle -> pendulum -> quality
  -> notifications -> finalize -> create_entry
The model step validates the choice against its family dropdown, so this
also proves every model is selectable.

For a representative set, the entry is then set up for real and the
hp_specs sensor must report the corrected datasheet; the options flow
round-trips and the entry unloads cleanly.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.const import (
    DOMAIN,
    MODEL_CHOICES,
    MODEL_CUSTOM,
    REQUIRED_ATTRIBUTES,
    SOURCE_SENSOR_ENTITY,
    family_for_model,
)
from homeassistant.config_entries import ConfigEntryState

ROOT = Path(__file__).resolve().parent.parent
DS = json.loads(
    (ROOT / "custom_components/daikin_cycle_ml/data/datasheets.json").read_text()
)["models"]

WIZARD_MODELS = [m for m in MODEL_CHOICES if m != MODEL_CUSTOM]

STEP_INPUT = {
    "attributes": {},
    "cycle": {"compressor_rps_threshold": 3, "fallback_power_threshold_w": 200},
    "pendulum": {
        "short_run_threshold_min": 20,
        "short_off_threshold_min": 5,
        "pendulum_cycles_per_day": 35,
        "dhw_pendulum_cycles_per_hour": 3,
    },
    "quality": {
        "good_run_threshold_min": 45,
        "good_dt_threshold_k": 5.0,
        "good_off_threshold_min": 20,
        "target_cycles_per_day": 8,
    },
    "notifications": {"persistent_enabled": True, "quiet_hours_enabled": False},
    "finalize": {},
}


def _set_source(hass):
    attrs = dict.fromkeys(REQUIRED_ATTRIBUTES, 0)
    hass.states.async_set(SOURCE_SENSOR_ENTITY, "Online", attrs)


async def _run_wizard(hass, model: str) -> dict:
    _set_source(hass)
    flow = hass.config_entries.flow
    r = await flow.async_init(DOMAIN, context={"source": "user"})
    assert r["step_id"] == "user"
    r = await flow.async_configure(
        r["flow_id"],
        {"family": family_for_model(model), "source_type": "monolithic"},
    )
    assert r["step_id"] == "model", r
    r = await flow.async_configure(
        r["flow_id"],
        {"source_sensor": SOURCE_SENSOR_ENTITY, "model": model,
         "attribute_mode": "auto"},
    )
    visited = []
    for _ in range(12):
        if r["type"] == "create_entry":
            break
        sid = r["step_id"]
        assert sid in STEP_INPUT, f"{model}: unexpected step {sid} ({r.get('errors')})"
        assert not r.get("errors"), (model, sid, r["errors"])
        visited.append(sid)
        r = await flow.async_configure(r["flow_id"], STEP_INPUT[sid])
    assert r["type"] == "create_entry", (model, visited, r)
    assert visited == list(STEP_INPUT), (model, visited)
    return r


@pytest.mark.parametrize("model", WIZARD_MODELS)
async def test_wizard_completes_for_every_model(hass, model):
    r = await _run_wizard(hass, model)
    assert r["data"]["model"] == model
    assert r["data"]["source_sensor"] == SOURCE_SENSOR_ENTITY
    assert r["options"]["pendulum_cycles_per_day"] == 35
    entry = hass.config_entries.async_get_entry(r["result"].entry_id)
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


SETUP_MODELS = [
    "epra12eav3",   # prod-1 model, corrected values
    "erga08evh7",   # new datasheet entry
    "edla16d3v3",   # was missing points
    "erga04eav3",   # A7/W55 -> A7/W45 relabel
    "epra04eav3",   # not in catalogue: must still load
    "basisprofiel",
]


@pytest.mark.parametrize("model", SETUP_MODELS)
async def test_setup_options_unload_after_wizard(hass, model):
    r = await _run_wizard(hass, model)
    entry = hass.config_entries.async_get_entry(r["result"].entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    specs = hass.states.get("sensor.daikin_cycle_ml_hp_specs")
    assert specs is not None
    if model in DS:
        assert specs.attributes.get("model") == model
        ds = DS[model]
        assert specs.attributes.get("nom_cop") == ds["nom_cop"]
        a7 = [p for p in specs.attributes.get("points") or [] if p["label"] == "A7/W35"]
        if any(p["label"] == "A7/W35" for p in ds.get("points", [])):
            assert a7 and a7[0]["cop"] == ds["nom_cop"]
        else:  # unverified, no curve (e.g. epra04eav3): loads without points
            assert a7 == []

    # options flow round-trip keeps the model and applies the change
    o = await hass.config_entries.options.async_init(entry.entry_id)
    o = await hass.config_entries.options.async_configure(
        o["flow_id"], user_input={"next_step_id": "device"}
    )
    o = await hass.config_entries.options.async_configure(
        o["flow_id"],
        {"sensors": {}, "detection": {"compressor_rps_threshold": 4}, "comfort": {}},
    )
    assert o["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.options["compressor_rps_threshold"] == 4
    assert entry.data["model"] == model

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
