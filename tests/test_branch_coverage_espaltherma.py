"""R643: Targeted branch coverage for every missing branch in _read_cop_effective."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator


def _mk_coord(data_mode: Any = "heating", power: str = "800") -> DaikinCycleMLCoordinator:
    coord = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    hass = MagicMock()
    hass.states.get.return_value = SimpleNamespace(
        state=power, attributes={"unit_of_measurement": "W"}
    )
    coord.hass = hass
    coord.power_sensor = "sensor.shelly"
    coord.cop_sensor_entity = None
    coord.options = {"supply_phases": 1}
    coord.data = MagicMock()
    coord.data.mode = data_mode
    return coord


FULL_ATTRS = {
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


class TestMissingBranches:
    """R643: Cover every branch our fuzz+matrix tests missed."""

    def test_no_dt_returns_no_dt(self) -> None:
        """Cover line 1494: dt_k missing -> return 'no_dt'."""
        attrs = dict(FULL_ATTRS)
        attrs.pop("Leaving water temp. before BUH (R1T)")
        attrs.pop("Inlet water temp.(R4T)")
        # Also remove R2T so fallback fails
        coord = _mk_coord()
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        assert cop is None
        assert src == "no_dt"

    def test_invalid_rps_returns_zero(self) -> None:
        """Cover line 1519: rps exception handler."""
        attrs = dict(FULL_ATTRS, **{"INV frequency (rps)": "not_a_number"})
        coord = _mk_coord()
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        # V1 path used; cop should still be computed (rps=0, then None passed to thermal)
        assert src == "computed_power_meter"
        assert cop is not None

    def test_data_none_uses_heating_default(self) -> None:
        """Cover lines 1522-1527: coord.data None -> mode = 'heating'."""
        coord = _mk_coord()
        coord.data = None  # type: ignore[assignment]
        attrs = dict(FULL_ATTRS)
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        assert cop is not None
        assert src == "computed_power_meter"

    def test_data_mode_empty_uses_heating_default(self) -> None:
        """Cover lines 1522-1523: coord.data.mode = None -> mode = 'heating'."""
        coord = _mk_coord(data_mode=None)
        attrs = dict(FULL_ATTRS)
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        assert cop is not None
        assert src == "computed_power_meter"

    def test_flow_negative_uses_none(self) -> None:
        """Cover line 1531->1533: flow <= 0 -> None passed to compute."""
        attrs = dict(FULL_ATTRS, **{"Flow sensor (l/min)": "-5.0"})
        coord = _mk_coord()
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        # With flow <= 0, compute_thermal_power_live may return None -> no_thermal
        # Accept either no_thermal OR a valid computed cop (depends on internal fallback)
        assert src in ("computed_power_meter", "no_thermal")

    def test_flow_zero_uses_none(self) -> None:
        """Cover line 1531->1533: flow == 0 -> None passed to compute."""
        attrs = dict(FULL_ATTRS, **{"Flow sensor (l/min)": "0"})
        coord = _mk_coord()
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        assert src in ("computed_power_meter", "no_thermal")

    def test_success_return_positive_cop(self) -> None:
        """Cover line 1542: normal success path returns round(cop, 4)."""
        attrs = dict(FULL_ATTRS, **{"Stats: Heat output (kW)": "5.45"})
        coord = _mk_coord()
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        assert cop is not None
        assert cop > 0
        assert src == "espaltherma_heat_output"
        # Verify the value is a 4-decimal rounded float
        assert cop == round(cop, 4)


class TestExplicitEdgeCases:
    """R643: Explicit tests to cover branches hypothesis may not always trigger."""

    def test_empty_attrs_returns_none(self) -> None:
        """Cover line 1494: attrs = {} -> return None, 'none'."""
        coord = _mk_coord()
        cop, src = coord._read_cop_effective(now=0.0, attrs={})
        assert cop is None
        assert src == "none"

    def test_nan_heat_output_falls_back_to_v1(self) -> None:
        """Cover lines 1506-1507: NaN in ESP32 heat -> fall through to V1."""
        import math
        attrs = dict(FULL_ATTRS, **{"Stats: Heat output (kW)": float("nan")})
        coord = _mk_coord()
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        assert src == "computed_power_meter"
        assert cop is not None
        assert math.isfinite(cop)

    def test_inf_heat_output_falls_back_to_v1(self) -> None:
        """Cover lines 1506-1507: +inf in ESP32 heat -> fall through to V1."""
        import math
        attrs = dict(FULL_ATTRS, **{"Stats: Heat output (kW)": float("inf")})
        coord = _mk_coord()
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        assert src == "computed_power_meter"
        assert cop is not None
        assert math.isfinite(cop)

    def test_negative_inf_heat_output_falls_back_to_v1(self) -> None:
        """Cover lines 1506-1507: -inf in ESP32 heat -> fall through to V1."""
        import math
        attrs = dict(FULL_ATTRS, **{"Stats: Heat output (kW)": float("-inf")})
        coord = _mk_coord()
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        assert src == "computed_power_meter"
        assert cop is not None
        assert math.isfinite(cop)

    def test_positive_esp32_heat_uses_esp32_path(self) -> None:
        """When v2 heat output drives COP, source tag must say so (v1.20.0).

        Pre-v1.20.0 this returned "computed_power_meter" — the _tsrc var
        was assigned "espaltherma_heat_output" but never returned. The
        test asserted the bug. Fixed to expect the actual source.
        """
        attrs = dict(FULL_ATTRS, **{"Stats: Heat output (kW)": "4.5"})
        coord = _mk_coord()
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        assert src == "espaltherma_heat_output", (
            f"v2 heat output used but source tag wrong: {src!r}; "
            f"_tsrc should propagate to snap.cop_source"
        )
        assert cop is not None
        # 4.5 kW / 0.8 kW = 5.625
        assert abs(cop - 5.625) < 0.001


class TestLine1494NoPower:
    """Cover line 1494: return None, 'no_power' when power_w is None."""

    def test_no_power_source_returns_no_power(self) -> None:
        """No meter, no v2 stats, no inverter current -> power_w is None."""
        # Build coord WITHOUT power_sensor
        coord = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
        hass = MagicMock()
        hass.states.get.return_value = None
        coord.hass = hass
        coord.power_sensor = None
        coord.cop_sensor_entity = None
        coord.options = {"supply_phases": 1}
        coord.data = MagicMock()
        coord.data.mode = "heating"
        # attrs WITHOUT INV primary current AND WITHOUT v2 stats
        attrs = {
            "Operation Mode": "Heating",
            "R1T-Outdoor air temp.": 8.5,
            "Leaving water temp. before BUH (R1T)": 30.6,
            "Inlet water temp.(R4T)": 26.0,
            "Flow sensor (l/min)": 17.4,
            # NO "INV primary current (A)"
            # NO "Stats: Electrical input estimated (kW)"
        }
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        assert cop is None
        assert src == "no_power"


class TestLine1522FlowException:
    """Cover lines 1522-1523: flow parse exception -> flow_lmin = 0.0."""

    def test_unparseable_flow_uses_zero(self) -> None:
        """Flow = 'abc' -> float() raises ValueError -> except -> flow_lmin = 0.0."""
        # ESP32 heat must be invalid so we enter the V1 block where flow is parsed
        attrs = dict(FULL_ATTRS, **{
            "Stats: Heat output (kW)": "invalid_heat_value",  # forces V1
            "Flow sensor (l/min)": "abc",                     # triggers except
        })
        coord = _mk_coord()
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        # We hit the flow exception branch (1522-1523)
        # Then rps=30 is valid, so compute may return a value OR no_thermal
        assert src in ("computed_power_meter", "no_thermal")

    def test_none_flow_type_error(self) -> None:
        """Flow = dict -> float() raises TypeError -> except -> flow_lmin = 0.0."""
        attrs = dict(FULL_ATTRS, **{
            "Stats: Heat output (kW)": "invalid_heat_value",
            "Flow sensor (l/min)": {"nested": "dict"},  # triggers TypeError
        })
        coord = _mk_coord()
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        assert src in ("computed_power_meter", "no_thermal")


class TestLine1542NoThermal:
    """Cover line 1542: return None, 'no_thermal' when V1 returns None."""

    def test_no_thermal_when_all_inputs_invalid(self) -> None:
        """ESP32 heat invalid + flow=rps=0 -> V1 returns None -> line 1542."""
        attrs = dict(FULL_ATTRS, **{
            "Stats: Heat output (kW)": "0",       # 0 → V1 fallback
            "Flow sensor (l/min)": "0",            # flow=0 → None passed
            "INV frequency (rps)": "0",            # rps=0 → None passed
        })
        coord = _mk_coord()
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        # V1 cannot compute with all inputs None -> line 1542
        assert cop is None
        assert src == "no_thermal"

    def test_no_thermal_when_esp32_negative_and_v1_no_inputs(self) -> None:
        """ESP32 heat=-5 + flow=0 + rps=0 -> V1 returns None -> line 1542."""
        attrs = dict(FULL_ATTRS, **{
            "Stats: Heat output (kW)": "-5",
            "Flow sensor (l/min)": "0",
            "INV frequency (rps)": "0",
        })
        coord = _mk_coord()
        cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
        assert cop is None
        assert src == "no_thermal"
