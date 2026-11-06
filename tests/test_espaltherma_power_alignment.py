"""R634, R639, R641: Real-world reproduction and matrix tests for ESPAltherma v2 alignment."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator

# Real production data from 2026-11-06 15:17:45
REAL_ATTRS = {
    "Operation Mode": "Heating",
    "Defrost Operation": "OFF",
    "R1T-Outdoor air temp.": 8.5,
    "INV primary current (A)": 3.1,
    "INV frequency (rps)": 30,
    "Water pump operation": "ON",
    "Leaving water temp. before BUH (R1T)": 30.6,
    "Leaving water temp. after BUH (R2T)": 30.5,
    "Inlet water temp.(R4T)": 26.0,
    "Flow sensor (l/min)": 17.4,
    "BUH Step1": "OFF",
    "BUH Step2": "OFF",
    "Stats: Heat output (kW)": 5.45,
    "Stats: Electrical input estimated (kW)": 0.81,
}

REAL_POWER_W = 802.42
REAL_COP_SENSOR = 6.41


def _mk_coord(
    *, power_sensor: str | None = None, cop_sensor: str | None = None
) -> DaikinCycleMLCoordinator:
    """Builds a minimal coordinator with the required dependencies mocked."""
    coord = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)

    # Mock Home Assistant state machine
    hass = MagicMock()
    def mock_get_state(entity_id: str) -> Any:
        if entity_id == power_sensor:
            return SimpleNamespace(state=str(REAL_POWER_W), attributes={"unit_of_measurement": "W"})
        if entity_id == cop_sensor:
            return SimpleNamespace(state=str(REAL_COP_SENSOR), attributes={})
        return None
    hass.states.get.side_effect = mock_get_state

    coord.hass = hass
    coord.power_sensor = power_sensor
    coord.cop_sensor_entity = cop_sensor
    coord.options = {"supply_phases": 1}
    coord.data = MagicMock()
    coord.data.mode = "heating"
    return coord


@pytest.mark.parametrize(
    "label, cop_sensor, power_sensor, attrs, expected_src, expected_cop",
    [
        # 1. Gold Standard: Own COP sensor
        ("own_cop", "sensor.my_cop", "sensor.power", REAL_ATTRS, "cop_sensor", REAL_COP_SENSOR),

        # 2. Power Meter + ESP v2 Heat (uses Shelly + 5.45 kW)
        ("meter_esp_v2", None, "sensor.power", REAL_ATTRS, "computed_power_meter", round(5.45 * 1000 / REAL_POWER_W, 4)),

        # 3. Power Meter + ESP v1 Fallback (no Stats)
        ("meter_esp_v1", None, "sensor.power", {k: v for k, v in REAL_ATTRS.items() if not k.startswith("Stats:")}, "computed_power_meter", 6.9595),

        # 4. No Meter + ESP v2 (uses ESP32 Heat / ESP32 Elec)
        ("no_meter_esp_v2", None, None, REAL_ATTRS, "computed_espaltherma_v2_stats", round(5.45 / 0.81, 4)),

        # 5. No Meter + ESP v1 Fallback (uses Integration Heat / Inverter Elec)
        ("no_meter_esp_v1", None, None, {k: v for k, v in REAL_ATTRS.items() if not k.startswith("Stats:")}, "computed_inverter_estimated_v1", 6.8689),
    ]
)
def test_cop_cascade_matrix(
    label: str, cop_sensor: str | None, power_sensor: str | None,
    attrs: dict[str, Any], expected_src: str, expected_cop: float
) -> None:
    """R641: Factor matrix testing all user combinations."""
    coord = _mk_coord(power_sensor=power_sensor, cop_sensor=cop_sensor)

    cop, src = coord._read_cop_effective(now=1793974396.849187, attrs=attrs)

    assert cop is not None, f"Test {label}: returned None"
    assert src == expected_src, f"Test {label}: expected src {expected_src}, got {src}"
    assert pytest.approx(cop, abs=0.01) == expected_cop, f"Test {label}: expected {expected_cop}, got {cop}"


def test_invalid_heat_output_falls_back_to_v1() -> None:
    """R634: If ESP32 publishes invalid heat, fallback to integration calculation."""
    bad_attrs = dict(REAL_ATTRS)
    bad_attrs["Stats: Heat output (kW)"] = "invalid_data"

    coord = _mk_coord(power_sensor="sensor.power")
    cop, src = coord._read_cop_effective(now=1793974396.849187, attrs=bad_attrs)

    assert src == "computed_power_meter"
    assert pytest.approx(cop, abs=0.01) == 6.9595
