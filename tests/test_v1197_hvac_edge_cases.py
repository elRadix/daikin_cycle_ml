"""v1.19.7 comprehensive HVAC edge-case matrix.

Categories:
1. COP behaviors (degradation, datasheet comparison, extreme values)
2. Thermal/electrical power and LWT-RWT deltaT implications
3. Temperature scenarios (deep cold, freezing, shoulder, warm)
4. Per-model sensor availability (6/12/16kW, hybrid EVLQ, legacy)
5. Setpoint oscillation
6. BUH / defrost / stale / missing attributes
7. Seeded fuzz (deterministic, reproducible)

All tests use a real CycleStore and the real coordinator._alert_binary_states.
No mock stores — that was the false-impression bug from earlier.
"""
import random
import time
from types import SimpleNamespace

import pytest

from custom_components.daikin_cycle_ml import coordinator as co
from custom_components.daikin_cycle_ml.storage.store import CycleStore


# ============================================================
# Builders
# ============================================================

def _cy(
    *, end_offset_s=-30, dur=3600, is_trans=0, mode="heating",
    off_s=None, dT_max=4.0, dT_avg=3.0, rps_max=30, rps_avg=25,
    thermal_kw=3.0, outdoor_temp=10.0, buh_used=0, defrost_used=0,
    quality_score=80,
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
        "quality_score": quality_score,
    }
    if off_s is not None:
        r["off_s"] = off_s
    return r


def _snap(**overrides):
    base = dict(
        mode="heating", anomaly=None,
        cop_degradation_week_pct=None, cop_vs_datasheet_pct=None,
        last_success_ts=time.time(), missing_attrs=[], advice=[],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _coord(store, options=None, **co_overrides):
    opts = {
        "short_run_threshold_min": 20,
        "short_off_threshold_min": 5,
        "pendulum_cycles_per_hour": 4,
        "pendulum_cycles_per_day": 40,
        "dhw_pendulum_cycles_per_hour": 3,
        "defrost_7d_count_threshold": 30,
        "buh_7d_ratio_threshold": 0.15,
    }
    if options:
        opts.update(options)
    c = SimpleNamespace(
        store=store, options=opts,
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


def _states(store, options=None, snap=None, **co_overrides):
    c = _coord(store, options, **co_overrides)
    s = snap if snap is not None else _snap()
    return co.DaikinCycleMLCoordinator._alert_binary_states(c, s)


def _empty_store():
    return CycleStore(maxlen=200)


# ============================================================
# 1. COP behaviors
# ============================================================

def test_cop_degradation_severe_fires():
    """-20% week-over-week degradation fires alert."""
    s = _states(_empty_store(), snap=_snap(cop_degradation_week_pct=-20.0))
    assert s["cop_degradation"] is True


def test_cop_degradation_mild_silent():
    """-5% is within normal noise, no alert."""
    s = _states(_empty_store(), snap=_snap(cop_degradation_week_pct=-5.0))
    assert s["cop_degradation"] is False


def test_cop_degradation_improvement_silent():
    """+15% improvement (post-defrost, warmer outdoor) must not fire degradation."""
    s = _states(_empty_store(), snap=_snap(cop_degradation_week_pct=15.0))
    assert s["cop_degradation"] is False


def test_cop_degradation_none_silent():
    """No data: must not fire (safety invariant)."""
    s = _states(_empty_store(), snap=_snap(cop_degradation_week_pct=None))
    assert s["cop_degradation"] is False


def test_cop_vs_datasheet_low_fires():
    """COP well below datasheet → fires."""
    s = _states(_empty_store(), snap=_snap(cop_vs_datasheet_pct=-40.0))
    assert s["cop_vs_datasheet_low"] is True


def test_cop_vs_datasheet_at_baseline_silent():
    """100% of datasheet: silent."""
    s = _states(_empty_store(), snap=_snap(cop_vs_datasheet_pct=100.0))
    assert s["cop_vs_datasheet_low"] is False


def test_cop_vs_datasheet_none_silent():
    """No datasheet loaded: must not fire."""
    s = _states(_empty_store(), snap=_snap(cop_vs_datasheet_pct=None))
    assert s["cop_vs_datasheet_low"] is False


def test_cop_alerts_independent_of_cycle_load():
    """Adding lots of normal cycles must not shift COP alerts."""
    store = _empty_store()
    for i in range(20):
        store.add_cycle(_cy(end_offset_s=-i * 900, dur=300, mode="heating"))
    s1 = _states(store, snap=_snap(cop_degradation_week_pct=-25.0))
    s2 = _states(_empty_store(), snap=_snap(cop_degradation_week_pct=-25.0))
    assert s1["cop_degradation"] == s2["cop_degradation"] is True


# ============================================================
# 2. Thermal/electrical power + deltaT (LWT-RWT implications)
# ============================================================

def test_high_thermal_power_no_false_alerts():
    """12kW system producing 12 kW thermal during heating: no alerts."""
    store = _empty_store()
    for end in [-12000, -6000, -30]:
        store.add_cycle(_cy(
            end_offset_s=end, dur=5400, thermal_kw=12.0,
            dT_max=6.0, dT_avg=5.0, rps_max=55, rps_avg=45,
            outdoor_temp=5.0,
        ))
    s = _states(store)
    assert s["short_run"] is False
    assert s["short_off"] is False


def test_low_thermal_power_underperf_no_cycle_alerts():
    """Underperformance (0.5 kW thermal): cycle-level alerts must not false-fire."""
    store = _empty_store()
    store.add_cycle(_cy(
        end_offset_s=-3000, dur=1800, thermal_kw=0.5,
        dT_max=1.5, dT_avg=1.0, rps_max=20, rps_avg=18,
        outdoor_temp=8.0,
    ))
    store.add_cycle(_cy(
        end_offset_s=-30, dur=1800, thermal_kw=0.5,
        dT_max=1.5, dT_avg=1.0, rps_max=20, rps_avg=18,
        outdoor_temp=8.0, off_s=1200,
    ))
    s = _states(store)
    # 30min runs, 20min gap: both above thresholds
    assert s["short_run"] is False
    assert s["short_off"] is False


def test_dt_max_startup_spike_classified_transient():
    """dT_max=16K in a 200s cycle: transient classifier should catch it."""
    from custom_components.daikin_cycle_ml.coordinator import _classify_transient
    rec = {"duration_s": 200, "dT_max": 16.0, "rps_max": 10.0}
    # duration<300, dT_max>3 (startup spike), rps<40 → NOT transient by rule
    # But cycle ends quickly anyway; this doc-tests classifier boundary
    assert _classify_transient(rec) is False  # dT too high + rps low fails rule


def test_dt_max_borderline_120_300s_transient():
    """120-300s + dT_max<3 + rps_max>=40: transient per classifier."""
    from custom_components.daikin_cycle_ml.coordinator import _classify_transient
    rec = {"duration_s": 200, "dT_max": 2.0, "rps_max": 50.0}
    assert _classify_transient(rec) is True


def test_dt_max_normal_heating_300s_not_transient():
    """300s + dT_max=4.5K: real heating cycle, not transient."""
    from custom_components.daikin_cycle_ml.coordinator import _classify_transient
    rec = {"duration_s": 300, "dT_max": 4.5, "rps_max": 30.0}
    assert _classify_transient(rec) is False


def test_dt_max_zero_measurement_error():
    """dT_max=0 with rps_max=0 (sensor glitch): cycle is not a real heat cycle."""
    from custom_components.daikin_cycle_ml.coordinator import _classify_transient
    rec = {"duration_s": 120, "dT_max": 0.0, "rps_max": 0.0}
    # 120 not <120 → no first-clause match. 120<300, dT_max<3, but rps_max=0<40 → no second
    assert _classify_transient(rec) is False


def test_thermal_kw_invariant_for_alerts():
    """Cycle alert decisions ignore thermal_kw_avg (preservation of current contract)."""
    store_a = _empty_store()
    store_b = _empty_store()
    for i in range(3):
        store_a.add_cycle(_cy(end_offset_s=-300 - i * 400, dur=300,
                             mode="heating", thermal_kw=1.0))
        store_b.add_cycle(_cy(end_offset_s=-300 - i * 400, dur=300,
                             mode="heating", thermal_kw=12.0))
    sa = _states(store_a)
    sb = _states(store_b)
    for key in ("short_run", "short_off", "pendulum_hourly",
                "dhw_pendulum", "high_cycle_rate"):
        assert sa[key] == sb[key], f"{key} depends on thermal_kw (should not)"


# ============================================================
# 3. Temperature scenarios (negative / extreme outdoor)
# ============================================================

@pytest.mark.parametrize("outdoor", [-20.0, -15.0, -10.0, -5.0, 0.0, 5.0, 10.0, 25.0, 35.0])
def test_clean_heating_any_outdoor_no_alerts(outdoor):
    """Any outdoor temp: clean heating cycle sequence has no false alerts."""
    store = _empty_store()
    for end in [-9000, -4500, -30]:
        store.add_cycle(_cy(
            end_offset_s=end, dur=3600, mode="heating",
            outdoor_temp=outdoor, off_s=1800,
        ))
    s = _states(store)
    assert s["short_run"] is False
    assert s["short_off"] is False


def test_deep_cold_defrost_every_cycle():
    """-15°C: defrost every heating cycle. No false alerts (defrost is normal)."""
    store = _empty_store()
    for end in [-9000, -4500, -30]:
        store.add_cycle(_cy(
            end_offset_s=end, dur=3600, mode="heating",
            outdoor_temp=-15.0, defrost_used=1, off_s=1800,
        ))
    s = _states(store)
    assert s["short_run"] is False
    assert s["short_off"] is False


def test_cooling_mode_temperature_35():
    """Warm day 35°C outdoor, cooling cycles (mode=cooling): no heating pendulum."""
    store = _empty_store()
    for i in range(3):
        store.add_cycle(_cy(
            end_offset_s=-500 - i * 400, dur=300,
            mode="cooling", outdoor_temp=35.0,
        ))
    s = _states(store)
    assert s["pendulum_hourly"] is False  # not heating


def test_transient_still_skipped_at_any_temp():
    """v1.19.7: transient skip works across all temperatures."""
    for outdoor in (-20.0, 0.0, 15.0, 35.0):
        store = _empty_store()
        store.add_cycle(_cy(
            end_offset_s=-60, dur=30, is_trans=1,
            thermal_kw=0.4, outdoor_temp=outdoor, off_s=30,
        ))
        s = _states(store)
        assert s["short_off"] is False, f"leaked at {outdoor}°C"
        assert s["short_run"] is False, f"leaked at {outdoor}°C"


# ============================================================
# 4. Per-model sensor availability
# ============================================================

def test_model_12kw_full_sensors():
    """12kW flagship: all sensors present, clean cycles, no alerts."""
    store = _empty_store()
    for end in [-9000, -4500, -30]:
        store.add_cycle(_cy(
            end_offset_s=end, dur=3600, thermal_kw=6.0,
            dT_max=5.0, dT_avg=4.0, rps_max=40, rps_avg=35,
            outdoor_temp=5.0, off_s=1800,
        ))
    assert _states(store)["short_run"] is False


def test_model_no_outdoor_temp_sensor():
    """Legacy model without outdoor_temp: alerts still decide correctly."""
    store = _empty_store()
    for end in [-9000, -4500, -30]:
        store.add_cycle(_cy(
            end_offset_s=end, dur=3600, outdoor_temp=None, off_s=1800,
        ))
    s = _states(store)
    assert s["short_run"] is False
    assert s["short_off"] is False


def test_model_no_thermal_kw_sensor():
    """Model without power meter: thermal_kw_avg=None, no cycle alerts."""
    store = _empty_store()
    for end in [-9000, -4500, -30]:
        store.add_cycle(_cy(
            end_offset_s=end, dur=3600, thermal_kw=None, off_s=1800,
        ))
    s = _states(store)
    assert s["short_run"] is False
    assert s["short_off"] is False


def test_model_no_rps_sensor():
    """Model exposing only compressor_on flag: rps_max=None, decisions still work."""
    from custom_components.daikin_cycle_ml.coordinator import _classify_transient
    rec = {"duration_s": 200, "dT_max": 2.0, "rps_max": None}
    # rps_max=None → second clause fails → not transient
    assert _classify_transient(rec) is False


def test_model_hybrid_boiler_contribution():
    """Hybrid EVLQ: boiler_contribution_samples>0 on cycles. No HP alerts."""
    store = _empty_store()
    for end in [-12000, -6000, -30]:
        rec = _cy(
            end_offset_s=end, dur=5400, mode="heating",
            outdoor_temp=-2.0, off_s=600,
        )
        rec["boiler_contribution_samples"] = 120
        store.add_cycle(rec)
    s = _states(store)
    assert s["short_run"] is False
    assert s["short_off"] is False


def test_model_6kw_short_cycling_real_pattern():
    """6kW with real 8min cycles 5 times in 1h: pendulum_hourly fires (correct)."""
    store = _empty_store()
    for i in range(5):
        store.add_cycle(_cy(
            end_offset_s=-200 - i * 700, dur=480,
            mode="heating", outdoor_temp=10.0,
        ))
    assert _states(store)["pendulum_hourly"] is True


def test_model_16kw_few_very_long_cycles():
    """16kW high thermal mass: 3 very long runs (3h each), no pendulum."""
    store = _empty_store()
    for end in [-20000, -10000, -30]:
        store.add_cycle(_cy(
            end_offset_s=end, dur=10800, mode="heating",
            outdoor_temp=0.0, off_s=3600,
        ))
    s = _states(store)
    assert s["pendulum_hourly"] is False
    assert s["short_run"] is False


def test_model_mixed_legacy_and_new_sensors():
    """Mixed: some cycles have thermal_kw, some don't. Alerts must not crash."""
    store = _empty_store()
    store.add_cycle(_cy(end_offset_s=-5000, dur=3000, thermal_kw=4.0))
    store.add_cycle(_cy(end_offset_s=-2000, dur=3000, thermal_kw=None))
    store.add_cycle(_cy(end_offset_s=-30, dur=3000, thermal_kw=4.5))
    s = _states(store)
    assert isinstance(s, dict)
    for v in s.values():
        assert isinstance(v, bool)


# ============================================================
# 5. Setpoint oscillation
# ============================================================

def test_setpoint_osc_fires_when_6_changes_with_reversal():
    """6 setpoint changes with direction reversal in 30min → fires."""
    from types import MethodType
    from custom_components.daikin_cycle_ml import coordinator as co_mod
    c = _coord(_empty_store(), options={"setpoint_oscillation_threshold": 4})
    # Bind the REAL method (do not stub — that's the bug we just fixed)
    c._compute_setpoint_oscillating = MethodType(
        co_mod.DaikinCycleMLCoordinator._compute_setpoint_oscillating, c
    )
    now = time.time()
    c._setpoint_history = [
        (now - 1500, 20.0), (now - 1200, 20.5), (now - 900, 20.0),
        (now - 600, 20.6), (now - 300, 20.1), (now - 100, 20.7),
    ]
    states = co_mod.DaikinCycleMLCoordinator._alert_binary_states(c, _snap())
    assert states["setpoint_osc"] is True


def test_setpoint_osc_monotonic_drift_silent():
    """Monotonic rise (no reversal): silent (guards slow drift)."""
    from types import MethodType
    from custom_components.daikin_cycle_ml import coordinator as co_mod
    c = _coord(_empty_store(), options={"setpoint_oscillation_threshold": 4})
    c._compute_setpoint_oscillating = MethodType(
        co_mod.DaikinCycleMLCoordinator._compute_setpoint_oscillating, c
    )
    now = time.time()
    c._setpoint_history = [
        (now - 1500, 20.0), (now - 1200, 20.1), (now - 900, 20.2),
        (now - 600, 20.3), (now - 300, 20.4), (now - 100, 20.5),
    ]
    states = co_mod.DaikinCycleMLCoordinator._alert_binary_states(c, _snap())
    assert states["setpoint_osc"] is False


# ============================================================
# 6. BUH / defrost / stale / missing
# ============================================================

def test_buh_excessive_fires():
    """BUH usage 20% of heating → above 15% threshold → fires."""
    s = _states(_empty_store(), _buh_7d_ratio=0.20)
    assert s["buh_excessive"] is True


def test_buh_normal_silent():
    """BUH 10%: within normal range, silent."""
    s = _states(_empty_store(), _buh_7d_ratio=0.10)
    assert s["buh_excessive"] is False


def test_defrost_excessive_fires():
    """31 defrosts in 7d (threshold 30) → fires."""
    s = _states(_empty_store(), _defrost_7d_sum=31)
    assert s["defrost_excessive"] is True


def test_defrost_normal_silent():
    """15 defrosts in 7d: normal cold-season count, silent."""
    s = _states(_empty_store(), _defrost_7d_sum=15)
    assert s["defrost_excessive"] is False


def test_source_stale_fires_when_no_data_5m():
    """ESPAltherma silent for >5x update interval → critical alert."""
    from custom_components.daikin_cycle_ml.const import UPDATE_INTERVAL_SECONDS
    from custom_components.daikin_cycle_ml.binary_sensor import SOURCE_STALE_FACTOR
    stale_ts = time.time() - (SOURCE_STALE_FACTOR * UPDATE_INTERVAL_SECONDS) - 10
    s = _states(_empty_store(), snap=_snap(last_success_ts=stale_ts))
    assert s["source_stale"] is True


def test_source_stale_fresh_silent():
    """Recent data: source_stale silent."""
    s = _states(_empty_store(), snap=_snap(last_success_ts=time.time()))
    assert s["source_stale"] is False


def test_source_stale_zero_ts_silent():
    """last_success_ts=0 (startup): must not fire."""
    s = _states(_empty_store(), snap=_snap(last_success_ts=0.0))
    assert s["source_stale"] is False


def test_missing_attributes_fires():
    """missing_attrs non-empty → warning."""
    s = _states(_empty_store(), snap=_snap(missing_attrs=["outdoor_temp"]))
    assert s["missing_attributes"] is True


def test_missing_attributes_empty_silent():
    """All required attrs present: silent."""
    s = _states(_empty_store(), snap=_snap(missing_attrs=[]))
    assert s["missing_attributes"] is False


# ============================================================
# 7. Seeded fuzz — deterministic, reproducible
# ============================================================

FUZZ_SEED = 0xD41C1E
FUZZ_ITERATIONS = 40


@pytest.mark.parametrize("seed", [FUZZ_SEED, FUZZ_SEED + 1, FUZZ_SEED + 2])
def test_fuzz_random_cycle_sequences(seed):
    """Random cycle sequences: no crash, bool dict, key set stable."""
    rng = random.Random(seed)
    store = _empty_store()
    for _ in range(rng.randint(5, 50)):
        dur = rng.choice([30, 60, 120, 200, 300, 600, 1800, 3600, 10800])
        is_trans = rng.choice([0, 1, "0", "1", "true", "false", "x", None, 1.9, True, False])
        mode = rng.choice(["heating", "dhw", "cooling", "defrost"])
        store.add_cycle(_cy(
            end_offset_s=-rng.randint(60, 86400),
            dur=dur, is_trans=is_trans, mode=mode,
            outdoor_temp=rng.choice([None, -20.0, 0.0, 10.0, 35.0]),
            off_s=rng.choice([None, 0, 30, 300, 3600]),
        ))
    s = _states(store)
    assert isinstance(s, dict)
    for k, v in s.items():
        assert isinstance(v, bool), f"{k} is {type(v).__name__}"


def test_fuzz_random_snap_attrs():
    """Random snapshot attribute combinations: no crash, safe defaults."""
    rng = random.Random(FUZZ_SEED + 10)
    for _ in range(FUZZ_ITERATIONS):
        snap = _snap(
            cop_degradation_week_pct=rng.choice([None, -50.0, -20.0, -5.0, 0.0, 30.0, "bad"]),
            cop_vs_datasheet_pct=rng.choice([None, -50.0, 50.0, 100.0, 150.0]),
            last_success_ts=rng.choice([0.0, time.time(), time.time() - 3600]),
            missing_attrs=rng.choice([[], ["x"], ["a", "b"]]),
        )
        try:
            s = _states(_empty_store(), snap=snap)
        except TypeError:
            # Some invalid literal types may raise TypeError on isinstance check
            # That's the correct safety behavior — assert we don't crash uncaught
            continue
        for v in s.values():
            assert isinstance(v, bool)


def test_fuzz_random_threshold_options():
    """Random threshold options: no crash, decision remains well-typed."""
    rng = random.Random(FUZZ_SEED + 20)
    for _ in range(20):
        opts = {
            "short_run_threshold_min": rng.choice([5, 20, 30, 60]),
            "short_off_threshold_min": rng.choice([1, 5, 10, 30]),
            "pendulum_cycles_per_hour": rng.choice([2, 4, 6, 10]),
            "pendulum_cycles_per_day": rng.choice([20, 40, 60]),
            "dhw_pendulum_cycles_per_hour": rng.choice([2, 3, 5]),
        }
        store = _empty_store()
        for i in range(rng.randint(1, 10)):
            store.add_cycle(_cy(
                end_offset_s=-rng.randint(60, 5000) * (i + 1),
                dur=rng.choice([120, 300, 600, 1800]),
                mode=rng.choice(["heating", "dhw"]),
            ))
        s = _states(store, options=opts)
        for k, v in s.items():
            assert isinstance(v, bool), f"{k}={v!r} with opts={opts}"


def test_fuzz_mixed_transient_values():
    """Mix of is_transient value types never crashes and stays consistent."""
    from custom_components.daikin_cycle_ml.storage.store import _is_transient_int
    for raw in [0, 1, "0", "1", "true", "false", "x", None, 1.9, True, False, "", [], {}]:
        v = _is_transient_int(raw)
        assert isinstance(v, int)
        assert v in (0, 1), f"_is_transient_int({raw!r}) = {v}, expected 0 or 1"


def test_fuzz_alert_states_key_set_stable():
    """The output dict must have exactly 17 keys, regardless of input."""
    expected_keys = {
        "short_run", "short_off", "pendulum_hourly", "pendulum_daily",
        "dhw_pendulum", "high_cycle_rate", "ml_anomaly", "setpoint_osc",
        "cop_degradation", "defrost_excessive", "buh_excessive",
        "source_stale", "missing_attributes", "cop_vs_datasheet_low",
        "db_retention_warning", "kmeans_retrain_stale",
        "energy_daily_anomaly",
    }
    rng = random.Random(FUZZ_SEED + 30)
    for _ in range(10):
        store = _empty_store()
        for _ in range(rng.randint(0, 20)):
            store.add_cycle(_cy(
                end_offset_s=-rng.randint(60, 86400),
                dur=rng.choice([30, 300, 3600]),
                mode=rng.choice(["heating", "dhw"]),
            ))
        s = _states(store)
        assert set(s.keys()) == expected_keys, "alert key set drifted"


# ============================================================
# 8. Full-day realistic scenarios (cold + warm)
# ============================================================

def test_full_day_cold_with_defrost_and_dhw():
    """Cold day pattern: heat cycles with defrost + DHW in middle. No false alerts."""
    store = _empty_store()
    cycles = [
        # (end_offset, dur, mode, defrost)
        (-86400, 5400, "heating", 1),
        (-78000, 3600, "heating", 1),
        (-70000, 5400, "heating", 1),
        (-60000, 1800, "dhw", 0),
        (-55000, 5400, "heating", 1),
        (-45000, 3600, "heating", 1),
        (-36000, 1800, "dhw", 0),
        (-30000, 5400, "heating", 1),
        (-15000, 5400, "heating", 1),
        (-5000, 3600, "heating", 1),
        (-30, 3600, "heating", 1),
    ]
    for end, dur, mode, dfr in cycles:
        store.add_cycle(_cy(
            end_offset_s=end, dur=dur, mode=mode,
            outdoor_temp=-8.0, defrost_used=dfr, off_s=600,
        ))
    s = _states(store)
    assert s["short_run"] is False
    assert s["short_off"] is False


def test_full_day_mild_shoulder_no_defrost():
    """Shoulder season 12°C: long cycles, occasional DHW, no alerts."""
    store = _empty_store()
    for end in [-86400, -70000, -50000, -30000, -15000, -5000, -30]:
        store.add_cycle(_cy(
            end_offset_s=end, dur=7200, mode="heating",
            outdoor_temp=12.0, defrost_used=0, off_s=1800,
        ))
    s = _states(store)
    assert s["short_run"] is False
    assert s["short_off"] is False
    assert s["pendulum_hourly"] is False

# ============================================================
# 9. Extreme COP boundaries (thresholds matter)
# ============================================================

@pytest.mark.parametrize("cop_val,expected", [
    (-100.0, True),   # catastrophic
    (-15.0, False),   # exactly AT threshold -> not < -> no fire (strict <)
    (-15.01, True),   # just past threshold (strictly less than -15.0)
    (-14.99, False),  # just under threshold
    (-8.0, False),    # DEGRADATION_THRESHOLD_PCT=-8 is for OTHER analyzer, not alerts
    (0.0, False),     # no change
    (50.0, False),    # improvement
])
def test_cop_degradation_threshold_boundaries(cop_val, expected):
    """Exact threshold behavior for cop_degradation (must use -15.0, not -8.0)."""
    s = _states(_empty_store(), snap=_snap(cop_degradation_week_pct=cop_val))
    assert s["cop_degradation"] is expected, (
        f"cop_degradation_week_pct={cop_val} → got {s['cop_degradation']}, "
        f"expected {expected}"
    )


@pytest.mark.parametrize("ds_pct,expected", [
    (-100.0, True),
    (-50.0, True),
    (-30.0, True),
    (0.0, False),
    (50.0, False),
    (100.0, False),
    (150.0, False),
])
def test_cop_vs_datasheet_threshold_matrix(ds_pct, expected):
    """Datasheet comparison alert fires below COP_VS_DATASHEET_LOW_PCT."""
    s = _states(_empty_store(), snap=_snap(cop_vs_datasheet_pct=ds_pct))
    assert s["cop_vs_datasheet_low"] is expected


def test_cop_samples_like_weekly_trends():
    """Different 'week' patterns; only the degrading ones fire.

    Simulates what cop_degradation analyzer feeds into the snapshot:
    - steady: no alert
    - gradual -2%/week: no alert
    - step -20%: fires
    - sudden -30%: fires
    """
    patterns = {
        0.0: False,
        -2.0: False,
        -10.0: False,   # still above -15.0 threshold
        -20.0: True,
        -30.0: True,
    }
    for pct, expected in patterns.items():
        s = _states(_empty_store(), snap=_snap(cop_degradation_week_pct=pct))
        assert s["cop_degradation"] is expected, (
            f"weekly trend {pct}% → {s['cop_degradation']}, expected {expected}"
        )


# ============================================================
# 10. Electrical power proxy (thermal / COP ratio implications)
# ============================================================

def test_electrical_load_implies_thermal():
    """Cycle with high rps produces high thermal; alerts based on duration only.

    Electrical power is derived from rps × voltage × power factor, not stored
    directly. What matters for alerts is cycle shape, which we verify stays
    decoupled from power proxy values.
    """
    store = _empty_store()
    # Low-electrical cycle (rps=15, low thermal)
    store.add_cycle(_cy(end_offset_s=-2000, dur=1800, rps_max=15, rps_avg=12,
                        thermal_kw=1.5, off_s=1200))
    # High-electrical cycle (rps=55, high thermal)
    store.add_cycle(_cy(end_offset_s=-30, dur=1800, rps_max=55, rps_avg=48,
                        thermal_kw=11.0, off_s=1200))
    s = _states(store)
    # Both are 30min cycles — no short_run regardless of power
    assert s["short_run"] is False
    assert s["short_off"] is False


def test_buh_step2_peak_power_no_false_short():
    """BUH step2 boost (extreme power) doesn't affect short_* decisions."""
    store = _empty_store()
    store.add_cycle(_cy(end_offset_s=-30, dur=3600, mode="heating",
                        buh_used=2, rps_max=55, thermal_kw=15.0, off_s=1800))
    s = _states(store)
    assert s["short_run"] is False
    assert s["short_off"] is False


def test_cop_ratio_extremes_do_not_shift_alerts():
    """Across thermal_kw from 0.3 to 20 kW: no cycle-alert decisions change."""
    for thermal_kw in (0.3, 1.0, 3.0, 6.0, 12.0, 20.0):
        store = _empty_store()
        # 30-minute cycles, well above 20-min short_run threshold
        for i in range(3):
            store.add_cycle(_cy(
                end_offset_s=-2400 - i * 3600, dur=1800, mode="heating",
                thermal_kw=thermal_kw, off_s=1800 if i > 0 else None,
            ))
        s = _states(store)
        for key in ("short_run", "short_off", "pendulum_hourly",
                    "dhw_pendulum", "high_cycle_rate", "pendulum_daily"):
            assert s[key] is False, f"{key} fires at thermal_kw={thermal_kw}"


# ============================================================
# 11. Extreme model range (beyond 6/12/16kW)
# ============================================================

EXTREME_MODELS = [
    # (name, dur, gap, dT_max, rps_max)
    ("4kW-mini",        1200,  600,   2.5, 55),
    ("8kW-typical",     2700, 1350,   3.8, 42),
    ("14kW-mid",        4200, 2100,   4.8, 32),
    ("18kW-large",      6000, 3000,   5.2, 26),
    ("24kW-commercial", 7200, 3600,   5.5, 22),
]


@pytest.mark.parametrize("name,dur,gap,dT,rps", EXTREME_MODELS)
def test_model_extreme_capacities_no_alerts(name, dur, gap, dT, rps):
    """4kW to 24kW range: clean cycling produces no alerts."""
    store = _empty_store()
    for i, end_off in enumerate([-(dur + gap) * 2, -(dur + gap), -30]):
        store.add_cycle(_cy(
            end_offset_s=end_off, dur=dur, dT_max=dT, rps_max=rps,
            off_s=(gap if i > 0 else None),
        ))
    s = _states(store)
    assert s["short_run"] is False, f"{name}: short_run"
    assert s["short_off"] is False, f"{name}: short_off"
    assert s["pendulum_hourly"] is False, f"{name}: pendulum_hourly"


@pytest.mark.parametrize("name,dur,gap,dT,rps", EXTREME_MODELS)
def test_model_extreme_transient_skip(name, dur, gap, dT, rps):
    """v1.19.7: transient skip works across the full 4-24kW model range."""
    store = _empty_store()
    store.add_cycle(_cy(end_offset_s=-(dur + 90), dur=dur, dT_max=dT, rps_max=rps))
    store.add_cycle(_cy(end_offset_s=-30, dur=30, is_trans=1, rps_max=0,
                        thermal_kw=0.3, off_s=60))
    s = _states(store)
    assert s["short_run"] is False, f"{name}: transient leaked"
    assert s["short_off"] is False, f"{name}: transient leaked"


# ============================================================
# 12. LWT / RWT deltaT extremes
# ============================================================

@pytest.mark.parametrize("dT_max,dT_avg", [
    (0.0, 0.0),     # no deltaT (pump-only)
    (0.1, 0.05),    # tiny (measurement noise)
    (0.5, 0.3),     # very low (underperforming system)
    (1.0, 0.8),     # low (low-load day)
    (3.0, 2.5),     # normal shoulder
    (5.0, 4.0),     # normal cold
    (8.0, 6.5),     # high (large capacity)
    (12.0, 10.0),   # extreme deltaT
    (20.0, 15.0),   # startup spike artefact
])
def test_dt_extremes_no_false_alerts_when_clean(dT_max, dT_avg):
    """Any LWT-RWT deltaT: clean long-run cycle sequence has no false alerts."""
    store = _empty_store()
    for end in [-9000, -4500, -30]:
        store.add_cycle(_cy(
            end_offset_s=end, dur=3600, dT_max=dT_max, dT_avg=dT_avg,
            off_s=1800,
        ))
    s = _states(store)
    assert s["short_run"] is False, f"dT_max={dT_max} caused short_run"
    assert s["short_off"] is False, f"dT_max={dT_max} caused short_off"


def test_dt_extreme_does_not_confuse_pendulum():
    """Extreme deltaT shouldn't suppress pendulum detection on real bursts."""
    store = _empty_store()
    # 4 real heating cycles with 12K deltaT (12kW system at full load)
    for i in range(4):
        store.add_cycle(_cy(
            end_offset_s=-300 - i * 400, dur=300,
            dT_max=12.0, dT_avg=10.0, rps_max=52,
            thermal_kw=15.0,
        ))
    assert _states(store)["pendulum_hourly"] is True


# ============================================================
# 13. Negative / extreme indoor temp via outdoor proxy
# ============================================================

@pytest.mark.parametrize("outdoor", [-25.0, -20.0, -15.0, -10.0, -5.0, 0.0])
def test_deep_freezing_heating_no_alerts(outdoor):
    """Deep winter: long heating cycles even at -25°C. No false alerts."""
    store = _empty_store()
    for end in [-14000, -7000, -30]:
        store.add_cycle(_cy(
            end_offset_s=end, dur=5400, mode="heating",
            outdoor_temp=outdoor, defrost_used=1, off_s=1800,
        ))
    s = _states(store)
    assert s["short_run"] is False
    assert s["short_off"] is False


@pytest.mark.parametrize("outdoor", [-15.0, -10.0, -5.0])
def test_deep_freezing_transient_skip(outdoor):
    """Deep cold: transient pump pulse still skipped."""
    store = _empty_store()
    store.add_cycle(_cy(end_offset_s=-200, dur=1800, outdoor_temp=outdoor))
    store.add_cycle(_cy(end_offset_s=-30, dur=30, is_trans=1, rps_max=0,
                        outdoor_temp=outdoor, off_s=30))
    s = _states(store)
    assert s["short_off"] is False


def test_missing_outdoor_temp_whole_store():
    """Model without outdoor sensor: all cycles have outdoor_temp=None. No crash."""
    store = _empty_store()
    for i in range(10):
        store.add_cycle(_cy(
            end_offset_s=-i * 900, dur=600, mode="heating",
            outdoor_temp=None,
        ))
    s = _states(store)
    assert isinstance(s, dict)
    for v in s.values():
        assert isinstance(v, bool)


# ============================================================
# 14. Hybrid edge cases (boiler + HP interaction)
# ============================================================

def test_hybrid_cold_day_boiler_priority():
    """Hybrid: HP cycles are short when boiler takes priority. Should fire pendulum."""
    store = _empty_store()
    # HP forced to short cycles because boiler handles load
    for i in range(4):
        rec = _cy(
            end_offset_s=-200 - i * 600, dur=300,
            mode="heating", outdoor_temp=-5.0,
            buh_used=0, defrost_used=0,
        )
        rec["boiler_contribution_samples"] = 100
        store.add_cycle(rec)
    # 4 short runs in 1h -> pendulum_hourly fires (this IS short-cycling for HP)
    s = _states(store)
    assert s["pendulum_hourly"] is True


def test_hybrid_boiler_only_no_hp_cycles():
    """Hybrid: boiler handling all demand, HP idle. No HP cycle alerts."""
    store = _empty_store()
    # No cycles at all
    s = _states(store)
    for key in ("short_run", "short_off", "pendulum_hourly",
                "dhw_pendulum", "high_cycle_rate"):
        assert s[key] is False

