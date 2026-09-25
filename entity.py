"""Base entity for Daikin Cycle ML."""
from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME, VERSION
from .coordinator import DaikinCycleMLCoordinator


class DaikinCycleMLEntity(CoordinatorEntity[DaikinCycleMLCoordinator]):
    """Common base: device info + unique_id + has_entity_name."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DaikinCycleMLCoordinator,
        key: str,
        name: str | None = None,  # deprecated, kept for backward compat
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{DOMAIN}_{coordinator.entry.entry_id}_{key}"
        # HA resolves name via translations/<lang>.json entity.<platform>.<key>.name
        # Keeping _attr_name unset lets the translation_key take precedence.
        self._attr_translation_key = key
        model = coordinator.entry.data.get("model", "unknown")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=NAME,
            manufacturer="Daikin",
            model=str(model),
            sw_version=VERSION,
        )

    @property
    def available(self) -> bool:
        if self.coordinator.data is None:
            return False
        return True

    def snapshot(self) -> Any:
        return self.coordinator.data
