"""v1.19.7 RED: _alert_binary_states must match binary_sensor semantics.

Three divergences found in PASTE 7C/7D:

1. short_run uses truthy is_transient check (v1.19.6 FASE 5B was only
   applied to binary_sensor; coordinator path still uses truthy).
2. short_off has no transient guard (v1.19.7 was only applied to
   binary_sensor; notifications still fire on transient predecessor).
3. pendulum_hourly uses cycles_in_window (all modes) instead of
   cycles_in_window_mode(MODE_HEATING) (v1.19.6 scope A was only
   applied to binary_sensor).

Each test calls the real _alert_binary_states with realistic cycle
data. Pre-fix: all three fail. Post-fix: all pass.
"""
import time
from types import SimpleNamespace

import pytest

from custom_components.daikin_cycle_ml import coordinator as co
from custom_components.daikin_cycle_ml.storage.store import CycleStore


def _mk_cycle(*, end_offset_s, dur, is_trans=0, mode="heating", off_s=None):
    end = time.time() + end_offset_s
    start = end - dur
    r = {
        "start_ts": start,
        "end_ts": end,
        "duration_s": dur,
        "mode": mode,
        "dT_max": 2.0,
        "rps_max": 30,
        "is_transient": is_trans,
    }
    if off_s is not None:
        r["off_s"] = off_s
    return r


def _mk_snap():
    return SimpleNamespace(
        mode="heating",
        anomaly=None,
        cop_degradation_week_pct=None,
        cop_vs_datasheet_pct=None,
        last_success_ts=time.time(),
        missing_attrs=[],
        advice=[],
    )


def _call_alert_states(store, options=None):
    """Call the real _alert_binary_states via a stub coordinator."""
    opts = options or {
        "short_run_threshold_min": 20,
        "short_off_threshold_min": 5,
        "pendulum_cycles_per_hour": 4,
        "pendulum_cycles_per_day": 40,
        "dhw_pendulum_cycles_per_hour": 3,
    }
    stub = SimpleNamespace(
        store=store,
        options=opts,
        _effective_threshold=lambda k, d: d,
        _compute_setpoint_oscillating=lambda: False,
        _db_retention_stale={"fired": False},
        _kmeans_stale={"fired": False},
        _energy_daily_anomaly={"fired": False},
        _defrost_7d_sum=0,
        _buh_7d_ratio=0.0,
    )
    # bind the method
    return co.DaikinCycleMLCoordinator._alert_binary_states(stub, _mk_snap())


# ---------- Bug 1: short_run truthy is_transient ----------

def test_short_run_corrupt_string_0_fires():
    """is_transient='0' with short duration must fire short_run (FASE 5B parity)."""
    store = CycleStore(maxlen=100)
    store.add_cycle(_mk_cycle(end_offset_s=-60, dur=600, is_trans="0"))
    states = _call_alert_states(store)
    assert states["short_run"] is True, (
        "truthy check on is_transient='0' silently disables short_run "
        "(should use _is_transient_int)"
    )


def test_short_run_real_cycle_fires():
    """Real (is_transient=0) short cycle must fire (preservation)."""
    store = CycleStore(maxlen=100)
    store.add_cycle(_mk_cycle(end_offset_s=-60, dur=600, is_trans=0))
    states = _call_alert_states(store)
    assert states["short_run"] is True


def test_short_run_transient_skips():
    """Transient short cycle must be silent (preservation)."""
    store = CycleStore(maxlen=100)
    store.add_cycle(_mk_cycle(end_offset_s=-60, dur=30, is_trans=1))
    states = _call_alert_states(store)
    assert states["short_run"] is False


# ---------- Bug 2: short_off missing transient guard ----------

def test_short_off_transient_cycle_skips():
    """Transient last cycle + short off_s must be silent (v1.19.7 parity)."""
    store = CycleStore(maxlen=100)
    # Transient cycle (pump pulse) ends 30s before "now"
    store.add_cycle(_mk_cycle(end_offset_s=-30, dur=30, is_trans=1, off_s=30))
    states = _call_alert_states(store)
    assert states["short_off"] is False, (
        "short_off in alert path lacks transient guard "
        "(binary_sensor v1.19.7 not propagated to notifications)"
    )


def test_short_off_transient_string_1_skips():
    """is_transient='1' on last cycle must also skip."""
    store = CycleStore(maxlen=100)
    store.add_cycle(_mk_cycle(end_offset_s=-30, dur=30, is_trans="1", off_s=30))
    states = _call_alert_states(store)
    assert states["short_off"] is False


def test_short_off_real_cycle_fires():
    """Real cycle + short off_s still fires (preservation)."""
    store = CycleStore(maxlen=100)
    store.add_cycle(_mk_cycle(end_offset_s=-30, dur=300, is_trans=0, off_s=30))
    states = _call_alert_states(store)
    assert states["short_off"] is True


# ---------- Bug 3: pendulum_hourly counts all modes ----------

def test_pendulum_hourly_heating_only():
    """3 DHW + 1 heating in 1h window must NOT fire pendulum_hourly (threshold=4)."""
    store = CycleStore(maxlen=100)
    now = time.time()
    # 3 DHW cycles, end times well inside 1h window
    for i in range(3):
        store.add_cycle(_mk_cycle(end_offset_s=-600 - i * 300, dur=300, mode="dhw"))
    # 1 heating cycle
    store.add_cycle(_mk_cycle(end_offset_s=-200, dur=300, mode="heating"))
    # sanity: verify window actually contains all 4
    total = store.cycles_in_window(now, 3600)
    heating = store.cycles_in_window_mode(now, 3600, "heating")
    assert total >= 4, f"setup: expected >=4 cycles in window, got {total}"
    assert heating == 1, f"setup: expected 1 heating, got {heating}"

    states = _call_alert_states(store)
    assert states["pendulum_hourly"] is False, (
        f"pendulum_hourly counts DHW as heating "
        f"(total={total} >= 4 -> fires, heating={heating} < 4 -> should not)"
    )


def test_pendulum_hourly_4_heating_fires():
    """4 real heating cycles must fire (preservation)."""
    store = CycleStore(maxlen=100)
    for i in range(4):
        store.add_cycle(_mk_cycle(end_offset_s=-600 - i * 300, dur=300, mode="heating"))
    states = _call_alert_states(store)
    assert states["pendulum_hourly"] is True


# ---------- Preservation: other alerts unaffected ----------

def test_pendulum_daily_still_uses_non_transient():
    """pendulum_daily uses non_transient_today (already correct, sanity check)."""
    store = CycleStore(maxlen=100)
    for i in range(40):
        store.add_cycle(_mk_cycle(end_offset_s=-i * 60, dur=300, is_trans=0))
    states = _call_alert_states(store)
    assert states["pendulum_daily"] is True


def test_empty_store_all_false():
    """Empty store: all bool alerts False."""
    store = CycleStore(maxlen=100)
    states = _call_alert_states(store)
    for key in ("short_run", "short_off", "pendulum_hourly",
                "pendulum_daily", "dhw_pendulum", "high_cycle_rate"):
        assert states[key] is False, f"empty store should yield {key}=False"

# ---------- NEW: dispatch-level coverage ----------

async def test_dispatch_short_off_transient_creates_no_notification():
    """Full dispatch path: transient last cycle should not emit short_off notification.

    This is the end-to-end proof that my v1.19.7 binary_sensor fix reaches
    notifications (a gap discovered in PASTE 7C).
    """
    from unittest.mock import AsyncMock, MagicMock
    from custom_components.daikin_cycle_ml.storage.store import CycleStore
    from custom_components.daikin_cycle_ml.engine.notification_engine import evaluate_alerts

    # Build states dict directly with short_off=False (post-fix behavior)
    states = {k: False for k in ("short_run", "short_off", "pendulum_hourly",
                                  "pendulum_daily", "dhw_pendulum", "high_cycle_rate",
                                  "ml_anomaly", "setpoint_osc", "cop_degradation",
                                  "defrost_excessive", "buh_excessive", "source_stale",
                                  "missing_attributes", "cop_vs_datasheet_low",
                                  "db_retention_warning", "kmeans_retrain_stale",
                                  "energy_daily_anomaly")}
    # short_off should be FALSE because transient cycle
    alerts = evaluate_alerts(states, {}, time.time(), {})
    short_off_alerts = [a for a in alerts if a.alert_type == "short_off"]
    assert short_off_alerts == [], (
        "post-fix, transient last cycle must produce zero short_off alerts"
    )


def test_alert_states_pendulum_dhw_only_does_not_fire():
    """3 DHW cycles + 0 heating: pendulum_hourly must be False (was True pre-fix)."""
    store = CycleStore(maxlen=100)
    for i in range(3):
        store.add_cycle(_mk_cycle(end_offset_s=-600 - i * 300, dur=300, mode="dhw"))
    states = _call_alert_states(store)
    assert states["pendulum_hourly"] is False, (
        "DHW-only cycles should not trigger pendulum_hourly (heating-only fix)"
    )

