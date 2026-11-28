"""#522: Altherma 3 R MT (ELVX12S23EJ6V + ERRA08EAV37) had no model.

Replay of the reporter's diagnostics (tests/fixtures/diagnostics/
epra08eav3_1_31_0_b63203fae1_*.json): the unit reports "Unit model"
ELVX12S23EJ6V and the entry was set up as EPRA08EAV3 because the catalogue
sent every EL* indoor unit to EPRA. Daikin pairs EL* units with ERRA only.

Also: a reconfigure that changes the model renamed nothing, so the entry
kept its first title.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from homeassistant.helpers.typing import UNDEFINED

from custom_components.daikin_cycle_ml.config_flow import _title_update, entry_title
from custom_components.daikin_cycle_ml.const import (
    MODEL_ALIASES,
    MODEL_CHOICES,
    MODEL_LABELS,
    SOURCE_TYPE_INDIVIDUAL,
)
from custom_components.daikin_cycle_ml.engine.model_catalog import resolve_model_text
from custom_components.daikin_cycle_ml.engine.model_profiles import MODEL_PROFILES

ROOT = Path(__file__).resolve().parent.parent
DS = json.loads((ROOT / "custom_components/daikin_cycle_ml/data/datasheets.json").read_text())["models"]
FILES = sorted((ROOT / "tests/fixtures/diagnostics").glob("epra08eav3_1_31_0_b63203fae1_*.json"))
ERRA = ("erra08eav3", "erra10eav3", "erra12eav3")


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_reporter_unit_resolves_to_erra(path):
    doc = json.loads(path.read_text())
    unit = doc["source"]["attributes"]["Unit model"]
    assert unit == "ELVX12S23EJ6V" and doc["entry"]["data"]["model"] == "epra08eav3"
    match = resolve_model_text(unit)
    assert match.kind == "ambiguous" and match.candidates == list(ERRA)
    assert "epra08eav3" not in match.candidates
    # with the outdoor code from the issue the model is exact
    assert resolve_model_text(f"{unit} + ERRA08EAV37").key == "erra08eav3"


def test_two_reporter_files():
    assert len(FILES) == 2


@pytest.mark.parametrize("key", ERRA)
def test_erra_is_a_full_model(key):
    assert key in MODEL_CHOICES and key in MODEL_PROFILES
    assert MODEL_LABELS[key].startswith("Daikin Altherma 3 R MT - ERRA")
    ds = DS[key]
    assert ds["verified"] is True and "Daikin" in ds["ref"]
    assert (ds["refrigerant"], ds["gwp"], ds["charge_kg"]) == ("R32", 675, 3.25)
    assert (ds["lwt_min"], ds["lwt_max"]) == (15, 65)
    pts = {p["label"]: (p["cop"], p["hc"]) for p in ds["points"]}
    # Daikin databook ERRA08-12EV3 section 4-1 (EN 14511, Keymark)
    a7 = pts["A7/W35"] == (4.92, 6.17) and pts["A7/W55"] == (2.94, 7.72) and len(pts) == 7
    assert pts["A2/W35"] == (4.08, 5.74) and pts["A-7/W35"] == (3.04, 7.49) and pts["A7/W45"] == (3.57, 7.73)
    assert (pts["A-2/W45"], pts["A-7/W55"]) == {
        "erra08eav3": ((2.83, 8.58), (2.05, 7.55)),
        "erra10eav3": ((2.59, 8.66), (2.11, 9.02)),
        "erra12eav3": ((2.54, 9.36), (2.11, 9.02)),
    }[key]
    assert a7 and ds["nom_cop"] == 4.92
    assert MODEL_ALIASES[key.replace("eav3", "ev3")] == key


def test_erra_max_capacity_by_size():
    assert [DS[k]["hc_max_a7"] for k in ERRA] == [7.95, 9.25, 9.97]
    assert [DS[k]["max_input_kw"] for k in ERRA] == [1.69, 2.04, 2.28]


def _entry(title, **data):
    return SimpleNamespace(title=title, data=data)


def test_reconfigure_renames_an_automatic_title():
    old = {"model": "epra08eav3", "source_sensor": "sensor.althermasensors"}
    new_title = "Daikin Cycle ML - Altherma 3 R MT - ERRA08EAV3 (Split) (sensor.althermasensors)"
    assert entry_title({**old, "model": "erra08eav3"}) == new_title
    # current form and the form before #504 (model key) are both automatic
    for title in (entry_title(old), "Daikin Cycle ML - epra08eav3 (sensor.althermasensors)"):
        assert _title_update(_entry(title, **old), {"model": "erra08eav3"}) == new_title


def test_reconfigure_keeps_a_title_the_user_gave():
    entry = _entry("Heat pump", model="epra08eav3", source_sensor="sensor.x")
    assert _title_update(entry, {"model": "erra08eav3"}) is UNDEFINED


def test_title_follows_the_source():
    old = {"model": "erra08eav3", "source_sensor": "sensor.x"}
    upd = _title_update(_entry(entry_title(old), **old), {"source_type": SOURCE_TYPE_INDIVIDUAL})
    assert upd.endswith("(v2 sensor.espaltherma_)")


# --- the unit code ESPAltherma reports fills the model field (real flow) ---

def _default(result, key):
    for k in result["data_schema"].schema:
        if str(k) == key:
            return k.default() if callable(k.default) else None
    raise KeyError(key)


async def _user_form(hass):
    from homeassistant import config_entries
    from custom_components.daikin_cycle_ml.const import DOMAIN
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})


@pytest.mark.asyncio
async def test_v2_unit_model_entity_fills_the_model_field(hass):
    # a v2 install (EPRA, ETVX indoor unit): the entity as ESPAltherma publishes it
    hass.states.async_set("sensor.espaltherma_unit_model", "ETVX12S23EJ6V",
                          {"friendly_name": "Daikin Altherma via ESPAltherma Unit model"})
    r = await _user_form(hass)
    assert _default(r, "family") == "ETVX12S23EJ6V"
    assert r["description_placeholders"]["unit_model"] == "ETVX12S23EJ6V"
    # submitted as is: the next screen offers only the three EPRA sizes
    from unittest.mock import patch
    with patch("custom_components.daikin_cycle_ml.async_setup_entry", return_value=True):
        r = await hass.config_entries.flow.async_configure(
            r["flow_id"], {"family": "ETVX12S23EJ6V", "source_type": "individual"})
    assert r["step_id"] == "individual_prefix"


@pytest.mark.asyncio
async def test_monolithic_attribute_and_other_prefix(hass):
    hass.states.async_set("sensor.althermasensors", "on", {"Unit model": "ELVX12S23EJ6V"})
    r = await _user_form(hass)
    assert _default(r, "family") == "ELVX12S23EJ6V"
    hass.states.async_remove("sensor.althermasensors")
    hass.states.async_set("sensor.wp_unit_model", "ERRA08EAV37")
    assert _default(await _user_form(hass), "family") == "ERRA08EAV37"


@pytest.mark.asyncio
async def test_unknown_or_missing_unit_model_leaves_the_field_empty(hass):
    r = await _user_form(hass)
    assert _default(r, "family") is None and r["description_placeholders"]["unit_model"] == "—"
    hass.states.async_set("sensor.espaltherma_unit_model", "unknown")
    hass.states.async_set("sensor.althermasensors", "on", {"Unit model": 12})
    assert _default(await _user_form(hass), "family") is None


def _hass(states):
    from types import SimpleNamespace as NS
    objs = {eid: NS(entity_id=eid, state=st, attributes=attrs) for eid, (st, attrs) in states.items()}
    return NS(states=NS(get=objs.get, async_all=lambda domain: [o for e, o in objs.items() if e.startswith(domain + ".")]))


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_diagnostics_model_check_flags_the_reporter_install(path):
    from custom_components.daikin_cycle_ml.engine.model_catalog import model_check
    doc = json.loads(path.read_text())
    hass = _hass({"sensor.althermasensors": ("on", doc["source"]["attributes"])})
    check = model_check(hass, doc["entry"]["data"]["model"])
    assert check == {"unit_model": "ELVX12S23EJ6V", "configured": "epra08eav3",
                     "candidates": list(ERRA), "matches": False}
    assert model_check(hass, "erra08eav3")["matches"] is True
    assert model_check(_hass({}), "erra08eav3") == {"unit_model": None}


# --- repair issue: the user is asked to correct the model ---

@pytest.mark.asyncio
async def test_repair_asks_to_correct_the_model(hass):
    from homeassistant.helpers import issue_registry as ir
    from custom_components.daikin_cycle_ml import repairs
    from custom_components.daikin_cycle_ml.const import DOMAIN
    doc = json.loads(FILES[0].read_text())
    hass.states.async_set("sensor.althermasensors", "on", doc["source"]["attributes"])
    coord = SimpleNamespace(entry=SimpleNamespace(data={"model": "epra08eav3"}))
    repairs._check_model_mismatch(hass, "e1", coord)
    issue = ir.async_get(hass).async_get_issue(DOMAIN, "model_mismatch_e1")
    assert issue and issue.translation_key == "model_mismatch"
    assert issue.translation_placeholders == {
        "unit_model": "ELVX12S23EJ6V",
        "configured": "Altherma 3 H MT - EPRA08EAV3",
        "candidates": "Altherma 3 R MT - ERRA08EAV3 (Split), Altherma 3 R MT - ERRA10EAV3 (Split), "
                      "Altherma 3 R MT - ERRA12EAV3 (Split)",
    }
    # checked once an hour: a corrected model clears it on the next check
    coord.entry.data["model"] = "erra08eav3"
    repairs._check_model_mismatch(hass, "e1", coord)
    assert ir.async_get(hass).async_get_issue(DOMAIN, "model_mismatch_e1") is not None
    coord._model_check_ts -= repairs.MODEL_CHECK_INTERVAL_S
    repairs._check_model_mismatch(hass, "e1", coord)
    assert ir.async_get(hass).async_get_issue(DOMAIN, "model_mismatch_e1") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("model, raised", [("custom", False), ("basisprofiel", True)])
async def test_repair_custom_is_left_alone_basic_profile_is_told(hass, model, raised):
    from homeassistant.helpers import issue_registry as ir
    from custom_components.daikin_cycle_ml import repairs
    from custom_components.daikin_cycle_ml.const import DOMAIN
    hass.states.async_set("sensor.espaltherma_unit_model", "ERRA08EAV37")
    repairs._check_model_mismatch(hass, "e2", SimpleNamespace(entry=SimpleNamespace(data={"model": model})))
    assert (ir.async_get(hass).async_get_issue(DOMAIN, "model_mismatch_e2") is not None) is raised


@pytest.mark.parametrize("lang", ["en", "nl", "fr"])
def test_repair_text_in_every_language(lang):
    tr = json.loads((ROOT / f"custom_components/daikin_cycle_ml/translations/{lang}.json").read_text())
    text = tr["issues"]["model_mismatch"]["description"]
    assert all(p in text for p in ("{unit_model}", "{configured}", "{candidates}"))
