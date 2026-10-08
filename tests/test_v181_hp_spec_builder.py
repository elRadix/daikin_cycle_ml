"""v1.8.1 -- HP spec JSON builder on Page A (issue #54, commit 2)."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from custom_components.daikin_cycle_ml import config_flow as cf
from custom_components.daikin_cycle_ml.engine import model_datasheets as md


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


def _spec(**kw):
    base = {
        "family": "Altherma 3 R",
        "kw": 8.0,
        "lwt_min": 25.0,
        "lwt_max": 55.0,
        "nom_cop": 4.6,
    }
    base.update(kw)
    return base


# ---------- validate_spec -- root + required ----------

def test_validate_spec_minimal_ok():
    spec, errs = md.validate_spec(_spec())
    assert errs == []
    assert spec["family"] == "Altherma 3 R"


def test_validate_spec_full_with_points_ok():
    spec, errs = md.validate_spec(_spec(
        refrigerant="R32",
        buh_kw=3.0,
        max_flow_lmin=22.0,
        noise_db=58.0,
        bivalent=False,
        min_modulation_kw=2.0,
        points=[{"label": "A7/W35", "t_out": 7.0, "t_lwc": 35.0, "cop": 4.6}],
    ))
    assert errs == []


def test_validate_spec_not_dict():
    spec, errs = md.validate_spec([])
    assert spec == {}
    assert errs == ["root: not a dict"]


def test_validate_spec_missing_required():
    spec, errs = md.validate_spec({"family": "X"})
    assert spec == {}
    assert any("missing" in e for e in errs)


# ---------- validate_spec -- kw / lwt semantics ----------

def test_validate_spec_kw_zero_rejected():
    _, errs = md.validate_spec(_spec(kw=0.0))
    assert any("kw=" in e and "> 0" in e for e in errs)


def test_validate_spec_kw_bool_rejected():
    _, errs = md.validate_spec(_spec(kw=True))
    assert any("kw=" in e for e in errs)


def test_validate_spec_kw_string_rejected():
    _, errs = md.validate_spec(_spec(kw="eight"))
    assert any("kw=" in e for e in errs)


def test_validate_spec_lwt_min_ge_lwt_max_rejected():
    _, errs = md.validate_spec(_spec(lwt_min=55.0, lwt_max=55.0))
    assert any("lwt_min" in e and "lwt_max" in e for e in errs)


def test_validate_spec_lwt_min_string_skips_range():
    _, errs = md.validate_spec(_spec(lwt_min="cold"))
    assert not any("lwt_min" in e and ">=" in e for e in errs)


def test_validate_spec_lwt_min_bool_skips_range():
    _, errs = md.validate_spec(_spec(lwt_min=True))
    assert not any(">=" in e for e in errs)


def test_validate_spec_lwt_max_string_skips_range():
    _, errs = md.validate_spec(_spec(lwt_max="hot"))
    assert not any(">=" in e for e in errs)


def test_validate_spec_lwt_max_bool_skips_range():
    _, errs = md.validate_spec(_spec(lwt_max=False))
    assert not any(">=" in e for e in errs)


# ---------- validate_spec -- optional fields ----------

def test_validate_spec_refrigerant_enum_rejected():
    _, errs = md.validate_spec(_spec(refrigerant="R22"))
    assert any("refrigerant" in e for e in errs)


def test_validate_spec_bivalent_non_bool_rejected():
    _, errs = md.validate_spec(_spec(bivalent="yes"))
    assert any("bivalent" in e for e in errs)


def test_validate_spec_buh_kw_out_of_range():
    _, errs = md.validate_spec(_spec(buh_kw=25.0))
    assert any("buh_kw" in e for e in errs)


def test_validate_spec_min_modulation_kw_out_of_range():
    _, errs = md.validate_spec(_spec(min_modulation_kw=99.0))
    assert any("min_modulation_kw" in e for e in errs)


def test_validate_spec_max_flow_lmin_out_of_range():
    _, errs = md.validate_spec(_spec(max_flow_lmin=999.0))
    assert any("max_flow_lmin" in e for e in errs)


def test_validate_spec_noise_db_out_of_range():
    _, errs = md.validate_spec(_spec(noise_db=5.0))
    assert any("noise_db" in e for e in errs)


def test_validate_spec_numeric_optional_bool_rejected():
    _, errs = md.validate_spec(_spec(buh_kw=True))
    assert any("buh_kw" in e for e in errs)


# ---------- validate_spec -- points ----------

def test_validate_spec_points_not_list():
    _, errs = md.validate_spec(_spec(points="nope"))
    assert any("points" in e and "not a list" in e for e in errs)


def test_validate_spec_point_not_dict():
    _, errs = md.validate_spec(_spec(points=["nope"]))
    assert any("not a dict" in e for e in errs)


def test_validate_spec_point_missing_key():
    _, errs = md.validate_spec(
        _spec(points=[{"label": "A7/W35", "t_out": 7.0, "t_lwc": 35.0}])
    )
    assert any("cop" in e for e in errs)


def test_validate_spec_point_out_of_range():
    _, errs = md.validate_spec(
        _spec(points=[{"label": "X", "t_out": 7.0, "t_lwc": 35.0, "cop": 99.0}])
    )
    assert any("cop=99" in e for e in errs)


def test_validate_spec_point_bool_cop_rejected():
    _, errs = md.validate_spec(
        _spec(points=[{"label": "X", "t_out": 7.0, "t_lwc": 35.0, "cop": True}])
    )
    assert errs


# ---------- config_flow -- model_custom_info spec builder ----------

def test_step_info_form_has_placeholders():
    flow = _wizard()
    r = asyncio.run(flow.async_step_model_custom_info())
    assert r["type"] == "form"
    assert r["step_id"] == "model_custom_info"
    ph = r["description_placeholders"]
    assert "spec_example_min" in ph
    assert "spec_example_full" in ph
    assert "Altherma 3 R" in ph["spec_example_min"]


def test_step_info_empty_routes_none():
    flow = _wizard()
    r = asyncio.run(flow.async_step_model_custom_info(user_input={
        "custom_datasheet_json": "",
    }))
    assert r["step_id"] == "attribute_mapping"
    assert flow._data["custom_datasheet"] is None


def test_step_info_whitespace_routes_none():
    flow = _wizard()
    r = asyncio.run(flow.async_step_model_custom_info(user_input={
        "custom_datasheet_json": "   \n  ",
    }))
    assert r["step_id"] == "attribute_mapping"
    assert flow._data["custom_datasheet"] is None


def test_step_info_valid_routes_with_spec():
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


def test_step_info_invalid_json():
    flow = _wizard()
    r = asyncio.run(flow.async_step_model_custom_info(user_input={
        "custom_datasheet_json": "{not json",
    }))
    assert r["type"] == "form"
    assert r["step_id"] == "model_custom_info"
    assert r["errors"]["custom_datasheet_json"] == "invalid_json"


def test_step_info_invalid_spec():
    flow = _wizard()
    r = asyncio.run(flow.async_step_model_custom_info(user_input={
        "custom_datasheet_json": '{"family": "X"}',
    }))
    assert r["type"] == "form"
    assert r["step_id"] == "model_custom_info"
    assert r["errors"]["custom_datasheet_json"] == "invalid_spec"
