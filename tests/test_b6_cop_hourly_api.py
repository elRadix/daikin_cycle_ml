"""B6: cop_hourly REST view + curve sensor. Marker: B6_COP_HOURLY_API_v1"""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml import api as api_mod
from custom_components.daikin_cycle_ml.api import (
    CopHourlyView,
    _parse_days,
)
from custom_components.daikin_cycle_ml.const import (
    COP_CURVE_RECENT_HOURS,
    COP_CURVE_RECENT_MAX_POINTS,
    COP_HOURLY_API_DEFAULT_DAYS,
    COP_HOURLY_API_MAX_DAYS,
)
from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    DataSnapshot,
)
from custom_components.daikin_cycle_ml.sensor import (
    SENSOR_DEFS,
    _attrs_cop_curve_recent,
)
from custom_components.daikin_cycle_ml.storage.db import CycleDB


# ---------- _parse_days ----------

def test_b6_parse_days_none_default():
    assert _parse_days(None) == COP_HOURLY_API_DEFAULT_DAYS


def test_b6_parse_days_valid():
    assert _parse_days("7") == 7
    assert _parse_days("1") == 1
    assert _parse_days(str(COP_HOURLY_API_MAX_DAYS)) == COP_HOURLY_API_MAX_DAYS


def test_b6_parse_days_zero_invalid():
    assert _parse_days("0") is None


def test_b6_parse_days_above_max_invalid():
    assert _parse_days(str(COP_HOURLY_API_MAX_DAYS + 1)) is None


def test_b6_parse_days_non_int_invalid():
    assert _parse_days("abc") is None


# ---------- View construction ----------

def _mk_view(entries=None):
    hass = MagicMock()
    hass.config_entries.async_entries.return_value = entries or []
    return CopHourlyView(hass), hass


def _mk_request(days=None, mode=None):
    q: dict[str, str] = {}
    if days is not None:
        q["days"] = days
    if mode is not None:
        q["mode"] = mode
    req = MagicMock()
    req.query = q
    return req


def test_b6_view_attrs():
    assert CopHourlyView.url == "/api/daikin_cycle_ml/cop_hourly"
    assert CopHourlyView.name == "api:daikin_cycle_ml:cop_hourly"
    assert CopHourlyView.requires_auth is True


async def test_b6_view_bad_days():
    view, _hass = _mk_view()
    resp = await view.get(_mk_request(days="abc"))
    assert resp.status == 400


async def test_b6_view_no_entries():
    view, _hass = _mk_view(entries=[])
    resp = await view.get(_mk_request())
    assert resp.status == 503


async def test_b6_view_no_coordinator():
    entry = SimpleNamespace(runtime_data=None)
    view, _hass = _mk_view(entries=[entry])
    resp = await view.get(_mk_request())
    assert resp.status == 503


async def test_b6_view_no_db():
    entry = SimpleNamespace(runtime_data=SimpleNamespace(db=None))
    view, _hass = _mk_view(entries=[entry])
    resp = await view.get(_mk_request())
    assert resp.status == 503


async def test_b6_view_query_failure():
    db = MagicMock()
    db.async_query_cop_hourly = AsyncMock(side_effect=RuntimeError("boom"))
    entry = SimpleNamespace(runtime_data=SimpleNamespace(db=db))
    view, _hass = _mk_view(entries=[entry])
    resp = await view.get(_mk_request(days="7"))
    assert resp.status == 500


async def test_b6_view_success_defaults():
    db = MagicMock()
    db.async_query_cop_hourly = AsyncMock(return_value=[{"ts_hour": 1}])
    entry = SimpleNamespace(runtime_data=SimpleNamespace(db=db))
    view, _hass = _mk_view(entries=[entry])
    resp = await view.get(_mk_request())
    assert resp.status == 200
    db.async_query_cop_hourly.assert_awaited_once()
    call_kwargs = db.async_query_cop_hourly.call_args.kwargs
    assert call_kwargs["mode"] is None


async def test_b6_view_mode_filter():
    db = MagicMock()
    db.async_query_cop_hourly = AsyncMock(return_value=[])
    entry = SimpleNamespace(runtime_data=SimpleNamespace(db=db))
    view, _hass = _mk_view(entries=[entry])
    await view.get(_mk_request(days="7", mode="heating"))
    call_kwargs = db.async_query_cop_hourly.call_args.kwargs
    assert call_kwargs["mode"] == "heating"


async def test_b6_view_mode_blank_becomes_none():
    db = MagicMock()
    db.async_query_cop_hourly = AsyncMock(return_value=[])
    entry = SimpleNamespace(runtime_data=SimpleNamespace(db=db))
    view, _hass = _mk_view(entries=[entry])
    await view.get(_mk_request(days="7", mode="   "))
    call_kwargs = db.async_query_cop_hourly.call_args.kwargs
    assert call_kwargs["mode"] is None


# ---------- Coordinator curve_recent ----------

async def test_b6_refresh_curve_db_none():
    obj = MagicMock()
    obj.db = None
    obj._cop_hourly_cache = {}
    await DaikinCycleMLCoordinator._refresh_cop_curve_recent(obj, 1000.0)
    assert obj._cop_hourly_cache == {}


async def test_b6_refresh_curve_populates():
    obj = MagicMock()
    obj.db = MagicMock()
    obj.db.async_query_cop_hourly = AsyncMock(return_value=[
        {"ts_hour": 100, "mode": "heating", "cop_mean": 3.5,
         "cop_p50": 3.5, "cop_p90": 4.0, "lwt_mean": 35.0,
         "outdoor_mean": 5.0, "n_samples": 12},
        {"ts_hour": 101, "mode": "dhw", "cop_mean": 2.0,
         "cop_p50": 2.0, "cop_p90": 2.2, "lwt_mean": 52.0,
         "outdoor_mean": 5.0, "n_samples": 4},
    ])
    obj._cop_hourly_cache = {}
    await DaikinCycleMLCoordinator._refresh_cop_curve_recent(obj, 1000.0)
    data = obj._cop_hourly_cache["curve_recent"]
    assert data["n_points"] == 2
    assert data["window_hours"] == COP_CURVE_RECENT_HOURS
    assert data["modes_present"] == ["dhw", "heating"]
    assert data["points"][0]["ts"] == 100 * 3600
    assert data["points"][0]["mode"] == "heating"


async def test_b6_refresh_curve_caps_points():
    obj = MagicMock()
    obj.db = MagicMock()
    rows = [
        {"ts_hour": i, "mode": "heating", "cop_mean": 3.0,
         "cop_p50": 3.0, "cop_p90": 3.5, "lwt_mean": None,
         "outdoor_mean": None, "n_samples": 1}
        for i in range(COP_CURVE_RECENT_MAX_POINTS + 20)
    ]
    obj.db.async_query_cop_hourly = AsyncMock(return_value=rows)
    obj._cop_hourly_cache = {}
    await DaikinCycleMLCoordinator._refresh_cop_curve_recent(obj, 1000.0)
    data = obj._cop_hourly_cache["curve_recent"]
    assert data["n_points"] == COP_CURVE_RECENT_MAX_POINTS


async def test_b6_refresh_curve_null_mode():
    obj = MagicMock()
    obj.db = MagicMock()
    obj.db.async_query_cop_hourly = AsyncMock(return_value=[
        {"ts_hour": 1, "mode": None, "cop_mean": 3.0,
         "cop_p50": 3.0, "cop_p90": 3.5, "lwt_mean": None,
         "outdoor_mean": None, "n_samples": 1},
    ])
    obj._cop_hourly_cache = {}
    await DaikinCycleMLCoordinator._refresh_cop_curve_recent(obj, 1000.0)
    data = obj._cop_hourly_cache["curve_recent"]
    assert data["points"][0]["mode"] == "unknown"


# ---------- Sensor helpers ----------

def test_b6_sensor_def_includes_key():
    keys = [d["key"] for d in SENSOR_DEFS]
    assert "cop_curve_recent" in keys


def test_b6_attrs_helper_populated():
    snap = DataSnapshot()
    snap.cop_curve_recent = {
        "points": [{"ts": 1, "mode": "heating", "cop_mean": 3.5}],
        "n_points": 1,
        "window_hours": 48,
        "modes_present": ["heating"],
        "updated_ts": 1000.0,
    }
    obj = MagicMock()
    attrs = _attrs_cop_curve_recent(snap, obj)
    assert attrs["n_points"] == 1
    assert attrs["window_hours"] == 48
    assert attrs["points"][0]["mode"] == "heating"


def test_b6_attrs_helper_empty():
    snap = DataSnapshot()
    obj = MagicMock()
    attrs = _attrs_cop_curve_recent(snap, obj)
    assert attrs["points"] == []
    assert attrs["n_points"] is None
    assert attrs["modes_present"] == []


async def test_b6_refresh_curve_isolated_failure():
    """Curve refresh failure must not break KPI cache/ts."""
    obj = MagicMock()
    obj.db = MagicMock()
    obj.db.async_cop_hourly_stats = AsyncMock(
        return_value={"n_hours": 24, "n_samples": 100,
                      "cop_mean": 3.5, "cop_p10": 3.0,
                      "cop_p90": 4.0, "cop_min": 3.0, "cop_max": 4.0}
    )
    obj.db.async_cop_hourly_by_mode = AsyncMock(
        return_value={"heating": {"cop_mean": 3.5}}
    )
    obj.db.async_query_cop_hourly = AsyncMock(
        side_effect=RuntimeError("curve boom")
    )
    obj._cop_hourly_cache = {}
    obj._cop_hourly_cache_ts = 0.0
    await DaikinCycleMLCoordinator._maybe_refresh_cop_hourly(obj, 2000.0)
    assert set(obj._cop_hourly_cache) >= {"day", "week", "month"}
    assert obj._cop_hourly_cache_ts == 2000.0
    assert "curve_recent" not in obj._cop_hourly_cache
