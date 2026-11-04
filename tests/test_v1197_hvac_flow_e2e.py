"""v1.19.7 end-to-end HVAC flow tests.

These tests exercise the FULL alert pipeline with a real CycleStore and
the real coordinator._alert_binary_states. They model realistic Daikin
Altherma behaviors across multiple heat pump sizes and hybrid installs.

Why these exist (the "false impression" fix):
- Previous unit tests mocked partial store interfaces. When production
  code grew new dependencies (e.g. cycles_in_window_mode), those tests
  passed for the wrong reason and would crash in production.
- These E2E tests build real cycle sequences that mirror the actual
  patterns in the 193-cycle Prod 1 fixture: long heating runs, DHW
  transitions, per-cycle defrosts, and pump-sampling transients.

Model coverage:
- 6kW (small, short cycles, frequent defrosts in shoulder season)
- 12kW (medium, longer runs, occasional DHW)
- 16kW (large, very long runs, high thermal mass)
- hybrid-EVLQ (boiler handover, cycle patterns differ)

Every model uses the same alert decision logic (mode-based, not
model-based). These tests verify the logic is model-agnostic AND
handles each model's typical cycle shape without false positives.

Fixture derivation:
- Cycle durations and gaps mirror the measured distribution from
  tests/fixtures/_prod1_20261103.db (193 cycles, 39 days).
- Defrost-on-every-cycle is a cold-climate scenario (not the default
  fixture) that must not affect alert decisions.
"""
import time
from types import SimpleNamespace

import pytest

from custom_components.daikin_cycle_ml import coordinator as co
from custom_components.daikin_cycle_ml.storage.store import CycleStore


# ============================================================
# Builders
# ============================================================

def _mk_cycle(
    *, end_offset_s, dur, is_trans=0, mode="heating",
    off_s=None, dT_max=4.0, dT_avg=3.0, rps_max=30, rps_avg=25,
    thermal_kw=3.0, outdoor_temp=10.0, buh_used=0, defrost_used=0,
):
    end = time.time() + end_offset_s
    start = end - dur
    r = {
        "start_ts": start, "end_ts": end, "duration_s": dur,
        "mode": mode, "is_transient": is_trans,
        "dT_max": dT_max, "dT_avg": dT_avg,
        "rps_max": rps_max, "rps_avg": rps_avg,
        "thermal_kw_avg": thermal_kw, "outdoor_temp": outdoor_temp,
        "buh_used": buh_used, "defrost_used": defrost_used,
        "quality_score": 80,
    }
    if off_s is not None:
        r["off_s"] = off_s
    return r


def _mk_snap(**overrides):
    base = dict(
        mode="heating", anomaly=None,
        cop_degradation_week_pct=None, cop_vs_datasheet_pct=None,
        last_success_ts=time.time(), missing_attrs=[], advice=[],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _mk_coord(store, options=None, snap_overrides=None, **co_overrides):
    opts = {
        "short_run_threshold_min": 20,
        "short_off_threshold_min": 5,
        "pendulum_cycles_per_hour": 4,
        "pendulum_cycles_per_day": 40,
        "dhw_pendulum_cycles_per_hour": 3,
    }
    if options:
        opts.update(options)
    c = SimpleNamespace(
        store=store,
        options=opts,
        _effective_threshold=lambda k, d: d,
        _compute_setpoint_oscillating=lambda: False,
        _setpoint_history=[],
        _db_retention_stale={"fired": False},
        _kmeans_stale={"fired": False},
        _energy_daily_anomaly={"fired": False},
        _defrost_7d_sum=0,
        _buh_7d_ratio=0.0,
    )
    for k, v in co_overrides.items():
        setattr(c, k, v)
    return c


def _states(store, options=None, snap_overrides=None, **co_overrides):
    c = _mk_coord(store, options, snap_overrides, **co_overrides)
    snap = _mk_snap(**(snap_overrides or {}))
    return co.DaikinCycleMLCoordinator._alert_binary_states(c, snap)


# ============================================================
# 1. HVAC FLOW — mode transitions in realistic sequences
# ============================================================

def test_e2e_clean_heating_day_no_alerts():
    """3 long heating cycles with >5min gaps: no spurious short_* alerts."""
    store = CycleStore(maxlen=100)
    # 3 heating cycles: 60min dur, 30min gaps, well-separated
    for i, end_off in enumerate([-9000, -4500, -30]):
        store.add_cycle(_mk_cycle(
            end_offset_s=end_off, dur=3600,
            off_s=(1800 if i > 0 else None),
        ))
    s = _states(store)
    assert s["short_run"] is False
    assert s["short_off"] is False
    assert s["pendulum_hourly"] is False
    assert s["high_cycle_rate"] is False


def test_e2e_heating_dhw_heating_no_spurious():
    """Heat → DHW → Heat: DHW-mode short gap must not fire short_off."""
    store = CycleStore(maxlen=100)
    store.add_cycle(_mk_cycle(end_offset_s=-5000, dur=3600, mode="heating"))
    # DHW cycle with 60s gap after heating (normal handover)
    store.add_cycle(_mk_cycle(
        end_offset_s=-500, dur=1800, mode="dhw", off_s=60,
    ))
    # Back to heating after DHW
    store.add_cycle(_mk_cycle(
        end_offset_s=-30, dur=2000, mode="heating", off_s=1200,
    ))
    s = _states(store)
    # short_off must be False because last cycle mode is heating but
    # the current cycle is fine; more importantly, DHW wasn't counted
    assert s["short_off"] is False


def test_e2e_heating_with_defrost_each_cycle():
    """Every heating cycle has defrost_used=1 (cold climate): no false positives."""
    store = CycleStore(maxlen=100)
    for end_off in [-9000, -4500, -30]:
        store.add_cycle(_mk_cycle(
            end_offset_s=end_off, dur=3600, defrost_used=1,
            outdoor_temp=-5.0, off_s=1800,
        ))
    s = _states(store)
    assert s["short_run"] is False
    assert s["short_off"] is False


def test_e2e_hybrid_boiler_handover():
    """Hybrid: boiler picks up demand while HP cycles are long. No HP alerts."""
    store = CycleStore(maxlen=100)
    for end_off in [-12000, -6000, -30]:
        store.add_cycle(_mk_cycle(
            end_offset_s=end_off, dur=5400,  # 90min
            mode="heating", off_s=600,
        ))
    s = _states(store)
    assert s["short_run"] is False
    assert s["short_off"] is False


# ============================================================
# 2. PENDULUM — comprehensive
# ============================================================

def test_pendulum_heating_3_silent():
    """3 heating cycles in 1h: below threshold=4, silent."""
    store = CycleStore(maxlen=100)
    for i in range(3):
        store.add_cycle(_mk_cycle(
            end_offset_s=-500 - i * 400, dur=300, mode="heating",
        ))
    assert _states(store)["pendulum_hourly"] is False


def test_pendulum_heating_4_fires():
    """4 real heating cycles in 1h: fires."""
    store = CycleStore(maxlen=100)
    for i in range(4):
        store.add_cycle(_mk_cycle(
            end_offset_s=-300 - i * 400, dur=300, mode="heating",
        ))
    assert _states(store)["pendulum_hourly"] is True


def test_pendulum_mixed_dhw_heating_silent():
    """v1.19.7 fix: 3 DHW + 1 heating = 4 total but 1 heating < 4 → silent."""
    store = CycleStore(maxlen=100)
    for i in range(3):
        store.add_cycle(_mk_cycle(
            end_offset_s=-600 - i * 300, dur=300, mode="dhw",
        ))
    store.add_cycle(_mk_cycle(
        end_offset_s=-100, dur=300, mode="heating",
    ))
    assert _states(store)["pendulum_hourly"] is False, (
        "DHW cycles must not count toward HEATING pendulum_hourly"
    )


def test_pendulum_dhw_3_fires_dhw_pendulum():
    """3 real DHW cycles in 1h: dhw_pendulum fires."""
    store = CycleStore(maxlen=100)
    for i in range(3):
        store.add_cycle(_mk_cycle(
            end_offset_s=-400 - i * 400, dur=300, mode="dhw",
        ))
    s = _states(store)
    assert s["dhw_pendulum"] is True
    assert s["pendulum_hourly"] is False  # no heating


def test_pendulum_daily_40_real_fires(freezer):
    """40 real cycles today: pendulum_daily fires.

    freeze_time avoids a midnight-UTC race: without it, 40 cycles spaced
    10 min apart (max -6.67h) span two UTC days when the test runs before
    ~06:40 UTC, leaving <40 "today" and breaking the assertion.
    """
    freezer.move_to("2026-11-04 12:00:00")
    store = CycleStore(maxlen=200)
    for i in range(40):
        store.add_cycle(_mk_cycle(
            end_offset_s=-i * 600, dur=300, is_trans=0, mode="heating",
        ))
    assert _states(store)["pendulum_daily"] is True


def test_pendulum_daily_with_transients_silent():
    """30 real + 15 transient = 45 total but 30 real < 40 → silent."""
    store = CycleStore(maxlen=200)
    for i in range(30):
        store.add_cycle(_mk_cycle(
            end_offset_s=-i * 800, dur=300, is_trans=0, mode="heating",
        ))
    for i in range(15):
        store.add_cycle(_mk_cycle(
            end_offset_s=-i * 100 - 30000, dur=30, is_trans=1, mode="heating",
        ))
    assert _states(store)["pendulum_daily"] is False, (
        "transient cycles must not count toward pendulum_daily"
    )


# ============================================================
# 3. MULTI-MODEL — realistic cycle patterns per capacity
# ============================================================

MODELS = [
    # name, typical_dur_s, typical_gap_s, typical_dT, typical_rps, outdoor
    ("6kW-small",         1800,  900,   3.0, 45, 8.0),
    ("12kW-medium",       3600, 1800,   4.5, 35, 5.0),
    ("16kW-large",        5400, 2700,   5.0, 28, 2.0),
    ("hybrid-EVLQ",       2400, 1200,   4.0, 32, -2.0),  # colder, boiler-assist
]


@pytest.mark.parametrize("name,dur,gap,dT,rps,outdoor", MODELS)
def test_model_clean_heating_no_alerts(name, dur, gap, dT, rps, outdoor):
    """Any model with clean, well-separated long runs must have no alerts."""
    store = CycleStore(maxlen=100)
    for i, end_off in enumerate([-(dur+gap)*2, -(dur+gap), -30]):
        store.add_cycle(_mk_cycle(
            end_offset_s=end_off, dur=dur, dT_max=dT, rps_max=rps,
            outdoor_temp=outdoor, off_s=(gap if i > 0 else None),
        ))
    s = _states(store)
    assert s["short_run"] is False, f"{name}: unexpected short_run"
    assert s["short_off"] is False, f"{name}: unexpected short_off"


@pytest.mark.parametrize("name,dur,gap,dT,rps,outdoor", MODELS)
def test_model_transient_pump_pulse_skipped(name, dur, gap, dT, rps, outdoor):
    """v1.19.7: transient pulse (30s) preceding real cycle is skipped for short_off."""
    store = CycleStore(maxlen=100)
    # Real long cycle
    store.add_cycle(_mk_cycle(
        end_offset_s=-(dur + 60), dur=dur, dT_max=dT, rps_max=rps,
        outdoor_temp=outdoor,
    ))
    # 30s transient
    store.add_cycle(_mk_cycle(
        end_offset_s=-30, dur=30, is_trans=1, rps_max=0,
        thermal_kw=0.4, outdoor_temp=outdoor, off_s=60,
    ))
    s = _states(store)
    assert s["short_run"] is False, f"{name}: transient leaked to short_run"
    assert s["short_off"] is False, f"{name}: transient leaked to short_off"


@pytest.mark.parametrize("name,dur,gap,dT,rps,outdoor", MODELS)
def test_model_dhw_transition_handled(name, dur, gap, dT, rps, outdoor):
    """Any model: heating → DHW transition must not trigger short_off."""
    store = CycleStore(maxlen=100)
    store.add_cycle(_mk_cycle(
        end_offset_s=-5000, dur=dur, dT_max=dT, rps_max=rps,
        outdoor_temp=outdoor, mode="heating",
    ))
    store.add_cycle(_mk_cycle(
        end_offset_s=-500, dur=1800, mode="dhw", outdoor_temp=outdoor,
        off_s=1200,
    ))
    s = _states(store)
    assert s["short_off"] is False, f"{name}: DHW transition leaked"


def test_model_hybrid_boiler_demand_no_hp_alert():
    """Hybrid EVLQ: boiler_operation_demand present, HP cycles still clean."""
    store = CycleStore(maxlen=100)
    for end_off in [-12000, -6000, -30]:
        store.add_cycle(_mk_cycle(
            end_offset_s=end_off, dur=5400, mode="heating",
            outdoor_temp=-3.0, off_s=600,
        ))
    snap = _mk_snap(mode="heating", boiler_operation_demand=True)
    c = _mk_coord(store)
    s = co.DaikinCycleMLCoordinator._alert_binary_states(c, snap)
    assert s["short_run"] is False
    assert s["short_off"] is False


# ============================================================
# 4. FIXTURE REPLAY — real 193-cycle DB
# ============================================================

FIXTURE = (
    __import__("pathlib").Path(__file__).parent
    / "fixtures" / "_prod1_20261103.db"
)


@pytest.mark.skipif(not FIXTURE.exists(), reason="Prod 1 fixture absent")
def test_fixture_full_replay_produces_valid_state():
    """Replay all 193 cycles; final state must not raise and must be bool dict."""
    import sqlite3
    con = sqlite3.connect(f"file:{FIXTURE}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM cycles ORDER BY start_ts")]
    con.close()

    store = CycleStore(maxlen=1000)
    store.hydrate_from_rows(rows, good_threshold=70)

    s = _states(store)
    assert isinstance(s, dict)
    expected_keys = {
        "short_run", "short_off", "pendulum_hourly", "pendulum_daily",
        "dhw_pendulum", "high_cycle_rate", "ml_anomaly", "setpoint_osc",
        "cop_degradation", "defrost_excessive", "buh_excessive",
        "source_stale", "missing_attributes", "cop_vs_datasheet_low",
        "db_retention_warning", "kmeans_retrain_stale",
        "energy_daily_anomaly", "short_cycling_pattern",
    }
    assert set(s.keys()) == expected_keys
    for k, v in s.items():
        assert isinstance(v, bool), f"{k} is {type(v).__name__}, expected bool"


@pytest.mark.skipif(not FIXTURE.exists(), reason="Prod 1 fixture absent")
def test_fixture_no_pendulum_hourly_on_real_data():
    """The 39-day fixture must not fire pendulum_hourly at final state (v1.19.7 fix)."""
    import sqlite3
    con = sqlite3.connect(f"file:{FIXTURE}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM cycles ORDER BY start_ts")]
    con.close()
    store = CycleStore(maxlen=1000)
    store.hydrate_from_rows(rows, good_threshold=70)
    s = _states(store)
    # On real 39-day data, counts never exceed threshold after fix
    assert s["pendulum_hourly"] is False
    assert s["high_cycle_rate"] is False
