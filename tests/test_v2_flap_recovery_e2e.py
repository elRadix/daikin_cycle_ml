"""v1.20.0 #281 Suite #2: source flap recovery E2E.

Proves graceful degradation + recovery when the source comes and goes.

Scenarios:
1. mono flapping: present -> drop -> back -> normal
2. v2 flapping: 12 entities -> 0 -> 12
3. cross-source: mono drop + v2 present -> AUTO picks v2
4. source_stale alert fires at correct timing (> 2x interval)
5. Recovery: stale -> healthy clears

R598: real _async_update_data ticks, real stale detection, real AUTO dispatch.
"""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.binary_sensor import (
    _is_source_stale, SOURCE_STALE_FACTOR,
)
from custom_components.daikin_cycle_ml.const import (
    ATTR_BUH_STEP1, ATTR_BUH_STEP2, ATTR_COP, ATTR_DEFROST_OPERATION,
    ATTR_FLOW_SENSOR, ATTR_INLET_WATER_R4T,
    ATTR_IU_OPERATION_MODE, ATTR_LEAVING_WATER_AFTER_BUH,
    ATTR_LW_SETPOINT, ATTR_OPERATION_MODE, ATTR_OUTDOOR_AIR_R1T,
    ATTR_WATER_PUMP_OPERATION, ATTR_3WAY_VALVE,
    CONF_SOURCE_TYPE, DEFAULT_INDIVIDUAL_PREFIX,
    SOURCE_TYPE_AUTO, SOURCE_TYPE_INDIVIDUAL, SOURCE_TYPE_MONOLITHIC,
    UPDATE_INTERVAL_SECONDS,
)
from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)
from custom_components.daikin_cycle_ml.engine.espaltherma_v2.slug import (
    make_json_key,
)

_COORD_MOD = "custom_components.daikin_cycle_ml.coordinator"


def _bare(source_type=SOURCE_TYPE_AUTO):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    # v1.20.0 #281: __new__ skips __init__, so all default attributes are
    # missing. Auto-populate them via AST introspection of __init__ to
    # avoid the whack-a-mole of missing `self._X` attributes one by one.
    # Only literal defaults are set; call-based defaults are skipped and
    # replaced by explicit mocks below.
    import ast
    from pathlib import Path as _P
    _src = _P(__file__).parent.parent / "custom_components" / "daikin_cycle_ml" / "coordinator.py"
    _tree = ast.parse(_src.read_text())
    for _node in ast.walk(_tree):
        if isinstance(_node, ast.FunctionDef) and _node.name == "__init__":
            for _stmt in _node.body:
                # AnnAssign: self._x: type = default
                if isinstance(_stmt, ast.AnnAssign) and isinstance(_stmt.target, ast.Attribute):
                    _attr = _stmt.target.attr
                    if _attr.startswith("_") and _stmt.value is not None:
                        try:
                            setattr(c, _attr, ast.literal_eval(_stmt.value))
                        except (ValueError, TypeError):
                            pass
                # Assign: self._x = default
                elif isinstance(_stmt, ast.Assign):
                    for _tgt in _stmt.targets:
                        if isinstance(_tgt, ast.Attribute) and _tgt.attr.startswith("_"):
                            try:
                                setattr(c, _tgt.attr, ast.literal_eval(_stmt.value))
                            except (ValueError, TypeError):
                                pass
            break

    # Now override with test-specific values and mocks
    c.hass = MagicMock()
    c.hass.states = MagicMock()
    c.hass.states.get = MagicMock(return_value=None)
    c.entry = MagicMock()
    c.entry.data = {CONF_SOURCE_TYPE: source_type}
    c.entry.options = {}
    c.source_type = source_type
    c.individual_prefix = DEFAULT_INDIVIDUAL_PREFIX
    c.source_entity = "sensor.althermasensors"
    c.options = {}
    c.store = MagicMock()
    c.store.daily_reset_if_needed = MagicMock(return_value=False)
    c.detector = MagicMock()
    c.detector.state = "idle"
    c.detector.snapshot = MagicMock(return_value={"mode": "unknown", "start_ts": 0.0})
    c.detector.update = MagicMock(return_value=None)
    c.db = None
    c._runtime_day_key = "2026-11-07"
    c._energy_day_key = "2026-11-07"
    c._track_setpoint = MagicMock()
    c._read_power_w = MagicMock(return_value=None)
    c._read_cop = MagicMock(return_value=None)
    c._read_cop_effective = MagicMock(return_value=(None, "none"))
    c._compute_electrical_power = MagicMock(return_value=(None, "none"))
    c._compute_setpoint_oscillating = MagicMock(return_value=False)
    c._accumulate_cycle_samples = MagicMock()
    c._process_new_cycle = AsyncMock(return_value=None)
    c._tick_buh_and_defrost = MagicMock()
    c._tick_energy = MagicMock()
    c._maybe_persist_accumulators = AsyncMock(return_value=None)
    c._maybe_reset_daily_accumulators = MagicMock()
    c._maybe_collect_cop_sample = AsyncMock(return_value=None)
    c._refresh_cop_today = AsyncMock(return_value=None)
    c._maybe_refresh_stooklijn = AsyncMock(return_value=None)
    c._refresh_7d_rollups = AsyncMock(return_value=None)
    c._async_dispatch_alerts = AsyncMock(return_value=None)
    c._async_check_repairs = AsyncMock(return_value=None)
    c._track_mode_transition = MagicMock()
    c._is_hybrid_install = MagicMock(return_value=False)
    c._auto_last_chosen = ""
    c._source_resolution = {}
    c._last_mode_change_ts = 0.0
    return c


def _full_attrs():
    return {
        ATTR_OPERATION_MODE: "Heating",
        ATTR_IU_OPERATION_MODE: "Heating",
        ATTR_3WAY_VALVE: "Off:Space",
        ATTR_DEFROST_OPERATION: False,
        ATTR_LEAVING_WATER_AFTER_BUH: 35.0,
        ATTR_INLET_WATER_R4T: 30.0,
        ATTR_OUTDOOR_AIR_R1T: 8.5,
        ATTR_FLOW_SENSOR: 15.2,
        ATTR_WATER_PUMP_OPERATION: True,
        ATTR_BUH_STEP1: False,
        ATTR_BUH_STEP2: False,
        ATTR_LW_SETPOINT: 40.0,
        ATTR_COP: 4.5,
    }


def _set_mono_available(c, available: bool):
    if available:
        state = MagicMock()
        state.attributes = _full_attrs()
        c.hass.states.get = MagicMock(return_value=state)
    else:
        c.hass.states.get = MagicMock(return_value=None)


def _set_v2_available(c, available: bool, monkeypatch):
    import custom_components.daikin_cycle_ml.coordinator as coord_mod
    from custom_components.daikin_cycle_ml.const import REQUIRED_ATTRIBUTES
    if available:
        def fake(h, prefix=None, custom_map=None):
            return SimpleNamespace(
                attrs=_full_attrs(),
                missing_required=[], collisions=[], discovered_count=12,
                missing_consumed=[],
            )
    else:
        # v1.20.0 #281: "v2 empty" must return 0/12 coverage (all 12
        # required missing), NOT 11/12. Missing only 1 item would make
        # coverage=11, which AUTO considers "better than mono 0/12".
        def fake(h, prefix=None, custom_map=None):
            return SimpleNamespace(
                attrs={}, missing_required=list(REQUIRED_ATTRIBUTES),
                collisions=[], discovered_count=0, missing_consumed=[],
            )
    monkeypatch.setattr(coord_mod, "resolve_attrs", fake)


def _set_read_mono(c, monkeypatch, missing=None):
    import custom_components.daikin_cycle_ml.coordinator as coord_mod
    monkeypatch.setattr(coord_mod, "read", lambda *a, **kw: _full_attrs())
    monkeypatch.setattr(
        coord_mod, "missing_required",
        lambda a: missing if missing is not None else [],
    )


# ============================================================
# 1. Mono flapping
# ============================================================


@pytest.mark.asyncio
async def test_mono_flap_drop_recovery(monkeypatch, freezer) -> None:
    """Mono present -> drop -> present -> last_success advances on recovery.

    Product behaviour: on complete drop, the dispatch returns early with
    a FRESH DataSnapshot whose last_success_ts is the default 0.0 (the
    drop path returns before `snap.last_success_ts = now`). We assert
    recovery is monotone via freezegun for determinism.
    """
    freezer.move_to("2026-11-07 12:00:00")
    c = _bare(SOURCE_TYPE_MONOLITHIC)
    _set_read_mono(c, monkeypatch)
    _set_mono_available(c, True)

    # Tick 1: healthy
    snap1 = await c._async_update_data()
    ts1 = snap1.last_success_ts
    assert ts1 > 0

    # Drop source -> early return with fresh DataSnapshot (last_success=0)
    freezer.move_to("2026-11-07 12:00:30")
    _set_mono_available(c, False)
    await c._async_update_data()

    # Recover -> last_success bumped, monotone vs ts1
    freezer.move_to("2026-11-07 12:01:00")
    _set_mono_available(c, True)
    snap3 = await c._async_update_data()
    assert snap3.last_success_ts > ts1, "recovery must bump last_success_ts"


@pytest.mark.asyncio
async def test_mono_flap_stale_fires_after_threshold(monkeypatch) -> None:
    """source_stale == True when age > STALE_FACTOR * interval."""
    c = _bare(SOURCE_TYPE_MONOLITHIC)
    _set_read_mono(c, monkeypatch)
    _set_mono_available(c, True)

    snap = await c._async_update_data()
    # Simulate long gap
    threshold = SOURCE_STALE_FACTOR * UPDATE_INTERVAL_SECONDS
    snap.last_success_ts = time.time() - threshold - 5
    assert _is_source_stale(snap, c) is True


@pytest.mark.asyncio
async def test_mono_flap_stale_clears_after_recovery(monkeypatch) -> None:
    """After recovery, source_stale == False."""
    c = _bare(SOURCE_TYPE_MONOLITHIC)
    _set_read_mono(c, monkeypatch)
    _set_mono_available(c, True)

    # Simulate stale
    stale_snap = MagicMock()
    stale_snap.last_success_ts = time.time() - 3600
    assert _is_source_stale(stale_snap, c) is True

    # Recover
    snap = await c._async_update_data()
    assert _is_source_stale(snap, c) is False


# ============================================================
# 2. V2 flapping
# ============================================================


@pytest.mark.asyncio
async def test_v2_flap_drop_no_last_success(monkeypatch) -> None:
    """v2 with 0 discovered -> last_success NOT bumped (GAP-4)."""
    c = _bare(SOURCE_TYPE_INDIVIDUAL)
    _set_v2_available(c, False, monkeypatch)
    snap = await c._async_update_data()
    assert snap.last_success_ts == 0.0


@pytest.mark.asyncio
async def test_v2_flap_recovery_bumps_last_success(monkeypatch) -> None:
    """v2 recovery (discovered > 0) -> last_success bumped."""
    c = _bare(SOURCE_TYPE_INDIVIDUAL)
    _set_v2_available(c, True, monkeypatch)
    snap = await c._async_update_data()
    assert snap.last_success_ts > 0


@pytest.mark.asyncio
async def test_v2_flap_full_cycle(monkeypatch, freezer) -> None:
    """v2: present -> drop -> present -> last_success monotone.

    GAP-4 preserved: 0 discovered -> last_success stays 0.0 on the drop
    tick. Recovery bumps it.
    """
    freezer.move_to("2026-11-07 12:00:00")
    c = _bare(SOURCE_TYPE_INDIVIDUAL)
    _set_v2_available(c, True, monkeypatch)
    snap1 = await c._async_update_data()
    ts1 = snap1.last_success_ts
    assert ts1 > 0

    # Drop -> fresh DataSnapshot with last_success=0 (GAP-4)
    freezer.move_to("2026-11-07 12:00:30")
    _set_v2_available(c, False, monkeypatch)
    snap_drop = await c._async_update_data()
    assert snap_drop.last_success_ts == 0.0, (
        "v2 drop must NOT bump last_success (GAP-4 preserved)"
    )

    # Recover
    freezer.move_to("2026-11-07 12:01:00")
    _set_v2_available(c, True, monkeypatch)
    snap3 = await c._async_update_data()
    assert snap3.last_success_ts > ts1


# ============================================================
# 3. Cross-source AUTO
# ============================================================


@pytest.mark.asyncio
async def test_auto_mono_drops_v2_takes_over(monkeypatch) -> None:
    """AUTO: mono drops -> v2 still available -> switch to v2 (no freeze)."""
    c = _bare(SOURCE_TYPE_AUTO)
    _set_read_mono(c, monkeypatch)
    _set_mono_available(c, True)
    _set_v2_available(c, True, monkeypatch)

    # Tick 1: both present, tie -> v2 wins (per Q1)
    await c._async_update_data()
    assert c._source_resolution["chosen"] == "individual"

    # Drop mono
    _set_mono_available(c, False)
    await c._async_update_data()
    # Still v2 (no change in chosen)
    assert c._source_resolution["chosen"] == "individual"
    assert c._source_resolution["mono_coverage"] == 0


@pytest.mark.asyncio
async def test_auto_v2_drops_mono_takes_over(monkeypatch) -> None:
    """AUTO: v2 drops -> mono still available -> switch back to mono."""
    c = _bare(SOURCE_TYPE_AUTO)
    _set_read_mono(c, monkeypatch)
    _set_mono_available(c, True)
    _set_v2_available(c, True, monkeypatch)

    # Tick 1: both full -> v2 (tie)
    await c._async_update_data()
    assert c._source_resolution["chosen"] == "individual"

    # Drop v2
    _set_v2_available(c, False, monkeypatch)
    snap = await c._async_update_data()
    # mono wins now (v2 0/12 < mono 12/12)
    assert c._source_resolution["chosen"] == "monolithic"
    assert c._source_resolution["v2_coverage"] == 0
    assert snap.last_success_ts > 0, "mono keeps last_success alive"


@pytest.mark.asyncio
async def test_auto_both_drop_freeze(monkeypatch) -> None:
    """AUTO: both drop -> freeze (Q2), last_success not bumped."""
    c = _bare(SOURCE_TYPE_AUTO)
    _set_read_mono(c, monkeypatch)
    _set_mono_available(c, False)
    _set_v2_available(c, False, monkeypatch)
    snap = await c._async_update_data()
    assert c._source_resolution["chosen"] == "monolithic"
    assert c._source_resolution["mono_coverage"] == 0
    assert c._source_resolution["v2_coverage"] == 0
    assert snap.last_success_ts == 0.0


@pytest.mark.asyncio
async def test_auto_full_flap_recovery(monkeypatch) -> None:
    """AUTO: both present -> both drop -> both back -> normal resumes."""
    c = _bare(SOURCE_TYPE_AUTO)
    _set_read_mono(c, monkeypatch)
    _set_v2_available(c, True, monkeypatch)
    _set_mono_available(c, True)

    # Healthy
    await c._async_update_data()
    assert c._source_resolution["chosen"] == "individual"

    # Both drop
    _set_mono_available(c, False)
    _set_v2_available(c, False, monkeypatch)
    await c._async_update_data()
    assert c._source_resolution["chosen"] == "monolithic"
    assert c._source_resolution["mono_coverage"] == 0
    assert c._source_resolution["v2_coverage"] == 0

    # Both recover
    _set_mono_available(c, True)
    _set_v2_available(c, True, monkeypatch)
    await c._async_update_data()
    assert c._source_resolution["chosen"] == "individual"
    assert c._source_resolution["v2_coverage"] == 12


# ============================================================
# 4. Freeze behaviour during outage
# ============================================================


@pytest.mark.asyncio
async def test_mono_outage_does_not_advance_detector(monkeypatch) -> None:
    """Mono drop -> freeze -> detector.update not called."""
    c = _bare(SOURCE_TYPE_MONOLITHIC)
    _set_read_mono(c, monkeypatch)
    _set_mono_available(c, False)
    await c._async_update_data()
    c.detector.update.assert_not_called()


@pytest.mark.asyncio
async def test_mono_recovery_resumes_detector(monkeypatch) -> None:
    """Mono recovery -> detector.update called."""
    c = _bare(SOURCE_TYPE_MONOLITHIC)
    _set_read_mono(c, monkeypatch)
    _set_mono_available(c, True)
    await c._async_update_data()
    c.detector.update.assert_called()
