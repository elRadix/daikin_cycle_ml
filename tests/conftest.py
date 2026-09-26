"""Shared pytest configuration for Daikin Cycle ML tests."""
from __future__ import annotations

import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in every test."""
    yield

@pytest.fixture(autouse=True)
def _disable_options_reload(hass):
    """OptionsFlowWithReload triggers entry reload; skip in unit tests."""
    from unittest.mock import AsyncMock, patch
    with patch.object(
        hass.config_entries, "async_reload",
        new=AsyncMock(return_value=True),
    ), patch.object(
        hass.config_entries, "async_schedule_reload",
        new=lambda *a, **k: None,
    ):
        yield
