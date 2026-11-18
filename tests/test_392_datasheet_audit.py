"""#392: datasheet audit guards + ESPAltherma beta alignment.

* every wizard model has a datasheet entry;
* point labels match their t_out / t_lwc (A7/W55 held W45 data before);
* no point carries hc == cop (data-entry error seen on EPRA E A7/W55);
* verified models carry a Daikin source and nom_cop == A7/W35 COP;
* models absent from Daikin's / ESPAltherma's catalogue are flagged, not removed;
* every catalogue model maps to an ESPAltherma beta definition family.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from custom_components.daikin_cycle_ml.const import MODEL_CHOICES, MODEL_LABELS

ROOT = Path(__file__).resolve().parent.parent
DS = json.loads(
    (ROOT / "custom_components/daikin_cycle_ml/data/datasheets.json").read_text()
)["models"]
ESPA = json.loads((ROOT / "docs/MODEL_ATTRIBUTES.json").read_text())
ESPA_DEFS = ESPA["models"] if "models" in ESPA else ESPA["_meta"]["models"]

GENERIC = {"basisprofiel", "custom"}
REAL_MODELS = [m for m in MODEL_CHOICES if m not in GENERIC]
_LABEL = re.compile(r"^A(-?\d+)/W(\d+)$")

# Daikin product-table values (EN14511 A7/W35, SCOP EN14825 average climate).
PINNED = {
    "epra08eav3": (4.92, 4.79, 3.47), "epra10eav3": (4.92, 4.82, 3.48),
    "epra12eav3": (4.92, 4.82, 3.48),
    "erga04eav3": (5.10, 4.54, 3.29), "erga06eav3": (4.85, 4.52, 3.27),
    "erga08eav3": (4.60, 4.61, 3.30), "erga08evh7": (4.60, 4.61, 3.35),
    "erla11dav3": (4.83, 4.72, 3.27), "erla14dav3": (4.87, 4.68, 3.26),
    "ebla04ev3": (5.10, 4.54, 3.29), "ebla06ev3": (4.85, 4.52, 3.28),
    "ebla08ev3": (4.60, 4.61, 3.35),
    "edla09d3v3": (4.91, 4.72, 3.39), "edla11d3v3": (4.83, 4.64, 3.32),
    "edla14d3v3": (4.87, 4.62, 3.37), "edla16d3v3": (4.53, 4.62, 3.33),
    "eblq05cv3": (5.00, 4.45, 3.22), "eblq07cv3": (4.52, 4.18, 3.22),
}
NOT_IN_CATALOGUE = {
    "epra04eav3", "epra06eav3", "epra11eav3", "epra14eav3", "epra16eav3",
    "epra18eav3", "erla04dav3", "erla06dav3", "erla08dav3", "erla12dav3",
    "epga10dav3",
}

# model key prefix -> substring of the ESPAltherma beta definition file name
ESPA_FAMILY = (
    (r"^epra\d+e", "EPRA E "), (r"^epra\d+d", "EPRA D"),
    (r"^erga", "ERGA "), (r"^erla", "ERLA D "), (r"^epga", "EPGA D"),
    (r"^ebla0[468]e", "EBLA-EDLA D series 4-8kW"),
    (r"^(ebla09|edla)", "EBLA-EDLA D series 9-16kW"),
    (r"^(eblq|edlq)0[57]", "LT_EBLQ-EBLQ-CA series 5-7kW"),
    (r"^(eblq|edlq)1", "LT_EBLQ-EDLQ-CA series 11-16kW"),
    (r"^epsk", "Altherma 4(EPSK"), (r"^(ekhbrd|errq)", "HT "),
    (r"^evlq", "Altherma(Hybrid)"),
)


def test_every_wizard_model_has_datasheet():
    assert not [m for m in REAL_MODELS if m not in DS]


def test_choices_and_labels_in_sync():
    assert set(MODEL_CHOICES) == set(MODEL_LABELS)


@pytest.mark.parametrize("model", sorted(DS))
def test_point_labels_match_conditions(model):
    for p in DS[model].get("points", []):
        m = _LABEL.match(p["label"])
        assert m, (model, p["label"])
        assert (int(m.group(1)), int(m.group(2))) == (p["t_out"], p["t_lwc"]), (model, p)


@pytest.mark.parametrize("model", sorted(DS))
def test_no_hc_copied_from_cop(model):
    for p in DS[model].get("points", []):
        assert "hc" not in p or p["hc"] != p["cop"], (model, p)


@pytest.mark.parametrize("model", sorted(DS))
def test_no_duplicate_point_labels(model):
    labels = [p["label"] for p in DS[model].get("points", [])]
    assert len(labels) == len(set(labels)), (model, labels)


@pytest.mark.parametrize("model", sorted(PINNED))
def test_verified_values_pinned(model):
    entry = DS[model]
    a7 = next(p for p in entry["points"] if p["label"] == "A7/W35")
    assert entry["verified"] is True and "daikin" in entry["ref"].lower()
    assert (a7["cop"], entry["scop_w35"], entry["scop_w55"]) == PINNED[model]
    assert entry["nom_cop"] == a7["cop"]


@pytest.mark.parametrize("model", sorted(d for d in DS if DS[d].get("verified")))
def test_verified_models_have_a7w35_with_capacity(model):
    a7 = [p for p in DS[model]["points"] if p["label"] == "A7/W35"]
    assert len(a7) == 1 and a7[0].get("hc", 0) > 0


@pytest.mark.parametrize("model", sorted(NOT_IN_CATALOGUE))
def test_non_catalogue_models_flagged_not_removed(model):
    assert model in MODEL_CHOICES  # no breaking change for existing entries
    assert DS[model]["verified"] is False and "catalogue" in DS[model]["note"]


@pytest.mark.parametrize("model", sorted(set(REAL_MODELS) - NOT_IN_CATALOGUE))
def test_catalogue_model_maps_to_espaltherma_definition(model):
    pattern = next((sub for rx, sub in ESPA_FAMILY if re.match(rx, model)), None)
    assert pattern, f"{model}: no ESPAltherma family mapping"
    assert any(pattern in d for d in ESPA_DEFS), (model, pattern)


def test_model_attributes_pinned_to_beta():
    meta = ESPA["_meta"]
    assert meta["branch"] == "beta" and len(meta["commit"]) == 40
