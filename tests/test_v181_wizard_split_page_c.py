"""v1.8.1 -- attribute_mapping_advanced (Page C, issue #54, commit 4)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

from custom_components.daikin_cycle_ml import config_flow as cf


def _wizard():
    flow = cf.DaikinCycleMLConfigFlow()
    flow.hass = MagicMock()
    flow._data = {}
    flow._options = {}
    flow._reconfigure_entry = None
    return flow


def _root() -> Path:
    return Path(__file__).resolve().parent.parent / "custom_components" / "daikin_cycle_ml"


def test_redirect_no_input_shows_advanced_form():
    flow = _wizard()
    r = asyncio.run(flow.async_step_model_custom())
    assert r["type"] == "form"
    assert r["step_id"] == "attribute_mapping_advanced"


def test_redirect_valid_json_routes_to_attributes():
    flow = _wizard()
    r = asyncio.run(flow.async_step_model_custom(user_input={
        "custom_attribute_map": "{\"a\": \"b\"}",
    }))
    assert r["step_id"] == "attributes"


def test_redirect_invalid_json_stays_on_advanced():
    flow = _wizard()
    r = asyncio.run(flow.async_step_model_custom(user_input={
        "custom_attribute_map": "not json",
    }))
    assert r["type"] == "form"
    assert r["step_id"] == "attribute_mapping_advanced"
    assert r["errors"]["custom_attribute_map"] == "invalid_json"


def test_advanced_direct_no_input():
    flow = _wizard()
    r = asyncio.run(flow.async_step_attribute_mapping_advanced())
    assert r["type"] == "form"
    assert r["step_id"] == "attribute_mapping_advanced"


def test_i18n_parity_16_steps():
    for rel in ("strings.json", "translations/en.json", "translations/nl.json"):
        d = json.loads((_root() / rel).read_text(encoding="utf-8"))
        assert len(d["config"]["step"]) == 16, rel


def test_i18n_attribute_mapping_advanced_key_present():
    for rel in ("strings.json", "translations/en.json", "translations/nl.json"):
        d = json.loads((_root() / rel).read_text(encoding="utf-8"))
        step = d["config"]["step"].get("attribute_mapping_advanced")
        assert step is not None, rel
        assert "custom_attribute_map" in step.get("data", {}), rel
        assert "custom_attribute_map" in step.get("data_description", {}), rel


def test_i18n_model_custom_key_still_present():
    for rel in ("strings.json", "translations/en.json", "translations/nl.json"):
        d = json.loads((_root() / rel).read_text(encoding="utf-8"))
        assert "model_custom" in d["config"]["step"], rel
