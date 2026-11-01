from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daikin_cycle_ml.diagnostics import async_get_config_entry_diagnostics


@pytest.mark.asyncio
async def test_diagnostics_no_secrets(hass):
    entry = MockConfigEntry(
        domain="daikin_cycle_ml",
        entry_id="diag_test",
        options={"notify_service": "notify.my_secret_service"},
    )
    entry.runtime_data = MagicMock()
    entry.runtime_data.data = MagicMock()
    entry.runtime_data.db = MagicMock()

    diag = await async_get_config_entry_diagnostics(hass, entry)
    diag_str = str(diag)
    assert "my_secret_service" not in diag_str
    assert "**REDACTED**" in diag_str or "notify_service" not in diag_str
