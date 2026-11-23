"""Setup wizard texts seen in a real Home Assistant (README screenshots).

Walking the wizard in a live Home Assistant showed:
- the family field pre-filled with the raw key "basisprofiel" (the field
  accepts typed codes, so Home Assistant shows the value, not its label);
- three fields labelled with their raw keys (short_cycling_window_min,
  short_cycling_min_cycles, buh_penalty_legionella_waived);
- "12 required attributes" (11 since #435) and a Dutch word in English;
- the confirm step, the entry title and the device showing "erga06eav3".
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.const import DOMAIN, MODEL_BASISPROFIEL, model_display
from tests.test_435_model_catalog import _source

TR = Path(__file__).resolve().parent.parent / "custom_components/daikin_cycle_ml"
FILES = ["strings.json", "translations/en.json", "translations/nl.json", "translations/fr.json"]
FIELDS = {"pendulum": ["short_cycling_window_min", "short_cycling_min_cycles"],
          "quality": ["buh_penalty_legionella_waived"]}


def test_model_display():
    assert model_display("erga06eav3") == "Altherma 3 R - ERGA06EAV3 (Split)"
    assert model_display(MODEL_BASISPROFIEL) == "Basic profile (safe defaults)"
    assert model_display("not_a_model") == "not_a_model"


@pytest.mark.parametrize("name", FILES)
def test_every_wizard_field_has_a_label_and_no_stale_text(name):
    s = json.loads((TR / name).read_text(encoding="utf-8"))
    for step, fields in FIELDS.items():
        st = s["config"]["step"][step]
        for f in fields:
            assert st["data"][f] and f not in st["data"][f], (name, step, f)
            assert st["data_description"][f], (name, step, f)
    adv = s["options"]["step"]["advanced"]
    assert adv["data"]["dhw_present"] != "dhw_present" and adv["data_description"]["dhw_present"], name
    text = json.dumps(s["config"]["step"], ensure_ascii=False)
    assert " 12 " not in text and "(pendelen)" not in text


async def test_empty_family_means_basic_profile_and_names_are_readable(hass):
    _source(hass)
    flow = hass.config_entries.flow
    r = await flow.async_init(DOMAIN, context={"source": "user"})
    fam = next(k for k in r["data_schema"].schema if str(k) == "family")
    assert not callable(fam.default)                    # no raw "basisprofiel" pre-filled
    r = await flow.async_configure(r["flow_id"], {"source_type": "monolithic"})
    assert r["step_id"] == "model"
    assert flow._progress[r["flow_id"]]._data.get("model", MODEL_BASISPROFIEL) == MODEL_BASISPROFIEL
    flow.async_abort(r["flow_id"])


@pytest.mark.parametrize("name", FILES)
def test_attribute_mode_choices_and_first_screen_are_translated(name):
    s = json.loads((TR / name).read_text(encoding="utf-8"))
    opts = s["selector"]["attribute_mode"]["options"]
    assert set(opts) == {"auto", "manual"} and all(opts.values())
    if name.endswith("nl.json"):
        desc = s["config"]["step"]["user"]["description"]
        assert "Detected" not in desc and "Basic profile" not in desc


def test_the_attribute_mode_selector_uses_the_translations():
    from custom_components.daikin_cycle_ml.config_flow import _ATTRIBUTE_MODE_SELECTOR
    assert _ATTRIBUTE_MODE_SELECTOR.config["translation_key"] == "attribute_mode"
