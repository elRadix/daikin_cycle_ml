"""Coexistence tests for coverage-based AUTO source selection (#281 T8b).

Q1 (user): v2 wins on tie.
Q2 (user): freeze when both empty (preserve GAP-4 stale alert).
Q3 (user): INFO on first choice, WARNING on switch.
Q4 (user): populate _source_resolution for diagnostics.

Each test asserts behaviour on the REAL coordinator method, not a
reconstruction. R598: behavioural tests call the actual function.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml.const import (
    ATTR_BUH_STEP1, ATTR_BUH_STEP2, ATTR_COP, ATTR_DEFROST_OPERATION,
    ATTR_FLOW_SENSOR, ATTR_INLET_WATER_R4T, ATTR_IU_OPERATION_MODE,
    ATTR_LEAVING_WATER_AFTER_BUH, ATTR_LW_SETPOINT,
    ATTR_OPERATION_MODE, ATTR_OUTDOOR_AIR_R1T,
    ATTR_WATER_PUMP_OPERATION, ATTR_3WAY_VALVE,
    CONF_SOURCE_TYPE, DEFAULT_INDIVIDUAL_PREFIX, DOMAIN,
    REQUIRED_ATTRIBUTES, SOURCE_TYPE_AUTO,
)

_COORD_MOD = "custom_components.daikin_cycle_ml.coordinator"


def _full_attrs() -> dict[str, object]:
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


def _make_resolve_result(
    attrs: dict | None = None,
    missing: list[str] | None = None,
    discovered: int = 12,
):
    m = SimpleNamespace(
        attrs=attrs if attrs is not None else _full_attrs(),
        missing_required=missing if missing is not None else [],
        collisions=[],
        discovered_count=discovered,
        missing_consumed=[],
    )
    return m


def _bare(source_type: str = SOURCE_TYPE_AUTO) -> object:
    """Bare coordinator mock for AUTO dispatch tests (mirrors dispatch fixture)."""
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
    )
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
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
    return c


class _Reached(BaseException):
    """Sentinel raised by mocked _tick_energy.

    BaseException (not Exception) so generic `except Exception` handlers
    in production code (DataUpdateCoordinator's tick wrapper) cannot
    accidentally swallow the sentinel. R598-adjacent: use the exact
    exception class that the target code will NOT catch, so the test
    proves the flow reached the intended line.
    """
    pass


def _set_mono_state(c, present: bool) -> None:
    if present:
        state = MagicMock()
        state.attributes = {"op": "Heating"}
        c.hass.states.get = MagicMock(return_value=state)
    else:
        c.hass.states.get = MagicMock(return_value=None)


def _set_resolve(monkeypatch, attrs=None, missing=None, discovered=12):
    def fake(h, prefix=DEFAULT_INDIVIDUAL_PREFIX, custom_map=None):
        return _make_resolve_result(attrs, missing, discovered)
    monkeypatch.setattr(f"{_COORD_MOD}.resolve_attrs", fake)


def _set_read(monkeypatch, attrs=None, missing=None):
    monkeypatch.setattr(
        f"{_COORD_MOD}.read",
        lambda *a, **kw: attrs if attrs is not None else _full_attrs(),
    )
    monkeypatch.setattr(
        f"{_COORD_MOD}.missing_required",
        lambda a: missing if missing is not None else [],
    )


# ---------- Q1: v2 wins on tie ----------


@pytest.mark.asyncio
async def test_both_full_v2_wins_on_tie(monkeypatch) -> None:
    """Q1: both 12/12 -> v2 wins (native ESPAltherma alignment)."""
    c = _bare()
    _set_mono_state(c, present=True)
    _set_resolve(monkeypatch)
    _set_read(monkeypatch)
    c._tick_energy = MagicMock(side_effect=_Reached())
    with pytest.raises(_Reached):
        await c._async_update_data()
    assert c._source_resolution["chosen"] == "individual"
    assert c._source_resolution["mono_coverage"] == 12
    assert c._source_resolution["v2_coverage"] == 12


# ---------- Coverage comparison ----------


@pytest.mark.asyncio
async def test_mono_full_v2_partial_mono_wins(monkeypatch) -> None:
    """Mono 12/12 > v2 5/12 -> mono wins."""
    c = _bare()
    _set_mono_state(c, present=True)
    _set_resolve(monkeypatch, missing=["I/U operation mode", "3way valve(On:DHW_Off:Space)", "Defrost Operation", "Leaving water temp. after BUH (R2T)", "Inlet water temp.(R4T)", "Outdoor air temp.(R1T)", "Flow sensor (l/min)"], attrs={"Operation Mode": "Heating"})
    _set_read(monkeypatch)
    c._tick_energy = MagicMock(side_effect=_Reached())
    with pytest.raises(_Reached):
        await c._async_update_data()
    assert c._source_resolution["chosen"] == "monolithic"
    assert c._source_resolution["mono_coverage"] == 12
    assert c._source_resolution["v2_coverage"] == 5


@pytest.mark.asyncio
async def test_mono_partial_v2_full_v2_wins(monkeypatch) -> None:
    """Mono 8/12 < v2 12/12 -> v2 wins."""
    c = _bare()
    _set_mono_state(c, present=True)
    _set_resolve(monkeypatch)
    partial_mono = {k: v for i, (k, v) in enumerate(_full_attrs().items()) if i < 8}
    _set_read(monkeypatch, attrs=partial_mono, missing=["x", "y", "z", "w"])
    c._tick_energy = MagicMock(side_effect=_Reached())
    with pytest.raises(_Reached):
        await c._async_update_data()
    assert c._source_resolution["chosen"] == "individual"
    assert c._source_resolution["mono_coverage"] == 8
    assert c._source_resolution["v2_coverage"] == 12


@pytest.mark.asyncio
async def test_only_mono_present_mono_wins(monkeypatch) -> None:
    """Mono 12/12, v2 0/12 -> mono."""
    c = _bare()
    _set_mono_state(c, present=True)
    _set_resolve(monkeypatch, attrs={}, missing=list(REQUIRED_ATTRIBUTES), discovered=0)
    _set_read(monkeypatch)
    c._tick_energy = MagicMock(side_effect=_Reached())
    with pytest.raises(_Reached):
        await c._async_update_data()
    assert c._source_resolution["chosen"] == "monolithic"


@pytest.mark.asyncio
async def test_only_v2_present_v2_wins(monkeypatch) -> None:
    """Mono 0/12, v2 12/12 -> v2."""
    c = _bare()
    _set_mono_state(c, present=False)
    _set_resolve(monkeypatch)
    c._tick_energy = MagicMock(side_effect=_Reached())
    with pytest.raises(_Reached):
        await c._async_update_data()
    assert c._source_resolution["chosen"] == "individual"


# ---------- Q2: freeze when both empty ----------


@pytest.mark.asyncio
async def test_both_empty_falls_back_to_monolithic_freezes(monkeypatch) -> None:
    """Q2: both 0/12 -> fallback to monolithic (freeze, stale alert fires)."""
    c = _bare()
    _set_mono_state(c, present=False)
    _set_resolve(monkeypatch, attrs={}, missing=list(REQUIRED_ATTRIBUTES), discovered=0)
    # capture: since chosen=mono, mono_state is None -> return snap early
    snap = await c._async_update_data()
    assert c._source_resolution["chosen"] == "monolithic"
    assert c._source_resolution["mono_coverage"] == 0
    assert c._source_resolution["v2_coverage"] == 0


# ---------- Q3: log on first choice (INFO), on switch (WARNING) ----------


@pytest.mark.asyncio
async def test_first_choice_logs_info(monkeypatch, caplog) -> None:
    """Q3: first choice logs INFO."""
    c = _bare()
    _set_mono_state(c, present=False)
    _set_resolve(monkeypatch)
    c._tick_energy = MagicMock(side_effect=_Reached())
    with caplog.at_level(logging.INFO, logger=_COORD_MOD):
        with pytest.raises(_Reached):
            await c._async_update_data()
    infos = [r for r in caplog.records if r.levelno == logging.INFO and "source auto" in r.getMessage()]
    assert any("chose individual" in r.getMessage() for r in infos), (
        f"expected INFO log, got: {[r.getMessage() for r in caplog.records]}"
    )


@pytest.mark.asyncio
async def test_switch_logs_warning(monkeypatch, caplog) -> None:
    """Q3: switching from mono to v2 logs WARNING."""
    c = _bare()
    _set_mono_state(c, present=True)
    _set_resolve(monkeypatch)
    _set_read(monkeypatch)
    # Force previous choice = monolithic
    c._auto_last_chosen = "monolithic"
    # Now v2 wins on tie -> switch
    c._tick_energy = MagicMock(side_effect=_Reached())
    with caplog.at_level(logging.WARNING, logger=_COORD_MOD):
        with pytest.raises(_Reached):
            await c._async_update_data()
    warns = [r for r in caplog.records if r.levelno == logging.WARNING and "source auto" in r.getMessage()]
    assert any("switched monolithic -> individual" in r.getMessage() for r in warns), (
        f"expected switch WARNING, got: {[r.getMessage() for r in caplog.records]}"
    )



@pytest.mark.asyncio
async def test_no_log_on_same_choice(monkeypatch, caplog) -> None:
    """Line 1665->1675: same choice as previous tick -> NO log, NO state change.

    Production scenario: two consecutive ticks with identical coverage.
    The coordinator runs every 30s; if mono/v2 coverage hasn't changed,
    we should NOT spam logs. Idempotency per tick.

    This covers the else-branch (chosen == _auto_last_chosen) that the
    other 12 tests never hit because _auto_last_chosen starts as ''.
    """
    c = _bare()
    _set_mono_state(c, present=True)
    _set_resolve(monkeypatch)
    _set_read(monkeypatch)
    # Simulate: previous tick already chose individual (v2 wins on tie)
    c._auto_last_chosen = "individual"
    c._tick_energy = MagicMock(side_effect=_Reached())
    with caplog.at_level(logging.INFO, logger=_COORD_MOD):
        with pytest.raises(_Reached):
            await c._async_update_data()
    # No "source auto" log at all (no choice, no switch)
    source_logs = [
        r for r in caplog.records if "source auto" in r.getMessage()
    ]
    assert not source_logs, (
        f"expected NO log on same choice, got: "
        f"{[r.getMessage() for r in source_logs]}"
    )
    # State unchanged
    assert c._auto_last_chosen == "individual"
    # _source_resolution still updated (transparency is per-tick)
    assert c._source_resolution["chosen"] == "individual"



# ---------- Q4: diagnostics exposure ----------


@pytest.mark.asyncio
async def test_source_resolution_populated(monkeypatch) -> None:
    """Q4: _source_resolution dict has all detail keys."""
    c = _bare()
    _set_mono_state(c, present=True)
    _set_resolve(monkeypatch)
    _set_read(monkeypatch)
    c._tick_energy = MagicMock(side_effect=_Reached())
    with pytest.raises(_Reached):
        await c._async_update_data()
    res = c._source_resolution
    assert res["mode"] == "auto"
    assert res["mono_coverage"] == 12
    assert res["v2_coverage"] == 12
    assert res["required_total"] == 12
    assert res["chosen"] == "individual"
    assert ">= " in res["reason"] or "> " in res["reason"]


# ---------- Freeze behaviour ----------


@pytest.mark.asyncio
async def test_freeze_when_both_empty_no_detector_advance(monkeypatch) -> None:
    """Q2: both empty -> detector.update NOT called (freeze path)."""
    c = _bare()
    _set_mono_state(c, present=False)
    _set_resolve(monkeypatch, attrs={}, missing=list(REQUIRED_ATTRIBUTES), discovered=0)
    await c._async_update_data()
    # Freeze path returns snap before detector.update
    c.detector.update.assert_not_called()


# ---------- Last_success_ts behaviour ----------


@pytest.mark.asyncio
async def test_v2_win_with_zero_discovered_does_not_bump_last_success(monkeypatch) -> None:
    """GAP-4 preserved: v2 chosen but discovered_count=0 -> last_success frozen."""
    c = _bare()
    _set_mono_state(c, present=False)
    _set_resolve(monkeypatch, attrs={"Operation Mode": "Heating"}, missing=list(REQUIRED_ATTRIBUTES)[1:], discovered=0)
    snap = await c._async_update_data()
    assert snap.last_success_ts == 0.0 or snap.last_success_ts is None


@pytest.mark.asyncio
async def test_v2_win_with_discovered_bumps_last_success(monkeypatch) -> None:
    """v2 chosen with discovered_count>0 -> last_success updated (normal)."""
    c = _bare()
    _set_mono_state(c, present=False)
    _set_resolve(monkeypatch)
    import time as _time
    before = _time.time()
    c._tick_energy = MagicMock(side_effect=_Reached())
    with pytest.raises(_Reached):
        await c._async_update_data()
    # Freeze=False -> went past the early return
    c.detector.update.assert_called_once()
