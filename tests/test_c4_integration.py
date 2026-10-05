"""C4: coordinator + sensor integration.

Marker: C4_INTEGRATION_TESTS_v1
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    DataSnapshot,
)
from custom_components.daikin_cycle_ml.sensor import (
    SENSOR_DEFS,
    _attrs_cop_degradation_status,
    _attrs_cop_degradation_week_pct,
    _attrs_cop_trend_30d,
    _value_cop_degradation_status,
    _value_cop_degradation_week_pct,
    _value_cop_trend_30d,
)


def _snap(**kw) -> DataSnapshot:
    s = DataSnapshot()
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def _coord() -> DaikinCycleMLCoordinator:
    c = MagicMock()
    c.db = None
    c._cop_degradation_cache = {}
    c._cop_degradation_cache_ts = 0.0
    return c


# --- DataSnapshot defaults ---

def test_snapshot_defaults():
    s = DataSnapshot()
    assert s.cop_degradation_status == "none"
    assert s.cop_degradation_week_pct is None
    assert s.cop_trend_30d is None
    assert s.cop_degradation_detail == {}
    assert s.cop_trend_detail == {}


# --- value_fns ---

def test_value_status():
    s = _snap(cop_degradation_status="warning")
    assert _value_cop_degradation_status(s, None) == "warning"


def test_value_week_pct():
    s = _snap(cop_degradation_week_pct=-12.5)
    assert _value_cop_degradation_week_pct(s, None) == -12.5


def test_value_week_pct_none():
    s = _snap(cop_degradation_week_pct=None)
    assert _value_cop_degradation_week_pct(s, None) is None


def test_value_trend():
    s = _snap(cop_trend_30d=-8.0)
    assert _value_cop_trend_30d(s, None) == -8.0


# --- attr_fns with populated detail ---

def test_attrs_status_full():
    detail = {
        "severity_raw": "critical",
        "severity_downgraded": True,
        "week_pct": -18.0,
        "week_pct_raw": -18.0,
        "lwt_shift_detected": True,
        "lwt_shift_c": 6.0,
        "threshold_pct": -8.0,
        "critical_pct": -15.0,
        "valid": True,
        "updated_ts": 1234.0,
    }
    s = _snap(cop_degradation_detail=detail)
    a = _attrs_cop_degradation_status(s, None)
    assert a["severity_raw"] == "critical"
    assert a["severity_downgraded"] is True
    assert a["week_pct"] == -18.0
    assert a["lwt_shift_detected"] is True
    assert a["updated_ts"] == 1234.0


def test_attrs_status_empty():
    s = _snap(cop_degradation_detail={})
    a = _attrs_cop_degradation_status(s, None)
    assert a["severity_raw"] == "none"
    assert a["severity_downgraded"] is False
    assert a["valid"] is False


def test_attrs_status_none_detail():
    s = _snap(cop_degradation_detail=None)
    a = _attrs_cop_degradation_status(s, None)
    assert a["severity_raw"] == "none"


def test_attrs_week_full():
    detail = {
        "mode": "heating",
        "window_days": 7,
        "n_samples_recent": 400,
        "n_samples_prev": 400,
        "n_days_recent": 8,
        "n_days_prev": 8,
        "n_bins_used": 2,
        "dynamic_min_samples": 100,
        "bins_used": [
            {"range": "mild", "hours_recent": 10, "hours_prev": 10,
             "cop_recent": 3.2, "cop_prev": 3.6,
             "ratio": 0.889, "weight": 10},
        ],
        "excluded_hours_recent": 0,
        "excluded_hours_prev": 1,
        "exclusion_skew": 0.125,
        "lwt_mean_recent": 35.0,
        "lwt_mean_prev": 34.0,
        "updated_ts": 1234.0,
    }
    s = _snap(cop_degradation_detail=detail)
    a = _attrs_cop_degradation_week_pct(s, None)
    assert a["mode"] == "heating"
    assert a["n_bins_used"] == 2
    assert len(a["bins_used"]) == 1
    assert a["exclusion_skew"] == 0.125


def test_attrs_week_empty():
    s = _snap(cop_degradation_detail={})
    a = _attrs_cop_degradation_week_pct(s, None)
    assert a["bins_used"] == []
    assert a["n_bins_used"] is None


def test_attrs_trend_full():
    detail = {
        "mode": "heating",
        "window_days": 30,
        "baseline_days": 30,
        "recent_days": 7,
        "n_hours_baseline": 20,
        "n_hours_recent": 10,
        "outdoor_spread_baseline_c": 19.0,
        "fit_slope": -0.1,
        "fit_intercept": 4.5,
        "fit_r2": 0.999,
        "cop_predicted_recent": 3.85,
        "cop_observed_recent": 3.47,
        "threshold_pct": -8.0,
        "critical_pct": -15.0,
        "valid": True,
        "updated_ts": 1234.0,
    }
    s = _snap(cop_trend_detail=detail)
    a = _attrs_cop_trend_30d(s, None)
    assert a["fit_slope"] == -0.1
    assert a["fit_r2"] == 0.999
    assert a["valid"] is True


def test_attrs_trend_empty():
    s = _snap(cop_trend_detail={})
    a = _attrs_cop_trend_30d(s, None)
    assert a["valid"] is False
    assert a["fit_slope"] is None


# --- SENSOR_DEFS coverage ---

def test_sensor_defs_present():
    keys = {d["key"] for d in SENSOR_DEFS}
    assert "cop_degradation_status" in keys
    assert "cop_degradation_week_pct" in keys
    assert "cop_trend_30d" in keys


def test_status_def_is_enum():
    st = next(
        d for d in SENSOR_DEFS if d["key"] == "cop_degradation_status"
    )
    assert st["options"] == ["none", "info", "warning", "critical"]
    assert "state_class" not in st


def test_week_pct_def_is_measurement():
    st = next(
        d for d in SENSOR_DEFS
        if d["key"] == "cop_degradation_week_pct"
    )
    assert st["unit"] == "%"
    assert st["state_class"] is not None


def test_trend_def_is_measurement():
    st = next(
        d for d in SENSOR_DEFS if d["key"] == "cop_trend_30d"
    )
    assert st["unit"] == "%"


# --- coordinator method: _maybe_refresh_cop_degradation ---

@pytest.mark.asyncio
async def test_refresh_no_db_returns_silently():
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
    )
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.db = None
    c._cop_degradation_cache = {}
    c._cop_degradation_cache_ts = 0.0
    await c._maybe_refresh_cop_degradation(time.time())
    assert c._cop_degradation_cache == {}


@pytest.mark.asyncio
async def test_refresh_throttled():
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
    )
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.db = AsyncMock()
    c.db.async_query_cop_hourly = AsyncMock(return_value=[])
    c.db.async_fetch_cycles = AsyncMock(return_value=[])
    c._cop_degradation_cache = {"pre": "set"}
    now = time.time()
    c._cop_degradation_cache_ts = now - 10.0  # within throttle
    await c._maybe_refresh_cop_degradation(now)
    assert c._cop_degradation_cache == {"pre": "set"}
    c.db.async_query_cop_hourly.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_populates_cache():
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
    )
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.db = AsyncMock()
    c.db.async_query_cop_hourly = AsyncMock(return_value=[])
    c.db.async_fetch_cycles = AsyncMock(return_value=[])
    c._cop_degradation_cache = {}
    c._cop_degradation_cache_ts = 0.0
    now = time.time()
    await c._maybe_refresh_cop_degradation(now)
    assert "degradation" in c._cop_degradation_cache
    assert "trend" in c._cop_degradation_cache
    assert c._cop_degradation_cache_ts == now


@pytest.mark.asyncio
async def test_refresh_db_error_preserves_cache():
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
    )
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.db = AsyncMock()
    c.db.async_query_cop_hourly = AsyncMock(side_effect=RuntimeError("boom"))
    c._cop_degradation_cache = {"keep": "me"}
    c._cop_degradation_cache_ts = 0.0
    await c._maybe_refresh_cop_degradation(time.time())
    assert c._cop_degradation_cache == {"keep": "me"}
