"""v1.12.5 #121: seed _last_cop_sample_ts from DB MAX(ts)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)


def _mk(db):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.db = db
    c._last_cop_sample_ts = 0.0
    c._cop_sample_seed_done = False
    c.cop_sensor_entity = "sensor.cop"
    c.hass = MagicMock()
    c.hass.states.get = MagicMock(return_value=None)
    return c


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_seed_from_max_ts():
    db = MagicMock()
    db.async_get_max_cop_sample_ts = AsyncMock(return_value=1792897000.0)
    c = _mk(db)
    await c._maybe_collect_cop_sample(1792897207.0)
    assert c._last_cop_sample_ts == 1792897000.0
    assert c._cop_sample_seed_done is True


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_seed_empty_db_stays_zero():
    db = MagicMock()
    db.async_get_max_cop_sample_ts = AsyncMock(return_value=None)
    c = _mk(db)
    await c._maybe_collect_cop_sample(1792897207.0)
    assert c._last_cop_sample_ts == 0.0
    assert c._cop_sample_seed_done is True


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_seed_error_falls_through():
    db = MagicMock()
    db.async_get_max_cop_sample_ts = AsyncMock(side_effect=RuntimeError("boom"))
    c = _mk(db)
    await c._maybe_collect_cop_sample(1792897207.0)
    assert c._last_cop_sample_ts == 0.0
    assert c._cop_sample_seed_done is True


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_seed_db_none_returns_early():
    c = _mk(None)
    await c._maybe_collect_cop_sample(1792897207.0)
    assert c._last_cop_sample_ts == 0.0
    assert c._cop_sample_seed_done is False


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_seed_skipped_when_already_done():
    db = MagicMock()
    db.async_get_max_cop_sample_ts = AsyncMock(return_value=1000.0)
    c = _mk(db)
    c._cop_sample_seed_done = True
    c._last_cop_sample_ts = 5000.0
    await c._maybe_collect_cop_sample(1792897207.0)
    assert c._last_cop_sample_ts == 5000.0
    db.async_get_max_cop_sample_ts.assert_not_called()


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_throttle_respected_after_seed():
    db = MagicMock()
    db.async_get_max_cop_sample_ts = AsyncMock(return_value=1792897200.0)
    c = _mk(db)
    await c._maybe_collect_cop_sample(1792897207.0)
    assert c._last_cop_sample_ts == 1792897200.0


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_collect_fires_after_seed_plus_301s():
    db = MagicMock()
    db.async_get_max_cop_sample_ts = AsyncMock(return_value=1000.0)
    c = _mk(db)
    await c._maybe_collect_cop_sample(1301.0)
    assert c._last_cop_sample_ts == 1000.0


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_restart_simulation_seed_runs_once():
    db = MagicMock()
    db.async_get_max_cop_sample_ts = AsyncMock(return_value=1792897000.0)
    c = _mk(db)
    await c._maybe_collect_cop_sample(1792897010.0)
    await c._maybe_collect_cop_sample(1792897050.0)
    assert c._last_cop_sample_ts == 1792897000.0
    assert db.async_get_max_cop_sample_ts.call_count == 1


# --- Real-method coverage (issue #121): exercises async_get_max_cop_sample_ts ---
import inspect as _inspect

import custom_components.daikin_cycle_ml.storage.db as _dbmod


def _real_db():
    for _name in dir(_dbmod):
        _obj = getattr(_dbmod, _name)
        if _inspect.isclass(_obj) and hasattr(_obj, "async_get_max_cop_sample_ts"):
            return _obj.__new__(_obj)
    raise RuntimeError("db class not found")


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_get_max_ts_conn_none_returns_none():
    db = _real_db()
    db._conn = None
    assert await db.async_get_max_cop_sample_ts() is None


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_get_max_ts_row_none_returns_none():
    db = _real_db()
    cursor = MagicMock()
    cursor.fetchone = AsyncMock(return_value=None)
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cursor)
    db._conn = conn
    assert await db.async_get_max_cop_sample_ts() is None


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_get_max_ts_row_first_none_returns_none():
    db = _real_db()
    cursor = MagicMock()
    cursor.fetchone = AsyncMock(return_value=(None,))
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cursor)
    db._conn = conn
    assert await db.async_get_max_cop_sample_ts() is None


@pytest.mark.asyncio  # type: ignore[untyped-decorator]
async def test_get_max_ts_happy_path_returns_float():
    db = _real_db()
    cursor = MagicMock()
    cursor.fetchone = AsyncMock(return_value=(1792897000.5,))
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cursor)
    db._conn = conn
    result = await db.async_get_max_cop_sample_ts()
    assert result == 1792897000.5
    assert isinstance(result, float)
