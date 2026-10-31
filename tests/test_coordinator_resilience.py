
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator


@pytest.mark.asyncio
async def test_coordinator_handles_source_offline(hass):
    entry = MockConfigEntry(domain="daikin_cycle_ml")
    coord = DaikinCycleMLCoordinator(hass, entry)
    coord.source_entity = "sensor.offline_sensor"
    hass.states.async_set("sensor.offline_sensor", "unavailable")
    # Hij crasht niet, maar geeft een lege snapshot terug
    snap = await coord._async_update_data()
    assert snap is not None
    assert snap.attrs == {}
