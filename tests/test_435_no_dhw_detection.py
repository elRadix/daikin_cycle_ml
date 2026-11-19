"""#435: a unit without DHW tank (no 3-way valve) must still detect cycles.

Fixture = the monolithic source of the #435 reporter (EHBX08EF6V +
ERGA06EAV3, wall-mounted, no tank, ESPAltherma v1 definition), copied
from the attached diagnostics. Before #435 the missing 3-way valve was a
required label: the #109 freeze guard returned before detection on every
tick, so the compressor at 16 rps read as off and every sensor stayed
unknown.
"""

from __future__ import annotations

from custom_components.daikin_cycle_ml.const import (
    ATTR_3WAY_VALVE,
    ATTR_BUH_STEP1,
    ATTR_BUH_STEP2,
    ATTR_INV_FREQUENCY_RPS,
    CORE_ATTRIBUTES,
    DETECTION_CRITICAL_ATTRIBUTES,
    DOMAIN,
    MODEL_BASISPROFIEL,
    REQUIRED_ATTRIBUTES,
    STRUCTURALLY_OPTIONAL_ATTRIBUTES,
)
from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    _detection_blocked,
)
from custom_components.daikin_cycle_ml.engine.attribute_reader import (
    missing_required,
)

SRC = "sensor.althermasensors"

# #435 reporter, diagnostics 2026-11-19 19:25 (v1.24.1)
ATTRS_435 = {
    "Operation Mode": "Heating",
    "Defrost Operation": "OFF",
    "Error Code": " 0",
    "Target Evap. Temp.": 47.5,
    "Target Cond. Temp.": 0,
    "Outdoor air temp.(R1T)": 10,
    "Discharge pipe temp.": 42.5,
    "INV primary current (A)": 1.3,
    "INV secondary current (A)": 7.4,
    "Voltage (N-phase) (V)": 145,
    "INV frequency (rps)": 16,
    "INV frequency 2 (rps)": 67,
    "Fan 1 (step)": 8,
    "Fan 2 (step)": 67,
    "I/U operation mode": "Heating",
    "Thermostat ON/OFF": "ON",
    "Freeze Protection": "OFF",
    "Silent Mode": "OFF",
    "LW setpoint (main)": 30.2,
    "BUH Step1": "OFF",
    "BUH Step2": "OFF",
    "Water pump operation": "ON",
    "Leaving water temp. before BUH (R1T)": 31.8,
    "Leaving water temp. after BUH (R2T)": 32.3,
    "Refrig. Temp. liquid side (R3T)": 30.8,
    "Inlet water temp.(R4T)": 28.1,
    "Indoor ambient temp. (R1T)": 20,
    "LW setpoint (add)": 38,
    "RT setpoint": 20,
    "Flow sensor (l/min)": 7.1,
    "Water pressure": 2,
    "Water pump signal (0:max-100:stop)": 72,
    "WifiRSSI": "-57dBm",
}


def _entry(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "source_type": "monolithic",
            "source_sensor": SRC,
            "attribute_mode": "auto",
            "model": MODEL_BASISPROFIEL,
        },
        options={},
    )
    entry.add_to_hass(hass)
    return entry


def test_3way_valve_is_structurally_optional():
    assert ATTR_3WAY_VALVE in CORE_ATTRIBUTES
    assert ATTR_3WAY_VALVE in STRUCTURALLY_OPTIONAL_ATTRIBUTES
    assert ATTR_3WAY_VALVE not in REQUIRED_ATTRIBUTES
    assert missing_required(ATTRS_435) == []


def test_detection_critical_excludes_buh_steps():
    assert ATTR_BUH_STEP1 not in DETECTION_CRITICAL_ATTRIBUTES
    assert ATTR_BUH_STEP2 not in DETECTION_CRITICAL_ATTRIBUTES
    assert set(DETECTION_CRITICAL_ATTRIBUTES) <= set(REQUIRED_ATTRIBUTES)
    assert _detection_blocked([]) is False
    # a model without backup heater keeps detecting
    assert _detection_blocked([ATTR_BUH_STEP1, ATTR_BUH_STEP2]) is False
    # the #109 guard still holds for a partial publish
    assert _detection_blocked(["Water pump operation"]) is True


async def test_435_unit_without_dhw_detects_heating_run(hass):
    coord = DaikinCycleMLCoordinator(hass, _entry(hass))
    hass.states.async_set(SRC, "unknown", ATTRS_435)
    data = await coord._async_update_data()
    assert data.missing_attrs == []
    assert coord.detector.state == "running"
    assert data.state == "running"
    assert data.mode == "heating"
    assert data.cycle_start_ts > 0
    # DHW resolved from the source: no valve, no tank sensor -> no DHW
    assert coord.dhw_present is False
    assert coord._dhw_present_source == "tier4_default"


async def test_435_unit_without_buh_steps_detects(hass):
    attrs = {
        k: v for k, v in ATTRS_435.items()
        if k not in (ATTR_BUH_STEP1, ATTR_BUH_STEP2)
    }
    coord = DaikinCycleMLCoordinator(hass, _entry(hass))
    hass.states.async_set(SRC, "unknown", attrs)
    data = await coord._async_update_data()
    assert set(data.missing_attrs) == {ATTR_BUH_STEP1, ATTR_BUH_STEP2}
    assert coord.detector.state == "running"


async def test_435_partial_publish_still_freezes(hass):
    attrs = {k: v for k, v in ATTRS_435.items() if k != "Water pump operation"}
    attrs[ATTR_INV_FREQUENCY_RPS] = 16
    coord = DaikinCycleMLCoordinator(hass, _entry(hass))
    hass.states.async_set(SRC, "unknown", attrs)
    await coord._async_update_data()
    assert coord.detector.state == "idle"
