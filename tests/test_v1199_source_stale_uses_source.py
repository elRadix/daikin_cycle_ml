"""v1.19.9: source_stale must check the SOURCE entity, not our tick.

Real prod-1 2026-11-05: alerts at 09:15, 10:16, 11:18 (61-62 min apart)
while source intervals were 22-33s throughout. Root cause: a long-running
tick (ML pipeline / rollup / datasheet refresh) causes
`now - last_success_ts > 120s` at dispatch time, firing a critical alert
despite the source being healthy.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from custom_components.daikin_cycle_ml.binary_sensor import _is_source_stale


def _mock_hass_with_source(updated_ts: float) -> MagicMock:
    hass = MagicMock()
    st = MagicMock()
    st.last_updated = datetime.fromtimestamp(updated_ts, tz=timezone.utc)
    hass.states.get.return_value = st
    return hass


def test_source_fresh_tick_stale_no_alert():
    """Source updated 10s ago, tick is 150s stale -> NO alert."""
    now = time.time()
    snap = SimpleNamespace(last_success_ts=now - 150)
    c = SimpleNamespace(
        hass=_mock_hass_with_source(now - 10),
        source_entity="sensor.althermasensors",
        options={},
    )
    assert _is_source_stale(snap, c) is False


def test_source_really_stale_fires():
    """Source updated 200s ago -> alert (real outage)."""
    now = time.time()
    snap = SimpleNamespace(last_success_ts=now - 10)  # tick fresh
    c = SimpleNamespace(
        hass=_mock_hass_with_source(now - 200),
        source_entity="sensor.althermasensors",
        options={},
    )
    assert _is_source_stale(snap, c) is True


def test_fallback_to_tick_when_hass_missing():
    """Unit tests without hass: fall back to tick-based check."""
    now = time.time()
    snap = SimpleNamespace(last_success_ts=now - 150)
    c = SimpleNamespace(hass=None, source_entity="sensor.x", options={})
    assert _is_source_stale(snap, c) is True


def test_fallback_when_entity_missing():
    """Source entity not in hass.states -> fall back to tick check."""
    now = time.time()
    hass = MagicMock()
    hass.states.get.return_value = None
    snap = SimpleNamespace(last_success_ts=now - 150)
    c = SimpleNamespace(
        hass=hass, source_entity="sensor.missing", options={}
    )
    assert _is_source_stale(snap, c) is True


def test_bootstrap_last_success_ts_zero():
    """Pre-first-tick: no alert (existing guard preserved)."""
    snap = SimpleNamespace(last_success_ts=0.0)
    c = SimpleNamespace(hass=None, source_entity="sensor.x", options={})
    assert _is_source_stale(snap, c) is False

def test_source_with_broken_last_updated_falls_back():
    """Malformed last_updated -> except branch -> tick fallback."""
    now = time.time()
    hass = MagicMock()
    st = MagicMock()
    st.last_updated = "not-a-datetime"  # .timestamp() raises AttributeError
    hass.states.get.return_value = st
    snap = SimpleNamespace(last_success_ts=now - 150)
    c = SimpleNamespace(
        hass=hass, source_entity="sensor.x", options={}
    )
    # tick stale + broken source -> fallback fires alert
    assert _is_source_stale(snap, c) is True

def test_broken_last_success_ts_coerced_to_zero():
    """Malformed last_success_ts -> except branch -> no alert (bootstrap)."""
    hass = MagicMock()
    hass.states.get.return_value = None  # fallback to tick anyway
    snap = SimpleNamespace(last_success_ts="bad-string")
    c = SimpleNamespace(
        hass=hass, source_entity="sensor.x", options={}
    )
    # Coerced to 0.0 -> treated as bootstrap -> no alert
    assert _is_source_stale(snap, c) is False
