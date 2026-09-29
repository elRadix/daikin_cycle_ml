"""R194/R195: integration-setup test using the real HA EntityRegistry.

R195: never entry.mock_state(LOADED) + async_forward_entry_setups.
Use hass.config_entries.async_setup(entry.entry_id) with a monkeypatched
DaikinCycleMLCoordinator + _async_setup_database no-op.
"""
from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daikin_cycle_ml import sensor as sensor_mod
from custom_components.daikin_cycle_ml.const import DOMAIN

_SLUG_RE = re.compile(r"^sensor\.daikin_cycle_ml_[a-z0-9_]+$")


def _mock_coordinator(entry_id):
    c = MagicMock()
    c.entry = MagicMock()
    c.entry.entry_id = entry_id
    c.entry.options = {}
    c.entry.data = {}
    c.entry.title = "Daikin Cycle ML"
    c.data = {}
    c.last_update_success = True
    c.async_add_listener = MagicMock(return_value=lambda: None)
    c.async_config_entry_first_refresh = AsyncMock()
    c.async_shutdown = AsyncMock()
    c.async_refresh = AsyncMock()
    c.async_request_refresh = AsyncMock()
    c.last_success_ts = 0.0
    c.state = "idle"
    c.mode = "idle"
    c.store = MagicMock()
    c.store.cycles_today = MagicMock(return_value=[])
    c.store.get = MagicMock(return_value=0)
    c.store.cycles_in_window = MagicMock(return_value=0)
    c.store.cycles_in_window_mode = MagicMock(return_value=0)
    c.cop_hourly_day = None
    c.cop_hourly_week = None
    c.cop_hourly_month = None
    c.cop_curve_recent = []
    c.stooklijn_advies = {}
    c.cop_today = {}
    c.db = AsyncMock()
    c.db.async_close = AsyncMock()
    return c


async def _setup_integration(hass, monkeypatch, entry_id="r194_int_test"):
    coord = _mock_coordinator(entry_id)

    def _factory(h, e):
        return coord

    monkeypatch.setattr(
        "custom_components.daikin_cycle_ml.DaikinCycleMLCoordinator",
        _factory,
    )
    monkeypatch.setattr(
        "custom_components.daikin_cycle_ml._async_setup_database",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "custom_components.daikin_cycle_ml.PLATFORMS",
        (Platform.SENSOR,),
    )
    monkeypatch.setattr(
        sensor_mod.DaikinCycleMLSensor,
        "native_value",
        property(lambda self: None),
    )
    monkeypatch.setattr(
        sensor_mod.DaikinCycleMLSensor,
        "extra_state_attributes",
        property(lambda self: None),
    )

    entry = MockConfigEntry(
        domain=DOMAIN, entry_id=entry_id, data={}, options={},
        title="Daikin Cycle ML",
    )
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[entry_id] = {"db": coord.db}
    ok = await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert ok, "async_setup returned False"
    return entry, coord


@pytest.mark.asyncio
@pytest.mark.expected_lingering_timers(True)
@pytest.mark.expected_lingering_tasks(True)
async def test_all_sensor_defs_registered_with_correct_slug(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every SENSOR_DEFS key must yield sensor.daikin_cycle_ml_<key>."""
    await _setup_integration(hass, monkeypatch)

    registry = er.async_get(hass)
    entries = [e for e in registry.entities.values() if e.platform == DOMAIN]
    eids = {e.entity_id for e in entries}

    expected = {
        "sensor.daikin_cycle_ml_" + spec["key"]
        for spec in sensor_mod.SENSOR_DEFS
    }
    missing = expected - eids
    assert not missing, (
        "missing expected slugs: %s; got: %s" % (sorted(missing), sorted(eids))
    )

    bad_shape = [eid for eid in eids if not _SLUG_RE.match(eid)]
    assert not bad_shape, "non-conforming slugs: %s" % sorted(bad_shape)

    collision = [
        eid for eid in eids
        if eid == "sensor.daikin_cycle_ml"
        or eid.endswith("_2")
        or eid.endswith("_3")
        or eid.endswith("_cop_curve_48h")
    ]
    assert not collision, "found collision slugs: %s" % sorted(collision)

    # R194 language leak: SENSOR_DEFS keys must be English slugs.
    _NL_LEAKS = ("vandaag", "stooklijn", "advies")
    leaked = [
        spec["key"] for spec in sensor_mod.SENSOR_DEFS
        if any(w in spec["key"] for w in _NL_LEAKS)
    ]
    assert not leaked, "NL-word in SENSOR_DEFS key: %s" % sorted(leaked)


@pytest.mark.asyncio
@pytest.mark.expected_lingering_timers(True)
@pytest.mark.expected_lingering_tasks(True)
async def test_migration_runs_through_real_registry(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_migrate_entity_ids must rename legacy slugs in the real registry."""
    registry = er.async_get(hass)

    legacy = registry.async_get_or_create(
        domain="sensor",
        platform=DOMAIN,
        unique_id="daikin_cycle_ml_r194_mig_test_cop_mean_day",
        suggested_object_id="daikin_cycle_ml",
    )
    if legacy.entity_id != "sensor.daikin_cycle_ml":
        registry.async_update_entity(
            legacy.entity_id, new_entity_id="sensor.daikin_cycle_ml",
        )
    assert registry.async_get("sensor.daikin_cycle_ml") is not None

    await _setup_integration(hass, monkeypatch, entry_id="r194_mig_test")

    renamed = registry.async_get("sensor.daikin_cycle_ml_cop_mean_day")
    assert renamed is not None, "migration did not rename bare slug"
    assert registry.async_get("sensor.daikin_cycle_ml") is None

@pytest.mark.asyncio
@pytest.mark.expected_lingering_timers(True)
@pytest.mark.expected_lingering_tasks(True)
async def test_v140_key_rename_migrates_through_real_registry(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v1.4.0: _migrate_entity_ids renames legacy keys via real registry."""
    registry = er.async_get(hass)
    entry_id = "r140_key_mig"
    pairs = (
        ("today", "cycles_today"),
        ("cop_vandaag", "cop_today"),
        ("stooklijn_advies", "heating_curve_advice"),
    )

    for old_key, _new_key in pairs:
        legacy = registry.async_get_or_create(
            domain="sensor",
            platform=DOMAIN,
            unique_id="daikin_cycle_ml_%s_%s" % (entry_id, old_key),
            suggested_object_id="daikin_cycle_ml_%s" % old_key,
        )
        assert legacy.entity_id == "sensor.daikin_cycle_ml_%s" % old_key

    await _setup_integration(hass, monkeypatch, entry_id=entry_id)

    for old_key, new_key in pairs:
        old_eid = "sensor.daikin_cycle_ml_%s" % old_key
        new_eid = "sensor.daikin_cycle_ml_%s" % new_key
        assert registry.async_get(old_eid) is None, old_eid
        renamed = registry.async_get(new_eid)
        assert renamed is not None, new_eid
        assert renamed.unique_id == (
            "daikin_cycle_ml_%s_%s" % (entry_id, new_key)
        )
        assert renamed.translation_key == new_key
