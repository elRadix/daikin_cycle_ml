"""Tests for cop_samples (batch 14b-1)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)
from custom_components.daikin_cycle_ml.storage.db import CycleDB


async def test_db_ensure_idempotent(tmp_path):
    db = CycleDB(tmp_path / 'c.db')
    await db.async_initialize()
    try:
        await db.async_ensure_cop_samples_table()
        await db.async_ensure_cop_samples_table()
        assert await db.async_count_cop_samples() == 0
    finally:
        await db.async_close()


async def test_db_insert_and_count(tmp_path):
    db = CycleDB(tmp_path / 'c.db')
    await db.async_initialize()
    try:
        ok = await db.async_insert_cop_sample({
            'ts': 1000.0, 'cop': 3.5, 'lwt': 32.0,
            'outdoor': 7.0, 'flow_lmin': 12.5,
            'power_stable': True,
        })
        assert ok is True
        assert await db.async_count_cop_samples() == 1
    finally:
        await db.async_close()


async def test_db_insert_optional_none(tmp_path):
    db = CycleDB(tmp_path / 'c.db')
    await db.async_initialize()
    try:
        ok = await db.async_insert_cop_sample({
            'ts': 2000.0, 'cop': 3.0, 'power_stable': False,
        })
        assert ok is True
    finally:
        await db.async_close()


async def test_db_insert_bad_ts_returns_false(tmp_path):
    db = CycleDB(tmp_path / 'c.db')
    await db.async_initialize()
    try:
        ok = await db.async_insert_cop_sample({
            'ts': 'not-a-number', 'cop': 3.0,
        })
        assert ok is False
    finally:
        await db.async_close()


async def test_db_fetch_by_days(tmp_path):
    import time
    db = CycleDB(tmp_path / 'c.db')
    await db.async_initialize()
    try:
        now = time.time()
        await db.async_insert_cop_sample({
            'ts': now - 10 * 86400, 'cop': 2.5, 'outdoor': 3.0,
            'power_stable': True,
        })
        await db.async_insert_cop_sample({
            'ts': now - 3600, 'cop': 3.5, 'outdoor': 7.0,
            'power_stable': True,
        })
        recent = await db.async_fetch_cop_samples(days=7)
        assert len(recent) == 1
        assert recent[0]['cop'] == 3.5
        all_rows = await db.async_fetch_cop_samples(days=30)
        assert len(all_rows) == 2
    finally:
        await db.async_close()


async def test_maintenance_prunes_cop_samples(tmp_path):
    import time
    db = CycleDB(tmp_path / 'c.db')
    await db.async_initialize()
    try:
        old = time.time() - 500 * 86400
        await db.async_insert_cop_sample({
            'ts': old, 'cop': 2.0, 'power_stable': True,
        })
        await db.async_insert_cop_sample({
            'ts': time.time() - 3600, 'cop': 3.5,
            'power_stable': True,
        })
        out = await db.async_run_maintenance(
            cycle_retention_days=90,
            alert_retention_days=30,
            cop_retention_days=365,
            vacuum=False,
        )
        assert out['cop_deleted'] == 1
        assert await db.async_count_cop_samples() == 1
    finally:
        await db.async_close()


async def test_async_count_allows_cop_samples(tmp_path):
    db = CycleDB(tmp_path / 'c.db')
    await db.async_initialize()
    try:
        n = await db.async_count('cop_samples')
        assert n == 0
    finally:
        await db.async_close()


def _bare():
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.db = MagicMock()
    c.db.async_insert_cop_sample = AsyncMock(return_value=True)
    c.hass = MagicMock()
    c.cop_sensor_entity = 'sensor.altherma_global_cop'
    c._last_cop_sample_ts = 0.0
    return c


def _state(state='3.5', **over):
    st = MagicMock()
    st.state = state
    base = {
        'leaving_temp': '32.5 C (After BUH)',
        'inlet_temp': '28.0 C',
        'delta_t': '4.5 C',
        'thermal_power': '5.2 kW',
        'electrical_input': '1.5 kW',
        'outdoor_temperature': '7.0 C',
        'flow_rate': '12.5 L/min',
        'backup_heater_active': False,
        'defrost_operation': 'OFF',
        'power_stable': True,
        'data_quality': 'Good',
    }
    base.update(over)
    st.attributes = base
    return st


async def test_collect_skips_interval_not_elapsed():
    c = _bare()
    c._last_cop_sample_ts = 1000.0
    await c._maybe_collect_cop_sample(1100.0)
    c.db.async_insert_cop_sample.assert_not_awaited()


async def test_collect_skips_no_state():
    c = _bare()
    c.hass.states.get = MagicMock(return_value=None)
    await c._maybe_collect_cop_sample(99999.0)
    c.db.async_insert_cop_sample.assert_not_awaited()


async def test_collect_skips_zero_cop():
    c = _bare()
    c.hass.states.get = MagicMock(return_value=_state('0.0'))
    await c._maybe_collect_cop_sample(99999.0)
    c.db.async_insert_cop_sample.assert_not_awaited()


async def test_collect_skips_poor_quality():
    c = _bare()
    c.hass.states.get = MagicMock(
        return_value=_state('3.5', data_quality='Poor/Idle'))
    await c._maybe_collect_cop_sample(99999.0)
    c.db.async_insert_cop_sample.assert_not_awaited()


async def test_collect_skips_power_unstable():
    c = _bare()
    c.hass.states.get = MagicMock(
        return_value=_state('3.5', power_stable=False))
    await c._maybe_collect_cop_sample(99999.0)
    c.db.async_insert_cop_sample.assert_not_awaited()


async def test_collect_skips_defrost():
    c = _bare()
    c.hass.states.get = MagicMock(
        return_value=_state('3.5', defrost_operation='ON'))
    await c._maybe_collect_cop_sample(99999.0)
    c.db.async_insert_cop_sample.assert_not_awaited()


async def test_collect_inserts_valid():
    c = _bare()
    c.hass.states.get = MagicMock(return_value=_state('3.5'))
    await c._maybe_collect_cop_sample(99999.0)
    c.db.async_insert_cop_sample.assert_awaited_once()
    assert c._last_cop_sample_ts == 99999.0

