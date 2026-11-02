"""Whole-chain reproduction tests for Issue #246: short_run on transients.

The bug has TWO locations in the pipeline:

  1. `binary_sensor._is_short_run(snap, coord)` — computes the ENTITY state
     shown in the dashboard. Missing `is_transient` guard.

  2. `coordinator._alert_binary_states(snap)` — computes the DICT passed to
     `evaluate_alerts()`. This is what triggers Telegram notifications.
     Missing the SAME `is_transient` guard.

Because both paths return True for a transient cycle, evaluate_alerts sees
`short_run=True` and — with a 30-min dedup window — re-fires every half hour
until a new cycle closes. One transient cycle → up to 8 notifications over
4 hours.

This file contains:
  - 2 REPRO tests (desired behavior — FAIL on v1.19.4, PASS on v1.19.5)
  - 2 GUARD tests (current correct behavior — PASS on both versions)
"""
from types import MethodType
from unittest.mock import MagicMock

from custom_components.daikin_cycle_ml.binary_sensor import _is_short_run
from custom_components.daikin_cycle_ml.coordinator import DaikinCycleMLCoordinator


def _mk_coord(last_cycle):
    """Coordinator stub with realistic alert-state dependencies."""
    c = MagicMock()
    c.options = {
        "short_run_threshold_min": 20,
        "short_off_threshold_min": 5,
        "pendulum_cycles_per_hour": 4,
        "pendulum_cycles_per_day": 40,
    }
    c._effective_threshold = lambda k, d: c.options.get(k, d)
    c.store = MagicMock()
    c.store.last_cycle = MagicMock(return_value=last_cycle)
    c.store.cycles_in_window = MagicMock(return_value=0)
    c.store.cycles_in_window_mode = MagicMock(return_value=0)
    c.store.non_transient_today = MagicMock(return_value=[])
    c._alert_binary_states = MethodType(
        DaikinCycleMLCoordinator._alert_binary_states, c
    )
    return c


def _mk_snap():
    s = MagicMock()
    s.mode = "heating"
    s.anomaly = None
    return s


# ═══════════════════════════════════════════════════════════════
# REPRODUCTION TESTS — will FAIL on v1.19.4, PASS on v1.19.5
# ═══════════════════════════════════════════════════════════════

def test_repro_entity_short_run_skips_transient():
    """Chain step 1 — entity state. Transient cycle must NOT show short_run=on."""
    c = _mk_coord({
        "mode": "heating",
        "duration_s": 60,
        "is_transient": 1,
        "dT_max": 0.6,
    })
    result = _is_short_run(_mk_snap(), c)
    assert result is False, (
        f"BUG #246: transient cycle (is_transient=1, 60s) returned "
        f"short_run={result}. Entity shows 'on' in dashboard. "
        f"Missing `if last.get('is_transient'): return False` guard."
    )


def test_repro_alert_state_short_run_skips_transient():
    """Chain step 2 — alert input. Transient cycle must NOT appear in states dict.

    This is what evaluate_alerts() consumes. If short_run=True here,
    the alert engine fires and re-fires on dedup expiry.
    """
    c = _mk_coord({
        "mode": "heating",
        "duration_s": 60,
        "is_transient": 1,
        "off_s": 900,
    })
    states = c._alert_binary_states(_mk_snap())
    assert states["short_run"] is False, (
        f"BUG #246: transient cycle set alert-state short_run="
        f"{states['short_run']}. evaluate_alerts() will emit + re-fire "
        f"every 30 min (dedup window) until next cycle closes."
    )


# ═══════════════════════════════════════════════════════════════
# GUARD TESTS — regression guards, PASS on both v1.19.4 and v1.19.5
# ═══════════════════════════════════════════════════════════════

def test_guard_entity_short_run_fires_real_short():
    """Real short cycle (5 min, is_transient=0) MUST still fire."""
    c = _mk_coord({
        "mode": "heating",
        "duration_s": 300,
        "is_transient": 0,
        "dT_max": 3.2,
    })
    assert _is_short_run(_mk_snap(), c) is True


def test_guard_alert_state_short_run_fires_real_short():
    """Same for alert-state path."""
    c = _mk_coord({
        "mode": "heating",
        "duration_s": 300,
        "is_transient": 0,
        "off_s": 900,
    })
    states = c._alert_binary_states(_mk_snap())
    assert states["short_run"] is True
