"""#417: an HA restart during a run dropped the part before the restart.

prod-1 2026-11-18: COP samples 23:04-23:25 (compressor running), HA
restart 23:34:16, cycle 429 starts 23:34:26 (first tick). The restore ran
after the first refresh, whose tick had opened and persisted a new cycle.
A heating <-> DHW split never persisted its new cycle either.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.const import (
    ATTR_3WAY_VALVE,
    ATTR_INV_FREQUENCY_RPS,
    ATTR_IU_OPERATION_MODE,
    ATTR_OPERATION_MODE,
    DETECTOR_PERSIST_S,
    DETECTOR_STATE_KEY,
)
from custom_components.daikin_cycle_ml.engine.cycle_detector import CycleDetector
from tests.test_v2_restart_open_cycle_e2e import (
    _full_attrs,
    _mk_coord_with_db,
    _mk_db,
)


def _running_attrs(dhw: bool = False) -> dict:
    a = _full_attrs()
    a[ATTR_INV_FREQUENCY_RPS] = 28.0
    a[ATTR_3WAY_VALVE] = "ON" if dhw else "OFF"
    if dhw:
        a[ATTR_IU_OPERATION_MODE] = "DHW"
        a[ATTR_OPERATION_MODE] = "DHW"
    return a


async def _coord(db, attrs):
    c = await _mk_coord_with_db(db)
    c.detector = CycleDetector({}, dhw_present=True)
    state = MagicMock()
    state.attributes = attrs
    c.hass.states.get = MagicMock(return_value=state)
    return c


async def _close(db) -> None:
    await db.async_close()
    await asyncio.sleep(0.05)


async def _persisted_start(db):
    payload = await db.async_get_model_state(DETECTOR_STATE_KEY)
    return (payload or {}).get("start_ts")


async def test_first_tick_after_restart_keeps_pre_restart_start(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        start = time.time() - 34 * 60                 # 23:00 -> restart 23:34
        before = CycleDetector({}, dhw_present=True)
        before.update(_running_attrs(), now=start, power_w=1500.0)
        assert before.state == "running"
        await db.async_set_model_state(DETECTOR_STATE_KEY, before.to_dict())

        c = await _coord(db, _running_attrs())          # new instance, idle
        await c._async_update_data()                    # first refresh
        assert c.detector.state == "running"
        assert c.detector.snapshot()["start_ts"] == pytest.approx(start)
        assert await _persisted_start(db) == pytest.approx(start)
        # the setup hook's restore afterwards is a no-op
        assert await c._restore_detector_once() is False
        assert c.detector.snapshot()["start_ts"] == pytest.approx(start)
    finally:
        await _close(db)


async def test_split_persists_new_cycle(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        c = await _coord(db, _running_attrs())
        c._detector_restore_done = True
        t0 = time.time() - 3600
        c.detector.update(_running_attrs(), now=t0, power_w=1500.0)
        # DHW seen 60 s ago: the split debounce is satisfied on the next tick
        c.detector.update(_running_attrs(dhw=True), now=time.time() - 60,
                          power_w=1500.0)
        await db.async_set_model_state(DETECTOR_STATE_KEY, c.detector.to_dict())
        c._detector_persist_ts = time.time()            # periodic not due
        state = MagicMock()
        state.attributes = _running_attrs(dhw=True)     # heating -> DHW split
        c.hass.states.get = MagicMock(return_value=state)
        c._process_new_cycle = AsyncMock(return_value=None)
        await c._async_update_data()
        new_start = c.detector.snapshot()["start_ts"]
        assert new_start > t0 + 3000
        assert await _persisted_start(db) == pytest.approx(new_start)
    finally:
        await _close(db)


async def test_running_cycle_persisted_periodically(tmp_path):
    db = await _mk_db(tmp_path)
    try:
        c = await _coord(db, _running_attrs())
        c._detector_restore_done = True
        await c._async_update_data()                     # opens + persists
        first = c._detector_persist_ts
        await db.async_set_model_state(DETECTOR_STATE_KEY, {})
        await c._async_update_data()                     # not due yet
        assert await db.async_get_model_state(DETECTOR_STATE_KEY) == {}
        c._detector_persist_ts = first - DETECTOR_PERSIST_S - 1
        await c._async_update_data()                     # due
        assert await _persisted_start(db) == pytest.approx(
            c.detector.snapshot()["start_ts"])
    finally:
        await _close(db)


async def test_restore_once_without_db():
    c = MagicMock()
    c.db = None
    c._detector_restore_done = False
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
    )
    assert await DaikinCycleMLCoordinator._restore_detector_once(c) is False


# --- resume gap = downtime, not run age (prod-1 runs last up to 11 h) ---------


def _payload(start: float, seen: float | None) -> dict:
    d = CycleDetector({}, dhw_present=True)
    d.update(_running_attrs(), now=start, power_w=1500.0)
    p = d.to_dict()
    if seen is None:
        p.pop("last_seen_ts")
    else:
        p["last_seen_ts"] = seen
    return p


def test_long_run_restored_after_short_downtime():
    now = time.time()
    d = CycleDetector({}, dhw_present=True)
    d.restore_from_dict(_payload(now - 9 * 3600, now - 300), now)
    assert d.state == "running"
    assert d.snapshot()["start_ts"] == pytest.approx(now - 9 * 3600)


def test_long_downtime_abandons_cycle():
    now = time.time()
    d = CycleDetector({}, dhw_present=True)
    d.restore_from_dict(_payload(now - 9 * 3600, now - 7 * 3600), now)
    assert d.state == "idle"


@pytest.mark.parametrize("seen,expected", [(None, "idle"), (True, "idle")])
def test_payload_without_last_seen_uses_start(seen, expected):
    now = time.time()
    d = CycleDetector({}, dhw_present=True)
    d.restore_from_dict(_payload(now - 9 * 3600, seen), now)
    assert d.state == expected


def test_to_dict_carries_last_seen():
    d = CycleDetector({}, dhw_present=True)
    d.update(_running_attrs(), now=1000.0, power_w=1500.0)
    d.update(_running_attrs(), now=1030.0, power_w=1500.0)
    assert d.to_dict()["last_seen_ts"] == 1030.0
