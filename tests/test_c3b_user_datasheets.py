"""C3b — user datasheet Store API (validate, load, save, remove)."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.daikin_cycle_ml.engine import model_datasheets as md
from homeassistant.core import HomeAssistant


def _valid_model() -> dict[str, Any]:
    return {
        "family": "EPRA",
        "kw": 4.0,
        "lwt_min": 25.0,
        "lwt_max": 55.0,
        "nom_cop": 4.6,
        "points": [
            {"label": "A7/W35", "t_out": 7.0, "t_lwc": 35.0, "cop": 4.6}
        ],
    }


def _payload(models: dict[str, Any], schema: int = 1) -> dict[str, Any]:
    return {"schema_version": schema, "models": models}


class TestValidateUserPayload:
    def test_valid(self) -> None:
        clean, errs = md.validate_user_payload(_payload({"x": _valid_model()}))
        assert errs == []
        assert "x" in clean

    def test_root_not_dict(self) -> None:
        clean, errs = md.validate_user_payload("nope")
        assert clean == {}
        assert "root" in errs[0]

    def test_schema_mismatch(self) -> None:
        clean, errs = md.validate_user_payload(_payload({}, schema=2))
        assert clean == {}
        assert any("schema_version" in e for e in errs)

    def test_models_not_dict(self) -> None:
        clean, errs = md.validate_user_payload(
            {"schema_version": 1, "models": []}
        )
        assert clean == {}
        assert "models" in errs[0]

    def test_invalid_model_collects_errors(self) -> None:
        clean, errs = md.validate_user_payload(
            _payload({"bad": {"family": "X"}})
        )
        assert "bad" not in clean
        assert any("missing" in e for e in errs)

    def test_partial_validity(self) -> None:
        clean, errs = md.validate_user_payload(
            _payload({"ok": _valid_model(), "bad": {"family": "X"}})
        )
        assert "ok" in clean and "bad" not in clean
        assert len(errs) >= 1

    def test_parse_user_payload_backward_compat(self) -> None:
        out = md.parse_user_payload(_payload({"x": _valid_model()}))
        assert "x" in out


class TestStoreRoundtrip:
    async def test_load_missing_returns_empty(self, hass: HomeAssistant) -> None:
        assert await md.load_user(hass, "entry1") == {}

    async def test_save_and_load(self, hass: HomeAssistant) -> None:
        models = {"x": _valid_model()}
        await md.save_user(hass, "entry1", models)
        assert await md.load_user(hass, "entry1") == models

    async def test_save_overwrites(self, hass: HomeAssistant) -> None:
        await md.save_user(hass, "e", {"a": _valid_model()})
        await md.save_user(hass, "e", {"b": _valid_model()})
        got = await md.load_user(hass, "e")
        assert set(got.keys()) == {"b"}

    async def test_entry_isolation(self, hass: HomeAssistant) -> None:
        await md.save_user(hass, "e1", {"a": _valid_model()})
        await md.save_user(hass, "e2", {"b": _valid_model()})
        assert set((await md.load_user(hass, "e1")).keys()) == {"a"}
        assert set((await md.load_user(hass, "e2")).keys()) == {"b"}


class TestRemoveUserModel:
    async def test_remove_existing(self, hass: HomeAssistant) -> None:
        await md.save_user(
            hass, "e", {"a": _valid_model(), "b": _valid_model()}
        )
        assert await md.remove_user_model(hass, "e", "a") is True
        assert set((await md.load_user(hass, "e")).keys()) == {"b"}

    async def test_remove_missing_returns_false(
        self, hass: HomeAssistant
    ) -> None:
        await md.save_user(hass, "e", {"a": _valid_model()})
        assert await md.remove_user_model(hass, "e", "z") is False

    async def test_remove_on_empty_store(self, hass: HomeAssistant) -> None:
        assert await md.remove_user_model(hass, "e", "a") is False


class TestStoreCorruption:
    async def test_wrong_version_raises(self, hass: HomeAssistant) -> None:
        store = md._store(hass, "e")
        await store.async_save({"version": 99, "models": {}})
        with pytest.raises(md.UserDatasheetError, match="version"):
            await md.load_user(hass, "e")

    async def test_non_dict_payload_raises(self, hass: HomeAssistant) -> None:
        store = md._store(hass, "e")
        # deliberately corrupt: list instead of dict
        await store.async_save(["nope"])  # type: ignore[arg-type]
        with pytest.raises(md.UserDatasheetError, match="not dict"):
            await md.load_user(hass, "e")

    async def test_models_not_dict_raises(self, hass: HomeAssistant) -> None:
        store = md._store(hass, "e")
        await store.async_save({"version": 1, "models": []})
        with pytest.raises(md.UserDatasheetError, match="models not dict"):
            await md.load_user(hass, "e")

class TestStoreLoadFailure:
    async def test_load_raises_on_store_failure(
        self, hass: HomeAssistant
    ) -> None:
        """Cover except branch: Store.async_load raises -> UserDatasheetError."""
        failing = MagicMock()
        failing.async_load = AsyncMock(side_effect=RuntimeError("boom"))
        with patch.object(md, "_store", return_value=failing):
            with pytest.raises(md.UserDatasheetError, match="store load failed"):
                await md.load_user(hass, "e")

