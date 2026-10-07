"""R306/R307 coverage: _float_list, restore state edge, coordinator wiring."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.const import (
    DETECTOR_STATE_KEY,
    STATE_IDLE,
    STATE_RUNNING,
)
from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)
from custom_components.daikin_cycle_ml.engine.cycle_detector import (
    CycleDetector,
    _float_list,
)


def _bare(db=None):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.db = db
    c.detector = CycleDetector()
    c.options = {}
    return c


# ---------- _float_list coverage ----------

def test_float_list_non_list_returns_empty() -> None:
    assert _float_list(None) == []
    assert _float_list("x") == []
    assert _float_list(42) == []


def test_float_list_bool_and_non_numeric_skipped() -> None:
    assert _float_list([1.0, True, "x", None, 2.5, False]) == [1.0, 2.5]


def test_float_list_all_rejected_returns_empty() -> None:
    assert _float_list([True, False, "x", None]) == []


def test_restore_from_dict_state_not_running() -> None:
    d = CycleDetector()
    d.restore_from_dict({"state": STATE_IDLE, "start_ts": 1000.0}, now=1100.0)
    assert d.state == STATE_IDLE


# ---------- coordinator _persist_detector_state ----------

@pytest.mark.asyncio
async def test_persist_no_db_returns_early() -> None:
    c = _bare(db=None)
    await c._persist_detector_state()


@pytest.mark.asyncio
async def test_persist_writes_running_payload() -> None:
    db = MagicMock()
    db.async_set_model_state = AsyncMock()
    c = _bare(db=db)
    c.detector._state = STATE_RUNNING
    c.detector._start_ts = 1000.0
    c.detector._mode = "heating"
    await c._persist_detector_state()
    db.async_set_model_state.assert_awaited_once()
    key, payload = db.async_set_model_state.call_args[0]
    assert key == DETECTOR_STATE_KEY
    assert payload["state"] == STATE_RUNNING


@pytest.mark.asyncio
async def test_persist_db_raises_swallowed() -> None:
    db = MagicMock()
    db.async_set_model_state = AsyncMock(side_effect=RuntimeError("x"))
    c = _bare(db=db)
    await c._persist_detector_state()


# ---------- coordinator _restore_detector_state ----------

@pytest.mark.asyncio
async def test_restore_no_db() -> None:
    c = _bare(db=None)
    assert await c._restore_detector_state() is False


@pytest.mark.asyncio
async def test_restore_no_payload() -> None:
    db = MagicMock()
    db.async_get_model_state = AsyncMock(return_value=None)
    c = _bare(db=db)
    assert await c._restore_detector_state() is False


@pytest.mark.asyncio
async def test_restore_idle_payload_returns_false() -> None:
    db = MagicMock()
    db.async_get_model_state = AsyncMock(return_value={"state": STATE_IDLE})
    c = _bare(db=db)
    assert await c._restore_detector_state() is False


@pytest.mark.asyncio
async def test_restore_running_payload_returns_true() -> None:
    import time as _t
    now = _t.time()
    db = MagicMock()
    db.async_get_model_state = AsyncMock(return_value={
        "state": STATE_RUNNING,
        "start_ts": now - 60.0,
        "mode": "heating",
        "rps_samples": [20.0],
    })
    c = _bare(db=db)
    assert await c._restore_detector_state() is True
    assert c.detector.state == STATE_RUNNING


@pytest.mark.asyncio
async def test_restore_db_raises_swallowed() -> None:
    db = MagicMock()
    db.async_get_model_state = AsyncMock(side_effect=RuntimeError("x"))
    c = _bare(db=db)
    assert await c._restore_detector_state() is False
