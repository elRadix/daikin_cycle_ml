"""C3b - coordinator integration: reload, sources, hp_specs attrs."""
from __future__ import annotations
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.daikin_cycle_ml.engine import model_datasheets as md
from custom_components.daikin_cycle_ml.engine.model_datasheets import (
    UserDatasheetError,
)

EID = "abcdef0123456789abcdef0123456789"


def _model() -> dict[str, Any]:
    return {
        "family": "EPRA", "kw": 4.0, "lwt_min": 25.0, "lwt_max": 55.0,
        "nom_cop": 4.6,
        "points": [{"label": "A7/W35", "t_out": 7.0, "t_lwc": 35.0, "cop": 4.6}],
    }


def _coord(entry_id: str = EID) -> Any:
    """Build a minimal coordinator-like object with just the datasheet fields."""
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
    )
    c = MagicMock(spec=DaikinCycleMLCoordinator)
    c.hass = MagicMock()
    c.entry = MagicMock()
    c.entry.entry_id = entry_id
    c._datasheet_cache = {}
    c._datasheet_merged = {}
    c._datasheet_user = {}
    c._datasheet_user_loaded = False
    c._datasheet_defaults = {}
    return c


class TestDatasheetSourcesProperty:
    def test_empty_when_merged_empty(self) -> None:
        from custom_components.daikin_cycle_ml.coordinator import (
            DaikinCycleMLCoordinator,
        )
        c = _coord()
        # use real property via class
        result = DaikinCycleMLCoordinator.datasheet_sources.fget(c)  # type: ignore[attr-defined]
        assert result == {}

    def test_bundled_only(self) -> None:
        from custom_components.daikin_cycle_ml.coordinator import (
            DaikinCycleMLCoordinator,
        )
        c = _coord()
        c._datasheet_merged = {
            "a": {"source": "bundled"},
            "b": {"source": "bundled"},
        }
        result = DaikinCycleMLCoordinator.datasheet_sources.fget(c)  # type: ignore[attr-defined]
        assert result == {"a": "bundled", "b": "bundled"}

    def test_mixed_sources(self) -> None:
        from custom_components.daikin_cycle_ml.coordinator import (
            DaikinCycleMLCoordinator,
        )
        c = _coord()
        c._datasheet_merged = {
            "epra04": {"source": "bundled"},
            "custom1": {"source": "user"},
        }
        result = DaikinCycleMLCoordinator.datasheet_sources.fget(c)  # type: ignore[attr-defined]
        assert result == {"epra04": "bundled", "custom1": "user"}

    def test_missing_source_defaults_bundled(self) -> None:
        from custom_components.daikin_cycle_ml.coordinator import (
            DaikinCycleMLCoordinator,
        )
        c = _coord()
        c._datasheet_merged = {"a": {}}
        result = DaikinCycleMLCoordinator.datasheet_sources.fget(c)  # type: ignore[attr-defined]
        assert result == {"a": "bundled"}

    def test_skips_non_dict_entries(self) -> None:
        from custom_components.daikin_cycle_ml.coordinator import (
            DaikinCycleMLCoordinator,
        )
        c = _coord()
        c._datasheet_merged = {"a": "bad", "b": {"source": "user"}}
        result = DaikinCycleMLCoordinator.datasheet_sources.fget(c)  # type: ignore[attr-defined]
        assert result == {"b": "user"}


class TestAsyncReloadUserDatasheets:
    async def test_reload_happy_path(self, hass: HomeAssistant) -> None:
        from custom_components.daikin_cycle_ml import coordinator as coord_mod
        from custom_components.daikin_cycle_ml.coordinator import (
            DaikinCycleMLCoordinator,
        )
        c = _coord()
        c.hass = hass
        user_models = {"my_hp": _model()}
        with patch.object(
            coord_mod, "_load_user_datasheets",
            new=AsyncMock(return_value=user_models),
        ), patch.object(
            coord_mod, "_load_bundled_datasheets",
            return_value={"epra04": _model()},
        ):
            await DaikinCycleMLCoordinator.async_reload_user_datasheets(c)
        assert c._datasheet_user == user_models
        assert "my_hp" in c._datasheet_merged
        assert "epra04" in c._datasheet_merged
        assert c._datasheet_user_loaded is True
        assert c._datasheet_cache == {}

    async def test_reload_propagates_user_error(self, hass: HomeAssistant) -> None:
        from custom_components.daikin_cycle_ml import coordinator as coord_mod
        from custom_components.daikin_cycle_ml.coordinator import (
            DaikinCycleMLCoordinator,
        )
        c = _coord()
        c.hass = hass
        with patch.object(
            coord_mod, "_load_user_datasheets",
            new=AsyncMock(side_effect=UserDatasheetError("boom")),
        ):
            with pytest.raises(UserDatasheetError):
                await DaikinCycleMLCoordinator.async_reload_user_datasheets(c)


class TestRefreshLazyLoadFallback:
    async def test_refresh_falls_back_on_user_error(
        self, hass: HomeAssistant
    ) -> None:
        from custom_components.daikin_cycle_ml.coordinator import (
            DaikinCycleMLCoordinator,
        )
        c = _coord()
        c.hass = hass
        c._datasheet_user_loaded = False
        c._datasheet_defaults = {}
        c.entry.data = {"model": "x"}
        with patch.object(
            c, "async_reload_user_datasheets",
            new=AsyncMock(side_effect=UserDatasheetError("boom")),
        ):
            await DaikinCycleMLCoordinator._refresh_datasheet_state(
                c, 1000.0, 40.0, 5.0, 3.5
            )
        assert c._datasheet_user_loaded is True
        assert c._datasheet_user == {}


class TestRefreshEarlyReturn:
    async def test_refresh_returns_early_on_non_positive_dt_live(self) -> None:
        """Cover the dT_live <= 0 guard in _refresh_datasheet_state."""
        from custom_components.daikin_cycle_ml.engine.model_datasheets import (
            load_bundled,
        )
        from custom_components.daikin_cycle_ml.coordinator import (
            DaikinCycleMLCoordinator,
        )
        coord = MagicMock()
        coord._datasheet_merged = load_bundled()
        coord._datasheet_user_loaded = True
        coord._datasheet_defaults = {}
        coord.entry.data = {"model": "erla11dav3"}
        coord._datasheet_cache = {}
        # lwt + 5 >= t_out - 8 forces dT_live <= 0
        await DaikinCycleMLCoordinator._refresh_datasheet_state(
            coord, 1000.0, 60.0, 80.0, 3.5
        )
        cache = coord._datasheet_cache
        assert cache["cop_normalized_a7w35"] is None
        assert cache["cop_vs_datasheet_pct"] is None
        assert cache["datasheet"] is not None


class TestAttrsHpSpecs:
    def test_includes_datasheet_sources(self) -> None:
        from custom_components.daikin_cycle_ml.sensor import _attrs_hp_specs
        s = MagicMock()
        s.datasheet = {"model": "epra04", "source": "bundled", "points": []}
        s.datasheet_model = "epra04"
        c = MagicMock()
        c.datasheet_sources = {"epra04": "bundled", "my_hp": "user"}
        out = _attrs_hp_specs(s, c)
        assert out["datasheet_sources"] == {"epra04": "bundled", "my_hp": "user"}
        assert out["configured"] is True

    def test_no_datasheet_still_calls_sources(self) -> None:
        from custom_components.daikin_cycle_ml.sensor import _attrs_hp_specs
        s = MagicMock()
        s.datasheet = None
        s.datasheet_model = "unknown"
        c = MagicMock()
        # "reason" branch returns early - datasheet_sources not required here
        out = _attrs_hp_specs(s, c)
        assert out["configured"] is False
