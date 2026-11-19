"""#435: model codes users know (indoor unit, kit, outdoor variants).

The #435 reporter owns EHBX08EF6V (indoor) + ERGA06EAV3 (outdoor) and
set up the basic profile because the wizard asked for the outdoor family
only. The family field now accepts any code; an indoor size that pairs
with several outdoor units narrows the model dropdown to those.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.const import (
    DOMAIN,
    MODEL_CHOICES,
    REQUIRED_ATTRIBUTES,
    SOURCE_SENSOR_ENTITY,
)
from custom_components.daikin_cycle_ml.engine.model_catalog import (
    FLAGGED_NON_CATALOGUE,
    INDOOR_HINT_BY_FAMILY,
    indoor_units_for,
    resolve_model_text,
)

ROOT = Path(__file__).resolve().parent.parent
DS = json.loads(
    (ROOT / "custom_components/daikin_cycle_ml/data/datasheets.json").read_text()
)["models"]


def test_flagged_set_matches_datasheets():
    flagged = {k for k, v in DS.items() if v.get("verified") is False}
    assert flagged == set(FLAGGED_NON_CATALOGUE)


@pytest.mark.parametrize(
    "text,kind,key,candidates",
    [
        # the #435 unit: indoor 08 pairs with two outdoor sizes
        ("EHBX08EF6V", "ambiguous", None, ["erga06eav3", "erga08eav3"]),
        ("ehbx08ef6v", "ambiguous", None, ["erga06eav3", "erga08eav3"]),
        # indoor + outdoor: the outdoor code decides
        ("EHBX08EF6V + ERGA06EAV3", "exact", "erga06eav3", ["erga06eav3"]),
        ("EHBX08EF6V / erga06eav3", "exact", "erga06eav3", ["erga06eav3"]),
        ("EHBX04EF6V", "indoor", "erga04eav3", ["erga04eav3"]),
        ("EHVX08S18EJ6V", "ambiguous", None, ["erga06eav3", "erga08eav3"]),
        ("EHSX04P30EF", "indoor", "erga04eav3", ["erga04eav3"]),
        # EPRA E 8-12 kW: flagged epra11eav3 never offered
        ("ETVX12S23EA9W", "ambiguous", None,
         ["epra08eav3", "epra10eav3", "epra12eav3"]),
        ("ELBX12EF6V", "ambiguous", None,
         ["epra08eav3", "epra10eav3", "epra12eav3"]),
        # EPRA 14-18 kW (D + E indoor series)
        ("ETVX16E6V", "ambiguous", None,
         ["epra14dav3", "epra16dav3", "epra18dav3"]),
        ("ETBH16DA6V", "ambiguous", None,
         ["epra14dav3", "epra16dav3", "epra18dav3"]),
        ("EAVX16S23DA9W", "ambiguous", None,
         ["epga11dav3", "epga14dav3", "epga16dav3"]),
        ("EBVX11S23DJ9W", "indoor", "erla11dav3", ["erla11dav3"]),
        ("EBBX16DF6V", "ambiguous", None, ["erla14dav3", "erla16dav3"]),
        # outdoor variants + monobloc sub-variants
        ("ERGA06EAV3H7", "alias", "erga06eav3", ["erga06eav3"]),
        ("EPRA14DAV37", "alias", "epra14dav3", ["epra14dav3"]),
        ("ERGA06EVH", "alias", "erga06eav3", ["erga06eav3"]),
        ("EDLA09DA3W1", "alias", "edla09d3v3", ["edla09d3v3"]),
        ("EBLA09DAV3", "alias", "ebla09da3w1", ["ebla09da3w1"]),
        ("EBLA06E2V3", "alias", "ebla06ev3", ["ebla06ev3"]),
        ("EBLQ011CAV3", "alias", "eblq11cv3", ["eblq11cv3"]),
        ("RDLQ07CAV3", "alias", "edlq07cv3", ["edlq07cv3"]),
        ("EHYHBH08AAV3", "alias", "evlq08cv3", ["evlq08cv3"]),
        ("ERGA06EAV3", "exact", "erga06eav3", ["erga06eav3"]),
    ],
)
def test_resolve(text, kind, key, candidates):
    m = resolve_model_text(text)
    assert (m.kind, m.key, m.candidates) == (kind, key, candidates)
    for c in m.candidates:
        assert c in MODEL_CHOICES
        assert c not in FLAGGED_NON_CATALOGUE


@pytest.mark.parametrize(
    "text,series",
    [
        ("EHVX08S18DJ6V", "Altherma 3 R (ERGA D)"),
        ("EHBX08CB3V", "Altherma LT (ERLQ / ERHQ)"),
        ("EHFH03S18DA3V", "Altherma 3 R (ERLA03 D)"),
        ("EBLA11DAV3", "Altherma 3 H monobloc"),
        ("EDLA04E2V3", "Altherma 3 H monobloc"),
        ("EGSAX06DA9W", "Altherma 3 GEO"),
        ("EGSQH10S18AA9W", "Altherma GEO2"),
        ("EKHWET90BAV3", "Altherma DHW heat pump"),
        ("EWAA004D2V3P", "Daikin mini chiller"),
        ("EPVX10S18A", "Altherma 4 (indoor code; pick your EPSK outdoor unit)"),
    ],
)
def test_known_without_datasheet(text, series):
    m = resolve_model_text(text)
    assert m.kind == "no_datasheet"
    assert m.series == series
    assert m.key is None and m.candidates == []


@pytest.mark.parametrize("text", ["", "foo", "XYZ123", "12345678"])
def test_unknown(text):
    m = resolve_model_text(text)
    assert m.kind == "unknown"
    assert m.key is None


def test_indoor_units_for_labels():
    assert indoor_units_for("erga06eav3") == [
        "EHBH/EHBX, EHVH/EHVX/EHVZ, EHSH/EHSX 08"
    ]
    assert indoor_units_for("erga04eav3") == [
        "EHBH/EHBX, EHVH/EHVX/EHVZ, EHSH/EHSX 04"
    ]
    assert indoor_units_for("edla09d3v3") == []
    assert set(INDOOR_HINT_BY_FAMILY) <= {
        "erga", "epra", "epga", "erla", "evlq", "ekhbrd",
    }


# ---------- wizard (HA flow manager) ----------


def _source(hass):
    hass.states.async_set(
        SOURCE_SENSOR_ENTITY, "Online", dict.fromkeys(REQUIRED_ATTRIBUTES, 0)
    )


async def test_wizard_ambiguous_indoor_code_narrows_models(hass):
    _source(hass)
    flow = hass.config_entries.flow
    r = await flow.async_init(DOMAIN, context={"source": "user"})
    r = await flow.async_configure(
        r["flow_id"], {"family": "EHBX08EF6V", "source_type": "monolithic"},
    )
    assert r["step_id"] == "model"
    sel = r["data_schema"].schema
    model_key = next(k for k in sel if str(k) == "model")
    opts = [o["value"] for o in sel[model_key].config["options"]]
    assert opts == ["erga06eav3", "erga08eav3"]
    labels = [o["label"] for o in sel[model_key].config["options"]]
    assert all("indoor EHBH/EHBX" in lbl for lbl in labels)
    r = await flow.async_configure(
        r["flow_id"],
        {"source_sensor": SOURCE_SENSOR_ENTITY, "model": "erga06eav3",
         "attribute_mode": "auto"},
    )
    assert r["step_id"] == "attributes"
    flow.async_abort(r["flow_id"])


async def test_wizard_indoor_plus_outdoor_picks_outdoor(hass):
    _source(hass)
    flow = hass.config_entries.flow
    r = await flow.async_init(DOMAIN, context={"source": "user"})
    r = await flow.async_configure(
        r["flow_id"],
        {"family": "EHBX08EF6V + ERGA06EAV3", "source_type": "monolithic"},
    )
    assert r["step_id"] == "model"
    sel = r["data_schema"].schema
    model_key = next(k for k in sel if str(k) == "model")
    assert model_key.default() == "erga06eav3"
    assert [o["value"] for o in sel[model_key].config["options"]] == ["erga06eav3"]
    flow.async_abort(r["flow_id"])


@pytest.mark.parametrize(
    "text,error",
    [("EHVX08S18DJ6V", "model_no_datasheet"), ("NOTAMODEL", "model_unknown")],
)
async def test_wizard_typed_code_errors(hass, text, error):
    _source(hass)
    flow = hass.config_entries.flow
    r = await flow.async_init(DOMAIN, context={"source": "user"})
    r = await flow.async_configure(
        r["flow_id"], {"family": text, "source_type": "monolithic"},
    )
    assert r["step_id"] == "user"
    assert r["errors"] == {"family": error}
    assert r["description_placeholders"]["code"] == text
    flow.async_abort(r["flow_id"])


async def test_wizard_family_pick_unchanged(hass):
    """Picking a family from the list keeps the full family dropdown."""
    _source(hass)
    flow = hass.config_entries.flow
    r = await flow.async_init(DOMAIN, context={"source": "user"})
    r = await flow.async_configure(
        r["flow_id"], {"family": "erga", "source_type": "monolithic"},
    )
    sel = r["data_schema"].schema
    model_key = next(k for k in sel if str(k) == "model")
    opts = [o["value"] for o in sel[model_key].config["options"]]
    assert opts == ["erga04eav3", "erga06eav3", "erga08eav3", "erga08evh7"]
    flow.async_abort(r["flow_id"])


async def test_wizard_typed_family_prefix_any_case(hass):
    _source(hass)
    flow = hass.config_entries.flow
    r = await flow.async_init(DOMAIN, context={"source": "user"})
    r = await flow.async_configure(
        r["flow_id"], {"family": " ERGA ", "source_type": "monolithic"},
    )
    assert r["step_id"] == "model"
    sel = r["data_schema"].schema
    model_key = next(k for k in sel if str(k) == "model")
    assert [o["value"] for o in sel[model_key].config["options"]][0] == "erga04eav3"
    flow.async_abort(r["flow_id"])


def test_monobloc_templates_yield_known_models():
    import re as _re

    from custom_components.daikin_cycle_ml.engine import model_catalog as mc

    for pat, tmpl in mc._MONOBLOC_RULES:
        sizes = _re.search(r"\(([0-9|]+)\)", pat.pattern).group(1).split("|")
        for size in sizes:
            assert tmpl.format(size) in MODEL_CHOICES, (pat.pattern, size)


def test_indoor_rule_with_only_flagged_candidates_is_skipped(monkeypatch):
    from custom_components.daikin_cycle_ml.engine import model_catalog as mc

    monkeypatch.setattr(
        mc, "FLAGGED_NON_CATALOGUE", frozenset({"erga04eav3"})
    )
    assert mc.resolve_model_text("EHBX04EF6V").kind == "unknown"
