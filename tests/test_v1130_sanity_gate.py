"""v1.13.0 #129 #124: sanity gate for cop_avg / thermal_kw_avg."""
from __future__ import annotations

import pytest

from custom_components.daikin_cycle_ml.const import (
    MAX_COP,
    MAX_THERMAL_KW,
    MIN_SAMPLES_FOR_AVG,
)
from custom_components.daikin_cycle_ml.coordinator import (
    _apply_cop_sanity_gate,
)
from custom_components.daikin_cycle_ml.engine.cycle_detector import (
    _apply_thermal_sanity_gate,
)


def test_cop_below_min_samples_nulls():
    avg, conf = _apply_cop_sanity_gate(3.5, 2)
    assert avg is None
    assert conf == "none"


def test_cop_none_count_nulls():
    avg, conf = _apply_cop_sanity_gate(3.5, None)
    assert avg is None
    assert conf == "none"


def test_cop_at_min_boundary_kept():
    avg, conf = _apply_cop_sanity_gate(3.5, MIN_SAMPLES_FOR_AVG)
    assert avg == 3.5
    assert conf == "low"


def test_cop_above_max_nulls():
    avg, conf = _apply_cop_sanity_gate(17.33, 10)
    assert avg is None
    assert conf == "none"


def test_cop_at_max_boundary_kept():
    avg, conf = _apply_cop_sanity_gate(MAX_COP, 12)
    assert avg == MAX_COP
    assert conf == "high"


def test_cop_none_value_with_sufficient_count_stays_none():
    avg, conf = _apply_cop_sanity_gate(None, 10)
    assert avg is None
    assert conf == "medium"


def test_thermal_none_stays_none():
    assert _apply_thermal_sanity_gate(None) is None


def test_thermal_below_max_kept():
    assert _apply_thermal_sanity_gate(4.0) == 4.0


def test_thermal_at_max_boundary_kept():
    assert _apply_thermal_sanity_gate(MAX_THERMAL_KW) == MAX_THERMAL_KW


def test_thermal_above_max_nulls():
    assert _apply_thermal_sanity_gate(40.55) is None
    assert _apply_thermal_sanity_gate(33.8) is None


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_collect_cycle_averages_return_value_also_gated():
    """R488: gated cop_avg must also NULL the tuple-return, not just record."""
    from custom_components.daikin_cycle_ml import coordinator as _coord
    c = object.__new__(_coord.DaikinCycleMLCoordinator)
    c._cycle_lwt_sum = 0.0
    c._cycle_lwt_count = 0
    c._cycle_indoor_sum = 0.0
    c._cycle_indoor_count = 0
    c._cycle_cop_w_sum = 173.3
    c._cycle_cop_weight_sum = 10.0
    c._cycle_cop_sq_w_sum = 173.3 * 17.33
    c._cycle_cop_count = 10
    c.indoor_temp_entity = None
    c.db = None
    record = {
        "start_ts": 1.0, "end_ts": 2.0,
        "duration_s": 600.0, "mode": "heating",
    }
    ret_avg, _lwt, _ind = await c._collect_cycle_averages(record)
    assert ret_avg is None
    assert record["cop_avg"] is None
    assert record["cop_confidence"] == "none"
    assert record["cop_sample_count"] == 10
