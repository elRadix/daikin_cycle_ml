"""#189: Altherma HT (ERRQ + ERSQ hydrobox) attribute names.

The ESPAltherma definition "Altherma(HT ERRQ-ERSQ outdoor unit 11-16kW).h"
(beta 3548ea2, docs/MODEL_ATTRIBUTES.json) publishes the water side as
"Leaving water temp. (hydrobox)" / "Inlet water temp. (hydrobox)" and the
compressor as "INV Comp. Frequency(Hz)". None of the three was an alias, so
an HT unit read no compressor speed and no water temperatures: no cycle
was ever detected. "R2T (discharge)" and "R4T (deicer)" on that unit are
refrigerant sensors and must not be read as water.

No HT install is in the diagnostics corpus yet (R399): the labels below are
exactly the definition's names, the values are a plausible running heat
pump at W60.
"""
from __future__ import annotations

import json
from pathlib import Path

from custom_components.daikin_cycle_ml.const import (
    ATTR_INLET_WATER_R4T,
    ATTR_INV_FREQUENCY_RPS,
    ATTR_LEAVING_WATER_BEFORE_BUH,
)
from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
from custom_components.daikin_cycle_ml.engine.attribute_compat import build_compat_view
from tests.test_435_no_dhw_detection import SRC, _entry

DEFINITION = "Altherma(HT ERRQ-ERSQ outdoor unit 11-16kW).h"

ATTRS_HT = {
    "Operation Mode": "Heating", "I/U operation mode": "Heating", "Thermostat ON/OFF": "ON",
    "I/U Thermostat ON/OFF": "ON", "Defrost Operation": "OFF", "Freeze Protection": "OFF",
    "Error Code": " 0", "Error type": "Normal", "R1T-Outdoor air temp.": 4.0,
    "INV Comp. Frequency(Hz)": 58, "Leaving water temp. (hydrobox)": 60.2,
    "Inlet water temp. (hydrobox)": 51.4, "R2T (discharge)": 88.0, "R4T (deicer)": -2.5,
    "R3T (R410A liquid)": 41.0, "R5T (suction 2)": 3.0, "R7T (liquid)": 30.5,
    "High Pressure": 2.9, "Low Pressure": 0.7, "Fan 1 (step)": 7,
    "Target Cond. Temp.": 46.0, "Target Evap. Temp.": -1.0,
}


def test_the_fixture_uses_only_names_of_the_ht_definition():
    labels = json.loads((Path(__file__).parent.parent / "docs/MODEL_ATTRIBUTES.json").read_text())["labels"]
    assert all(DEFINITION in labels[k] for k in ATTRS_HT), [k for k in ATTRS_HT if DEFINITION not in labels[k]]


def test_hydrobox_water_and_hz_compressor_resolve():
    v = build_compat_view(ATTRS_HT)
    assert v[ATTR_LEAVING_WATER_BEFORE_BUH] == 60.2
    assert v[ATTR_INLET_WATER_R4T] == 51.4                 # not R4T (deicer)
    assert v[ATTR_INV_FREQUENCY_RPS] == 58


async def test_an_ht_unit_detects_a_heating_run(hass):
    coord = DaikinCycleMLCoordinator(hass, _entry(hass))
    hass.states.async_set(SRC, "unknown", ATTRS_HT)
    data = await coord._async_update_data()
    assert coord.detector.state == "running"
    assert data.state == "running" and data.mode == "heating"
    assert ATTR_INLET_WATER_R4T not in data.missing_attrs


def test_a_stand_in_keeps_the_freeze_guard_for_real_gaps():
    from custom_components.daikin_cycle_ml.coordinator import _detection_blocked
    r2t, flow = "Leaving water temp. after BUH (R2T)", "Flow sensor (l/min)"
    assert _detection_blocked([r2t, flow], ATTRS_HT) is False          # R1T + compressor published
    assert _detection_blocked([r2t, flow]) is True                     # no attrs: #109 guard as before
    no_rps = {k: v for k, v in ATTRS_HT.items() if k != "INV Comp. Frequency(Hz)"}
    assert _detection_blocked([flow], no_rps) is True                  # flow is the only start signal left
    assert _detection_blocked([ATTR_INLET_WATER_R4T], ATTRS_HT) is True  # no stand-in for R4T


def test_the_setpoint_does_not_freeze_detection():
    from custom_components.daikin_cycle_ml.const import ATTR_LW_SETPOINT, DETECTION_CRITICAL_ATTRIBUTES, REQUIRED_ATTRIBUTES
    assert ATTR_LW_SETPOINT in REQUIRED_ATTRIBUTES            # still reported as missing
    assert ATTR_LW_SETPOINT not in DETECTION_CRITICAL_ATTRIBUTES
