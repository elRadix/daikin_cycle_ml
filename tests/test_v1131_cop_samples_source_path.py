"""v1.13.2 #196 hotfix — cop_samples source-driven sampling path."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
    DataSnapshot,
)


def _make_coord(cop_sensor_entity="sensor.cop", data=None):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.db = MagicMock()
    c.db.async_get_max_cop_sample_ts = AsyncMock(return_value=None)
    c.db.async_insert_cop_sample = AsyncMock(return_value=True)
    c._last_cop_sample_ts = 0.0
    c._cop_sample_seed_done = True
    c.cop_sensor_entity = cop_sensor_entity
    c.hass = MagicMock()
    if data is not None:
        c.data = data
    return c


def _state(val, attrs=None):
    s = MagicMock()
    s.state = val
    s.attributes = attrs or {}
    return s


def _full_attrs():
    return {
        "Outdoor air temp.(R1T)": 7.5,
        "Leaving water temp. after BUH (R2T)": 32.0,
        "Inlet water temp.(R4T)": 28.0,
        "Flow sensor (l/min)": 15.5,
    }


async def test_collect_no_cop_sensor_uses_data_cop():
    """cop_sensor_entity empty → fall back to self.data.cop with source attrs."""
    snap = DataSnapshot(attrs=_full_attrs())
    snap.cop = 3.2
    c = _make_coord(cop_sensor_entity="", data=snap)
    await c._maybe_collect_cop_sample(99999.0)
    c.db.async_insert_cop_sample.assert_awaited_once()
    row = c.db.async_insert_cop_sample.await_args[0][0]
    assert row['cop'] == 3.2


async def test_collect_data_cop_invalid_float_skips():
    """data.cop='garbage' → float raises → exception branch → skip."""
    snap = DataSnapshot(attrs=_full_attrs())
    snap.cop = "garbage"  # type: ignore[assignment]
    c = _make_coord(cop_sensor_entity="", data=snap)
    await c._maybe_collect_cop_sample(99999.0)
    c.db.async_insert_cop_sample.assert_not_awaited()


async def test_collect_data_cop_zero_skips():
    """data.cop=0 → not > 0 → skip."""
    snap = DataSnapshot(attrs=_full_attrs())
    snap.cop = 0.0
    c = _make_coord(cop_sensor_entity="", data=snap)
    await c._maybe_collect_cop_sample(99999.0)
    c.db.async_insert_cop_sample.assert_not_awaited()


async def test_collect_data_cop_none_skips():
    """No cop_sensor + no data.cop → skip."""
    snap = DataSnapshot(attrs=_full_attrs())
    snap.cop = None
    c = _make_coord(cop_sensor_entity="", data=snap)
    await c._maybe_collect_cop_sample(99999.0)
    c.db.async_insert_cop_sample.assert_not_awaited()


async def test_collect_source_attrs_good_quality():
    """Full source attrs + valid cop_sensor → data_quality='Good' → insert."""
    snap = DataSnapshot(attrs=_full_attrs())
    c = _make_coord(data=snap)
    c.hass.states.get = MagicMock(return_value=_state('4.2'))
    await c._maybe_collect_cop_sample(99999.0)
    c.db.async_insert_cop_sample.assert_awaited_once()
    row = c.db.async_insert_cop_sample.await_args[0][0]
    assert row['cop'] == 4.2
    assert row['lwt'] == 32.0
    assert row['outdoor'] == 7.5
    assert row['flow_lmin'] == 15.5
    assert row['power_stable'] is True
    assert row['source'] == 'interval'


async def test_collect_source_attrs_partial_quality_skips():
    """Source without lwt → data_quality='Partial' → existing gate skips."""
    attrs = {
        "Outdoor air temp.(R1T)": 7.5,
        "Flow sensor (l/min)": 15.5,
    }
    snap = DataSnapshot(attrs=attrs)
    c = _make_coord(data=snap)
    c.hass.states.get = MagicMock(return_value=_state('4.2'))
    await c._maybe_collect_cop_sample(99999.0)
    c.db.async_insert_cop_sample.assert_not_awaited()


async def test_collect_source_attrs_defrost_on_skips():
    """Source Defrost Operation=ON → sample.defrost=True → gate skips."""
    attrs = dict(_full_attrs())
    attrs["Defrost Operation"] = "ON"
    snap = DataSnapshot(attrs=attrs)
    c = _make_coord(data=snap)
    c.hass.states.get = MagicMock(return_value=_state('4.2'))
    await c._maybe_collect_cop_sample(99999.0)
    c.db.async_insert_cop_sample.assert_not_awaited()


async def test_collect_source_attrs_lwt_fallback_to_r1t():
    """Missing R2T but present R1T → R1T used as lwt fallback."""
    attrs = {
        "Outdoor air temp.(R1T)": 7.5,
        "Leaving water temp. before BUH (R1T)": 30.5,
        "Flow sensor (l/min)": 15.5,
    }
    snap = DataSnapshot(attrs=attrs)
    c = _make_coord(data=snap)
    c.hass.states.get = MagicMock(return_value=_state('4.2'))
    await c._maybe_collect_cop_sample(99999.0)
    c.db.async_insert_cop_sample.assert_awaited_once()
    row = c.db.async_insert_cop_sample.await_args[0][0]
    assert row['lwt'] == 30.5


async def test_collect_source_attrs_missing_outdoor_partial_skip():
    """Source has lwt but no outdoor → data_quality='Partial' → skip."""
    attrs = {
        "Leaving water temp. after BUH (R2T)": 32.0,
        "Inlet water temp.(R4T)": 28.0,
        "Flow sensor (l/min)": 15.5,
    }
    snap = DataSnapshot(attrs=attrs)
    c = _make_coord(data=snap)
    c.hass.states.get = MagicMock(return_value=_state('4.2'))
    await c._maybe_collect_cop_sample(99999.0)
    c.db.async_insert_cop_sample.assert_not_awaited()


async def test_collect_source_attrs_missing_flow_inserts():
    """Source has lwt+outdoor but no flow → data_quality='Good' → insert, flow None."""
    attrs = {
        "Leaving water temp. after BUH (R2T)": 32.0,
        "Outdoor air temp.(R1T)": 7.5,
    }
    snap = DataSnapshot(attrs=attrs)
    c = _make_coord(data=snap)
    c.hass.states.get = MagicMock(return_value=_state('4.2'))
    await c._maybe_collect_cop_sample(99999.0)
    c.db.async_insert_cop_sample.assert_awaited_once()
    row = c.db.async_insert_cop_sample.await_args[0][0]
    assert row['flow_lmin'] is None
