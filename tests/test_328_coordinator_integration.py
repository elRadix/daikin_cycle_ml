"""#328 Integration tests: coordinator lifecycle wiring for dhw_present.

These tests exercise the full path from snap.attrs → last_attrs →
_resolve_dhw_present → detector._dhw_present. They close the gap that
unit tests on _resolve_dhw_present alone could not catch (helper
correctness != helper is actually invoked in production flow).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from custom_components.daikin_cycle_ml.const import (
    CONF_DHW_PRESENT, DHW_PRESENT_AUTO, DHW_PRESENT_NEVER,
    ATTR_3WAY_VALVE, ATTR_DHW_TANK_TEMP,
)
from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)


def _mk_coord(hass, options=None):
    entry = MagicMock()
    entry.options = options or {}
    entry.data = {}
    return DaikinCycleMLCoordinator(hass, entry)


@pytest.mark.asyncio
async def test_ensure_dhw_present_resolves_from_valve(hass):
    coord = _mk_coord(hass)
    snap = MagicMock(); snap.attrs = {ATTR_3WAY_VALVE: True}
    await coord._async_ensure_dhw_present(snap)
    assert coord.dhw_present is True
    assert coord.detector._dhw_present is True
    assert coord._dhw_present_resolved is True
    assert coord._dhw_present_source == "tier1_attrs"


@pytest.mark.asyncio
async def test_ensure_dhw_present_override_never_wins(hass):
    coord = _mk_coord(hass, {CONF_DHW_PRESENT: DHW_PRESENT_NEVER})
    snap = MagicMock(); snap.attrs = {ATTR_3WAY_VALVE: True}  # valve says yes
    await coord._async_ensure_dhw_present(snap)
    assert coord.dhw_present is False      # override wins
    assert coord.detector._dhw_present is False
    assert coord._dhw_present_source == "override_never"


@pytest.mark.asyncio
async def test_ensure_dhw_present_runs_once(hass):
    coord = _mk_coord(hass)
    coord._resolve_dhw_present = AsyncMock(return_value=True)
    snap = MagicMock(); snap.attrs = {"Operation Mode": "Heating"}
    await coord._async_ensure_dhw_present(snap)
    await coord._async_ensure_dhw_present(snap)
    assert coord._resolve_dhw_present.await_count == 1


@pytest.mark.asyncio
async def test_last_attrs_updated_each_tick(hass):
    coord = _mk_coord(hass)
    snap1 = MagicMock(); snap1.attrs = {"foo": 1}
    await coord._async_ensure_dhw_present(snap1)
    assert coord.last_attrs == {"foo": 1}
    snap2 = MagicMock(); snap2.attrs = {"bar": 2}
    await coord._async_ensure_dhw_present(snap2)
    assert coord.last_attrs == {"bar": 2}


@pytest.mark.asyncio
async def test_resolution_failure_defaults_to_true(hass):
    coord = _mk_coord(hass)
    coord._resolve_dhw_present = AsyncMock(side_effect=Exception("boom"))
    snap = MagicMock(); snap.attrs = {"Operation Mode": "Heating"}
    await coord._async_ensure_dhw_present(snap)
    assert coord.dhw_present is True
    assert coord._dhw_present_source == "fallback_on_error"


@pytest.mark.asyncio
async def test_resolve_auto_history_from_db(hass):
    coord = _mk_coord(hass, {CONF_DHW_PRESENT: DHW_PRESENT_AUTO})
    coord.db = MagicMock()
    coord.db.async_get_dhw_cycle_count = AsyncMock(return_value=3)
    snap = MagicMock(); snap.attrs = {"Operation Mode": "Heating"}  # no DHW signals
    await coord._async_ensure_dhw_present(snap)
    assert coord.dhw_present is True
    assert coord._dhw_present_source == "tier3_history"


@pytest.mark.asyncio
async def test_resolve_auto_default_false_no_signals(hass):
    """#176 Frans: no valve, no tank, no history -> False (bypass active)."""
    coord = _mk_coord(hass, {CONF_DHW_PRESENT: DHW_PRESENT_AUTO})
    coord.db = MagicMock()
    coord.db.async_get_dhw_cycle_count = AsyncMock(return_value=0)
    snap = MagicMock(); snap.attrs = {"Operation Mode": "Heating"}
    await coord._async_ensure_dhw_present(snap)
    assert coord.dhw_present is False
    assert coord._dhw_present_source == "tier4_default"


# ==== Bug A: AST contract — ensure MUST run before detector.update ====

def test_async_update_data_ensure_before_detector_update():
    """_async_ensure_dhw_present must be called BEFORE detector.update so
    tick-1 classification uses the resolved dhw_present (Phase 3 regression)."""
    import ast
    from pathlib import Path
    src = Path("custom_components/daikin_cycle_ml/coordinator.py").read_text()
    tree = ast.parse(src)
    cls = next(n for n in tree.body
               if isinstance(n, ast.ClassDef) and n.name == "DaikinCycleMLCoordinator")
    upd = next(n for n in cls.body
               if isinstance(n, ast.AsyncFunctionDef) and n.name == "_async_update_data")
    ensure_lines = [
        n.lineno for n in ast.walk(upd)
        if isinstance(n, ast.Attribute) and n.attr == "_async_ensure_dhw_present"
    ]
    update_lines = [
        n.lineno for n in ast.walk(upd)
        if isinstance(n, ast.Attribute) and n.attr == "update"
        and isinstance(n.value, ast.Attribute) and n.value.attr == "detector"
    ]
    assert ensure_lines, "_async_ensure_dhw_present not called in _async_update_data"
    assert update_lines, "detector.update not called in _async_update_data"
    assert min(ensure_lines) < min(update_lines), (
        f"ORDERING BUG: ensure at {min(ensure_lines)}, update at {min(update_lines)}. "
        f"tick-1 classification will use stale dhw_present."
    )


# ==== Bug B: Empty-attrs tick must not lock in tier4 default ====

@pytest.mark.asyncio
async def test_ensure_dhw_present_does_not_lock_on_empty_attrs(hass):
    """Frozen ticks (attrs={}) must not resolve to tier4 and lock the value.
    Otherwise #167 auto-detection never sees the valve that arrives next tick."""
    coord = _mk_coord(hass, {CONF_DHW_PRESENT: DHW_PRESENT_AUTO})
    coord.db = MagicMock()
    coord.db.async_get_dhw_cycle_count = AsyncMock(return_value=0)
    snap = MagicMock(); snap.attrs = {}
    await coord._async_ensure_dhw_present(snap)
    assert coord._dhw_present_resolved is False, (
        "premature resolution on empty attrs — would lock out valve discovery"
    )
    snap.attrs = {ATTR_3WAY_VALVE: True}
    await coord._async_ensure_dhw_present(snap)
    assert coord.dhw_present is True
    assert coord._dhw_present_source == "tier1_attrs"
    assert coord._dhw_present_resolved is True


# ==== End-to-end: tick-1 classifies with resolved dhw_present ====

@pytest.mark.asyncio
async def test_tick_1_classifies_with_resolved_dhw_present(hass):
    """Chain: snap → _async_ensure_dhw_present → detector.update → mode.

    For #176 Frans (override=never, valve=True ghost):
    without ordering fix, tick-1 classifies as 'dhw' (ghost);
    with fix, tick-1 classifies as 'heating'.
    """
    from custom_components.daikin_cycle_ml.const import (
        ATTR_OPERATION_MODE, ATTR_INV_FREQUENCY_RPS,
    )

    coord = _mk_coord(hass, {CONF_DHW_PRESENT: DHW_PRESENT_NEVER})
    attrs = {
        ATTR_3WAY_VALVE: True,                  # ghost valve — would say DHW
        ATTR_OPERATION_MODE: "Heating",         # real signal says heating
        ATTR_INV_FREQUENCY_RPS: 50.0,           # > 3.0 threshold -> RUNNING
    }
    snap = MagicMock(); snap.attrs = attrs

    await coord._async_ensure_dhw_present(snap)
    assert coord.detector._dhw_present is False, "override_never not applied"

    # FSM: IDLE -> RUNNING may need 1-2 ticks
    for tick in range(3):
        coord.detector.update(attrs, now=1000.0 + tick * 30.0, power_w=None)
        if coord.detector.snapshot()["mode"] != "unknown":
            break
    mode = coord.detector.snapshot()["mode"]
    assert mode == "heating", (
        f"BUG: classified as {mode!r} (dhw_present={coord.detector._dhw_present})"
    )


@pytest.mark.asyncio
async def test_tick_1_default_auto_valve_detects_dhw(hass):
    """#167: bool valve present, no override → tick-1 detects DHW."""
    from custom_components.daikin_cycle_ml.const import (
        ATTR_OPERATION_MODE, ATTR_INV_FREQUENCY_RPS,
    )

    coord = _mk_coord(hass, {CONF_DHW_PRESENT: DHW_PRESENT_AUTO})
    coord.db = MagicMock()
    coord.db.async_get_dhw_cycle_count = AsyncMock(return_value=0)
    attrs = {
        ATTR_3WAY_VALVE: True,
        ATTR_OPERATION_MODE: "Heating",
        ATTR_INV_FREQUENCY_RPS: 50.0,           # > 3.0 threshold -> RUNNING
    }
    snap = MagicMock(); snap.attrs = attrs

    await coord._async_ensure_dhw_present(snap)
    assert coord.detector._dhw_present is True, "tier1 auto-detect failed"

    for tick in range(3):
        coord.detector.update(attrs, now=1000.0 + tick * 30.0, power_w=None)
        if coord.detector.snapshot()["mode"] != "unknown":
            break
    mode = coord.detector.snapshot()["mode"]
    assert mode == "dhw", (
        f"BUG: classified as {mode!r} (dhw_present={coord.detector._dhw_present})"
    )
