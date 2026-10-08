"""v1.9.0 PR C — shared filter chain for cop_low + stooklijn_advies.

Covers ALERTS_V2.md sections 4.4 and 4.5.
Refs #66.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.daikin_cycle_ml import const
from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator
from custom_components.daikin_cycle_ml.engine import notification_engine as ne
from custom_components.daikin_cycle_ml.engine.notification_engine import (
    passes_filters,
)


def _bare(options=None):
    c = DaikinCycleMLCoordinator.__new__(DaikinCycleMLCoordinator)
    c.options = dict(options or {})
    c.hass = MagicMock()
    c.hass.services = MagicMock()
    c.hass.services.async_call = AsyncMock()
    c._last_alert_sent = {}
    c._notify_fail_streak = 0
    c._notify_fail_target = ""
    c._emit_alert = AsyncMock()
    return c


# ============================================================
# passes_filters helper
# ============================================================

def test_passes_filters_group_disabled_blocks():
    opts = {"alert_group_cop_stooklijn": False}
    assert passes_filters("cop_low", "warning", opts, now=1e9) is False
    assert passes_filters("stooklijn_advies", "warning", opts, now=1e9) is False


def test_passes_filters_quiet_hours_blocks_non_critical(monkeypatch):
    monkeypatch.setattr(ne, "_in_quiet_hours", lambda *a, **k: True)
    opts = {"quiet_hours_enabled": True}
    assert passes_filters("cop_low", "warning", opts, now=1e9) is False


def test_passes_filters_quiet_hours_allows_critical(monkeypatch):
    monkeypatch.setattr(ne, "_in_quiet_hours", lambda *a, **k: True)
    opts = {"quiet_hours_enabled": True}
    assert passes_filters("cop_low", "critical", opts, now=1e9) is True


def test_passes_filters_quiet_disabled_allows():
    opts = {"quiet_hours_enabled": False}
    assert passes_filters("cop_low", "warning", opts, now=1e9) is True


# ============================================================
# 4.4 — standalone emitters respect group + quiet
# ============================================================

def test_maybe_notify_cop_low_group_disabled_blocks_emit():
    c = _bare(options={"alert_group_cop_stooklijn": False})
    asyncio.run(c._maybe_notify_cop_low(1e6, {"cop": 2.0, "samples_today": 10}))
    c._emit_alert.assert_not_awaited()
    assert "cop_low" not in c._last_alert_sent


def test_maybe_notify_cop_low_quiet_hours_blocks_emit(monkeypatch):
    monkeypatch.setattr(ne, "_in_quiet_hours", lambda *a, **k: True)
    c = _bare(options={"quiet_hours_enabled": True})
    asyncio.run(c._maybe_notify_cop_low(1e6, {"cop": 2.0, "samples_today": 10}))
    c._emit_alert.assert_not_awaited()


def test_maybe_notify_stooklijn_group_disabled_blocks_emit():
    c = _bare(options={"alert_group_cop_stooklijn": False})
    asyncio.run(c._maybe_notify_stooklijn(1e6, {
        "state": "lower_lwt", "betrouwbaarheid": 0.85,
        "besparing_cop_pct": 8.0, "comfort_impact": -0.3,
    }))
    c._emit_alert.assert_not_awaited()


def test_maybe_notify_stooklijn_quiet_hours_blocks_emit(monkeypatch):
    monkeypatch.setattr(ne, "_in_quiet_hours", lambda *a, **k: True)
    c = _bare(options={"quiet_hours_enabled": True})
    asyncio.run(c._maybe_notify_stooklijn(1e6, {
        "state": "lower_lwt", "betrouwbaarheid": 0.85,
        "besparing_cop_pct": 8.0, "comfort_impact": -0.3,
    }))
    c._emit_alert.assert_not_awaited()


# ============================================================
# 4.5 — threshold single-source-of-truth
# ============================================================

def test_threshold_constants_defined():
    assert const.COP_LOW_THRESHOLD == 2.5
    assert const.COP_LOW_MIN_SAMPLES == 3
    assert const.STOOKLIJN_MIN_CONFIDENCE == 0.7
    assert const.STOOKLIJN_MIN_SAVINGS_PCT == 5.0
    assert const.TEST_ALERT_DELTA == 0.1


def test_cop_low_threshold_boundary():
    c = _bare()
    asyncio.run(c._maybe_notify_cop_low(1e6, {"cop": 2.5, "samples_today": 10}))
    c._emit_alert.assert_not_awaited()


def test_cop_low_min_samples_boundary():
    c = _bare()
    asyncio.run(c._maybe_notify_cop_low(1e6, {"cop": 2.0, "samples_today": 2}))
    c._emit_alert.assert_not_awaited()


def test_stooklijn_confidence_boundary():
    # Just-below threshold: blocked
    c = _bare()
    asyncio.run(c._maybe_notify_stooklijn(1e6, {
        "state": "lower_lwt", "betrouwbaarheid": 0.69,
        "besparing_cop_pct": 8.0, "comfort_impact": -0.3,
    }))
    c._emit_alert.assert_not_awaited()

    # At threshold (>= inclusive): emits
    c2 = _bare()
    asyncio.run(c2._maybe_notify_stooklijn(1e6, {
        "state": "lower_lwt", "betrouwbaarheid": 0.7,
        "besparing_cop_pct": 8.0, "comfort_impact": -0.3,
    }))
    c2._emit_alert.assert_awaited()


def test_stooklijn_savings_boundary():
    # Just-below threshold: blocked
    c = _bare()
    asyncio.run(c._maybe_notify_stooklijn(1e6, {
        "state": "lower_lwt", "betrouwbaarheid": 0.85,
        "besparing_cop_pct": 4.99, "comfort_impact": -0.3,
    }))
    c._emit_alert.assert_not_awaited()

    # At threshold (>= inclusive): emits
    c2 = _bare()
    asyncio.run(c2._maybe_notify_stooklijn(1e6, {
        "state": "lower_lwt", "betrouwbaarheid": 0.85,
        "besparing_cop_pct": 5.0, "comfort_impact": -0.3,
    }))
    c2._emit_alert.assert_awaited()


# ============================================================
# Language propagation to both emitters
# ============================================================

def test_maybe_notify_cop_low_renders_in_dutch():
    c = _bare(options={"notification_language": "nl"})
    asyncio.run(c._maybe_notify_cop_low(1e6, {"cop": 2.0, "samples_today": 10}))
    msg = c._emit_alert.await_args.args[0].message
    assert "Dag-COP laag" in msg


def test_maybe_notify_stooklijn_renders_in_dutch():
    c = _bare(options={"notification_language": "nl"})
    asyncio.run(c._maybe_notify_stooklijn(1e6, {
        "state": "lower_lwt", "betrouwbaarheid": 0.85,
        "besparing_cop_pct": 8.0, "comfort_impact": -0.3,
    }))
    msg = c._emit_alert.await_args.args[0].message
    assert "Stooklijn advies" in msg  # NL-specific (EN renders "Stooklijn advice")


# ============================================================
# Test-emitter uses shared delta
# ============================================================

def test_test_emitter_uses_test_alert_delta():
    c = _bare()
    out = asyncio.run(c.async_emit_test_alert("cop_low"))
    expected = f"{const.COP_LOW_THRESHOLD - const.TEST_ALERT_DELTA:.2f}"
    assert expected in out


# ============================================================
# Regression — test-all still emits both (Plan-B gate)
# ============================================================

def test_emit_all_still_emits_both_alert_types():
    c = _bare()
    c.data = MagicMock()
    c._build_alert_context = MagicMock(return_value={})
    c._setpoint_history = []
    out = asyncio.run(c._emit_all_test_alerts(ignore_filters=True))
    assert "=== cop_low ===" in out
    assert "=== stooklijn_advies ===" in out
