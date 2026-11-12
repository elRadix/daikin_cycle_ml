"""v1.22.4 diagnostics v2 — new sections + value-level redaction."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, PropertyMock

import pytest

from custom_components.daikin_cycle_ml.diagnostics import (
    _alerts_snapshot,
    _buh_snapshot,
    _defrost_snapshot,
    _detector_snapshot,
    _device_registry,
    _entities_registry,
    _features_snapshot,
    _meta_envelope,
    _redact_strings_recursive,
    _source_full,
    _state_map,
    async_get_config_entry_diagnostics,
)


def _fake_coord(**kw):
    c = MagicMock()
    c.source_entity = kw.get("source_entity", "sensor.althermasensors")
    c._source_resolution = kw.get("source_resolution", {})
    c._last_alert_sent = kw.get("last_alert_sent", {})
    c._defrost_count_today = kw.get("defrost_count", 0)
    c._defrost_start_ts = kw.get("defrost_start", None)
    c._defrost_duration_s = kw.get("defrost_dur", None)
    c._last_defrost_ts = kw.get("last_defrost", None)
    c._buh_step = kw.get("buh_step", 0)
    c._db_integrity_ok = kw.get("integrity", True)
    c._db_retention_stale = kw.get("retention", {})
    c.detector = kw.get("detector", None)
    c.store = kw.get("store", None)
    c.data = kw.get("data", MagicMock())
    c.data.attrs = kw.get("attrs", {})
    c.data.state = "running"
    c.data.mode = "heating"
    c.data.missing_attrs = []
    c.data.is_hybrid = False
    c.data.hybrid_mode = ""
    c.dhw_present = True
    c._dhw_present_source = "tier1_attrs"
    c._dhw_present_resolved = True
    c.baseline = None
    c.adaptive = None
    c._kmeans_centroids = []
    c._cluster_labels = {}
    c._kmeans_stale = {}
    c._stooklijn_cache = {}
    c._cop_today_cache = {}
    c.db = None
    return c


# ---------- meta ----------
def test_meta_envelope_shape():
    m = _meta_envelope(_fake_coord())
    assert m["diagnostics_format"] == 2
    assert "notify_service" in m["redaction_keys"]
    assert "generated_at" in m
    assert m["coordinator_missing"] is False


def test_meta_envelope_coordinator_missing():
    assert _meta_envelope(None)["coordinator_missing"] is True


# ---------- source ----------
@pytest.mark.asyncio
async def test_source_full_available(hass):
    attrs = {"Operation Mode": "Heating", "3way valve": True, "R2T": 42.0}
    hass.states.async_set("sensor.althermasensors", "on", attrs)
    coord = _fake_coord()
    out = _source_full(hass, coord)
    assert out["attribute_count"] == 3
    assert out["attributes_full"]["3way valve"] is True
    assert out["available"] is True
    assert out["url_redactions"] == 0


@pytest.mark.asyncio
async def test_source_full_missing(hass):
    coord = _fake_coord(source_entity="sensor.does_not_exist")
    out = _source_full(hass, coord)
    assert out["available"] is False
    assert out["reason"] == "state_missing"


@pytest.mark.asyncio
async def test_source_full_url_redaction(hass):
    attrs = {"Firmware URL": "https://admin:secret@fw.local/v1"}
    hass.states.async_set("sensor.althermasensors", "on", attrs)
    out = _source_full(hass, _fake_coord())
    assert "secret" not in json.dumps(out)
    assert "https://**REDACTED**@fw.local/v1" in out["attributes_full"]["Firmware URL"]
    assert out["url_redactions"] == 1


@pytest.mark.asyncio
async def test_source_full_no_source_configured(hass):
    coord = _fake_coord(source_entity=None)
    out = _source_full(hass, coord)
    assert out["reason"] == "no_source"


# ---------- entities / device ----------
@pytest.mark.asyncio
async def test_entities_registry_empty(hass, fake_entry):
    out = _entities_registry(hass, fake_entry)
    assert out["registered"] == 0
    assert out["entries"] == []


@pytest.mark.asyncio
async def test_entities_registry_lists_entities(hass, fake_entry):
    from homeassistant.helpers import entity_registry as er
    reg = er.async_get(hass)
    reg.async_get_or_create(
        "sensor", "daikin_cycle_ml", "u1",
        suggested_object_id="daikin_cycle_ml_state",
        config_entry=fake_entry,
    )
    hass.states.async_set("sensor.daikin_cycle_ml_state", "running", {"k": 1})
    out = _entities_registry(hass, fake_entry)
    assert out["registered"] >= 1
    entry = next(e for e in out["entries"] if e["entity_id"].endswith("state"))
    assert entry["state"] == "running"
    assert entry["attributes"]["k"] == 1


@pytest.mark.asyncio
async def test_device_registry_missing(hass, fake_entry):
    out = _device_registry(hass, fake_entry)
    assert out["missing"] is True


# ---------- detector / features / alerts / defrost / buh ----------
def test_detector_snapshot_missing():
    assert _detector_snapshot(_fake_coord())["missing"] is True


def test_detector_snapshot_present():
    det = MagicMock(spec=[])
    det._state = "RUNNING"
    det._mode = "heating"
    det._rps_threshold = 3.0
    det._dhw_present = True
    out = _detector_snapshot(_fake_coord(detector=det))
    assert out["state"] == "RUNNING"
    assert out["mode"] == "heating"


def test_features_snapshot_missing():
    assert _features_snapshot(_fake_coord())["missing"] is True


def test_features_snapshot_present():
    store = MagicMock()
    store.last_cycle.return_value = {"id": 42, "feature_vector": [1.0, 2.0]}
    out = _features_snapshot(_fake_coord(store=store))
    assert out["last_cycle_id"] == 42
    assert out["vector"] == [1.0, 2.0]


def test_alerts_snapshot():
    coord = _fake_coord(last_alert_sent={"defrost_excessive": 100.0})
    out = _alerts_snapshot(coord)
    assert out["dispatch_count"] == 1
    assert "defrost_excessive" in out["dispatch_history"]


def test_defrost_snapshot():
    coord = _fake_coord(defrost_count=3, defrost_start=100.0, defrost_dur=300)
    out = _defrost_snapshot(coord)
    assert out["count_today"] == 3
    assert out["start_ts"] == 100.0
    assert out["duration_s"] == 300


def test_buh_snapshot():
    assert _buh_snapshot(_fake_coord(buh_step=2))["step"] == 2


# ---------- state mapping ----------
def test_state_map_known():
    assert _state_map("keep") == "stable"
    assert _state_map("raise") == "raise_lwt"
    assert _state_map("no_data") == "no_data"


def test_state_map_unknown_passthrough():
    assert _state_map("weird") == "weird"


# ---------- redaction ----------
def test_redact_recursive_notify_target():
    d = {"x": "notify.mobile_app_alice_iphone", "y": 1}
    r = _redact_strings_recursive(d)
    assert r["x"] == "notify.**REDACTED**"
    assert r["y"] == 1


def test_redact_recursive_nested():
    d = {"a": {"b": "notify.bob_phone"}, "c": ["notify.alice_tab"]}
    r = _redact_strings_recursive(d)
    assert r["a"]["b"] == "notify.**REDACTED**"
    assert r["c"][0] == "notify.**REDACTED**"


# ---------- integration: coordinator missing ----------
@pytest.mark.asyncio
async def test_full_diag_coordinator_missing(hass, fake_entry):
    fake_entry.runtime_data = None
    out = await async_get_config_entry_diagnostics(hass, fake_entry)
    assert out == {"error": "coordinator_not_ready"}


@pytest.fixture
def fake_entry(hass):
    """Real ConfigEntry registered in hass.config_entries.

    Why not MagicMock(spec=ConfigEntry): HA's entity_registry rejects
    config_entry=<mock> with 'unknown config entry' because it validates
    existence in hass.config_entries before linking the entity.
    """
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    e = MockConfigEntry(
        domain="daikin_cycle_ml",
        entry_id="test_entry",
        title="Test",
        data={"source_sensor": "sensor.althermasensors"},
        options={"notify_service": "notify.mobile_app_alice_iphone"},
    )
    e.add_to_hass(hass)
    return e
