"""RED tests for full native ESPAltherma v2 support (issue #281).

Covers 6 gaps + co-existence + wizard UX:

GAP-1: auto mode hard-loops when no monolithic (KeyError source_sensor)
GAP-2: individual gets BOTH missing_attrs + espaltherma_v2_missing_attrs
GAP-3: _normalize("inf") leaks float('inf') into DB / COP math
GAP-4: source_stale never fires in individual (last_success_ts always set)
GAP-5: entry title shows "... ()" in individual mode
GAP-6: reconfigure / options cannot change source_type
GAP-7 (new): wizard shows no discovery info (user can't tell what exists)

R634: fails on current code if gaps are real. Regression guards included.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.daikin_cycle_ml import repairs
from custom_components.daikin_cycle_ml.config_flow import (
    DaikinCycleMLConfigFlow,
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
    SOURCE_TYPE_AUTO,
    SOURCE_TYPE_INDIVIDUAL,
)
from custom_components.daikin_cycle_ml.engine.attribute_reader import _normalize
from custom_components.daikin_cycle_ml.engine.espaltherma_v2.slug import (
    make_json_key,
)

# ---------- fixtures ----------


def _full_attrs_str() -> dict[str, str]:
    return {
        ATTR_OPERATION_MODE: "Heating",
        ATTR_IU_OPERATION_MODE: "Heating",
        ATTR_3WAY_VALVE: "Off:Space",
        ATTR_DEFROST_OPERATION: "OFF",
        ATTR_LEAVING_WATER_AFTER_BUH: "35.0",
        ATTR_INLET_WATER_R4T: "30.0",
        ATTR_OUTDOOR_AIR_R1T: "8.5",
        ATTR_FLOW_SENSOR: "15.2",
        ATTR_WATER_PUMP_OPERATION: "ON",
        ATTR_BUH_STEP1: "OFF",
        ATTR_BUH_STEP2: "OFF",
        ATTR_LW_SETPOINT: "40.0",
    }


def _v2_states(n_missing: int = 0) -> list[MagicMock]:
    payload = _full_attrs_str()
    keys = list(payload.keys())
    missing = set(keys[-n_missing:]) if n_missing else set()
    out = []
    for label, val in payload.items():
        if label in missing:
            continue
        s = MagicMock()
        s.entity_id = f"{DEFAULT_INDIVIDUAL_PREFIX}{make_json_key(label)}"
        s.state = val
        out.append(s)
    return out


def _hass_v2_only(n_missing: int = 0) -> MagicMock:
    states = _v2_states(n_missing)
    hass = MagicMock()
    hass.states.async_all = MagicMock(
        side_effect=lambda d: states if d == "sensor" else []
    )
    hass.states.get = MagicMock(
        side_effect=lambda eid: next(
            (s for s in states if s.entity_id == eid), None
        )
    )
    return hass


def _hass_both() -> MagicMock:
    """Both a monolithic sensor and full v2 entities exist."""
    v2 = _v2_states(0)
    attrs = _full_attrs_str()
    mono = MagicMock()
    mono.entity_id = "sensor.althermasensors"
    mono.state = "on"
    mono.attributes = attrs
    all_states = [*v2, mono]

    def _all(domain):
        return [s for s in all_states if s.entity_id.startswith("sensor.")]

    def _get(eid):
        for s in all_states:
            if s.entity_id == eid:
                return s
        return None

    hass = MagicMock()
    hass.states.async_all = MagicMock(side_effect=_all)
    hass.states.get = MagicMock(side_effect=_get)
    return hass


def _flow(hass: MagicMock) -> DaikinCycleMLConfigFlow:
    flow = DaikinCycleMLConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._data = {}
    flow._options = {}
    flow._selected_family = None
    flow._selected_model = None
    flow._reconfigure_entry = None
    return flow


# ---------- GAP-1: auto with v2-only no longer crashes ----------


@pytest.mark.asyncio
async def test_gap1_auto_v2_only_does_not_require_source_sensor() -> None:
    """RED: current async_step_model does user_input['source_sensor'] unconditionally."""
    hass = _hass_v2_only(0)
    flow = _flow(hass)
    flow._data[CONF_SOURCE_TYPE] = SOURCE_TYPE_AUTO
    # Simulate what auto user does: submit model without source_sensor
    try:
        r = await flow.async_step_model(
            {"model": "epra12eav3", "attribute_mode": "auto"}
        )
    except KeyError as e:
        pytest.fail(f"GAP-1: auto crashed on missing source_sensor: {e!r}")
    # Must land on a form step, not crash
    assert r.get("type") == "form"


@pytest.mark.asyncio
async def test_gap1_user_step_offers_auto() -> None:
    """Wizard user-step must expose auto + a clear preview of what's detected."""
    hass = _hass_v2_only(0)
    flow = _flow(hass)
    r = await flow.async_step_user()
    assert r["type"] == "form"
    # Placeholders should include discovery summary (#GAP-7)
    ph = r.get("description_placeholders") or {}
    assert "mono_found" in ph or "detected" in ph or "discovery" in str(ph), (
        f"wizard user-step must show discovery preview, got {sorted(ph.keys())}"
    )


# ---------- GAP-2: no duplicate repair ----------


def _snap(missing: list[str]) -> SimpleNamespace:
    return SimpleNamespace(missing_attrs=list(missing), last_success_ts=0.0)


def _coord(source_type: str = "individual") -> SimpleNamespace:
    return SimpleNamespace(
        source_type=source_type,
        individual_prefix="sensor.espaltherma_",
        _db_integrity_ok=True,
        _notify_fail_streak=0,
        _notify_fail_target="",
        _migration_error=None,
    )


@pytest.fixture
def fake_ir(monkeypatch):
    created: list[tuple[str, dict]] = []
    deleted: list[str] = []
    monkeypatch.setattr(
        repairs.ir,
        "async_create_issue",
        lambda h, d, iid, **kw: created.append((iid, dict(kw))),
    )
    monkeypatch.setattr(
        repairs.ir,
        "async_delete_issue",
        lambda h, d, iid: deleted.append(iid),
    )
    return SimpleNamespace(created=created, deleted=deleted)


def test_gap2_no_duplicate_repair_in_individual(fake_ir) -> None:
    """RED: both _check_missing_attrs AND _check_v2_missing_attrs fire."""
    hass = MagicMock()
    snap = _snap([ATTR_BUH_STEP1, ATTR_BUH_STEP2])
    coord = _coord("individual")
    asyncio.run(repairs.async_check_repairs(hass, "e1", snap, coordinator=coord))
    v2_issues = [
        i for i, _ in fake_ir.created
        if i.startswith("espaltherma_v2_missing_attrs")
    ]
    legacy_issues = [
        i for i, _ in fake_ir.created
        if i == "missing_attrs_e1"
    ]
    assert v2_issues, "v2 issue must fire"
    assert not legacy_issues, (
        f"GAP-2: legacy missing_attrs must be suppressed in individual mode, "
        f"got: {legacy_issues}"
    )


def test_gap2_monolithic_legacy_still_fires(fake_ir) -> None:
    """Regression: monolithic unchanged."""
    hass = MagicMock()
    snap = _snap([ATTR_OPERATION_MODE])
    coord = _coord("monolithic")
    asyncio.run(repairs.async_check_repairs(hass, "e1", snap, coordinator=coord))
    ids = [i for i, _ in fake_ir.created]
    assert "missing_attrs_e1" in ids
    assert not any(i.startswith("espaltherma_v2") for i in ids)


# ---------- GAP-3: inf/nan string filters ----------


@pytest.mark.parametrize("raw", ["inf", "INF", "Infinity", "-inf", "+inf"])
def test_gap3_normalize_rejects_inf(raw: str) -> None:
    """RED: current _normalize returns float('inf') for 'inf'."""
    assert _normalize(raw) is None, f"GAP-3: '{raw}' must normalize to None"


@pytest.mark.parametrize("raw", ["nan", "NaN", "NAN"])
def test_gap3_normalize_rejects_nan(raw: str) -> None:
    """Regression: nan already filtered."""
    assert _normalize(raw) is None


# ---------- GAP-4: source_stale in individual mode ----------


def _snap_tick(discovered: int, last_ok: float = 0.0) -> SimpleNamespace:
    return SimpleNamespace(
        missing_attrs=[],
        last_success_ts=last_ok,
        discovered_count=discovered,
    )


@pytest.mark.asyncio
async def test_gap4_source_stale_fires_when_zero_discovered(monkeypatch) -> None:
    """RED: individual with discovered_count=0 must be stale.

    Currently coordinator always sets last_success_ts = now in individual,
    so _is_source_stale never fires even with 0 discovered entities.
    """
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
    )
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.hass = MagicMock()
    c.entry = MagicMock()
    c.entry.data = {CONF_SOURCE_TYPE: SOURCE_TYPE_INDIVIDUAL}
    c.entry.options = {}
    c.source_type = SOURCE_TYPE_INDIVIDUAL
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

    empty_result = SimpleNamespace(
        attrs={}, missing_required=list(_full_attrs_str().keys()),
        collisions=[], discovered_count=0,
    )
    monkeypatch.setattr(
        "custom_components.daikin_cycle_ml.coordinator.resolve_attrs",
        lambda h, prefix=None: empty_result,
    )
    import time as _time
    _before = _time.time()
    snap = await c._async_update_data()
    # RED: current sets last_success_ts=now always; we need it NOT updated
    # when discovered_count == 0, so _is_source_stale sees stale.
    assert snap.last_success_ts < _before, (
        f"GAP-4: individual+0 discovered must NOT bump last_success_ts "
        f"(got {snap.last_success_ts}, before={_before})"
    )


@pytest.mark.asyncio
async def test_gap4_healthy_individual_bumps_last_success(monkeypatch) -> None:
    """Regression: healthy individual still updates last_success_ts."""
    # Reuse above but with full payload
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
    )
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.hass = MagicMock()
    c.entry = MagicMock()
    c.entry.data = {CONF_SOURCE_TYPE: SOURCE_TYPE_INDIVIDUAL}
    c.entry.options = {}
    c.source_type = SOURCE_TYPE_INDIVIDUAL
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

    from custom_components.daikin_cycle_ml.engine.attribute_reader import _normalize
    good_result = SimpleNamespace(
        attrs={k: _normalize(v) for k, v in _full_attrs_str().items()},
        missing_required=[],
        collisions=[],
        discovered_count=12,
    )
    monkeypatch.setattr(
        "custom_components.daikin_cycle_ml.coordinator.resolve_attrs",
        lambda h, prefix=None: good_result,
    )
    import time as _time
    before = _time.time()
    snap = await c._async_update_data()
    assert snap.last_success_ts >= before


# ---------- GAP-5: title in individual mode ----------


@pytest.mark.asyncio
async def test_gap5_title_shows_v2_in_individual() -> None:
    """RED: current title uses source_sensor which is '' in individual."""
    hass = _hass_v2_only(0)
    flow = _flow(hass)
    flow._data = {
        CONF_SOURCE_TYPE: SOURCE_TYPE_INDIVIDUAL,
        CONF_INDIVIDUAL_PREFIX: DEFAULT_INDIVIDUAL_PREFIX,
        "model": "epra12eav3",
        "source_sensor": "sensor.althermasensors",  # kept for legacy safety
    }
    result = await flow.async_step_finalize({})
    assert result["type"] == "create_entry"
    title = result["title"]
    assert "v2" in title.lower() or "individual" in title.lower(), (
        f"GAP-5: title must signal v2 mode, got {title!r}"
    )


# ---------- GAP-6: reconfigure / options can change source_type ----------


@pytest.mark.asyncio
async def test_gap6_reconfigure_basic_individual_branch() -> None:
    """RED: reconfigure_basic currently KeyError on missing source_sensor."""
    hass = _hass_v2_only(0)
    flow = _flow(hass)
    _entry = MagicMock()
    _entry.entry_id = "e1"
    _entry.data = {
        CONF_SOURCE_TYPE: SOURCE_TYPE_INDIVIDUAL,
        CONF_INDIVIDUAL_PREFIX: DEFAULT_INDIVIDUAL_PREFIX,
        "model": "epra12eav3",
    }
    flow._data = dict(_entry.data)
    # _get_reconfigure_entry reads HA context; mock it directly.
    flow._get_reconfigure_entry = MagicMock(return_value=_entry)
    try:
        r = await flow.async_step_reconfigure_basic(
            {"model": "epra12eav3"}  # no source_sensor
        )
    except KeyError as e:
        pytest.fail(f"GAP-6: reconfigure_basic crashed on missing source_sensor: {e!r}")
    # Should succeed (update and abort)
    assert r["type"] in ("abort", "form", "create_entry")


@pytest.mark.asyncio
async def test_gap6_options_device_has_source_type() -> None:
    """RED: OptionsFlow.device has no source_type / individual_prefix fields."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.daikin_cycle_ml.config_flow import (
        DaikinCycleMLOptionsFlow,
    )
    from custom_components.daikin_cycle_ml.const import DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_SOURCE_TYPE: SOURCE_TYPE_INDIVIDUAL,
            CONF_INDIVIDUAL_PREFIX: DEFAULT_INDIVIDUAL_PREFIX,
            "model": "epra12eav3",
            "source_sensor": "sensor.althermasensors",
        },
        options={},
        version=1,
    )
    flow = DaikinCycleMLOptionsFlow()
    flow.hass = MagicMock()
    flow.hass.config_entries.async_get_entry = MagicMock(return_value=entry)
    flow.hass.config_entries.async_update_entry = MagicMock()
    # HA OptionsFlow.config_entry is a read-only property that reads from
    # flow.handler (an entry_id string) in modern HA versions. Set both
    # so config_entry resolves without ValueError.
    flow.handler = entry.entry_id
    flow.context = {"entry_id": entry.entry_id}
    r = await flow.async_step_device()
    assert r["type"] == "form"
    # Extract all keys from section-schemas
    keys = set()
    for k, v in r["data_schema"].schema.items():
        # Section markers contain nested schemas
        if hasattr(v, "schema") and isinstance(getattr(v, "schema", None), dict):
            for inner in v.schema.keys():
                name = getattr(inner, "schema", inner)
                keys.add(str(name))
        keys.add(str(getattr(k, "schema", k)))
    assert "source_type" in keys, (
        f"GAP-6: options device step must expose source_type, got keys: {sorted(keys)}"
    )


# ---------- Co-existence: coverage-based auto ----------


@pytest.mark.asyncio
async def test_coexistence_auto_picks_individual_when_both_full(
    monkeypatch,
) -> None:
    """Both present + both full -> prefer individual (v2 wins on tie, #281)."""
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
    )
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.hass = _hass_both()
    c.entry = MagicMock()
    c.entry.data = {CONF_SOURCE_TYPE: SOURCE_TYPE_AUTO}
    c.entry.options = {}
    c.source_type = SOURCE_TYPE_AUTO
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

    resolve_calls: list[str] = []

    def _fake_resolve(h, prefix=DEFAULT_INDIVIDUAL_PREFIX):
        resolve_calls.append(prefix)
        from custom_components.daikin_cycle_ml.engine.attribute_reader import _normalize
        return SimpleNamespace(
            attrs={k: _normalize(v) for k, v in _full_attrs_str().items()},
            missing_required=[], collisions=[], discovered_count=12,
        )

    monkeypatch.setattr(
        "custom_components.daikin_cycle_ml.coordinator.resolve_attrs",
        _fake_resolve,
    )
    await c._async_update_data()
    # v2 wins on tie per #281 decision -> resolver MUST be called
    assert resolve_calls, (
        "co-existence: auto with both full must prefer individual (v2 wins on tie), "
        f"resolve_attrs called {len(resolve_calls)}x"
    )

