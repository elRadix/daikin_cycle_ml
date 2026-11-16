"""Bug #7: source_stale must use last_reported, not last_updated.

Prod-1 2026-11-16 22:25:
  source.last_updated = 462s ago (stable weather, value unchanged)
  source.last_reported = should be ~30s (MQTT publishes every tick)
  coordinator.last_success_ts = 0.02s ago
  sensor.source_health = healthy
  binary_sensor.source_stale = "on"  <- WRONG

SOURCE_STALE_FACTOR=4.0 × UPDATE_INTERVAL_SECONDS=30 -> thr=120s
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from custom_components.daikin_cycle_ml.binary_sensor import (
    SOURCE_STALE_FACTOR,
    _is_source_stale,
)
from custom_components.daikin_cycle_ml.const import UPDATE_INTERVAL_SECONDS
from custom_components.daikin_cycle_ml.sensor import _attrs_source_health


def _snap(last_success_ts, last_sample_ts=None):
    return SimpleNamespace(
        last_success_ts=last_success_ts,
        last_sample_ts=last_sample_ts if last_sample_ts is not None else last_success_ts,
        errors_total=0,
        missing_attrs=[],
    )


def _mock_source(updated_ts, reported_ts=None):
    hass = MagicMock()
    st = MagicMock()
    st.last_updated = datetime.fromtimestamp(updated_ts, tz=UTC)
    if reported_ts is not None:
        st.last_reported = datetime.fromtimestamp(reported_ts, tz=UTC)
    else:
        del st.last_reported
    hass.states.get.return_value = st
    return hass


def _ctx(updated_ts, reported_ts=None, hass=True):
    if not hass:
        return SimpleNamespace(hass=None, source_entity=None, options={})
    return SimpleNamespace(
        hass=_mock_source(updated_ts, reported_ts),
        source_entity="sensor.x",
        options={},
    )


def _now(ts):
    return patch(
        "custom_components.daikin_cycle_ml.binary_sensor._now",
        return_value=ts,
    )


def test_factor_is_4x():
    assert SOURCE_STALE_FACTOR == 4.0
    assert UPDATE_INTERVAL_SECONDS == 30


def test_fresh_source_not_stale():
    with _now(1000.0):
        assert _is_source_stale(_snap(1000.0), _ctx(990.0)) is False


def test_slow_tick_fresh_source_not_stale():
    """v1.19.9 regression: slow coordinator tick must not trigger."""
    with _now(1000.0):
        assert _is_source_stale(_snap(850.0), _ctx(990.0)) is False


def test_really_stale_source_fires():
    with _now(1000.0):
        assert _is_source_stale(_snap(990.0), _ctx(800.0)) is True


def test_prod_case_stable_value_fresh_publish():
    """Prod-1: last_updated 462s, last_reported 30s -> NOT stale."""
    with _now(1000.0):
        c = _ctx(updated_ts=538.0, reported_ts=970.0)
        assert _is_source_stale(_snap(999.98), c) is False


def test_old_ha_fallback_to_last_updated():
    """No last_reported (HA <2023.9) -> use last_updated."""
    with _now(1000.0):
        c = _ctx(updated_ts=800.0, reported_ts=None)
        assert _is_source_stale(_snap(990.0), c) is True


def test_no_hass_falls_back_to_tick():
    with _now(1000.0):
        assert _is_source_stale(_snap(850.0), _ctx(0, hass=False)) is True
        assert _is_source_stale(_snap(990.0), _ctx(0, hass=False)) is False


def test_zero_ts_returns_false():
    with _now(1000.0):
        assert _is_source_stale(_snap(0.0), _ctx(0, hass=False)) is False


def test_source_health_sensor_unchanged():
    """sensor.source_health = 'coordinator poll ok' (different semantic)."""
    with patch(
        "custom_components.daikin_cycle_ml.sensor._now",
        return_value=1000.0,
    ):
        attrs = _attrs_source_health(_snap(999.98), None)
    assert attrs["is_stale"] is False


def test_zero_ts_with_hass_present():
    """Zero last_success_ts -> defensive False even with hass."""
    with _now(1000.0):
        assert _is_source_stale(_snap(0.0), _ctx(500.0)) is False
