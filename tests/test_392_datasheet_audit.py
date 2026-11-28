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
    # #522: Daikin catalogue ELVX + ERRA08-12EV3, daikin.eu ELBH + ERRA table
    "erra08eav3": (4.92, 4.79, 3.37), "erra10eav3": (4.92, 4.79, 3.38),
    "erra12eav3": (4.92, 4.82, 3.47),
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
    # #522: ERRA (Altherma 3 R MT) has no own definition; it runs the EPRA E 8-12 kW one
    (r"^erra\d+e", "EPRA E "),
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


# #473: heating capacities (kW) from the Daikin product tables, read online.
# (label -> (hc, cop)); EKHBRD COPs were already in the file and match.
CAPACITY_PINNED = {
    "edlq05cv3": {"A7/W35": (4.4, 5.0), "A7/W45": (4.03, 3.58)},
    "edlq07cv3": {"A7/W35": (7.0, 4.52), "A7/W45": (6.9, 3.42)},
    **{f"{fam}{s}cv3": {"A7/W35": a, "A7/W45": b} for fam in ("eblq", "edlq")
       for s, a, b in (("11", (11.2, 4.61), (11.0, 3.55)),
                       ("14", (14.5, 4.30), (13.6, 3.32)),
                       ("16", (16.0, 4.26), (15.2, 3.26)))},
    "ekhbrd011": {"A7/W35": (11.2, 4.2), "A7/W65": (11.3, 2.97), "A7/W80": (11.0, 2.5)},
    "ekhbrd014": {"A7/W35": (14.4, 3.72), "A7/W65": (14.5, 2.89), "A7/W80": (14.0, 2.48)},
    "ekhbrd016": {"A7/W35": (16.0, 3.72), "A7/W65": (16.0, 2.73), "A7/W80": (16.0, 2.41)},
    "epsk12aw1": {"A7/W35": (10.2, 5.5)},
    "epsk14aw1": {"A7/W35": (10.2, 5.5)},
}


@pytest.mark.parametrize("model", sorted(CAPACITY_PINNED))
def test_capacities_from_product_tables_pinned(model):
    entry = DS[model]
    got = {p["label"]: (p["hc"], p["cop"]) for p in entry["points"]}
    assert got == CAPACITY_PINNED[model]
    assert entry["verified"] is True and "daikin" in entry["ref"].lower()
    assert entry["nom_cop"] == got["A7/W35"][1]


# #473: capacities kept although not confirmed for the exact model
# (no verified flag: false means non-catalogue; the note gives the source).
UNVERIFIED_CAPACITY = {
    "epsk06aw1": {"A7/W35": 5.81}, "epsk08aw1": {"A7/W35": 7.62},
    "epsk10aw1": {"A7/W35": 8.11},
    "epga11dav3": {"A7/W35": 11.1}, "epga14dav3": {"A7/W35": 14.5},
    "epga16dav3": {"A7/W35": 16.5},
    "errq011": {"A7/W65": 11.0}, "errq014": {"A7/W65": 14.0},
    "errq016": {"A7/W65": 16.0},
}


@pytest.mark.parametrize("model", sorted(UNVERIFIED_CAPACITY))
def test_unverified_capacities_kept_and_flagged(model):
    entry = DS[model]
    got = {p["label"]: p["hc"] for p in entry["points"] if "hc" in p}
    assert got == UNVERIFIED_CAPACITY[model]
    assert "verified" not in entry and entry["note"]
    a7 = next(p for p in entry["points"] if p["label"] == "A7/W35")
    assert entry["nom_cop"] == a7["cop"] or model.startswith("epga")
