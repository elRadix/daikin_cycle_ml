"""v1.12.9 - _migrate_entity_ids idempotency (issue #141).

Bug: partial migration could leave an entity with the NEW unique_id but
the OLD entity_id (or vice versa). On next setup, _migrate_entity_ids
called async_update_entity with new_unique_id that was already owned by
the same entity, raising:

    ValueError: Unique id '..._cop_today' is already in use by
    'sensor.daikin_cycle_ml_cop_vandaag'

Sensor platform setup failed for the whole entry.

New guard: if old_entry.unique_id == new_uid, update only entity_id +
translation_key (the unique_id is already correct).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml.sensor import _migrate_entity_ids


ENTRY_ID = "01M5PE5F4PKTN6001N91MMQGY8"
DOMAIN = "daikin_cycle_ml"
OLD_EID = "sensor.daikin_cycle_ml_cop_vandaag"
NEW_EID = "sensor.daikin_cycle_ml_cop_today"
NEW_UID = f"{DOMAIN}_{ENTRY_ID}_cop_today"
OLD_UID = f"{DOMAIN}_{ENTRY_ID}_cop_vandaag"


def _make_entry():
    entry = MagicMock()
    entry.entry_id = ENTRY_ID
    entry.domain = DOMAIN
    return entry


def _make_registry(entities: dict[str, MagicMock]):
    registry = MagicMock()

    def _async_get(eid):
        return entities.get(eid)

    def _async_entries_for(reg, eid):
        return [e for e in entities.values() if e.config_entry_id == eid]

    registry.async_get = MagicMock(side_effect=_async_get)
    registry.async_update_entity = MagicMock()
    return registry, _async_entries_for


def _make_entity(eid, uid, config_entry_id=ENTRY_ID):
    e = MagicMock()
    e.entity_id = eid
    e.unique_id = uid
    e.platform = DOMAIN
    e.config_entry_id = config_entry_id
    return e


def _run_migrate(monkeypatch, entities):
    import custom_components.daikin_cycle_ml.sensor as sensor_mod
    registry, _ = _make_registry(entities)

    def _fake_entries(reg, eid):
        return [e for e in entities.values() if e.config_entry_id == eid]

    # Patch BOTH functions used by _migrate_entity_ids: async_get (lookups)
    # and async_entries_for_config_entry (owns set). Patching only async_get
    # leaves the real HA function iterating over our MagicMock registry,
    # producing an empty `owned` set and silently skipping all updates.
    monkeypatch.setattr(sensor_mod.er, "async_get", lambda hass: registry)
    monkeypatch.setattr(
        sensor_mod.er, "async_entries_for_config_entry", _fake_entries,
    )
    _migrate_entity_ids(MagicMock(), _make_entry())
    return registry


def test_partial_migration_unique_id_already_updated(monkeypatch):
    """#141: unique_id == new_uid, entity_id still OLD. Must NOT raise."""
    entities = {
        OLD_EID: _make_entity(OLD_EID, NEW_UID),  # partial: uid migrated, eid not
    }
    registry = _run_migrate(monkeypatch, entities)

    registry.async_update_entity.assert_called_once()
    call = registry.async_update_entity.call_args
    assert call.args[0] == OLD_EID
    kw = call.kwargs
    assert kw["new_entity_id"] == NEW_EID
    assert kw["translation_key"] == "cop_today"
    assert "new_unique_id" not in kw  # <- critical: uid unchanged (would raise)


def test_fresh_migration_updates_all_three(monkeypatch):
    """Happy path: old eid + old uid. Update entity_id, unique_id, translation_key."""
    entities = {
        OLD_EID: _make_entity(OLD_EID, OLD_UID),
    }
    registry = _run_migrate(monkeypatch, entities)

    registry.async_update_entity.assert_called_once()
    kw = registry.async_update_entity.call_args.kwargs
    assert kw["new_entity_id"] == NEW_EID
    assert kw["new_unique_id"] == NEW_UID
    assert kw["translation_key"] == "cop_today"


def test_already_fully_migrated_is_skipped(monkeypatch):
    """entity_id target already exists → skip, do not touch registry."""
    entities = {
        OLD_EID: _make_entity(OLD_EID, OLD_UID),
        NEW_EID: _make_entity(NEW_EID, NEW_UID),
    }
    registry = _run_migrate(monkeypatch, entities)

    # No update should fire (both _cop_vandaag and _cop_today exist;
    # the async_get(new_eid) is not None guard skips the loop iteration)
    registry.async_update_entity.assert_not_called()
