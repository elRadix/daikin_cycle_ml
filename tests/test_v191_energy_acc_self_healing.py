"""v1.9.1 I9 — energy/runtime accumulator self-healing + restore retry tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)


def _bare(**overrides):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.db = overrides.get("db")
    c._runtime_day_key = overrides.get("runtime_day_key", "")
    c._energy_day_key = overrides.get("energy_day_key", "")
    c._buh_step1_s = 0.0
    c._buh_step2_s = 0.0
    c._defrost_count_today = 0
    c._defrost_duration_s = 0.0
    c._last_defrost_ts = 0.0
    c._energy_acc = {
        "heating": {"th": 0.0, "el": 0.0},
        "dhw": {"th": 0.0, "el": 0.0},
        "cooling": {"th": 0.0, "el": 0.0},
    }
    c._last_runtime_persist_ts = 0.0
    c._last_energy_persist_ts = 0.0
    return c


@pytest.mark.asyncio
async def test_persist_energy_restores_from_db_if_higher():
    """DB has real data, memory is zero — restore from DB, do NOT overwrite."""
    db = MagicMock()
    db.async_get_model_state = AsyncMock(return_value={
        "day": "2026-10-05",
        "heating_th_kwh": 5.0,
        "heating_el_kwh": 1.5,
        "dhw_th_kwh": 2.0,
        "dhw_el_kwh": 0.6,
        "cooling_th_kwh": 0.0,
        "cooling_el_kwh": 0.0,
    })
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db, energy_day_key="2026-10-05")
    await c._persist_energy_acc()
    db.async_set_model_state.assert_not_awaited()
    assert c._energy_acc["heating"]["th"] == 5.0
    assert c._energy_acc["heating"]["el"] == 1.5
    assert c._energy_acc["dhw"]["th"] == 2.0


@pytest.mark.asyncio
async def test_persist_energy_overwrites_when_mem_higher():
    """Memory > DB → normal persist runs (no restore)."""
    db = MagicMock()
    db.async_get_model_state = AsyncMock(return_value={
        "day": "2026-10-05",
        "heating_th_kwh": 1.0,
        "heating_el_kwh": 0.3,
        "dhw_th_kwh": 0.0, "dhw_el_kwh": 0.0,
        "cooling_th_kwh": 0.0, "cooling_el_kwh": 0.0,
    })
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db, energy_day_key="2026-10-05")
    c._energy_acc["heating"]["th"] = 9.0
    await c._persist_energy_acc()
    db.async_set_model_state.assert_awaited_once()


@pytest.mark.asyncio
async def test_persist_energy_ignores_db_day_mismatch():
    """DB has different day → treat as no existing data, normal persist."""
    db = MagicMock()
    db.async_get_model_state = AsyncMock(return_value={
        "day": "2026-10-04",
        "heating_th_kwh": 99.0,
    })
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db, energy_day_key="2026-10-05")
    c._energy_acc["heating"]["th"] = 1.0
    await c._persist_energy_acc()
    db.async_set_model_state.assert_awaited_once()


@pytest.mark.asyncio
async def test_persist_runtime_restores_from_db_if_higher():
    db = MagicMock()
    db.async_get_model_state = AsyncMock(return_value={
        "day": "2026-10-05",
        "buh_step1_s": 60.0,
        "buh_step2_s": 120.0,
        "defrost_count": 3,
        "defrost_duration_s": 300.0,
        "last_defrost_ts": 999.0,
    })
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db, runtime_day_key="2026-10-05")
    await c._persist_runtime_acc()
    db.async_set_model_state.assert_not_awaited()
    assert c._buh_step1_s == 60.0
    assert c._defrost_count_today == 3


@pytest.mark.asyncio
async def test_restore_energy_logs_payload_not_dict():
    """Silent path now logs; still returns False."""
    db = MagicMock()
    db.async_get_model_state = AsyncMock(return_value="not a dict")
    c = _bare(db=db)
    with patch(
        "custom_components.daikin_cycle_ml.coordinator._LOGGER"
    ) as log:
        ok = await c._restore_energy_acc()
    assert ok is False
    assert log.warning.called


@pytest.mark.asyncio
async def test_restore_energy_logs_day_mismatch():
    db = MagicMock()
    db.async_get_model_state = AsyncMock(return_value={
        "day": "2026-01-01",
    })
    c = _bare(db=db)
    with patch(
        "custom_components.daikin_cycle_ml.coordinator._LOGGER"
    ) as log:
        ok = await c._restore_energy_acc()
    assert ok is False
    assert log.warning.called


@pytest.mark.asyncio
async def test_restore_runtime_logs_payload_not_dict():
    db = MagicMock()
    db.async_get_model_state = AsyncMock(return_value=42)
    c = _bare(db=db)
    with patch(
        "custom_components.daikin_cycle_ml.coordinator._LOGGER"
    ) as log:
        ok = await c._restore_runtime_acc()
    assert ok is False
    assert log.warning.called


@pytest.mark.asyncio
async def test_restore_runtime_logs_day_mismatch():
    db = MagicMock()
    db.async_get_model_state = AsyncMock(return_value={
        "day": "2026-01-01",
    })
    c = _bare(db=db)
    with patch(
        "custom_components.daikin_cycle_ml.coordinator._LOGGER"
    ) as log:
        ok = await c._restore_runtime_acc()
    assert ok is False
    assert log.warning.called


@pytest.mark.asyncio
async def test_persist_runtime_overwrites_when_mem_higher():
    """Memory > DB → normal persist runs (no restore).

    Covers the false branch of the runtime persist inner guard
    (coordinator.py line 1138 -> 1153).
    """
    db = MagicMock()
    db.async_get_model_state = AsyncMock(return_value={
        "day": "2026-10-05",
        "buh_step1_s": 10.0,
        "buh_step2_s": 20.0,
        "defrost_count": 3,
        "defrost_duration_s": 300.0,
        "last_defrost_ts": 999.0,
    })
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db, runtime_day_key="2026-10-05")
    c._buh_step1_s = 999.0
    await c._persist_runtime_acc()
    db.async_set_model_state.assert_awaited_once()
    key, payload = db.async_set_model_state.call_args[0]
    assert key == "runtime_acc.2026-10-05"
    assert payload["buh_step1_s"] == 999.0
