"""v1.12.1: source gate tests for #109 restart phantom short_off."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)


_COORD_MOD = "custom_components.daikin_cycle_ml.coordinator"


def _bare() -> DaikinCycleMLCoordinator:
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.hass = MagicMock()
    c.hass.states.get = MagicMock(return_value=MagicMock())
    c.source_entity = "sensor.test_source"
    c.options = {}
    c.entry = MagicMock()
    c.entry.data = {}
    c.store = MagicMock()
    c.store.daily_reset_if_needed = MagicMock(return_value=False)
    c.detector = MagicMock()
    c.detector.state = "running"
    c.detector.snapshot = MagicMock(
        return_value={"mode": "heating", "start_ts": 1700000000.0}
    )
    c.detector.update = MagicMock(return_value=None)
    c.db = None
    c._runtime_day_key = ""
    c._energy_day_key = ""
    c._track_setpoint = MagicMock()
    c._read_power_w = MagicMock(return_value=1500.0)
    c._read_cop = MagicMock(return_value=3.5)
    c._compute_setpoint_oscillating = MagicMock(return_value=False)
    c._accumulate_cycle_samples = MagicMock()
    c._process_new_cycle = AsyncMock(return_value=None)
    c._tick_buh_and_defrost = MagicMock()
    c._tick_energy = MagicMock()
    c._maybe_persist_accumulators = AsyncMock(return_value=None)
    c._maybe_reset_daily_accumulators = MagicMock()
    return c


@pytest.mark.asyncio
async def test_detector_not_updated_when_attrs_missing(monkeypatch):
    c = _bare()
    monkeypatch.setattr(f"{_COORD_MOD}.read", lambda *a, **kw: {})
    monkeypatch.setattr(f"{_COORD_MOD}.missing_required", lambda attrs: ["rps"])
    snap = await c._async_update_data()
    c.detector.update.assert_not_called()
    assert snap.missing_attrs == ["rps"]


@pytest.mark.asyncio
async def test_detector_updated_when_attrs_complete(monkeypatch):
    """Gate bypassed -> execution reaches detector.update() on complete attrs."""
    # BaseException (not Exception): _async_update_data wraps its body in
    # 'except Exception' -- we must bypass that to escape with the sentinel.
    class _Reached(BaseException):
        pass

    c = _bare()
    monkeypatch.setattr(f"{_COORD_MOD}.read", lambda *a, **kw: {})
    monkeypatch.setattr(f"{_COORD_MOD}.missing_required", lambda attrs: [])
    c.detector.update = MagicMock(side_effect=_Reached())
    with pytest.raises(_Reached):
        await c._async_update_data()
    c._track_setpoint.assert_called_once()
    c.detector.update.assert_called_once()


@pytest.mark.asyncio
async def test_snap_state_preserved_during_missing_attrs(monkeypatch):
    c = _bare()
    monkeypatch.setattr(f"{_COORD_MOD}.read", lambda *a, **kw: {})
    monkeypatch.setattr(f"{_COORD_MOD}.missing_required", lambda attrs: ["rps"])
    snap = await c._async_update_data()
    assert snap.state == "running"
    assert snap.mode == "heating"
    assert snap.cycle_start_ts == 1700000000.0


@pytest.mark.asyncio
async def test_process_new_cycle_not_called_when_attrs_missing(monkeypatch):
    c = _bare()
    monkeypatch.setattr(f"{_COORD_MOD}.read", lambda *a, **kw: {})
    monkeypatch.setattr(f"{_COORD_MOD}.missing_required", lambda attrs: ["rps"])
    await c._async_update_data()
    c._process_new_cycle.assert_not_called()


@pytest.mark.asyncio
async def test_tick_energy_not_called_when_attrs_missing(monkeypatch):
    c = _bare()
    monkeypatch.setattr(f"{_COORD_MOD}.read", lambda *a, **kw: {})
    monkeypatch.setattr(f"{_COORD_MOD}.missing_required", lambda attrs: ["rps"])
    await c._async_update_data()
    c._tick_energy.assert_not_called()


@pytest.mark.asyncio
async def test_last_success_ts_updated_during_missing_attrs(monkeypatch):
    c = _bare()
    monkeypatch.setattr(f"{_COORD_MOD}.read", lambda *a, **kw: {})
    monkeypatch.setattr(f"{_COORD_MOD}.missing_required", lambda attrs: ["rps"])
    snap = await c._async_update_data()
    assert snap.last_success_ts > 0.0
    assert snap.last_sample_ts == snap.last_success_ts
