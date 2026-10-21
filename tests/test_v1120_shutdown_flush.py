"""v1.12.0: shutdown flush + STOP handler tests (issue #104)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator


def _bare() -> DaikinCycleMLCoordinator:
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.db = AsyncMock()
    c._persist_runtime_acc = AsyncMock(return_value=None)
    c._persist_energy_acc = AsyncMock(return_value=None)
    c._persist_detector_state = AsyncMock(return_value=None)
    return c


async def test_flush_accumulators_calls_all_three():
    c = _bare()
    await c._async_flush_accumulators()
    c._persist_runtime_acc.assert_called_once()
    c._persist_energy_acc.assert_called_once()
    c._persist_detector_state.assert_called_once()


async def test_flush_accumulators_isolates_failures():
    c = _bare()
    c._persist_runtime_acc.side_effect = RuntimeError("runtime boom")
    await c._async_flush_accumulators()
    c._persist_runtime_acc.assert_called_once()
    c._persist_energy_acc.assert_called_once()
    c._persist_detector_state.assert_called_once()


async def test_handle_shutdown_calls_flush():
    c = _bare()
    c._async_flush_accumulators = AsyncMock(return_value=None)
    await c._async_handle_shutdown()
    c._async_flush_accumulators.assert_called_once()


async def test_handle_shutdown_accepts_event_arg():
    c = _bare()
    c._async_flush_accumulators = AsyncMock(return_value=None)
    await c._async_handle_shutdown(object())
    c._async_flush_accumulators.assert_called_once()


async def test_flush_accumulators_order_preserved():
    """Sequence: runtime, energy, detector — matches source order (R378)."""
    c = _bare()
    parent = MagicMock()
    parent.attach_mock(c._persist_runtime_acc, "rt")
    parent.attach_mock(c._persist_energy_acc, "el")
    parent.attach_mock(c._persist_detector_state, "dt")
    await c._async_flush_accumulators()
    assert [m[0] for m in parent.mock_calls] == ["rt", "el", "dt"]
