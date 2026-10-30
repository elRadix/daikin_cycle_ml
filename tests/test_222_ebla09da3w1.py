"""Issue #222: EBLA09DA3W1 (9 kW 3-phase R32 monobloc) datasheet tests."""
from __future__ import annotations

import json
from pathlib import Path

from custom_components.daikin_cycle_ml.const import (
    MODEL_CHOICES,
    MODEL_EBLA09DA3W1,
    MODEL_LABELS,
    family_for_model,
)
from custom_components.daikin_cycle_ml.engine.model_datasheets import (
    get_datasheet,
    load_bundled,
)
from custom_components.daikin_cycle_ml.engine.model_profiles import MODEL_PROFILES

_DATA = Path(__file__).resolve().parent.parent / (
    "custom_components/daikin_cycle_ml/data/datasheets.json"
)


def test_222_model_registered():
    assert MODEL_EBLA09DA3W1 == "ebla09da3w1"


def test_222_model_in_choices():
    assert MODEL_EBLA09DA3W1 in MODEL_CHOICES


def test_222_model_choice_name():
    name = MODEL_LABELS.get(MODEL_EBLA09DA3W1)
    assert name is not None
    assert "EBLA09DA3W1" in name
    assert "3-phase" in name or "3N" in name or "R32" in name


def test_222_family_is_ebla():
    assert family_for_model("ebla09da3w1") == "ebla"


def test_222_profile_exists():
    assert MODEL_EBLA09DA3W1 in MODEL_PROFILES
    profile = MODEL_PROFILES[MODEL_EBLA09DA3W1]
    assert profile["compressor_rps_threshold"] > 0
    assert profile["max_cycle_duration_min"] > 0


def test_222_datasheet_loads():
    bundled = load_bundled()
    assert "ebla09da3w1" in bundled
    ds = get_datasheet(bundled, "ebla09da3w1")
    assert ds is not None
    assert ds["kw"] == 9 and ds["refrigerant"] == "R32"
    assert ds["nom_cop"] == 4.91
    assert ds["lwt_min"] == 15 and ds["lwt_max"] == 60


def test_222_nominal_points():
    raw = json.loads(_DATA.read_text())
    entry = raw["models"]["ebla09da3w1"]
    pts = {p["label"]: p for p in entry["points"]}
    expected = {"A-7/W35": (-7, 35, 2.81), "A2/W35": (2, 35, 3.79),
                "A7/W35": (7, 35, 4.91), "A7/W45": (7, 45, 3.71)}
    for label, (t_out, t_lwc, cop) in expected.items():
        assert label in pts
        assert pts[label]["t_out"] == t_out
        assert pts[label]["t_lwc"] == t_lwc
        assert pts[label]["cop"] == cop


def test_222_part_load_curves_average():
    raw = json.loads(_DATA.read_text())
    plc = raw["models"]["ebla09da3w1"]["part_load_curves"]
    assert plc["climate_zone"] == "average"
    w35 = {pt["t_out"]: pt["cop"] for pt in plc["w35"]}
    assert (w35[-7], w35[2], w35[7], w35[12]) == (3.07, 4.52, 6.78, 8.75)
    w55 = {pt["t_out"]: pt["cop"] for pt in plc["w55"]}
    assert (w55[-7], w55[2], w55[7], w55[12]) == (2.09, 3.28, 4.80, 6.45)


def test_222_part_load_curves_warmer_separate():
    raw = json.loads(_DATA.read_text())
    warmer = raw["models"]["ebla09da3w1"]["part_load_curves_warmer"]
    assert warmer["climate_zone"] == "warmer"
    assert len(warmer["w35"]) == 3 and len(warmer["w55"]) == 3
    w35 = {pt["t_out"]: pt["cop"] for pt in warmer["w35"]}
    assert (w35[2], w35[7], w35[12]) == (3.36, 5.59, 7.87)


def test_222_scop_by_climate():
    raw = json.loads(_DATA.read_text())
    scop = raw["models"]["ebla09da3w1"]["scop"]
    assert scop["average"]["w35"] == 4.82 and scop["average"]["w55"] == 3.44
    assert scop["warmer"]["w35"] == 6.20 and scop["warmer"]["w55"] == 4.26


def test_222_meta_sources_recorded():
    meta = json.loads(_DATA.read_text())["_meta"]
    assert len(meta["sources"]) == 4
    for tag in ("daikin.eu", "keymark", "daikin.at", "ncm-pcdb"):
        assert any(tag in s for s in meta["sources"]), f"missing {tag}"
    assert "climate_zone_note" in meta
    assert meta["generated"].startswith("2026-10-30")


def test_222_cop_vs_datasheet_uses_a7w35():
    ds = get_datasheet(load_bundled(), "ebla09da3w1")
    a7w35 = next((pt["cop"] for pt in ds["points"] if pt["label"] == "A7/W35"), None)
    assert a7w35 == 4.91
