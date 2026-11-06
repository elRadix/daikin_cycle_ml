"""R272 RED phase: defrost + unknown state must skip COP computation.

Must FAIL on current code. After fix, must PASS.
"""
from __future__ import annotations
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator


BASE_ATTRS: dict[str, Any] = {
    "Operation Mode": "Heating",
    "Defrost Operation": "OFF",
    "R1T-Outdoor air temp.": 8.5,
    "INV frequency (rps)": 30,
    "Leaving water temp. before BUH (R1T)": 30.6,
    "Inlet water temp.(R4T)": 26.0,
    "Flow sensor (l/min)": 17.4,
    "BUH Step1": "OFF",
    "BUH Step2": "OFF",
    "Stats: Heat output (kW)": "5.45",
}


def _mk_coord(*, user_cop: str | None = None) -> DaikinCycleMLCoordinator:
    coord = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    hass = MagicMock()
    def _get(eid: str) -> Any:
        if eid == user_cop:
            return SimpleNamespace(state="3.5", attributes={})
        return SimpleNamespace(
            state="800", attributes={"unit_of_measurement": "W"}
        )
    hass.states.get.side_effect = _get
    coord.hass = hass
    coord.power_sensor = "sensor.shelly"
    coord.cop_sensor_entity = user_cop
    coord.options = {"supply_phases": 1}
    coord.data = MagicMock()
    coord.data.mode = "heating"
    return coord


class TestDefrostGate:
    def test_defrost_uppercase_skips(self) -> None:
        attrs = dict(BASE_ATTRS, **{"Defrost Operation": "ON"})
        coord = _mk_coord()
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        assert cop is None, f"expected None during defrost, got {cop}"
        assert src == "defrost_active", f"expected 'defrost_active', got {src}"

    def test_defrost_lowercase_skips(self) -> None:
        attrs = dict(BASE_ATTRS, **{"Defrost Operation": "on"})
        coord = _mk_coord()
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        assert cop is None
        assert src == "defrost_active"

    def test_defrost_bool_true_skips(self) -> None:
        attrs = dict(BASE_ATTRS, **{"Defrost Operation": True})
        coord = _mk_coord()
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        assert cop is None
        assert src == "defrost_active"

    def test_defrost_does_not_override_user_cop_sensor(self) -> None:
        """User's own COP sensor is authoritative — even during defrost."""
        attrs = dict(BASE_ATTRS, **{"Defrost Operation": "ON"})
        coord = _mk_coord(user_cop="sensor.my_cop")
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        assert cop == 3.5
        assert src == "cop_sensor"


class TestUnknownHeatOutput:
    def test_unknown_heat_skips(self) -> None:
        attrs = dict(BASE_ATTRS, **{"Stats: Heat output (kW)": "unknown"})
        coord = _mk_coord()
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        assert cop is None, f"'unknown' should skip, got {cop}"
        assert src == "heat_unknown", f"got {src}"

    def test_unavailable_heat_skips(self) -> None:
        attrs = dict(BASE_ATTRS, **{"Stats: Heat output (kW)": "unavailable"})
        coord = _mk_coord()
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        assert cop is None
        assert src == "heat_unknown"

    def test_invalid_data_still_falls_back_to_v1(self) -> None:
        """R273 guard: 'invalid_data' must still V1-fallback (not 'heat_unknown')."""
        attrs = dict(BASE_ATTRS, **{"Stats: Heat output (kW)": "invalid_data"})
        coord = _mk_coord()
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        assert cop is not None
        assert src == "computed_power_meter"

    def test_null_heat_still_falls_back_to_v1(self) -> None:
        """None heat output must NOT trigger 'heat_unknown'."""
        attrs = dict(BASE_ATTRS)
        attrs.pop("Stats: Heat output (kW)")
        coord = _mk_coord()
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        assert cop is not None
        assert src == "computed_power_meter"
