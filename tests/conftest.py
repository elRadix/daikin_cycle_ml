"""Shared pytest configuration for Daikin Cycle ML tests."""

from __future__ import annotations

import sys
from pathlib import Path

# CRITICAL: insert repo root BEFORE pytest_plugins triggers phcc,
# because phcc rewrites sys.path during plugin load and would
# otherwise drop the repo root (52b8g).
_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

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

    with (
        patch.object(
            hass.config_entries,
            "async_reload",
            new=AsyncMock(return_value=True),
        ),
        patch.object(
            hass.config_entries,
            "async_schedule_reload",
            new=lambda *a, **k: None,
        ),
    ):
        yield

@pytest.fixture
def patched_compat(monkeypatch):
    """v1.19.9 R647: shared fixture for build_compat_view patching."""
    import custom_components.daikin_cycle_ml.coordinator as coord_mod
    def _fake_build_compat(a):
        if isinstance(a, dict):
            return a.get("__test_attrs__", a)
        return {}
    monkeypatch.setattr(coord_mod, "build_compat_view", _fake_build_compat)


@pytest.fixture(autouse=True)
def mock_frontend_dependency(request):
    """Mark the frontend loaded for tests that set the integration up.

    manifest.json depends on ``frontend`` (the card is served and loaded
    by the integration); the test HA has no frontend package. Only tests
    that use ``hass`` are touched: requesting ``hass`` for every test
    would build a Home Assistant instance for each sync test too.
    """
    if "hass" not in request.fixturenames:
        return
    hass = request.getfixturevalue("hass")
    hass.config.components.add("frontend")
    hass.data.setdefault("frontend_extra_module_url", set())
