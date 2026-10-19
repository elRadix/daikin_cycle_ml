"""v1.9.0 J — avg_duration_7d_min (Q5) tests."""
from __future__ import annotations
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
import pytest
from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator


def _bare() -> DaikinCycleMLCoordinator:
    return object.__new__(DaikinCycleMLCoordinator)


# --- helper: _compute_avg_duration_7d_min ---

@pytest.mark.asyncio
async def test_helper_none_when_db_absent() -> None:
    c = _bare()
    assert await c._compute_avg_duration_7d_min() is None


@pytest.mark.asyncio
async def test_helper_none_when_getter_absent() -> None:
    c = _bare()
    c.db = SimpleNamespace()
    assert await c._compute_avg_duration_7d_min() is None


@pytest.mark.asyncio
async def test_helper_none_on_exception() -> None:
    c = _bare()
    c.db = SimpleNamespace(async_avg_duration_since=AsyncMock(side_effect=RuntimeError("x")))
    assert await c._compute_avg_duration_7d_min() is None


@pytest.mark.asyncio
async def test_helper_none_when_query_returns_none() -> None:
    c = _bare()
    c.db = SimpleNamespace(async_avg_duration_since=AsyncMock(return_value=None))
    assert await c._compute_avg_duration_7d_min() is None


@pytest.mark.asyncio
async def test_helper_converts_seconds_to_minutes() -> None:
    c = _bare()
    c.db = SimpleNamespace(async_avg_duration_since=AsyncMock(return_value=900.0))
    assert await c._compute_avg_duration_7d_min() == 15


@pytest.mark.asyncio
async def test_helper_rounds_to_int() -> None:
    c = _bare()
    c.db = SimpleNamespace(async_avg_duration_since=AsyncMock(return_value=935.0))
    assert await c._compute_avg_duration_7d_min() == 16


@pytest.mark.asyncio
async def test_helper_passes_7day_window() -> None:
    c = _bare()
    m = AsyncMock(return_value=600.0)
    c.db = SimpleNamespace(async_avg_duration_since=m)
    before = time.time()
    await c._compute_avg_duration_7d_min()
    after = time.time()
    args, _ = m.call_args
    since = args[0]
    assert before - (7 * 86400) - 2 <= since <= after - (7 * 86400) + 2


# --- ctx: field only on 3 targets ---

def _snap() -> Any:
    n = SimpleNamespace()
    for f in (
        "lwt_setpoint", "lwt_actual", "indoor_temp", "flow_lmin", "outdoor_temp",
        "cop_degradation_week_pct", "cop_trend_30d",
    ):
        setattr(n, f, None)
    return n


def _coord_for_ctx() -> Any:
    from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator as C
    c = object.__new__(C)
    c._avg_duration_7d_min = 42
    c.store = MagicMock()
    c.store.last_cycle.return_value = {"duration_s": 1800}
    c.store.cycles_in_window.return_value = 0
    c.store.cycles_in_window_mode.return_value = 0
    c.store.cycles_today.return_value = []
    c.options = {}
    c._setpoint_history = []
    c._kmeans_stale = {}
    c._energy_daily_anomaly = {}
    c._defrost_7d_sum = 0
    c._buh_7d_ratio = 0.0
    c.config_entry = None
    return c


def test_ctx_has_avg_on_pendulum_hourly() -> None:
    ctx = _coord_for_ctx()._build_alert_context(_snap())
    assert ctx["pendulum_hourly"].get("avg_duration_7d_min") == 42


def test_ctx_has_avg_on_pendulum_daily() -> None:
    ctx = _coord_for_ctx()._build_alert_context(_snap())
    assert ctx["pendulum_daily"].get("avg_duration_7d_min") == 42


def test_ctx_has_avg_on_ml_anomaly() -> None:
    ctx = _coord_for_ctx()._build_alert_context(_snap())
    assert ctx["ml_anomaly"].get("avg_duration_7d_min") == 42


def test_ctx_generic_pendulum_unchanged() -> None:
    ctx = _coord_for_ctx()._build_alert_context(_snap())
    assert "avg_duration_7d_min" not in ctx["pendulum"]


def test_ctx_short_run_unchanged() -> None:
    ctx = _coord_for_ctx()._build_alert_context(_snap())
    assert "avg_duration_7d_min" not in ctx["short_run"]


# --- schema + labels ---

def test_schema_pendulum_hourly_has_row() -> None:
    from custom_components.daikin_cycle_ml.engine.status_report import ALERT_SCHEMA
    keys = [t[1] for t in ALERT_SCHEMA["pendulum_hourly"]]
    assert "avg_duration_7d" in keys


def test_schema_pendulum_daily_has_row() -> None:
    from custom_components.daikin_cycle_ml.engine.status_report import ALERT_SCHEMA
    keys = [t[1] for t in ALERT_SCHEMA["pendulum_daily"]]
    assert "avg_duration_7d" in keys


def test_schema_ml_anomaly_has_row() -> None:
    from custom_components.daikin_cycle_ml.engine.status_report import ALERT_SCHEMA
    keys = [t[1] for t in ALERT_SCHEMA["ml_anomaly"]]
    assert "avg_duration_7d" in keys


def test_labels_en_present() -> None:
    from custom_components.daikin_cycle_ml.engine import status_report as sr
    assert sr.ALERT_LABELS["en"]["avg_duration_7d"] == "Avg duration 7d"


def test_labels_nl_present() -> None:
    from custom_components.daikin_cycle_ml.engine import status_report as sr
    assert sr.ALERT_LABELS["nl"]["avg_duration_7d"] == "Gem. duur 7d"


def test_last_duration_min_preserved() -> None:
    from custom_components.daikin_cycle_ml.engine.status_report import ALERT_SCHEMA
    keys = [t[1] for t in ALERT_SCHEMA["pendulum_hourly"]]
    assert "last_duration" in keys
