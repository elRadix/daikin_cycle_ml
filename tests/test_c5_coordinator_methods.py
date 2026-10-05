"""v1.6.0-C5 coordinator method coverage: accumulators + persist + tick."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.const import (
    ATTR_BUH_STEP1,
    ATTR_BUH_STEP2,
    ATTR_DEFROST_OPERATION,
    ATTR_INV_FREQUENCY_RPS,
)
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
    c._prev_defrost = False
    c._defrost_start_ts = None
    c._defrost_count_today = 0
    c._defrost_duration_s = 0.0
    c._last_defrost_ts = 0.0
    c._last_runtime_tick_ts = 0.0
    c._last_energy_tick_ts = 0.0
    return c


def _zero_acc():
    return {
        "heating": {"th": 0.0, "el": 0.0},
        "dhw": {"th": 0.0, "el": 0.0},
        "cooling": {"th": 0.0, "el": 0.0},
    }


def test_ensure_energy_acc_lazy_init():
    c = _bare()
    c.__dict__.pop("_energy_acc", None)
    acc = c._ensure_energy_acc()
    assert acc["heating"] == {"th": 0.0, "el": 0.0}
    assert c._ensure_energy_acc() is acc


def test_ensure_energy_acc_uses_existing():
    c = _bare()
    seeded = _zero_acc()
    seeded["heating"]["th"] = 42.0
    c._energy_acc = seeded
    assert c._ensure_energy_acc() is seeded


def test_energy_snapshot_returns_deep_copy():
    c = _bare()
    c._energy_acc = _zero_acc()
    snap = c.energy_snapshot
    snap["heating"]["th"] = 99.0
    assert c._energy_acc["heating"]["th"] == 0.0


@pytest.mark.asyncio
async def test_persist_runtime_acc_db_none_returns():
    c = _bare(db=None, runtime_day_key="2026-10-05")
    await c._persist_runtime_acc()


@pytest.mark.asyncio
async def test_persist_runtime_acc_empty_day_returns():
    db = MagicMock()
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db, runtime_day_key="")
    await c._persist_runtime_acc()
    db.async_set_model_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_persist_runtime_acc_success():
    db = MagicMock()
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db, runtime_day_key="2026-10-05")
    c._buh_step1_s = 10.0
    c._buh_step2_s = 20.0
    c._defrost_count_today = 3
    c._defrost_duration_s = 300.0
    c._last_defrost_ts = 999.0
    await c._persist_runtime_acc()
    db.async_set_model_state.assert_awaited_once()
    key, payload = db.async_set_model_state.call_args[0]
    assert key == "runtime_acc.2026-10-05"
    assert payload["buh_step1_s"] == 10.0
    assert payload["defrost_count"] == 3


@pytest.mark.asyncio
async def test_persist_runtime_acc_swallows_exception():
    db = MagicMock()
    db.async_set_model_state = AsyncMock(side_effect=RuntimeError("x"))
    c = _bare(db=db, runtime_day_key="2026-10-05")
    await c._persist_runtime_acc()


@pytest.mark.asyncio
async def test_persist_energy_acc_db_none_returns():
    c = _bare(db=None, energy_day_key="2026-10-05")
    await c._persist_energy_acc()


@pytest.mark.asyncio
async def test_persist_energy_acc_empty_day_returns():
    db = MagicMock()
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db, energy_day_key="")
    await c._persist_energy_acc()
    db.async_set_model_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_persist_energy_acc_success():
    db = MagicMock()
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db, energy_day_key="2026-10-05")
    c._energy_acc = {
        "heating": {"th": 1.0, "el": 0.3},
        "dhw": {"th": 2.0, "el": 0.6},
        "cooling": {"th": 0.0, "el": 0.0},
    }
    await c._persist_energy_acc()
    db.async_set_model_state.assert_awaited_once()
    key, payload = db.async_set_model_state.call_args[0]
    assert key == "energy_acc.2026-10-05"
    assert payload["heating_th_kwh"] == 1.0
    assert payload["dhw_el_kwh"] == 0.6


@pytest.mark.asyncio
async def test_persist_energy_acc_swallows_exception():
    db = MagicMock()
    db.async_set_model_state = AsyncMock(side_effect=RuntimeError("x"))
    c = _bare(db=db, energy_day_key="2026-10-05")
    await c._persist_energy_acc()


def test_maybe_reset_first_call_initializes_day():
    c = _bare()
    now = time.time()
    c._maybe_reset_daily_accumulators(now)
    day = time.strftime("%Y-%m-%d", time.localtime(now))
    assert c._runtime_day_key == day
    assert c._energy_day_key == day


def test_maybe_reset_same_day_noop():
    c = _bare()
    now = time.time()
    day = time.strftime("%Y-%m-%d", time.localtime(now))
    c._runtime_day_key = day
    c._buh_step1_s = 100.0
    c._maybe_reset_daily_accumulators(now)
    assert c._buh_step1_s == 100.0


def test_tick_buh_step1_on():
    c = _bare()
    c._last_runtime_tick_ts = 1000.0
    c._tick_buh_and_defrost({ATTR_BUH_STEP1: True}, 1030.0)
    assert c._buh_step1_s == 30.0


def test_tick_buh_step2_on():
    c = _bare()
    c._last_runtime_tick_ts = 1000.0
    c._tick_buh_and_defrost({ATTR_BUH_STEP2: True}, 1060.0)
    assert c._buh_step2_s == 60.0


def test_tick_buh_both_on():
    c = _bare()
    c._last_runtime_tick_ts = 1000.0
    c._tick_buh_and_defrost(
        {ATTR_BUH_STEP1: True, ATTR_BUH_STEP2: True}, 1090.0
    )
    assert c._buh_step1_s == 90.0
    assert c._buh_step2_s == 90.0


def test_tick_defrost_on_transition():
    c = _bare()
    c._last_runtime_tick_ts = 1000.0
    c._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: True}, 1030.0)
    assert c._defrost_count_today == 1
    assert c._defrost_start_ts == 1030.0
    assert c._last_defrost_ts == 1030.0


def test_tick_defrost_off_transition():
    c = _bare()
    c._last_runtime_tick_ts = 1000.0
    c._prev_defrost = True
    c._defrost_start_ts = 1000.0
    c._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: False}, 1030.0)
    assert c._defrost_duration_s == 30.0
    assert c._defrost_start_ts is None


def test_tick_defrost_continue_live_tally():
    c = _bare()
    c._last_runtime_tick_ts = 1000.0
    c._prev_defrost = True
    c._defrost_start_ts = 900.0
    c._defrost_duration_s = 10.0
    c._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: True}, 1060.0)
    assert c._defrost_duration_s == 160.0


def test_tick_buh_swallows_exception():
    class Bad:
        def get(self, k):
            raise RuntimeError("x")
    c = _bare()
    c._last_runtime_tick_ts = 1000.0
    c._tick_buh_and_defrost(Bad(), 1030.0)


def test_tick_energy_power_cop_path():
    c = _bare()
    c._last_energy_tick_ts = 1000.0
    c._energy_acc = _zero_acc()
    c._tick_energy(
        {ATTR_INV_FREQUENCY_RPS: 50.0}, 1030.0,
        mode="heating", power_w=2000.0, cop=4.0,
    )
    assert c._energy_acc["heating"]["th"] > 0.0
    assert c._energy_acc["heating"]["el"] > 0.0


def test_tick_energy_rps_cop_fallback():
    c = _bare()
    c._last_energy_tick_ts = 1000.0
    c._energy_acc = _zero_acc()
    c._tick_energy(
        {ATTR_INV_FREQUENCY_RPS: 50.0}, 1030.0,
        mode="heating", power_w=None, cop=3.0,
    )
    assert c._energy_acc["heating"]["th"] > 0.0
    assert c._energy_acc["heating"]["el"] > 0.0


def test_tick_energy_idle_returns():
    c = _bare()
    c._last_energy_tick_ts = 1000.0
    c._energy_acc = _zero_acc()
    c._tick_energy({}, 1030.0, mode="heating", power_w=None, cop=None)
    assert c._energy_acc["heating"]["th"] == 0.0


def test_tick_energy_zero_dt_returns():
    c = _bare()
    c._last_energy_tick_ts = 1000.0
    c._energy_acc = _zero_acc()
    c._tick_energy(
        {ATTR_INV_FREQUENCY_RPS: 50.0}, 1000.0,
        mode="heating", power_w=2000.0, cop=4.0,
    )
    assert c._energy_acc["heating"]["th"] == 0.0


def test_tick_energy_unknown_mode_falls_back():
    c = _bare()
    c._last_energy_tick_ts = 1000.0
    c._energy_acc = _zero_acc()
    c._tick_energy(
        {ATTR_INV_FREQUENCY_RPS: 50.0}, 1030.0,
        mode="foo", power_w=2000.0, cop=4.0,
    )
    assert c._energy_acc["heating"]["th"] > 0.0


def test_tick_energy_swallows_exception():
    class Bad:
        def get(self, k):
            raise RuntimeError("x")
    c = _bare()
    c._last_energy_tick_ts = 1000.0
    c._tick_energy(
        Bad(), 1030.0, mode="heating", power_w=2000.0, cop=4.0,
    )


def test_runtime_snapshot_shape():
    c = _bare()
    c._buh_step1_s = 10.0
    c._buh_step2_s = 20.0
    c._defrost_count_today = 3
    c._defrost_duration_s = 300.0
    c._last_defrost_ts = 999.0
    snap = c.runtime_snapshot
    assert snap["buh_step1_s"] == 10.0
    assert snap["defrost_count"] == 3.0
    assert snap["last_defrost_ts"] == 999.0

def test_tick_defrost_off_without_start_ts():
    """Branch 907->910: off-transition waarbij _defrost_start_ts None is."""
    c = _bare()
    c._last_runtime_tick_ts = 1000.0
    c._prev_defrost = True
    c._defrost_start_ts = None
    c._tick_buh_and_defrost({ATTR_DEFROST_OPERATION: False}, 1030.0)
    assert c._defrost_duration_s == 0.0
    assert c._defrost_start_ts is None


def test_tick_energy_no_kw_el_via_rps():
    """Branches 950->952 en 954->exit: geen kw_el, wel thermal via rps."""
    c = _bare()
    c._last_energy_tick_ts = 1000.0
    c._energy_acc = _zero_acc()
    c._tick_energy(
        {ATTR_INV_FREQUENCY_RPS: 50.0}, 1030.0,
        mode="heating", power_w=None, cop=None,
    )
    assert c._energy_acc["heating"]["th"] > 0.0
    assert c._energy_acc["heating"]["el"] == 0.0
