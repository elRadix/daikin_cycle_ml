"""RED tests for ESPAltherma v2 source-type selection (issue #281).

R634: These tests MUST FAIL on current code if the source_type feature is
missing. Expected RED failures:
- `async_step_user` form does not include `source_type`
- `source_type=individual` does NOT route to `individual_prefix`
- `async_step_individual_prefix` does not exist
- `async_step_individual_review` does not exist

Existing behavior (monolithic + legacy shim) must remain green.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.daikin_cycle_ml.config_flow import (
    DaikinCycleMLConfigFlow,
)
from custom_components.daikin_cycle_ml.const import (
    CONF_INDIVIDUAL_PREFIX,
    CONF_SOURCE_TYPE,
    DEFAULT_INDIVIDUAL_PREFIX,
    REQUIRED_ATTRIBUTES,
    SOURCE_TYPE_AUTO,
    SOURCE_TYPE_INDIVIDUAL,
    SOURCE_TYPE_MONOLITHIC,
)


def _fresh_flow() -> DaikinCycleMLConfigFlow:
    """Minimal fresh flow state for calling async_step_* directly."""
    flow = DaikinCycleMLConfigFlow()
    flow.hass = MagicMock()
    flow.hass.states.async_all = MagicMock(return_value=[])
    flow.hass.states.get = MagicMock(return_value=None)
    flow.context = {}
    flow._data = {}
    flow._options = {}
    flow._selected_family = None
    flow._selected_model = None
    flow._reconfigure_entry = None
    return flow


def _schema_keys(schema_obj) -> set[str]:
    """Extract key names from a vol.Schema. Keys are vol.Optional/Required."""
    out: set[str] = set()
    for k in schema_obj.schema.keys():
        name = getattr(k, "schema", k)
        out.add(str(name))
    return out


# ---------- user form: source_type field presence ----------


@pytest.mark.asyncio
async def test_user_form_has_source_type_field() -> None:
    """RED: current form only has 'family'."""
    flow = _fresh_flow()
    result = await flow.async_step_user()
    assert result["type"] == "form"
    assert result["step_id"] == "user"
    keys = _schema_keys(result["data_schema"])
    assert "family" in keys, "existing family field must remain"
    assert "source_type" in keys, "source_type field must be added (#281)"


# ---------- user submit: routing per source_type ----------


@pytest.mark.asyncio
async def test_user_default_source_type_is_monolithic() -> None:
    """Backwards-compat: no source_type -> default monolithic, routes to model."""
    flow = _fresh_flow()
    result = await flow.async_step_user({"family": "ERGA"})
    assert result["step_id"] == "model", "monolithic path unchanged"
    assert flow._data.get(CONF_SOURCE_TYPE) == SOURCE_TYPE_MONOLITHIC, (
        "default source_type must be persisted as monolithic"
    )


@pytest.mark.asyncio
async def test_user_monolithic_routes_to_model() -> None:
    flow = _fresh_flow()
    result = await flow.async_step_user(
        {"family": "ERGA", "source_type": SOURCE_TYPE_MONOLITHIC}
    )
    assert result["step_id"] == "model"


@pytest.mark.asyncio
async def test_user_auto_routes_to_model() -> None:
    """Auto uses runtime dispatch; no prefix step in config_flow."""
    flow = _fresh_flow()
    result = await flow.async_step_user(
        {"family": "ERGA", "source_type": SOURCE_TYPE_AUTO}
    )
    assert result["step_id"] == "model"


@pytest.mark.asyncio
async def test_user_individual_routes_to_prefix() -> None:
    """RED: current flow routes individual to model."""
    flow = _fresh_flow()
    result = await flow.async_step_user(
        {"family": "ERGA", "source_type": SOURCE_TYPE_INDIVIDUAL}
    )
    assert result["step_id"] == "individual_prefix", (
        f"individual must route to prefix step, got {result['step_id']!r}"
    )


@pytest.mark.asyncio
async def test_legacy_shim_routes_to_model() -> None:
    """Existing tests submit `source_sensor` (legacy) — must not break."""
    flow = _fresh_flow()
    result = await flow.async_step_user(
        {"source_sensor": "sensor.x", "model": "epra12eav3"}
    )
    assert result["step_id"] == "model"


# ---------- individual_prefix step ----------


@pytest.mark.asyncio
async def test_individual_prefix_form_defaults_to_default_value() -> None:
    """RED: step does not exist yet."""
    flow = _fresh_flow()
    flow._data = {CONF_SOURCE_TYPE: SOURCE_TYPE_INDIVIDUAL}
    result = await flow.async_step_individual_prefix()
    assert result["type"] == "form"
    assert result["step_id"] == "individual_prefix"
    keys = _schema_keys(result["data_schema"])
    assert "individual_prefix" in keys


@pytest.mark.asyncio
async def test_individual_prefix_submit_to_review() -> None:
    """RED: step does not exist yet."""
    flow = _fresh_flow()
    flow._data = {CONF_SOURCE_TYPE: SOURCE_TYPE_INDIVIDUAL}
    result = await flow.async_step_individual_prefix(
        {"individual_prefix": "sensor.custom_"}
    )
    assert result["step_id"] == "individual_review"
    assert flow._data.get(CONF_INDIVIDUAL_PREFIX) == "sensor.custom_"


@pytest.mark.asyncio
async def test_individual_prefix_stores_default_when_blank() -> None:
    """Empty submit -> stores DEFAULT_INDIVIDUAL_PREFIX."""
    flow = _fresh_flow()
    flow._data = {CONF_SOURCE_TYPE: SOURCE_TYPE_INDIVIDUAL}
    await flow.async_step_individual_prefix({"individual_prefix": ""})
    assert flow._data.get(CONF_INDIVIDUAL_PREFIX) == DEFAULT_INDIVIDUAL_PREFIX


# ---------- individual_review step ----------


@pytest.mark.asyncio
async def test_individual_review_returns_form_with_placeholders() -> None:
    """RED: step does not exist yet."""
    flow = _fresh_flow()
    flow._data = {
        CONF_SOURCE_TYPE: SOURCE_TYPE_INDIVIDUAL,
        CONF_INDIVIDUAL_PREFIX: "sensor.espaltherma_",
    }
    result = await flow.async_step_individual_review()
    assert result["type"] == "form"
    assert result["step_id"] == "individual_review"
    placeholders = result.get("description_placeholders", {})
    assert "matched" in placeholders
    assert "total" in placeholders
    assert placeholders["total"] == str(len(REQUIRED_ATTRIBUTES))


@pytest.mark.asyncio
async def test_individual_review_shows_matched_equals_total_on_full_payload() -> None:
    """When all required entities are present, matched == total == 12."""
    flow = _fresh_flow()
    flow._data = {
        CONF_SOURCE_TYPE: SOURCE_TYPE_INDIVIDUAL,
        CONF_INDIVIDUAL_PREFIX: "sensor.espaltherma_",
    }
    # Simulate a full v2 install: every required label resolves.
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
    )
    from custom_components.daikin_cycle_ml.engine.espaltherma_v2.slug import (
        make_json_key,
    )
    values = {
        ATTR_OPERATION_MODE: "Heating", ATTR_IU_OPERATION_MODE: "Heating",
        ATTR_3WAY_VALVE: "Off:Space", ATTR_DEFROST_OPERATION: "OFF",
        ATTR_LEAVING_WATER_AFTER_BUH: "35.0", ATTR_INLET_WATER_R4T: "30.0",
        ATTR_OUTDOOR_AIR_R1T: "8.5", ATTR_FLOW_SENSOR: "15.0",
        ATTR_WATER_PUMP_OPERATION: "ON", ATTR_BUH_STEP1: "OFF",
        ATTR_BUH_STEP2: "OFF", ATTR_LW_SETPOINT: "40.0",
    }
    states = []
    for label, val in values.items():
        s = MagicMock()
        s.entity_id = f"sensor.espaltherma_{make_json_key(label)}"
        s.state = val
        states.append(s)

    def async_all(domain: str) -> list[MagicMock]:
        return states if domain == "sensor" else []

    def get(eid: str) -> MagicMock | None:
        for s in states:
            if s.entity_id == eid:
                return s
        return None

    flow.hass.states.async_all = MagicMock(side_effect=async_all)
    flow.hass.states.get = MagicMock(side_effect=get)

    result = await flow.async_step_individual_review()
    ph = result["description_placeholders"]
    assert ph["matched"] == ph["total"] == str(len(REQUIRED_ATTRIBUTES))


@pytest.mark.asyncio
async def test_individual_review_submit_continues_to_model() -> None:
    """RED: step does not exist yet."""
    flow = _fresh_flow()
    flow._data = {
        CONF_SOURCE_TYPE: SOURCE_TYPE_INDIVIDUAL,
        CONF_INDIVIDUAL_PREFIX: "sensor.espaltherma_",
    }
    result = await flow.async_step_individual_review({})
    assert result["step_id"] == "model"


# ---------- full chain ----------


@pytest.mark.asyncio
async def test_full_chain_individual_creates_entry() -> None:
    """End-to-end individual flow ends in create_entry with the new fields.

    RED: current flow ignores source_type end-to-end, so `create_entry` data
    will lack both source_type and individual_prefix.
    """
    flow = _fresh_flow()
    # user
    await flow.async_step_user(
        {"family": "ERGA", "source_type": SOURCE_TYPE_INDIVIDUAL}
    )
    # prefix
    await flow.async_step_individual_prefix(
        {"individual_prefix": "sensor.espaltherma_"}
    )
    # review (submit)
    await flow.async_step_individual_review({})
    # Skip async_step_model: it requires a valid source_sensor entity in
    # hass.states, but the individual path doesn't use source_sensor at all.
    # Pre-set the model state directly, then call finalize.
    flow._selected_family = "ERGA"
    flow._selected_model = "epra12eav3"
    flow._data.setdefault("model", "epra12eav3")
    flow._data.setdefault("source_sensor", "sensor.althermasensors")
    result = await flow.async_step_finalize({})
    assert result["type"] == "create_entry"
    assert result["data"].get(CONF_SOURCE_TYPE) == SOURCE_TYPE_INDIVIDUAL
    assert (
        result["data"].get(CONF_INDIVIDUAL_PREFIX) == "sensor.espaltherma_"
    )


# ---------- v1.20.0 #281 coverage: exception paths + branch coverage ----------


@pytest.mark.asyncio
async def test_user_step_survives_discovery_import_error(monkeypatch) -> None:
    """Lines 356-357: build_slug_index raises -> v2_count falls back to 0,
    form still rendered (defensive; prevents a broken integration from
    bricking the whole config flow)."""
    from custom_components.daikin_cycle_ml.engine.espaltherma_v2 import (
        discovery,
    )
    def boom(*args, **kwargs):
        raise RuntimeError("simulated discovery failure")
    monkeypatch.setattr(discovery, "build_slug_index", boom)
    flow = _fresh_flow()
    result = await flow.async_step_user()
    assert result["step_id"] == "user"
    assert result["description_placeholders"]["v2_count"] == "0"


@pytest.mark.asyncio
async def test_individual_review_shows_collisions(monkeypatch) -> None:
    """Line 411: non-empty collisions -> collision_block populated."""
    from custom_components.daikin_cycle_ml import config_flow as cf
    fake = MagicMock()
    fake.missing_required = []
    fake.collisions = ["fin_temp"]
    fake.discovered_count = 12
    monkeypatch.setattr(
        cf, "resolve_attrs", lambda hass, prefix: fake,
    )
    flow = _fresh_flow()
    flow._data[CONF_INDIVIDUAL_PREFIX] = DEFAULT_INDIVIDUAL_PREFIX
    result = await flow.async_step_individual_review()
    ph = result["description_placeholders"]
    assert "fin_temp" in ph["collision_block"]
    assert ph["matched"] == ph["total"] == "12"


@pytest.mark.asyncio
async def test_model_step_custom_model_individual_goes_to_custom_info() -> None:
    """Line 448: MODEL_CUSTOM in individual flow -> custom_info step."""
    from custom_components.daikin_cycle_ml.const import (
        MODEL_CUSTOM,
    )
    flow = _fresh_flow()
    flow._data[CONF_SOURCE_TYPE] = SOURCE_TYPE_INDIVIDUAL
    result = await flow.async_step_model({"model": MODEL_CUSTOM})
    assert result["step_id"] == "model_custom_info"



# ---------- v1.20.0 #281 R693-compliant OptionsFlow helpers ----------

def _fresh_options_flow(entry):
    """R693-compliant OptionsFlow construction.

    HA OptionsFlow.config_entry is a read-only property that calls
    `hass.config_entries.async_get_known_entry(self._config_entry_id)`.
    Setting `flow.config_entry = entry` raises AttributeError (no setter).
    Mock the lookup instead. See R693.

    Also mocks async_get_entry (older HA versions) so both APIs work.
    """
    from custom_components.daikin_cycle_ml.config_flow import (
        DaikinCycleMLOptionsFlow,
    )
    flow = DaikinCycleMLOptionsFlow()
    flow.hass = MagicMock()
    flow.hass.config_entries = MagicMock()
    flow.hass.config_entries.async_update_entry = MagicMock()
    flow.hass.config_entries.async_get_known_entry = MagicMock(return_value=entry)
    flow.hass.config_entries.async_get_entry = MagicMock(return_value=entry)
    flow.handler = entry.entry_id
    flow.context = {"entry_id": entry.entry_id}
    return flow


def _await_if_coroutine(result):
    """`_save` is sync `def` returning async_create_entry's coroutine.
    Return the coroutine so callers can `await _await_if_coroutine(...)`.
    """
    return result


class _BrokenDataEntry:
    """ConfigEntry whose .data access raises (simulates uninitialized)."""

    def __init__(self, entry_id: str) -> None:
        self.entry_id = entry_id
        self.options: dict = {}

    @property
    def data(self):
        raise ValueError("config entry data not initialized")


# ---------- reconfigure_basic: setdefault branches (lines 1039-1043) ----------


@pytest.mark.asyncio
async def test_reconfigure_basic_switch_to_auto_skips_prefix_default(
    monkeypatch,
) -> None:
    """Line 1039: switch to AUTO enters the individual-branch
    (_skip_source_probe=True) but AUTO != INDIVIDUAL, so setdefault is
    NOT executed.
    """
    flow = _fresh_flow()
    entry = MagicMock()
    entry.data = {CONF_SOURCE_TYPE: SOURCE_TYPE_MONOLITHIC}
    entry.entry_id = "test-entry"
    flow._get_reconfigure_entry = MagicMock(return_value=entry)
    captured: dict = {}

    def fake_abort(entry_arg, data_updates=None, reason=None):
        captured["data_updates"] = dict(data_updates or {})
        return {"type": "abort", "reason": reason}

    monkeypatch.setattr(flow, "async_update_and_abort", fake_abort)
    await flow.async_step_reconfigure_basic({
        CONF_SOURCE_TYPE: SOURCE_TYPE_AUTO,
    })
    updates = captured["data_updates"]
    assert updates.get(CONF_SOURCE_TYPE) == SOURCE_TYPE_AUTO
    # AUTO != INDIVIDUAL, so setdefault was NOT executed
    assert CONF_INDIVIDUAL_PREFIX not in updates


@pytest.mark.asyncio
async def test_reconfigure_basic_switch_to_individual_sets_prefix_default(
    monkeypatch,
) -> None:
    """Companion: switch to INDIVIDUAL enters the same branch AND fires
    setdefault at line 1039-1042 with the default prefix.
    """
    flow = _fresh_flow()
    entry = MagicMock()
    entry.data = {CONF_SOURCE_TYPE: SOURCE_TYPE_MONOLITHIC}
    entry.entry_id = "test-entry"
    flow._get_reconfigure_entry = MagicMock(return_value=entry)
    captured: dict = {}

    def fake_abort(entry_arg, data_updates=None, reason=None):
        captured["data_updates"] = dict(data_updates or {})
        return {"type": "abort", "reason": reason}

    monkeypatch.setattr(flow, "async_update_and_abort", fake_abort)
    await flow.async_step_reconfigure_basic({
        CONF_SOURCE_TYPE: SOURCE_TYPE_INDIVIDUAL,
    })
    updates = captured["data_updates"]
    assert updates.get(CONF_SOURCE_TYPE) == SOURCE_TYPE_INDIVIDUAL
    assert updates.get(CONF_INDIVIDUAL_PREFIX) == DEFAULT_INDIVIDUAL_PREFIX


# ---------- options _save source_type routing (lines 1162-1171) ----------


@pytest.mark.asyncio
async def test_options_device_step_updates_source_type() -> None:
    """Lines 1162-1171: source_type change persists to entry.data
    (not options) via config_entries.async_update_entry.
    """
    entry = MagicMock()
    entry.data = {CONF_SOURCE_TYPE: SOURCE_TYPE_MONOLITHIC}
    entry.options = {}
    entry.entry_id = "test-entry"
    flow = _fresh_options_flow(entry)
    result = flow._save({
        "source_type": {CONF_SOURCE_TYPE: SOURCE_TYPE_INDIVIDUAL},
    })
    # _save is sync but returns coroutine (async_create_entry)
    if hasattr(result, "__await__"):
        result = await result
    flow.hass.config_entries.async_update_entry.assert_called_once()
    call_kwargs = flow.hass.config_entries.async_update_entry.call_args
    args, kwargs = call_kwargs
    updated = kwargs.get("data")
    if updated is None and len(args) > 1:
        updated = args[1]
    assert updated is not None
    assert updated.get(CONF_SOURCE_TYPE) == SOURCE_TYPE_INDIVIDUAL


# ---------- options _save failure path (lines 1172-1177) ----------


@pytest.mark.asyncio
async def test_options_save_warns_on_config_entry_failure(caplog) -> None:
    """Lines 1172-1177 + R580: config_entry.data access raises -> WARNING
    logged (not debug), change NOT persisted, _save still completes.
    """
    import logging

    entry = _BrokenDataEntry("test-entry")
    flow = _fresh_options_flow(entry)
    with caplog.at_level(logging.WARNING):
        result = flow._save({
            "source_type": {CONF_SOURCE_TYPE: SOURCE_TYPE_INDIVIDUAL},
        })
        if hasattr(result, "__await__"):
            result = await result
    # Warning was logged
    warns = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("source_type update failed" in r.getMessage() for r in warns), (
        f"R580: expected warning about source_type update failure; "
        f"got: {[r.getMessage() for r in warns]}"
    )
    # Change was NOT persisted
    flow.hass.config_entries.async_update_entry.assert_not_called()
    # _save still returned something usable (create_entry result)
    assert isinstance(result, dict)


# ---------- R580 fix #1: discovery warning (not silent) ----------


@pytest.mark.asyncio
async def test_user_step_warns_when_discovery_raises(
    monkeypatch, caplog,
) -> None:
    """R580: discovery failure logs WARNING (visible in HA logs), not silent.
    User form still shows v2_count=0 (doesn't brick the flow).
    """
    import logging

    from custom_components.daikin_cycle_ml.engine.espaltherma_v2 import (
        discovery,
    )

    def boom(*args, **kwargs):
        raise RuntimeError("simulated discovery failure")

    monkeypatch.setattr(discovery, "build_slug_index", boom)
    flow = _fresh_flow()
    with caplog.at_level(logging.WARNING):
        result = await flow.async_step_user()
    warns = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any(
        "ESPAltherma v2 discovery failed" in r.getMessage() for r in warns
    ), f"R580: expected discovery warning; got: {[r.getMessage() for r in warns]}"
    assert result["description_placeholders"]["v2_count"] == "0"


@pytest.mark.asyncio
async def test_options_save_skips_update_when_source_type_unchanged() -> None:
    """Line 1177->1195: source_type submitted == current -> _changed empty
    -> async_update_entry NOT called, no warning. User intentionally resubmits
    the current value (e.g. from any options step that shares _save)."""
    entry = MagicMock()
    entry.data = {CONF_SOURCE_TYPE: SOURCE_TYPE_MONOLITHIC}
    entry.options = {}
    entry.entry_id = "test-entry"
    flow = _fresh_options_flow(entry)
    # Same source_type as current data -> no change
    result = flow._save({
        "source_type": {CONF_SOURCE_TYPE: SOURCE_TYPE_MONOLITHIC},
    })
    if hasattr(result, "__await__"):
        result = await result
    # No update because nothing changed
    flow.hass.config_entries.async_update_entry.assert_not_called()
