"""R640: Fuzz test for `float(raw_heat)` parse path in _read_cop_effective.

Strategy: 200 random values for 'Stats: Heat output (kW)'.
Invariant (R552): the coordinator must NEVER return NaN/inf/negative COP.
"""
from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator

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


def _mk_coord() -> DaikinCycleMLCoordinator:
    coord = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    hass = MagicMock()
    hass.states.get.return_value = SimpleNamespace(
        state="800", attributes={"unit_of_measurement": "W"}
    )
    coord.hass = hass
    coord.power_sensor = "sensor.shelly"
    coord.cop_sensor_entity = None
    coord.options = {"supply_phases": 1}
    coord.data = MagicMock()
    coord.data.mode = "heating"
    return coord


@given(raw=st.one_of(
    st.text(min_size=0, max_size=20),
    st.floats(allow_nan=True, allow_infinity=True),
    st.integers(min_value=-1000, max_value=1000),
    st.none(),
    st.lists(st.integers()),
))
@settings(max_examples=200, deadline=None)
def test_fuzz_heat_output_never_returns_invalid_cop(raw: Any) -> None:
    """R640 + R552: 200 random inputs must never produce NaN/inf/negative COP."""
    coord = _mk_coord()
    attrs = dict(BASE_ATTRS, **{"Stats: Heat output (kW)": raw})
    # Must never raise
    cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
    # src is always a string
    assert isinstance(src, str)
    # If cop returned, it MUST be finite and positive
    if cop is not None:
        assert isinstance(cop, (int, float))
        assert math.isfinite(cop), f"COP={cop} is not finite (raw={raw!r})"
        assert cop > 0, f"COP={cop} is not positive (raw={raw!r})"


@given(raw=st.floats(min_value=-10.0, max_value=50.0))
@settings(max_examples=100, deadline=None)
def test_fuzz_heat_output_positive_matches_expected_esp32_path(raw: float) -> None:
    """R640 + R641: positive finite heat → ESP32 thermal path (verified via COP math).

    When raw > 0 (finite), the ESP32 thermal is used (not V1 fallback).
    COP should equal raw / power_w_kW = raw / 0.8, unless it exceeds MAX_COP.
    """
    if not math.isfinite(raw):
        return  # Skip non-finite; covered by test 1
    coord = _mk_coord()
    attrs = dict(BASE_ATTRS, **{"Stats: Heat output (kW)": str(raw)})
    from custom_components.daikin_cycle_ml.const import MAX_COP
    cop, src = coord._read_cop_effective(now=0.0, attrs=attrs)
    if raw <= 0:
        # V1 fallback: expected cop ~6.96 (thermal 5.58kW / power 0.8kW)
        assert cop is not None, f"raw={raw}: expected V1 cop, got None (src={src})"
        assert 6.5 < cop < 7.5, f"raw={raw}: expected ~6.96, got {cop}"
        assert src == "computed_power_meter"
    else:
        expected = raw * 1000.0 / 800.0
        if expected > MAX_COP:
            # Above MAX_COP -> reject
            assert cop is None, f"raw={raw}: expected rejection (COP>{MAX_COP}), got {cop}"
            assert src == "cop_out_of_range", (
                f"raw={raw}: expected cop_out_of_range, got {src}"
            )
        elif round(expected, 4) <= 0:
            # Below rounding granularity: round(cop, 4)=0.0 -> rejected by R643
            # guard (data integrity: 0.0 COP is nonsensical)
            assert cop is None, (
                f"raw={raw}: expected round-to-zero rejection, got {cop}"
            )
            assert src == "cop_out_of_range", (
                f"raw={raw}: expected cop_out_of_range, got {src}"
            )
        else:
            # Normal ESP32 path: cop = raw / 0.8, positive finite
            # abs tolerance = 0.0001 (2x rounding granularity of round(cop, 4))
            assert cop is not None, (
                f"raw={raw}: expected ESP32 cop {expected}, got None (src={src})"
            )
            assert abs(cop - expected) < 0.0001, (
                f"raw={raw}: expected {expected}, got {cop} (abs diff {abs(cop-expected):.2e})"
            )
            # v1.20.0 #281: v2 heat pad -> tag reflects ESP32 thermal source.
            assert src == "espaltherma_heat_output"
