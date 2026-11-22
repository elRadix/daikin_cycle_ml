"""#487: hot water on a source without I/U operation mode (EDLA, ESPAltherma v1).

Replay of the reporter's data: the corpus file edla09d3v3_1_29_1 holds the
32 source values (no I/U operation mode, no pump state); the history in the
issue shows "Operation Mode" = Heating all morning while the 3-way valve was
ON from 06:47 to 07:13 and the tank rose from 36 to 47 degC inside a
heating run that lasted all night. v1.29.1 counted the whole run as heating
(cycles_dhw 0 since install). The valve is now the DHW signal for such a
source, read only while the compressor runs.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from custom_components.daikin_cycle_ml.binary_sensor import _is_dhw_active
from custom_components.daikin_cycle_ml.engine.cycle_detector import CycleDetector

CORPUS = Path(__file__).parent / "fixtures/diagnostics/edla09d3v3_1_29_1_8ef865c795_202611220957.json"
T0 = 1_795_300_000.0
OPTS = {"compressor_rps_threshold": 12.0}       # the reporter's own option


def _attrs(valve: str, tank: float) -> dict:
    a = dict(json.loads(CORPUS.read_text(encoding="utf-8"))["source"]["attributes"])
    assert "I/U operation mode" not in a and a["Operation Mode"] == "Heating"
    a.update({"Defrost Operation": "OFF", "INV frequency (rps)": 30,
              "3way valve(On:DHW_Off:Space)": valve, "DHW tank temp. (R5T)": tank})
    return a


def _replay(det: CycleDetector) -> list[dict]:
    """Heating 06:00-06:47, valve ON 06:47-07:13 (tank 36 -> 47), heating again."""
    records, t = [], T0
    for minute in range(0, 120):
        valve = "ON" if 47 <= minute < 73 else "OFF"
        tank = 36.0 + max(0, min(minute - 47, 26)) * 11 / 26
        rec = det.update(_attrs(valve, tank), t + minute * 60, power_w=1000.0)
        if rec:
            records.append(rec)
    return records


def test_valve_splits_the_heating_run_into_hot_water_and_back():
    det = CycleDetector(OPTS, dhw_present=True)
    records = _replay(det)
    modes = [r["mode"] for r in records]
    assert modes == ["heating", "dhw"], records
    heat, dhw = records
    # valve ON for 26 min; each split waits the 60 s debounce of a valve-only source
    assert 25 * 60 <= dhw["duration_s"] <= 27 * 60
    assert heat["ended_by"] == "split" and dhw["ended_by"] == "split"
    assert det.snapshot()["mode"] == "heating"          # back to space heating


def test_without_dhw_tank_the_valve_is_ignored():
    det = CycleDetector(OPTS, dhw_present=False)
    assert _replay(det) == []                           # one heating run, never split


def test_with_an_indoor_mode_the_valve_alone_still_does_not_split():
    det = CycleDetector(OPTS, dhw_present=True)
    t = T0
    for minute in range(0, 30):
        a = _attrs("ON" if minute >= 10 else "OFF", 40.0)
        a["I/U operation mode"] = "Heating"                 # an indoor mode that stays heating
        assert det.update(a, t + minute * 60, power_w=1000.0) is None


@pytest.mark.parametrize(("iu", "state", "mode", "expected"), [
    (None, "running", "dhw", True),        # #487: no indoor mode, detector in DHW
    (None, "running", "heating", False),
    (None, "idle", "dhw", False),          # valve resting ON with the compressor off
    ("DHW", "running", "heating", True),   # indoor mode still decides when present
    ("Heating", "running", "dhw", False),
])
def test_dhw_active_binary_sensor(iu, state, mode, expected):
    attrs = {"3way valve(On:DHW_Off:Space)": "ON"}
    if iu is not None:
        attrs["I/U operation mode"] = iu
    s = SimpleNamespace(attrs=attrs, state=state, mode=mode)
    assert _is_dhw_active(s, SimpleNamespace()) is expected
