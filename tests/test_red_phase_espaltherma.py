"""RED-phase tests: written BEFORE final fix to prove each gap exists.

R594: these tests must FAIL on current code. If any pass, STOP - the test
assumption is wrong, not the production code.

Each test targets a specific branch that the current implementation may skip.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator


def _mk_coord(**kwargs: Any) -> DaikinCycleMLCoordinator:
    coord = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    hass = MagicMock()
    hass.states.get.return_value = None
    coord.hass = hass
    coord.power_sensor = kwargs.get("power_sensor")
    coord.cop_sensor_entity = kwargs.get("cop_sensor")
    coord.options = {"supply_phases": 1}
    coord.data = MagicMock()
    coord.data.mode = "heating"
    return coord


BASE_ATTRS = {
    "Operation Mode": "Heating",
    "R1T-Outdoor air temp.": 8.5,
    "INV primary current (A)": 3.1,
    "INV frequency (rps)": 30,
    "Leaving water temp. before BUH (R1T)": 30.6,
    "Inlet water temp.(R4T)": 26.0,
    "Flow sensor (l/min)": 17.4,
    "BUH Step1": "OFF",
    "BUH Step2": "OFF",
}


class TestBoundaryThreshold:
    """R641: thermal_kw <= 0 threshold at 3 boundaries (ε-, boundary, ε+)."""

    def _make_power_meter(self):
        """Helper: mock a Shelly meter returning 800 W."""
        coord = _mk_coord(power_sensor="sensor.shelly")
        coord.hass.states.get.return_value = SimpleNamespace(
            state="800", attributes={"unit_of_measurement": "W"}
        )
        return coord

    def test_boundary_thermal_kw_epsilon_below_zero(self):
        """ε-: thermal_kw = -0.01 -> must fall back to V1 (per bug fix)."""
        coord = self._make_power_meter()
        attrs = dict(BASE_ATTRS, **{"Stats: Heat output (kW)": "-0.01"})
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        assert src == "computed_power_meter", f"expected V1 fallback, got {src}"
        assert cop is not None

    def test_boundary_thermal_kw_exactly_zero(self):
        """boundary: thermal_kw = 0.0 -> must fall back to V1."""
        coord = self._make_power_meter()
        attrs = dict(BASE_ATTRS, **{"Stats: Heat output (kW)": "0.0"})
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        assert src == "computed_power_meter", f"expected V1 fallback, got {src}"
        assert cop is not None

    def test_boundary_thermal_kw_epsilon_above_zero(self):
        """ε+: thermal_kw = 0.01 -> must use ESP32 heat output.

        v1.20.0 #281: source tag now reflects thermal source (ESP32)
        rather than only power source; _read_cop_effective returns
        'espaltherma_heat_output' when v2 heat was consumed.
        """
        coord = self._make_power_meter()
        attrs = dict(BASE_ATTRS, **{"Stats: Heat output (kW)": "0.01"})
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        assert src == "espaltherma_heat_output"
        # Verify: thermal_kw used is 0.01 (ESP32), not computed from Δt (5.58)
        assert cop is not None
        assert cop < 1.0, f"COP should reflect 0.01kW heat / 0.8kW power < 0.02, got {cop}"


class TestParseFailureBranches:
    """R635: every input type that fails float() must trigger graceful fallback."""

    @pytest.mark.parametrize("bad_value", [
        "invalid_data",     # non-numeric string
        "",                 # empty string
        None,               # None (missing treated as absent)
        [],                 # list (unparseable)
        {"key": "val"},     # dict (unparseable)
    ])
    def test_bad_heat_output_falls_back(self, bad_value):
        """Any unparseable Heat output -> V1 fallback, not 'no_thermal'."""
        coord = _mk_coord(power_sensor="sensor.shelly")
        coord.hass.states.get.return_value = SimpleNamespace(
            state="800", attributes={"unit_of_measurement": "W"}
        )
        attrs = dict(BASE_ATTRS, **{"Stats: Heat output (kW)": bad_value})
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        assert src == "computed_power_meter", f"bad_value={bad_value!r} -> {src}"
        assert cop is not None


class TestFullChain:
    """R639: end-to-end from _read_cop_effective through the full cascade."""

    def test_full_chain_esp_v2_with_meter(self):
        """No mocks between coordinator layers: attrs flow through all methods."""
        coord = _mk_coord(power_sensor="sensor.shelly")
        coord.hass.states.get.return_value = SimpleNamespace(
            state="810", attributes={"unit_of_measurement": "W"}
        )
        attrs = dict(BASE_ATTRS, **{
            "Stats: Heat output (kW)": "5.45",
            "Stats: Electrical input estimated (kW)": "0.81",
        })
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        # Cascade: no COP sensor -> meter (Shelly) -> ESP32 heat output (5.45)
        # Expected COP: 5.45kW / 0.810kW = 6.728
        # v1.20.0 #281: tag reflects thermal source (ESP32), not just power.
        assert src == "espaltherma_heat_output"
        assert pytest.approx(cop, abs=0.01) == 6.7284
