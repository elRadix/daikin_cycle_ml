"""Live temperatures on ``thermal_power_live`` for the native efficiency card.

The card draws water / return / outdoor / room graphs from the recorder
history of this one sensor, so the attributes must be there on v1
(monolithic) and v2 (individual) names, and the configured indoor
sensor wins over the controller's room sensor.
"""
from __future__ import annotations

from types import SimpleNamespace

from custom_components.daikin_cycle_ml.engine.thermal import (
    LIVE_TEMP_LABELS,
    live_temps_from_view,
)
from custom_components.daikin_cycle_ml.sensor import (
    _attrs_thermal_power_live,
    _live_temps,
    _safe_float_text,
)

V1 = {
    "Leaving water temp. before BUH (R1T)": 33.1,
    "Leaving water temp. after BUH (R2T)": 33.3,
    "Inlet water temp.(R4T)": 27.5,
    "R1T-Outdoor air temp.": 8.2,
    "LW setpoint (main)": 31.7,
    "Indoor ambient temp. (R1T)": 20.0,
    "RT setpoint": "20.0",
    "Refrig. Temp. liquid side (R3T)": 34.6,
    "INV frequency (rps)": 32,
    "Flow sensor (l/min)": 14.1,
}


def _snap(attrs):
    return SimpleNamespace(attrs=attrs, power_w=936.0, cop=6.2, mode="heating", state="running")


def test_view_reads_every_label():
    from custom_components.daikin_cycle_ml.engine.attribute_compat import build_compat_view

    t = live_temps_from_view(build_compat_view(V1))
    assert t == {
        "lwt_c": 33.1, "lwt_after_buh_c": 33.3, "return_c": 27.5, "outdoor_c": 8.2,
        "lw_setpoint_c": 31.7, "room_c": 20.0, "room_setpoint_c": 20.0, "refrigerant_liquid_c": 34.6,
    }
    assert set(t) == set(LIVE_TEMP_LABELS)


def test_view_fallbacks_and_bad_values():
    # no R1T before BUH: R2T is the leaving water; text that is not a number -> None
    t = live_temps_from_view({
        "Leaving water temp. after BUH (R2T)": 35.0, "Outdoor air temp.(R1T)": "-3.5",
        "RT setpoint": "n/a", "Inlet water temp.(R4T)": True,
    })
    assert t["lwt_c"] == 35.0 and t["outdoor_c"] == -3.5
    assert t["room_setpoint_c"] is None and t["return_c"] is None and t["room_c"] is None


def test_attrs_carry_the_temps_and_keep_the_inputs():
    a = _attrs_thermal_power_live(_snap(V1), SimpleNamespace())
    assert a["input_power_w"] == 936.0 and a["input_flow_lmin"] == 14.1
    assert a["lwt_c"] == 33.1 and a["return_c"] == 27.5 and a["outdoor_c"] == 8.2


def _coord(state):
    states = {"sensor.living": SimpleNamespace(state=state)} if state is not None else {}
    return SimpleNamespace(indoor_temp_entity="sensor.living",
                           hass=SimpleNamespace(states=SimpleNamespace(get=states.get)))


def test_configured_indoor_sensor_wins():
    assert _live_temps(_snap(V1), _coord("21.4"))["room_c"] == 21.4


def test_indoor_sensor_unknown_or_missing_keeps_controller_value():
    assert _live_temps(_snap(V1), _coord("unavailable"))["room_c"] == 20.0
    assert _live_temps(_snap(V1), _coord(None))["room_c"] == 20.0
    no_hass = SimpleNamespace(indoor_temp_entity="sensor.living", hass=None)
    assert _live_temps(_snap(V1), no_hass)["room_c"] == 20.0
    assert _live_temps(SimpleNamespace(attrs=None), SimpleNamespace())["lwt_c"] is None


def test_safe_float_text():
    assert _safe_float_text("1.5") == 1.5
    assert _safe_float_text(None) is None
    assert _safe_float_text("nan") is None and _safe_float_text("inf") is None
