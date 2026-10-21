"""v1.12.0: DB-first cycle persist + feature-vector consistency (issue #103)."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator


class _FakeSnap:
    def __init__(self) -> None:
        self.mode = "heating"
        self.anomaly = None
        self.advice = None
        self.cluster_id = None


def _make_coord() -> DaikinCycleMLCoordinator:
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = {"action_advice_enabled": False}
    c.db = MagicMock()
    c.db.async_insert_cycle = AsyncMock(return_value=101)
    c.db.async_insert_features = AsyncMock(return_value=None)
    c.db.async_update_cycle_cluster = AsyncMock(return_value=None)
    c._collect_cycle_averages = AsyncMock(
        return_value=(5.0, 30.0, 21.0)
    )
    c._assign_cluster = MagicMock(return_value=2)
    c._maybe_rollup_day = AsyncMock(return_value=None)
    c.adaptive = MagicMock()
    c.adaptive.observe_cycle = MagicMock(return_value=None)
    c.baseline = MagicMock()
    c.baseline.get = MagicMock(return_value=MagicMock(
        update=MagicMock(return_value=None)
    ))
    c._clamp_duration = lambda d, m: d  # type: ignore[method-assign]
    return c


def _rec() -> dict[str, Any]:
    return {
        "start_ts": 1000.0, "end_ts": 1060.0, "duration_s": 60,
        "mode": "heating", "dT_max": 5.0, "dT_avg": 3.0,
        "rps_max": 30, "rps_avg": 20.0, "thermal_kw_avg": 2.5,
        "buh_used": 0, "defrost_used": 0,
    }


async def test_db_insert_called_before_ml(monkeypatch):
    """DB-first ordering: cycle insert must precede ML observe_cycle."""
    order: list[str] = []
    c = _make_coord()
    c.db.async_insert_cycle = AsyncMock(
        side_effect=lambda r: order.append("db_insert") or 101
    )
    c.adaptive.observe_cycle = MagicMock(
        side_effect=lambda *a, **k: order.append("ml_observe")
    )
    # Patch extract_feature_vector at module level
    import custom_components.daikin_cycle_ml.coordinator as co
    monkeypatch.setattr(
        co, "extract_feature_vector", lambda *a, **k: [0.0] * 12
    )
    monkeypatch.setattr(
        co, "evaluate_anomaly",
        lambda *a, **k: MagicMock(is_anomaly=False),
    )
    await c._process_new_cycle(_rec(), _FakeSnap())
    assert "db_insert" in order and "ml_observe" in order
    assert order.index("db_insert") < order.index("ml_observe")


async def test_features_include_thermal_kw_avg(monkeypatch):
    """Regression: features path must pass thermal_kw_avg (was missing pre-v1.12.0)."""
    captured: list[dict] = []
    c = _make_coord()

    def _fake_extract(record, **kwargs):
        captured.append(dict(kwargs))
        return [0.0] * 12

    import custom_components.daikin_cycle_ml.coordinator as co
    monkeypatch.setattr(co, "extract_feature_vector", _fake_extract)
    monkeypatch.setattr(
        co, "evaluate_anomaly",
        lambda *a, **k: MagicMock(is_anomaly=False),
    )
    await c._process_new_cycle(_rec(), _FakeSnap())
    # Both calls (features + ML) must include thermal_kw_avg
    assert len(captured) == 2
    for call in captured:
        assert "thermal_kw_avg" in call
        assert call["thermal_kw_avg"] == 2.5


async def test_db_insert_cycle_exception_isolated(monkeypatch):
    """DB cycle insert raises → ML still runs, features skipped, cid=None."""
    c = _make_coord()
    c.db.async_insert_cycle = AsyncMock(side_effect=RuntimeError("db boom"))
    import custom_components.daikin_cycle_ml.coordinator as co
    monkeypatch.setattr(
        co, "extract_feature_vector", lambda *a, **k: [0.0] * 12
    )
    monkeypatch.setattr(
        co, "evaluate_anomaly",
        lambda *a, **k: MagicMock(is_anomaly=False),
    )
    await c._process_new_cycle(_rec(), _FakeSnap())
    # ML still ran
    c.adaptive.observe_cycle.assert_called_once()
    # features skipped because cid=None
    c.db.async_insert_features.assert_not_called()


async def test_features_exception_isolated(monkeypatch):
    """Features insert raises → ML still runs, cluster not updated."""
    c = _make_coord()
    c.db.async_insert_features = AsyncMock(side_effect=RuntimeError("features boom"))
    import custom_components.daikin_cycle_ml.coordinator as co
    monkeypatch.setattr(
        co, "extract_feature_vector", lambda *a, **k: [0.0] * 12
    )
    monkeypatch.setattr(
        co, "evaluate_anomaly",
        lambda *a, **k: MagicMock(is_anomaly=False),
    )
    await c._process_new_cycle(_rec(), _FakeSnap())
    # ML still ran
    c.adaptive.observe_cycle.assert_called_once()
    # cluster not updated because feature path failed
    c.db.async_update_cycle_cluster.assert_not_called()


async def test_cluster_assign_exception_isolated(monkeypatch):
    """_assign_cluster raises → does not block rollup, ML still runs."""
    c = _make_coord()
    c._assign_cluster = MagicMock(side_effect=RuntimeError("cluster boom"))
    import custom_components.daikin_cycle_ml.coordinator as co
    monkeypatch.setattr(
        co, "extract_feature_vector", lambda *a, **k: [0.0] * 12
    )
    monkeypatch.setattr(
        co, "evaluate_anomaly",
        lambda *a, **k: MagicMock(is_anomaly=False),
    )
    await c._process_new_cycle(_rec(), _FakeSnap())
    c._maybe_rollup_day.assert_awaited_once()


async def test_rollup_called_after_ml(monkeypatch):
    """Rollup is last; ML runs before it."""
    order: list[str] = []
    c = _make_coord()
    c.adaptive.observe_cycle = MagicMock(
        side_effect=lambda *a, **k: order.append("ml")
    )
    c._maybe_rollup_day = AsyncMock(
        side_effect=lambda r: order.append("rollup")
    )
    import custom_components.daikin_cycle_ml.coordinator as co
    monkeypatch.setattr(
        co, "extract_feature_vector", lambda *a, **k: [0.0] * 12
    )
    monkeypatch.setattr(
        co, "evaluate_anomaly",
        lambda *a, **k: MagicMock(is_anomaly=False),
    )
    await c._process_new_cycle(_rec(), _FakeSnap())
    assert order == ["ml", "rollup"]
