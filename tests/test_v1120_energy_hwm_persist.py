"""v1.12.0: energy HWM persistence tests (issue #101 sub-item 3a)."""
from __future__ import annotations

import datetime as _dt
from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator

_MODES = ("heating", "dhw", "cooling")


def _today() -> str:
    return _dt.date.today().strftime("%Y-%m-%d")


def _zero() -> dict[str, dict[str, float]]:
    return {m: {"th": 0.0, "el": 0.0} for m in _MODES}


def _make_coord(
    acc: dict[str, dict[str, float]] | None = None,
    hwm: dict[str, dict[str, float]] | None = None,
    day: str | None = None,
) -> DaikinCycleMLCoordinator:
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.db = MagicMock()
    c.db.async_get_model_state = AsyncMock(return_value=None)
    c.db.async_set_model_state = AsyncMock(return_value=None)
    c._energy_acc = acc if acc is not None else _zero()
    c._energy_hwm = hwm if hwm is not None else _zero()
    c._energy_day_key = day if day is not None else _today()
    return c


async def test_persist_writes_hwm_fields():
    acc = _zero()
    acc["heating"] = {"th": 5.0, "el": 1.0}
    hwm = _zero()
    hwm["heating"] = {"th": 7.5, "el": 1.5}
    c = _make_coord(acc=acc, hwm=hwm)
    await c._persist_energy_acc()
    c.db.async_set_model_state.assert_called_once()
    payload = c.db.async_set_model_state.call_args.args[1]
    assert payload["heating_th_kwh"] == 5.0
    assert payload["heating_el_kwh"] == 1.0
    assert payload["heating_th_hwm_kwh"] == 7.5
    assert payload["heating_el_hwm_kwh"] == 1.5


async def test_restore_new_day_sets_hwm_from_db():
    today = _today()
    c = _make_coord(day="2026-01-01")
    c.db.async_get_model_state = AsyncMock(return_value={
        "day": today,
        "heating_th_kwh": 10.0, "heating_el_kwh": 2.0,
        "heating_th_hwm_kwh": 15.0, "heating_el_hwm_kwh": 3.0,
        "dhw_th_kwh": 0.0, "dhw_el_kwh": 0.0,
        "dhw_th_hwm_kwh": 0.0, "dhw_el_hwm_kwh": 0.0,
        "cooling_th_kwh": 0.0, "cooling_el_kwh": 0.0,
        "cooling_th_hwm_kwh": 0.0, "cooling_el_hwm_kwh": 0.0,
    })
    assert await c._restore_energy_acc() is True
    assert c._energy_acc["heating"]["th"] == 10.0
    assert c._energy_hwm["heating"]["th"] == 15.0
    assert c._energy_hwm["heating"]["el"] == 3.0


async def test_restore_same_day_merges_hwm_max():
    today = _today()
    # Same-day restore: hwm in memory higher than db -> memory wins (max)
    acc_mem = _zero()
    acc_mem["heating"] = {"th": 5.0, "el": 1.0}
    hwm_mem = _zero()
    hwm_mem["heating"] = {"th": 20.0, "el": 15.0}
    c = _make_coord(acc=acc_mem, hwm=hwm_mem, day=today)
    c.db.async_get_model_state = AsyncMock(return_value={
        "day": today,
        "heating_th_kwh": 5.0, "heating_el_kwh": 1.0,
        "heating_th_hwm_kwh": 8.0, "heating_el_hwm_kwh": 3.0,
    })
    assert await c._restore_energy_acc() is True
    # max() preserves memory high HWM
    assert c._energy_hwm["heating"]["th"] == 20.0
    assert c._energy_hwm["heating"]["el"] == 15.0


async def test_restore_same_day_lifts_hwm_from_db():
    today = _today()
    acc_mem = _zero()
    acc_mem["heating"] = {"th": 5.0, "el": 1.0}
    hwm_mem = _zero()
    hwm_mem["heating"] = {"th": 5.0, "el": 1.0}
    c = _make_coord(acc=acc_mem, hwm=hwm_mem, day=today)
    c.db.async_get_model_state = AsyncMock(return_value={
        "day": today,
        "heating_th_kwh": 5.0, "heating_el_kwh": 1.0,
        "heating_th_hwm_kwh": 15.0, "heating_el_hwm_kwh": 4.0,
    })
    assert await c._restore_energy_acc() is True
    # db hwm higher -> restored hwm wins
    assert c._energy_hwm["heating"]["th"] == 15.0
    assert c._energy_hwm["heating"]["el"] == 4.0


async def test_selfheal_bumps_hwm_from_db():
    today = _today()
    acc_mem = _zero()
    acc_mem["heating"] = {"th": 5.0, "el": 1.0}
    hwm_mem = _zero()
    hwm_mem["heating"] = {"th": 5.5, "el": 1.5}
    c = _make_coord(acc=acc_mem, hwm=hwm_mem, day=today)
    # DB reports acc=10/2 (higher than mem=5/1) -> self-heal triggers
    c.db.async_get_model_state = AsyncMock(return_value={
        "day": today,
        "heating_th_kwh": 10.0, "heating_el_kwh": 2.0,
        "heating_th_hwm_kwh": 12.0, "heating_el_hwm_kwh": 2.5,
    })
    await c._persist_energy_acc()
    # Self-heal: acc replaced by DB, hwm raised to max(mem, db, db_acc)
    assert c._energy_acc["heating"]["th"] == 10.0
    assert c._energy_acc["heating"]["el"] == 2.0
    assert c._energy_hwm["heating"]["th"] == 12.0  # loaded_hwm highest
    assert c._energy_hwm["heating"]["el"] == 2.5   # max(1.5, 2.5, 2.0)
    # Self-heal returns without writing: no set_model_state call
    c.db.async_set_model_state.assert_not_called()
