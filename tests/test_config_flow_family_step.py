"""Family wizard + selector factory tests (v1.13.2)."""
from __future__ import annotations

from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daikin_cycle_ml.config_flow import (
    _build_family_selector,
    _build_model_selector,
)
from custom_components.daikin_cycle_ml.const import (
    DOMAIN,
    MODEL_BASISPROFIEL,
    MODEL_CUSTOM,
    MODEL_ERGA08EAV3,
    MODEL_FAMILIES,
    models_in_family,
)


_VALID_STATE = {
    "R1T": 30.0, "R2T": 25.0, "R4T": 40.0, "R5T": 22.0, "R6T": 21.0,
    "R7T": 15.0, "RPS": 30, "IU_Operation_Mode": "heating",
    "LWT_setpoint": 35.0, "Flow": 10.0, "BUH_Step1": "OFF",
    "Defrost_Operation": "OFF", "3way_valve": "OFF",
}


def _fields(schema):
    return {getattr(k, "schema", k) for k in schema.schema.keys()}


async def _start(hass):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )


async def _cfg(hass, fid, payload):
    return await hass.config_entries.flow.async_configure(fid, payload)


def _flow(hass, fid):
    return hass.config_entries.flow._progress[fid]


# ---------- factory tests ----------
def test_build_family_selector_shape():
    sel = _build_family_selector()
    vals = [o["value"] for o in sel.config["options"]]
    assert len(vals) == 2 + len(MODEL_FAMILIES)
    assert MODEL_BASISPROFIEL in vals
    assert MODEL_CUSTOM in vals


def test_build_model_selector_basis():
    sel = _build_model_selector(MODEL_BASISPROFIEL)
    assert [o["value"] for o in sel.config["options"]] == [MODEL_BASISPROFIEL]


def test_build_model_selector_custom():
    sel = _build_model_selector(MODEL_CUSTOM)
    assert [o["value"] for o in sel.config["options"]] == [MODEL_CUSTOM]


def test_build_model_selector_family():
    sel = _build_model_selector("erga")
    vals = [o["value"] for o in sel.config["options"]]
    assert MODEL_ERGA08EAV3 in vals
    assert len(vals) == 4


def test_build_model_selector_unknown():
    sel = _build_model_selector("zzz")
    assert [o["value"] for o in sel.config["options"]] == [MODEL_BASISPROFIEL]


# ---------- family step ----------
async def test_init_shows_family_form(hass):
    r = await _start(hass)
    assert r["type"] == FlowResultType.FORM
    assert r["step_id"] == "user"
    fields = _fields(r["data_schema"])
    assert "family" in fields


async def test_family_step_real(hass):
    r = await _start(hass)
    r = await _cfg(hass, r["flow_id"], {"family": "erga"})
    assert r["step_id"] == "model"
    f = _flow(hass, r["flow_id"])
    assert f._selected_family == "erga"
    assert f._selected_model in models_in_family("erga")


async def test_family_step_basis(hass):
    r = await _start(hass)
    r = await _cfg(hass, r["flow_id"], {"family": MODEL_BASISPROFIEL})
    f = _flow(hass, r["flow_id"])
    assert f._selected_model == MODEL_BASISPROFIEL


async def test_family_step_custom(hass):
    r = await _start(hass)
    r = await _cfg(hass, r["flow_id"], {"family": MODEL_CUSTOM})
    f = _flow(hass, r["flow_id"])
    assert f._selected_model == MODEL_CUSTOM


async def _add_entry(hass, entry_id):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "source_sensor": "sensor.x",
            "model": MODEL_ERGA08EAV3,
            "attribute_mode": "auto",
        },
        entry_id=entry_id,
    )
    entry.add_to_hass(hass)
    return entry


async def test_family_step_mismatch_picks_first(hass):
    await _add_entry(hass, "t1")
    r = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": "t1"}
    )
    r = await _cfg(hass, r["flow_id"], {"next_step_id": "reconfigure_full"})
    r = await _cfg(hass, r["flow_id"], {"family": "epra"})
    f = _flow(hass, r["flow_id"])
    assert f._selected_family == "epra"
    assert f._selected_model == models_in_family("epra")[0]


async def test_family_step_preserves_matching(hass):
    await _add_entry(hass, "t2")
    r = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": "t2"}
    )
    r = await _cfg(hass, r["flow_id"], {"next_step_id": "reconfigure_full"})
    r = await _cfg(hass, r["flow_id"], {"family": "erga"})
    f = _flow(hass, r["flow_id"])
    assert f._selected_model == MODEL_ERGA08EAV3


# ---------- model step schema ----------
async def test_model_step_schema_real(hass):
    r = await _start(hass)
    r = await _cfg(hass, r["flow_id"], {"family": "erga"})
    fields = _fields(r["data_schema"])
    assert {"source_sensor", "model", "attribute_mode"} <= fields


async def test_model_step_schema_basis(hass):
    r = await _start(hass)
    r = await _cfg(hass, r["flow_id"], {"family": MODEL_BASISPROFIEL})
    fields = _fields(r["data_schema"])
    assert "source_sensor" in fields
    assert "model" not in fields
    assert "attribute_mode" in fields


# ---------- legacy shim ----------
async def test_legacy_no_model_fallback(hass):
    r = await _start(hass)
    r = await _cfg(hass, r["flow_id"], {"source_sensor": "sensor.nope"})
    assert r["step_id"] == "model"
    assert r["errors"] == {"source_sensor": "entity_not_found"}
    f = _flow(hass, r["flow_id"])
    assert f._selected_model == MODEL_BASISPROFIEL


async def test_legacy_with_model(hass):
    r = await _start(hass)
    r = await _cfg(
        hass, r["flow_id"],
        {"source_sensor": "sensor.nope", "model": MODEL_ERGA08EAV3},
    )
    assert r["step_id"] == "model"
    assert r["errors"] == {"source_sensor": "entity_not_found"}
    f = _flow(hass, r["flow_id"])
    assert f._selected_model == MODEL_ERGA08EAV3


async def test_legacy_empty_selected_model(hass):
    # CF-5: empty _selected_model → fallback to MODEL_BASISPROFIEL in async_step_model
    r = await _start(hass)
    r = await _cfg(hass, r["flow_id"], {"family": "erga"})
    f = _flow(hass, r["flow_id"])
    f._selected_model = ""
    r = await hass.config_entries.flow.async_configure(
        r["flow_id"], {"source_sensor": "sensor.nope"}
    )
    # CF-5 filled model from fallback, entity check fails → error form
    assert r["step_id"] == "model"
    assert r["errors"] == {"source_sensor": "entity_not_found"}


# ---------- edge cases ----------
async def test_schema_default_forced_mismatch(hass):
    # _selected_model not in _selected_family → schema falls back to fam_models[0]
    r = await _start(hass)
    r = await _cfg(hass, r["flow_id"], {"family": "erga"})
    f = _flow(hass, r["flow_id"])
    f._selected_family = "epra"
    f._selected_model = MODEL_ERGA08EAV3
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {})
    assert r["step_id"] == "model"


async def test_schema_empty_selected_model_real_family(hass):
    # not default_model → True branch when _selected_model=""
    r = await _start(hass)
    r = await _cfg(hass, r["flow_id"], {"family": "erga"})
    f = _flow(hass, r["flow_id"])
    f._selected_model = ""
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {})
    assert r["step_id"] == "model"


# ---------- reconfigure full presets ----------
async def test_reconfigure_full_presets(hass):
    await _add_entry(hass, "t3")
    r = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": "t3"}
    )
    r = await _cfg(hass, r["flow_id"], {"next_step_id": "reconfigure_full"})
    f = _flow(hass, r["flow_id"])
    assert f._selected_family == "erga"
    assert f._selected_model == MODEL_ERGA08EAV3
