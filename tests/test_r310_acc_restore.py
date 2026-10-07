"""R310: energy/runtime accumulator rehydration on coordinator startup."""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.localtime(time.time()))


def _make_coord() -> DaikinCycleMLCoordinator:
    """Coordinator without __init__ side effects (R258)."""
    c = object.__new__(DaikinCycleMLCoordinator)
    c.db = None
    c._buh_step1_s = 0.0
    c._buh_step2_s = 0.0
    c._defrost_count_today = 0
    c._defrost_duration_s = 0.0
    c._last_defrost_ts = 0.0
    c._runtime_day_key = ""
    c._energy_day_key = ""
    c._energy_acc = {
        "heating": {"th": 0.0, "el": 0.0},
        "dhw": {"th": 0.0, "el": 0.0},
        "cooling": {"th": 0.0, "el": 0.0},
    }
    return c


# ---------- _restore_runtime_acc ----------

@pytest.mark.asyncio
async def test_restore_runtime_acc_no_db() -> None:
    assert await _make_coord()._restore_runtime_acc() is False


@pytest.mark.asyncio
async def test_restore_runtime_acc_payload_not_dict() -> None:
    c = _make_coord()
    c.db = AsyncMock()
    c.db.async_get_model_state = AsyncMock(return_value="not-a-dict")
    assert await c._restore_runtime_acc() is False


@pytest.mark.asyncio
async def test_restore_runtime_acc_wrong_day() -> None:
    c = _make_coord()
    c.db = AsyncMock()
    c.db.async_get_model_state = AsyncMock(
        return_value={"day": "2000-01-01"}
    )
    assert await c._restore_runtime_acc() is False


@pytest.mark.asyncio
async def test_restore_runtime_acc_happy() -> None:
    c = _make_coord()
    today = _today()
    c.db = AsyncMock()
    c.db.async_get_model_state = AsyncMock(
        return_value={
            "day": today,
            "buh_step1_s": 120.0,
            "buh_step2_s": 60.0,
            "defrost_count": 3,
            "defrost_duration_s": 240.0,
            "last_defrost_ts": 1000.0,
        }
    )
    assert await c._restore_runtime_acc() is True
    assert c._buh_step1_s == 120.0
    assert c._buh_step2_s == 60.0
    assert c._defrost_count_today == 3
    assert c._defrost_duration_s == 240.0
    assert c._last_defrost_ts == 1000.0
    assert c._runtime_day_key == today


@pytest.mark.asyncio
async def test_restore_runtime_acc_exception() -> None:
    c = _make_coord()
    c.db = AsyncMock()
    c.db.async_get_model_state = AsyncMock(
        side_effect=RuntimeError("boom")
    )
    assert await c._restore_runtime_acc() is False


# ---------- _restore_energy_acc ----------

@pytest.mark.asyncio
async def test_restore_energy_acc_no_db() -> None:
    assert await _make_coord()._restore_energy_acc() is False


@pytest.mark.asyncio
async def test_restore_energy_acc_payload_none() -> None:
    c = _make_coord()
    c.db = AsyncMock()
    c.db.async_get_model_state = AsyncMock(return_value=None)
    assert await c._restore_energy_acc() is False


@pytest.mark.asyncio
async def test_restore_energy_acc_wrong_day() -> None:
    c = _make_coord()
    c.db = AsyncMock()
    c.db.async_get_model_state = AsyncMock(
        return_value={"day": "2000-01-01"}
    )
    assert await c._restore_energy_acc() is False


@pytest.mark.asyncio
async def test_restore_energy_acc_happy() -> None:
    c = _make_coord()
    today = _today()
    c.db = AsyncMock()
    c.db.async_get_model_state = AsyncMock(
        return_value={
            "day": today,
            "heating_th_kwh": 1.5,
            "heating_el_kwh": 0.3,
            "dhw_th_kwh": 2.0,
            "dhw_el_kwh": 0.4,
            "cooling_th_kwh": 0.0,
            "cooling_el_kwh": 0.0,
        }
    )
    assert await c._restore_energy_acc() is True
    assert c._energy_acc["heating"]["th"] == 1.5
    assert c._energy_acc["heating"]["el"] == 0.3
    assert c._energy_acc["dhw"]["th"] == 2.0
    assert c._energy_acc["dhw"]["el"] == 0.4
    assert c._energy_acc["cooling"]["th"] == 0.0
    assert c._energy_day_key == today


@pytest.mark.asyncio
async def test_restore_energy_acc_exception() -> None:
    c = _make_coord()
    c.db = AsyncMock()
    c.db.async_get_model_state = AsyncMock(
        side_effect=RuntimeError("boom")
    )
    assert await c._restore_energy_acc() is False


# ---------- wiring ----------

def test_setup_hook_calls_restores_in_order() -> None:
    src = Path(
        "custom_components/daikin_cycle_ml/coordinator.py"
    ).read_text()
    idx_det = src.index("await self._restore_detector_state()")
    idx_rt = src.index("await self._restore_runtime_acc()")
    idx_el = src.index("await self._restore_energy_acc()")
    assert idx_det < idx_rt < idx_el
