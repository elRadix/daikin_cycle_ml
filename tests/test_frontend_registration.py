"""Tests for frontend registration."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.daikin_cycle_ml.frontend import async_register_frontend


@pytest.mark.asyncio
async def test_async_register_frontend_success(hass):
    """Test that static paths and JS module are registered correctly."""
    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()

    with patch(
        "custom_components.daikin_cycle_ml.frontend.add_extra_js_url"
    ) as mock_add_js:
        await async_register_frontend(hass)

        hass.http.async_register_static_paths.assert_called_once()
        mock_add_js.assert_called_once_with(
            hass, "/daikin_cycle_ml/daikin-daily-summary-card.js"
        )

@pytest.mark.asyncio
async def test_async_register_frontend_failure(hass):
    """Test that exceptions are logged and swallowed."""
    hass.http = MagicMock()
    hass.http.async_register_static_paths = AsyncMock(
        side_effect=Exception("Test error")
    )

    with patch(
        "custom_components.daikin_cycle_ml.frontend._LOGGER.exception"
    ) as mock_log:
        await async_register_frontend(hass)
        mock_log.assert_called_once()
