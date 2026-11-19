"""Frontend registration for Daikin Cycle ML."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig  # type: ignore[attr-defined]
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

async def async_register_frontend(hass: HomeAssistant) -> None:
    """Register static path and add the JS module to the frontend."""
    local_path = Path(__file__).parent
    try:
        await hass.http.async_register_static_paths([
            StaticPathConfig("/daikin_cycle_ml", str(local_path), False)
        ])
        add_extra_js_url(hass, "/daikin_cycle_ml/daikin-daily-summary-card.js")
        _LOGGER.info("Daikin frontend card registered")
    except Exception:
        _LOGGER.exception("Failed to register Daikin frontend card")
