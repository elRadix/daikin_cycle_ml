"""v1.15.1 — hybrid entities must not exist on non-hybrid installs."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from custom_components.daikin_cycle_ml import binary_sensor as binary_mod
from custom_components.daikin_cycle_ml import sensor as sensor_mod

_HYBRID_SENSOR_KEYS = frozenset(
    {"hybrid_mode", "boiler_efficiency_cop", "boiler_contribution_today_pct"}
)
_HYBRID_BINARY_KEYS = frozenset({"boiler_operation_demand", "boiler_dhw_demand"})


def _entry(entry_id: str = "ENTRY01") -> MagicMock:
    e = MagicMock()
    e.entry_id = entry_id
    return e


def _coord(entry: MagicMock, *, is_hybrid: bool) -> MagicMock:
    c = MagicMock()
    c.entry = entry
    c.data = MagicMock(is_hybrid=is_hybrid)
    return c


def _fake_sensor_factory(instances: list) -> object:
    def _mk(*args, **kwargs):
        m = MagicMock()
        m._key = kwargs["key"]
        instances.append(m)
        return m
    return _mk


def _fake_binary_factory(instances: list) -> object:
    def _mk(*args, **kwargs):
        m = MagicMock()
        m._key = kwargs["key"]
        instances.append(m)
        return m
    return _mk


@pytest.mark.asyncio
async def test_sensor_non_hybrid_skips_hybrid_entities():
    entry = _entry()
    entry.runtime_data = _coord(entry, is_hybrid=False)
    created: list = []
    with patch.object(sensor_mod, "_migrate_entity_ids"), \
         patch.object(sensor_mod, "async_remove_stale_entities") as purge, \
         patch.object(sensor_mod, "DaikinCycleMLSensor",
                      side_effect=_fake_sensor_factory(created)):
        await sensor_mod.async_setup_entry(MagicMock(), entry, lambda ents: None)
    keys = {e._key for e in created}
    assert keys.isdisjoint(_HYBRID_SENSOR_KEYS)
    purge.assert_called_once()
    assert purge.call_args.args[2] == _HYBRID_SENSOR_KEYS


@pytest.mark.asyncio
async def test_sensor_hybrid_creates_hybrid_entities():
    entry = _entry()
    entry.runtime_data = _coord(entry, is_hybrid=True)
    created: list = []
    with patch.object(sensor_mod, "_migrate_entity_ids"), \
         patch.object(sensor_mod, "async_remove_stale_entities") as purge, \
         patch.object(sensor_mod, "DaikinCycleMLSensor",
                      side_effect=_fake_sensor_factory(created)):
        await sensor_mod.async_setup_entry(MagicMock(), entry, lambda ents: None)
    keys = {e._key for e in created}
    assert _HYBRID_SENSOR_KEYS <= keys
    purge.assert_not_called()


@pytest.mark.asyncio
async def test_binary_sensor_non_hybrid_skips_hybrid_entities():
    entry = _entry()
    entry.runtime_data = _coord(entry, is_hybrid=False)
    created: list = []
    with patch.object(binary_mod, "async_remove_stale_entities") as purge, \
         patch.object(binary_mod, "DaikinCycleMLBinarySensor",
                      side_effect=_fake_binary_factory(created)):
        await binary_mod.async_setup_entry(MagicMock(), entry, lambda ents: None)
    keys = {e._key for e in created}
    assert keys.isdisjoint(_HYBRID_BINARY_KEYS)
    purge.assert_called_once()
    assert purge.call_args.args[2] == _HYBRID_BINARY_KEYS


@pytest.mark.asyncio
async def test_binary_sensor_hybrid_creates_hybrid_entities():
    entry = _entry()
    entry.runtime_data = _coord(entry, is_hybrid=True)
    created: list = []
    with patch.object(binary_mod, "async_remove_stale_entities") as purge, \
         patch.object(binary_mod, "DaikinCycleMLBinarySensor",
                      side_effect=_fake_binary_factory(created)):
        await binary_mod.async_setup_entry(MagicMock(), entry, lambda ents: None)
    keys = {e._key for e in created}
    assert _HYBRID_BINARY_KEYS <= keys
    purge.assert_not_called()


@pytest.mark.asyncio
async def test_cleanup_purges_only_hybrid_entries():
    from custom_components.daikin_cycle_ml.const import DOMAIN
    from custom_components.daikin_cycle_ml.entity import async_remove_stale_entities

    entry_id = "ENTRY01"
    keys = frozenset({"hybrid_mode", "boiler_efficiency_cop"})

    keep = MagicMock(unique_id=f"{DOMAIN}_{entry_id}_cycles_today",
                     entity_id="sensor.cycles_today")
    kill = MagicMock(unique_id=f"{DOMAIN}_{entry_id}_hybrid_mode",
                     entity_id="sensor.hybrid_mode")
    fake_reg = MagicMock()

    with patch("homeassistant.helpers.entity_registry.async_get",
               return_value=fake_reg), \
         patch("homeassistant.helpers.entity_registry.async_entries_for_config_entry",
               return_value=[keep, kill]):
        async_remove_stale_entities(MagicMock(), entry_id, keys)

    fake_reg.async_remove.assert_called_once_with("sensor.hybrid_mode")
