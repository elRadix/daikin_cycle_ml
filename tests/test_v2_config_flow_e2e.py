"""E2E config flow tests for ESPAltherma v2 (issue #281).

R634/R639: full-chain from user step to finalize, for both individual
and monolithic modes, plus partial/outage scenarios.

RED: currently `async_step_model` assumes `source_sensor` in user_input;
individual mode hits KeyError at line 410. Also `async_step_diagnose` and
`async_step_attributes` read `hass.states.get(source_sensor)` which is
None in individual mode — they show all-missing.

Regression guards (must stay green):
- monolithic legacy flow unchanged
- existing monolithic wizard tests (test_48*, test_v181*) untouched
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

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
    SOURCE_TYPE_MONOLITHIC,
)
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


def _build_hass_with_v2(
    n_missing: int = 0,
    prefix: str = DEFAULT_INDIVIDUAL_PREFIX,
) -> MagicMock:
    """Mock hass with n_missing required attrs absent from v2 entity set."""
    payload = _full_attrs_str()
    keys = list(payload.keys())
    missing_keys = set(keys[-n_missing:]) if n_missing else set()
    states = []
    for label, val in payload.items():
        if label in missing_keys:
            continue
        s = MagicMock()
        s.entity_id = f"{prefix}{make_json_key(label)}"
        s.state = val
        states.append(s)

    hass = MagicMock()

    def async_all(domain: str) -> list[MagicMock]:
        return states if domain == "sensor" else []

    def get(eid: str) -> MagicMock | None:
        for s in states:
            if s.entity_id == eid:
                return s
        return None

    hass.states.async_all = MagicMock(side_effect=async_all)
    hass.states.get = MagicMock(side_effect=get)
    return hass


def _make_flow(hass: MagicMock) -> DaikinCycleMLConfigFlow:
    flow = DaikinCycleMLConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._data = {}
    flow._options = {}
    flow._selected_family = None
    flow._selected_model = None
    flow._reconfigure_entry = None
    return flow


async def _drive_wizard_to_finalize(flow: DaikinCycleMLConfigFlow) -> dict:
    """Drive the wizard through every post-model step with minimal input."""
    # User step
    r = await flow.async_step_user(
        {"family": "ERGA", "source_type": flow._data.get(CONF_SOURCE_TYPE,
                                                        SOURCE_TYPE_MONOLITHIC)}
    )
    # If individual, drive through prefix + review
    if r.get("step_id") == "individual_prefix":
        r = await flow.async_step_individual_prefix(
            {"individual_prefix": flow._data.get(CONF_INDIVIDUAL_PREFIX,
                                                 DEFAULT_INDIVIDUAL_PREFIX)}
        )
        assert r.get("step_id") == "individual_review"
        r = await flow.async_step_individual_review({})
        assert r.get("step_id") == "model", (
            f"review should dispatch to model, got {r.get('step_id')}"
        )
    # Model step. Monolithic needs source_sensor; individual does not.
    # Build input based on the flow's source_type so monolithic/auto
    # (which resolve to monolithic here) send the legacy field, while
    # individual omits it (async_step_model must handle that per #281).
    _src = flow._data.get(CONF_SOURCE_TYPE, SOURCE_TYPE_MONOLITHIC)
    _model_input: dict = {"model": "epra12eav3", "attribute_mode": "auto"}
    if _src in (SOURCE_TYPE_MONOLITHIC, SOURCE_TYPE_AUTO):
        _model_input["source_sensor"] = "sensor.althermasensors"
    r = await flow.async_step_model(_model_input)
    # After model, we may land on attributes/diagnose/model_custom_info
    # Just continue until we hit finalize, max 15 steps.
    for _ in range(15):
        if r.get("step_id") == "finalize":
            break
        sid = r.get("step_id")
        if sid == "attributes":
            r = await flow.async_step_attributes({})
        elif sid == "cycle":
            r = await flow.async_step_cycle({
                "compressor_rps_threshold": 3.0,
            })
        elif sid == "pendulum":
            r = await flow.async_step_pendulum({
                "short_run_threshold_min": 20,
                "short_off_threshold_min": 5,
                "short_cycling_window_min": 60,
                "short_cycling_min_cycles": 3,
                "pendulum_cycles_per_hour": 4,
                "pendulum_cycles_per_day": 40,
            })
        elif sid == "quality":
            r = await flow.async_step_quality({
                "good_run_threshold_min": 45,
                "good_dt_threshold_k": 5.0,
                "good_off_threshold_min": 20,
                "target_cycles_per_day": 8,
                "short_cycle_ratio_threshold_pct": 50,
            })
        elif sid == "notifications":
            r = await flow.async_step_notifications({
                "persistent_enabled": True,
            })
        elif sid == "diagnose":
            # Individual mode: diagnose should not blow up on missing state
            r = await flow.async_step_diagnose({})
        elif sid == "model_custom_info":
            r = await flow.async_step_model_custom_info({})
        elif sid == "map_attributes":
            r = await flow.async_step_map_attributes({})
        else:
            raise AssertionError(
                f"wizard stuck at unexpected step {sid!r} "
                f"(flow._data keys: {sorted(flow._data.keys())})"
            )
    assert r.get("step_id") == "finalize", (
        f"never reached finalize, last step {r.get('step_id')}, "
        f"data={sorted(flow._data.keys())}"
    )
    # Finalize submit
    return await flow.async_step_finalize({})


# ---------- E2E: individual 12/12 ----------


@pytest.mark.asyncio
async def test_e2e_individual_full_12_of_12() -> None:
    hass = _build_hass_with_v2(n_missing=0)
    flow = _make_flow(hass)
    flow._data[CONF_SOURCE_TYPE] = SOURCE_TYPE_INDIVIDUAL
    flow._data[CONF_INDIVIDUAL_PREFIX] = DEFAULT_INDIVIDUAL_PREFIX
    result = await _drive_wizard_to_finalize(flow)
    assert result["type"] == "create_entry"
    assert result["data"].get(CONF_SOURCE_TYPE) == SOURCE_TYPE_INDIVIDUAL
    assert (
        result["data"].get(CONF_INDIVIDUAL_PREFIX) == DEFAULT_INDIVIDUAL_PREFIX
    )
    assert result["data"].get("model") == "epra12eav3"


@pytest.mark.asyncio
async def test_e2e_individual_partial_5_missing() -> None:
    """5 missing (BUH Step1/2 + LW setpoint + outdoor + flow) still completes."""
    hass = _build_hass_with_v2(n_missing=5)
    flow = _make_flow(hass)
    flow._data[CONF_SOURCE_TYPE] = SOURCE_TYPE_INDIVIDUAL
    flow._data[CONF_INDIVIDUAL_PREFIX] = DEFAULT_INDIVIDUAL_PREFIX
    result = await _drive_wizard_to_finalize(flow)
    assert result["type"] == "create_entry"
    assert result["data"].get(CONF_SOURCE_TYPE) == SOURCE_TYPE_INDIVIDUAL


@pytest.mark.asyncio
async def test_e2e_individual_full_outage_0_of_12() -> None:
    """0/12 attrs: wizard completes gracefully (repair issue is coordinator's
    job, not config flow)."""
    hass = _build_hass_with_v2(n_missing=12)
    flow = _make_flow(hass)
    flow._data[CONF_SOURCE_TYPE] = SOURCE_TYPE_INDIVIDUAL
    flow._data[CONF_INDIVIDUAL_PREFIX] = DEFAULT_INDIVIDUAL_PREFIX
    result = await _drive_wizard_to_finalize(flow)
    assert result["type"] == "create_entry"


# ---------- E2E: auto ----------


@pytest.mark.asyncio
async def test_e2e_auto_with_monolithic_present() -> None:
    hass = _build_hass_with_v2(n_missing=0)
    # Add monolithic entity
    mono = MagicMock()
    mono.entity_id = "sensor.althermasensors"
    mono.state = "on"
    mono.attributes = dict(_full_attrs_str().items())

    existing_all = hass.states.async_all.side_effect
    existing_get = hass.states.get.side_effect

    def async_all(domain):
        return existing_all(domain)

    def get(eid):
        if eid == "sensor.althermasensors":
            return mono
        return existing_get(eid)

    hass.states.async_all = MagicMock(side_effect=async_all)
    hass.states.get = MagicMock(side_effect=get)

    flow = _make_flow(hass)
    flow._data[CONF_SOURCE_TYPE] = SOURCE_TYPE_AUTO
    result = await _drive_wizard_to_finalize(flow)
    assert result["type"] == "create_entry"
    assert result["data"].get(CONF_SOURCE_TYPE) == SOURCE_TYPE_AUTO


# ---------- E2E: monolithic unchanged ----------


@pytest.mark.asyncio
async def test_e2e_monolithic_legacy_path_unchanged() -> None:
    """Regression: monolithic user with full source_sensor works identically."""
    attrs = _full_attrs_str()
    mono = MagicMock()
    mono.entity_id = "sensor.althermasensors"
    mono.state = "on"
    mono.attributes = attrs

    hass = MagicMock()
    hass.states.async_all = MagicMock(return_value=[])
    hass.states.get = MagicMock(
        side_effect=lambda eid: mono if eid == "sensor.althermasensors" else None
    )

    flow = _make_flow(hass)
    flow._data[CONF_SOURCE_TYPE] = SOURCE_TYPE_MONOLITHIC
    result = await _drive_wizard_to_finalize(flow)
    assert result["type"] == "create_entry"
    assert result["data"].get(CONF_SOURCE_TYPE) == SOURCE_TYPE_MONOLITHIC


# ---------- diagnose / attributes in individual mode ----------


@pytest.mark.asyncio
async def test_individual_diagnose_uses_resolver() -> None:
    """RED: async_step_diagnose reads hass.states.get(source_sensor) only.

    Without a resolver-aware branch, individual mode sees source=None
    and reports all required attributes as missing (missing_count=12).
    """
    hass = _build_hass_with_v2(n_missing=0)
    flow = _make_flow(hass)
    flow._data[CONF_SOURCE_TYPE] = SOURCE_TYPE_INDIVIDUAL
    flow._data[CONF_INDIVIDUAL_PREFIX] = DEFAULT_INDIVIDUAL_PREFIX
    # No _smart_available preset: force diagnose to do the real work
    result = await flow.async_step_diagnose()
    assert result["type"] == "form"
    assert result["step_id"] == "diagnose"
    ph = result.get("description_placeholders", {})
    # With resolver wired, missing_count must be 0 (all 12 present)
    assert ph.get("missing_count") == "0", (
        f"individual diagnose should see 0 missing, got {ph.get('missing_count')}"
    )


@pytest.mark.asyncio
async def test_individual_attributes_uses_resolver() -> None:
    """RED: async_step_attributes currently shows all-missing."""
    hass = _build_hass_with_v2(n_missing=0)
    flow = _make_flow(hass)
    flow._data[CONF_SOURCE_TYPE] = SOURCE_TYPE_INDIVIDUAL
    flow._data[CONF_INDIVIDUAL_PREFIX] = DEFAULT_INDIVIDUAL_PREFIX
    flow._data["model"] = "epra12eav3"
    result = await flow.async_step_attributes()
    assert result["type"] == "form"
    assert result["step_id"] == "attributes"
    ph = result.get("description_placeholders", {})
    present = int(ph.get("present", "0"))
    total = int(ph.get("total", "0"))
    assert total > 0
    # With resolver wired, individual full payload should show ~100% present
    assert present >= total * 0.8, (
        f"individual attributes should show >=80% present, "
        f"got {present}/{total}"
    )


# ---------- per-sensor value integrity (partial coverage) ----------


@pytest.mark.asyncio
async def test_individual_full_payload_all_values_normalized() -> None:
    """After wizard, entry.data must reflect source_type=individual."""
    hass = _build_hass_with_v2(n_missing=0)
    flow = _make_flow(hass)
    flow._data[CONF_SOURCE_TYPE] = SOURCE_TYPE_INDIVIDUAL
    flow._data[CONF_INDIVIDUAL_PREFIX] = DEFAULT_INDIVIDUAL_PREFIX
    result = await _drive_wizard_to_finalize(flow)
    assert result["data"][CONF_SOURCE_TYPE] == SOURCE_TYPE_INDIVIDUAL
    # No BOOL/string confusion: attribute_map not set (auto = canonical)
    assert "attribute_map" not in result["data"] or (
        result["data"]["attribute_map"] == {}
    )
