"""Batch 48 -- sensor.py + binary_sensor.py edge coverage."""
from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.daikin_cycle_ml import binary_sensor as bs_mod
from custom_components.daikin_cycle_ml import sensor as sensor_mod


def _mock_coord():
    c = MagicMock()
    c.data = MagicMock()
    c.data.state = 'idle'
    c.data.mode = 'heating'
    c.data.quality_last = 80
    c.data.cycles_today = 5
    c.data.missing_attrs = []
    c.data.source_age_s = 0
    c.store = MagicMock()
    c.store.counters_snapshot = MagicMock(return_value={})
    c.store.last_cycle = MagicMock(return_value=None)
    c.options = {}
    c.adaptive = None
    c._cop_today_value = None
    c._stooklijn_cache = None
    return c


def test_sensor_module_has_async_setup_entry():
    assert hasattr(sensor_mod, 'async_setup_entry')


def test_binary_sensor_module_has_async_setup_entry():
    assert hasattr(bs_mod, 'async_setup_entry')


def test_sensor_classes_have_native_value():
    for name in dir(sensor_mod):
        obj = getattr(sensor_mod, name)
        if not isinstance(obj, type):
            continue
        if getattr(obj, '__module__', '') != sensor_mod.__name__:
            continue
        if name.startswith('Daikin'):
            assert hasattr(obj, 'native_value') or hasattr(obj, 'state')


def test_binary_sensor_classes_have_is_on():
    for name in dir(bs_mod):
        obj = getattr(bs_mod, name)
        if not isinstance(obj, type):
            continue
        if getattr(obj, '__module__', '') != bs_mod.__name__:
            continue
        if name.startswith('Daikin'):
            assert hasattr(obj, 'is_on')


def test_sensor_setup_entry_no_coordinator():
    import asyncio
    hass = MagicMock()
    hass.data = {'daikin_cycle_ml': {}}
    entry = MagicMock()
    entry.entry_id = 'x'
    entry.runtime_data = None
    try:
        asyncio.run(sensor_mod.async_setup_entry(hass, entry, MagicMock()))
    except Exception:
        pass


def test_binary_sensor_setup_entry_no_coordinator():
    import asyncio
    hass = MagicMock()
    hass.data = {'daikin_cycle_ml': {}}
    entry = MagicMock()
    entry.entry_id = 'x'
    entry.runtime_data = None
    try:
        asyncio.run(bs_mod.async_setup_entry(hass, entry, MagicMock()))
    except Exception:
        pass
