"""Tests for model_datasheets loader (C3a)."""
from __future__ import annotations

import pytest

from custom_components.daikin_cycle_ml.engine import model_datasheets as md


def _valid_model(**over):
    base = {
        "family": "Split", "kw": 8, "lwt_min": 15, "lwt_max": 60,
        "nom_cop": 4.5,
        "points": [{"label": "A7/W35", "t_out": 7, "t_lwc": 35, "cop": 4.5}],
    }
    base.update(over)
    return base


def _payload(models, schema=1):
    return {"schema_version": schema, "models": models}


# ============ _validate_model ============
def test_validate_not_dict():
    assert md._validate_model("k", "nope") == ["k: not a dict"]


def test_validate_missing_model_keys():
    errs = md._validate_model("k", {"family": "X"})
    assert any("missing" in e for e in errs)


def test_validate_points_not_list():
    errs = md._validate_model("k", _valid_model(points="bad"))
    assert any("not a list" in e for e in errs)


def test_validate_point_not_dict():
    errs = md._validate_model("k", _valid_model(points=[1, 2]))
    assert any("not a dict" in e for e in errs)


def test_validate_point_missing_keys():
    errs = md._validate_model("k", _valid_model(points=[{"label": "X"}]))
    assert any("missing" in e for e in errs)


@pytest.mark.parametrize("field,val", [
    ("t_out", 999), ("t_lwc", 999), ("cop", 999),
    ("t_out", "x"), ("cop", None),
])
def test_validate_point_out_of_range(field, val):
    p = {"label": "X", "t_out": 7, "t_lwc": 35, "cop": 4.5, field: val}
    errs = md._validate_model("k", _valid_model(points=[p]))
    assert any("out of range" in e for e in errs)


@pytest.mark.parametrize("field,val", [
    ("t_out", -30.0), ("t_out", 40.0),
    ("t_lwc", 10.0), ("t_lwc", 70.0),
    ("cop", 0.5), ("cop", 10.0),
])
def test_validate_boundary_valid(field, val):
    p = {"label": "X", "t_out": 7, "t_lwc": 35, "cop": 4.5, field: val}
    assert md._validate_model("k", _valid_model(points=[p])) == []


@pytest.mark.parametrize("field,val", [
    ("t_out", -30.01), ("t_out", 40.01),
    ("t_lwc", 9.99), ("t_lwc", 70.01),
    ("cop", 0.49), ("cop", 10.01),
])
def test_validate_just_outside(field, val):
    p = {"label": "X", "t_out": 7, "t_lwc": 35, "cop": 4.5, field: val}
    errs = md._validate_model("k", _valid_model(points=[p]))
    assert any("out of range" in e for e in errs)


def test_validate_optional_fields_ok():
    m = _valid_model(scop_w35=4.6, scop_w55=3.2, refrigerant="R32", gwp=675)
    m["points"][0]["hc"] = 6.0
    assert md._validate_model("k", m) == []


def test_validate_empty_points_ok():
    assert md._validate_model("k", _valid_model(points=[])) == []


def test_validate_valid():
    assert md._validate_model("k", _valid_model()) == []


# ============ _parse_payload ============
def test_parse_root_not_dict():
    assert md._parse_payload("nope", "T") == {}


def test_parse_root_list():
    assert md._parse_payload([1, 2], "T") == {}


def test_parse_wrong_schema_high():
    assert md._parse_payload(_payload({}, schema=99), "T") == {}


def test_parse_wrong_schema_missing():
    assert md._parse_payload({"models": {}}, "T") == {}


def test_parse_models_not_dict():
    assert md._parse_payload({"schema_version": 1, "models": "x"}, "T") == {}


def test_parse_models_missing_key():
    assert md._parse_payload({"schema_version": 1}, "T") == {}


def test_parse_drops_invalid_keeps_valid():
    out = md._parse_payload(_payload({"ok": _valid_model(), "bad": "nope"}), "T")
    assert "ok" in out and "bad" not in out


def test_parse_empty_models_ok():
    assert md._parse_payload(_payload({}), "T") == {}


# ============ load_bundled ============
def test_load_bundled_real_15():
    b = md.load_bundled()
    assert len(b) == 15


def test_load_bundled_has_expected_keys():
    b = md.load_bundled()
    for k in ("epra08eav3", "epra12eav3", "erla11dav3", "erla14dav3", "erla16dav3"):
        assert k in b, k


def test_load_bundled_missing_file(tmp_path):
    assert md.load_bundled(tmp_path / "nope.json") == {}


def test_load_bundled_corrupt_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json")
    assert md.load_bundled(p) == {}


def test_load_bundled_directory(tmp_path):
    d = tmp_path / "dir"
    d.mkdir()
    assert md.load_bundled(d) == {}


def test_load_bundled_wrong_schema(tmp_path):
    import json
    p = tmp_path / "wrong.json"
    p.write_text(json.dumps({"schema_version": 99, "models": {}}))
    assert md.load_bundled(p) == {}


def test_load_bundled_specific_points_count():
    b = md.load_bundled()
    assert len(b["erla11dav3"]["points"]) == 9
    assert len(b["epra08eav3"]["points"]) == 6


def test_load_bundled_empty_points_preserved():
    b = md.load_bundled()
    assert b["erla12dav3"]["points"] == []
    assert b["erla04dav3"]["points"] == []


# ============ parse_user_payload ============
def test_parse_user_happy():
    out = md.parse_user_payload(_payload({"x": _valid_model()}))
    assert "x" in out


def test_parse_user_empty_ok():
    assert md.parse_user_payload(_payload({})) == {}


def test_parse_user_wrong_schema():
    assert md.parse_user_payload(_payload({}, schema=2)) == {}


def test_parse_user_drops_invalid():
    out = md.parse_user_payload(_payload({"bad": {"family": "X"}}))
    assert out == {}


# ============ merge ============
def test_merge_bundled_only():
    m = md.merge({"a": _valid_model()}, {})
    assert m["a"]["source"] == "bundled"


def test_merge_user_overrides():
    m = md.merge({"a": _valid_model()}, {"a": _valid_model(nom_cop=5.0)})
    assert m["a"]["source"] == "user"
    assert m["a"]["nom_cop"] == 5.0


def test_merge_user_only_new_key():
    m = md.merge({}, {"x": _valid_model()})
    assert m["x"]["source"] == "user"


def test_merge_both_empty():
    assert md.merge({}, {}) == {}


def test_merge_no_mutation_of_inputs():
    b = {"a": _valid_model()}
    u = {"a": _valid_model(nom_cop=5.0)}
    md.merge(b, u)
    assert "source" not in b["a"]
    assert "source" not in u["a"]


# ============ get_datasheet ============
def test_get_datasheet_missing_key():
    assert md.get_datasheet({}, "x") is None


def test_get_datasheet_empty_points():
    assert md.get_datasheet({"x": {"points": [], "source": "bundled"}}, "x") is None


def test_get_datasheet_no_points_field():
    assert md.get_datasheet({"x": {"source": "bundled"}}, "x") is None


def test_get_datasheet_valid():
    d = md.get_datasheet({"x": _valid_model()}, "x")
    assert d is not None
    assert d["nom_cop"] == 4.5


def test_get_datasheet_source_preserved():
    m = md.merge({"x": _valid_model()}, {})
    assert md.get_datasheet(m, "x")["source"] == "bundled"


# ============ KNOWN_SCHEMA_VERSION + constants ============
def test_known_schema_version():
    assert md.KNOWN_SCHEMA_VERSION == 1


def test_bundled_path_exists():
    assert md._BUNDLED_PATH.exists()


# ============ round-trip integration ============
def test_roundtrip_bundled_load_merge_get():
    b = md.load_bundled()
    m = md.merge(b, {})
    d = md.get_datasheet(m, "erla14dav3")
    assert d is not None
    assert d["family"] == "Split"
    assert d["kw"] == 14
    assert len(d["points"]) == 9


def test_roundtrip_user_overrides_bundled_empty_model():
    b = md.load_bundled()
    u = md.parse_user_payload(_payload({
        "erla12dav3": _valid_model(family="Split", kw=12, nom_cop=4.85),
    }))
    m = md.merge(b, u)
    assert md.get_datasheet(m, "erla12dav3") is not None
    # bundled others intact
    assert md.get_datasheet(m, "erla11dav3")["source"] == "bundled"


# ============ load_defaults ============
def test_load_defaults_real():
    d = md.load_defaults()
    assert d["defrost_below_c"] == 5
    assert d["off_above_c"] == 20
    assert d["outdoor_min_c"] == -25
    assert d["outdoor_max_c"] == 35
    assert d["buh_above_offset_c"] == -5


def test_load_defaults_missing(tmp_path):
    assert md.load_defaults(tmp_path / "nope.json") == {}


def test_load_defaults_corrupt(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{broken")
    assert md.load_defaults(p) == {}


def test_load_defaults_not_dict(tmp_path):
    p = tmp_path / "list.json"
    p.write_text('["x"]')
    assert md.load_defaults(p) == {}


def test_load_defaults_no_defaults_key(tmp_path):
    p = tmp_path / "x.json"
    p.write_text('{"schema_version": 1, "models": {}}')
    assert md.load_defaults(p) == {}


def test_load_defaults_not_dict_value(tmp_path):
    p = tmp_path / "x.json"
    p.write_text('{"defaults": "nope"}')
    assert md.load_defaults(p) == {}
