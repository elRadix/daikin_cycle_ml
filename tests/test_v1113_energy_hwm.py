"""v1.11.3: monotonic energy accumulators (total_increasing contract)."""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.localtime(time.time()))


def _make_coord() -> DaikinCycleMLCoordinator:
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
        "dhw":     {"th": 0.0, "el": 0.0},
        "cooling": {"th": 0.0, "el": 0.0},
    }
    c._energy_hwm = {
        "heating": {"th": 0.0, "el": 0.0},
        "dhw":     {"th": 0.0, "el": 0.0},
        "cooling": {"th": 0.0, "el": 0.0},
    }
    return c


def test_hwm_holds_when_acc_lowered():
    c = _make_coord()
    c._energy_acc["heating"]["th"] = 12.28
    assert c._energy_hwm["heating"]["th"] == 0.0


def test_merge_preserves_memory_when_db_stale():
    c = _make_coord()
    c._energy_acc["heating"]["th"] = 12.45
    c._energy_hwm["heating"]["th"] = 12.45
    loaded = {"th": 12.28, "el": 0.0}
    for k in ("th", "el"):
        c._energy_acc["heating"][k] = max(c._energy_acc["heating"][k], loaded[k])
        if c._energy_acc["heating"][k] > c._energy_hwm["heating"][k]:
            c._energy_hwm["heating"][k] = c._energy_acc["heating"][k]
    assert c._energy_acc["heating"]["th"] == 12.45
    assert c._energy_hwm["heating"]["th"] == 12.45


def test_ensure_energy_acc_keeps_existing_hwm():
    c = _make_coord()
    c._energy_hwm = {
        "heating": {"th": 99.0, "el": 5.0},
        "dhw":     {"th": 0.0,  "el": 0.0},
        "cooling": {"th": 0.0,  "el": 0.0},
    }
    c._ensure_energy_acc()
    assert c._energy_hwm["heating"]["th"] == 99.0
    assert c._energy_hwm["heating"]["el"] == 5.0


def test_ensure_energy_acc_lazy_init_when_new():
    c = object.__new__(DaikinCycleMLCoordinator)
    c._energy_acc = {
        "heating": {"th": 0.0, "el": 0.0},
        "dhw":     {"th": 0.0, "el": 0.0},
        "cooling": {"th": 0.0, "el": 0.0},
    }
    c._ensure_energy_acc()
    assert hasattr(c, "_energy_hwm")
    assert c._energy_hwm["heating"]["th"] == 0.0


def test_restore_same_day_keeps_higher_memory():
    c = _make_coord()
    today = _today()
    c._energy_day_key = today
    c._energy_acc = {
        "heating": {"th": 12.45, "el": 2.0},
        "dhw":     {"th": 0.0,   "el": 0.0},
        "cooling": {"th": 0.0,   "el": 0.0},
    }
    c._energy_hwm = {
        "heating": {"th": 12.45, "el": 2.0},
        "dhw":     {"th": 0.0,   "el": 0.0},
        "cooling": {"th": 0.0,   "el": 0.0},
    }
    c.db = AsyncMock()
    c.db.async_get_model_state = AsyncMock(return_value={
        "day": today,
        "heating_th_kwh": 12.28, "heating_el_kwh": 1.9,
        "dhw_th_kwh": 0.0, "dhw_el_kwh": 0.0,
        "cooling_th_kwh": 0.0, "cooling_el_kwh": 0.0,
    })
    ok = asyncio.run(c._restore_energy_acc())
    assert ok is True
    assert c._energy_acc["heating"]["th"] == 12.45
    assert c._energy_acc["heating"]["el"] == 2.0


def test_restore_same_day_raises_mem_to_db_when_db_higher():
    c = _make_coord()
    today = _today()
    c._energy_day_key = today
    c._energy_acc = {
        "heating": {"th": 1.0, "el": 0.2},
        "dhw":     {"th": 0.0, "el": 0.0},
        "cooling": {"th": 0.0, "el": 0.0},
    }
    c._energy_hwm = {
        "heating": {"th": 1.0, "el": 0.2},
        "dhw":     {"th": 0.0, "el": 0.0},
        "cooling": {"th": 0.0, "el": 0.0},
    }
    c.db = AsyncMock()
    c.db.async_get_model_state = AsyncMock(return_value={
        "day": today,
        "heating_th_kwh": 5.5, "heating_el_kwh": 1.1,
        "dhw_th_kwh": 0.0, "dhw_el_kwh": 0.0,
        "cooling_th_kwh": 0.0, "cooling_el_kwh": 0.0,
    })
    ok = asyncio.run(c._restore_energy_acc())
    assert ok is True
    assert c._energy_acc["heating"]["th"] == 5.5
    assert c._energy_hwm["heating"]["th"] == 5.5


def test_persist_self_heal_syncs_hwm():
    c = _make_coord()
    today = _today()
    c._energy_day_key = today
    c._energy_acc = {
        "heating": {"th": 1.0, "el": 0.2},
        "dhw":     {"th": 0.0, "el": 0.0},
        "cooling": {"th": 0.0, "el": 0.0},
    }
    c._energy_hwm = {
        "heating": {"th": 1.0, "el": 0.2},
        "dhw":     {"th": 0.0, "el": 0.0},
        "cooling": {"th": 0.0, "el": 0.0},
    }
    c.db = AsyncMock()
    c.db.async_get_model_state = AsyncMock(return_value={
        "day": today,
        "heating_th_kwh": 8.0, "heating_el_kwh": 2.0,
        "dhw_th_kwh": 0.0, "dhw_el_kwh": 0.0,
        "cooling_th_kwh": 0.0, "cooling_el_kwh": 0.0,
    })
    c.db.async_set_model_state = AsyncMock()
    asyncio.run(c._persist_energy_acc())
    assert c._energy_acc["heating"]["th"] == 8.0
    assert c._energy_hwm["heating"]["th"] == 8.0
    c.db.async_set_model_state.assert_not_called()


class _DetRunning:
    state = "running"


def test_tick_energy_advances_hwm():
    c = _make_coord()
    c._last_energy_tick_ts = 100.0
    c.detector = _DetRunning()
    attrs = {"BUH Step1": False, "BUH Step2": False}
    c._tick_energy(attrs, now=200.0, mode="heating", power_w=2000.0, cop=4.0)
    th_after = c._energy_acc["heating"]["th"]
    el_after = c._energy_acc["heating"]["el"]
    assert th_after > 0.0
    assert el_after > 0.0
    assert c._energy_hwm["heating"]["th"] == th_after
    assert c._energy_hwm["heating"]["el"] == el_after


def test_tick_energy_kw_el_none_branch():
    c = _make_coord()
    c._last_energy_tick_ts = 100.0
    c.detector = _DetRunning()
    attrs = {
        "BUH Step1": False,
        "BUH Step2": False,
        "Flow sensor (l/min)": 15.0,
        "Leaving water temp. after BUH (R2T)": 35.0,
        "Inlet water temp.(R4T)": 30.0,
        "INV frequency (rps)": 22.0,
    }
    c._tick_energy(attrs, now=200.0, mode="heating", power_w=None, cop=None)
    assert c._energy_acc["heating"]["el"] == 0.0


def test_tick_energy_th_hwm_already_higher_false_branch():
    """hwm["th"] already > acc["th"] → skip hwm update (False branch)."""
    c = _make_coord()
    c._last_energy_tick_ts = 100.0
    c.detector = _DetRunning()
    # Pre-set hwm higher than what a single tick will add
    c._energy_hwm["heating"]["th"] = 100.0
    c._energy_hwm["heating"]["el"] = 100.0
    attrs = {"BUH Step1": False, "BUH Step2": False}
    c._tick_energy(attrs, now=200.0, mode="heating", power_w=2000.0, cop=4.0)
    # acc grew, but did not exceed hwm → hwm unchanged
    assert c._energy_acc["heating"]["th"] > 0.0
    assert c._energy_hwm["heating"]["th"] == 100.0
    assert c._energy_hwm["heating"]["el"] == 100.0
