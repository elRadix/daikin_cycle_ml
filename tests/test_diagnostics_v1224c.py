"""v1.22.4-C: coverage for defensive branches in diagnostics helpers.

Every test in this file targets ONE specific uncovered branch (per
coverage report line numbers). No pragmas, no skipped branches.
"""
from __future__ import annotations

import json

import pytest
from unittest.mock import MagicMock, patch as _patch

from custom_components.daikin_cycle_ml.diagnostics import (
    _detector_snapshot,
    _detector_transitions,
    _device_registry,
    _entities_registry,
    _redact_strings_recursive,
    _repairs_snapshot,
    _source_full,
)


@pytest.fixture
def fake_entry_c(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    e = MockConfigEntry(
        domain="daikin_cycle_ml",
        entry_id="test_entry_c",
        title="Test C",
        data={"source_sensor": "sensor.althermasensors"},
    )
    e.add_to_hass(hass)
    return e


# ---- 1. line 47: tuple branch ----
def test_redact_strings_recursive_tuple():
    result = _redact_strings_recursive(
        (1, "notify.alice_phone", {"k": "notify.bob_tab"})
    )
    assert isinstance(result, tuple)
    assert result[0] == 1
    assert result[1] == "notify.**REDACTED**"
    assert result[2]["k"] == "notify.**REDACTED**"


# ---- 2. lines 216-217: >64KB truncation ----
@pytest.mark.asyncio
async def test_source_full_truncation(hass):
    big = {f"attr_{i}": "x" * 500 for i in range(300)}  # ~150KB
    hass.states.async_set("sensor.althermasensors", "on", big)
    coord = MagicMock()
    coord.source_entity = "sensor.althermasensors"
    out = _source_full(hass, coord)
    assert out["attributes_truncated"] is True
    assert len(out["attributes_full"]) <= 200


# ---- 3. line 241: per-entity attr truncation ----
@pytest.mark.asyncio
async def test_entities_registry_per_entity_truncation(hass, fake_entry_c):
    from homeassistant.helpers import entity_registry as er
    reg = er.async_get(hass)
    reg.async_get_or_create(
        "sensor", "daikin_cycle_ml", "big_attrs_entity_c",
        suggested_object_id="daikin_cycle_ml_big",
        config_entry=fake_entry_c,
    )
    hass.states.async_set(
        "sensor.daikin_cycle_ml_big", "ok", {"blob": "y" * 5000},
    )
    out = _entities_registry(hass, fake_entry_c)
    big = next(e for e in out["entries"] if e["entity_id"].endswith("big"))
    assert big["attributes"]["_truncated"] is True
    assert big["attributes"]["_original_bytes"] > 4096


# ---- 4. lines 261-262: device found (success path) ----
@pytest.mark.asyncio
async def test_device_registry_success(hass, fake_entry_c):
    from homeassistant.helpers import device_registry as dr
    reg = dr.async_get(hass)
    reg.async_get_or_create(
        config_entry_id=fake_entry_c.entry_id,
        identifiers={("daikin_cycle_ml", "test_dev_c")},
        name="Test Device",
        model="EPRA12",
        sw_version="1.0",
    )
    out = _device_registry(hass, fake_entry_c)
    assert "missing" not in out
    assert out["model"] == "EPRA12"
    assert out["sw_version"] == "1.0"


# ---- 5. lines 289-290: bad run_start_ts -> except pass ----
def test_detector_snapshot_bad_run_start_ts():
    det = MagicMock(spec=[])
    det._state = "RUNNING"
    det._run_start_ts = "not-a-number"
    coord = MagicMock()
    coord.detector = det
    out = _detector_snapshot(coord)
    assert out["state"] == "RUNNING"
    assert "run_duration_s" not in out


# ---- 6. line 292: empty out -> no_known_attrs ----
def test_detector_snapshot_no_known_attrs():
    det = MagicMock(spec=[])
    coord = MagicMock()
    coord.detector = det
    out = _detector_snapshot(coord)
    assert out["missing"] is True
    assert out["reason"] == "no_known_attrs"


# ---- 7. lines 383-384: list(t) raises ----
def test_detector_transitions_raises():
    class Bad:
        def __iter__(self):
            raise RuntimeError("boom")
    coord = MagicMock()
    coord._transitions = Bad()
    assert _detector_transitions(coord) == []


# ---- 8. lines 395-400: actual issues present ----
@pytest.mark.asyncio
async def test_repairs_snapshot_with_issues(hass):
    from homeassistant.helpers import issue_registry as ir
    from custom_components.daikin_cycle_ml.const import DOMAIN
    ir.async_create_issue(
        hass, DOMAIN, "test_issue_1",
        is_fixable=False, severity=ir.IssueSeverity.WARNING,
        translation_key="test_issue_1",
    )
    out = _repairs_snapshot(hass)
    assert out["count"] >= 1
    found = next(
        (i for i in out["active"] if i["issue_id"] == "test_issue_1"), None
    )
    assert found is not None
    assert "severity" in found
    assert "is_fixable" in found


# ---- 9. lines 407-408: ir.async_get raises -> error path ----
@pytest.mark.asyncio
async def test_repairs_snapshot_exception(hass):
    from homeassistant.helpers import issue_registry as ir
    with _patch.object(ir, "async_get", side_effect=RuntimeError("boom")):
        out = _repairs_snapshot(hass)
    assert out["active"] == []
    assert out["count"] == 0
    assert out.get("error") is True


# ---- sanity: end-to-end full diagnostics still valid ----
@pytest.mark.asyncio
async def test_full_diagnostics_still_calls_new_helpers(hass, fake_entry_c):
    """Integration check: all v1.22.4 helpers are wired in the dump."""
    from custom_components.daikin_cycle_ml.diagnostics import (
        async_get_config_entry_diagnostics,
    )
    coord = MagicMock()
    coord.source_entity = "sensor.althermasensors"
    coord._source_resolution = {}
    coord._last_alert_sent = {}
    coord._defrost_count_today = 0
    coord._defrost_start_ts = None
    coord._defrost_duration_s = None
    coord._last_defrost_ts = None
    coord._buh_step = 0
    coord._db_integrity_ok = True
    coord._db_retention_stale = {}
    coord._tick_count = 0
    coord._tick_durations_ms = []
    coord._last_tick_duration_ms = 0.0
    coord._tick_duration_max_ms = 0.0
    coord._uptime_start_monotonic = 0.0
    coord._last_exception = None
    coord._last_exception_ts = None
    coord._last_exception_traceback = None
    coord._samples_last_24h = 0
    coord._samples_expected_24h = 0
    coord._gap_count_24h = 0
    coord._largest_gap_s = 0.0
    coord._last_gap_s = None
    coord._duplicate_ts_count = 0
    coord._non_numeric_attrs = []
    coord._null_attrs_last_tick = []
    coord._transitions = []
    coord.detector = None
    coord.store = MagicMock()
    coord.store.count.return_value = 0
    coord.store.counters_snapshot.return_value = {}
    coord.store.last_cycle.return_value = None
    coord.baseline = None
    coord.adaptive = None
    coord._kmeans_centroids = []
    coord._cluster_labels = {}
    coord._kmeans_stale = {}
    coord._stooklijn_cache = {}
    coord._cop_today_cache = {}
    coord.db = None
    coord.data = MagicMock()
    coord.data.attrs = {}
    coord.data.state = "running"
    coord.data.mode = "heating"
    coord.data.missing_attrs = []
    coord.data.is_hybrid = False
    coord.data.hybrid_mode = ""
    coord.dhw_present = True
    coord._dhw_present_source = "tier1_attrs"
    coord._dhw_present_resolved = True
    fake_entry_c.runtime_data = coord
    out = await async_get_config_entry_diagnostics(hass, fake_entry_c)
    for key in (
        "meta", "source", "entry", "coordinator", "detector", "features",
        "alerts", "bivalent", "defrost", "buh", "entities", "device",
        "runtime", "sampling", "coordinator_timing", "transitions", "repairs",
        "database", "store", "baseline", "adaptive", "clusters", "cop_analysis",
    ):
        assert key in out, f"missing section: {key}"


# ---- 10. line 261->260: device loop iterates, no match ----
@pytest.mark.asyncio
async def test_device_registry_no_match(hass, fake_entry_c):
    """Branch 261->260: device exists but its config_entries doesn't
    include our entry_id -> if-False, loop back to line 260, exit."""
    from homeassistant.helpers import device_registry as dr
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    other = MockConfigEntry(
        domain="daikin_cycle_ml", entry_id="other_dev_e", title="Other"
    )
    other.add_to_hass(hass)
    reg = dr.async_get(hass)
    reg.async_get_or_create(
        config_entry_id="other_dev_e",
        identifiers={("daikin_cycle_ml", "dev_other")},
        name="Other Device",
    )
    out = _device_registry(hass, fake_entry_c)
    assert out["missing"] is True
    assert out["reason"] == "no_device_for_entry"


# ---- 11 + 12. line 398 + 399->394: non-tuple key + non-DOMAIN dom ----
def test_repairs_snapshot_non_tuple_key(hass):
    """Branches 398 + 399->394: issue key is not a tuple -> dom=None ->
    dom != DOMAIN -> next iteration / loop end."""
    from homeassistant.helpers import issue_registry as ir
    fake_reg = MagicMock()
    fake_issue = MagicMock()
    fake_issue.severity = "warning"
    fake_issue.is_fixable = False
    fake_issue.translation_key = None
    fake_reg.issues = {"not_a_tuple_key": fake_issue}
    with _patch.object(ir, "async_get", return_value=fake_reg):
        out = _repairs_snapshot(hass)
    assert out["count"] == 0
    assert out["active"] == []
