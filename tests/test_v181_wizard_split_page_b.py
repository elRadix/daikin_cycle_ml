"""v1.8.1 -- attribute_mapping choice page (issue #54, commit 3)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

from custom_components.daikin_cycle_ml import config_flow as cf


def _wizard():
    flow = cf.DaikinCycleMLConfigFlow()
    h = MagicMock()
    h.states = MagicMock()
    h.states.get = MagicMock(return_value=None)
    h.config_entries = MagicMock()
    h.services = MagicMock()
    flow.hass = h
    flow._data = {}
    flow._options = {}
    flow._reconfigure_entry = None
    return flow


# ---------- attribute_mapping form ----------

def test_form_default_json():
    flow = _wizard()
    r = asyncio.run(flow.async_step_attribute_mapping())
    assert r["type"] == "form"
    assert r["step_id"] == "attribute_mapping"
    assert "mapping_mode" in r["data_schema"].schema


def test_json_routes_to_model_custom():
    flow = _wizard()
    r = asyncio.run(flow.async_step_attribute_mapping(user_input={
        "mapping_mode": "json",
    }))
    assert r["step_id"] == "model_custom"


def test_manual_routes_to_map_attributes():
    flow = _wizard()
    r = asyncio.run(flow.async_step_attribute_mapping(user_input={
        "mapping_mode": "manual",
    }))
    assert r["step_id"] == "map_attributes"


def test_unknown_mode_defaults_json():
    flow = _wizard()
    r = asyncio.run(flow.async_step_attribute_mapping(user_input={
        "mapping_mode": "garbage",
    }))
    assert r["step_id"] == "model_custom"


def test_missing_mode_defaults_json():
    flow = _wizard()
    r = asyncio.run(flow.async_step_attribute_mapping(user_input={}))
    assert r["step_id"] == "model_custom"


# ---------- model_custom_info routes through choice page now ----------

def test_info_empty_routes_to_attribute_mapping():
    flow = _wizard()
    r = asyncio.run(flow.async_step_model_custom_info(user_input={
        "custom_datasheet_json": "",
    }))
    assert r["step_id"] == "attribute_mapping"
    assert flow._data["custom_datasheet"] is None


def test_info_valid_spec_routes_to_attribute_mapping_with_spec():
    flow = _wizard()
    raw = (
        '{"family": "Altherma 3 R", "kw": 8.0, '
        '"lwt_min": 25.0, "lwt_max": 55.0, "nom_cop": 4.6}'
    )
    r = asyncio.run(flow.async_step_model_custom_info(user_input={
        "custom_datasheet_json": raw,
    }))
    assert r["step_id"] == "attribute_mapping"
    assert flow._data["custom_datasheet"]["kw"] == 8.0


def test_info_invalid_json_stays_on_info():
    flow = _wizard()
    r = asyncio.run(flow.async_step_model_custom_info(user_input={
        "custom_datasheet_json": "{not json",
    }))
    assert r["step_id"] == "model_custom_info"
    assert r["errors"]["custom_datasheet_json"] == "invalid_json"


def test_info_invalid_spec_stays_on_info():
    flow = _wizard()
    r = asyncio.run(flow.async_step_model_custom_info(user_input={
        "custom_datasheet_json": '{"family": "X"}',
    }))
    assert r["step_id"] == "model_custom_info"
    assert r["errors"]["custom_datasheet_json"] == "invalid_spec"


# ---------- backward-compat: model_custom still directly reachable ----------

def test_model_custom_method_still_works():
    flow = _wizard()
    r = asyncio.run(flow.async_step_model_custom())
    assert r["step_id"] == "model_custom"
    assert r["type"] == "form"


# ---------- i18n parity 15/15/15 ----------

def _root() -> Path:
    return Path(__file__).resolve().parent.parent / "custom_components" / "daikin_cycle_ml"


def test_i18n_parity_15_steps():
    for rel in ("strings.json", "translations/en.json", "translations/nl.json"):
        d = json.loads((_root() / rel).read_text(encoding="utf-8"))
        assert len(d["config"]["step"]) == 15, rel


def test_i18n_attribute_mapping_key_present():
    for rel in ("strings.json", "translations/en.json", "translations/nl.json"):
        d = json.loads((_root() / rel).read_text(encoding="utf-8"))
        step = d["config"]["step"].get("attribute_mapping")
        assert step is not None, rel
        assert "mapping_mode" in step.get("data", {}), rel
        assert "mapping_mode" in step.get("data_description", {}), rel
