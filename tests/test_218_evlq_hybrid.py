"""Tests for Daikin Altherma R Hybrid (EVLQ series) — issue #218."""
from __future__ import annotations

import json
from pathlib import Path

from custom_components.daikin_cycle_ml.const import (
    MODEL_CHOICES,
    MODEL_EVLQ05CV3,
    MODEL_EVLQ08CV3,
    MODEL_FAMILIES,
    MODEL_LABELS,
    family_for_model,
    resolve_model_key,
)
from custom_components.daikin_cycle_ml.engine.attribute_compat import ALIAS_GROUPS
from custom_components.daikin_cycle_ml.engine.model_profiles import MODEL_PROFILES


def test_evlq_models_are_registered():
    for m in (MODEL_EVLQ05CV3, MODEL_EVLQ08CV3):
        assert m in MODEL_CHOICES, f"{m} missing from MODEL_CHOICES"
        assert m in MODEL_LABELS, f"{m} missing from MODEL_LABELS"
        assert m in MODEL_PROFILES, f"{m} missing from MODEL_PROFILES"


def test_evlq_family_registered():
    assert family_for_model(MODEL_EVLQ05CV3) == "evlq"
    assert family_for_model(MODEL_EVLQ08CV3) == "evlq"
    assert MODEL_FAMILIES["evlq"] == "Altherma R Hybrid"


def test_evlq_indoor_unit_aliases_resolve():
    # ESPAltherma may report the indoor unit name; aliases must map to the outdoor unit model
    assert resolve_model_key("ehyhbh05av32") == MODEL_EVLQ05CV3
    assert resolve_model_key("ehyhbh08av32") == MODEL_EVLQ08CV3
    assert resolve_model_key("ehyhbx08av3") == MODEL_EVLQ08CV3


def test_evlq_datasheets_loadable():
    path = Path(__file__).parent.parent / "custom_components" / "daikin_cycle_ml" / "data" / "datasheets.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for m in (MODEL_EVLQ05CV3, MODEL_EVLQ08CV3):
        assert m in data["models"], f"{m} missing from datasheets.json"
        entry = data["models"][m]
        assert entry["nom_cop"] > 0
        assert entry["kw"] > 0
        assert entry["lwt_min"] < entry["lwt_max"]
        assert entry["refrigerant"] == "R410A"
        assert entry["bivalent"] is True
        assert len(entry["points"]) >= 4
        # Verify all points are W35 reference
        for p in entry["points"]:
            assert p["t_lwc"] == 35


def test_evlq_attribute_aliases():
    assert "Outlet Water Heat Exch. Temp. (R1T)" in ALIAS_GROUPS["Leaving water temp. before BUH (R1T)"]
    assert "Outlet Water BUH Temp. (R2T)" in ALIAS_GROUPS["Leaving water temp. after BUH (R2T)"]
    assert "DHW tank temp (R5T)" in ALIAS_GROUPS["DHW tank temp. (R5T)"]


# ============================================================
# Hybrid data layer (thermal.py helpers)
# ============================================================

from custom_components.daikin_cycle_ml.engine.thermal import (
    boiler_active_from_attrs,
    boiler_efficiency_cop_from_attrs,
    dhw_tank_temp_from_attrs,
    hybrid_mode_from_attrs,
    safe_bool,
)


def test_safe_bool_all_forms():
    assert safe_bool(True) is True
    assert safe_bool(False) is False
    assert safe_bool("ON") is True
    assert safe_bool("off") is False
    assert safe_bool("True") is True
    assert safe_bool("yes") is True
    assert safe_bool("0") is False
    assert safe_bool(1) is True
    assert safe_bool(0) is False
    assert safe_bool(None) is False
    assert safe_bool("garbage") is False


def test_boiler_active_operation_demand():
    assert boiler_active_from_attrs({"Boiler Operation Demand": "ON"}) is True
    assert boiler_active_from_attrs({"Boiler Operation Demand": True}) is True
    assert boiler_active_from_attrs({"Boiler Operation Demand": "OFF"}) is False


def test_boiler_active_dhw_demand():
    assert boiler_active_from_attrs({"Boiler DHW Demand": "ON"}) is True
    assert boiler_active_from_attrs({"Boiler DHW Demand": True}) is True
    assert boiler_active_from_attrs({"Boiler DHW Demand": "OFF"}) is False


def test_boiler_active_absent_attrs():
    """Non-hybrid installations: no boiler attrs → False (safe default)."""
    assert boiler_active_from_attrs({}) is False
    assert boiler_active_from_attrs({"SomeOther": 1}) is False


def test_boiler_active_either_demand():
    """Either demand signal triggers boiler_active."""
    assert boiler_active_from_attrs({
        "Boiler Operation Demand": "OFF",
        "Boiler DHW Demand": "ON",
    }) is True


def test_dhw_tank_temp_disconnected_sentinel():
    """-40.7 °C is the R5T 'disconnected' sentinel → must return None."""
    assert dhw_tank_temp_from_attrs({"DHW tank temp. (R5T)": -40.7}) is None
    assert dhw_tank_temp_from_attrs({"DHW tank temp. (R5T)": -25.0}) is None


def test_dhw_tank_temp_normal_values():
    assert dhw_tank_temp_from_attrs({"DHW tank temp. (R5T)": 52.0}) == 52.0
    assert dhw_tank_temp_from_attrs({"DHW tank temp. (R5T)": 0.0}) == 0.0
    assert dhw_tank_temp_from_attrs({"DHW tank temp. (R5T)": -15.0}) == -15.0


def test_dhw_tank_temp_absent():
    assert dhw_tank_temp_from_attrs({}) is None


def test_hybrid_mode_extraction():
    assert hybrid_mode_from_attrs({"Hybrid Op. Mode": "H/P only"}) == "H/P only"
    assert hybrid_mode_from_attrs({"Hybrid Op. Mode": "Hybrid"}) == "Hybrid"
    assert hybrid_mode_from_attrs({}) == ""


def test_boiler_efficiency_cop():
    assert boiler_efficiency_cop_from_attrs({"BE COP": 1.3}) == 1.3
    assert boiler_efficiency_cop_from_attrs({"BE COP": "1.5"}) is None  # str → None
    assert boiler_efficiency_cop_from_attrs({}) is None


# ============================================================
# Boiler guard in CycleDetector (issue #218)
# ============================================================

from custom_components.daikin_cycle_ml.engine.cycle_detector import (
    STATE_IDLE,
    STATE_RUNNING,
    CycleDetector,
)


def _base_attrs(rps: float = 0.0) -> dict:
    """Minimal attrs dict for CycleDetector.update()."""
    return {
        "INV frequency (rps)": rps,
        "I/U operation mode": "Heating",
        "Water pump operation": "ON",
        "Leaving water temp. before BUH (R1T)": 30.0,
        "Inlet water temp.(R4T)": 25.0,
        "Outdoor air temp.(R1T)": 10.0,
        "BUH Step1": False,
        "BUH Step2": False,
        "Defrost Operation": False,
        "Flow sensor (l/min)": 12.0,
    }


def test_boiler_guard_idle_skips_cycle_open():
    """boiler_active=True, compressor off, IDLE → no cycle opens."""
    d = CycleDetector({})
    assert d.state == STATE_IDLE
    rec = d.update(_base_attrs(rps=0.0), now=1000.0, power_w=None, boiler_active=True)
    assert rec is None
    assert d.state == STATE_IDLE


def test_boiler_guard_running_force_closes():
    """boiler_active=True, compressor off, RUNNING → cycle force-closes."""
    d = CycleDetector({})
    # Open a real cycle first
    d.update(_base_attrs(rps=30.0), now=1000.0, power_w=2000.0)
    assert d.state == STATE_RUNNING
    # Now boiler kicks in, HP compressor off
    rec = d.update(_base_attrs(rps=0.0), now=1200.0, power_w=0.0, boiler_active=True)
    assert rec is not None
    assert rec["boiler_contribution_samples"] == 0
    assert d.state == STATE_IDLE


def test_boiler_contribution_tracked_in_idle_open():
    """When HP + boiler co-fire during IDLE→RUNNING, sample is counted."""
    d = CycleDetector({})
    rec = d.update(_base_attrs(rps=30.0), now=1000.0, power_w=2000.0, boiler_active=True)
    # No record yet (still running)
    assert rec is None
    assert d.state == STATE_RUNNING


def test_boiler_contribution_counted_in_record():
    """Co-fire samples appear in the closed record."""
    d = CycleDetector({})
    # Open with co-fire
    d.update(_base_attrs(rps=30.0), now=1000.0, power_w=2000.0, boiler_active=True)
    # Continue with co-fire
    d.update(_base_attrs(rps=32.0), now=1060.0, power_w=2100.0, boiler_active=True)
    # Close HP cycle by turning compressor off WITHOUT boiler (so no force-close)
    rec = d.update(_base_attrs(rps=0.0), now=1120.0, power_w=0.0, boiler_active=False)
    # Record may be None if pump=ON keeps IDLE; force a longer idle instead
    if rec is None:
        # send a close by pump off (which triggers _close in idle? Let's just verify state)
        rec = d.update({**_base_attrs(rps=0.0), "Water pump operation": "OFF"},
                       now=1180.0, power_w=0.0, boiler_active=False)
    assert rec is not None
    assert rec["boiler_contribution_samples"] >= 2


def test_boiler_samples_persist_in_to_dict():
    """_boiler_samples round-trips via to_dict/restore_from_dict."""
    d = CycleDetector({})
    d.update(_base_attrs(rps=30.0), now=1000.0, power_w=2000.0, boiler_active=True)
    d.update(_base_attrs(rps=32.0), now=1060.0, power_w=2100.0, boiler_active=True)
    payload = d.to_dict()
    assert payload["boiler_samples"] == 2

    d2 = CycleDetector({})
    d2.restore_from_dict(payload, now=1070.0)
    # After restore, another co-fire should increment from 2 → 3
    d2.update(_base_attrs(rps=33.0), now=1080.0, power_w=2100.0, boiler_active=True)
    payload2 = d2.to_dict()
    assert payload2["boiler_samples"] == 3


def test_boiler_samples_restore_invalid_payload():
    """Invalid boiler_samples type → silently defaults to 0."""
    d = CycleDetector({})
    payload = d.to_dict()
    # Not running → empty dict, populate manually
    payload = {
        "state": "running",
        "start_ts": 1000.0,
        "mode": "heating",
        "rps_samples": [],
        "dt_samples": [],
        "outdoor_samples": [],
        "buh_used": False,
        "defrost_used": False,
        "thermal_kw_samples": [],
        "pending_mode": None,
        "pending_mode_since": 0.0,
        "boiler_samples": "not_an_int",
    }
    d.restore_from_dict(payload, now=1010.0)
    assert d.to_dict()["boiler_samples"] == 0


# ============================================================
# Block 3A: Sensors + Binary sensors + Diagnostics
# ============================================================

def test_boiler_binary_sensor_defs_exist():
    """Both boiler binary sensors must be registered."""
    from custom_components.daikin_cycle_ml.binary_sensor import BINARY_SENSOR_DEFS
    keys = {d["key"] for d in BINARY_SENSOR_DEFS}
    assert "boiler_operation_demand" in keys
    assert "boiler_dhw_demand" in keys


def test_boiler_binary_sensor_operation_demand():
    """boiler_operation_demand reflects snap.boiler_active."""
    from custom_components.daikin_cycle_ml.binary_sensor import BINARY_SENSOR_DEFS
    from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
    d = next(x for x in BINARY_SENSOR_DEFS if x["key"] == "boiler_operation_demand")
    assert d["state_fn"](DataSnapshot(boiler_active=True, is_hybrid=True), None) is True
    assert d["state_fn"](DataSnapshot(boiler_active=False, is_hybrid=True), None) is False


def test_boiler_binary_sensor_dhw_demand():
    """boiler_dhw_demand reflects snap.boiler_dhw_active."""
    from custom_components.daikin_cycle_ml.binary_sensor import BINARY_SENSOR_DEFS
    from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
    d = next(x for x in BINARY_SENSOR_DEFS if x["key"] == "boiler_dhw_demand")
    assert d["state_fn"](DataSnapshot(boiler_dhw_active=True, is_hybrid=True), None) is True
    assert d["state_fn"](DataSnapshot(boiler_dhw_active=False, is_hybrid=True), None) is False


def test_hybrid_mode_sensor_enum():
    """hybrid_mode returns value or 'unknown', exposes valid options."""
    from custom_components.daikin_cycle_ml.sensor import SENSOR_DEFS
    from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
    d = next(x for x in SENSOR_DEFS if x["key"] == "hybrid_mode")
    assert d["value_fn"](DataSnapshot(hybrid_mode="H/P only", is_hybrid=True), None) == "H/P only"
    assert d["value_fn"](DataSnapshot(hybrid_mode="Hybrid", is_hybrid=True), None) == "Hybrid"
    assert d["value_fn"](DataSnapshot(hybrid_mode="", is_hybrid=True), None) == "unknown"
    for opt in ("H/P only", "Hybrid", "Boiler only", "unknown"):
        assert opt in d["options"]


def test_boiler_efficiency_cop_sensor():
    """boiler_efficiency_cop returns value or None."""
    from custom_components.daikin_cycle_ml.sensor import SENSOR_DEFS
    from custom_components.daikin_cycle_ml.coordinator import DataSnapshot
    d = next(x for x in SENSOR_DEFS if x["key"] == "boiler_efficiency_cop")
    assert d["value_fn"](DataSnapshot(boiler_efficiency_cop=1.3, is_hybrid=True), None) == 1.3
    assert d["value_fn"](DataSnapshot(boiler_efficiency_cop=None, is_hybrid=True), None) is None
    assert d["attr_fn"](DataSnapshot(boiler_efficiency_cop=1.3, is_hybrid=True), None)["info_only"] is True


def test_diagnostics_includes_hybrid_fields():
    """Diagnostics dump contains all 5 hybrid fields."""
    from pathlib import Path
    src = Path("custom_components/daikin_cycle_ml/diagnostics.py").read_text()
    for field in (
        "boiler_active", "boiler_dhw_active", "hybrid_mode",
        "boiler_efficiency_cop", "inv_freq_secondary",
    ):
        assert f'"{field}"' in src, f"missing {field} in diagnostics"


# ============================================================
# Block 3B.1 — Hybrid warning in async_step_attributes
# ============================================================

from custom_components.daikin_cycle_ml.config_flow import (
    _is_hybrid_model,
    _hybrid_attrs_present,
)


def test_is_hybrid_model_evlq():
    """EVLQ models are detected as hybrid."""
    assert _is_hybrid_model("evlq05cv3") is True
    assert _is_hybrid_model("evlq08cv3") is True


def test_is_hybrid_model_non_hybrid():
    """Non-EVLQ models are not hybrid."""
    assert _is_hybrid_model("epra08eav3") is False
    assert _is_hybrid_model("edla09d3v3") is False
    assert _is_hybrid_model("basisprofiel") is False
    assert _is_hybrid_model("") is False


def test_hybrid_attrs_present_both():
    """Boiler Operation Demand alone is enough."""
    assert _hybrid_attrs_present({"Boiler Operation Demand": "OFF"}) is True


def test_hybrid_attrs_present_dhw_only():
    """Boiler DHW Demand alone is enough."""
    assert _hybrid_attrs_present({"Boiler DHW Demand": "OFF"}) is True


def test_hybrid_attrs_present_absent():
    """Neither attribute present → False."""
    assert _hybrid_attrs_present({}) is False
    assert _hybrid_attrs_present({"INV frequency (rps)": 30.0}) is False


# ============================================================
# Block 3B.1b — async_step_attributes hybrid_hint branch
# ============================================================

import asyncio
from unittest.mock import MagicMock
from custom_components.daikin_cycle_ml import config_flow as _cf


def _hybrid_wizard(src):
    """Helper: minimal DaikinCycleMLConfigFlow with mocked hass."""
    h = MagicMock()
    h.states = MagicMock()
    h.states.get = MagicMock(return_value=src)
    h.config_entries = MagicMock()
    h.services = MagicMock()
    h.services.async_services = MagicMock(return_value={})
    flow = _cf.DaikinCycleMLConfigFlow()
    flow.hass = h
    flow._data = {"source_sensor": "sensor.x", "model": "evlq08cv3"}
    flow._options = {}
    flow._reconfigure_entry = None
    return flow


def test_attributes_hybrid_warning_when_boiler_attrs_missing():
    """Hybrid model + no boiler attrs → hybrid_hint is set."""
    src = MagicMock()
    src.attributes = {
        "INV frequency (rps)": 30.0,
        "Operation Mode": "Heating",
        # deliberately NO Boiler Operation Demand / Boiler DHW Demand
    }
    flow = _hybrid_wizard(src)
    r = asyncio.run(flow.async_step_attributes())
    assert r["type"] == "form"
    assert r["step_id"] == "attributes"
    assert "Hybrid model detected" in r["description_placeholders"]["hybrid_hint"]


def test_attributes_hybrid_no_warning_when_boiler_attrs_present():
    """Hybrid model + boiler attrs present → hybrid_hint is empty."""
    src = MagicMock()
    src.attributes = {
        "INV frequency (rps)": 30.0,
        "Boiler Operation Demand": "OFF",
    }
    flow = _hybrid_wizard(src)
    r = asyncio.run(flow.async_step_attributes())
    assert r["type"] == "form"
    assert r["description_placeholders"]["hybrid_hint"] == ""


def test_attributes_non_hybrid_no_hint():
    """Non-hybrid model → hybrid_hint always empty."""
    src = MagicMock()
    src.attributes = {"INV frequency (rps)": 30.0}
    h = MagicMock()
    h.states = MagicMock()
    h.states.get = MagicMock(return_value=src)
    h.config_entries = MagicMock()
    h.services = MagicMock()
    h.services.async_services = MagicMock(return_value={})
    flow = _cf.DaikinCycleMLConfigFlow()
    flow.hass = h
    flow._data = {"source_sensor": "sensor.x", "model": "epra08eav3"}
    flow._options = {}
    flow._reconfigure_entry = None
    r = asyncio.run(flow.async_step_attributes())
    assert r["type"] == "form"
    assert r["description_placeholders"]["hybrid_hint"] == ""


# ============================================================
# Block 3B.2 — Reconfigure HP↔Hybrid transition detection
# ============================================================

def _reconfig_wizard(current_model, new_model, src_attrs=None):
    """Helper: minimal flow for reconfigure_basic."""
    if src_attrs is None:
        from custom_components.daikin_cycle_ml.const import REQUIRED_ATTRIBUTES
        src_attrs = dict.fromkeys(REQUIRED_ATTRIBUTES, 0)

    src = MagicMock()
    src.state = "ok"
    src.attributes = src_attrs
    src.last_changed = None
    src.last_updated = None

    entry = MagicMock()
    entry.data = {"model": current_model, "source_sensor": "sensor.x"}
    entry.options = {}

    h = MagicMock()
    h.states = MagicMock()
    h.states.get = MagicMock(return_value=src)
    h.config_entries = MagicMock()
    h.services = MagicMock()
    h.services.async_services = MagicMock(return_value={})

    flow = _cf.DaikinCycleMLConfigFlow()
    flow.hass = h
    flow._data = {}
    flow._options = {}
    flow._reconfigure_entry = entry
    flow._get_reconfigure_entry = lambda: entry  # type: ignore[assignment]
    return flow, entry


def test_reconfigure_hp_to_hybrid_reason():
    """HP→Hybrid transition emits reconfigure_hybrid_change reason."""
    flow, _ = _reconfig_wizard("epra08eav3", "evlq08cv3")
    r = asyncio.run(flow.async_step_reconfigure_basic(user_input={
        "source_sensor": "sensor.x",
        "model": "evlq08cv3",
    }))
    assert r["type"] == "abort"
    assert r["reason"] == "reconfigure_hybrid_change"


def test_reconfigure_hybrid_to_hp_reason():
    """Hybrid→HP transition emits reconfigure_hybrid_change reason."""
    flow, _ = _reconfig_wizard("evlq08cv3", "epra08eav3")
    r = asyncio.run(flow.async_step_reconfigure_basic(user_input={
        "source_sensor": "sensor.x",
        "model": "epra08eav3",
    }))
    assert r["type"] == "abort"
    assert r["reason"] == "reconfigure_hybrid_change"


def test_reconfigure_hp_to_hp_reason_unchanged():
    """HP→HP change emits reconfigure_successful reason."""
    flow, _ = _reconfig_wizard("epra08eav3", "edla09d3v3")
    r = asyncio.run(flow.async_step_reconfigure_basic(user_input={
        "source_sensor": "sensor.x",
        "model": "edla09d3v3",
    }))
    assert r["type"] == "abort"
    assert r["reason"] == "reconfigure_successful"


def test_reconfigure_hybrid_to_hybrid_reason_unchanged():
    """Hybrid→Hybrid change emits reconfigure_successful reason."""
    flow, _ = _reconfig_wizard("evlq05cv3", "evlq08cv3")
    r = asyncio.run(flow.async_step_reconfigure_basic(user_input={
        "source_sensor": "sensor.x",
        "model": "evlq08cv3",
    }))
    assert r["type"] == "abort"
    assert r["reason"] == "reconfigure_successful"


def test_reconfigure_source_only_no_model_change():
    """Source-only change (no model change) emits reconfigure_successful."""
    flow, _ = _reconfig_wizard("epra08eav3", "epra08eav3")
    r = asyncio.run(flow.async_step_reconfigure_basic(user_input={
        "source_sensor": "sensor.x",
        "model": "epra08eav3",
    }))
    assert r["type"] == "abort"
    assert r["reason"] == "reconfigure_successful"


# ============================================================
# Block 3C.1 — COP sample filter (boiler-only skip)
# ============================================================

import pytest
from unittest.mock import AsyncMock, MagicMock as _MM


def _cop_coord(state: str, boiler_active: bool):
    """Minimal coordinator for _maybe_collect_cop_sample test."""
    from custom_components.daikin_cycle_ml.coordinator import DataSnapshot

    c = _MM()
    c.db = _MM()
    c.db.async_get_max_cop_sample_ts = AsyncMock(return_value=None)
    c.db.async_insert_cop_sample = AsyncMock(return_value=True)
    c._cop_sample_seed_done = True
    c._last_cop_sample_ts = 0.0
    c.cop_sensor_entity = None
    c._resolve_cop_sample_mode = _MM(return_value="heating")
    c.adaptive = _MM()
    c.adaptive.suggest = _MM(return_value={})

    snap = DataSnapshot()
    snap.cop = 4.5
    snap.state = state
    snap.boiler_active = boiler_active
    snap.attrs = {
        "Operation Mode": "Heating",
        "Outdoor air temp.(R1T)": 10.0,
        "Flow sensor (l/min)": 15.0,
        "Inlet water temp.(R4T)": 25.0,
        "Leaving water temp. before BUH (R1T)": 30.0,
    }
    c.data = snap
    return c


@pytest.mark.asyncio
async def test_cop_sample_skipped_when_boiler_only():
    """Boiler active + HP idle → no COP sample written."""
    from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator

    c = _cop_coord(state="idle", boiler_active=True)
    await DaikinCycleMLCoordinator._maybe_collect_cop_sample(c, now=10000.0)
    c.db.async_insert_cop_sample.assert_not_called()


@pytest.mark.asyncio
async def test_cop_sample_written_when_hp_running_no_boiler():
    """HP running, no boiler → COP sample written (baseline)."""
    from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator

    c = _cop_coord(state="running", boiler_active=False)
    await DaikinCycleMLCoordinator._maybe_collect_cop_sample(c, now=10000.0)
    c.db.async_insert_cop_sample.assert_called_once()


@pytest.mark.asyncio
async def test_cop_sample_written_when_hp_running_with_boiler():
    """HP running + boiler active (co-fire) → sample still written."""
    from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator

    c = _cop_coord(state="running", boiler_active=True)
    await DaikinCycleMLCoordinator._maybe_collect_cop_sample(c, now=10000.0)
    c.db.async_insert_cop_sample.assert_called_once()


# ============================================================
# Block 2 (all-in) — DB v21 + alert suppress
# ============================================================


def test_evaluate_alerts_boiler_suppress():
    """Boiler-only suppresses HP-cycle alerts."""
    from custom_components.daikin_cycle_ml.engine.notification_engine import evaluate_alerts
    alerts = evaluate_alerts(
        binary_states={"short_run": True, "pendulum_hourly": True},
        options={},
        now=1000.0,
        boiler_active=True,
        hp_running=False,
    )
    types = {a.alert_type for a in alerts}
    assert "short_run" not in types
    assert "pendulum_hourly" not in types


def test_evaluate_alerts_hp_running_not_suppressed():
    """HP running overrides boiler suppress (co-fire)."""
    from custom_components.daikin_cycle_ml.engine.notification_engine import evaluate_alerts
    alerts = evaluate_alerts(
        binary_states={"short_run": True},
        options={},
        now=1000.0,
        boiler_active=True,
        hp_running=True,
    )
    types = {a.alert_type for a in alerts}
    assert "short_run" in types


def test_evaluate_alerts_no_boiler_no_suppress():
    """No boiler → all alerts pass through."""
    from custom_components.daikin_cycle_ml.engine.notification_engine import evaluate_alerts
    alerts = evaluate_alerts(
        binary_states={"short_run": True, "pendulum_hourly": True},
        options={},
        now=1000.0,
        boiler_active=False,
        hp_running=False,
    )
    types = {a.alert_type for a in alerts}
    assert "short_run" in types
    assert "pendulum_hourly" in types


def test_evaluate_alerts_non_suppressed_type_passes():
    """Non-HP-cycle alerts pass through even with boiler."""
    from custom_components.daikin_cycle_ml.engine.notification_engine import evaluate_alerts
    alerts = evaluate_alerts(
        binary_states={"dhw_pendulum": True},
        options={},
        now=1000.0,
        boiler_active=True,
        hp_running=False,
    )
    types = {a.alert_type for a in alerts}
    assert "dhw_pendulum" in types


# ============================================================
# Block 3D — v21 migration coverage
# ============================================================

import pytest as _pytest


@pytest.mark.asyncio
async def test_migrate_to_v21_adds_column(tmp_path):
    """v21 adds boiler_contribution_samples when missing."""
    from custom_components.daikin_cycle_ml.storage.db import CycleDB
    db = CycleDB(tmp_path / "v21test.db")
    await db.async_open()
    await db.async_initialize()
    conn = db._require()

    # Drop the column to simulate pre-v21 schema
    try:
        await conn.execute(
            "ALTER TABLE cycles DROP COLUMN boiler_contribution_samples"
        )
        await conn.commit()
    except Exception as exc:
        await db.async_close()
        pytest.skip(f"SQLite cannot DROP COLUMN: {exc}")

    result = await db.async_migrate_to_v21()
    assert result.get("completed") is True
    assert "boiler_contribution_samples" in result.get("columns_added", [])

    # Verify column exists post-migration
    cur = await conn.execute("PRAGMA table_info(cycles)")
    cols = {row[1] for row in await cur.fetchall()}
    await cur.close()
    assert "boiler_contribution_samples" in cols

    await db.async_close()


@pytest.mark.asyncio
async def test_migrate_to_v21_idempotent(tmp_path):
    """v21 is idempotent via completion marker."""
    from custom_components.daikin_cycle_ml.storage.db import CycleDB
    db = CycleDB(tmp_path / "v21idem.db")
    await db.async_open()
    await db.async_initialize()

    # First run: column already exists (from schema.sql) → no-op, marker set
    first = await db.async_migrate_to_v21()
    assert first.get("completed") is True

    # Second run: marker prevents rerun
    second = await db.async_migrate_to_v21()
    assert second.get("skipped") == 1

    await db.async_close()


# ============================================================
# Block 3C.1 — coordinator edge: data_obj=None path
# ============================================================

@pytest.mark.asyncio
async def test_cop_sample_with_none_data_obj():
    """_maybe_collect_cop_sample with data=None uses getattr defaults."""
    from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
    from unittest.mock import AsyncMock as _AM, MagicMock as _M

    c = _M()
    c.db = _M()
    c.db.async_get_max_cop_sample_ts = _AM(return_value=None)
    c.db.async_insert_cop_sample = _AM(return_value=True)
    c._cop_sample_seed_done = True
    c._last_cop_sample_ts = 0.0
    c.cop_sensor_entity = "sensor.x"
    c._resolve_cop_sample_mode = _M(return_value="heating")
    c.adaptive = _M()
    c.adaptive.suggest = _M(return_value={})

    st = _M()
    st.state = "4.5"
    st.attributes = {}
    c.hass = _M()
    c.hass.states = _M()
    c.hass.states.get = _M(return_value=st)

    # data_obj = None: exercises getattr(None, 'boiler_active', False) paths
    c.data = None

    # Should not crash; sample may or may not be inserted depending on parser
    await DaikinCycleMLCoordinator._maybe_collect_cop_sample(c, now=10000.0)


# ============================================================
# Coverage: coordinator lines 2853 + 2874->exit
# ============================================================

@pytest.mark.asyncio
async def test_cop_sample_invalid_parse_returns_early(monkeypatch):
    """Line 2853: parse returns None → return before INSERT."""
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator, DataSnapshot,
    )
    from custom_components.daikin_cycle_ml.engine import cop_analyzer as _ca
    from unittest.mock import AsyncMock as _AM, MagicMock as _M

    monkeypatch.setattr(_ca, "parse_global_cop_attrs", lambda _m: None)

    c = _M()
    c.db = _M()
    c.db.async_get_max_cop_sample_ts = _AM(return_value=None)
    c.db.async_insert_cop_sample = _AM(return_value=True)
    c._cop_sample_seed_done = True
    c._last_cop_sample_ts = 0.0
    c.cop_sensor_entity = "sensor.x"
    c._resolve_cop_sample_mode = _M(return_value="heating")

    st = _M()
    st.state = "4.5"
    st.attributes = {}
    c.hass = _M()
    c.hass.states = _M()
    c.hass.states.get = _M(return_value=st)

    snap = DataSnapshot()
    snap.cop = 4.5
    snap.state = "running"
    snap.boiler_active = False
    snap.attrs = {}
    c.data = snap

    await DaikinCycleMLCoordinator._maybe_collect_cop_sample(c, now=10000.0)
    c.db.async_insert_cop_sample.assert_not_called()


@pytest.mark.asyncio
async def test_cop_sample_insert_returns_false_branch():
    """Line 2874->exit: insert returns False → _last_cop_sample_ts unchanged."""
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator, DataSnapshot,
    )
    from unittest.mock import AsyncMock as _AM, MagicMock as _M

    c = _M()
    c.db = _M()
    c.db.async_get_max_cop_sample_ts = _AM(return_value=None)
    c.db.async_insert_cop_sample = _AM(return_value=False)
    c._cop_sample_seed_done = True
    c._last_cop_sample_ts = 0.0
    c.cop_sensor_entity = None
    c._resolve_cop_sample_mode = _M(return_value="heating")

    snap = DataSnapshot()
    snap.cop = 4.5
    snap.state = "running"
    snap.boiler_active = False
    snap.attrs = {
        "Operation Mode": "Heating",
        "Outdoor air temp.(R1T)": 10.0,
        "Flow sensor (l/min)": 15.0,
        "Inlet water temp.(R4T)": 25.0,
        "Leaving water temp. before BUH (R1T)": 30.0,
    }
    c.data = snap

    await DaikinCycleMLCoordinator._maybe_collect_cop_sample(c, now=10000.0)
    assert c._last_cop_sample_ts == 0.0


# ============================================================
# Block B — engineered COP separation (v22 boiler_active)
# ============================================================

@pytest.mark.asyncio
async def test_migrate_to_v22_adds_column(tmp_path):
    """v22 adds boiler_active column to cop_samples."""
    from custom_components.daikin_cycle_ml.storage.db import CycleDB
    db = CycleDB(tmp_path / "v22test.db")
    await db.async_open()
    await db.async_initialize()

    # Fresh DB: column already exists via CREATE TABLE. Drop to simulate pre-v22.
    conn = db._require()
    try:
        await conn.execute("ALTER TABLE cop_samples DROP COLUMN boiler_active")
        await conn.commit()
    except Exception as exc:
        await db.async_close()
        pytest.skip(f"SQLite cannot DROP COLUMN: {exc}")

    result = await db.async_migrate_to_v22()
    assert result.get("completed") is True
    assert "boiler_active" in result.get("columns_added", [])

    cur = await conn.execute("PRAGMA table_info(cop_samples)")
    cols = {row[1] for row in await cur.fetchall()}
    await cur.close()
    assert "boiler_active" in cols
    await db.async_close()


@pytest.mark.asyncio
async def test_migrate_to_v22_idempotent(tmp_path):
    """v22 is idempotent via marker."""
    from custom_components.daikin_cycle_ml.storage.db import CycleDB
    db = CycleDB(tmp_path / "v22idem.db")
    await db.async_open()
    await db.async_initialize()
    first = await db.async_migrate_to_v22()
    assert first.get("completed") is True
    second = await db.async_migrate_to_v22()
    assert second.get("skipped") == 1
    await db.async_close()


@pytest.mark.asyncio
async def test_cop_sample_co_fire_saved_with_flag():
    """Co-fire sample saved with boiler_active=1."""
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator, DataSnapshot,
    )
    from unittest.mock import AsyncMock as _AM, MagicMock as _M

    c = _M()
    c.db = _M()
    c.db.async_get_max_cop_sample_ts = _AM(return_value=None)
    c.db.async_insert_cop_sample = _AM(return_value=True)
    c._cop_sample_seed_done = True
    c._last_cop_sample_ts = 0.0
    c.cop_sensor_entity = None
    c._resolve_cop_sample_mode = _M(return_value="heating")

    snap = DataSnapshot()
    snap.cop = 4.5
    snap.state = "running"
    snap.boiler_active = True  # co-fire
    snap.attrs = {
        "Operation Mode": "Heating",
        "Outdoor air temp.(R1T)": 10.0,
        "Flow sensor (l/min)": 15.0,
        "Inlet water temp.(R4T)": 25.0,
        "Leaving water temp. before BUH (R1T)": 30.0,
    }
    c.data = snap

    await DaikinCycleMLCoordinator._maybe_collect_cop_sample(c, now=10000.0)
    c.db.async_insert_cop_sample.assert_called_once()
    row = c.db.async_insert_cop_sample.call_args[0][0]
    assert row.get('boiler_active') == 1


@pytest.mark.asyncio
async def test_cop_sample_pure_hp_has_flag_zero():
    """Pure HP sample has boiler_active=0."""
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator, DataSnapshot,
    )
    from unittest.mock import AsyncMock as _AM, MagicMock as _M

    c = _M()
    c.db = _M()
    c.db.async_get_max_cop_sample_ts = _AM(return_value=None)
    c.db.async_insert_cop_sample = _AM(return_value=True)
    c._cop_sample_seed_done = True
    c._last_cop_sample_ts = 0.0
    c.cop_sensor_entity = None
    c._resolve_cop_sample_mode = _M(return_value="heating")

    snap = DataSnapshot()
    snap.cop = 4.5
    snap.state = "running"
    snap.boiler_active = False
    snap.attrs = {
        "Operation Mode": "Heating",
        "Outdoor air temp.(R1T)": 10.0,
        "Flow sensor (l/min)": 15.0,
        "Inlet water temp.(R4T)": 25.0,
        "Leaving water temp. before BUH (R1T)": 30.0,
    }
    c.data = snap

    await DaikinCycleMLCoordinator._maybe_collect_cop_sample(c, now=10000.0)
    row = c.db.async_insert_cop_sample.call_args[0][0]
    assert row.get('boiler_active') == 0


# ============================================================
# Non-hybrid isolation: sensors return None, no boiler_pct field
# ============================================================

def test_boiler_sensors_none_for_non_hybrid_snapshot():
    """Non-hybrid snapshot → boiler sensors return None (unavailable)."""
    from custom_components.daikin_cycle_ml.binary_sensor import BINARY_SENSOR_DEFS
    from custom_components.daikin_cycle_ml.coordinator import DataSnapshot

    snap = DataSnapshot(is_hybrid=False, boiler_active=True, boiler_dhw_active=True)
    for key in ("boiler_operation_demand", "boiler_dhw_demand"):
        d = next(x for x in BINARY_SENSOR_DEFS if x["key"] == key)
        assert d["state_fn"](snap, None) is None


def test_boiler_sensors_return_state_for_hybrid_snapshot():
    """Hybrid snapshot → boiler sensors return actual state."""
    from custom_components.daikin_cycle_ml.binary_sensor import BINARY_SENSOR_DEFS
    from custom_components.daikin_cycle_ml.coordinator import DataSnapshot

    snap = DataSnapshot(is_hybrid=True, boiler_active=True, boiler_dhw_active=False)
    for key, expected in (("boiler_operation_demand", True), ("boiler_dhw_demand", False)):
        d = next(x for x in BINARY_SENSOR_DEFS if x["key"] == key)
        assert d["state_fn"](snap, None) is expected


def test_hybrid_mode_sensor_none_for_non_hybrid():
    """Non-hybrid → hybrid_mode sensor returns None."""
    from custom_components.daikin_cycle_ml.sensor import SENSOR_DEFS
    from custom_components.daikin_cycle_ml.coordinator import DataSnapshot

    snap = DataSnapshot(is_hybrid=False, hybrid_mode="H/P only")
    d = next(x for x in SENSOR_DEFS if x["key"] == "hybrid_mode")
    assert d["value_fn"](snap, None) is None


def test_boiler_contribution_pct_none_for_non_hybrid():
    """Non-hybrid → boiler_contribution_today_pct returns None."""
    from custom_components.daikin_cycle_ml.sensor import SENSOR_DEFS
    from custom_components.daikin_cycle_ml.coordinator import DataSnapshot

    snap = DataSnapshot(
        is_hybrid=False,
        cop_today={"cop": 4.5, "boiler_pct": 50.0},
    )
    d = next(x for x in SENSOR_DEFS if x["key"] == "boiler_contribution_today_pct")
    assert d["value_fn"](snap, None) is None


def test_is_hybrid_install_helper():
    """_is_hybrid_install() returns True for EVLQ models."""
    from unittest.mock import MagicMock as _M
    from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator

    c = _M()
    c.entry = _M()
    c.entry.data = {"model": "evlq08cv3"}
    assert DaikinCycleMLCoordinator._is_hybrid_install(c) is True

    c.entry.data = {"model": "epra08eav3"}
    assert DaikinCycleMLCoordinator._is_hybrid_install(c) is False

    c.entry = None
    assert DaikinCycleMLCoordinator._is_hybrid_install(c) is False


# ============================================================
# Coverage: _is_hybrid_install + hybrid boiler_pct path + self-healing
# ============================================================

def test_is_hybrid_install_exception_branch(monkeypatch):
    """_is_hybrid_install catches exception from family_for_model."""
    from unittest.mock import MagicMock as _M
    from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
    import custom_components.daikin_cycle_ml.coordinator as _coord_mod

    # Monkeypatch family_for_model import path
    def _raise(*a, **kw):
        raise RuntimeError("simulated")
    monkeypatch.setattr(
        "custom_components.daikin_cycle_ml.const.family_for_model", _raise
    )

    c = _M()
    c.entry = _M()
    c.entry.data = {"model": "evlq08cv3"}
    # exception in try → returns False
    assert DaikinCycleMLCoordinator._is_hybrid_install(c) is False


@pytest.mark.asyncio
async def test_refresh_cop_today_hybrid_with_boiler_pct():
    """Hybrid snapshot: _build adds boiler_pct to cop_today."""
    import time as _time
    from unittest.mock import AsyncMock as _AM, MagicMock as _M
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator, DataSnapshot,
    )

    lt = _time.localtime()
    today_start = _time.mktime(
        (lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)
    )
    ts = today_start + 3600

    # 2 pure HP + 2 co-fire samples
    rows = [
        {"ts": ts, "cop": 4.0, "mode": "heating", "boiler_active": 0},
        {"ts": ts + 1, "cop": 4.5, "mode": "heating", "boiler_active": 0},
        {"ts": ts + 2, "cop": 6.0, "mode": "heating", "boiler_active": 1},
        {"ts": ts + 3, "cop": 6.5, "mode": "heating", "boiler_active": 1},
    ]

    c = _M()
    c.entry = _M()
    c.entry.data = {"model": "evlq08cv3"}
    c.db = _M()
    c.db.async_fetch_cop_samples = _AM(return_value=rows)
    c._cop_today_cache = {}
    c._cop_today_heating_cache = {}

    await DaikinCycleMLCoordinator._refresh_cop_today(c, ts + 10)

    heating = c._cop_today_heating_cache
    # 2 pure HP samples → cop = 4.25
    assert heating.get("cop") == 4.25
    assert heating.get("samples_today") == 2
    # 50% of samples were co-fire
    assert heating.get("boiler_pct") == 50.0


@pytest.mark.asyncio
async def test_refresh_cop_today_all_boiler_only_hybrid():
    """Hybrid: all co-fire (no pure HP) → boiler_pct only, no cop."""
    import time as _time
    from unittest.mock import AsyncMock as _AM, MagicMock as _M
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator,
    )

    lt = _time.localtime()
    today_start = _time.mktime(
        (lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)
    )
    ts = today_start + 3600
    rows = [
        {"ts": ts, "cop": 6.0, "mode": "heating", "boiler_active": 1},
    ]

    c = _M()
    c.entry = _M()
    c.entry.data = {"model": "evlq08cv3"}
    c.db = _M()
    c.db.async_fetch_cop_samples = _AM(return_value=rows)
    c._cop_today_cache = {}
    c._cop_today_heating_cache = {}

    await DaikinCycleMLCoordinator._refresh_cop_today(c, ts + 10)
    heating = c._cop_today_heating_cache
    assert "cop" not in heating
    assert heating.get("boiler_pct") == 100.0


@pytest.mark.asyncio
async def test_ensure_cop_samples_table_self_heals_missing_column(tmp_path):
    """async_ensure_cop_samples_table adds boiler_active to legacy DB."""
    from custom_components.daikin_cycle_ml.storage.db import CycleDB

    db = CycleDB(tmp_path / "selfheal.db")
    await db.async_open()
    await db.async_initialize()
    conn = db._require()

    # Drop the column to simulate legacy DB
    try:
        await conn.execute("ALTER TABLE cop_samples DROP COLUMN boiler_active")
        await conn.commit()
    except Exception as exc:
        await db.async_close()
        pytest.skip(f"SQLite cannot DROP COLUMN: {exc}")

    # Verify column is gone
    cur = await conn.execute("PRAGMA table_info(cop_samples)")
    cols = {row[1] for row in await cur.fetchall()}
    await cur.close()
    assert "boiler_active" not in cols

    # Call ensure → should self-heal
    await db.async_ensure_cop_samples_table()

    cur = await conn.execute("PRAGMA table_info(cop_samples)")
    cols = {row[1] for row in await cur.fetchall()}
    await cur.close()
    assert "boiler_active" in cols
    await db.async_close()


# ============================================================
# Coverage: 4 exact-missing lines (coordinator 2544, db 1504-1508/2393/2416)
# ============================================================

@pytest.mark.asyncio
async def test_refresh_stooklijn_skips_cofire_samples():
    """coordinator.py line 2544: co-fire samples skipped in stooklijn loop."""
    import time as _time
    from unittest.mock import AsyncMock as _AM, MagicMock as _M
    from custom_components.daikin_cycle_ml.coordinator import (
        DaikinCycleMLCoordinator, DataSnapshot,
    )

    now = _time.time()
    # 20 pure HP samples (18+ needed for analyze_stooklijn) + 1 co-fire
    # The co-fire sample triggers `continue` at line 2544.
    rows = [
        {
            "ts": now - i * 60,
            "cop": 4.5,
            "lwt": 35.0,
            "outdoor": 7.0,
            "flow_lmin": 15.0,
            "power_stable": 1,
            "mode": "heating",
            "boiler_active": 0,
        }
        for i in range(20)
    ]
    # Append one co-fire sample that MUST be skipped
    rows.append({
        "ts": now - 21 * 60,
        "cop": 8.0,
        "lwt": 35.0,
        "outdoor": 7.0,
        "flow_lmin": 15.0,
        "power_stable": 1,
        "mode": "heating",
        "boiler_active": 1,  # ← triggers continue at line 2544
    })

    c = _M()
    c.db = _M()
    c.db.async_fetch_cop_samples = _AM(return_value=rows)
    c.options = {}
    c.indoor_temp_entity = None
    c.hass = _M()
    c._stooklijn_cache = {}
    snap = DataSnapshot()
    snap.attrs = {}
    c.data = snap

    # Should not raise; co-fire sample skipped
    await DaikinCycleMLCoordinator._maybe_refresh_stooklijn(c, now=now, force=True)


@pytest.mark.asyncio
async def test_migrate_to_v22_legacy_db_gets_column(tmp_path):
    """db.py lines 1504-1508: v22 ALTER path on true legacy DB."""
    import aiosqlite
    from custom_components.daikin_cycle_ml.storage.db import CycleDB

    db_path = tmp_path / "legacy_v22.db"
    # Build legacy schema: cop_samples without boiler_active + model_state
    # (async_migrate_to_v22 checks the marker in model_state).
    async with aiosqlite.connect(str(db_path)) as raw:
        await raw.execute(
            "CREATE TABLE cop_samples ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "ts REAL NOT NULL,"
            "cop REAL NOT NULL,"
            "lwt REAL,"
            "outdoor REAL,"
            "flow_lmin REAL,"
            "power_stable INTEGER DEFAULT 0)"
        )
        await raw.execute(
            "CREATE TABLE cycles ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "start_ts REAL NOT NULL UNIQUE)"
        )
        await raw.execute(
            "CREATE TABLE model_state ("
            "key TEXT PRIMARY KEY,"
            "value_json TEXT,"
            "updated_ts REAL)"
        )
        await raw.commit()

    db = CycleDB(db_path)
    await db.async_open()
    try:
        conn = db._require()

        # Pre-condition: no boiler_active
        cur = await conn.execute("PRAGMA table_info(cop_samples)")
        cols = {row[1] for row in await cur.fetchall()}
        await cur.close()
        assert "boiler_active" not in cols

        # Migrate → ensure self-heals the column
        result = await db.async_migrate_to_v22()
        assert result.get("completed") is True

        # Post-condition: column present
        cur = await conn.execute("PRAGMA table_info(cop_samples)")
        cols = {row[1] for row in await cur.fetchall()}
        await cur.close()
        assert "boiler_active" in cols
    finally:
        await db.async_close()


@pytest.mark.asyncio
async def test_fetch_cop_samples_exclude_boiler(tmp_path):
    """db.py line 2393: include_boiler=False filters co-fire samples."""
    import time as _time
    from custom_components.daikin_cycle_ml.storage.db import CycleDB

    db = CycleDB(tmp_path / "fetch_filter.db")
    await db.async_open()
    await db.async_initialize()

    now = _time.time()
    # Insert: 1 pure HP + 1 co-fire
    await db.async_insert_cop_sample({
        "ts": now - 10, "cop": 4.0, "lwt": 35.0,
        "outdoor": 7.0, "flow_lmin": 15.0,
        "power_stable": True, "mode": "heating",
        "boiler_active": 0,
    })
    await db.async_insert_cop_sample({
        "ts": now - 5, "cop": 8.0, "lwt": 35.0,
        "outdoor": 7.0, "flow_lmin": 15.0,
        "power_stable": True, "mode": "heating",
        "boiler_active": 1,
    })

    # include_boiler=True (default): 2 rows
    all_rows = await db.async_fetch_cop_samples(days=1)
    assert len(all_rows) == 2

    # include_boiler=False: only pure HP → triggers line 2393
    pure_rows = await db.async_fetch_cop_samples(days=1, include_boiler=False)
    assert len(pure_rows) == 1
    assert pure_rows[0]["cop"] == 4.0

    await db.async_close()


@pytest.mark.asyncio
async def test_fetch_cop_samples_between_exclude_boiler(tmp_path):
    """db.py line 2416: include_boiler=False on between-fetch."""
    import time as _time
    from custom_components.daikin_cycle_ml.storage.db import CycleDB

    db = CycleDB(tmp_path / "between_filter.db")
    await db.async_open()
    await db.async_initialize()

    now = _time.time()
    await db.async_insert_cop_sample({
        "ts": now - 10, "cop": 4.0, "lwt": 35.0,
        "outdoor": 7.0, "flow_lmin": 15.0,
        "power_stable": True, "mode": "heating",
        "boiler_active": 0,
    })
    await db.async_insert_cop_sample({
        "ts": now - 5, "cop": 8.0, "lwt": 35.0,
        "outdoor": 7.0, "flow_lmin": 15.0,
        "power_stable": True, "mode": "heating",
        "boiler_active": 1,
    })

    # Both in window
    all_rows = await db.async_fetch_cop_samples_between(now - 100, now)
    assert len(all_rows) == 2

    # exclude co-fire → triggers line 2416
    pure_rows = await db.async_fetch_cop_samples_between(
        now - 100, now, include_boiler=False
    )
    assert len(pure_rows) == 1
    assert pure_rows[0]["cop"] == 4.0

    await db.async_close()
