"""Frontend: serve and load the native Lovelace card(s) of Daikin Cycle ML.

The card is served from the integration folder and added to every
dashboard with ``add_extra_js_url``: users add
``type: custom:daikin-daily-summary-card`` without installing anything
or adding a Lovelace resource. The URL carries the integration version,
so browsers fetch the new card after every update instead of a cached one.
"""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig  # type: ignore[attr-defined]
from homeassistant.core import HomeAssistant

from ..const import DOMAIN, VERSION

_LOGGER = logging.getLogger(__name__)

URL_BASE = f"/{DOMAIN}_frontend"
CARD_FILES = ("daikin-daily-summary-card.js",)
_REGISTERED = f"{DOMAIN}_frontend_registered"


def card_urls() -> list[str]:
    """Versioned module URLs of the cards (cache-busting on update)."""
    return [f"{URL_BASE}/{name}?v={VERSION}" for name in CARD_FILES]


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Serve the card folder and load the cards on every dashboard (once)."""
    if hass.data.get(_REGISTERED):
        return
    if getattr(hass, "http", None) is None:  # no HTTP server (tests, safe mode)
        _LOGGER.debug("HTTP not available: Daikin Cycle ML card not served")
        return
    local_path = Path(__file__).parent
    try:
        await hass.http.async_register_static_paths([
            StaticPathConfig(URL_BASE, str(local_path), True)
        ])
        for url in card_urls():
            add_extra_js_url(hass, url)
    except Exception:  # a card must never break the integration
        _LOGGER.exception("Failed to register the Daikin Cycle ML card")
        return
    hass.data[_REGISTERED] = True
    _LOGGER.debug("Daikin Cycle ML card registered: %s", card_urls())
