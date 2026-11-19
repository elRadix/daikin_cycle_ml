"""The integration serves and loads its native card (no Lovelace resource)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.daikin_cycle_ml.const import VERSION
from custom_components.daikin_cycle_ml.frontend import (
    URL_BASE,
    async_register_frontend,
    card_urls,
)

_MOD = "custom_components.daikin_cycle_ml.frontend"


def test_card_url_is_versioned():
    assert card_urls() == [f"{URL_BASE}/daikin-daily-summary-card.js?v={VERSION}"]


@pytest.mark.asyncio
async def test_register_serves_folder_and_loads_card_once(hass):
    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()
    with patch(f"{_MOD}.add_extra_js_url") as add_js:
        await async_register_frontend(hass)
        await async_register_frontend(hass)  # second entry / reload: no-op
    hass.http.async_register_static_paths.assert_awaited_once()
    cfg = hass.http.async_register_static_paths.call_args.args[0][0]
    assert cfg.url_path == URL_BASE and cfg.path.endswith("frontend")
    assert cfg.cache_headers is True  # safe: the URL changes with the version
    add_js.assert_called_once_with(hass, card_urls()[0])


@pytest.mark.asyncio
async def test_register_without_http_is_skipped(hass):
    hass.http = None
    with patch(f"{_MOD}.add_extra_js_url") as add_js:
        await async_register_frontend(hass)
    add_js.assert_not_called()


@pytest.mark.asyncio
async def test_register_failure_is_logged_not_raised(hass):
    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock(side_effect=RuntimeError("boom"))
    with patch(f"{_MOD}._LOGGER.exception") as log:
        await async_register_frontend(hass)
    log.assert_called_once()
    # a later attempt may still succeed
    hass.http.async_register_static_paths = AsyncMock()
    with patch(f"{_MOD}.add_extra_js_url") as add_js:
        await async_register_frontend(hass)
    add_js.assert_called_once()
