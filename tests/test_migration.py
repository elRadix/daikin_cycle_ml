"""v1.3.1 entity_id migration tests."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant

from custom_components.daikin_cycle_ml.sensor import _migrate_entity_ids


def _mock_registry(existing_ids=None):
    reg = MagicMock()
    existing = set(existing_ids or [])
    reg.async_get.side_effect = lambda eid: MagicMock() if eid in existing else None
    return reg


def test_migration_renames_wrong_entity_ids(hass: HomeAssistant) -> None:
    reg = _mock_registry(existing_ids=["sensor.daikin_cycle_ml"])
    entry = MagicMock(entry_id="abc")
    with patch("custom_components.daikin_cycle_ml.sensor.er.async_get", return_value=reg):
        _migrate_entity_ids(hass, entry)
    reg.async_update_entity.assert_called_once_with(
        "sensor.daikin_cycle_ml",
        new_entity_id="sensor.daikin_cycle_ml_cop_mean_day",
    )


def test_migration_skips_absent(hass: HomeAssistant) -> None:
    reg = _mock_registry(existing_ids=[])
    entry = MagicMock(entry_id="abc")
    with patch("custom_components.daikin_cycle_ml.sensor.er.async_get", return_value=reg):
        _migrate_entity_ids(hass, entry)
    reg.async_update_entity.assert_not_called()


def test_migration_idempotent_already_correct(hass: HomeAssistant) -> None:
    reg = _mock_registry(existing_ids=["sensor.daikin_cycle_ml", "sensor.daikin_cycle_ml_cop_mean_day"])
    entry = MagicMock(entry_id="abc")
    with patch("custom_components.daikin_cycle_ml.sensor.er.async_get", return_value=reg):
        _migrate_entity_ids(hass, entry)
    reg.async_update_entity.assert_not_called()
