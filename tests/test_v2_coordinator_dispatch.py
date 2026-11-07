"""RED tests for ESPAltherma v2 coordinator dispatch (issue #281).

R634: These tests MUST FAIL on current code if source-type dispatch is
missing. Expected RED failures:
- `resolve_attrs` not called in individual mode
- individual partial-missing still triggers monolithic-style freeze
- auto fallback to individual not wired

Regressions guarded (must remain green before AND after fix):
- monolithic partial-missing still freezes (#109)
- monolithic source-missing still returns early
- auto prefers monolithic when available
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

_COORD_MOD = "custom_components.daikin_cycle_ml.coordinator"

from custom_components.daikin_cycle_ml.coordinator import (
    DaikinCycleMLCoordinator,
)
from custom_components.daikin_cycle_ml.const import (
    ATTR_3WAY_VALVE,
    ATTR_BUH_STEP1,
    ATTR_BUH_STEP2,
    ATTR_DEFROST_OPERATION,
    ATTR_FLOW_SENSOR,
    ATTR_INLET_WATER_R4T,
    ATTR_IU_OPERATION_MODE,
    ATTR_LEAVING_WATER_AFTER_BUH,
    ATTR_LW_SETPOINT,
    ATTR_OPERATION_MODE,
    ATTR_OUTDOOR_AIR_R1T,
    ATTR_WATER_PUMP_OPERATION,
    CONF_INDIVIDUAL_PREFIX,
    CONF_SOURCE_TYPE,
    DEFAULT_INDIVIDUAL_PREFIX,
    REQUIRED_ATTRIBUTES,
    SOURCE_TYPE_AUTO,
    SOURCE_TYPE_INDIVIDUAL,
    SOURCE_TYPE_MONOLITHIC,
)


class _Reached(BaseException):
    """Sentinel to escape try/except Exception blocks in _async_update_data."""


def _full_attrs() -> dict[str, object]:
    return {
        ATTR_OPERATION_MODE: "Heating",
        ATTR_IU_OPERATION_MODE: "Heating",
        ATTR_3WAY_VALVE: "Off:Space",
        ATTR_DEFROST_OPERATION: False,
        ATTR_LEAVING_WATER_AFTER_BUH: 35.0,
        ATTR_INLET_WATER_R4T: 30.0,
        ATTR_OUTDOOR_AIR_R1T: 8.5,
        ATTR_FLOW_SENSOR: 15.0,
        ATTR_WATER_PUMP_OPERATION: True,
        ATTR_BUH_STEP1: False,
        ATTR_BUH_STEP2: False,
        ATTR_LW_SETPOINT: 40.0,
    }


def _bare(
    source_type: str = SOURCE_TYPE_MONOLITHIC,
    source_entity: str = "sensor.althermasensors",
    individual_prefix: str = DEFAULT_INDIVIDUAL_PREFIX,
) -> DaikinCycleMLCoordinator:
    """Bare coordinator with enough mocks to reach full tick processing."""
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.hass = MagicMock()
    c.hass.states.get = MagicMock(return_value=None)
    c.hass.states.async_all = MagicMock(return_value=[])
    c.entry = MagicMock()
    c.entry.data = {
        CONF_SOURCE_TYPE: source_type,
        CONF_INDIVIDUAL_PREFIX: individual_prefix,
        "source_sensor": source_entity,
    }
    c.entry.options = {}
    c.source_entity = source_entity
    c.source_type = source_type
    c.individual_prefix = individual_prefix
    c.options = {}
    c.store = MagicMock()
    c.store.daily_reset_if_needed = MagicMock(return_value=False)
    c.detector = MagicMock()
    c.detector.state = "running"
    c.detector.snapshot = MagicMock(
        return_value={"mode": "heating", "start_ts": 1700000000.0}
    )
    c.detector.update = MagicMock(return_value=None)
    c.db = None
    c._runtime_day_key = "2026-11-07"
    c._energy_day_key = "2026-11-07"
    c._track_setpoint = MagicMock()
    c._read_power_w = MagicMock(return_value=1500.0)
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
    c._refresh_alerts_today = AsyncMock(return_value=None)
    c._is_hybrid_install = MagicMock(return_value=False)
    return c


def _resolve_result(
    attrs: dict[str, object],
    missing: list[str] | None = None,
    discovered: int = 12,
    missing_consumed: list[str] | None = None,
) -> MagicMock:
    m = MagicMock()
    m.attrs = attrs
    m.missing_required = missing if missing is not None else []
    m.collisions = []
    m.missing_consumed = missing_consumed if missing_consumed is not None else []
    m.discovered_count = discovered
    return m


# ---------- individual mode: uses resolver ----------


@pytest.mark.asyncio
async def test_individual_mode_calls_resolve_attrs(monkeypatch) -> None:
    """RED: individual mode currently uses monolithic source_entity only."""
    c = _bare(source_type=SOURCE_TYPE_INDIVIDUAL)
    calls: list[str] = []

    def fake_resolve(hass, prefix=DEFAULT_INDIVIDUAL_PREFIX, custom_map=None):
        calls.append(prefix)
        return _resolve_result(_full_attrs())

    monkeypatch.setattr(f"{_COORD_MOD}.resolve_attrs", fake_resolve)
    c._tick_energy = MagicMock(side_effect=_Reached())
    with pytest.raises(_Reached):
        await c._async_update_data()
    assert calls == [DEFAULT_INDIVIDUAL_PREFIX]
    c.detector.update.assert_called_once()


@pytest.mark.asyncio
async def test_individual_mode_uses_custom_prefix(monkeypatch) -> None:
    """RED: prefix ignored until dispatch is wired."""
    c = _bare(
        source_type=SOURCE_TYPE_INDIVIDUAL,
        individual_prefix="sensor.custom_",
    )
    prefixes: list[str] = []

    def fake_resolve(hass, prefix=DEFAULT_INDIVIDUAL_PREFIX, custom_map=None):
        prefixes.append(prefix)
        return _resolve_result(_full_attrs())

    monkeypatch.setattr(f"{_COORD_MOD}.resolve_attrs", fake_resolve)
    c._tick_energy = MagicMock(side_effect=_Reached())
    with pytest.raises(_Reached):
        await c._async_update_data()
    assert prefixes == ["sensor.custom_"]


# ---------- individual mode: freeze policy ----------


@pytest.mark.asyncio
async def test_individual_partial_missing_does_not_freeze(monkeypatch) -> None:
    """RED: partial missing must proceed (no freeze) for individual mode.

    Non-BUH models never publish BUH Step1/Step2. Freezing on that would
    block cycle detection entirely. Per-label repairs handle it.
    """
    c = _bare(source_type=SOURCE_TYPE_INDIVIDUAL)
    partial = _full_attrs()
    missing = [ATTR_BUH_STEP1, ATTR_BUH_STEP2]
    for k in missing:
        del partial[k]
    monkeypatch.setattr(
        f"{_COORD_MOD}.resolve_attrs",
        lambda *a, **kw: _resolve_result(partial, missing=missing),
    )
    c._tick_energy = MagicMock(side_effect=_Reached())
    with pytest.raises(_Reached):
        await c._async_update_data()
    c.detector.update.assert_called_once()


@pytest.mark.asyncio
async def test_individual_full_outage_freezes(monkeypatch) -> None:
    """Individual with 0/12 attrs (total outage) -> freeze (#109 preserved).

    Tick still runs per #280, but detector is frozen.
    """
    c = _bare(source_type=SOURCE_TYPE_INDIVIDUAL)
    monkeypatch.setattr(
        f"{_COORD_MOD}.resolve_attrs",
        lambda *a, **kw: _resolve_result(
            {}, missing=list(REQUIRED_ATTRIBUTES), discovered=0
        ),
    )
    c._tick_buh_and_defrost = MagicMock(side_effect=_Reached())
    with pytest.raises(_Reached):
        await c._async_update_data()
    c.detector.update.assert_not_called()  # frozen


# ---------- auto mode ----------


@pytest.mark.asyncio
async def test_auto_prefers_monolithic_when_available(monkeypatch) -> None:
    """Regression: monolithic entity exists -> use it, never call resolve_attrs."""
    c = _bare(source_type=SOURCE_TYPE_AUTO)
    state = MagicMock()
    state.attributes = {"op": "Heating"}
    c.hass.states.get = MagicMock(return_value=state)

    def fail_resolve(*a, **kw):
        raise AssertionError("resolve_attrs must not be called")

    monkeypatch.setattr(f"{_COORD_MOD}.resolve_attrs", fail_resolve)
    monkeypatch.setattr(
        f"{_COORD_MOD}.read", lambda *a, **kw: _full_attrs()
    )
    monkeypatch.setattr(f"{_COORD_MOD}.missing_required", lambda a: [])
    c._tick_energy = MagicMock(side_effect=_Reached())
    with pytest.raises(_Reached):
        await c._async_update_data()
    c.detector.update.assert_called_once()


@pytest.mark.asyncio
async def test_auto_falls_back_to_individual(monkeypatch) -> None:
    """RED: auto with no monolithic -> use resolver on individual entities."""
    c = _bare(source_type=SOURCE_TYPE_AUTO)
    c.hass.states.get = MagicMock(return_value=None)  # no monolithic

    calls: list[str] = []

    def fake_resolve(hass, prefix=DEFAULT_INDIVIDUAL_PREFIX, custom_map=None):
        calls.append(prefix)
        return _resolve_result(_full_attrs())

    monkeypatch.setattr(f"{_COORD_MOD}.resolve_attrs", fake_resolve)
    c._tick_energy = MagicMock(side_effect=_Reached())
    with pytest.raises(_Reached):
        await c._async_update_data()
    assert calls  # RED: currently empty


# ---------- monolithic regressions (must stay green) ----------


@pytest.mark.asyncio
async def test_monolithic_partial_missing_still_freezes(monkeypatch) -> None:
    """Regression: #109 partial-missing freeze unchanged for monolithic."""
    c = _bare(source_type=SOURCE_TYPE_MONOLITHIC)
    state = MagicMock()
    state.attributes = {"op": "Heating"}
    c.hass.states.get = MagicMock(return_value=state)
    monkeypatch.setattr(
        f"{_COORD_MOD}.read",
        lambda *a, **kw: {ATTR_OPERATION_MODE: "Heating"},
    )
    monkeypatch.setattr(
        f"{_COORD_MOD}.missing_required", lambda a: [ATTR_FLOW_SENSOR]
    )
    c._tick_buh_and_defrost = MagicMock(side_effect=_Reached())
    with pytest.raises(_Reached):
        await c._async_update_data()
    c.detector.update.assert_not_called()  # frozen


@pytest.mark.asyncio
async def test_monolithic_missing_source_returns_early(monkeypatch) -> None:
    """Regression: no monolithic entity -> early return, no tick, no detect."""
    c = _bare(source_type=SOURCE_TYPE_MONOLITHIC)
    c.hass.states.get = MagicMock(return_value=None)
    await c._async_update_data()
    c.detector.update.assert_not_called()
    c._tick_buh_and_defrost.assert_not_called()
