"""#510: COP 0 with ESPAltherma v2 when a Stats sensor is shown in W.

The reporter switched "Stats: Electrical input estimated (kW)" to W in Home
Assistant (to compare it with a HomeWizard meter): its state became 1780
(W) instead of 1.78 (kW). The integration read 1780 kW -> COP 0.0039, and
the curve advice lost its samples. The entity's own unit now wins.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.daikin_cycle_ml import async_remove_entry, async_setup_entry, async_unload_entry
from custom_components.daikin_cycle_ml.const import (
    CONF_INDIVIDUAL_PREFIX,
    CONF_SOURCE_TYPE,
    DEFAULT_INDIVIDUAL_PREFIX,
    DOMAIN,
    SOURCE_TYPE_INDIVIDUAL,
)
from custom_components.daikin_cycle_ml.engine.espaltherma_v2.resolver import to_label_unit
from custom_components.daikin_cycle_ml.engine.espaltherma_v2.slug import make_json_key
from homeassistant.config_entries import ConfigEntryState

P = DEFAULT_INDIVIDUAL_PREFIX
BASE = {
    "Operation Mode": ("Heating", None), "I/U operation mode": ("Heating", None),
    "3way valve(On:DHW_Off:Space)": ("OFF", None), "Defrost Operation": ("OFF", None),
    "Leaving water temp. after BUH (R2T)": ("35.0", "°C"), "Inlet water temp.(R4T)": ("30.0", "°C"),
    "Outdoor air temp.(R1T)": ("6.0", "°C"), "Flow sensor (l/min)": ("19.8", "L/min"),
    "Water pump operation": ("ON", None), "BUH Step1": ("OFF", None), "BUH Step2": ("OFF", None),
    "LW setpoint (main)": ("35.0", "°C"), "INV frequency (rps)": ("42", "Hz"),
    "Stats: Heat output (kW)": ("6.9", "kW"),
}


async def _cop(hass, electrical: tuple[str, str]) -> float | None:
    for label, (val, unit) in {**BASE, "Stats: Electrical input estimated (kW)": electrical}.items():
        hass.states.async_set(f"{P}{make_json_key(label)}", val, {"unit_of_measurement": unit} if unit else {})
    entry = MockConfigEntry(domain=DOMAIN, entry_id=f"e510_{electrical[1]}", version=1, options={},
                            data={"model": "erga06eav3", CONF_SOURCE_TYPE: SOURCE_TYPE_INDIVIDUAL,
                                  CONF_INDIVIDUAL_PREFIX: P})
    entry.add_to_hass(hass)
    object.__setattr__(entry, "state", ConfigEntryState.SETUP_IN_PROGRESS)
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    try:
        await async_setup_entry(hass, entry)
        snap = await entry.runtime_data._async_update_data()
        assert snap.electrical_power_source == "espaltherma_v2_stats"
        assert snap.electrical_power_w == pytest.approx(1780.0)
        return snap.cop
    finally:
        for fn in (async_unload_entry, async_remove_entry):
            try:
                await fn(hass, entry)
            except Exception:
                pass


@pytest.mark.asyncio
async def test_stats_power_shown_in_watts(hass) -> None:
    assert await _cop(hass, ("1780", "W")) == pytest.approx(6.9 / 1.78, rel=0.01)


@pytest.mark.asyncio
async def test_stats_power_in_kilowatts_unchanged(hass) -> None:
    assert await _cop(hass, ("1.78", "kW")) == pytest.approx(6.9 / 1.78, rel=0.01)


def test_to_label_unit():
    kw, kwh = "Stats: Heat output (kW)", "Stats: Electricity today heating (kWh)"
    assert to_label_unit(1780.0, "W", kw) == pytest.approx(1.78)
    assert to_label_unit(0.002, "MW", kw) == pytest.approx(2.0)
    assert to_label_unit(12500.0, "Wh", kwh) == pytest.approx(12.5)
    assert to_label_unit(0.0125, "MWh", kwh) == pytest.approx(12.5)
    assert to_label_unit(95.0, "°F", "Leaving water temp. after BUH (R2T)") == pytest.approx(35.0)
    assert to_label_unit(1.78, "kW", kw) == 1.78
    assert to_label_unit(1780.0, None, kw) == 1780.0                 # no unit: as published
    assert to_label_unit("ON", "W", kw) == "ON" and to_label_unit(True, "W", kw) is True
    assert to_label_unit(5.0, "W", "INV frequency (rps)") == 5.0     # label without kW
    assert to_label_unit(5.0, "W", None) == 5.0
