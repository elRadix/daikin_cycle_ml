"""Large attributes stay out of the recorder (16 KB limit).

prod-1: "State attributes for sensor.daikin_cycle_ml_daily_summary_recent
exceed maximum size of 16384 bytes ... Attributes will not be stored",
logged on every update. 31 days x modes plus events_by_day pass the limit.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

from homeassistant.components.recorder.db_schema import MAX_STATE_ATTRS_BYTES

from custom_components.daikin_cycle_ml import sensor as s


def _entity(key: str):
    spec = next(d for d in s.SENSOR_DEFS if d["key"] == key)
    cls = s.DaikinCycleMLLargeSensor if key in s.LARGE_ATTR_SENSORS else s.DaikinCycleMLSensor
    return cls(MagicMock(), key=spec["key"], name=spec["name"], value_fn=spec["value_fn"])


def test_large_sensors_exclude_their_big_attributes():
    unrec = _entity("daily_summary_recent")._Entity__combined_unrecorded_attributes
    assert {"days", "events_by_day", "totals_by_mode"} <= unrec
    assert "points" in _entity("cop_curve_recent")._Entity__combined_unrecorded_attributes
    assert "alerts" in _entity("alerts_today")._Entity__combined_unrecorded_attributes
    assert s.LARGE_ATTR_SENSORS <= {d["key"] for d in s.SENSOR_DEFS}


def test_graph_history_of_the_efficiency_card_is_still_recorded():
    # the Efficiency card draws its graphs from this sensor's recorded attributes
    assert "thermal_power_live" not in s.LARGE_ATTR_SENSORS
    assert not _entity("thermal_power_live")._Entity__combined_unrecorded_attributes & {
        "lwt_c", "return_c", "outdoor_c", "input_power_w", "input_cop", "input_flow_lmin"}


def test_a_month_of_summary_is_over_the_limit_without_the_exclusion():
    day = {"day": "2026-11-01", "mode": "heating", "cycles": 6, "runs": 6, "dur_min": 905.5,
           "dur_max": 300.0, "dur_min_avg": 150.9, "quality_avg": 88.4, "buh": 0, "defrost": 4}
    attrs = {"days": [dict(day, mode=m) for _ in range(31) for m in ("heating", "dhw", "cooling")],
             "events_by_day": {f"2026-11-{i:02d}": {"buh_min": 0.0, "defrost_events": 4} for i in range(1, 32)}}
    assert len(json.dumps(attrs)) > MAX_STATE_ATTRS_BYTES
