import pytest
from unittest.mock import AsyncMock, MagicMock
from custom_components.daikin_cycle_ml.const import (
    CONF_DHW_PRESENT, DHW_PRESENT_AUTO, DHW_PRESENT_ALWAYS,
    DHW_PRESENT_NEVER, ATTR_3WAY_VALVE, ATTR_DHW_TANK_TEMP,
    ATTR_OPERATION_MODE, ATTR_IU_OPERATION_MODE,
)
from custom_components.daikin_cycle_ml.engine.cycle_detector import (
    CycleDetector, _parse_valve,
)
from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator

# --- D1: _parse_valve must accept booleans (#167) ---
def test_parse_valve_bool_true():
    assert _parse_valve({ATTR_3WAY_VALVE: True}) == "ON"

def test_parse_valve_bool_false():
    assert _parse_valve({ATTR_3WAY_VALVE: False}) == "OFF"

def test_parse_valve_string_on():
    assert _parse_valve({ATTR_3WAY_VALVE: "ON"}) == "ON"

def test_parse_valve_missing():
    assert _parse_valve({}) is None

# --- D2: _classify_mode valve-corroboration ---
def test_classify_dhw_present_valve_on_bool():
    # #167: Operation Mode says Heating, valve says True (bool) → must be dhw
    det = CycleDetector({}, dhw_present=True)
    attrs = {ATTR_3WAY_VALVE: True, ATTR_OPERATION_MODE: "Heating"}
    assert det._classify_mode(attrs) == "dhw"

def test_classify_dhw_present_valve_off():
    # Valve OFF → use operation mode
    det = CycleDetector({}, dhw_present=True)
    attrs = {ATTR_3WAY_VALVE: False, ATTR_OPERATION_MODE: "Heating"}
    assert det._classify_mode(attrs) == "heating"

def test_classify_dhw_present_no_valve_opmode():
    # No valve, operation mode decides
    det = CycleDetector({}, dhw_present=True)
    attrs = {ATTR_IU_OPERATION_MODE: "DHW"}
    assert det._classify_mode(attrs) == "dhw"

# --- #176 Frans: dhw_present=False bypasses everything ---
def test_classify_bypass_when_no_dhw():
    det = CycleDetector({}, dhw_present=False)
    attrs = {ATTR_3WAY_VALVE: True, ATTR_OPERATION_MODE: "Heating"}
    assert det._classify_mode(attrs) == "heating"

# --- Override priority ---
@pytest.mark.asyncio
async def test_resolve_override_always(hass):
    entry = MagicMock()
    entry.options = {CONF_DHW_PRESENT: DHW_PRESENT_ALWAYS}
    coord = DaikinCycleMLCoordinator(hass, entry)
    assert await coord._resolve_dhw_present() is True

@pytest.mark.asyncio
async def test_resolve_override_never(hass):
    entry = MagicMock()
    entry.options = {CONF_DHW_PRESENT: DHW_PRESENT_NEVER}
    coord = DaikinCycleMLCoordinator(hass, entry)
    assert await coord._resolve_dhw_present() is False

# === Phase 4: Coverage for _resolve_dhw_present auto-detect branches ===

@pytest.mark.asyncio
async def test_resolve_auto_valve_in_attrs(hass):
    """Cover: 3way valve attr present → return True (1751-1753)."""
    entry = MagicMock(); entry.options = {CONF_DHW_PRESENT: DHW_PRESENT_AUTO}
    coord = DaikinCycleMLCoordinator(hass, entry)
    coord.last_attrs = {ATTR_3WAY_VALVE: True}
    assert await coord._resolve_dhw_present() is True

@pytest.mark.asyncio
async def test_resolve_auto_dhw_tank_temp(hass):
    """Cover: tank temp attr (OR branch) → return True (1753)."""
    entry = MagicMock(); entry.options = {CONF_DHW_PRESENT: DHW_PRESENT_AUTO}
    coord = DaikinCycleMLCoordinator(hass, entry)
    coord.last_attrs = {ATTR_DHW_TANK_TEMP: 45.0}
    assert await coord._resolve_dhw_present() is True

@pytest.mark.asyncio
async def test_resolve_auto_db_has_dhw(hass):
    """Cover: db has method, count > 0 → True (1754-1755)."""
    entry = MagicMock(); entry.options = {CONF_DHW_PRESENT: DHW_PRESENT_AUTO}
    coord = DaikinCycleMLCoordinator(hass, entry)
    coord.last_attrs = {}
    coord.db = MagicMock(); coord.db.async_get_dhw_cycle_count = AsyncMock(return_value=5)
    assert await coord._resolve_dhw_present() is True

@pytest.mark.asyncio
async def test_resolve_auto_db_empty(hass):
    """Cover: db has method, count == 0 → False (1755-1756)."""
    entry = MagicMock(); entry.options = {CONF_DHW_PRESENT: DHW_PRESENT_AUTO}
    coord = DaikinCycleMLCoordinator(hass, entry)
    coord.last_attrs = {}
    coord.db = MagicMock(); coord.db.async_get_dhw_cycle_count = AsyncMock(return_value=0)
    assert await coord._resolve_dhw_present() is False

@pytest.mark.asyncio
async def test_resolve_auto_db_without_method(hass):
    """Cover: db has no method → False (1754 hasattr False)."""
    entry = MagicMock(); entry.options = {CONF_DHW_PRESENT: DHW_PRESENT_AUTO}
    coord = DaikinCycleMLCoordinator(hass, entry)
    coord.last_attrs = {}
    coord.db = object()  # bare object, no async_get_dhw_cycle_count
    assert await coord._resolve_dhw_present() is False

# === DB async_get_dhw_cycle_count coverage ===

@pytest.mark.asyncio
async def test_db_get_dhw_cycle_count_with_rows():
    """Cover: row truthy → return row[0] (1161-1164 truthy)."""
    from custom_components.daikin_cycle_ml.storage.db import CycleDB
    db = CycleDB.__new__(CycleDB)
    cur = AsyncMock(); cur.fetchone = AsyncMock(return_value=(3,))
    conn = MagicMock(); conn.execute = AsyncMock(return_value=cur)
    db._require = MagicMock(return_value=conn)
    assert await db.async_get_dhw_cycle_count() == 3

@pytest.mark.asyncio
async def test_db_get_dhw_cycle_count_empty():
    from custom_components.daikin_cycle_ml.storage.db import CycleDB
    db = CycleDB.__new__(CycleDB)
    cur = AsyncMock(); cur.fetchone = AsyncMock(return_value=None)
    conn = MagicMock(); conn.execute = AsyncMock(return_value=cur)
    db._require = MagicMock(return_value=conn)
    assert await db.async_get_dhw_cycle_count() == 0


# === R1 isolation: coordinator __init__ must not register hass timers ===

@pytest.mark.asyncio
async def test_coordinator_init_does_not_register_timers(hass):
    """Constructing the coordinator must be side-effect free on hass timers."""
    from unittest.mock import patch
    import custom_components.daikin_cycle_ml.coordinator as cmod
    with patch.object(cmod, "async_track_time_change") as ttc, \
         patch.object(cmod, "async_track_time_interval") as tti:
        entry = MagicMock(); entry.options = {}
        DaikinCycleMLCoordinator(hass, entry)
        assert ttc.call_count == 0, f"async_track_time_change: {ttc.call_count}×"
        assert tti.call_count == 0, f"async_track_time_interval: {tti.call_count}×"
