"""I8: energy_acc / runtime_acc day-key decoupling."""
from __future__ import annotations
import time
from unittest.mock import AsyncMock, MagicMock
import pytest
from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator


def _bare():
    c = object.__new__(DaikinCycleMLCoordinator)
    c._runtime_day_key = ""
    c._energy_day_key = ""
    c._buh_step1_s = 0.0
    c._buh_step2_s = 0.0
    c._prev_defrost = False
    c._defrost_start_ts = None
    c._defrost_count_today = 0
    c._defrost_duration_s = 0.0
    c._energy_acc = {m: {"th": 0.0, "el": 0.0} for m in ("heating", "dhw", "cooling")}
    c._last_defrost_ts = None
    c.source_entity = "sensor.test"
    c._errors_total = 0
    return c


def _today():
    return time.strftime("%Y-%m-%d", time.localtime(time.time()))


def test_prod_scenario_runtime_empty_energy_today():
    c = _bare()
    c._runtime_day_key = ""
    c._energy_day_key = _today()
    c._energy_acc["heating"]["el"] = 6.89
    c._maybe_reset_daily_accumulators(time.time())
    assert c._runtime_day_key == _today()
    assert c._energy_day_key == _today()
    assert c._energy_acc["heating"]["el"] == 6.89


def test_prod_mirror_energy_empty_runtime_today():
    c = _bare()
    c._runtime_day_key = _today()
    c._energy_day_key = ""
    c._buh_step1_s = 42.0
    c._maybe_reset_daily_accumulators(time.time())
    assert c._energy_day_key == _today()
    assert c._buh_step1_s == 42.0


def test_both_stale_resets_both():
    c = _bare()
    c._runtime_day_key = "2020-01-01"
    c._energy_day_key = "2020-01-01"
    c._buh_step1_s = 100.0
    c._energy_acc["heating"]["el"] = 5.0
    c._maybe_reset_daily_accumulators(time.time())
    assert c._runtime_day_key == _today()
    assert c._energy_day_key == _today()
    assert c._buh_step1_s == 0.0
    assert c._energy_acc["heating"]["el"] == 0.0


def test_energy_only_stale_resets_energy_only():
    c = _bare()
    c._runtime_day_key = _today()
    c._energy_day_key = "2020-01-01"
    c._buh_step1_s = 100.0
    c._energy_acc["heating"]["el"] = 5.0
    c._maybe_reset_daily_accumulators(time.time())
    assert c._buh_step1_s == 100.0
    assert c._energy_acc["heating"]["el"] == 0.0


def test_runtime_only_stale_resets_runtime_only():
    c = _bare()
    c._runtime_day_key = "2020-01-01"
    c._energy_day_key = _today()
    c._buh_step1_s = 100.0
    c._energy_acc["heating"]["el"] = 5.0
    c._maybe_reset_daily_accumulators(time.time())
    assert c._buh_step1_s == 0.0
    assert c._energy_acc["heating"]["el"] == 5.0


def test_both_same_noop():
    c = _bare()
    c._runtime_day_key = _today()
    c._energy_day_key = _today()
    c._buh_step1_s = 100.0
    c._energy_acc["heating"]["el"] = 5.0
    c._maybe_reset_daily_accumulators(time.time())
    assert c._buh_step1_s == 100.0
    assert c._energy_acc["heating"]["el"] == 5.0


def _stub_update(c):
    c.store = MagicMock()
    c._maybe_reset_daily_accumulators = MagicMock()
    c.hass = MagicMock()
    c.hass.states.get.return_value = None


@pytest.mark.asyncio
async def test_update_persist_both_stale():
    c = _bare(); c.db = AsyncMock(); c.db.async_set_model_state = AsyncMock()
    _stub_update(c)
    c._runtime_day_key = "2020-01-01"
    c._energy_day_key = "2020-01-01"
    await c._async_update_data()
    assert c.db.async_set_model_state.await_count == 2


@pytest.mark.asyncio
async def test_update_persist_energy_only_when_runtime_empty():
    c = _bare(); c.db = AsyncMock(); c.db.async_set_model_state = AsyncMock()
    _stub_update(c)
    c._runtime_day_key = ""
    c._energy_day_key = "2020-01-01"
    await c._async_update_data()
    assert c.db.async_set_model_state.await_count == 1
    assert c.db.async_set_model_state.await_args_list[0].args[0].startswith("energy_acc.")


@pytest.mark.asyncio
async def test_update_persist_runtime_only_when_energy_empty():
    c = _bare(); c.db = AsyncMock(); c.db.async_set_model_state = AsyncMock()
    _stub_update(c)
    c._runtime_day_key = "2020-01-01"
    c._energy_day_key = ""
    await c._async_update_data()
    assert c.db.async_set_model_state.await_count == 1
    assert c.db.async_set_model_state.await_args_list[0].args[0].startswith("runtime_acc.")
