"""Tests for HT profile + HT datasheet curves (#175)."""
from __future__ import annotations

import json
from pathlib import Path

from custom_components.daikin_cycle_ml.engine.model_profiles import (
    MODEL_PROFILES,
    _BASE,
)

DATA_PATH = (
    Path(__file__).parent.parent
    / "custom_components" / "daikin_cycle_ml" / "data" / "datasheets.json"
)

HT_MODELS = [
    "ekhbrd011", "ekhbrd014", "ekhbrd016",
    "errq011", "errq014", "errq016",
]


# ---------- Profile tests ----------

def test_ht_profiles_use_ht_thresholds():
    for m in HT_MODELS:
        p = MODEL_PROFILES[m]
        assert p["good_dt_threshold_k"] == 10.0, m
        assert p["max_cycle_duration_min"] == 300, m
        assert p["defrost_interval_min"] == 45, m
        assert p["short_run_threshold_min"] == 30, m
        assert p["target_cycles_per_day"] == 5, m


def test_non_ht_profiles_unchanged():
    p = MODEL_PROFILES["epra08eav3"]
    assert p["good_dt_threshold_k"] == 5.0
    assert p["max_cycle_duration_min"] == 240
    # EBLQ is LT monoblock, must remain on _BASE
    assert MODEL_PROFILES["eblq05cv3"]["good_dt_threshold_k"] == 5.0


def test_ht_profiles_preserve_base_keys():
    for m in HT_MODELS:
        for k in _BASE:
            assert k in MODEL_PROFILES[m], f"{m} missing {k}"


# ---------- Datasheet tests ----------

def _load():
    with DATA_PATH.open() as f:
        return json.load(f)


def test_ht_datasheets_have_three_points():
    d = _load()
    for m in HT_MODELS:
        pts = d["models"][m]["points"]
        assert len(pts) == 3, m
        labels = {p["label"] for p in pts}
        assert labels == {"A7/W35", "A7/W65", "A7/W80"}, m


def test_ht_datasheets_cop_decreases_with_lwt():
    d = _load()
    for m in HT_MODELS:
        by_lwt = {p["t_lwc"]: p["cop"] for p in d["models"][m]["points"]}
        assert by_lwt[35] > by_lwt[65] > by_lwt[80], m


def test_ht_datasheets_lwt_range():
    d = _load()
    for m in HT_MODELS:
        e = d["models"][m]
        assert e["lwt_min"] == 25
        assert e["lwt_max"] == 80


def test_ht_datasheets_nom_cop_unchanged():
    d = _load()
    expected = {
        "ekhbrd011": 4.2, "ekhbrd014": 3.72, "ekhbrd016": 3.72,
        "errq011": 4.22, "errq014": 3.94, "errq016": 3.72,
    }
    for m, val in expected.items():
        assert d["models"][m]["nom_cop"] == val, m


def test_ht_datasheets_points_shape():
    d = _load()
    for m in HT_MODELS:
        for p in d["models"][m]["points"]:
            assert set(p.keys()) == {"label", "t_out", "t_lwc", "cop"}
            assert 0.0 < p["cop"] < 15.0
            assert -30 <= p["t_out"] <= 50
            assert 5 <= p["t_lwc"] <= 80
