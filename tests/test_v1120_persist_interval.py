"""v1.12.0: persist interval 300s→30s test (issue #101 sub-item 3b)."""
from __future__ import annotations

from unittest.mock import AsyncMock

from custom_components.daikin_cycle_ml.const import ENERGY_PERSIST_INTERVAL_S
from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator


def _make_coord(
    *,
    last_energy: float = 0.0,
    last_runtime: float = 0.0,
) -> DaikinCycleMLCoordinator:
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c._persist_runtime_acc = AsyncMock(return_value=None)
    c._persist_energy_acc = AsyncMock(return_value=None)
    c._last_runtime_persist_ts = last_runtime
    c._last_energy_persist_ts = last_energy
    return c


def test_interval_constant_is_30s():
    """Regression guard: interval must stay at tick cadence."""
    assert ENERGY_PERSIST_INTERVAL_S == 30.0


async def test_first_tick_below_interval_does_not_persist():
    c = _make_coord(last_energy=0.0, last_runtime=0.0)
    await c._maybe_persist_accumulators(now=10.0)
    c._persist_runtime_acc.assert_not_called()
    c._persist_energy_acc.assert_not_called()


async def test_tick_at_interval_persists_both():
    c = _make_coord(last_energy=0.0, last_runtime=0.0)
    await c._maybe_persist_accumulators(now=30.0)
    c._persist_runtime_acc.assert_called_once()
    c._persist_energy_acc.assert_called_once()
    assert c._last_runtime_persist_ts == 30.0
    assert c._last_energy_persist_ts == 30.0


async def test_tick_just_below_interval_does_not_persist():
    """Guard: interval is strict >=, not > — 29.9s must not fire."""
    c = _make_coord(last_energy=0.0, last_runtime=0.0)
    await c._maybe_persist_accumulators(now=29.9)
    c._persist_runtime_acc.assert_not_called()
    c._persist_energy_acc.assert_not_called()


async def test_second_persist_after_full_interval():
    """Two consecutive ticks at 30s, 60s → both fire (regression from 300s)."""
    c = _make_coord(last_energy=0.0, last_runtime=0.0)
    await c._maybe_persist_accumulators(now=30.0)
    assert c._persist_runtime_acc.call_count == 1
    await c._maybe_persist_accumulators(now=60.0)
    assert c._persist_runtime_acc.call_count == 2
    assert c._persist_energy_acc.call_count == 2
    assert c._last_energy_persist_ts == 60.0
