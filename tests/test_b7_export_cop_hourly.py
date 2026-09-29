"""B7: export_cop_hourly service. Marker: B7_EXPORT_COP_HOURLY_v1"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
import voluptuous as vol

from homeassistant.exceptions import HomeAssistantError

from custom_components.daikin_cycle_ml.services import (
    SCHEMA_EXPORT_COP_HOURLY,
    SERVICE_EXPORT_COP_HOURLY,
    _do_export_cop_hourly,
    _handle_export_cop_hourly,
)


def _mk_coord(db=None):
    coord = MagicMock()
    coord.db = db
    return coord


def _mk_rows():
    return [
        {"ts_hour": 100, "mode": "heating", "n_samples": 12,
         "cop_mean": 3.5, "cop_p10": 3.0, "cop_p50": 3.5,
         "cop_p90": 4.0, "cop_std": 0.1, "lwt_mean": 35.0,
         "outdoor_mean": 5.0, "outdoor_min": 4.0,
         "outdoor_max": 6.0, "flow_mean": 15.0,
         "updated_ts": 1000.0},
        {"ts_hour": 101, "mode": "dhw", "n_samples": 4,
         "cop_mean": 2.0, "cop_p10": 1.9, "cop_p50": 2.0,
         "cop_p90": 2.2, "cop_std": 0.1, "lwt_mean": 52.0,
         "outdoor_mean": 5.0, "outdoor_min": 4.0,
         "outdoor_max": 6.0, "flow_mean": 14.0,
         "updated_ts": 1000.0},
    ]


def test_b7_service_constant():
    assert SERVICE_EXPORT_COP_HOURLY == "export_cop_hourly"


def test_b7_schema_valid():
    data = SCHEMA_EXPORT_COP_HOURLY({
        "entry_id": "abc", "days": 7, "mode": "heating",
        "format": "csv",
    })
    assert data["entry_id"] == "abc"
    assert data["days"] == 7
    assert data["mode"] == "heating"
    assert data["format"] == "csv"


def test_b7_schema_defaults():
    data = SCHEMA_EXPORT_COP_HOURLY({"entry_id": "abc"})
    assert data["days"] == 30
    assert data["format"] == "json"
    assert data.get("mode") is None


def test_b7_schema_rejects_zero_days():
    with pytest.raises(vol.Invalid):
        SCHEMA_EXPORT_COP_HOURLY({"entry_id": "abc", "days": 0})


def test_b7_schema_rejects_too_many_days():
    with pytest.raises(vol.Invalid):
        SCHEMA_EXPORT_COP_HOURLY({"entry_id": "abc", "days": 366})


def test_b7_schema_rejects_bad_format():
    with pytest.raises(vol.Invalid):
        SCHEMA_EXPORT_COP_HOURLY({"entry_id": "abc", "format": "xml"})


async def test_b7_worker_json():
    db = MagicMock()
    db.async_query_cop_hourly = AsyncMock(return_value=_mk_rows())
    coord = _mk_coord(db=db)
    out = await _do_export_cop_hourly(coord, 30, None, "json")
    assert out["format"] == "json"
    assert out["count"] == 2
    assert out["rows"] == _mk_rows()
    assert out["mode"] is None
    assert out["days"] == 30


async def test_b7_worker_csv():
    db = MagicMock()
    db.async_query_cop_hourly = AsyncMock(return_value=_mk_rows())
    coord = _mk_coord(db=db)
    out = await _do_export_cop_hourly(coord, 30, None, "csv")
    assert out["format"] == "csv"
    assert out["count"] == 2
    assert "ts_hour" in out["content"]
    assert "heating" in out["content"]


async def test_b7_worker_csv_empty():
    db = MagicMock()
    db.async_query_cop_hourly = AsyncMock(return_value=[])
    coord = _mk_coord(db=db)
    out = await _do_export_cop_hourly(coord, 30, None, "csv")
    assert out["content"] == ""
    assert out["count"] == 0


async def test_b7_worker_no_db():
    coord = _mk_coord(db=None)
    with pytest.raises(HomeAssistantError):
        await _do_export_cop_hourly(coord, 30, None, "json")


async def test_b7_worker_mode_filter():
    db = MagicMock()
    db.async_query_cop_hourly = AsyncMock(return_value=[])
    coord = _mk_coord(db=db)
    await _do_export_cop_hourly(coord, 7, "dhw", "json")
    kwargs = db.async_query_cop_hourly.call_args.kwargs
    assert kwargs["mode"] == "dhw"


async def test_b7_handler_passthrough(monkeypatch):
    from custom_components.daikin_cycle_ml import services as svc
    db = MagicMock()
    db.async_query_cop_hourly = AsyncMock(return_value=_mk_rows())
    coord = _mk_coord(db=db)
    monkeypatch.setattr(svc, "_resolve_coordinator", lambda h, e: coord)
    hass = MagicMock()
    call = MagicMock()
    call.data = {
        "entry_id": "e1", "days": 7, "mode": None, "format": "json",
    }
    out = await _handle_export_cop_hourly(hass, call)
    assert out["count"] == 2
    assert out["days"] == 7


async def test_b7_registration_includes_export_cop_hourly():
    from custom_components.daikin_cycle_ml import services as svc
    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.has_service = MagicMock(return_value=False)
    registered = []

    def _reg(domain, name, handler, schema=None):
        registered.append(name)

    hass.services.async_register = MagicMock(side_effect=_reg)
    await svc.async_register_services(hass)
    assert "export_cop_hourly" in registered
