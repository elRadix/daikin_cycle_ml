"""#467: model profile on top of the setup model's datasheet.

The user fills in what the datasheet lacks (max heat at A-7/W35, the
compressor speed range) or adjusts a value. Every value carries its source
(datasheet / learned / manual); manual wins. The profile is applied on the
one path every consumer reads the datasheet through, so a value the user
sets is used across the integration (COP against the datasheet, the
normalised A7/W35 COP, alerts, cards).
"""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.daikin_cycle_ml.engine import model_profile as mp

DS = {
    "family": "Altherma 3 R", "kw": 11.0, "nom_cop": 4.86, "lwt_min": 25, "lwt_max": 55,
    "points": [
        {"label": "A7/W35", "t_out": 7, "t_lwc": 35, "cop": 4.86, "hc": 10.6},
        {"label": "A-7/W55", "t_out": -7, "t_lwc": 55, "cop": 1.82},
        {"label": "bad"},
    ],
}


def test_apply_without_profile_marks_datasheet_sources():
    out = mp.apply_profile(DS, None, "erla11dav3")
    assert out["value_sources"] == {"kw": "datasheet", "nom_cop": "datasheet", "lwt_min": "datasheet", "lwt_max": "datasheet"}
    a7 = next(p for p in out["points"] if p["label"] == "A7/W35")
    assert a7["src"] == {"cop": "datasheet", "hc": "datasheet"}
    assert out["profile"]["applied"] is False
    assert len(out["points"]) == 2           # the point without temperatures is dropped
    assert "src" not in DS["points"][0]       # the bundled entry is never changed


def test_manual_values_fill_and_override_per_value():
    prof = mp.edit({}, "erla11dav3", fields={"kw": 11.2, "rps_max": 90},
                   points=[{"t_out": -7, "t_lwc": 55, "hc": 7.2},      # fills a missing value
                           {"t_out": 7, "t_lwc": 35, "cop": 5.0},      # overrides one value
                           {"t_out": -7, "t_lwc": 35, "hc": 8.5, "cop": 2.92}])  # new point
    out = mp.apply_profile(DS, prof, "erla11dav3", {"rps_min": 16, "rps_max": 95})
    pts = {(p["t_out"], p["t_lwc"]): p for p in out["points"]}
    assert pts[(-7.0, 55.0)]["hc"] == 7.2 and pts[(-7.0, 55.0)]["src"] == {"cop": "datasheet", "hc": "manual"}
    assert pts[(7.0, 35.0)]["cop"] == 5.0 and pts[(7.0, 35.0)]["hc"] == 10.6
    assert pts[(7.0, 35.0)]["src"] == {"cop": "manual", "hc": "datasheet"}
    assert pts[(-7.0, 35.0)]["label"] == "A-7/W35" and pts[(-7.0, 35.0)]["src"] == {"hc": "manual", "cop": "manual"}
    assert out["kw"] == 11.2 and out["value_sources"]["kw"] == "manual"
    assert out["rps_max"] == 90 and out["value_sources"]["rps_max"] == "manual"   # manual beats learned
    assert out["rps_min"] == 16 and out["value_sources"]["rps_min"] == "learned"
    assert out["profile"] == {"model": "erla11dav3", "applied": True, "manual_fields": ["kw", "rps_max"], "manual_points": 3}


def test_profile_of_another_model_is_kept_but_not_applied():
    prof = mp.edit({}, "erla11dav3", fields={"kw": 9.0})
    out = mp.apply_profile(DS, prof, "epra12eav3")
    assert out["kw"] == 11.0 and out["profile"]["applied"] is False and out["profile"]["model"] == "erla11dav3"


def test_profile_alone_builds_an_entry_and_nothing_gives_none():
    prof = mp.edit({}, "custom", points=[{"t_out": 7, "t_lwc": 35, "cop": 4.5}])
    out = mp.apply_profile(None, prof, "custom")
    assert out["points"][0]["label"] == "A7/W35" and out["points"][0]["cop"] == 4.5
    assert mp.apply_profile(None, None, "custom") is None
    assert mp.apply_profile(None, prof, "other") is None


def test_learned_range_never_beats_the_datasheet():
    out = mp.apply_profile({**DS, "rps_max": 100}, None, "m", {"rps_min": 16, "rps_max": 95, "runs": 40})
    assert out["rps_max"] == 100 and out["value_sources"]["rps_max"] == "datasheet"
    assert out["value_sources"]["rps_min"] == "learned"
    out = mp.apply_profile(DS, None, "m", {"rps_min": 0.2, "rps_max": "x"})   # out of range / not a number
    assert "rps_min" not in out and "rps_max" not in out


def test_edit_clears_values_points_and_resets():
    prof = mp.edit({}, "m", fields={"kw": 11.0, "rps_min": 15},
                   points=[{"t_out": 2, "t_lwc": 35, "hc": 9.0, "cop": 3.65}])
    prof = mp.edit(prof, "m", fields={"kw": None, "nope": 1},
                   points=[{"t_out": 2, "t_lwc": 35, "hc": None}, {"t_out": None, "t_lwc": 35}])
    assert prof["fields"] == {"rps_min": 15.0}
    assert prof["points"] == [{"t_out": 2.0, "t_lwc": 35.0, "cop": 3.65}]
    prof = mp.edit(prof, "m", points=[{"t_out": 2, "t_lwc": 35, "cop": None}])
    assert prof["points"] == []
    assert mp.edit(prof, "m", reset=True) == {"model": "m", "fields": {}, "points": []}
    # editing for another model starts a new profile
    assert mp.edit({"model": "a", "fields": {"kw": 5}}, "b", fields={"nom_cop": 4})["fields"] == {"nom_cop": 4.0}


def test_normalize_drops_invalid_parts():
    raw = {"model": "", "fields": {"kw": 999, "nom_cop": "4.2", "lwt_max": True},
           "points": ["x", {"t_out": 99, "t_lwc": 35, "cop": 3}, {"t_out": 7, "t_lwc": 35, "cop": 99},
                      {"t_out": "7", "t_lwc": 35.04, "hc": "10.5"}, {"t_out": 7, "t_lwc": 35, "cop": float("nan")}]}
    assert mp.normalize(raw) == {"model": None, "fields": {"nom_cop": 4.2},
                                 "points": [{"t_out": 7.0, "t_lwc": 35.0, "hc": 10.5}]}
    assert mp.normalize("x") == mp.empty_profile()
    assert mp.normalize({"fields": [], "points": None}) == mp.empty_profile()


def test_validate_edit_explains_every_error():
    assert mp.validate_edit({"kw": 11, "rps_max": None}, [{"t_out": -7, "t_lwc": 55, "hc": 7.2, "cop": None}]) == []
    errs = mp.validate_edit({"kw": 0, "x": 1}, [{"t_out": -50, "t_lwc": 5, "hc": 99, "y": 1}, "z"])
    assert any("kw=0" in e for e in errs) and any("unknown field 'x'" in e for e in errs)
    assert any("t_out=-50" in e for e in errs) and any("t_lwc=5" in e for e in errs)
    assert any("hc=99" in e for e in errs) and any("unknown field 'y'" in e for e in errs)
    assert any("not a mapping" in e for e in errs)
    assert mp.validate_edit("x", None) == ["fields must be a mapping"]
    assert mp.validate_edit(None, "x") == ["points must be a list"]


def test_learn_rps_needs_enough_runs_and_is_robust():
    assert mp.learn_rps([(30, 60)] * 5) == {"runs": 5}
    rows = [(18 + i % 5, 70 + i % 20) for i in range(40)] + [(1, 140)]   # one odd run
    out = mp.learn_rps(rows)
    assert out["runs"] == 41 and 17 <= out["rps_min"] <= 19 and 85 <= out["rps_max"] <= 90
    assert mp.learn_rps([(50, 40)] * 30) == {"runs": 30}        # max below min: not learned
    assert mp.learn_rps([(None, "x")] * 30) == {"runs": 0}


async def test_store_round_trip(hass):
    saved = await mp.save(hass, "e1", {"model": "m", "fields": {"kw": 11, "bad": 1}})
    assert saved == {"model": "m", "fields": {"kw": 11.0}, "points": []}
    assert await mp.load(hass, "e1") == saved
    assert await mp.load(hass, "e2") == mp.empty_profile()


# ---------- the whole integration uses the profile ----------

def _coord():
    from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator

    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.hass = MagicMock()
    c.entry = SimpleNamespace(entry_id="e1", data={"model": "erla11dav3"})
    c._datasheet_merged = {"erla11dav3": dict(DS)}
    c._datasheet_user_loaded = True
    c._datasheet_defaults = {"outdoor_min_c": -25}
    c._datasheet_cache = {}
    c._model_profile = mp.empty_profile()
    c._rps_learned = {}
    return c


async def test_reload_reads_the_store_and_survives_a_bad_one():
    c = _coord()
    with patch.object(mp, "load", AsyncMock(return_value={"model": "erla11dav3", "fields": {"kw": 9.5}, "points": []})):
        await c.async_reload_model_profile()
    assert c.model_profile["fields"] == {"kw": 9.5}
    with patch.object(mp, "load", AsyncMock(side_effect=ValueError("broken"))):
        await c.async_reload_model_profile()
    assert c.model_profile == mp.empty_profile()


async def test_profile_reaches_the_snapshot_datasheet():
    c = _coord()
    c._model_profile = mp.edit({}, "erla11dav3", points=[{"t_out": -7, "t_lwc": 55, "hc": 7.2}])
    c._rps_learned = {"rps_min": 16, "rps_max": 95, "runs": 30}
    await c._refresh_datasheet_state(time.time(), None, None, None)
    ds = c._datasheet_cache["datasheet"]
    pt = next(p for p in ds["points"] if p["t_out"] == -7)
    assert pt["hc"] == 7.2 and pt["src"]["hc"] == "manual"
    assert ds["rps_min"] == 16 and ds["value_sources"]["rps_min"] == "learned"
    assert c.rps_learned["runs"] == 30


def test_edit_ignores_out_of_range_values_and_apply_skips_bad_points():
    prof = mp.edit({}, "m", points=[{"t_out": 7, "t_lwc": 35, "hc": 99, "cop": 4.0}])
    assert prof["points"] == [{"t_out": 7.0, "t_lwc": 35.0, "cop": 4.0}]
    out = mp.apply_profile({"nom_cop": 4.0, "points": ["not a point", {"t_out": 7, "t_lwc": 35, "cop": 4.0}]}, None, "m")
    assert len(out["points"]) == 1


async def test_rps_query_on_the_real_schema(tmp_path):
    import sqlite3

    from custom_components.daikin_cycle_ml.storage.db import CycleDB

    empty = CycleDB.__new__(CycleDB)
    empty._conn = None
    assert await empty.async_rps_since(0.0) == []
    db = CycleDB(str(tmp_path / "t.db"))
    await db.async_initialize()
    try:
        rows = [  # start, end, duration, mode, rps_max, rps_avg, is_transient
            (100, 4000, 3900, "heating", 72, 28.5, 0),
            (100, 4000, 3900, "dhw", 90, 60.0, 0),
            (100, 400, 300, "heating", 40, 30.0, 0),        # too short
            (100, 4000, 3900, "cooling", 80, 50.0, 0),      # cooling
            (100, 4000, 3900, "heating", 70, 25.0, 1),      # transient
            (100, 4000, 3900, "heating", None, None, 0),    # no speed
        ]
        for i, r in enumerate(rows):
            r = (r[0] + i, *r[1:])   # start_ts is unique
            await db._conn.execute(
                "INSERT INTO cycles (start_ts, end_ts, duration_s, mode, rps_max, rps_avg, is_transient) "
                "VALUES (?,?,?,?,?,?,?)", r)
        await db._conn.commit()
        assert sorted(await db.async_rps_since(0.0)) == [(28.5, 72), (60.0, 90)]
        assert await db.async_rps_since(5000.0) == []
    finally:
        await db.async_close()
    bad = CycleDB.__new__(CycleDB)
    bad._conn = MagicMock()
    bad._conn.execute = AsyncMock(side_effect=sqlite3.OperationalError("locked"))
    assert await bad.async_rps_since(0.0) == []


# ---------- service: set_model_profile ----------

def _svc_coord(model="erla11dav3"):
    c = MagicMock()
    c.entry = SimpleNamespace(entry_id="e1", data={"model": model})
    c.model_profile = mp.empty_profile()
    c.async_reload_model_profile = AsyncMock()
    c.async_request_refresh = AsyncMock()
    return c


async def test_service_saves_reloads_and_refreshes(hass):
    from custom_components.daikin_cycle_ml import services as S

    c = _svc_coord()
    call = SimpleNamespace(data={"points": [{"t_out": -7, "t_lwc": 55, "hc": 7.2}], "fields": {"rps_min": 16}})
    with patch.object(S, "_resolve_optional_coordinator", return_value=c):
        res = await S._handle_set_model_profile(hass, call)
    assert res["model"] == "erla11dav3"
    assert res["profile"]["points"] == [{"t_out": -7.0, "t_lwc": 55.0, "hc": 7.2}]
    assert (await mp.load(hass, "e1"))["fields"] == {"rps_min": 16.0}
    c.async_reload_model_profile.assert_awaited_once()
    c.async_request_refresh.assert_awaited_once()


async def test_service_refuses_invalid_values(hass):
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.daikin_cycle_ml import services as S

    c = _svc_coord()
    with patch.object(S, "_resolve_optional_coordinator", return_value=c), \
            pytest.raises(HomeAssistantError, match="kw=0"):
        await S._handle_set_model_profile(hass, SimpleNamespace(data={"fields": {"kw": 0}}))
    c.async_reload_model_profile.assert_not_awaited()


def test_service_schema_and_registration():
    from custom_components.daikin_cycle_ml import services as S

    assert S.SCHEMA_SET_MODEL_PROFILE({})["reset"] is False
    src = (S.__file__)
    assert "SERVICE_SET_MODEL_PROFILE" in open(src).read()


# ---------- Configure -> Model profile ----------

def _options_flow(monkeypatch, hass, coord):
    from custom_components.daikin_cycle_ml.config_flow import DaikinCycleMLOptionsFlow

    entry = SimpleNamespace(entry_id="e1", data={"model": "erla11dav3"}, options={"x": 1}, runtime_data=coord)
    flow = DaikinCycleMLOptionsFlow()
    flow.hass = hass
    monkeypatch.setattr(DaikinCycleMLOptionsFlow, "config_entry", property(lambda self: entry), raising=False)
    return flow


async def test_configure_step_shows_current_values_and_learned_range(hass, monkeypatch):
    await mp.save(hass, "e1", mp.edit({}, "erla11dav3", fields={"rps_max": 90}))
    coord = SimpleNamespace(rps_learned={"rps_min": 16.0, "rps_max": 95.0, "runs": 34},
                            async_reload_model_profile=AsyncMock())
    flow = _options_flow(monkeypatch, hass, coord)
    res = await flow.async_step_model_profile()
    assert res["type"] == "form" and res["step_id"] == "model_profile"
    assert res["description_placeholders"]["learned"] == "16.0–95.0 rps (34)"
    keys = {str(k): k for k in res["data_schema"].schema}
    assert keys["rps_max"].description["suggested_value"] == 90.0
    assert keys["points"].description["suggested_value"] is None


async def test_configure_step_saves_and_reloads(hass, monkeypatch):
    coord = SimpleNamespace(rps_learned={"runs": 3}, async_reload_model_profile=AsyncMock())
    flow = _options_flow(monkeypatch, hass, coord)
    res = await flow.async_step_model_profile()
    assert res["description_placeholders"]["learned"] == "— (3)"
    res = await flow.async_step_model_profile({"rps_min": 16, "points": [{"t_out": -7, "t_lwc": 55, "hc": 7.2}]})
    assert res["type"] == "create_entry" and res["data"] == {"x": 1}
    saved = await mp.load(hass, "e1")
    assert saved["fields"] == {"rps_min": 16.0} and saved["points"][0]["hc"] == 7.2
    coord.async_reload_model_profile.assert_awaited_once()


async def test_configure_step_explains_invalid_values(hass, monkeypatch):
    flow = _options_flow(monkeypatch, hass, None)
    await mp.save(hass, "e1", mp.edit({}, "other", fields={"kw": 5}))   # profile of another model
    res = await flow.async_step_model_profile({"rps_max": 500, "points": [{"t_out": 99, "t_lwc": 35, "cop": 3}]})
    assert res["errors"] == {"base": "invalid_profile"}
    assert "rps_max=500" in res["description_placeholders"]["problem"]
    assert res["description_placeholders"]["learned"] == "— (0)"
    keys = {str(k): k for k in res["data_schema"].schema}
    assert keys["kw"].description["suggested_value"] is None      # other model's value not shown
    res = await flow.async_step_model_profile({"kw": 11.0})
    assert res["type"] == "create_entry"
