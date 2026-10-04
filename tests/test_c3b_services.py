"""C3b - services: import_datasheet, remove_user_datasheet + Repairs."""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.daikin_cycle_ml import repairs as rp
from custom_components.daikin_cycle_ml import services as svc
from custom_components.daikin_cycle_ml.const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

EID = "abcdef0123456789abcdef0123456789"


def _model() -> dict[str, Any]:
    return {"family": "EPRA", "kw": 4.0, "lwt_min": 25.0, "lwt_max": 55.0,
            "nom_cop": 4.6,
            "points": [{"label": "A7/W35", "t_out": 7.0, "t_lwc": 35.0, "cop": 4.6}]}


def _payload(models: dict[str, Any] | None = None, schema: int = 1) -> dict[str, Any]:
    return {"schema_version": schema,
            "models": models if models is not None else {"x": _model()}}


def _fake_coord() -> MagicMock:
    c = MagicMock()
    c.async_reload_user_datasheets = AsyncMock()
    return c


async def _call(hass: HomeAssistant, name: str, data: dict[str, Any], coord: MagicMock | None = None) -> tuple[Any, MagicMock, dict[str, MagicMock]]:
    coord = coord or _fake_coord()
    await svc.async_register_services(hass)
    m = {"import_invalid": MagicMock(), "clear_import_invalid": MagicMock(),
         "schema_unknown": MagicMock(), "clear_schema_unknown": MagicMock()}
    with patch.object(svc, "_resolve_coordinator", return_value=coord), \
         patch.object(svc, "raise_datasheet_import_invalid", m["import_invalid"]), \
         patch.object(svc, "clear_datasheet_import_invalid", m["clear_import_invalid"]), \
         patch.object(svc, "raise_datasheet_schema_unknown", m["schema_unknown"]), \
         patch.object(svc, "clear_datasheet_schema_unknown", m["clear_schema_unknown"]):
        resp = await hass.services.async_call(
            DOMAIN, name, data, blocking=True, return_response=True)
    return resp, coord, m


class TestImportHappyPath:
    async def test_dict_payload_imported(self, hass: HomeAssistant) -> None:
        resp, c, m = await _call(hass, svc.SERVICE_IMPORT_DATASHEET,
            {svc.ATTR_ENTRY_ID: EID, svc.ATTR_PAYLOAD: _payload()})
        assert resp == {"imported": ["x"], "errors": []}
        c.async_reload_user_datasheets.assert_awaited_once()
        m["import_invalid"].assert_not_called()
        m["clear_import_invalid"].assert_called_once()

    async def test_json_string_payload(self, hass: HomeAssistant) -> None:
        resp, _, _ = await _call(hass, svc.SERVICE_IMPORT_DATASHEET,
            {svc.ATTR_ENTRY_ID: EID, svc.ATTR_PAYLOAD: json.dumps(_payload())})
        assert resp["imported"] == ["x"] and resp["errors"] == []

    async def test_partial_validity(self, hass: HomeAssistant) -> None:
        resp, c, m = await _call(hass, svc.SERVICE_IMPORT_DATASHEET,
            {svc.ATTR_ENTRY_ID: EID,
             svc.ATTR_PAYLOAD: _payload({"ok": _model(), "bad": {"family": "X"}})})
        assert resp["imported"] == ["ok"]
        assert len(resp["errors"]) >= 1
        c.async_reload_user_datasheets.assert_awaited_once()
        m["import_invalid"].assert_called_once()

    async def test_clears_issues_on_success(self, hass: HomeAssistant) -> None:
        _, _, m = await _call(hass, svc.SERVICE_IMPORT_DATASHEET,
            {svc.ATTR_ENTRY_ID: EID, svc.ATTR_PAYLOAD: _payload()})
        m["clear_import_invalid"].assert_called_once()
        m["clear_schema_unknown"].assert_called_once()


class TestImportErrors:
    async def test_invalid_json_string(self, hass: HomeAssistant) -> None:
        resp, c, m = await _call(hass, svc.SERVICE_IMPORT_DATASHEET,
            {svc.ATTR_ENTRY_ID: EID, svc.ATTR_PAYLOAD: "{nope"})
        assert resp["imported"] == []
        assert "json parse error" in resp["errors"][0]
        c.async_reload_user_datasheets.assert_not_awaited()
        m["import_invalid"].assert_called_once()

    async def test_schema_version_mismatch(self, hass: HomeAssistant) -> None:
        resp, _, m = await _call(hass, svc.SERVICE_IMPORT_DATASHEET,
            {svc.ATTR_ENTRY_ID: EID, svc.ATTR_PAYLOAD: _payload(schema=2)})
        assert resp["imported"] == []
        m["schema_unknown"].assert_called_once()
        m["import_invalid"].assert_not_called()

    async def test_empty_models(self, hass: HomeAssistant) -> None:
        resp, _, m = await _call(hass, svc.SERVICE_IMPORT_DATASHEET,
            {svc.ATTR_ENTRY_ID: EID,
             svc.ATTR_PAYLOAD: {"schema_version": 1, "models": []}})
        assert resp["imported"] == []
        m["import_invalid"].assert_called_once()

    async def test_root_not_dict(self, hass: HomeAssistant) -> None:
        resp, _, _ = await _call(hass, svc.SERVICE_IMPORT_DATASHEET,
            {svc.ATTR_ENTRY_ID: EID, svc.ATTR_PAYLOAD: "42"})
        assert resp["imported"] == []
        assert len(resp["errors"]) >= 1

    async def test_reload_missing_attr_safe(self, hass: HomeAssistant) -> None:
        coord = MagicMock(spec=[])
        resp, _, _ = await _call(hass, svc.SERVICE_IMPORT_DATASHEET,
            {svc.ATTR_ENTRY_ID: EID, svc.ATTR_PAYLOAD: _payload()}, coord=coord)
        assert resp["imported"] == ["x"]


class TestRemove:
    async def test_remove_existing(self, hass: HomeAssistant) -> None:
        await _call(hass, svc.SERVICE_IMPORT_DATASHEET,
            {svc.ATTR_ENTRY_ID: EID, svc.ATTR_PAYLOAD: _payload()})
        resp, c, _ = await _call(hass, svc.SERVICE_REMOVE_USER_DATASHEET,
            {svc.ATTR_ENTRY_ID: EID, svc.ATTR_MODEL_KEY: "x"})
        assert resp == {"removed": True, "model_key": "x"}
        c.async_reload_user_datasheets.assert_awaited_once()

    async def test_remove_missing_noop(self, hass: HomeAssistant) -> None:
        resp, c, _ = await _call(hass, svc.SERVICE_REMOVE_USER_DATASHEET,
            {svc.ATTR_ENTRY_ID: EID, svc.ATTR_MODEL_KEY: "nope"})
        assert resp == {"removed": False, "model_key": "nope"}
        c.async_reload_user_datasheets.assert_not_awaited()

    async def test_remove_reload_missing_attr_safe(self, hass: HomeAssistant) -> None:
        await _call(hass, svc.SERVICE_IMPORT_DATASHEET,
            {svc.ATTR_ENTRY_ID: EID, svc.ATTR_PAYLOAD: _payload()})
        coord = MagicMock(spec=[])
        resp, _, _ = await _call(hass, svc.SERVICE_REMOVE_USER_DATASHEET,
            {svc.ATTR_ENTRY_ID: EID, svc.ATTR_MODEL_KEY: "x"}, coord=coord)
        assert resp["removed"] is True


class TestRepairsSmoke:
    def test_raise_import_invalid_calls_create(self, hass: HomeAssistant) -> None:
        with patch.object(ir, "async_create_issue") as m:
            rp.raise_datasheet_import_invalid(hass, EID, ["boom"])
            m.assert_called_once()
            assert m.call_args.kwargs["translation_placeholders"]["count"] == "1"

    def test_raise_import_invalid_empty_errors(self, hass: HomeAssistant) -> None:
        with patch.object(ir, "async_create_issue") as m:
            rp.raise_datasheet_import_invalid(hass, EID, [])
            m.assert_called_once()

    def test_clear_import_invalid_calls_delete(self, hass: HomeAssistant) -> None:
        with patch.object(ir, "async_delete_issue") as m:
            rp.clear_datasheet_import_invalid(hass, EID)
            m.assert_called_once()

    def test_raise_schema_unknown_placeholder(self, hass: HomeAssistant) -> None:
        with patch.object(ir, "async_create_issue") as m:
            rp.raise_datasheet_schema_unknown(hass, EID, 99)
            m.assert_called_once()
            assert m.call_args.kwargs["translation_placeholders"]["found"] == "99"

    def test_clear_schema_unknown_calls_delete(self, hass: HomeAssistant) -> None:
        with patch.object(ir, "async_delete_issue") as m:
            rp.clear_datasheet_schema_unknown(hass, EID)
            m.assert_called_once()

    def test_raise_load_failed_truncates(self, hass: HomeAssistant) -> None:
        with patch.object(ir, "async_create_issue") as m:
            rp.raise_datasheet_load_failed(hass, EID, "x" * 500)
            m.assert_called_once()
            assert len(m.call_args.kwargs["translation_placeholders"]["reason"]) <= 120

    def test_clear_load_failed(self, hass: HomeAssistant) -> None:
        with patch.object(ir, "async_delete_issue") as m:
            rp.clear_datasheet_load_failed(hass, EID)
            m.assert_called_once()


class TestServiceRegistration:
    async def test_all_new_services_registered(self, hass: HomeAssistant) -> None:
        await svc.async_register_services(hass)
        assert hass.services.has_service(DOMAIN, svc.SERVICE_IMPORT_DATASHEET)
        assert hass.services.has_service(DOMAIN, svc.SERVICE_REMOVE_USER_DATASHEET)

    async def test_registration_idempotent(self, hass: HomeAssistant) -> None:
        await svc.async_register_services(hass)
        await svc.async_register_services(hass)
        assert hass.services.has_service(DOMAIN, svc.SERVICE_IMPORT_DATASHEET)
